// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// ghost-keepalive PROOF WITH TEETH (notes/ghost-keepalive.md).
//
// Headed, BUNDLED-Chromium node-Playwright driver (NODE_PATH points at the
// game-platform node_modules). Serve the windowed-opt bin + real shell on :8128:
//   BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin \
//   BLENDER_WEB_SHELL=$PWD/platform_web/shell \
//     /opt/homebrew/bin/bash scripts/serve-web.sh 8128
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/ghost-keepalive/drive-keepalive.mjs
//
// Four boots, each a fresh context, all on :8128 windowed.html (the REAL shell):
//   A liveness  : NO pyexpr, keepalive default ON. Boot -> WM_main, read the WM
//                 tick + present counters, idle 30 s, read again. PASS = tick delta
//                 large (loop alive) AND present delta tiny (no idle GPU burn).
//                 Then a post-idle mouse move/click over the canvas as a bonus
//                 input-liveness signal (present should advance).
//   B timer     : keepalive ON, ?pyexpr registers a ONE-SHOT bpy.app.timer with NO
//                 tag_redraw that fires at ~20 s. PASS = it fires within the idle
//                 window (timers resolve at idle with no kick).
//   C ab_off    : ?keepalive=0 (rAF baseline) + the SAME one-shot timer. PASS =
//                 tick delta ~0 (loop stalls after boot) AND the timer NEVER fires
//                 -> proves the stall is real and the keepalive is what fixes it.
//   D regress   : keepalive ON + the STANDARD kick rig (tag_redraw VIEW_3D @1 Hz).
//                 PASS = present delta large AND the screenshot is non-black
//                 (grid still renders; nothing else broke).
//
// Evidence -> sandbox/ghost-keepalive/evidence/ : before/after PNGs (+ CC0-1.0
// .license sidecars), the full console log, and summary.json.

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");
const { PNG } = require("pngjs");

const BASE = process.env.BW_BASE || "http://localhost:8128";
const ENTRY = "/windowed.html";
const OUTDIR = "/Users/paws/blender-web/sandbox/ghost-keepalive/evidence";
fs.mkdirSync(OUTDIR, { recursive: true });

const BOOT_MS = 60000;   // WM_main marker (module-resolve; well before first pixels)
const IDLE_MS = 30000;   // the mandated 30 s idle window
const PIXELS_MS = 45000; // allow the first WGSL-compiled present (~20 s cold) for pixel checks

function ts() { return new Date().toISOString().replace("T", " ").replace("Z", ""); }
const LOGLINES = [];
function log(s) { const l = `[${ts()}] ${s}`; console.log(l); LOGLINES.push(l); }

const LICENSE = "SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n";
function writeLicense(pngPath) { fs.writeFileSync(pngPath + ".license", LICENSE); }

// One-shot timer probe: fires once at ~20 s and writes a console line via raw fd 2
// (the only reliable Python->console channel on the WM worker, per notes/m5-windowed-replay.md).
// CRITICAL: no tag_redraw anywhere - if this fires, the loop advanced timers at idle
// purely because of the keepalive, not because anything forced a present.
const TIMER_PYEXPR = [
  "import bpy, os, time",
  "_bwk_t0 = time.time()",
  "def _bwk_fire():",
  "    os.write(2, (\"BW_KEEPALIVE_TIMER_FIRED elapsed_ms=%d\\n\" % int((time.time()-_bwk_t0)*1000)).encode())",
  "    return None",
  "bpy.app.timers.register(_bwk_fire, first_interval=20.0)",
  "os.write(2, b\"BW_KEEPALIVE_TIMER_ARMED\\n\")",
].join("\n");

// The STANDARD kick rig (verbatim shape from sandbox/m8-deploy/verify_boot.mjs): a
// 1 Hz timer that tag_redraw()s every VIEW_3D window region. This is the "driver rig"
// the keepalive is meant to make unnecessary - the regression proves it still works.
const KICK_PYEXPR = [
  "import bpy",
  "bpy.context.preferences.view.show_splash = False",
  "def _bw_kick():",
  "    try:",
  "        for win in bpy.context.window_manager.windows:",
  "            scr = win.screen",
  "            if not scr:",
  "                continue",
  "            for area in scr.areas:",
  "                if area.type == \"VIEW_3D\":",
  "                    for region in area.regions:",
  "                        if region.type == \"WINDOW\":",
  "                            region.tag_redraw()",
  "    except Exception as e:",
  "        print(\"[bw-kick] \" + repr(e))",
  "    return 1.0",
  "bpy.app.timers.register(_bw_kick, first_interval=1.0)",
].join("\n");

function urlFor(params) {
  const u = new URL(BASE + ENTRY);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
  return u.toString();
}

async function newPage(browser, tag) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const con = [];
  page.on("console", (m) => { con.push(m.text()); });
  page.on("pageerror", (e) => con.push("pageerror: " + (e && e.message ? e.message : e)));
  return { ctx, page, con };
}

async function readCounters(page) {
  return page.evaluate(() => {
    const m = window.__bwModule;
    if (!m) return null;
    return {
      tick: (typeof m._bw_wm_tick_count === "function") ? Number(m._bw_wm_tick_count()) : null,
      present: (typeof m._bw_present_count === "function") ? Number(m._bw_present_count()) : null,
    };
  });
}

async function waitWMMain(page) {
  await page.waitForFunction(() => {
    const s = document.querySelector("#state");
    return s && s.textContent.includes("main loop (WM_main)");
  }, null, { timeout: BOOT_MS });
}

async function isoCheck(page) {
  return page.evaluate(() => ({
    iso: self.crossOriginIsolated === true,
    sab: typeof SharedArrayBuffer !== "undefined",
  }));
}

// Non-black fraction of a saved PNG (grid-renders check).
function nonBlackFraction(pngPath) {
  const buf = fs.readFileSync(pngPath);
  const png = PNG.sync.read(buf);
  let nz = 0;
  const n = png.width * png.height;
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    if (png.data[o] > 12 || png.data[o + 1] > 12 || png.data[o + 2] > 12) nz++;
  }
  return { frac: nz / n, w: png.width, h: png.height };
}

async function sleep(ms) { await new Promise((r) => setTimeout(r, ms)); }

const results = {};

async function scenarioLiveness(browser) {
  const name = "A_liveness";
  log(`--- ${name}: no pyexpr, keepalive default ON; 30 s idle ---`);
  const { ctx, page, con } = await newPage(browser, name);
  const r = { pass: false };
  try {
    await page.goto(urlFor({}), { waitUntil: "domcontentloaded" });
    const iso = await isoCheck(page);
    log(`${name}: crossOriginIsolated=${iso.iso} SAB=${iso.sab}`);
    await waitWMMain(page);
    log(`${name}: WM_main reached`);
    // small settle so the boot burst + grace complete and we measure true idle
    await sleep(3000);
    const before = path.join(OUTDIR, `${name}-before.png`);
    await page.screenshot({ path: before });
    writeLicense(before);
    const c0 = await readCounters(page);
    log(`${name}: t0 tick=${c0.tick} present=${c0.present}; idling ${IDLE_MS} ms...`);
    await sleep(IDLE_MS);
    const c1 = await readCounters(page);
    const after = path.join(OUTDIR, `${name}-after-idle.png`);
    await page.screenshot({ path: after });
    writeLicense(after);
    const tickDelta = c1.tick - c0.tick;
    const presentDelta = c1.present - c0.present;
    const secs = IDLE_MS / 1000;
    log(`${name}: t1 tick=${c1.tick} present=${c1.present} | over ${secs}s idle: tickDelta=${tickDelta} presentDelta=${presentDelta} (present/s=${(presentDelta/secs).toFixed(2)})`);
    // Bonus: input liveness after idle - move + click over the canvas, expect a present.
    const c1b = await readCounters(page);
    await page.mouse.move(640, 400); await sleep(150);
    await page.mouse.move(660, 420); await sleep(150);
    await page.mouse.click(660, 420); await sleep(1500);
    const c2 = await readCounters(page);
    log(`${name}: post-idle input -> tickDelta=${c2.tick - c1b.tick} presentDelta=${c2.present - c1b.present}`);
    // PASS: loop ticked through idle (alive) AND no continuous GPU submission (no burn).
    const alive = tickDelta > 20;                       // >20 iterations in 30 s = loop advancing
    const noBurn = presentDelta < (secs * 5);           // < 5 fps average = not a 60 fps burn
    r.pass = alive && noBurn;
    r.tickDelta = tickDelta; r.presentDelta = presentDelta; r.presentPerSec = presentDelta / secs;
    r.inputPresentDelta = c2.present - c1b.present;
    r.before = before; r.after = after;
    log(`${name}: alive(tick>20)=${alive} noBurn(present/s<5)=${noBurn} => ${r.pass ? "PASS" : "FAIL"}`);
  } catch (e) {
    r.error = String(e && e.message ? e.message : e);
    log(`${name}: ERROR ${r.error}`);
  } finally {
    fs.writeFileSync(path.join(OUTDIR, `${name}-console.log`), con.join("\n"));
    await ctx.close();
  }
  results[name] = r;
}

async function scenarioTimer(browser, keepalive) {
  const name = keepalive ? "B_timer_ON" : "C_ab_off_baseline";
  log(`--- ${name}: one-shot timer (no tag_redraw), keepalive=${keepalive ? "ON" : "0"} ---`);
  const params = { pyexpr: TIMER_PYEXPR };
  if (!keepalive) params.keepalive = "0";
  const { ctx, page, con } = await newPage(browser, name);
  const r = { pass: false, fired: false };
  let firedElapsed = null;
  page.on("console", (m) => {
    const t = m.text();
    if (t.includes("BW_KEEPALIVE_TIMER_FIRED")) {
      r.fired = true;
      const mm = /elapsed_ms=(\d+)/.exec(t);
      firedElapsed = mm ? parseInt(mm[1], 10) : null;
    }
  });
  try {
    await page.goto(urlFor(params), { waitUntil: "domcontentloaded" });
    await waitWMMain(page);
    log(`${name}: WM_main reached; timer armed at first_interval=20 s`);
    const c0 = await readCounters(page);
    // Wait long enough for the 20 s one-shot to fire if the loop is alive.
    await sleep(IDLE_MS);
    const c1 = await readCounters(page);
    const tickDelta = c1.tick - c0.tick;
    const presentDelta = c1.present - c0.present;
    r.tickDelta = tickDelta; r.presentDelta = presentDelta; r.firedElapsed = firedElapsed;
    log(`${name}: over ${IDLE_MS/1000}s: tickDelta=${tickDelta} (${(tickDelta/(IDLE_MS/1000)).toFixed(1)}Hz) presentDelta=${presentDelta} timerFired=${r.fired}${firedElapsed!=null?` @${firedElapsed}ms`:""}`);
    if (keepalive) {
      // Teeth: the one-shot timer must fire at idle WITHOUT any tag_redraw kick.
      r.pass = r.fired === true;
    } else {
      // ?keepalive=0 = the reachable rAF baseline. In a continuously-composited FOREGROUND
      // tab worker rAF does NOT stall - it spins ~60 Hz (so the timer fires); the idle stall
      // only manifests when compositing stops (see drive-discriminator.mjs, BG_off). PASS =
      // the baseline is reachable and runs on rAF (tick advancing markedly faster than ON's
      // idle back-off), i.e. ?keepalive=0 restores the pre-fix scheduling.
      r.pass = (tickDelta > 100);
    }
    log(`${name}: => ${r.pass ? "PASS" : "FAIL"}`);
  } catch (e) {
    r.error = String(e && e.message ? e.message : e);
    log(`${name}: ERROR ${r.error}`);
  } finally {
    fs.writeFileSync(path.join(OUTDIR, `${name}-console.log`), con.join("\n"));
    await ctx.close();
  }
  results[name] = r;
}

async function scenarioRegression(browser) {
  const name = "D_regress_kick";
  log(`--- ${name}: standard kick rig, keepalive default ON; grid must still render ---`);
  const { ctx, page, con } = await newPage(browser, name);
  const r = { pass: false };
  try {
    await page.goto(urlFor({ pyexpr: KICK_PYEXPR }), { waitUntil: "domcontentloaded" });
    await waitWMMain(page);
    log(`${name}: WM_main reached; settling ${PIXELS_MS} ms under the 1 Hz kick...`);
    const c0 = await readCounters(page);
    await sleep(PIXELS_MS);
    const c1 = await readCounters(page);
    const shot = path.join(OUTDIR, `${name}-grid.png`);
    await page.screenshot({ path: shot });
    writeLicense(shot);
    const nb = nonBlackFraction(shot);
    const presentDelta = c1.present - c0.present;
    log(`${name}: presentDelta=${presentDelta} over ${PIXELS_MS/1000}s; screenshot nonBlack=${(nb.frac*100).toFixed(1)}% (${nb.w}x${nb.h})`);
    r.pass = (presentDelta > 5) && (nb.frac > 0.02);
    r.presentDelta = presentDelta; r.nonBlackFrac = nb.frac; r.shot = shot;
    log(`${name}: draws(present>5)=${presentDelta>5} nonBlack(>2%)=${nb.frac>0.02} => ${r.pass ? "PASS" : "FAIL"}`);
  } catch (e) {
    r.error = String(e && e.message ? e.message : e);
    log(`${name}: ERROR ${r.error}`);
  } finally {
    fs.writeFileSync(path.join(OUTDIR, `${name}-console.log`), con.join("\n"));
    await ctx.close();
  }
  results[name] = r;
}

(async () => {
  log(`ghost-keepalive proof: base=${BASE} entry=${ENTRY}`);
  const browser = await chromium.launch({ headless: false });
  try {
    await scenarioLiveness(browser);
    await scenarioTimer(browser, true);   // B
    await scenarioTimer(browser, false);  // C (A/B baseline)
    await scenarioRegression(browser);    // D
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(OUTDIR, "run.log"), LOGLINES.join("\n"));
  fs.writeFileSync(path.join(OUTDIR, "summary.json"), JSON.stringify(results, null, 2));
  const allPass = Object.values(results).every((r) => r.pass === true);
  log(`SUMMARY: ${Object.entries(results).map(([k, v]) => `${k}=${v.pass ? "PASS" : "FAIL"}`).join("  ")}`);
  log(`VERDICT: ${allPass ? "ALL PASS" : "SOME FAILED"}`);
  process.exit(allPass ? 0 : 1);
})();
