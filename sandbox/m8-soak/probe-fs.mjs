// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 } })).newPage();
const py = [
 'import bpy,os,sys,gc,json',
 'def _p():',
 ' d={"tick":1}',
 ' try:',
 '  import resource; d["rss"]=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss',
 ' except Exception as e:',
 '  d["rss"]="ERR:"+type(e).__name__',
 ' try:',
 '  d["blocks"]=sys.getallocatedblocks()',
 ' except Exception:',
 '  d["blocks"]=-1',
 ' d["objs"]=len(gc.get_objects()); d["meshes"]=len(bpy.data.meshes); d["objects"]=len(bpy.data.objects)',
 ' os.makedirs("/soak",exist_ok=True)',
 ' open("/soak/probe.json","w").write(json.dumps(d))',
 ' return None',
 'bpy.app.timers.register(_p, first_interval=2.0)',
].join('\n');
await page.goto('http://localhost:8127/windowed.html?pyexpr=' + encodeURIComponent(py), { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await sleep(5000);
const r = await page.evaluate(() => {
  try { const s = window.__bwModule.FS.readFile('/soak/probe.json', { encoding: 'utf8' }); return { ok: true, s }; }
  catch (e) { return { ok: false, err: e.message }; }
});
console.log('FSREAD ' + JSON.stringify(r));
await browser.close();
