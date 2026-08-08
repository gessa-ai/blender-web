// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r32 - bound-buffer CONTENT capture driver. Boots the windowed opt build with
// BW_DIAG=1; the backend's on_draw_capture (wgpu_diag_readback) captures, once per
// distinct hunt target (workbench prepass "wbp" + outline "oln"), the expected @binding
// layout, the actual emitted bind entries, and a buffer readback of every bound buffer +
// the indirect-args window. Each readback is written to /tmp/bw_bufread_<n>.bin with a
// BW_BUFREAD_DONE line; this driver pulls each file via window.__bwModule.FS.readFile and
// decodes it as hex / u32 / f32 for semantic comparison (prepass vs outline transforms).
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r32/bufcap.mjs [label] [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'r32').trim();
const PORT = parseInt(process.argv[3] || '8124', 10);
const SETTLE_MS = parseInt(process.argv[4] || '75000', 10);
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r32';
const EVID = '/Users/paws/blender-web/platform_web/shell/evidence';
const BOOT_MS = 240000;

const PYEXPR = [
  'import bpy, os',
  'os.environ["BW_DIAG"] = "1"',
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

const all = [];
const cap = [];         // BW_CAP / BW_CAPEXP / BW_CAPBIND
const kicks = [];       // BW_BUFREAD_KICK
const dones = [];       // BW_BUFREAD_DONE (with file=)
const gpuErrors = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.startsWith('BW_CAP')) cap.push(t);
  if (t.includes('BW_BUFREAD_KICK')) kicks.push(t);
  if (t.includes('BW_BUFREAD_DONE')) dones.push(t);
  if (t.includes('GPU-ERROR') || t.includes('ValidationError') || t.includes('Uncaptured')) {
    gpuErrors.push(t);
  }
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
  return { x: r.x, y: r.y, w: r.width, h: r.height };
});
const clip = { x: Math.round(rect.x), y: Math.round(rect.y), width: W, height: H };

log(`settling ${SETTLE_MS} ms (kick + capture + AllowSpontaneous delivery)...`);
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
    function hex(u8, n) {
      let s = '';
      for (let i = 0; i < Math.min(n, u8.length); i++) s += u8[i].toString(16).padStart(2, '0');
      return s;
    }
    function analyze(t) {
      const path = t.file, label = t.label || '';
      let bytes;
      try { bytes = M.FS.readFile(path); } catch (e) { return { path, label, error: String(e) }; }
      if (bytes.length < 32) return { path, label, error: 'short', len: bytes.length };
      const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      const magic = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
      const size = dv.getUint32(8, true);
      const HDR = 32;
      const data = bytes.subarray(HDR);
      const ddv = new DataView(data.buffer, data.byteOffset, data.byteLength);
      const nWords = Math.min(64, (data.length / 4) | 0);
      const u32 = [], f32 = [];
      for (let i = 0; i < nWords; i++) {
        u32.push(ddv.getUint32(i * 4, true));
        f32.push(+ddv.getFloat32(i * 4, true).toFixed(4));
      }
      let nz = 0;
      for (let i = 0; i < data.length; i++) if (data[i]) nz++;
      return {
        path, label, magic, size, dataLen: data.length,
        nzFrac: +(nz / data.length).toFixed(4),
        hex64: hex(data, 64), u32, f32,
      };
    }
    return targets.map(analyze);
  }, fileTargets);
} catch (e) {
  analyses = [{ error: 'page.evaluate failed: ' + String(e) }];
}

await page.screenshot({ path: `${EVID}/m4-r32-${LABEL}-shot.png`, clip });

writeFileSync(`${OUTDIR}/r32-${LABEL}.all.log`, all.join('\n') + '\n');
writeFileSync(`${OUTDIR}/r32-${LABEL}.analyses.json`,
  JSON.stringify({ cap, kicks, dones, analyses }, null, 2));

console.log(`\n==== BW_CAP lines (${cap.length}) ====`);
cap.forEach((l) => console.log('  ' + l));
console.log(`\n==== KICK lines (${kicks.length}) ====`);
kicks.forEach((l) => console.log('  ' + l));
console.log(`\n==== DONE lines (${dones.length}) ====`);
dones.forEach((l) => console.log('  ' + l));
console.log(`\n==== FILE ANALYSES (${analyses.length}) ====`);
for (const a of analyses) {
  console.log(`  [${a.label}] size=${a.size} nz=${a.nzFrac} err=${a.error || '-'}`);
  if (a.u32) console.log(`     u32: ${a.u32.slice(0, 16).join(',')}`);
  if (a.f32) console.log(`     f32: ${a.f32.slice(0, 16).join(',')}`);
}
console.log(`\n==== GPU errors: ${gpuErrors.length} ====`);
gpuErrors.slice(0, 8).forEach((e) => console.log('  ! ' + e.slice(0, 200)));

await ctx.close();
await browser.close();
log('done');
