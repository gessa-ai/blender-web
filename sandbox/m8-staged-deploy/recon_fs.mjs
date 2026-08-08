// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// recon_fs.mjs - reconnaissance: settle the stage-1 mount mechanism BEFORE the
// staged integration. Boots the monolith bundle, then probes which FS-mutation
// primitives actually work post-WM_main:
//   (A) Python (WM-worker thread, owns WasmFS): os.makedirs + write into a NEW dir.
//   (B) JS main thread: FS.mkdir / FS.mkdirTree into /bw, write into a NEW dir.
//   (C) JS main thread: write a flat file directly under /bw (the proven primitive).
// The staged loader will pick the reliable path from these receipts.
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const PORT = parseInt(process.argv[2] || '8130', 10);
const BASE = `http://localhost:${PORT}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const PYEXPR = [
  'import bpy,os',
  'def _recon():',
  '    r=[]',
  '    try:',
  '        os.makedirs("/bw/_recon_py/a/b", exist_ok=True)',
  '        open("/bw/_recon_py/a/b/z.txt","w").write("PYOK")',
  '        r.append("py_makedirs=OK read="+open("/bw/_recon_py/a/b/z.txt").read())',
  '    except Exception as e: r.append("py_makedirs=FAIL "+repr(e))',
  '    open("/bw/_recon_py_result","w").write(" | ".join(r))',
  '    return None',
  'bpy.app.timers.register(_recon, first_interval=0.5)',
].join('\n');

const url = `${BASE}/index.html?gate=1280x720&pyexpr=${encodeURIComponent(PYEXPR)}`;

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: 1380, height: 820 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const logs = [];
page.on('console', (m) => logs.push(m.text()));
page.on('pageerror', (e) => logs.push('PAGEERR ' + e.message));

console.log('recon: booting', url.slice(0, 80));
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, null, { timeout: 180000 });
console.log('recon: WM_main reached');
await sleep(4000);

// (B)+(C) JS main-thread FS probes
const js = await page.evaluate(() => {
  const out = {};
  const FS = window.__bwModule && window.__bwModule.FS;
  out.hasFS = !!FS;
  out.hasMkdir = FS && typeof FS.mkdir === 'function';
  out.hasMkdirTree = FS && typeof FS.mkdirTree === 'function';
  out.hasCreatePath = window.__bwModule && typeof window.__bwModule.FS_createPath === 'function';
  out.hasCreateDataFile = window.__bwModule && typeof window.__bwModule.FS_createDataFile === 'function';
  try { FS.mkdir('/bw/_recon_js1'); out.mkdir = 'OK'; } catch (e) { out.mkdir = 'FAIL ' + e; }
  try { FS.mkdirTree('/bw/_recon_js2/x/y'); FS.writeFile('/bw/_recon_js2/x/y/z.txt', 'JSOK'); out.mkdirTree = 'OK read=' + FS.readFile('/bw/_recon_js2/x/y/z.txt', { encoding: 'utf8' }); } catch (e) { out.mkdirTree = 'FAIL ' + e; }
  try { FS.writeFile('/bw/_recon_flat.txt', 'FLATOK'); out.flatWrite = 'OK read=' + FS.readFile('/bw/_recon_flat.txt', { encoding: 'utf8' }); } catch (e) { out.flatWrite = 'FAIL ' + e; }
  return out;
});
console.log('recon JS:', JSON.stringify(js, null, 2));

// (A) read the Python result
let py = null;
for (let i = 0; i < 30; i++) {
  py = await page.evaluate(() => { try { return window.__bwModule.FS.readFile('/bw/_recon_py_result', { encoding: 'utf8' }); } catch (e) { return null; } });
  if (py) break;
  await sleep(500);
}
console.log('recon PY:', py);
console.log('--- console tail ---');
console.log(logs.filter((l) => /recon|error|WM|Python|FS/i.test(l)).slice(-15).join('\n'));
await browser.close();
