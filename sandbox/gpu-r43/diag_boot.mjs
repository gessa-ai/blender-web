// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r43 F12 bind-group diagnostic driver. Reuses the r35 startup-file boot flow (seed the
// .blend into OPFS, boot windowed.html?args=..., trigger an offscreen render) but captures
// the FULL browser console to a log so the BW_DIAG-gated [bw-r43bind] expected-vs-emitted
// dump (temporary instrumentation in wgpu_context.cc) is preserved along with every
// [bw][GPU-ERROR] line. Headed bundled Chromium; neutral mouse move over the canvas before
// the render window so a fresh boot composites (rAF gate).
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node diag_boot.mjs <blendPath> <ENGINE> <outName> [port] [settleMs] [resW] [resH]

import { createRequire } from 'module';
import { writeFileSync, readFileSync, mkdirSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const HOST_BLEND = process.argv[2];
const ENGINE = (process.argv[3] || 'BLENDER_WORKBENCH').trim();
const OUTNAME = process.argv[4] || 'diag';
const PORT = parseInt(process.argv[5] || '8127', 10);
const SETTLE_MS = parseInt(process.argv[6] || '150000', 10);
const RESW = parseInt(process.argv[7] || '128', 10);
const RESH = parseInt(process.argv[8] || '128', 10);
const W = 640, H = 480;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r43';
const CAPDIR = `${OUTDIR}/caps/${OUTNAME}`;
const BOOT_MS = 300000;
const OPFS_NAME = 'bw_suite.blend';
const BLEND_PATH = '/projects/' + OPFS_NAME;
mkdirSync(CAPDIR, { recursive: true });

const blendB64 = readFileSync(HOST_BLEND).toString('base64');

const PYEXPR = [
  'import bpy, os, glob',
  'os.environ["BW_DIAG"] = "1"',
  'bpy.context.preferences.view.show_splash = False',
  'def _bw_kick():',
  '    try:',
  '        for win in bpy.context.window_manager.windows:',
  '            scr = win.screen',
  '            if not scr:',
  '                continue',
  '            for area in scr.areas:',
  '                if area.type == "VIEW_3D":',
  '                    for region in area.regions:',
  '                        if region.type == "WINDOW":',
  '                            region.tag_redraw()',
  '    except Exception:',
  '        pass',
  '    return 0.3',
  'bpy.app.timers.register(_bw_kick, first_interval=1.0)',
  'def _bw_render():',
  '    try:',
  '        sc = bpy.context.scene',
  '        sc.render.engine = "' + ENGINE + '"',
  '        sc.render.resolution_x = ' + RESW,
  '        sc.render.resolution_y = ' + RESH,
  '        sc.render.resolution_percentage = 100',
  '        sc.frame_set(1)',
  '        os.write(2, b"[bw-r43bind] === RENDER START ===\\n")',
  '        sc.render.image_settings.file_format = "PNG"',
  '        sc.render.filepath = "/tmp/r43_render"',
  '        bpy.ops.render.render(write_still=True)',
  '        open("/tmp/m6_bridge_done", "w").write("OK " + sc.render.engine)',
  '        os.write(2, b"[bw-r43bind] === RENDER DONE ===\\n")',
  '    except Exception as e:',
  '        open("/tmp/m6_bridge_done", "w").write("ERR " + repr(e))',
  '        os.write(2, b"[bw-r43bind] RENDER FAIL " + repr(e).encode() + b"\\n")',
  '    return None',
  'bpy.app.timers.register(_bw_render, first_interval=7.0)',
].join('\n');

function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 80, height: H + 80 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

log(`seeding ${OPFS_NAME} into OPFS via /bin/bw_seed.html`);
await page.goto(`${BASE}/bin/bw_seed.html`, { waitUntil: 'domcontentloaded' });
const seedRes = await page.evaluate(async ({ b64, name }) => {
  try {
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    const root = await navigator.storage.getDirectory();
    const fh = await root.getFileHandle(name, { create: true });
    const w = await fh.createWritable();
    await w.write(arr);
    await w.close();
    const rf = await (await root.getFileHandle(name)).getFile();
    return { ok: true, size: rf.size };
  } catch (e) { return { ok: false, err: String(e) }; }
}, { b64: blendB64, name: OPFS_NAME });
log(`OPFS seed: ${JSON.stringify(seedRes)}`);
if (!seedRes.ok) { console.error('OPFS seed FAILED'); await browser.close(); process.exit(3); }

const url = `${BASE}/windowed.html?gate=${W}x${H}&args=${encodeURIComponent(BLEND_PATH)}&pyexpr=${encodeURIComponent(PYEXPR)}`;
const allLines = [], bindLines = [], gpuErrors = [];
page.on('console', (m) => {
  const t = m.text();
  allLines.push(t);
  if (t.includes('[bw-r43bind]')) bindLines.push(t);
  if (t.includes('GPU-ERROR') || t.includes('GPU-LOST')) gpuErrors.push(t);
});
log(`booting windowed engine=${ENGINE}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log('WM_main up');

// neutral mouse move over the canvas so a fresh boot composites (rAF gate).
try {
  const box = await page.evaluate(() => {
    const c = document.querySelector('canvas');
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });
  if (box) { await page.mouse.move(box.x, box.y); await page.mouse.move(box.x + 3, box.y + 3); }
} catch (e) { /* ignore */ }

let doneTxt = null;
const tR = Date.now();
while (Date.now() - tR < SETTLE_MS) {
  doneTxt = await page.evaluate(() => {
    try { return window.__bwModule.FS.readFile('/tmp/m6_bridge_done', { encoding: 'utf8' }); }
    catch (e) { return null; }
  }).catch(() => null);
  if (doneTxt) break;
  await page.waitForTimeout(1500).catch(() => {});
}
log(`render sentinel: ${doneTxt ? JSON.stringify(doneTxt) : '(timeout)'}`);
// give the async uncaptured-error callbacks + dumps a moment to flush
await page.waitForTimeout(3000).catch(() => {});

writeFileSync(`${CAPDIR}/console.all.log`, allLines.join('\n'));
writeFileSync(`${CAPDIR}/bind.log`, bindLines.join('\n'));
writeFileSync(`${CAPDIR}/gpuerrors.log`, gpuErrors.join('\n'));
await page.screenshot({ path: `${CAPDIR}/composite.png` }).catch(() => {});
// pull the F12 render-result PNG (black under the bug) out of the wasm FS.
try {
  const png = await page.evaluate(() => {
    try {
      const b = window.__bwModule.FS.readFile('/tmp/r43_render0001.png');
      let s = ''; for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
      return { len: b.length, b64: btoa(s) };
    } catch (e) { return null; }
  });
  if (png && png.b64) writeFileSync(`${CAPDIR}/render_f12.png`, Buffer.from(png.b64, 'base64'));
} catch (e) { /* ignore */ }

console.log('\n==== R43 DIAG RESULT ====');
console.log('engine     :', ENGINE);
console.log('sentinel   :', doneTxt);
console.log('bindLines  :', bindLines.length);
console.log('gpuErrors  :', gpuErrors.length);
console.log('capdir     :', CAPDIR);
if (gpuErrors.length) console.log('gpuErr[0]  :', gpuErrors[0]);
await browser.close();
process.exit(0);
