// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r57 layer-view readback proof -- STARTUP-FILE variant (no live open_mainfile).
//
// open_mainfile in a live windowed session corrupts GPU bind state (GPUValidationError
// "Number of entries (6) did not match expected (7)" -> invalid CommandBuffer -> the
// render draws nothing). To measure the suite on a CLEAN GPU context, this rig instead
// boots Blender with the suite .blend as the STARTUP FILE:
//   1. navigate to a same-origin seed page (/bin/bw_seed.html, no Blender), write the
//      .blend into OPFS root -- which bw_mount_opfs mounts at /projects (persists per
//      origin, visible to the WM worker's WasmFS OPFS backend);
//   2. navigate to windowed.html?args=/projects/bw_suite.blend so creator opens it at
//      startup (fresh GPU context, no open_mainfile);
//   3. a factory-style pyexpr forces the engine + 128x128 and renders frame 1; the
//      BW_DIAG hook (patch 0125) lands the true bytes in /tmp/bw_readback_<seq>.bin.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node bridge_layer_view.mjs <blendPath> <ENGINE> <outName> [port] [settleMs] [resW] [resH]

import { createRequire } from 'module';
import { writeFileSync, readFileSync, mkdirSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const HOST_BLEND = process.argv[2];
const ENGINE = (process.argv[3] || 'BLENDER_WORKBENCH').trim();
const OUTNAME = process.argv[4] || 'out';
const PORT = parseInt(process.argv[5] || '8143', 10);
const SETTLE_MS = parseInt(process.argv[6] || '200000', 10);
const RESW = parseInt(process.argv[7] || '128', 10);
const RESH = parseInt(process.argv[8] || '128', 10);
const MODE = process.argv[9] || 'render';
const W = 640, H = 480;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r57-readback-hardening';
const CAPDIR = `${OUTDIR}/caps/${OUTNAME}`;
const BOOT_MS = 300000;
const OPFS_NAME = 'bw_suite.blend';        // OPFS root -> /projects/bw_suite.blend
const BLEND_PATH = '/projects/' + OPFS_NAME;
mkdirSync(CAPDIR, { recursive: true });

const blendB64 = readFileSync(HOST_BLEND).toString('base64');

// Factory-style render pyexpr (scene already loaded from the startup file).
const RENDER_PYEXPR = [
  'import bpy, os, glob',
  'os.environ["BW_DIAG"] = "1"',
  'os.environ["BW_READBACK_CAPTURE"] = "1"',
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
  '        for f in glob.glob("/tmp/bw_readback_*.bin") + glob.glob("/tmp/bw_prod_readback_*.bin"):',
  '            try:',
  '                os.remove(f)',
  '            except Exception:',
  '                pass',
  '        sc.render.image_settings.file_format = "PNG"',
  '        sc.render.filepath = "/tmp/m6_bridge"',
  '        print("M6_BRIDGE_START engine=" + sc.render.engine + " res=%dx%d file=" % (sc.render.resolution_x, sc.render.resolution_y) + (bpy.data.filepath or "<none>"))',
  '        bpy.ops.render.render(write_still=True)',
  '        open("/tmp/m6_bridge_done", "w").write("OK " + sc.render.engine)',
  '        print("M6_BRIDGE_DONE")',
  '    except Exception as e:',
  '        open("/tmp/m6_bridge_done", "w").write("ERR " + repr(e))',
  '        print("M6_BRIDGE_FAIL " + repr(e))',
  '    return None',
  'bpy.app.timers.register(_bw_render, first_interval=7.0)',
].join('\n');

const VIEWPORT_PYEXPR = [
  'import bpy',
  'bpy.context.preferences.view.show_splash = False',
  'bpy.context.scene.render.engine = "' + ENGINE + '"',
  '_bw_view_ticks = 0',
  'def _bw_view():',
  '    global _bw_view_ticks',
  '    _bw_view_ticks += 1',
  '    for win in bpy.context.window_manager.windows:',
  '        if not win.screen:',
  '            continue',
  '        for area in win.screen.areas:',
  '            if area.type != "VIEW_3D":',
  '                continue',
  '            space = area.spaces.active',
  '            space.shading.type = "RENDERED"',
  '            space.overlay.show_overlays = False',
  '            space.show_gizmo = False',
  '            space.region_3d.view_perspective = "CAMERA"',
  '            for region in area.regions:',
  '                if region.type == "WINDOW":',
  '                    region.tag_redraw()',
  '    if _bw_view_ticks >= 80:',
  '        open("/tmp/m6_bridge_done", "w").write("OK VIEWPORT " + bpy.context.scene.render.engine)',
  '        return None',
  '    return 0.5',
  'bpy.app.timers.register(_bw_view, first_interval=1.0)',
].join('\n');

const PYEXPR = MODE === 'viewport' ? VIEWPORT_PYEXPR : RENDER_PYEXPR;

function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 80, height: H + 80 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

// --- Step 1: seed the blend into OPFS root from a same-origin page (no Blender boot).
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
    // verify
    const rf = await (await root.getFileHandle(name)).getFile();
    return { ok: true, size: rf.size };
  } catch (e) { return { ok: false, err: String(e) }; }
}, { b64: blendB64, name: OPFS_NAME });
log(`OPFS seed: ${JSON.stringify(seedRes)}`);
if (!seedRes.ok) { console.error('OPFS seed FAILED'); await browser.close(); process.exit(3); }

// --- Step 2: boot windowed with the blend as the startup file arg.
const url = `${BASE}/windowed.html?gate=${W}x${H}&args=${encodeURIComponent(BLEND_PATH)}&pyexpr=${encodeURIComponent(PYEXPR)}`;
const marks = [], gpuErrors = [], kicks = [], dones = [], binddump = [], deviceReceipts = [];
const consoleLines = [], pageErrors = [], prodReceipts = [];
page.on('console', (m) => {
  const t = m.text();
  consoleLines.push(`[${m.type()}] ${t}`);
  if (t.includes('M6_BRIDGE')) marks.push(t);
  if (t.includes('GPU-ERROR') || t.includes('GPU-LOST')) gpuErrors.push(t);
  if (t.includes('BW_READBACK_KICK')) kicks.push(t);
  if (t.includes('BW_READBACK_DONE')) dones.push(t);
  if (t.includes('R52-BIND') || t.includes('R52-IMG')) binddump.push(t);
  if (t.includes('WM-worker WebGPU device pre-acquired')) deviceReceipts.push(t);
  if (t.includes('BW_PROD_READBACK')) prodReceipts.push(t);
});
page.on('pageerror', (e) => pageErrors.push(String(e)));
log(`booting windowed with args=${BLEND_PATH} engine=${ENGINE}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log('WM_main up');

// --- Step 3: wait for render sentinel, then pull the diag dumps.
const tR = Date.now();
// Heavy EEVEE scenes can device-lose / crash the tab; a crashed page rejects every
// page.* call at the Node level (the in-page try/catch cannot catch a dead target).
// Everything below is crash-tolerant and a manifest is ALWAYS written (in finally) so
// the scene is scored as a render-crash instead of losing the whole batch.
let pageCrashed = false;
page.on('crash', () => { pageCrashed = true; });
async function safeEval(fn, arg) {
  try { return await page.evaluate(fn, arg); } catch (e) { pageCrashed = true; return undefined; }
}

let doneTxt = null;
const caps = [];
let listing = [];
let operatorPng = null;
try {
  const tR2 = Date.now();
  while (Date.now() - tR2 < SETTLE_MS && !pageCrashed) {
    doneTxt = await safeEval(() => {
      try { return window.__bwModule.FS.readFile('/tmp/m6_bridge_done', { encoding: 'utf8' }); }
      catch (e) { return null; }
    });
    if (doneTxt) break;
    if (pageCrashed) break;
    await page.waitForTimeout(1500).catch(() => { pageCrashed = true; });
  }
  log(`render sentinel: ${doneTxt ? JSON.stringify(doneTxt) : (pageCrashed ? '(page crashed)' : '(timeout)')}`);

  let prevCount = -1, stable = 0;
  const tD = Date.now();
  while (Date.now() - tD < 30000 && !pageCrashed) {
    listing = await safeEval(() => {
      try {
        return window.__bwModule.FS.readdir('/tmp')
          .filter((f) => /^bw_(?:prod_)?readback_\d+\.bin$/.test(f)).sort();
      } catch (e) { return []; }
    }) || [];
    if (listing.length > 0 && listing.length === prevCount) { stable++; if (stable >= 3) break; }
    else stable = 0;
    prevCount = listing.length;
    if (pageCrashed) break;
    await page.waitForTimeout(1000).catch(() => { pageCrashed = true; });
  }
  log(`diag dumps: ${listing.length} files ${JSON.stringify(listing)}`);

  for (const fn of listing) {
    const info = await safeEval((name) => {
      const M = window.__bwModule;
      const bytes = M.FS.readFile('/tmp/' + name);
      const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      const h = { magic: String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]),
                  ver: dv.getUint32(4, true), w: dv.getUint32(8, true), hgt: dv.getUint32(12, true),
                  fmt: dv.getUint32(16, true), texel: dv.getUint32(20, true), rowb: dv.getUint32(24, true),
                  dbytes: dv.getUint32(28, true), len: bytes.length };
      let bin = ''; for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      h.b64 = btoa(bin);
      return h;
    }, fn);
    if (!info) continue;
    const seq = parseInt(fn.match(/(\d+)/)[1], 10);
    writeFileSync(`${CAPDIR}/${fn}`, Buffer.from(info.b64, 'base64'));
    delete info.b64;
    caps.push({ file: fn, seq, ...info });
  }

  const png = await safeEval(() => {
    try {
      const M = window.__bwModule;
      const names = M.FS.readdir('/tmp').filter((f) => /^m6_bridge.*\.png$/.test(f)).sort();
      if (names.length === 0) return null;
      const name = names[names.length - 1];
      const b = M.FS.readFile('/tmp/' + name);
      let s = ''; for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
      return { name, len: b.length, b64: btoa(s) };
    } catch (e) { return null; }
  });
  if (png && png.b64) {
    operatorPng = {name: png.name, len: png.len};
    writeFileSync(`${CAPDIR}/render_operator.png`, Buffer.from(png.b64, 'base64'));
  }
  await page.screenshot({ path: `${CAPDIR}/composite.png` }).catch(() => { pageCrashed = true; });
} catch (e) {
  log('post-boot error (treated as page crash): ' + String(e));
  pageCrashed = true;
} finally {
  const manifest = { mode: MODE, hostBlend: HOST_BLEND, engine: ENGINE, res: [RESW, RESH],
                     opfs: seedRes, sentinel: doneTxt, pageCrashed, gpuErrorCount: gpuErrors.length,
                     pageErrorCount: pageErrors.length,
                     kicks: kicks.length, dones: dones.length, caps, marks, operatorPng,
                     deviceReceipts, prodReceipts,
                     doneLines: dones.slice(-8), gpuErrorSample: gpuErrors.slice(0, 8),
                     pageErrorSample: pageErrors.slice(0, 8) };
  writeFileSync(`${CAPDIR}/manifest.json`, JSON.stringify(manifest, null, 2));
  writeFileSync(`${CAPDIR}/console.log`, consoleLines.join('\n') + '\n');
  writeFileSync(`${CAPDIR}/pageerrors.log`, pageErrors.join('\n') + (pageErrors.length ? '\n' : ''));
  /* r46: full deduplicated GPU-error set (the manifest sample is only 8). */
  try {
    const seen = new Map();
    for (const e of gpuErrors) { seen.set(e, (seen.get(e) || 0) + 1); }
    const lines = [...seen.entries()].sort((a, b) => b[1] - a[1])
      .map(([e, n]) => `[x${n}] ${e.replace(/\n/g, ' | ')}`);
    writeFileSync(`${CAPDIR}/gpuerrors.uniq.txt`, lines.join('\n') + '\n');
  } catch (e) { /* ignore */ }
  /* r52: dedup the BW_DIAG bind-stream dump (R52-BIND texture binds / R52-IMG storage
   * images) so the collision-vs-aspect question is decidable from the capture. */
  try {
    const seen = new Map();
    for (const e of binddump) { seen.set(e, (seen.get(e) || 0) + 1); }
    const lines = [...seen.entries()].sort((a, b) => b[1] - a[1])
      .map(([e, n]) => `[x${n}] ${e.replace(/\n/g, ' | ')}`);
    writeFileSync(`${CAPDIR}/binddump.uniq.txt`, lines.join('\n') + '\n');
  } catch (e) { /* ignore */ }
}

console.log('\n==== BOOT-BRIDGE RESULT ====');
console.log('engine   :', ENGINE);
console.log('sentinel :', doneTxt);
console.log('kicks/dones:', kicks.length, '/', dones.length);
console.log('caps     :', caps.map((c) => `#${c.seq}:${c.w}x${c.hgt}/fmt${c.fmt}`).join(' '));
console.log('gpuErrors:', gpuErrors.length);
console.log('pageErrors:', pageErrors.length);
console.log('prodReceipts:', prodReceipts.length);
console.log('capdir   :', CAPDIR);
await browser.close();
process.exit(0);
