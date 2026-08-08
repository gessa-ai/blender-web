// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 900, height: 600 } })).newPage();
const lines = [];
page.on('console', (m) => { const t = m.text(); lines.push(m.type()+"|"+t.slice(0,200)); });
const py = [
 'import bpy,os,gc',
 'def ctx():',
 '    for w in bpy.context.window_manager.windows:',
 '        s=w.screen',
 '        if not s: continue',
 '        for a in s.areas:',
 '            if a.type=="VIEW_3D":',
 '                r=next((x for x in a.regions if x.type=="WINDOW"),None)',
 '                return w,a,r',
 '    return None,None,None',
 'w,a,r=ctx()',
 'os.write(2,("BURST_CTX win=%s area=%s region=%s mode=%s\\n"%(w is not None,a is not None,r is not None,bpy.context.mode)).encode())',
 'ok=0; fail=0',
 'for i in range(20):',
 '    ph=i%4',
 '    try:',
 '        with bpy.context.temp_override(window=w,area=a,region=r):',
 '            if ph==0: bpy.ops.object.select_all(action="SELECT" if i%8<4 else "DESELECT")',
 '            elif ph==1: bpy.ops.transform.translate(value=(0.05,0,0))',
 '            elif ph==2: bpy.ops.object.editmode_toggle()',
 '            else: (bpy.ops.ed.undo() if i%8<4 else bpy.ops.ed.redo())',
 '        ok+=1',
 '    except Exception as e:',
 '        fail+=1',
 '        if fail<=4: os.write(2,("OPFAIL ph=%d %s %s\\n"%(ph,type(e).__name__,str(e)[:100])).encode())',
 'os.write(2,("BURST_DONE ok=%d fail=%d objs=%d meshes=%d objects=%d\\n"%(ok,fail,len(gc.get_objects()),len(bpy.data.meshes),len(bpy.data.objects))).encode())',
].join('\n');
await page.goto('http://localhost:8127/windowed.html?pyexpr=' + encodeURIComponent(py), { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await sleep(3000);
console.log("ALL\n" + lines.slice(-30).join("\n"));
await browser.close();
