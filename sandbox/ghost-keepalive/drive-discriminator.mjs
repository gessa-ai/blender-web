// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// ghost-keepalive A/B DISCRIMINATOR (companion to drive-keepalive.mjs).
//
// drive-keepalive.mjs proved the mandated bar (liveness after 30 s idle, no idle
// GPU burn, regression). This adds the honest A/B characterisation of keepalive
// ON vs OFF, in BOTH tab states:
//
//   FG (foreground, continuously composited): measure tick + present deltas over a
//       20 s idle. Finding: a VISIBLE tab keeps the worker rAF firing, so the OFF
//       (rAF) baseline does NOT stall here - it spins the loop at ~60 Hz; keepalive
//       ON instead backs off to ~4 Hz. Neither submits frames continuously at idle.
//
//   BG (backgrounded, compositing stopped): the real stall condition. Boot, arm a
//       short one-shot timer, then hide the tab (bring a blank tab to front) and
//       read the WM tick counter of the hidden tab over 30 s.
//         OFF (rAF): a hidden tab pauses requestAnimationFrame -> the loop FREEZES
//              (tick delta ~0, timer never fires) = the M7b idle stall, reproduced.
//         ON (setTimeout): a hidden tab throttles but still fires setTimeout -> the
//              loop KEEPS TICKING (tick delta > 0, timer fires) = the stall is fixed.
//
// Evidence -> sandbox/ghost-keepalive/evidence/discriminator.{log,json}.

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

// one-shot timer, no tag_redraw, short interval for the BG test
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

async function foreground(browser, enabled) {
  const key = enabled ? "FG_on" : "FG_off";
  const params = {};
  if (!enabled) params.keepalive = "0";
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const r = {};
  try {
    await page.goto(urlFor(params), { waitUntil: "domcontentloaded" });
    await waitWM(page);
    await sleep(3000); // let boot + grace settle so we measure true idle
    const c0 = await counters(page);
    await sleep(20000);
    const c1 = await counters(page);
    r.tickDelta = c1.tick - c0.tick;
    r.presentDelta = c1.present - c0.present;
    r.tickHz = +(r.tickDelta / 20).toFixed(1);
    r.presentHz = +(r.presentDelta / 20).toFixed(2);
    log(`${key}: FG 20 s idle -> tick ${r.tickDelta} (${r.tickHz} Hz)  present ${r.presentDelta} (${r.presentHz} Hz)`);
  } catch (e) { r.error = String(e && e.message ? e.message : e); log(`${key}: ERROR ${r.error}`); }
  finally { await ctx.close(); }
  out[key] = r;
}

async function backgrounded(browser, enabled) {
  const key = enabled ? "BG_on" : "BG_off";
  const params = { pyexpr: TIMER_PYEXPR };
  if (!enabled) params.keepalive = "0";
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const r = { fired: false };
  page.on("console", (m) => { if (m.text().includes("BW_KEEPALIVE_TIMER_FIRED")) r.fired = true; });
  try {
    await page.goto(urlFor(params), { waitUntil: "domcontentloaded" });
    await waitWM(page);
    await sleep(2500); // brief settle, but hide BEFORE the 8 s timer would fire
    const c0 = await counters(page);
    const vis0 = await page.evaluate(() => document.visibilityState);
    // Hide the blender tab by bringing a blank tab in the SAME context to the front.
    const blank = await ctx.newPage();
    await blank.goto("about:blank");
    await blank.bringToFront();
    await sleep(600);
    const visHidden = await page.evaluate(() => document.visibilityState); // read on the hidden page (main-thread JS, not rAF-gated)
    log(`${key}: visibility ${vis0} -> ${visHidden} (blender tab hidden); waiting 30 s backgrounded...`);
    await sleep(30000);
    const c1 = await counters(page); // still readable while hidden
    r.tickDelta = c1.tick - c0.tick;
    r.presentDelta = c1.present - c0.present;
    r.visHidden = visHidden;
    log(`${key}: BG 30 s -> tick ${r.tickDelta}  present ${r.presentDelta}  timerFired=${r.fired}`);
    await page.bringToFront(); // restore (avoid leaving it wedged)
  } catch (e) { r.error = String(e && e.message ? e.message : e); log(`${key}: ERROR ${r.error}`); }
  finally { await ctx.close(); }
  out[key] = r;
}

(async () => {
  log(`ghost-keepalive discriminator: base=${BASE}`);
  const browser = await chromium.launch({ headless: false });
  try {
    await foreground(browser, true);
    await foreground(browser, false);
    await backgrounded(browser, true);
    await backgrounded(browser, false);
  } finally { await browser.close(); }

  // Honest verdicts.
  const bgOnAlive = (out.BG_on && out.BG_on.tickDelta > 5 && out.BG_on.fired === true);
  const bgOffStalled = (out.BG_off && out.BG_off.tickDelta <= 5 && out.BG_off.fired === false);
  out._verdicts = {
    background_keepalive_keeps_loop_alive: bgOnAlive,
    background_rAF_baseline_stalls: bgOffStalled,
    foreground_keepalive_idles_slower_than_rAF:
      !!(out.FG_on && out.FG_off && out.FG_on.tickHz < out.FG_off.tickHz),
  };
  fs.writeFileSync(path.join(OUTDIR, "discriminator.log"), LOG.join("\n"));
  fs.writeFileSync(path.join(OUTDIR, "discriminator.json"), JSON.stringify(out, null, 2));
  log(`VERDICTS: ${JSON.stringify(out._verdicts)}`);
  const ok = bgOnAlive && bgOffStalled;
  log(`STALL-FIX PROVEN: ${ok ? "YES" : "NO"}`);
  process.exit(ok ? 0 : 1);
})();
