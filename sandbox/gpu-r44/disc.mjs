// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r44 - workbench resolve lane. Boots windowed-opt with BW_DIAG + BW_DIAG_ARM +
// BW_DIAG_WORLD, arms the gbuffer + deferred-resolve-color capture (r44 diag), and
// reads back viewport_color. Clusters cube faces from the gbuffer (render space) and
// samples the RESOLVE OUTPUT (color_tx) per face (same render space) to localise the
// darkening resolve-vs-downstream, plus dumps the WorldData UBO bytes reaching the GPU.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules node sandbox/gpu-r44/disc.mjs [label] [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'disc').trim();
const PORT = parseInt(process.argv[3] || '8128', 10);
const SETTLE_MS = parseInt(process.argv[4] || '40000', 10);
const W = 1600, H = 900;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r44';
const BOOT_MS = 240000;

const PY = [
  'import bpy, os, json',
  'os.environ["BW_DIAG"] = "1"',
  'os.environ["BW_DIAG_ARM"] = "4"',
  'os.environ["BW_DIAG_WORLD"] = "1"',
  'bpy.context.preferences.view.show_splash = False',
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
  '    if n == 25:',
  '        open("/tmp/bw_diag_cmd", "w").write("readback viewport_color\\n")',
  '        os.write(2, b"[bw-r44] scheduled: readback viewport_color\\n")',
  '    return 0.3',
  'bpy.app.timers.register(_bw_kick, first_interval=1.0)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PY)}`;
function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

const all = [], dones = [], world = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.includes('BW_READBACK_DONE')) dones.push(t);
  if (t.includes('[BW_DIAG_WORLD]')) world.push(t);
});
page.on('pageerror', (e) => { all.push('[pageerror] ' + String(e)); });

log(`booting ${LABEL} url-len=${url.length} port=${PORT}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
const tB = Date.now();
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log(`WM_main in ${Date.now() - tB} ms; settling ${SETTLE_MS} ms`);
// neutral mouse move over canvas so the first composite happens
try {
  const box = await page.evaluate(() => { const c = document.querySelector('canvas'); const r = c.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
  await page.mouse.move(box.x + box.w * 0.5, box.y + box.h * 0.5);
  await page.mouse.move(box.x + box.w * 0.52, box.y + box.h * 0.5);
} catch (e) { log('mousemove err ' + e); }
await page.waitForTimeout(SETTLE_MS);

writeFileSync(`${OUTDIR}/r44-${LABEL}.all.log`, all.join('\n') + '\n');

function parseKV(line) { const o = {}; for (const m of line.matchAll(/(\w+)=([^\s]+)/g)) o[m[1]] = m[2]; return o; }
const fileTargets = dones.map(parseKV).filter((o) => o.file).map((o) => ({ label: o.label, file: o.file }));
// keep the LAST file per label (freshest)
const byLabel = {};
for (const t of fileTargets) byLabel[t.label] = t;
const targets = Object.values(byLabel);
log('readback files: ' + JSON.stringify(targets));

const analyses = await page.evaluate((targets) => {
  const M = window.__bwModule;
  function h2f(h) {
    const s = (h & 0x8000) >> 15, e = (h & 0x7C00) >> 10, f = h & 0x03FF;
    if (e === 0) return (s ? -1 : 1) * Math.pow(2, -14) * (f / 1024);
    if (e === 31) return f ? NaN : (s ? -Infinity : Infinity);
    return (s ? -1 : 1) * Math.pow(2, e - 15) * (1 + f / 1024);
  }
  function srgb2lin(c) { return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
  function read(t) {
    let bytes; try { bytes = M.FS.readFile(t.file); } catch (e) { return { label: t.label, error: String(e) }; }
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const hdr = { w: dv.getUint32(8, true), h: dv.getUint32(12, true), fmt: dv.getUint32(16, true), texel: dv.getUint32(20, true), pitch: dv.getUint32(24, true) };
    return { label: t.label, hdr, dv, bytes };
  }
  const F = {};
  for (const t of targets) { const r = read(t); F[r.label] = r; }
  const out = { have: Object.keys(F), hdrs: {} };
  for (const k of Object.keys(F)) if (!F[k].error) out.hdrs[k] = F[k].hdr;

  const obj = F['prepass_objectid'], nor = F['prepass_normal'], mat = F['prepass_material'], res = F['resolve_color'];
  if (!obj || !nor || obj.error || nor.error) { out.error = 'missing gbuffer'; return out; }
  const { w, h } = nor.hdr, B = 32;
  const oP = obj.hdr.pitch, oT = obj.hdr.texel, nP = nor.hdr.pitch, nT = nor.hdr.texel;
  const rP = res && !res.error ? res.hdr.pitch : 0, rT = res && !res.error ? res.hdr.texel : 0;
  function normal(x, y) {
    const off = B + y * nP + x * nT;
    let fx = h2f(nor.dv.getUint16(off, true)) * 4 - 2, fy = h2f(nor.dv.getUint16(off + 2, true)) * 4 - 2;
    const f = fx * fx + fy * fy, g = Math.sqrt(Math.max(0, 1 - f / 4));
    return [fx * g, fy * g, 1 - f / 2];
  }
  // resolve_color sample (RGBA16F, scene-linear). returns [r,g,b] linear or null.
  function resLin(x, y) {
    if (!res || res.error) return null;
    const off = B + y * rP + x * rT;
    return [h2f(res.dv.getUint16(off, true)), h2f(res.dv.getUint16(off + 2, true)), h2f(res.dv.getUint16(off + 4, true))];
  }
  const mP = mat && !mat.error ? mat.hdr.pitch : 0, mT = mat && !mat.error ? mat.hdr.texel : 0;
  // prepass_material RGBA16F: rgb=base_color, a=float_pair_encode(roughness,metallic).
  function matData(x, y) {
    if (!mat || mat.error) return null;
    const off = B + y * mP + x * mT;
    const rgb = [h2f(mat.dv.getUint16(off, true)), h2f(mat.dv.getUint16(off + 2, true)), h2f(mat.dv.getUint16(off + 4, true))];
    const a = h2f(mat.dv.getUint16(off + 6, true));
    const idata = Math.trunc(a);
    const roughness = (idata & 31) / 31, metallic = (idata >> 5) / 7;
    return { rgb, a, roughness, metallic };
  }
  const clusters = [];
  let cube = 0;
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const oid = obj.dv.getUint16(B + y * oP + x * oT, true);
      if (oid === 0) continue;
      cube++;
      const n = normal(x, y);
      let cl = null;
      for (const c of clusters) { const d = c.n[0] * n[0] + c.n[1] * n[1] + c.n[2] * n[2]; if (d > 0.985) { cl = c; break; } }
      if (!cl) { cl = { n: n.slice(), nSum: [0, 0, 0], count: 0, resSum: [0, 0, 0], baseSum: [0, 0, 0], aSum: 0, roughSum: 0, metalSum: 0, xSum: 0, ySum: 0 }; clusters.push(cl); }
      cl.count++; cl.nSum[0] += n[0]; cl.nSum[1] += n[1]; cl.nSum[2] += n[2]; cl.xSum += x; cl.ySum += y;
      const rl = resLin(x, y);
      if (rl) { cl.resSum[0] += rl[0]; cl.resSum[1] += rl[1]; cl.resSum[2] += rl[2]; }
      const md = matData(x, y);
      if (md) { cl.baseSum[0] += md.rgb[0]; cl.baseSum[1] += md.rgb[1]; cl.baseSum[2] += md.rgb[2]; cl.aSum += md.a; cl.roughSum += md.roughness; cl.metalSum += md.metallic; }
    }
  }
  clusters.sort((a, b) => b.count - a.count);
  out.faces = clusters.slice(0, 6).filter((c) => c.count > 200).map((c) => ({
    count: c.count,
    n_view: c.nSum.map((v) => +(v / c.count).toFixed(4)),
    centroid: [Math.round(c.xSum / c.count), Math.round(c.ySum / c.count)],
    resolve_linear: c.resSum.map((v) => +(v / c.count).toFixed(4)),
    base_color: c.baseSum.map((v) => +(v / c.count).toFixed(4)),
    mat_alpha: +(c.aSum / c.count).toFixed(3),
    roughness: +(c.roughSum / c.count).toFixed(4),
    metallic: +(c.metalSum / c.count).toFixed(4),
  }));
  out.cube = cube; out.w = w; out.h = h;

  // Per-face viewport_color sampling at the render-space centroids (r38 method). Try
  // identity and y-flip mappings; 7x7 average of the display bytes + linear decode.
  const vpF = F['viewport_color'];
  if (vpF && !vpF.error && out.faces) {
    const { w: vw, h: vh, pitch: vpp, texel: vt } = vpF.hdr;
    function sample(cx, cy, flip) {
      let n = 0, s = [0, 0, 0];
      for (let dy = -3; dy <= 3; dy++) for (let dx = -3; dx <= 3; dx++) {
        const x = cx + dx; let y = cy + dy; if (flip) y = vh - 1 - y;
        if (x < 0 || x >= vw || y < 0 || y >= vh) continue;
        const off = B + y * vpp + x * vt;
        s[0] += vpF.bytes[off]; s[1] += vpF.bytes[off + 1]; s[2] += vpF.bytes[off + 2]; n++;
      }
      if (!n) return null;
      const d = s.map((v) => +(v / n).toFixed(1));
      return { disp: d, lin: d.map((v) => +srgb2lin(v / 255).toFixed(4)) };
    }
    for (const f of out.faces) {
      f.viewport_ident = sample(f.centroid[0], f.centroid[1], false);
      f.viewport_yflip = sample(f.centroid[0], f.centroid[1], true);
    }
  }
  // viewport_color: histogram gray display levels (window space, 8-bit display-encoded).
  // Cube grays sit in a band above the background gray; overlays are chromatic/bright.
  const vp = F['viewport_color'];
  if (vp && !vp.error) {
    const { w: vw, h: vh, pitch: vpp, texel: vt } = vp.hdr;
    const hist = new Array(256).fill(0);
    for (let y = 0; y < vh; y += 1) for (let x = 0; x < vw; x += 1) {
      const off = B + y * vpp + x * vt;
      const a = vp.bytes[off], b = vp.bytes[off + 1], c = vp.bytes[off + 2];
      if (Math.abs(a - b) <= 4 && Math.abs(b - c) <= 4) { const g = Math.round((a + b + c) / 3); hist[g]++; }
    }
    // dominant gray levels
    const peaks = hist.map((n, i) => ({ v: i, n })).filter((p) => p.n > 500).sort((a, b) => b.n - a.n).slice(0, 8);
    out.viewport_gray_peaks = peaks.map((p) => ({ disp: p.v, n: p.n, lin: +srgb2lin(p.v / 255).toFixed(4) }));
    out.viewport_hdr = vp.hdr;
  }
  return out;
}, targets);

console.log('\n==== WorldData UBO (GPU-side bytes) ====');
world.slice(-6).forEach((l) => console.log(l));
console.log('\n==== READBACK headers ====');
console.log(JSON.stringify(analyses.hdrs || {}, null, 0));
console.log('\n==== per cube face: gbuffer material + viewport display/linear ====');
(analyses.faces || []).forEach((f) => console.log(`  count=${f.count} n_view=[${f.n_view}] base=[${f.base_color}] rough=${f.roughness} metal=${f.metallic} centroid=[${f.centroid}]\n      vp_ident disp=[${f.viewport_ident && f.viewport_ident.disp}] lin=[${f.viewport_ident && f.viewport_ident.lin}]\n      vp_yflip disp=[${f.viewport_yflip && f.viewport_yflip.disp}] lin=[${f.viewport_yflip && f.viewport_yflip.lin}]`));
console.log('\nviewport_color gray peaks (disp,count,linear): ' + JSON.stringify(analyses.viewport_gray_peaks || []));
console.log('cube px=' + analyses.cube + ' render=' + analyses.w + 'x' + analyses.h);
if (analyses.error) console.log('ANALYSIS ERROR: ' + analyses.error + ' have=' + JSON.stringify(analyses.have));

writeFileSync(`${OUTDIR}/r44-${LABEL}.result.json`, JSON.stringify(analyses, null, 2));
console.log('\n(full console -> ' + `${OUTDIR}/r44-${LABEL}.all.log` + ')');
await browser.close();
