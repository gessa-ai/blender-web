// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 } })).newPage();
await page.goto('http://localhost:8127/windowed.html', { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await sleep(3000);
const r = await page.evaluate(async () => {
  const out = { coi: self.crossOriginIsolated, jsHeap: (performance.memory||{}).usedJSHeapSize };
  try { const m = await performance.measureUserAgentSpecificMemory(); out.total = m.bytes; out.n = m.breakdown.length; } catch (e) { out.err = e.message; }
  return out;
});
console.log('MEM2 ' + JSON.stringify(r));
await browser.close();
