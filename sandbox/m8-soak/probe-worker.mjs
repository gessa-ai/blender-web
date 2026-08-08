// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const withTimeout = (p, ms) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error('to')), ms))]);
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 } })).newPage();
await page.goto('http://localhost:8127/windowed.html', { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await sleep(3000);
const ws = page.workers();
console.log('WORKERS ' + ws.length);
let got = null;
for (let i = 0; i < ws.length; i++) {
  try {
    const v = await withTimeout(ws[i].evaluate(() => (typeof wasmMemory !== 'undefined' && wasmMemory.buffer) ? wasmMemory.buffer.byteLength : (self.HEAP8 ? self.HEAP8.buffer.byteLength : -1)), 3000);
    console.log('W' + i + ' bytes=' + v);
    if (typeof v === 'number' && v > 0 && got === null) got = v;
  } catch (e) { console.log('W' + i + ' ' + e.message); }
}
console.log('WASM_SIGNAL ' + got);
await browser.close();
