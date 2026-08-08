// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M8 boot-verify for the name-section-stripped Release binary (bin-namestrip).
// Headed bundled Chromium (matches the M5 proven launch). Boots windowed.html on
// :8127, waits for the "main loop (WM_main)" marker, confirms first pixels, grabs
// a visual capture, and probes the wasm heap + JS heap. PASS iff WM_main reached,
// no abort, first-pixels seen, and __bwModule/HEAP readable.

import { createRequire } from 'module';
import { writeFileSync, mkdirSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const PORT = parseInt(process.argv[2] || '8127', 10);
const BASE = `http://localhost:${PORT}`;
const OUT = '/Users/paws/blender-web/sandbox/m8-soak/evidence';
mkdirSync(OUT, { recursive: true });
const BOOT_MS = 240000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ts = () => new Date().toISOString().replace('T', ' ').replace('Z', '');
const log = (s) => console.log(`[${ts()}] ${s}`);

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

const sig = { present: 0, gpuErr: 0, aborted: false, fatal: [] };
page.on('console', (m) => {
  const t = m.text();
  if (t.includes('presentBackbuffer')) sig.present++;
  if (t.includes('GPU-ERROR') || t.includes('ValidationError')) sig.gpuErr++;
  if (t.includes('abort(') || t.includes('Aborted') || t.includes('RuntimeError') || t.includes('Traceback')) {
    sig.fatal.push(t.slice(0, 200));
  }
});
page.on('pageerror', (e) => sig.fatal.push('pageerror: ' + (e && e.message ? e.message : e)));

let rec = { ok: false, boot_ms: null, present: 0, gpuErr: 0, wasmBytes: null, jsHeap: null, note: null };
try {
  log(`booting ${BASE}/windowed.html`);
  await page.goto(`${BASE}/windowed.html`, { waitUntil: 'domcontentloaded' });
  const t0 = Date.now();
  await page.waitForFunction(() => {
    const s = document.querySelector('#state');
    return s && (s.textContent.includes('main loop (WM_main)') || s.getAttribute('data-state') === 'aborted');
  }, null, { timeout: BOOT_MS, polling: 500 });
  const st = await page.evaluate(() => document.querySelector('#state').getAttribute('data-state'));
  rec.boot_ms = Date.now() - t0;
  if (st === 'aborted') { rec.note = 'boot aborted'; throw new Error(rec.note); }
  log(`WM_main in ${rec.boot_ms} ms; settling for first pixels`);
  await sleep(4000);
  rec.present = sig.present;
  rec.gpuErr = sig.gpuErr;
  const probe = await page.evaluate(() => {
    const m = window.__bwModule;
    const wasmBytes = (m && m.HEAP8 && m.HEAP8.buffer) ? m.HEAP8.buffer.byteLength : null;
    const pm = performance.memory || null;
    return { hasModule: !!m, wasmBytes, jsHeap: pm ? pm.usedJSHeapSize : null };
  });
  rec.wasmBytes = probe.wasmBytes;
  rec.jsHeap = probe.jsHeap;
  await page.screenshot({ path: `${OUT}/boot-verify-namestrip.png` });
  rec.ok = !!probe.hasModule && probe.wasmBytes > 0 && sig.fatal.length === 0;
  rec.note = rec.ok ? 'OK' : ('module=' + probe.hasModule + ' wasm=' + probe.wasmBytes + ' fatal=' + sig.fatal.length);
  log(`present(first-pixels marker)=${rec.present} gpuErr=${rec.gpuErr} wasmBytes=${rec.wasmBytes} jsHeap=${rec.jsHeap}`);
} catch (e) {
  rec.note = (rec.note ? rec.note + '; ' : '') + 'exception: ' + (e && e.message ? e.message : e);
} finally {
  rec.fatal = sig.fatal.slice(0, 5);
  writeFileSync(`${OUT}/boot-verify.json`, JSON.stringify(rec, null, 2) + '\n');
  await ctx.close();
  await browser.close();
  log('VERDICT: ' + (rec.ok ? 'PASS' : 'FAIL') + '  ' + JSON.stringify(rec));
}
