// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 } })).newPage();
const hb = []; let dhInstalled = false;
page.on('console', (m) => { const t = m.text(); if (t.includes('SOAK_HB')) hb.push(t.slice(0,200)); if (t.includes('SOAK_DH_INSTALLED')) dhInstalled = true; });
const py = [
 'import bpy,os,sys,gc',
 'c=[0]',
 'def _dh():',
 '    c[0]+=1',
 '    if c[0]%15==0:',
 '        try:',
 '            import resource; rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss',
 '        except Exception as e:',
 '            rss="ERR:"+type(e).__name__',
 '        os.write(2,("SOAK_HB frames=%d rss=%s blocks=%d objs=%d meshes=%d\\n"%(c[0],rss,sys.getallocatedblocks(),len(gc.get_objects()),len(bpy.data.meshes))).encode())',
 'bpy.types.SpaceView3D.draw_handler_add(_dh,(),"WINDOW","POST_PIXEL")',
 'os.write(2,b"SOAK_DH_INSTALLED\\n")',
].join('\n');
await page.goto('http://localhost:8127/windowed.html?pyexpr=' + encodeURIComponent(py), { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await page.bringToFront();
await page.evaluate(() => { window.__raf=0; (function l(){ window.__raf++; requestAnimationFrame(l); })(); });
// drive input: focus canvas, move mouse across viewport, press keys
const box = await page.evaluate(() => { const c=document.getElementById('canvas'); const r=c.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; });
const cx = box.x + box.w*0.5, cy = box.y + box.h*0.5;
await page.mouse.click(cx, cy);
for (let i=0;i<20;i++){
  await page.mouse.move(cx + Math.sin(i)*80, cy + Math.cos(i)*60);
  if (i%4===0) await page.keyboard.press('a');
  await sleep(400);
}
await sleep(2000);
const raf = await page.evaluate(() => window.__raf);
console.log('RESULT dhInstalled='+dhInstalled+' rafCount='+raf+' hbLines='+hb.length);
if (hb.length) console.log('HB_SAMPLE ' + hb[hb.length-1]);
await browser.close();
