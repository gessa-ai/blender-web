// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
// Contract check: ?gate=WxH still renders canvas at EXACTLY WxH (DPR forced 1) with
// the store wired in, and the OPFS mount still reports PERSISTENT (coexistence).
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
const all = [];
page.on('console', (m) => all.push(m.text()));
await page.goto('http://localhost:8126/windowed.html?gate=800x600', { waitUntil: 'domcontentloaded', timeout: 180000 });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, { timeout: 180000 });
let mount = '';
for (let i = 0; i < 40; i++) { await page.waitForTimeout(1000); const m = all.filter(l => l.includes('M7 store')); if (m.length) { mount = m[m.length-1]; break; } }
const dims = await page.evaluate(() => { const c = document.querySelector('#canvas'); return { w: c.width, h: c.height, cssw: c.style.width, cssh: c.style.height }; });
console.log('GATE canvas backing:', JSON.stringify(dims), '(deviceScaleFactor=2, gate forces DPR 1)');
console.log('GATE mount line     :', mount || '(none)');
const exact = dims.w === 800 && dims.h === 600;
const persist = /PERSISTENT/.test(mount);
console.log(exact ? 'PASS gate-exact-size 800x600' : 'FAIL gate-exact-size ' + JSON.stringify(dims));
console.log(persist ? 'PASS gate-store-coexists' : 'FAIL gate-store-coexists');
await browser.close();
process.exit(exact && persist ? 0 : 1);
