// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r37 - DEFECT 1 discriminator (workbench solid shading delta).
// Boots windowed-opt with BW_DIAG + BW_DIAG_ARM=3, dumps (via os.write) the view
// matrix + the active solid studio-light's light directions/colours (the CORRECT L,
// shared with the native oracle), and reads back the prepass gbuffer normal / material
// / object-id + the composited viewport_color. Then it decodes the actual view-space
// normals the composite consumes, names each visible cube face by transforming to
// world space, and computes the predicted per-face brightness using (N_actual,
// L_correct). Compared against the r34-measured rankings this splits the fork:
//   predicted ranking ~ NATIVE (left brightest) -> the GPU is using a WRONG L (UBO bug)
//   predicted ranking ~ WEB (left darkest)      -> N_actual itself is wrong (normal bug)
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r37/disc.mjs [label] [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'disc').trim();
const PORT = parseInt(process.argv[3] || '8123', 10);
const SETTLE_MS = parseInt(process.argv[4] || '45000', 10);
const W = 1600, H = 900;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r37';
const BOOT_MS = 240000;

// pyexpr: BW_DIAG + boot-arm, splash off, kick timer; at n==20 dump introspection
// (view matrix + studio light) and schedule a viewport_color readback.
const PY = [
  'import bpy, os, json',
  'os.environ["BW_DIAG"] = "1"',
  'os.environ["BW_DIAG_ARM"] = "3"',
  'bpy.context.preferences.view.show_splash = False',
  'def _dump_info():',
  '    try:',
  '        info = {}',
  '        rd = None; sh = None',
  '        for win in bpy.context.window_manager.windows:',
  '            scr = win.screen',
  '            if not scr: continue',
  '            for area in scr.areas:',
  '                if area.type == "VIEW_3D":',
  '                    sp = area.spaces.active',
  '                    sh = sp.shading',
  '                    for r in area.regions:',
  '                        if r.type == "WINDOW":',
  '                            rd = r.data',
  '        if rd is not None:',
  '            vm = rd.view_matrix',
  '            info["view_matrix"] = [list(row) for row in vm]',
  '            info["is_perspective"] = rd.is_perspective',
  '        if sh is not None:',
  '            info["light"] = sh.light',
  '            info["studio_light_name"] = sh.studio_light',
  '            info["use_specular"] = bool(getattr(sh, "show_specular_highlight", False))',
  '            info["show_cavity"] = bool(getattr(sh, "show_cavity", False))',
  '            info["show_shadows"] = bool(getattr(sh, "show_shadows", False))',
  '            info["use_world_space_lighting"] = bool(getattr(sh, "use_world_space_lighting", False))',
  '            info["color_type"] = getattr(sh, "color_type", "?")',
  '            info["single_color"] = list(getattr(sh, "single_color", (0,0,0)))',
  '            sl = None',
  '            for s in bpy.context.preferences.studio_lights:',
  '                if s.name == sh.studio_light and str(s.type) == "STUDIO":',
  '                    sl = s',
  '            if sl is not None:',
  '                lights = []',
  '                for L in sl.solid_lights:',
  '                    lights.append({"use": bool(L.use), "dir": list(L.direction),',
  '                                   "diff": list(L.diffuse_color), "spec": list(L.specular_color),',
  '                                   "smooth": float(L.smooth)})',
  '                info["solid_lights"] = lights',
  '                info["ambient"] = list(sl.solid_lights[0].diffuse_color) if False else None',
  '        info["scene_view_transform"] = bpy.context.scene.view_settings.view_transform',
  '        info["display_device"] = bpy.context.scene.display_settings.display_device',
  '        os.write(2, ("[bw-r37-info] " + json.dumps(info) + "\\n").encode())',
  '    except Exception as e:',
  '        os.write(2, ("[bw-r37-info-err] " + repr(e) + "\\n").encode())',
  '_bw = {"n": 0}',
  'def _bw_kick():',
  '    _bw["n"] += 1',
  '    n = _bw["n"]',
  '    try:',
  '        for win in bpy.context.window_manager.windows:',
  '            scr = win.screen',
  '            if not scr: continue',
  '            for area in scr.areas:',
  '                if area.type == "VIEW_3D":',
  '                    for region in area.regions:',
  '                        if region.type == "WINDOW":',
  '                            region.tag_redraw()',
  '    except Exception as e:',
  '        os.write(2, ("[bw-kick] " + repr(e) + "\\n").encode())',
  '    if n == 20:',
  '        _dump_info()',
  '        open("/tmp/bw_diag_cmd", "w").write("readback viewport_color\\n")',
  '        os.write(2, b"[bw-r37] scheduled: readback viewport_color + info dumped\\n")',
  '    return 0.3',
  'bpy.app.timers.register(_bw_kick, first_interval=1.0)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PY)}`;
function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

const all = [], dones = [], info = [], errs = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.includes('BW_READBACK_DONE')) dones.push(t);
  if (t.includes('[bw-r37-info]')) info.push(t);
  if (t.includes('GPU-ERROR') || t.includes('ValidationError') || t.includes('Uncaptured')) errs.push(t);
});

log(`booting ${LABEL} url-len=${url.length}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
const tB = Date.now();
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log(`WM_main in ${Date.now() - tB} ms; settling ${SETTLE_MS} ms`);
await page.waitForTimeout(SETTLE_MS);

function parseKV(line) { const o = {}; for (const m of line.matchAll(/(\w+)=([^\s]+)/g)) o[m[1]] = m[2]; return o; }
const fileTargets = dones.map(parseKV).filter((o) => o.file);

// Analyse the readback files in-page (FS.readFile), decoding half-float normals.
const analyses = await page.evaluate((targets) => {
  const M = window.__bwModule;
  function h2f(h) {
    const s = (h & 0x8000) >> 15, e = (h & 0x7C00) >> 10, f = h & 0x03FF;
    if (e === 0) return (s ? -1 : 1) * Math.pow(2, -14) * (f / 1024);
    if (e === 31) return f ? NaN : (s ? -Infinity : Infinity);
    return (s ? -1 : 1) * Math.pow(2, e - 15) * (1 + f / 1024);
  }
  function readFile(t) {
    let bytes; try { bytes = M.FS.readFile(t.file); } catch (e) { return { label: t.label, error: String(e) }; }
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const hdr = { magic: String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]),
      w: dv.getUint32(8, true), h: dv.getUint32(12, true), fmt: dv.getUint32(16, true),
      texel: dv.getUint32(20, true), pitch: dv.getUint32(24, true) };
    return { label: t.label, hdr, bytes };
  }
  const files = {};
  for (const t of targets) { const r = readFile(t); if (!r.error) files[r.label] = r; }

  const objL = files['prepass_objectid'], norL = files['prepass_normal'], matL = files['prepass_material'], depL = files['prepass_depth'];
  if (!objL || !norL) return { error: 'missing prepass readbacks', have: Object.keys(files) };

  const { w, h } = norL.hdr;
  const objDv = new DataView(objL.bytes.buffer, objL.bytes.byteOffset, objL.bytes.byteLength);
  const norDv = new DataView(norL.bytes.buffer, norL.bytes.byteOffset, norL.bytes.byteLength);
  const matDv = matL ? new DataView(matL.bytes.buffer, matL.bytes.byteOffset, matL.bytes.byteLength) : null;
  const depDv = depL ? new DataView(depL.bytes.buffer, depL.bytes.byteOffset, depL.bytes.byteLength) : null;
  const objBase = 32, norBase = 32, matBase = 32, depBase = 32;
  const objPitch = objL.hdr.pitch, norPitch = norL.hdr.pitch, matPitch = matL ? matL.hdr.pitch : 0, depPitch = depL ? depL.hdr.pitch : 0;
  const objTexel = objL.hdr.texel, norTexel = norL.hdr.texel, matTexel = matL ? matL.hdr.texel : 0, depTexel = depL ? depL.hdr.texel : 0;

  // Collect cube pixels (object_id != 0), decode view-space normals, cluster into faces.
  function decodeNormal(x, y) {
    const off = norBase + y * norPitch + x * norTexel;
    const e0 = h2f(norDv.getUint16(off, true));
    const e1 = h2f(norDv.getUint16(off + 2, true));
    const f0 = e0 * 4 - 2, f1 = e1 * 4 - 2;
    const f = f0 * f0 + f1 * f1;
    const g = Math.sqrt(Math.max(0, 1 - f / 4));
    return [f0 * g, f1 * g, 1 - f / 2];
  }
  let cubeCount = 0;
  const clusters = []; // per visible face
  function addToCluster(n, col, dep, x, y) {
    for (const c of clusters) {
      const d = c.n[0] * n[0] + c.n[1] * n[1] + c.n[2] * n[2];
      const cl = Math.hypot(...c.n) * Math.hypot(...n);
      if (cl > 0 && d / cl > 0.98) { // same face
        c.count++;
        for (let k = 0; k < 3; k++) { c.nSum[k] += n[k]; if (col) c.colorSum[k] += col[k]; }
        c.xSum += x; c.ySum += y; if (dep != null) { c.depSum += dep; c.depN++; }
        return;
      }
    }
    clusters.push({ n: n.slice(), nSum: n.slice(), count: 1, colorSum: col ? col.slice() : [0, 0, 0],
      xSum: x, ySum: y, depSum: dep != null ? dep : 0, depN: dep != null ? 1 : 0 });
  }
  const sx = 2, sy = 2;
  for (let y = 0; y < h; y += sy) for (let x = 0; x < w; x += sx) {
    const oid = objDv.getUint16(objBase + y * objPitch + x * objTexel, true);
    if (oid === 0) continue;
    cubeCount++;
    const n = decodeNormal(x, y);
    let col = null;
    if (matDv) { const mo = matBase + y * matPitch + x * matTexel;
      col = [h2f(matDv.getUint16(mo, true)), h2f(matDv.getUint16(mo + 2, true)), h2f(matDv.getUint16(mo + 4, true))]; }
    let dep = null;
    if (depDv) dep = depDv.getFloat32(depBase + y * depPitch + x * depTexel, true);
    addToCluster(n, col, dep, x, y);
  }
  clusters.sort((a, b) => b.count - a.count);
  const faces = clusters.slice(0, 6).filter(c => c.count > 50).map(c => ({
    count: c.count,
    n_view: c.nSum.map(v => +(v / c.count).toFixed(4)),
    base_color: matDv ? c.colorSum.map(v => +(v / c.count).toFixed(3)) : null,
    centroid_px: [Math.round(c.xSum / c.count), Math.round(c.ySum / c.count)],
    mean_depth: c.depN ? +(c.depSum / c.depN).toFixed(5) : null,
  }));
  return { w, h, cubeCount, faceCount: faces.length, faces,
    norFmt: norL.hdr.fmt, norTexel, objFmt: objL.hdr.fmt,
    haveFiles: Object.keys(files) };
}, fileTargets);

// Parse the info dump (view matrix + studio lights).
let parsedInfo = null;
if (info.length) { try { parsedInfo = JSON.parse(info[info.length - 1].replace('[bw-r37-info]', '').trim()); } catch (e) { parsedInfo = { parseError: String(e), raw: info[info.length - 1] }; } }

writeFileSync(`${OUTDIR}/r37-${LABEL}.all.log`, all.join('\n') + '\n');
writeFileSync(`${OUTDIR}/r37-${LABEL}.result.json`, JSON.stringify({ dones, info: parsedInfo, analyses, gpuErrors: errs.slice(0, 20) }, null, 2));

console.log('\n==== DONE lines ====');
dones.forEach(l => console.log('  ' + l));
console.log('\n==== INFO (view matrix + studio lights) ====');
console.log(JSON.stringify(parsedInfo, null, 2));
console.log('\n==== GBUFFER FACE ANALYSIS ====');
console.log(JSON.stringify(analyses, null, 2));
console.log(`\n==== GPU errors: ${errs.length} ====`);

await ctx.close();
await browser.close();
log('done');
