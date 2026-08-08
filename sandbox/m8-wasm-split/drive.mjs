// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M8 wasm-split harness driver. Headed BUNDLED Chromium via Playwright
// (NODE_PATH=/Users/paws/plushly/game-platform/node_modules), port 8127.
//
// Proves the emscripten 6.0.5 SPLIT_MODULE demand-load contract under the shipped
// constraint set WITHOUT JSPI:
//   T1 boot:   module boots, cold_subsystem NOT executed, secondary NOT fetched.
//   T2 cmd1:   demand-call cold on the proxied-main worker -> secondary fetched
//              synchronously, cold executes, result correct, NO SuspendError/abort.
//   T3 cmd2:   demand-call cold on a freshly spawned pthread (TBB-equivalent) ->
//              works (decisive pthread test).
// Network log distinguishes true demand-load (fetch happens at T2, not at boot).

import { createRequire } from 'module';
import { writeFileSync, mkdirSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const PORT = parseInt(process.argv[2] || '8127', 10);
const BASE = `http://localhost:${PORT}`;
const OUT = '/Users/paws/blender-web/sandbox/m8-wasm-split/evidence';
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (s) => console.log(`[drive] ${s}`);

const net = [];         // {url, when} for *.wasm requests
const consoleLines = [];
const fatal = [];
let secondaryFetchedBefore = { boot: false, cmd1: false };

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: 800, height: 600 } });
const page = await ctx.newPage();

page.on('request', (req) => {
  const u = req.url();
  if (u.endsWith('.wasm')) net.push({ url: u.split('/').pop(), t: Date.now() });
});
page.on('console', (m) => {
  const t = m.text();
  consoleLines.push(t);
  if (/SuspendError|WebAssembly\.promising|Asyncify/.test(t)) fatal.push('SUSPEND: ' + t.slice(0, 200));
  if (/abort\(|Aborted|RuntimeError|unreachable/.test(t)) fatal.push('ABORT: ' + t.slice(0, 200));
});
page.on('pageerror', (e) => fatal.push('pageerror: ' + (e && e.message ? e.message : e)));

const rec = { pass: false, tests: {}, sizes: {}, secondaryFile: 'harness.deferred.wasm', fatal: [], note: null };

const deferredFetched = () => net.some((r) => r.url === 'harness.deferred.wasm');

try {
  log(`booting ${BASE}/index.html`);
  await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => {
    const s = document.querySelector('#state');
    const v = s && s.getAttribute('data-state');
    return v === 'boot-done' || v === 'aborted' || v === 'boot-timeout';
  }, null, { timeout: 60000, polling: 200 });

  const st = await page.evaluate(() => document.querySelector('#state').getAttribute('data-state'));
  const coldAtBoot = await page.evaluate(() => window.__coldRuns());
  secondaryFetchedBefore.boot = deferredFetched();

  // T1: boot reached, cold not run, secondary not fetched.
  rec.tests.T1_boot = {
    state: st,
    coldRuns: coldAtBoot,
    secondaryFetchedAtBoot: secondaryFetchedBefore.boot,
    pass: st === 'boot-done' && coldAtBoot === 0 && !secondaryFetchedBefore.boot,
  };
  log(`T1 boot: state=${st} coldRuns=${coldAtBoot} secondaryFetched=${secondaryFetchedBefore.boot}`);
  if (st !== 'boot-done') { rec.note = 'boot did not complete'; throw new Error(rec.note); }

  // T2: demand-call cold on the proxied-main worker.
  const seq0 = await page.evaluate(() => window.__doneSeq());
  log(`issuing cmd 1 (cold on proxied-main worker); doneSeq=${seq0}`);
  await page.evaluate(() => window.__cmd(1));
  await page.waitForFunction((s0) => window.__doneSeq() > s0, seq0, { timeout: 30000, polling: 100 });
  const r1 = await page.evaluate(() => ({ result: window.__result(), cold: window.__coldRuns() }));
  const secAfterCmd1 = deferredFetched();
  // expected cold_subsystem(100): acc=100 iterated 2000x of LCG
  rec.tests.T2_cmd1_proxied_main = {
    result: r1.result,
    coldRuns: r1.cold,
    secondaryFetchedNow: secAfterCmd1,
    fetchWasDemand: !secondaryFetchedBefore.boot && secAfterCmd1,
    pass: r1.cold === 1 && secAfterCmd1 && fatal.length === 0,
  };
  log(`T2 cmd1: result=${r1.result} coldRuns=${r1.cold} secondaryFetched=${secAfterCmd1} fatal=${fatal.length}`);

  // T3: demand-call cold on a fresh pthread (decisive).
  const seq1 = await page.evaluate(() => window.__doneSeq());
  log(`issuing cmd 2 (cold on a fresh pthread); doneSeq=${seq1}`);
  await page.evaluate(() => window.__cmd(2));
  let cmd2ok = true, cmd2err = null;
  try {
    await page.waitForFunction((s1) => window.__doneSeq() > s1, seq1, { timeout: 30000, polling: 100 });
  } catch (e) { cmd2ok = false; cmd2err = 'timeout waiting for pthread cold completion'; }
  const r2 = await page.evaluate(() => ({ result: window.__result(), cold: window.__coldRuns() }));
  rec.tests.T3_cmd2_fresh_pthread = {
    completed: cmd2ok,
    error: cmd2err,
    result: r2.result,
    coldRuns: r2.cold,
    pass: cmd2ok && r2.cold === 2 && fatal.length === 0,
  };
  log(`T3 cmd2: completed=${cmd2ok} result=${r2.result} coldRuns=${r2.cold} err=${cmd2err} fatal=${fatal.length}`);

  await page.screenshot({ path: `${OUT}/harness-final.png` });
  rec.fatal = fatal;
  rec.wasmRequests = net.map((r) => r.url);
  rec.pass = rec.tests.T1_boot.pass && rec.tests.T2_cmd1_proxied_main.pass && rec.tests.T3_cmd2_fresh_pthread.pass;
} catch (e) {
  rec.note = (rec.note ? rec.note + '; ' : '') + 'driver exception: ' + (e && e.message ? e.message : e);
  rec.fatal = fatal;
} finally {
  await page.evaluate(() => window.__cmd(99)).catch(() => {});
  writeFileSync(`${OUT}/drive-result.json`, JSON.stringify(rec, null, 2));
  writeFileSync(`${OUT}/drive-console.log`, consoleLines.join('\n'));
  await browser.close();
  log(`VERDICT: ${rec.pass ? 'PASS' : 'FAIL'}  (evidence: ${OUT}/drive-result.json)`);
  console.log(JSON.stringify(rec.tests, null, 2));
  process.exit(rec.pass ? 0 : 1);
}
