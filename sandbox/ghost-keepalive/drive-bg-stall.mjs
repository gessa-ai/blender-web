// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// ghost-keepalive STALL REPRODUCTION (the real A/B). The present-gated worker rAF
// only stalls when the tab stops compositing. Playwright's DEFAULT Chromium flags
// (--disable-backgrounding-occluded-windows / --disable-renderer-backgrounding /
// --disable-background-timer-throttling) keep background tabs composited, which is
// why drive-discriminator.mjs could not hide the tab. Here we launch with those
// three flags REMOVED (ignoreDefaultArgs) so a background tab actually goes
// document.visibilityState=hidden and its worker rAF pauses.
//
// Boot ON and OFF; arm a one-shot bpy.app.timer (no tag_redraw) at 8 s; hide the
// blender tab BEFORE it would fire (bring a blank tab to front); wait 30 s hidden;
// read the WM tick counter of the hidden tab (main-thread CDP evaluate, not rAF-gated).
//   OFF (rAF)      : hidden -> rAF paused -> loop FREEZES (tick ~0, timer never fires).
//   ON  (setTimeout): hidden -> setTimeout throttled but alive -> loop TICKS, timer fires.
//
// Evidence -> sandbox/ghost-keepalive/evidence/bg-stall.{log,json}.

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = process.env.BW_BASE || "http://localhost:8128";
const ENTRY = "/windowed.html";
const OUTDIR = "/Users/paws/blender-web/sandbox/ghost-keepalive/evidence";
fs.mkdirSync(OUTDIR, { recursive: true });
const BOOT_MS = 60000;

function ts() { return new Date().toISOString().replace("T", " ").replace("Z", ""); }
const LOG = [];
function log(s) { const l = `[${ts()}] ${s}`; console.log(l); LOG.push(l); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const TIMER_PYEXPR = [
  "import bpy, os, time",
  "_t0 = time.time()",
  "def _f():",
  "    os.write(2, (\"BW_KEEPALIVE_TIMER_FIRED elapsed_ms=%d\\n\" % int((time.time()-_t0)*1000)).encode())",
  "    return None",
  "bpy.app.timers.register(_f, first_interval=8.0)",
  "os.write(2, b\"BW_KEEPALIVE_TIMER_ARMED\\n\")",
].join("\n");

function urlFor(params) {
  const u = new URL(BASE + ENTRY);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
  return u.toString();
}
async function counters(page) {
  return page.evaluate(() => {
    const m = window.__bwModule;
    return m ? { tick: Number(m._bw_wm_tick_count()), present: Number(m._bw_present_count()) } : null;
  });
}
async function waitWM(page) {
  await page.waitForFunction(() => {
    const s = document.querySelector("#state");
    return s && s.textContent.includes("main loop (WM_main)");
  }, null, { timeout: BOOT_MS });
}

const out = {};
async function run(browser, enabled) {
  const key = enabled ? "BG_on" : "BG_off";
  const params = { pyexpr: TIMER_PYEXPR };
  if (!enabled) params.keepalive = "0";
  const ctx = await browser.newContext({ viewport: { width: 1000, height: 700 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const r = { fired: false };
  page.on("console", (m) => { if (m.text().includes("BW_KEEPALIVE_TIMER_FIRED")) r.fired = true; });
  try {
    await page.goto(urlFor(params), { waitUntil: "domcontentloaded" });
    await waitWM(page);
    await sleep(2000); // hide well before the 8 s one-shot would fire
    const c0 = await counters(page);
    const blank = await ctx.newPage();
    await blank.goto("about:blank");
    await blank.bringToFront();
    await sleep(1200);
    const vis = await page.evaluate(() => document.visibilityState);
    log(`${key}: blender tab visibilityState=${vis} after hiding; waiting 30 s...`);
    await sleep(30000);
    const c1 = await counters(page);
    r.visHidden = vis;
    r.tickDelta = c1.tick - c0.tick;
    r.presentDelta = c1.present - c0.present;
    log(`${key}: hidden 30 s -> tickDelta=${r.tickDelta}  presentDelta=${r.presentDelta}  timerFired=${r.fired}  (vis=${vis})`);
    await page.bringToFront();
  } catch (e) { r.error = String(e && e.message ? e.message : e); log(`${key}: ERROR ${r.error}`); }
  finally { await ctx.close(); }
  out[key] = r;
}

(async () => {
  log(`ghost-keepalive BG stall test: base=${BASE} (default anti-throttle flags REMOVED)`);
  const browser = await chromium.launch({
    headless: false,
    ignoreDefaultArgs: [
      "--disable-backgrounding-occluded-windows",
      "--disable-renderer-backgrounding",
      "--disable-background-timer-throttling",
    ],
  });
  try {
    await run(browser, false); // OFF first (baseline stall)
    await run(browser, true);  // ON (fix)
  } finally { await browser.close(); }

  const hid = (out.BG_off && out.BG_off.visHidden === "hidden") && (out.BG_on && out.BG_on.visHidden === "hidden");
  const offStalled = out.BG_off && out.BG_off.tickDelta <= 5 && out.BG_off.fired === false;
  const onAlive = out.BG_on && out.BG_on.tickDelta > 5 && out.BG_on.fired === true;
  out._verdicts = { tab_actually_hidden: hid, off_rAF_stalls: offStalled, on_keepalive_survives: onAlive };
  fs.writeFileSync(path.join(OUTDIR, "bg-stall.log"), LOG.join("\n"));
  fs.writeFileSync(path.join(OUTDIR, "bg-stall.json"), JSON.stringify(out, null, 2));
  log(`VERDICTS: ${JSON.stringify(out._verdicts)}`);
  const proven = hid && offStalled && onAlive;
  log(`STALL REPRODUCED AND FIXED: ${proven ? "YES" : "NO (see log)"}`);
  process.exit(proven ? 0 : 1);
})();
