// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 } })).newPage();
let draws = 0; const errs = [];
page.on('console', (m) => { const t = m.text(); if (t.includes('SOAK_DRAW')) draws++; if (t.includes('SOAK_HB')) errs.push(t.slice(0,180)); });
const py = [
 'import bpy,os,sys,gc',
 'c=[0]',
 'def _dh():',
 '    c[0]+=1',
 '    os.write(2,b"SOAK_DRAW\\n")',
 'bpy.types.SpaceView3D.draw_handler_add(_dh,(),"WINDOW","POST_PIXEL")',
 'try:',
 '    import resource; rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss',
 'except Exception as e:',
 '    rss="ERR:"+type(e).__name__',
 'os.write(2,("SOAK_HB rss=%s blocks=%d objs=%d\\n"%(rss,sys.getallocatedblocks(),len(gc.get_objects()))).encode())',
].join('\n');
await page.goto('http://localhost:8127/windowed.html?pyexpr=' + encodeURIComponent(py), { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await page.bringToFront();
await sleep(2000); const d0 = draws;
const box = await page.evaluate(() => { const c=document.getElementById('canvas'); const r=c.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; });
const cx = box.x + box.w*0.5, cy = box.y + box.h*0.5;
await page.mouse.move(cx, cy); await page.mouse.click(cx, cy);
for (let i=0;i<15;i++){ await page.mouse.move(cx+Math.sin(i)*100, cy+Math.cos(i)*80, {steps:3}); await sleep(150); }
await sleep(500); const d1 = draws;
await page.keyboard.press('a'); await page.keyboard.press('Tab'); await sleep(500); await page.keyboard.press('Tab'); await sleep(500);
const d2 = draws;
console.log('DRAWS boot='+d0+' afterMouse='+d1+' afterKeys='+d2+' hb='+JSON.stringify(errs));
await browser.close();
