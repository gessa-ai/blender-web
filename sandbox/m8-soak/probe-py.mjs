// SPDX-License-Identifier: GPL-3.0-or-later
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 } })).newPage();
page.on('console', (m) => { const t = m.text(); if (t.includes('PYMEM')) console.log('CONSOLE ' + t.slice(0, 300)); });
const py = `import bpy,os,sys,gc\ndef _p():\n try:\n  import resource; rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n except Exception as e:\n  rss='ERR:'+type(e).__name__\n try:\n  blk=sys.getallocatedblocks()\n except Exception as e:\n  blk='ERR'\n os.write(2, ('PYMEM rss=%s blocks=%s objs=%d meshes=%d objects=%d\\n'%(rss,blk,len(gc.get_objects()),len(bpy.data.meshes),len(bpy.data.objects))).encode())\n return None\nbpy.app.timers.register(_p, first_interval=2.0)`;
const url = 'http://localhost:8127/windowed.html?pyexpr=' + encodeURIComponent(py);
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 240000, polling: 500 });
await sleep(6000);
await browser.close();
