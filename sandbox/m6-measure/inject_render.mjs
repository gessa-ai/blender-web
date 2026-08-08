// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M6 GPU-suite extraction confirmation with a REAL suite blend. Injects a host
// .blend into WasmFS (FS.writeFile), opens it (load_ui=False, keeping the live
// GHOST/WebGPU context), forces the suite engine, renders frame 1 to a WasmFS
// PNG, and pulls the bytes back via FS.readFile. Proves the offscreen render-to-
// file extraction path on a representative suite scene (not just the factory
// cube). No backend edits; diagnostic only.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/m6-measure/inject_render.mjs <hostBlendPath> <ENGINE> <outName> [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync, readFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const HOST_BLEND = process.argv[2];
const ENGINE = (process.argv[3] || 'BLENDER_WORKBENCH').trim();
const OUTNAME = process.argv[4] || 'inject';
const PORT = parseInt(process.argv[5] || '8126', 10);
const SETTLE_MS = parseInt(process.argv[6] || '180000', 10);
const W = 640, H = 480;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/m6-measure';
const BOOT_MS = 300000;

const blendB64 = readFileSync(HOST_BLEND).toString('base64');

const PYEXPR = [
  'import bpy, os',
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
  '        if not os.path.exists("/tmp/inject.blend"):',
  '            return 0.5',   // wait until the rig has written the blend
  '        bpy.ops.wm.open_mainfile(filepath="/tmp/inject.blend", load_ui=False)',
  '        sc = bpy.context.scene',
  '        sc.render.engine = "' + ENGINE + '"',
  '        sc.frame_set(1)',
  '        sc.render.image_settings.file_format = "PNG"',
  '        sc.render.filepath = "/tmp/m6_inject"',
  '        print("M6_INJECT_START engine=" + sc.render.engine + " res=%dx%d" % (sc.render.resolution_x*sc.render.resolution_percentage//100, sc.render.resolution_y*sc.render.resolution_percentage//100))',
  '        bpy.ops.render.render(write_still=True)',
  '        open("/tmp/m6_inject_done", "w").write("OK " + sc.render.engine)',
  '        print("M6_INJECT_DONE")',
  '    except Exception as e:',
  '        open("/tmp/m6_inject_done", "w").write("ERR " + repr(e))',
  '        print("M6_INJECT_FAIL " + repr(e))',
  '    return None',
  'bpy.app.timers.register(_bw_render, first_interval=6.0)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PYEXPR)}`;
function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 80, height: H + 80 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const marks = [], gpuErrors = [];
page.on('console', (m) => {
  const t = m.text();
  if (t.includes('M6_INJECT')) marks.push(t);
  if (t.includes('GPU-ERROR') || t.includes('GPU-LOST')) gpuErrors.push(t);
});

log(`booting ${HOST_BLEND} engine=${ENGINE}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log('WM_main up; injecting blend into WasmFS');

// Write the blend into WasmFS from the host bytes.
await page.evaluate((b64) => {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  window.__bwModule.FS.writeFile('/tmp/inject.blend', arr);
}, blendB64);
log('blend written to /tmp/inject.blend; waiting for render sentinel');

const tR = Date.now();
let doneTxt = null;
while (Date.now() - tR < SETTLE_MS) {
  doneTxt = await page.evaluate(() => {
    try { return window.__bwModule.FS.readFile('/tmp/m6_inject_done', { encoding: 'utf8' }); }
    catch (e) { return null; }
  });
  if (doneTxt) break;
  await page.waitForTimeout(1500);
}
log(`sentinel: ${doneTxt === null ? '(timeout)' : JSON.stringify(doneTxt)} after ${Date.now() - tR} ms`);

const analysis = await page.evaluate(() => {
  const M = window.__bwModule;
  let bytes;
  try { bytes = M.FS.readFile('/tmp/m6_inject.png'); } catch (e) { return { error: 'readFile: ' + String(e) }; }
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  const out = { pngLen: bytes.length, b64: btoa(bin) };
  out.pngSig = (bytes[0] === 0x89 && bytes[1] === 0x50);
  if (bytes.length > 24) {
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    out.width = dv.getUint32(16, false); out.height = dv.getUint32(20, false);
  }
  return out;
}).catch((e) => ({ error: String(e) }));

if (analysis && analysis.b64) {
  writeFileSync(`${OUTDIR}/evidence/${OUTNAME}.png`, Buffer.from(analysis.b64, 'base64'));
  delete analysis.b64;
}
await page.screenshot({ path: `${OUTDIR}/evidence/${OUTNAME}_composite.png` });
writeFileSync(`${OUTDIR}/${OUTNAME}.json`, JSON.stringify({ hostBlend: HOST_BLEND, engine: ENGINE, sentinel: doneTxt, analysis, gpuErrorCount: gpuErrors.length, marks }, null, 2));

console.log('\n==== INJECT-RENDER RESULT ====');
console.log('blend    :', HOST_BLEND);
console.log('engine   :', ENGINE);
console.log('sentinel :', doneTxt);
console.log('analysis :', JSON.stringify(analysis));
console.log('gpuErrs  :', gpuErrors.length);
console.log('marks    :', marks.join(' | '));
await browser.close();
process.exit(0);
