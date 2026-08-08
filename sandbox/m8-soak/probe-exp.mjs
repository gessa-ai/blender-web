// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 900, height: 600 } })).newPage();
await page.goto('http://localhost:8127/windowed.html', { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await sleep(2000);
const r = await page.evaluate(() => {
  const m = window.__bwModule || {};
  const allKeys = Object.keys(m);
  const fnHeap = allKeys.filter(k => /heap|sbrk|memory|malloc|emscripten_get/i.test(k));
  const out = { nKeys: allKeys.length, sample: allKeys.slice(0, 25), fnHeap };
  const tryc = (name) => { try { if (typeof m[name] === 'function') return m[name](); } catch(e){ return 'ERR:'+e.message; } return 'n/a'; };
  out.heapSize = tryc('_emscripten_get_heap_size');
  out.sbrk = tryc('_sbrk');
  return out;
});
console.log('EXP ' + JSON.stringify(r));
await browser.close();
