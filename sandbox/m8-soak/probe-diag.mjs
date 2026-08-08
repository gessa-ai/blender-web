// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 900, height: 600 } })).newPage();
const hits = [];
page.on('console', (m) => { const t = m.text(); if (/BW_(EXPR|OSW|TIMER)|Traceback|Error|SOAK/.test(t)) hits.push(m.type()+': '+t.slice(0,200)); });
const py = [
 'import os',
 'os.write(2, b"BW_OSW_TOP\\n")',
 'import bpy',
 'def _t():',
 ' os.write(2, b"BW_TIMER_FIRED\\n")',
 ' return None',
 'bpy.app.timers.register(_t, first_interval=2.0)',
 'os.write(2, b"BW_EXPR_END\\n")',
].join('\n');
await page.goto('http://localhost:8127/windowed.html?pyexpr=' + encodeURIComponent(py), { waitUntil: 'domcontentloaded' });
try { await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 }); } catch(e){ hits.push('WAIT_FAIL '+e.message); }
await sleep(6000);
console.log('HITS ' + JSON.stringify(hits, null, 0));
await browser.close();
