// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M5 tier-(c) event-simulate REPLAY driver (Playwright, headed bundled Chromium).
//
// Runs each M5 session in a FRESH page/context (one boot per session, crash
// isolation) against the windowed blender_browser wasm build served by
// scripts/serve-web.sh with BLENDER_WEB_SHELL=sandbox/m5-prep/web. Per session:
//   1. goto ?session=<mod.func>, wait for the "main loop (WM_main)" marker.
//   2. wait for /m5/done.txt (the runner's FS sentinel) via window.__m5_status.
//   3. pull /m5/out.json + /m5/trace.log + the console log back over
//      window.__bwModule.FS and save them under wasm-out/.
//
// Serve first (PORT 8125 is this lane's):
//   BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed/bin \
//   BLENDER_WEB_SHELL=/Users/paws/blender-web/sandbox/m5-prep/web \
//     /opt/homebrew/bin/bash scripts/serve-web.sh 8125
// Then:
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/m5-prep/web/drive-sessions.mjs [port] [session ...]
//
// The binary may be relinked by another lane; if a boot aborts, retry in ~5 min.

import { createRequire } from 'module';
import { writeFileSync, mkdirSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const PORT = parseInt(process.argv[2] || '8125', 10);
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/m5-prep/wasm-out';
mkdirSync(OUTDIR, { recursive: true });

const ALL_SESSIONS = [
  'm5_core.object_select_all',
  'm5_core.object_click_select',
  'm5_core.object_transform_grxsz',
  'm5_core.edit_mode_toggle',
  'm5_core.edit_mode_select_modes',
  'm5_core.mesh_extrude_region',
  'm5_core.mesh_bevel',
  'm5_core.undo_depth',
];
const SESSIONS = process.argv.length > 3 ? process.argv.slice(3) : ALL_SESSIONS;

const BOOT_MS = 240000;   // 926 MB wasm + 85 MB data over localhost, per boot.
const DONE_MS = 180000;   // session run budget after WM_main.
const POLL_MS = 500;

function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Sanitize an operator log to the oracle's canonical trace form: keep only
// "operator | Started bpy.ops...." lines, strip everything up to "| Started ".
function sanitizeTrace(raw) {
  if (!raw) return '';
  const out = [];
  for (const line of raw.split('\n')) {
    if (/operator\s*\| Started bpy\.ops\./.test(line)) {
      out.push(line.replace(/^.*\| Started /, ''));
    }
  }
  return out.join('\n') + (out.length ? '\n' : '');
}

const browser = await chromium.launch({ headless: false });
const results = [];

for (const session of SESSIONS) {
  const rec = { session, boot_ms: null, run_ms: null, result: null,
                state_sha: null, ntrace_file: 0, ntrace_console: 0,
                present: 0, errors: [], note: null };
  const ctx = await browser.newContext({
    viewport: { width: 1380, height: 820 }, deviceScaleFactor: 1,
  });
  const page = await ctx.newPage();
  const present = { count: 0 };
  const gpuErr = { count: 0 };
  page.on('console', (m) => {
    const t = m.text();
    if (t.includes('presentBackbuffer')) present.count++;
    // Routine windowed-build GPU validation noise: count, don't store.
    if (t.includes('GPU-ERROR') || t.includes('ValidationError') || t.includes('WebGPU')) {
      gpuErr.count++; return;
    }
    // Real session-level failures only.
    if (t.includes('M5_FATAL') || t.includes('M5_SESSION_ERROR') || t.includes('M5_DUMP_ERROR')
        || t.includes('M5_TB') || t.includes('Traceback')) {
      rec.errors.push(t.slice(0, 200));
    }
  });

  const url = `${BASE}/?session=${encodeURIComponent(session)}`;
  log(`=== ${session} ===`);
  log(`booting ${url}`);
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    const t0 = Date.now();
    await page.waitForFunction(() => {
      const s = document.querySelector('#state');
      return s && (s.textContent.includes('main loop (WM_main)')
        || s.getAttribute('data-state') === 'aborted');
    }, null, { timeout: BOOT_MS, polling: 500 });
    const st0 = await page.evaluate(() => window.__m5_status());
    if (st0.error) {
      rec.note = 'boot status.error=' + st0.error;
      try {
        const cl = await page.evaluate(() => (window.__m5 && window.__m5.log)
          ? window.__m5.log.slice(-40).join('\n') : '');
        writeFileSync(`${OUTDIR}/${session}.bootfail.txt`, cl);
      } catch (_) {}
      throw new Error(rec.note);
    }
    rec.boot_ms = Date.now() - t0;
    log(`WM_main in ${rec.boot_ms} ms`);

    // Poll for the console-reassembled dump (no browser-thread FS access).
    const t1 = Date.now();
    let done = false;
    while (Date.now() - t1 < DONE_MS) {
      const st = await page.evaluate(() => window.__m5_status());
      if (st.error) { rec.note = 'status.error=' + st.error; break; }
      if (st.done || st.hasOut) { done = true; break; }
      await sleep(POLL_MS);
    }
    rec.run_ms = Date.now() - t1;
    rec.present = present.count;
    rec.gpu_err = gpuErr.count;

    // Give a moment for trailing console lines (the closing quit_blender op line)
    // to arrive after M5_DONE, then pull everything from the console channel.
    await sleep(1500);
    const pull = await page.evaluate(() => window.__m5_result());
    rec.fsMatches = pull.fsMatches;

    const dump = pull.out || pull.outFs || null;
    if (dump) {
      writeFileSync(`${OUTDIR}/${session}.json`, dump);
      const m = /"_m5_result": "([a-z]+)"/.exec(dump);
      rec.result = m ? m[1] : (done ? 'ok?' : 'partial');
      rec.dump_src = pull.out ? (pull.fsMatches ? 'console+fs' : 'console') : 'fs-only';
    } else {
      rec.result = done ? 'done-no-json' : 'timeout-no-json';
    }

    const consoleRaw = pull.console || '';
    writeFileSync(`${OUTDIR}/${session}.console.txt`, consoleRaw);
    const traceFromConsole = sanitizeTrace(consoleRaw);
    writeFileSync(`${OUTDIR}/${session}.trace.txt`, traceFromConsole);
    rec.ntrace_console = traceFromConsole ? traceFromConsole.trim().split('\n').length : 0;
    rec.ntrace_file = rec.ntrace_console;

    // Evidence screenshot (Playwright page capture, NOT a bpy readback).
    try {
      await page.screenshot({ path: `${OUTDIR}/${session}.png` });
    } catch (_) {}

    log(`${session}: result=${rec.result} run=${rec.run_ms}ms present=${rec.present} `
        + `trace(file=${rec.ntrace_file},console=${rec.ntrace_console}) errors=${rec.errors.length}`);
  } catch (e) {
    rec.note = (rec.note ? rec.note + '; ' : '') + 'exception: ' + (e && e.message ? e.message : e);
    rec.result = rec.result || 'boot-fail';
    log(`${session}: FAIL ${rec.note}`);
  } finally {
    results.push(rec);
    await ctx.close();
  }
}

await browser.close();
writeFileSync(`${OUTDIR}/_run-summary.json`, JSON.stringify(results, null, 1) + '\n');
log('=== SUMMARY ===');
for (const r of results) {
  log(`${r.result === 'ok' ? 'OK ' : '?? '} ${r.session}  result=${r.result} `
      + `boot=${r.boot_ms}ms run=${r.run_ms}ms present=${r.present} `
      + `trace(f=${r.ntrace_file},c=${r.ntrace_console})`
      + (r.note ? `  note=${r.note}` : ''));
}
log(`summary -> ${OUTDIR}/_run-summary.json`);
