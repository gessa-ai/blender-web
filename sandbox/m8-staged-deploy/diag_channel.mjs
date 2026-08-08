// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// diag_channel.mjs [port] - confirm a REPEATING file-only timer survives (keepalive)
// long enough for a rig-written go-flag pattern: timer polls /bw/_go; rig writes it
// after 3s; timer then writes /bw/_done with the tick count.
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const PORT = parseInt(process.argv[2] || '8130', 10);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PY = [
  'import bpy,os',
  '_n=[0]',
  'def _t():',
  '    _n[0]+=1',
  '    if os.path.exists("/bw/_go"):',
  '        f=open("/bw/_done","w"); f.write("FIRED@tick"+str(_n[0])); f.close(); return None',
  '    return 0.3',
  'bpy.app.timers.register(_t, first_interval=0.3)',
].join('\n');
const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 840 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.addInitScript((expr) => { window.__BW_PYEXPR = expr; window.__BW_STAGE1_MANUAL = true; }, PY);
await page.goto(`http://localhost:${PORT}/index.html?gate=1280x720`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 180000 });
await sleep(3000);
await page.evaluate(() => window.__bwModule.FS.writeFile('/bw/_go', new Uint8Array([49])));
let done = null;
for (let i = 0; i < 30; i++) { done = await page.evaluate(() => { try { return window.__bwModule.FS.readFile('/bw/_done', { encoding: 'utf8' }); } catch (e) { return null; } }); if (done) break; await sleep(500); }
console.log('CHANNEL repeating+goflag /bw/_done =', JSON.stringify(done));
await browser.close();
