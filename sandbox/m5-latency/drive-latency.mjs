// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M5 input-to-visible-frame LATENCY driver (Playwright, headed bundled Chromium).
//
// Measures the windowed blender_browser build's interactive latency honestly, on
// ONE wall clock (epoch seconds):
//   * keypress dispatch  = Python time.time() emitted by the probe (M5LAT_DISPATCH)
//   * operator start     = CLOG "Started bpy.ops.<op>" line, converted to epoch
//                          via a tick_start calibrated from bracketed M5LAT_CAL
//   * visible present     = first CDP screencast frame (Page.screencastFrame,
//                          metadata.timestamp = Network.TimeSinceEpoch) whose
//                          canvas pixels change vs the pre-dispatch baseline
// Reports keypress->operator-start, operator->present, and end-to-end
// (median/p95) over N samples, plus boot-to-interactive (load->WM_main->first
// paint). See notes/m5-latency-budget.md for method floors/ceilings.
//
// Serve first (this lane's port 8125):
//   BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed-opt/bin \
//   BLENDER_WEB_SHELL=/Users/paws/blender-web/sandbox/m5-latency/web \
//     /opt/homebrew/bin/bash scripts/serve-web.sh 8125
// Then:
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/m5-latency/drive-latency.mjs \
//       --port 8125 --session m5_latency.tab --n 32 --spacing 0.6 --label opt
//   ... or boot-only:  --session boot --boots 3

import { createRequire } from 'module';
import { writeFileSync, mkdirSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sharp = require('sharp');

// ---- args -------------------------------------------------------------------
function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : dflt;
}
const PORT = parseInt(arg('port', '8125'), 10);
const SESSION = arg('session', 'm5_latency.tab');
const N = parseInt(arg('n', '32'), 10);
const SPACING = parseFloat(arg('spacing', '0.6'));
const LABEL = arg('label', 'run');
const BOOTS = parseInt(arg('boots', '3'), 10);
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/m5-latency/out';
mkdirSync(OUTDIR, { recursive: true });

const BOOT_MS = 300000;      // cold fetch of wasm/data over localhost, per boot.
const RUN_PAD_MS = 20000;    // slack beyond the probe's own scheduled duration.
const TW = 160, TH = 90;     // greyscale thumbnail size for pixel-diff signatures.

function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- stats ------------------------------------------------------------------
function quantile(sorted, q) {
  if (!sorted.length) return null;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}
function stats(arr) {
  const a = arr.filter((x) => x != null && isFinite(x)).slice().sort((x, y) => x - y);
  if (!a.length) return { n: 0 };
  const sum = a.reduce((s, x) => s + x, 0);
  return {
    n: a.length, min: a[0], max: a[a.length - 1], mean: sum / a.length,
    median: quantile(a, 0.5), p95: quantile(a, 0.95),
  };
}
const r1 = (x) => (x == null ? null : Math.round(x * 10) / 10);

// ---- CLOG timestamp parse ---------------------------------------------------
// "MM:SS.mmm  operator | Started bpy.ops.<id>(...)"  (or "HH:MM:SS.mmm" past 1h)
function parseClogStarted(line) {
  const m = /^(\d+):(\d+)(?::(\d+))?\.(\d+)\s+operator\s*\|\s*Started\s+(bpy\.ops\.[A-Za-z0-9_.]+)/.exec(line);
  if (!m) return null;
  let h = 0, mi, se, ms;
  if (m[3] != null) { h = +m[1]; mi = +m[2]; se = +m[3]; } else { mi = +m[1]; se = +m[2]; }
  ms = +m[4];
  return { rel: h * 3600 + mi * 60 + se + ms / 1000, op: m[5] };
}

// greyscale thumbnail signature (Uint8Array length TW*TH) for a JPEG buffer.
async function signature(buf) {
  try {
    const out = await sharp(buf).greyscale().resize(TW, TH, { fit: 'fill' }).raw().toBuffer();
    return new Uint8Array(out);
  } catch (e) { return null; }
}
function meanAbsDiff(a, b) {
  if (!a || !b || a.length !== b.length) return null;
  let s = 0;
  for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]);
  return s / a.length;
}
function meanBright(a) {
  if (!a) return null;
  let s = 0; for (let i = 0; i < a.length; i++) s += a[i];
  return s / a.length;
}

// ---- one boot: returns {frames, consoleLines, boot} -------------------------
async function bootAndCapture(browser, url, { runMs }) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 860 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const consoleLines = [];
  page.on('console', (m) => consoleLines.push(m.text()));
  page.on('pageerror', (e) => consoleLines.push('PAGEERROR ' + e.message));

  const client = await ctx.newCDPSession(page);
  const frames = [];   // {t: epoch seconds, buf: Buffer}
  client.on('Page.screencastFrame', async (ev) => {
    const t = (ev.metadata && ev.metadata.timestamp) ? ev.metadata.timestamp : Date.now() / 1000;
    frames.push({ t, buf: Buffer.from(ev.data, 'base64') });
    try { await client.send('Page.screencastFrameAck', { sessionId: ev.sessionId }); } catch (_) {}
  });

  const boot = { load_start: null, wm_main: null };
  boot.load_start = Date.now() / 1000;
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  // Start the screencast right after the doc loads so we capture the first paint.
  await client.send('Page.startScreencast', { format: 'jpeg', quality: 70, maxWidth: 1400, maxHeight: 860, everyNthFrame: 1 });

  await page.waitForFunction(() => {
    const s = document.querySelector('#state');
    return s && (s.textContent.includes('main loop (WM_main)') || s.getAttribute('data-state') === 'aborted');
  }, null, { timeout: BOOT_MS, polling: 250 });
  boot.wm_main = Date.now() / 1000;

  const st0 = await page.evaluate(() => window.__m5lat_status());
  if (st0.error) {
    log(`boot error: ${st0.error}`);
    const cl = consoleLines.slice(-40).join('\n');
    writeFileSync(`${OUTDIR}/${LABEL}.bootfail.txt`, cl);
  }

  // Let the run play out: wait for M5LAT_DONE (or the padded budget).
  const deadline = Date.now() + runMs;
  while (Date.now() < deadline) {
    const st = await page.evaluate(() => window.__m5lat_status());
    if (st.done || st.error) break;
    await sleep(300);
  }
  await sleep(1500);  // trailing frames + console lines.

  try { await client.send('Page.stopScreencast'); } catch (_) {}
  const fullConsole = await page.evaluate(() => window.__m5lat_console());
  await ctx.close();
  return { frames, consoleLines: (fullConsole || consoleLines.join('\n')).split('\n'), boot };
}

// ---- boot-to-interactive (first non-black paint) ----------------------------
async function firstPaint(frames, sigs) {
  // First frame whose brightness rises clearly above the black start.
  let base = null;
  for (let i = 0; i < frames.length; i++) {
    const b = meanBright(sigs[i]);
    if (b == null) continue;
    if (base == null) base = b;
    if (b > Math.max(base + 6, 6)) return frames[i].t;
  }
  return null;
}

// ---- main -------------------------------------------------------------------
const browser = await chromium.launch({ headless: false });

if (SESSION === 'boot') {
  const boots = [];
  for (let k = 0; k < BOOTS; k++) {
    const url = `${BASE}/?session=m5_latency.tab&n=0&spacing=0.1`;
    log(`=== boot ${k + 1}/${BOOTS} (${LABEL}) ===  ${url}`);
    const cap = await bootAndCapture(browser, url, { runMs: 90000 });
    const sigs = [];
    for (const f of cap.frames) sigs.push(await signature(f.buf));
    const fp = await firstPaint(cap.frames, sigs);
    const rec = {
      run: k + 1,
      load_to_wm_main_ms: r1((cap.boot.wm_main - cap.boot.load_start) * 1000),
      load_to_first_paint_ms: fp ? r1((fp - cap.boot.load_start) * 1000) : null,
      wm_main_to_first_paint_ms: fp ? r1((fp - cap.boot.wm_main) * 1000) : null,
      frames: cap.frames.length,
    };
    boots.push(rec);
    log(`boot ${k + 1}: load->WM_main=${rec.load_to_wm_main_ms}ms  load->first-paint=${rec.load_to_first_paint_ms}ms  frames=${rec.frames}`);
  }
  const out = {
    label: LABEL, kind: 'boot-to-interactive', boots,
    summary: {
      load_to_wm_main_ms: stats(boots.map((b) => b.load_to_wm_main_ms)),
      load_to_first_paint_ms: stats(boots.map((b) => b.load_to_first_paint_ms)),
    },
  };
  writeFileSync(`${OUTDIR}/boot-${LABEL}.json`, JSON.stringify(out, null, 1) + '\n');
  log(`boot-to-interactive -> ${OUTDIR}/boot-${LABEL}.json`);
  await browser.close();
  process.exit(0);
}

// ---- latency session --------------------------------------------------------
const OP_BY_SESSION = {
  'm5_latency.tab': 'bpy.ops.object.editmode_toggle',
  'm5_latency.nkey': 'bpy.ops.wm.context_toggle',
  'm5_latency.selall': 'bpy.ops.object.select_all',
};
const PROBE_OP = OP_BY_SESSION[SESSION] || null;

// The -O0 dev build compiles workbench shaders synchronously on first draw
// (many seconds, during which bpy.app timers do not fire), so the generator only
// begins after that. Floor the wait well above the probe's own scheduled span.
const scheduledMs = Math.max((5 * 0.15 + (N + 1) * SPACING) * 1000 + RUN_PAD_MS, 220000);
const url = `${BASE}/?session=${encodeURIComponent(SESSION)}&n=${N}&spacing=${SPACING}`;
log(`=== latency ${SESSION} n=${N} spacing=${SPACING}s label=${LABEL} ===`);
log(`booting ${url}`);
const cap = await bootAndCapture(browser, url, { runMs: scheduledMs });
await browser.close();

writeFileSync(`${OUTDIR}/${LABEL}.console.txt`, cap.consoleLines.join('\n'));
log(`captured ${cap.frames.length} screencast frames; ${cap.consoleLines.length} console lines`);

// Decode all frames to signatures.
const sigs = [];
for (const f of cap.frames) sigs.push(await signature(f.buf));

// Parse console: calibration, dispatches, operator-starts.
const cal = [];          // {k, t0, t1}
const dispatches = [];   // {i, label, t}
const ops = [];          // {rel, op}  (all "Started" lines)
const calOps = [];       // undo_push "Started" lines in order
for (const line of cap.consoleLines) {
  let m;
  if ((m = /^M5LAT_CAL (\d+) ([\d.]+) ([\d.]+)/.exec(line))) {
    cal.push({ k: +m[1], t0: +m[2], t1: +m[3] });
  } else if ((m = /^M5LAT_DISPATCH (\d+) (\S+) ([\d.]+)/.exec(line))) {
    dispatches.push({ i: +m[1], label: m[2], t: +m[3] });
  } else {
    const c = parseClogStarted(line);
    if (c) {
      ops.push(c);
      if (c.op === 'bpy.ops.ed.undo_push') calOps.push(c);
    }
  }
}

// tick_start: pair k-th M5LAT_CAL with k-th undo_push "Started".
const tickStarts = [];
const pairs = Math.min(cal.length, calOps.length);
for (let k = 0; k < pairs; k++) {
  const mid = (cal[k].t0 + cal[k].t1) / 2;   // op wall-time is within [t0,t1]
  tickStarts.push(mid - calOps[k].rel);
}
tickStarts.sort((a, b) => a - b);
const tickStart = tickStarts.length ? quantile(tickStarts, 0.5) : null;
const tickSpreadMs = tickStarts.length ? r1((tickStarts[tickStarts.length - 1] - tickStarts[0]) * 1000) : null;
log(`calibration: ${pairs} pairs, tick_start spread=${tickSpreadMs}ms`);

// Frame-to-frame baseline noise (median consecutive meanAbsDiff), for the change threshold.
const consec = [];
for (let i = 1; i < sigs.length; i++) { const d = meanAbsDiff(sigs[i - 1], sigs[i]); if (d != null) consec.push(d); }
consec.sort((a, b) => a - b);
// Static floor = LOW percentile of consecutive diffs (the p50/p95 are polluted by
// the very toggle-change frames we detect). The toggle signal (dMax) is ~25x this
// floor, so a floor*8 threshold cleanly separates onset from static jitter.
const noiseMed = consec.length ? quantile(consec, 0.5) : 0;
const noiseP95 = consec.length ? quantile(consec, 0.95) : 0;
const noiseFloor = consec.length ? quantile(consec, 0.25) : 0;
const CHANGE_THRESH = Math.max(noiseFloor * 8, noiseMed * 5, 5.0);
log(`frame-diff noise: p25(floor)=${r1(noiseFloor)} median=${r1(noiseMed)} p95=${r1(noiseP95)} -> change_thresh=${r1(CHANGE_THRESH)}`);

// Frame cadence.
const dts = [];
for (let i = 1; i < cap.frames.length; i++) dts.push((cap.frames[i].t - cap.frames[i - 1].t) * 1000);
const cad = stats(dts);
log(`screencast cadence ms: median=${r1(cad.median)} p95=${r1(cad.p95)}`);

// Per-dispatch measurement.
const samples = [];
let opIdx = 0;
for (let d = 0; d < dispatches.length; d++) {
  const disp = dispatches[d];
  const tDisp = disp.t;
  const tEnd = (d + 1 < dispatches.length) ? dispatches[d + 1].t : tDisp + SPACING + 1.0;

  // operator start: next matching probe op with epoch in the window.
  let tOp = null, tOpRel = null;
  if (tickStart != null && PROBE_OP) {
    for (; opIdx < ops.length; opIdx++) {
      if (ops[opIdx].op !== PROBE_OP) continue;
      const epoch = ops[opIdx].rel + tickStart;
      if (epoch < tDisp - 0.02) continue;      // belongs to an earlier dispatch
      if (epoch >= tEnd) break;                // none for this dispatch
      tOp = epoch; tOpRel = ops[opIdx].rel; opIdx++; break;
    }
  }

  // baseline signature: last frame at or before dispatch.
  let baseIdx = -1;
  for (let i = 0; i < cap.frames.length; i++) { if (cap.frames[i].t <= tDisp) baseIdx = i; else break; }
  // visible: first frame after dispatch whose diff vs baseline exceeds threshold.
  let tVis = null, dMax = 0;
  if (baseIdx >= 0) {
    for (let i = baseIdx + 1; i < cap.frames.length; i++) {
      if (cap.frames[i].t > tEnd + 0.25) break;
      const diff = meanAbsDiff(sigs[i], sigs[baseIdx]);
      if (diff != null && diff > dMax) dMax = diff;
      if (tVis == null && diff != null && diff > CHANGE_THRESH) tVis = cap.frames[i].t;
    }
  }

  samples.push({
    i: disp.i, label: disp.label,
    kp_to_op_ms: (tOp != null) ? (tOp - tDisp) * 1000 : null,
    op_to_present_ms: (tOp != null && tVis != null) ? (tVis - tOp) * 1000 : null,
    end_to_end_ms: (tVis != null) ? (tVis - tDisp) * 1000 : null,
    dMax: r1(dMax), hasOp: tOp != null, hasVis: tVis != null,
  });
}

const good = samples.filter((s) => s.end_to_end_ms != null);
const withOp = samples.filter((s) => s.kp_to_op_ms != null);
const withBoth = samples.filter((s) => s.op_to_present_ms != null);

const result = {
  label: LABEL, session: SESSION, probe_op: PROBE_OP, n_requested: N,
  n_dispatch: dispatches.length, n_with_visible: good.length,
  n_with_operator: withOp.length,
  calibration: { pairs, tick_start_spread_ms: tickSpreadMs },
  frame_diff_noise: { floor_p25: r1(noiseFloor), median: r1(noiseMed), p95: r1(noiseP95), change_thresh: r1(CHANGE_THRESH) },
  screencast_cadence_ms: { median: r1(cad.median), p95: r1(cad.p95), frames: cap.frames.length },
  boot: {
    load_to_wm_main_ms: r1((cap.boot.wm_main - cap.boot.load_start) * 1000),
  },
  metrics: {
    keypress_to_operator_ms: statsRounded(withOp.map((s) => s.kp_to_op_ms)),
    operator_to_present_ms: statsRounded(withBoth.map((s) => s.op_to_present_ms)),
    end_to_end_ms: statsRounded(good.map((s) => s.end_to_end_ms)),
  },
  samples: samples.map((s) => ({ ...s,
    kp_to_op_ms: r1(s.kp_to_op_ms), op_to_present_ms: r1(s.op_to_present_ms), end_to_end_ms: r1(s.end_to_end_ms) })),
};

function statsRounded(arr) {
  const s = stats(arr);
  return { n: s.n, median: r1(s.median), p95: r1(s.p95), min: r1(s.min), max: r1(s.max), mean: r1(s.mean) };
}

writeFileSync(`${OUTDIR}/lat-${LABEL}.json`, JSON.stringify(result, null, 1) + '\n');
log('=== RESULT ===');
log(`dispatches=${result.n_dispatch} with_operator=${result.n_with_operator} with_visible=${result.n_with_visible}`);
log(`keypress->operator ms  median=${result.metrics.keypress_to_operator_ms.median} p95=${result.metrics.keypress_to_operator_ms.p95}`);
log(`operator->present ms   median=${result.metrics.operator_to_present_ms.median} p95=${result.metrics.operator_to_present_ms.p95}`);
log(`end-to-end ms          median=${result.metrics.end_to_end_ms.median} p95=${result.metrics.end_to_end_ms.p95}`);
log(`-> ${OUTDIR}/lat-${LABEL}.json`);
