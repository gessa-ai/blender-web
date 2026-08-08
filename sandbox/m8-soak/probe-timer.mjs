// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 900, height: 600 } })).newPage();
let fires = 0;
page.on('console', (m) => { const t = m.text(); if (t.includes('BW_TICK')) { fires++; } });
const py = [
 'import bpy,os',
 'n=[0]',
 'def _k():',
 '    n[0]+=1',
 '    os.write(2, ("BW_TICK %d\\n"%n[0]).encode())',
 '    try:',
 '        for win in bpy.context.window_manager.windows:',
 '            scr=win.screen',
 '            if scr:',
 '                for a in scr.areas:',
 '                    if a.type=="VIEW_3D":',
 '                        for r in a.regions:',
 '                            if r.type=="WINDOW": r.tag_redraw()',
 '    except Exception as e: os.write(2,("BW_KERR %s\\n"%e).encode())',
 '    return 0.5',
 'bpy.app.timers.register(_k, first_interval=1.0)',
].join('\n');
await page.goto('http://localhost:8127/windowed.html?pyexpr=' + encodeURIComponent(py), { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await page.bringToFront();
await sleep(12000);
console.log('TIMER_FIRES ' + fires);
await browser.close();
