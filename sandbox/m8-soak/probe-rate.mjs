// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 } })).newPage();
let n = 0; const kinds = {};
page.on('console', (m) => { n++; const t=m.text(); const k=(t.match(/\[bw-r29-\w+\]|presentBackbuffer|GPU-ERROR|ValidationError/)||['other'])[0]; kinds[k]=(kinds[k]||0)+1; });
await page.goto('http://localhost:8127/windowed.html', { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await page.bringToFront();
await sleep(3000);
async function win(label, act){ const a=n; if(act) await act(); await sleep(5000); console.log(label+' lines/5s='+(n-a)); }
await win('idle1');
await win('idle2');
const box = await page.evaluate(() => { const c=document.getElementById('canvas'); const r=c.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; });
const cx=box.x+box.w*0.5, cy=box.y+box.h*0.5;
await win('input', async ()=>{ await page.mouse.click(cx,cy); for(let i=0;i<10;i++){ await page.mouse.move(cx+i*10,cy+i*5); await page.keyboard.press('a'); } });
console.log('KINDS ' + JSON.stringify(kinds));
await browser.close();
