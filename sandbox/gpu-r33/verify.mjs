// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r33 - FIX verification. Boots the windowed opt build with BW_DIAG=1 + BW_DIAG_ARM=N so
// the patch-0117 diagnostic readback captures the gbuffer the instant each of the first N
// workbench-prepass submits lands (state (a)). Pulls each /tmp/bw_readback_<n>.bin via
// window.__bwModule.FS.readFile and reports writtenFrac per attachment (material/normal/
// objectid non-zero byte fraction; depth = fraction of texels != 1.0 + min). ALSO screenshots
// the composite so the SOLID SHADED CUBE is visible at the pixel level. With the stencil-
// reference fix the prepass writes fragments (was all-empty in r31/r32) and the cube shades.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r33/verify.mjs [label] [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'verify').trim();
const PORT = parseInt(process.argv[3] || '8124', 10);
const SETTLE_MS = parseInt(process.argv[4] || '60000', 10);
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r33';
const EVID = '/Users/paws/blender-web/platform_web/shell/evidence';
const BOOT_MS = 240000;

const PYEXPR = [
  'import bpy, os',
  'os.environ["BW_DIAG"] = "1"',
  'os.environ["BW_DIAG_ARM"] = "3"',
  'bpy.context.preferences.view.show_splash = False',
  '_bw = {"n": 0}',
  'def _bw_kick():',
  '    _bw["n"] += 1',
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
  '    except Exception as e:',
  '        os.write(2, ("[bw-kick] " + repr(e) + "\\n").encode())',
  '    return 0.3',
  'bpy.app.timers.register(_bw_kick, first_interval=1.0)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PYEXPR)}`;
function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({
  viewport: { width: W + 120, height: H + 120 },
  deviceScaleFactor: 1,
});
const page = await ctx.newPage();

const all = [], r33 = [], dones = [], gpuErrors = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.includes('[bw-r33]')) r33.push(t);
  if (t.includes('BW_READBACK_DONE')) dones.push(t);
  if (t.includes('GPU-ERROR') || t.includes('GPU-LOST')) gpuErrors.push(t);
});

log(`booting label=${LABEL} url-len=${url.length}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
const tB = Date.now();
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log(`WM_main in ${Date.now() - tB} ms`);

const rect = await page.evaluate(() => {
  const r = document.getElementById('canvas').getBoundingClientRect();
  return { x: r.x, y: r.y };
});
const clip = { x: Math.round(rect.x), y: Math.round(rect.y), width: W, height: H };

log(`settling ${SETTLE_MS} ms (arm=3 prepass captures + AllowSpontaneous delivery)...`);
await page.waitForTimeout(SETTLE_MS);

function parseKV(line) {
  const o = {};
  for (const m of line.matchAll(/(\w+)=([^\s]+)/g)) o[m[1]] = m[2];
  return o;
}
const fileTargets = dones.map(parseKV).filter((o) => o.file);

let analyses = [];
try {
  analyses = await page.evaluate((targets) => {
    const M = window.__bwModule;
    function analyze(t) {
      const path = t.file, label = t.label || '';
      let bytes;
      try { bytes = M.FS.readFile(path); } catch (e) { return { path, label, error: String(e) }; }
      if (bytes.length < 32) return { path, label, error: 'short', len: bytes.length };
      const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      const w = dv.getUint32(8, true), h = dv.getUint32(12, true);
      const fmt = dv.getUint32(16, true), texel = dv.getUint32(20, true);
      const data = bytes.subarray(32);
      let nz = 0;
      for (let i = 0; i < data.length; i++) if (data[i]) nz++;
      const out = { path, label, w, h, fmt, texel, dataLen: data.length,
                    nzByteFrac: +(nz / data.length).toFixed(5) };
      // Depth: interpret as float32, writtenFrac = texels < 1.0, min value.
      if (label.indexOf('depth') >= 0 && texel === 4) {
        const fdv = new DataView(data.buffer, data.byteOffset, data.byteLength);
        const n = (data.length / 4) | 0;
        let written = 0, min = 1e9;
        for (let i = 0; i < n; i++) {
          const v = fdv.getFloat32(i * 4, true);
          if (v < 0.999999) written++;
          if (v < min) min = v;
        }
        out.depthWrittenFrac = +(written / n).toFixed(5);
        out.depthMin = +min.toFixed(5);
      }
      return out;
    }
    return targets.map(analyze);
  }, fileTargets);
} catch (e) {
  analyses = [{ error: 'page.evaluate failed: ' + String(e) }];
}

await page.screenshot({ path: `${EVID}/m4-r33-${LABEL}-shot.png`, clip });

// Dedup the draw lines by shader for a compact record.
const seen = new Set(); const draws = [];
for (const l of r33) {
  const m = l.match(/draw shader=(\S+)/);
  if (m && !seen.has(m[1])) { seen.add(m[1]); draws.push(l); }
}

writeFileSync(`${OUTDIR}/r33-${LABEL}.all.log`, all.join('\n') + '\n');
writeFileSync(`${OUTDIR}/r33-${LABEL}.analyses.json`,
  JSON.stringify({ draws, dones, analyses, gpuErrorCount: gpuErrors.length }, null, 2));

console.log(`\n==== draw lines (${draws.length}) ====`);
draws.forEach((l) => console.log('  ' + l));
console.log(`\n==== DONE (${dones.length}) ====`);
dones.forEach((l) => console.log('  ' + l));
console.log(`\n==== gbuffer analyses (${analyses.length}) ====`);
for (const a of analyses) {
  console.log(`  [${a.label}] ${a.w}x${a.h} fmt=${a.fmt} texel=${a.texel} ` +
    `nzByteFrac=${a.nzByteFrac} ` +
    (a.depthWrittenFrac !== undefined ? `depthWrittenFrac=${a.depthWrittenFrac} depthMin=${a.depthMin} ` : '') +
    `err=${a.error || '-'}`);
}
console.log(`\n==== GPU errors: ${gpuErrors.length} ====`);
gpuErrors.slice(0, 6).forEach((e) => console.log('  ! ' + e.slice(0, 200)));

await ctx.close();
await browser.close();
log('done');
