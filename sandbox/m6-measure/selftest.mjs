// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M6 GPU-suite EXTRACTION-PATH SELF-TEST (measure lane, port 8126).
// Boots the windowed-opt WebGPU build, renders the factory-startup default cube
// with BLENDER_WORKBENCH via bpy.ops.render.render(write_still=True) to a WasmFS
// path, then pulls the PNG bytes via window.__bwModule.FS.readFile and reports
// byte-uniformity (zero fraction, distinct byte values, min/max). This proves
// whether the offscreen render-to-file extraction path yields REAL pixels or the
// all-zero/garbage output of the gpu-sync-readback-windowed deferral BEFORE any
// suite result is trusted. No backend edits; diagnostic only.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/m6-measure/selftest.mjs [engine] [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const ENGINE = (process.argv[2] || 'BLENDER_WORKBENCH').trim();
const PORT = parseInt(process.argv[3] || '8126', 10);
const SETTLE_MS = parseInt(process.argv[4] || '90000', 10);
const W = 640, H = 480;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/m6-measure';
const BOOT_MS = 300000;

// pyexpr: splash off + a redraw kick + a one-shot render timer that renders the
// already-loaded factory scene with $ENGINE to /tmp/m6_selftest.png and drops a
// /tmp/m6_selftest_done sentinel carrying OK/err.
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
  '        sc = bpy.context.scene',
  '        sc.render.engine = "' + ENGINE + '"',
  '        sc.render.resolution_x = 128',
  '        sc.render.resolution_y = 128',
  '        sc.render.resolution_percentage = 100',
  '        sc.frame_set(1)',
  '        sc.render.image_settings.file_format = "PNG"',
  '        sc.render.filepath = "/tmp/m6_selftest"',
  '        print("M6_SELFTEST_RENDER_START engine=" + sc.render.engine)',
  '        bpy.ops.render.render(write_still=True)',
  '        open("/tmp/m6_selftest_done", "w").write("OK " + sc.render.engine)',
  '        print("M6_SELFTEST_RENDER_DONE")',
  '    except Exception as e:',
  '        open("/tmp/m6_selftest_done", "w").write("ERR " + repr(e))',
  '        print("M6_SELFTEST_RENDER_FAIL " + repr(e))',
  '    return None',
  'bpy.app.timers.register(_bw_render, first_interval=8.0)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PYEXPR)}`;
function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({
  viewport: { width: W + 80, height: H + 80 },
  deviceScaleFactor: 1,
});
const page = await ctx.newPage();

const all = [], marks = [], gpuErrors = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.includes('M6_SELFTEST')) marks.push(t);
  if (t.includes('GPU-ERROR') || t.includes('GPU-LOST')) gpuErrors.push(t);
});

log(`booting engine=${ENGINE} url-len=${url.length}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
const tB = Date.now();
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log(`WM_main in ${Date.now() - tB} ms`);

// Wait for the render sentinel file (or console mark), up to SETTLE_MS.
log(`waiting up to ${SETTLE_MS} ms for /tmp/m6_selftest_done ...`);
const tR = Date.now();
let doneTxt = null;
while (Date.now() - tR < SETTLE_MS) {
  doneTxt = await page.evaluate(() => {
    try { return window.__bwModule.FS.readFile('/tmp/m6_selftest_done', { encoding: 'utf8' }); }
    catch (e) { return null; }
  });
  if (doneTxt) break;
  await page.waitForTimeout(1000);
}
log(`sentinel: ${doneTxt === null ? '(timeout, none)' : JSON.stringify(doneTxt)} after ${Date.now() - tR} ms`);

// Pull + analyze the PNG bytes from WasmFS.
const analysis = await page.evaluate(() => {
  const M = window.__bwModule;
  const out = {};
  let bytes;
  try { bytes = M.FS.readFile('/tmp/m6_selftest.png'); }
  catch (e) { return { error: 'readFile: ' + String(e) }; }
  out.pngLen = bytes.length;
  // Return the raw PNG (base64) so the host can save + oiiotool-inspect it.
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  out.b64 = btoa(bin);
  // PNG signature check + IHDR dims.
  out.pngSig = (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47);
  if (bytes.length > 24) {
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    out.width = dv.getUint32(16, false);
    out.height = dv.getUint32(20, false);
  }
  // Byte-level uniformity of the WHOLE encoded file (a real image => diverse IDAT).
  const seen = new Uint8Array(256);
  let nz = 0, distinct = 0;
  for (let i = 0; i < bytes.length; i++) { if (bytes[i]) nz++; if (!seen[bytes[i]]) { seen[bytes[i]] = 1; distinct++; } }
  out.zeroFrac = +(1 - nz / bytes.length).toFixed(5);
  out.distinctBytes = distinct;
  return out;
}).catch((e) => ({ error: 'page.evaluate: ' + String(e) }));

if (analysis && analysis.b64) {
  writeFileSync(`${OUTDIR}/evidence/selftest_${ENGINE}.png`, Buffer.from(analysis.b64, 'base64'));
  delete analysis.b64;
}

await page.screenshot({ path: `${OUTDIR}/evidence/selftest_${ENGINE}_composite.png` });
writeFileSync(`${OUTDIR}/selftest_${ENGINE}.json`,
  JSON.stringify({ engine: ENGINE, sentinel: doneTxt, analysis, gpuErrorCount: gpuErrors.length, marks }, null, 2));

console.log('\n==== SELF-TEST RESULT ====');
console.log('engine       :', ENGINE);
console.log('sentinel     :', doneTxt);
console.log('analysis     :', JSON.stringify(analysis));
console.log('gpuErrors    :', gpuErrors.length);
console.log('marks        :', marks.join(' | '));

await browser.close();
process.exit(0);
