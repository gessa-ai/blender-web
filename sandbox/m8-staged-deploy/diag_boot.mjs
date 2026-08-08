// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// diag_boot.mjs [port] - boot whatever bundle is served, run a pyexpr that closes
// its file + tests `import dis`, dump console + marker. Used to A/B the monolith vs
// staged to attribute the 'dis' ModuleNotFoundError.
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const fs = require('fs');
const PORT = parseInt(process.argv[2] || '8130', 10);
const TAG = process.argv[3] || 'diag';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PY = [
  'import bpy,os,sys',
  'def _m():',
  '    r="bpy="+bpy.app.version_string',
  '    try:',
  '        import dis; r+=" dis=OK"',
  '    except Exception as e: r+=" dis_ERR="+repr(e)',
  '    f=open("/bw/_diag_marker","w"); f.write(r); f.close(); return None',
  'bpy.app.timers.register(_m, first_interval=0.6)',
].join('\n');
const url = `http://localhost:${PORT}/index.html?gate=1280x720&stage1=manual&pyexpr=${encodeURIComponent(PY)}`;
const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 840 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const lines = [];
page.on('console', (m) => lines.push(m.text()));
page.on('pageerror', (e) => lines.push('PAGEERR ' + (e.message || e)));
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 180000 });
await sleep(4000);
const marker = await page.evaluate(() => { try { return window.__bwModule.FS.readFile('/bw/_diag_marker', { encoding: 'utf8' }); } catch (e) { return 'READ_ERR:' + e; } });
console.log(TAG + ' marker:', marker);
const disLines = lines.filter((l) => /dis|Traceback|ModuleNotFound|marker/i.test(l));
console.log(TAG + ' dis/traceback lines:', disLines.length);
disLines.slice(0, 12).forEach((l) => console.log('  | ' + l.slice(0, 140)));
fs.writeFileSync(`/Users/paws/blender-web/sandbox/m8-staged-deploy/artifacts/${TAG}_console.log`, lines.join('\n'));
await browser.close();
