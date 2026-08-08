// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r38 - colour-management lane: dump the OCIO view-transform GPU path.
// Boots windowed-opt with BW_DIAG (via pyexpr), forces a fresh AgX display-shader
// construction by toggling use_curve_mapping (cache-key change; OCIO_to_display is
// unchanged), so the BW_DIAG-gated dumps fire:
//   [bw-r38-ocio-construct] which binder + view/display/look
//   [bw-r38-lut3d]/[bw-r38-lut1d2d] LUT metadata + first source values
//   [bw-r38-ocio-src-*] the generated OCIO GLSL (AgX log2 + LUT sample)
//   [bw-r38-params] scene_linear_matrix / exponent / scale (exposure check)
//   [bw-r38-wgsl-*] the Tint-translated WGSL for OCIO_Display
// Also schedules a viewport_color readback (post-AgX composite).
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r38/disc.mjs [label] [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'disc').trim();
const PORT = parseInt(process.argv[3] || '8129', 10);
const SETTLE_MS = parseInt(process.argv[4] || '45000', 10);
const W = 1600, H = 900;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r38';
const BOOT_MS = 240000;

const PY = [
  'import bpy, os, json',
  'os.environ["BW_DIAG"] = "1"',
  'def _dump_info():',
  '    try:',
  '        info = {}',
  '        info["view_transform"] = bpy.context.scene.view_settings.view_transform',
  '        info["look"] = bpy.context.scene.view_settings.look',
  '        info["use_curve_mapping"] = bool(bpy.context.scene.view_settings.use_curve_mapping)',
  '        info["exposure"] = bpy.context.scene.view_settings.exposure',
  '        info["gamma"] = bpy.context.scene.view_settings.gamma',
  '        info["display_device"] = bpy.context.scene.display_settings.display_device',
  '        os.write(2, ("[bw-r38-info] " + json.dumps(info) + "\\n").encode())',
  '    except Exception as e:',
  '        os.write(2, ("[bw-r38-info-err] " + repr(e) + "\\n").encode())',
  'def _redraw():',
  '    for win in bpy.context.window_manager.windows:',
  '        scr = win.screen',
  '        if not scr: continue',
  '        for area in scr.areas:',
  '            if area.type == "VIEW_3D":',
  '                for region in area.regions:',
  '                    if region.type == "WINDOW":',
  '                        region.tag_redraw()',
  '# Cycle >4 distinct view transforms (cache MAX_SIZE=4) to EVICT the boot-cached AgX,',
  '# then land on AgX so a FRESH AgX display-shader is constructed with BW_DIAG set.',
  '_seq = ["Filmic", "Raw", "False Color", "Khronos PBR Neutral", "Standard", "AgX"]',
  '_bw = {"n": 0}',
  'def _setvt(vt):',
  '    try:',
  '        bpy.context.scene.view_settings.view_transform = vt',
  '        os.write(2, ("[bw-r38] set view_transform=" + vt + "\\n").encode())',
  '    except Exception as e:',
  '        os.write(2, ("[bw-r38-setvt-err] " + vt + " " + repr(e) + "\\n").encode())',
  'def _bw_kick():',
  '    _bw["n"] += 1',
  '    n = _bw["n"]',
  '    os.environ["BW_DIAG"] = "1"',
  '    try:',
  '        if 2 <= n <= 7:',
  '            _setvt(_seq[n - 2])',
  '        if n == 9:',
  '            _dump_info()',
  '        _redraw()',
  '        if n == 14:',
  '            open("/tmp/bw_diag_cmd", "w").write("readback viewport_color\\n")',
  '            os.write(2, b"[bw-r38] scheduled: readback viewport_color (scene=AgX)\\n")',
  '    except Exception as e:',
  '        os.write(2, ("[bw-kick] " + repr(e) + "\\n").encode())',
  '    return 0.4',
  'bpy.app.timers.register(_bw_kick, first_interval=0.5)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PY)}`;
function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

const all = [];
page.on('console', (m) => { all.push(m.text()); });
page.on('pageerror', (e) => { all.push('[pageerror] ' + String(e)); });

log(`booting ${LABEL} url-len=${url.length} port=${PORT}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
const tB = Date.now();
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log(`WM_main in ${Date.now() - tB} ms; settling ${SETTLE_MS} ms`);
await page.waitForTimeout(SETTLE_MS);

writeFileSync(`${OUTDIR}/r38-${LABEL}.all.log`, all.join('\n') + '\n');

// Extract marker sections for a quick readable summary.
function grep(prefix) { return all.filter((l) => l.includes(prefix)); }
function sliceBetween(beginMark, endMark) {
  const out = [];
  let on = false;
  for (const l of all) {
    if (l.includes(beginMark)) { on = true; out.push(l); continue; }
    if (l.includes(endMark)) { out.push(l); on = false; continue; }
    if (on) out.push(l);
  }
  return out;
}

console.log('\n==== [bw-r38-info] ====');
grep('[bw-r38-info]').forEach((l) => console.log(l));
console.log('\n==== [bw-r38-ocio-construct] ====');
grep('[bw-r38-ocio-construct]').forEach((l) => console.log(l));
console.log('\n==== [bw-r38-lut*] ====');
grep('[bw-r38-lut').forEach((l) => console.log(l));
console.log('\n==== [bw-r38-params] ====');
grep('[bw-r38-params]').forEach((l) => console.log(l));
console.log('\n==== OCIO GLSL src (lines) ====');
console.log(String(sliceBetween('[bw-r38-ocio-src-begin]', '[bw-r38-ocio-src-end]').length) + ' lines captured');
console.log('\n==== OCIO WGSL (lines) ====');
console.log(String(sliceBetween('[bw-r38-wgsl-begin]', '[bw-r38-wgsl-end]').length) + ' lines captured');
console.log('\n==== READBACK DONE ====');
grep('BW_READBACK_DONE').forEach((l) => console.log(l));
console.log('\n(full console -> ' + `${OUTDIR}/r38-${LABEL}.all.log` + ')');

await browser.close();
