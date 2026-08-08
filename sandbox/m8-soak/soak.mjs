// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M8 30-minute soak of the name-section-stripped Release gate binary
// (build-wasm-windowed-opt/bin-namestrip, served on :8127).
//
// The WM main loop is emscripten_set_main_loop, driven by the browser main
// thread's requestAnimationFrame (proxied to the WM worker under
// PROXY_TO_PTHREAD). So a main-thread rAF counter is a faithful present/loop
// liveness signal: if Blender's per-frame draw/present blocks, the main thread
// blocks and the counter stalls. (The C-side presentBackbuffer printf is capped
// at 2 frames and cannot serve here; bpy.app timers / draw handlers do not fire
// under this harness -- see notes/m8-soak-and-namestrip.md for the channel audit.)
//
// Activity: periodic input bursts to the canvas (mouse orbit/select + the
// M5-proven keys A / G-move / Tab in-out / Ctrl+Z) churn the event pipeline,
// operators, edit-mode enter/exit and the undo stack -- the prime leak surfaces.
// Bursts are periodic (not continuous) to keep the r29-diag console volume bounded.
//
// Sampled every SAMPLE_MS: usedJSHeapSize (JS glue heap), rAF frame count
// (liveness), console line + GPU-error + fatal counts. A finer 2 s watchdog flags
// any present stall > STALL_MS. wasm linear memory is NOT directly readable in this
// build (MODULARIZE hides wasmMemory in the factory closure; no memory accessor is
// exported) -- documented limitation; the strip changes zero runtime bytes so
// runtime memory behaviour is identical to the unstripped binary regardless.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//          node sandbox/m8-soak/soak.mjs [port] [minutes]

import { createRequire } from 'module';
import { writeFileSync, appendFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const PORT = parseInt(process.argv[2] || '8127', 10);
const MINUTES = parseFloat(process.argv[3] || '30');
const BASE = `http://localhost:${PORT}`;
const OUT = '/Users/paws/blender-web/sandbox/m8-soak';
const EVID = OUT + '/evidence';
const RUN_MS = Math.round(MINUTES * 60000);
const SAMPLE_MS = 30000;
const WATCH_MS = 2000;
const STALL_MS = 5000;
const BURST_EVERY_MS = 15000;
const BOOT_MS = 240000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ts = () => new Date().toISOString();
const log = (s) => console.log(`[${ts()}] ${s}`);
const CSV = `${OUT}/soak-timeseries.csv`;
const LIVE = `${OUT}/soak-live.json`;

const state = {
  startedAt: ts(), status: 'booting', boot_ms: null,
  console_total: 0, gpu_err: 0, fatals: [], stalls: [], samples: [],
  verdict: null,
};
const recentRing = [];
function pushRecent(t) { recentRing.push(t); if (recentRing.length > 60) recentRing.shift(); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

page.on('console', (m) => {
  state.console_total++;
  const t = m.text();
  if (t.includes('GPU-ERROR') || t.includes('ValidationError') || t.includes('Dawn: ')) state.gpu_err++;
  if (t.includes('abort(') || t.includes('Aborted') || t.includes('RuntimeError') || t.includes('Traceback')) {
    if (state.fatals.length < 40) state.fatals.push(t.slice(0, 240));
  }
  if (/error|warn/i.test(m.type())) pushRecent(m.type() + ': ' + t.slice(0, 160));
});
page.on('pageerror', (e) => { state.fatals.push('pageerror: ' + (e && e.message ? e.message : e)); });
page.on('crash', () => { state.fatals.push('PAGE CRASH'); });

writeFileSync(CSV, 't_sec,usedJSHeap,totalJSHeap,rafCount,rafDelta,console_total,gpu_err,fatals,note\n');
function writeLive() { try { writeFileSync(LIVE, JSON.stringify(state, null, 1) + '\n'); } catch (_) {} }

let bootOk = false;
try {
  log(`booting ${BASE}/windowed.html  (soak ${MINUTES} min)`);
  await page.goto(`${BASE}/windowed.html`, { waitUntil: 'domcontentloaded' });
  const tb = Date.now();
  await page.waitForFunction(() => {
    const s = document.querySelector('#state');
    return s && (s.textContent.includes('main loop (WM_main)') || s.getAttribute('data-state') === 'aborted');
  }, null, { timeout: BOOT_MS, polling: 500 });
  const st = await page.evaluate(() => document.querySelector('#state').getAttribute('data-state'));
  state.boot_ms = Date.now() - tb;
  if (st === 'aborted') throw new Error('boot aborted');
  bootOk = true;
  log(`WM_main in ${state.boot_ms} ms`);
  await page.bringToFront();
  await sleep(3000);
  await page.evaluate(() => { window.__raf = 0; (function l() { window.__raf++; requestAnimationFrame(l); })(); });
  await page.screenshot({ path: `${EVID}/soak-start.png` });
} catch (e) {
  state.status = 'boot-fail';
  state.fatals.push('boot exception: ' + (e && e.message ? e.message : e));
}

async function readRaf() { try { return await page.evaluate(() => window.__raf || 0); } catch (_) { return null; } }
async function readMem() {
  try { return await page.evaluate(() => { const pm = performance.memory || {}; return { u: pm.usedJSHeapSize || 0, t: pm.totalJSHeapSize || 0 }; }); }
  catch (_) { return { u: 0, t: 0 }; }
}

// canvas centre for input
let cx = 640, cy = 360;
try { const b = await page.evaluate(() => { const c = document.getElementById('canvas'); const r = c.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }); cx = b.x + b.w * 0.5; cy = b.y + b.h * 0.5; } catch (_) {}

let burstPhase = 0;
async function inputBurst() {
  try {
    await page.mouse.move(cx, cy);
    await page.mouse.click(cx, cy);                 // pick / focus
    await page.keyboard.press('a');                 // select all
    // G-move: grab, move, confirm
    await page.keyboard.press('g');
    await page.mouse.move(cx + 60, cy + 30, { steps: 4 });
    await page.mouse.click(cx + 60, cy + 30);
    await page.keyboard.press('Tab');               // edit mode
    await page.keyboard.press('a');
    await page.keyboard.press('Tab');               // object mode
    await page.keyboard.press('Control+z');         // undo
    await page.keyboard.press('Control+z');
    // small orbit (MMB drag) to churn view + redraw
    await page.mouse.move(cx - 40, cy - 20);
    burstPhase++;
  } catch (e) { if (state.fatals.length < 40) state.fatals.push('burst err: ' + e.message); }
}

if (bootOk) {
  state.status = 'running';
  const t0 = Date.now();
  let lastRaf = await readRaf();
  let lastRafWall = Date.now();
  let lastSample = 0, lastBurst = 0;
  let firstUsed = null, sampleN = 0;
  while (Date.now() - t0 < RUN_MS) {
    await sleep(WATCH_MS);
    const now = Date.now();
    // liveness watchdog
    const raf = await readRaf();
    if (raf !== null && lastRaf !== null) {
      if (raf > lastRaf) { lastRaf = raf; lastRafWall = now; }
      else if (now - lastRafWall > STALL_MS) {
        const stall = { t_sec: Math.round((now - t0) / 1000), gap_ms: now - lastRafWall, raf };
        state.stalls.push(stall);
        log(`STALL detected: raf frozen ${stall.gap_ms} ms at t=${stall.t_sec}s`);
        lastRafWall = now; // avoid spamming; re-arm
      }
    }
    // periodic activity burst
    if (now - lastBurst >= BURST_EVERY_MS) { lastBurst = now; await inputBurst(); }
    // periodic full sample
    if (now - lastSample >= SAMPLE_MS) {
      lastSample = now;
      const mem = await readMem();
      const rnow = await readRaf();
      const tsec = Math.round((now - t0) / 1000);
      const prevRaf = sampleN === 0 ? 0 : state.samples[state.samples.length - 1]._raf;
      const rafDelta = rnow - prevRaf;
      if (firstUsed === null) firstUsed = mem.u;
      const s = { t_sec: tsec, usedJSHeap: mem.u, totalJSHeap: mem.t, _raf: rnow, rafDelta,
                  console_total: state.console_total, gpu_err: state.gpu_err, fatals: state.fatals.length,
                  bursts: burstPhase };
      state.samples.push(s);
      appendFileSync(CSV, `${tsec},${mem.u},${mem.t},${rnow},${rafDelta},${state.console_total},${state.gpu_err},${state.fatals.length},\n`);
      writeLive();
      log(`t=${tsec}s used=${(mem.u / 1e6).toFixed(1)}MB rafΔ=${rafDelta} console=${state.console_total} gpuErr=${state.gpu_err} fatals=${state.fatals.length} bursts=${burstPhase}`);
      sampleN++;
      if (state.fatals.length > 0 && /CRASH|pageerror|Aborted|abort\(/.test(state.fatals.join(' '))) {
        log('FATAL detected -> ending soak early'); break;
      }
    }
  }
  try { await page.screenshot({ path: `${EVID}/soak-end.png` }); } catch (_) {}
  state.status = 'done';
}

// ---- verdict ----
function verdict() {
  const S = state.samples;
  const v = { bootOk, n_samples: S.length };
  if (!bootOk || S.length < 2) { v.pass = false; v.reason = 'insufficient samples / boot fail'; return v; }
  // heap back-half growth
  const half = Math.floor(S.length / 2);
  const backAvg = S.slice(half).reduce((a, s) => a + s.usedJSHeap, 0) / (S.length - half);
  const frontAvg = S.slice(0, half).reduce((a, s) => a + s.usedJSHeap, 0) / half;
  v.heap_front_MB = +(frontAvg / 1e6).toFixed(2);
  v.heap_back_MB = +(backAvg / 1e6).toFixed(2);
  v.heap_growth_pct = +(((backAvg - frontAvg) / frontAvg) * 100).toFixed(2);
  // first vs last used
  v.heap_first_MB = +(S[0].usedJSHeap / 1e6).toFixed(2);
  v.heap_last_MB = +(S[S.length - 1].usedJSHeap / 1e6).toFixed(2);
  // liveness: every 30s window advanced
  v.min_rafDelta = Math.min(...S.slice(1).map((s) => s.rafDelta));
  v.stalls = state.stalls.length;
  v.gpu_err = state.gpu_err;
  v.fatals = state.fatals.length;
  const heapOk = v.heap_growth_pct < 10;
  const liveOk = v.min_rafDelta > 0 && v.stalls === 0;
  const gpuOk = v.gpu_err === 0;
  const noFatal = v.fatals === 0;
  v.checks = { heapOk, liveOk, gpuOk, noFatal };
  v.pass = heapOk && liveOk && gpuOk && noFatal;
  v.bar = 'heap back-half growth <10%; no present stall >5s (rafDelta>0 every 30s window); zero GPU errors; no crash/abort';
  return v;
}
state.verdict = verdict();
state.endedAt = ts();
writeLive();
writeFileSync(`${OUT}/soak-result.json`, JSON.stringify(state, null, 1) + '\n');
log('SOAK VERDICT: ' + (state.verdict.pass ? 'PASS' : 'FAIL') + '  ' + JSON.stringify(state.verdict));
await ctx.close();
await browser.close();
