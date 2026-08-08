// SPDX-License-Identifier: GPL-3.0-or-later
// Find a reliable wasm-linear-memory size signal under PROXY_TO_PTHREAD.
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const BASE = 'http://localhost:8127';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 } })).newPage();
await page.goto(`${BASE}/windowed.html`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await sleep(3000);

console.log('workers: ' + page.workers().length);
// try each worker for a shared wasm memory size
for (const w of page.workers()) {
  try {
    const r = await w.evaluate(() => {
      const g = self;
      const cand = {};
      try { if (g.wasmMemory && g.wasmMemory.buffer) cand.wasmMemory = g.wasmMemory.buffer.byteLength; } catch (e) {}
      try { if (g.HEAP8 && g.HEAP8.buffer) cand.HEAP8 = g.HEAP8.buffer.byteLength; } catch (e) {}
      try { if (g.Module && g.Module.HEAP8 && g.Module.HEAP8.buffer) cand.ModuleHEAP8 = g.Module.HEAP8.buffer.byteLength; } catch (e) {}
      try { if (g.Module && g.Module.wasmMemory) cand.ModuleWasmMem = g.Module.wasmMemory.buffer.byteLength; } catch (e) {}
      return { url: g.location ? g.location.href.slice(-40) : '?', cand };
    });
    console.log('WORKER ' + JSON.stringify(r));
  } catch (e) { console.log('WORKER err ' + e.message); }
}

const ua = await page.evaluate(async () => {
  const out = { crossOriginIsolated: self.crossOriginIsolated };
  if (typeof performance.measureUserAgentSpecificMemory === 'function') {
    try { const r = await performance.measureUserAgentSpecificMemory(); out.total = r.bytes; out.types = Array.from(new Set(r.breakdown.flatMap(b => b.types))); }
    catch (e) { out.err = e.message; }
  } else out.err = 'no measureUserAgentSpecificMemory';
  return out;
});
console.log('UA-MEM ' + JSON.stringify(ua));
await browser.close();
