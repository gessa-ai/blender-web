// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// recon_fs2.mjs - second recon: FS.mkdir fails post-boot, but the preload itself
// creates dirs. Test whether the emscripten preload helpers FS_createPath /
// FS_createDataFile (exported on the module) work post-WM_main, and whether a
// preloaded file can be overwritten, and whether many new files can be added to an
// existing dir. These settle the stage-1 mount design.
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const PORT = parseInt(process.argv[2] || '8130', 10);
const BASE = `http://localhost:${PORT}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const url = `${BASE}/index.html?gate=1280x720`;

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: 1380, height: 820 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const logs = [];
page.on('console', (m) => logs.push(m.text()));
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, null, { timeout: 180000 });
console.log('recon2: WM_main reached');
await sleep(3000);

const r = await page.evaluate(() => {
  const out = {};
  const mod = window.__bwModule, FS = mod.FS;
  // 1. FS_createPath: create a brand-new nested dir the way the preload does.
  try {
    mod.FS_createPath('/bw', '_r2/deep/nest', true, true);
    out.createPath = 'OK';
  } catch (e) { out.createPath = 'FAIL ' + e; }
  // 2. FS_createDataFile into that new dir.
  try {
    mod.FS_createDataFile('/bw/_r2/deep/nest', 'f.txt', new Uint8Array([65, 66, 67]), true, true, true);
    out.createDataFile = 'OK read=' + FS.readFile('/bw/_r2/deep/nest/f.txt', { encoding: 'utf8' });
  } catch (e) { out.createDataFile = 'FAIL ' + e; }
  // 3. FS.writeFile a NEW file into a deep PRE-EXISTING preload dir.
  try {
    FS.writeFile('/bw/scripts/addons_core/_r2new.txt', 'NEWOK');
    out.newInExistingDir = 'OK';
  } catch (e) { out.newInExistingDir = 'FAIL ' + e; }
  // 4. Overwrite a PRELOADED file (does the preload backend allow rewrite?).
  try {
    const p = '/bw/scripts/addons_core/io_scene_gltf2/__init__.py';
    const before = FS.readFile(p).length;
    FS.writeFile(p, new Uint8Array([1, 2, 3, 4]));
    const after = FS.readFile(p).length;
    out.overwritePreloaded = 'OK before=' + before + ' after=' + after;
  } catch (e) { out.overwritePreloaded = 'FAIL ' + e; }
  // 5. Analytics: what backend/mode does /bw have? (mode bits)
  try {
    const st = FS.stat('/bw');
    out.bwMode = '0' + (st.mode & 0o7777).toString(8);
  } catch (e) { out.bwMode = 'stat FAIL ' + e; }
  return out;
});
console.log('recon2:', JSON.stringify(r, null, 2));
await browser.close();
