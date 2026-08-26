// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// measure_boot.mjs <port> <label> [runs] - honest cold/warm boot timing for the
// bundle served at <port>. For each run it records, from navigation start:
//   - time-to-WM_main       (the #state "main loop (WM_main)" marker)
//   - time-to-first-pixels  (GHOST's "presentBackbuffer frame 0" console line)
// Matrix per invocation: COLD (fresh context = empty HTTP+wasm cache + empty OPFS)
// and WARM (same context, one warm-up load then measured reloads) at no throttle,
// plus a COLD throttled pass (CDP 4G ~1.5 MB/s) to expose the download-bound win
// that localhost hides. Headed bundled Chromium. Serve with serve_measure.py
// (production cache policy) so WARM actually reuses cache.
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = parseInt(process.argv[2] || '8130', 10);
const LABEL = process.argv[3] || 'bundle';
const RUNS = parseInt(process.argv[4] || '3', 10);
const THROTTLE_MBPS = process.argv[5] !== undefined ? parseFloat(process.argv[5]) : 1.5; // 0 = skip throttled pass
const ONLY = process.argv[6] || 'all'; // 'all' | 'throttle' (skip unthrottled) | 'plain'
const BASE = `http://localhost:${PORT}`;
const URL = `${BASE}/index.html`; // trusted init state keeps stage-1 off the boot path we time
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const BOOT_MS = 300000;
const OUTDIR = '/Users/paws/blender-web/sandbox/m8-staged-deploy/artifacts';
fs.mkdirSync(OUTDIR, { recursive: true });

// One boot in the given page; returns {wm, fp} ms from just-before-goto.
async function bootOnce(page) {
  const t = { fp: null };
  const onCon = (m) => { if (t.fp === null && m.text().includes('presentBackbuffer')) t.fp = Date.now() - t0; };
  page.on('console', onCon);
  const t0 = Date.now();
  t.t0 = t0;
  await page.goto(URL, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: BOOT_MS });
  const wm = Date.now() - t0;
  // give first-pixels a brief chance if it trails WM_main
  for (let i = 0; i < 30 && t.fp === null; i++) await sleep(100);
  page.off('console', onCon);
  return { wm, fp: t.fp };
}

async function throttle(page, mbps) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false, downloadThroughput: mbps * 1e6, uploadThroughput: (mbps / 2) * 1e6, latency: 40,
  });
}

const browser = await chromium.launch({ headless: false });
const results = {}; // scenario -> [{wm,fp}]

// COLD: fresh context per run (empty cache + OPFS).
async function coldPass(name, mbps) {
  results[name] = [];
  for (let i = 0; i < RUNS; i++) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
    await ctx.addInitScript(() => { window.__BW_STAGE1_MANUAL = true; });
    const page = await ctx.newPage();
    if (mbps) await throttle(page, mbps);
    const r = await bootOnce(page);
    results[name].push(r);
    console.log(`  ${name} run ${i + 1}: WM_main=${r.wm}ms first-pixels=${r.fp === null ? 'n/a' : r.fp + 'ms'}`);
    await ctx.close();
  }
}

// WARM: one context; a warm-up load populates the cache; then measured reloads.
async function warmPass(name) {
  results[name] = [];
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { window.__BW_STAGE1_MANUAL = true; });
  const page = await ctx.newPage();
  const w = await bootOnce(page); // warm-up (discarded)
  console.log(`  ${name} warmup (discarded): WM_main=${w.wm}ms`);
  for (let i = 0; i < RUNS; i++) {
    const r = await bootOnce(page); // reload reuses cache
    results[name].push(r);
    console.log(`  ${name} run ${i + 1}: WM_main=${r.wm}ms first-pixels=${r.fp === null ? 'n/a' : r.fp + 'ms'}`);
  }
  await ctx.close();
}

console.log(`\n=== measure ${LABEL} @ ${BASE} (${RUNS} runs each) ===`);
if (ONLY !== 'throttle') { console.log('[cold, no throttle]'); await coldPass('cold', 0); }
if (ONLY !== 'throttle') { console.log('[warm, no throttle]'); await warmPass('warm'); }
if (THROTTLE_MBPS > 0 && ONLY !== 'plain') { console.log(`[cold, throttled ${THROTTLE_MBPS} MB/s, brotli wire]`); await coldPass(`cold-${THROTTLE_MBPS}mbps`, THROTTLE_MBPS); }
await browser.close();

function med(a) { const s = a.filter((x) => x !== null).sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : null; }
const summary = { label: LABEL, port: PORT, runs: RUNS, at: new Date().toISOString(), scenarios: {} };
console.log(`\n--- ${LABEL} medians ---`);
for (const k of Object.keys(results)) {
  const wm = results[k].map((r) => r.wm), fp = results[k].map((r) => r.fp);
  summary.scenarios[k] = { wm, fp, wm_median: med(wm), fp_median: med(fp) };
  console.log(`  ${k}: WM_main median=${med(wm)}ms  first-pixels median=${med(fp) === null ? 'n/a' : med(fp) + 'ms'}  (WM runs: ${wm.join(',')})`);
}
fs.writeFileSync(`${OUTDIR}/measure_${LABEL}.json`, JSON.stringify(summary, null, 2));
console.log(`wrote ${OUTDIR}/measure_${LABEL}.json`);
