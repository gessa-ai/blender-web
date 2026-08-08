// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M6 r35 TICK-PUMPED RENDER-RESULT BRIDGE driver.
//
// The synchronous GPU readback the render OP uses returns zeros in the windowed
// WM-worker profile (gpu-sync-readback-windowed), so bpy.ops.render.render writes a
// BLACK PNG. This rig instead pulls the TRUE bytes via the BW_DIAG-gated hook in
// WGPUTexture::read (patch 0125): every read() kicks a tick-pumped async readback
// (diag_kick_readback, AllowSpontaneous) whose bytes land in /tmp/bw_readback_<seq>.bin
// on a later main-loop tick. The rig:
//   1. boots windowed-opt with BW_DIAG=1 (set in os.environ before any render),
//   2. (inject mode) writes a suite .blend and open_mainfile's it,
//   3. clears stale /tmp/bw_readback_*.bin, forces the engine + 128x128, renders,
//   4. keeps ticking (the redraw kick keeps the loop alive) and polls until the diag
//      dumps stabilise, then pulls every bw_readback_*.bin via FS.readFile.
// The host then decodes the render-result dump (decode_readback.py) and compares to the
// golden with oiiotool. RenderResult/PNG stays black on purpose; the truth is the dump.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node bridge_render.mjs <factory|inject> <blendPathOrDash> <ENGINE> <outName> \
//        [port] [settleMs] [resW] [resH]

import { createRequire } from 'module';
import { writeFileSync, readFileSync, mkdirSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const MODE = (process.argv[2] || 'factory').trim();        // factory | inject
const HOST_BLEND = process.argv[3] || '-';
const ENGINE = (process.argv[4] || 'BLENDER_WORKBENCH').trim();
const OUTNAME = process.argv[5] || 'out';
const PORT = parseInt(process.argv[6] || '8126', 10);
const SETTLE_MS = parseInt(process.argv[7] || '240000', 10);
const RESW = parseInt(process.argv[8] || '128', 10);
const RESH = parseInt(process.argv[9] || '128', 10);
// Seconds to let the viewport redraw the newly-opened scene (rebuilding GPU resources)
// after open_mainfile before rendering, so the render is not on a half-migrated context.
const SETTLE_OPEN = parseFloat(process.argv[10] || '8');
const W = 640, H = 480;                                     // gate/canvas size
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r35';
const CAPDIR = `${OUTDIR}/caps/${OUTNAME}`;
const BOOT_MS = 300000;
mkdirSync(CAPDIR, { recursive: true });

const injectBlend = MODE === 'inject';
const blendB64 = injectBlend ? readFileSync(HOST_BLEND).toString('base64') : '';

// pyexpr: BW_DIAG on FIRST, splash off, redraw kick (keeps the loop alive so the
// AllowSpontaneous map completions fire), then a phase-driven timer:
//   inject: wait for blend -> open_mainfile -> SETTLE_OPEN s of redraws -> render.
//   factory: render the already-loaded default scene.
// The settle lets DRW rebuild the newly-opened scene's GPU resources before the render,
// avoiding a render on a half-migrated context.
const PY_INJECT = [
  'import bpy, os, glob, time',
  'os.environ["BW_DIAG"] = "1"',
  'bpy.context.preferences.view.show_splash = False',
  '_bw = {"phase": 0, "t_open": 0.0}',
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
  '    return 0.2',
  'bpy.app.timers.register(_bw_kick, first_interval=1.0)',
  'def _do_render():',
  '    sc = bpy.context.scene',
  '    sc.render.engine = "' + ENGINE + '"',
  '    sc.render.resolution_x = ' + RESW,
  '    sc.render.resolution_y = ' + RESH,
  '    sc.render.resolution_percentage = 100',
  '    sc.frame_set(1)',
  '    for f in glob.glob("/tmp/bw_readback_*.bin"):',
  '        try:',
  '            os.remove(f)',
  '        except Exception:',
  '            pass',
  '    sc.render.image_settings.file_format = "PNG"',
  '    sc.render.filepath = "/tmp/m6_bridge"',
  '    print("M6_BRIDGE_START engine=" + sc.render.engine + " res=%dx%d" % (sc.render.resolution_x, sc.render.resolution_y))',
  '    bpy.ops.render.render(write_still=True)',
  '    open("/tmp/m6_bridge_done", "w").write("OK " + sc.render.engine)',
  '    print("M6_BRIDGE_DONE")',
  'def _bw_drive():',
  '    try:',
  '        if not os.path.exists("/tmp/inject.blend"):',
  '            return 0.5',
  '        bpy.ops.wm.open_mainfile(filepath="/tmp/inject.blend", load_ui=False)',
  '        print("M6_BRIDGE_OPENED")',
  '        _do_render()',   // open + render in ONE callback: an intervening viewport
  '    except Exception as e:',  // redraw on the just-opened (corrupted) state device-loses.
  '        open("/tmp/m6_bridge_done", "w").write("ERR " + repr(e))',
  '        print("M6_BRIDGE_FAIL " + repr(e))',
  '    return None',
  'bpy.app.timers.register(_bw_drive, first_interval=5.0)',
];
const PY_FACTORY = [
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
  '        for f in glob.glob("/tmp/bw_readback_*.bin"):',
  '            try:',
  '                os.remove(f)',
  '            except Exception:',
  '                pass',
  '        sc.render.image_settings.file_format = "PNG"',
  '        sc.render.filepath = "/tmp/m6_bridge"',
  '        print("M6_BRIDGE_START engine=" + sc.render.engine + " res=%dx%d" % (sc.render.resolution_x, sc.render.resolution_y))',
  '        bpy.ops.render.render(write_still=True)',
  '        open("/tmp/m6_bridge_done", "w").write("OK " + sc.render.engine)',
  '        print("M6_BRIDGE_DONE")',
  '    except Exception as e:',
  '        open("/tmp/m6_bridge_done", "w").write("ERR " + repr(e))',
  '        print("M6_BRIDGE_FAIL " + repr(e))',
  '    return None',
  'bpy.app.timers.register(_bw_render, first_interval=8.0)',
];
const PYEXPR = (injectBlend ? PY_INJECT : PY_FACTORY).join('\n');

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PYEXPR)}`;
function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 80, height: H + 80 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const marks = [], gpuErrors = [], kicks = [], dones = [];
page.on('console', (m) => {
  const t = m.text();
  if (t.includes('M6_BRIDGE')) marks.push(t);
  if (t.includes('GPU-ERROR') || t.includes('GPU-LOST')) gpuErrors.push(t);
  if (t.includes('BW_READBACK_KICK')) kicks.push(t);
  if (t.includes('BW_READBACK_DONE')) dones.push(t);
});

log(`booting mode=${MODE} engine=${ENGINE} out=${OUTNAME}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log('WM_main up');

if (injectBlend) {
  await page.evaluate((b64) => {
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    window.__bwModule.FS.writeFile('/tmp/inject.blend', arr);
  }, blendB64);
  log('blend written to /tmp/inject.blend');
}

// Wait for the render sentinel.
const tR = Date.now();
let doneTxt = null;
while (Date.now() - tR < SETTLE_MS) {
  doneTxt = await page.evaluate(() => {
    try { return window.__bwModule.FS.readFile('/tmp/m6_bridge_done', { encoding: 'utf8' }); }
    catch (e) { return null; }
  });
  if (doneTxt) break;
  await page.waitForTimeout(1500);
}
log(`render sentinel: ${doneTxt === null ? '(timeout)' : JSON.stringify(doneTxt)} after ${Date.now() - tR} ms`);

// Keep ticking and poll for the diag dumps to appear + stabilise (the AllowSpontaneous
// completions fire on ticks AFTER the render OP returns).
let prevCount = -1, stable = 0, listing = [];
const tD = Date.now();
while (Date.now() - tD < 60000) {
  listing = await page.evaluate(() => {
    try {
      const M = window.__bwModule;
      return M.FS.readdir('/tmp').filter((f) => /^bw_readback_\d+\.bin$/.test(f)).sort();
    } catch (e) { return []; }
  });
  if (listing.length > 0 && listing.length === prevCount) {
    stable++;
    if (stable >= 3) break;
  } else {
    stable = 0;
  }
  prevCount = listing.length;
  await page.waitForTimeout(1000);
}
log(`diag dumps: ${listing.length} files ${JSON.stringify(listing)}`);

// Pull every dump to the host.
const caps = [];
for (const fn of listing) {
  const info = await page.evaluate((name) => {
    const M = window.__bwModule;
    const bytes = M.FS.readFile('/tmp/' + name);
    // parse header for reporting
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const magic = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
    const h = { magic, ver: dv.getUint32(4, true), w: dv.getUint32(8, true), hgt: dv.getUint32(12, true),
                fmt: dv.getUint32(16, true), texel: dv.getUint32(20, true), rowb: dv.getUint32(24, true),
                dbytes: dv.getUint32(28, true), len: bytes.length };
    let bin = '';
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    h.b64 = btoa(bin);
    return h;
  }, fn);
  const seq = parseInt(fn.match(/(\d+)/)[1], 10);
  writeFileSync(`${CAPDIR}/${fn}`, Buffer.from(info.b64, 'base64'));
  delete info.b64;
  caps.push({ file: fn, seq, ...info });
}

// Also pull the (black) PNG the render OP wrote, for the record.
const png = await page.evaluate(() => {
  try {
    const b = window.__bwModule.FS.readFile('/tmp/m6_bridge0001.png');
    let s = ''; for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
    return { len: b.length, b64: btoa(s) };
  } catch (e) { return null; }
});
if (png && png.b64) { writeFileSync(`${CAPDIR}/render_op_black.png`, Buffer.from(png.b64, 'base64')); }

await page.screenshot({ path: `${CAPDIR}/composite.png` });
const manifest = { mode: MODE, hostBlend: HOST_BLEND, engine: ENGINE, res: [RESW, RESH],
                   sentinel: doneTxt, gpuErrorCount: gpuErrors.length, kicks: kicks.length,
                   dones: dones.length, caps, marks, doneLines: dones.slice(-8),
                   gpuErrorSample: gpuErrors.slice(0, 8) };
writeFileSync(`${CAPDIR}/manifest.json`, JSON.stringify(manifest, null, 2));

console.log('\n==== BRIDGE RESULT ====');
console.log('mode/engine :', MODE, ENGINE);
console.log('sentinel    :', doneTxt);
console.log('kicks/dones :', kicks.length, '/', dones.length);
console.log('caps        :', caps.map((c) => `#${c.seq}:${c.w}x${c.hgt}/fmt${c.fmt}`).join(' '));
console.log('gpuErrors   :', gpuErrors.length);
console.log('capdir      :', CAPDIR);
await browser.close();
process.exit(0);
