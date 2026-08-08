// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r32 - pipeline-pool discriminator. Boots the windowed opt build with BW_DIAG=1 and
// BW_DIAG_ARM=3 (so on_draw_submit reads the gbuffer depth right after the prepass submit),
// optionally BW_NOCACHE=1 (env arg) to force a FRESH build_pipeline for the workbench
// prepass. Captures BW_POOL (hit/miss) traces and the prepass_depth texture readback and
// reports whether the prepass wrote any depth (< 1.0). If a fresh pipeline rasterizes but
// the cached one does not, the pool is the defect; if neither does, the pool is exonerated.
//
// Usage: NODE_PATH=... node sandbox/gpu-r32/pooltest.mjs [label] [port] [settleMs] [nocache]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'pool').trim();
const PORT = parseInt(process.argv[3] || '8124', 10);
const SETTLE_MS = parseInt(process.argv[4] || '75000', 10);
const NOCACHE = (process.argv[5] || '') === 'nocache';
const MRT1 = (process.argv[6] || '') === '1mrt';
const NODEPTH = (process.argv[7] || '') === 'nodepth';
const DALWAYS = (process.argv[8] || '') === 'dalways';
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r32';
const EVID = '/Users/paws/blender-web/platform_web/shell/evidence';
const BOOT_MS = 240000;

const PYEXPR = [
  'import bpy, os',
  'os.environ["BW_DIAG"] = "1"',
  'os.environ["BW_DIAG_ARM"] = "3"',
  ...(NOCACHE ? ['os.environ["BW_NOCACHE"] = "1"', 'os.environ["BW_INJECT"] = "1"'] : []),
  ...(MRT1 ? ['os.environ["BW_1MRT"] = "1"'] : []),
  ...(NODEPTH ? ['os.environ["BW_NODEPTH"] = "1"'] : []),
  ...(DALWAYS ? ['os.environ["BW_DALWAYS"] = "1"'] : []),
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
const ctx = await browser.newContext({ viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

const all = [];
const pool = [], dones = [], gpuErrors = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.startsWith('BW_POOL')) pool.push(t);
  if (t.includes('BW_READBACK_DONE')) dones.push(t);
  if (t.includes('GPU-ERROR') || t.includes('ValidationError') || t.includes('Uncaptured')) gpuErrors.push(t);
});

log(`booting label=${LABEL} nocache=${NOCACHE}`);
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

log(`settling ${SETTLE_MS} ms...`);
await page.waitForTimeout(SETTLE_MS);

function parseKV(line) { const o = {}; for (const m of line.matchAll(/(\w+)=([^\s]+)/g)) o[m[1]] = m[2]; return o; }
const targets = dones.map(parseKV).filter((o) => o.file && (o.label || '').includes('prepass'));

let analyses = [];
try {
  analyses = await page.evaluate((targets) => {
    const M = window.__bwModule;
    return targets.map((t) => {
      let bytes;
      try { bytes = M.FS.readFile(t.file); } catch (e) { return { label: t.label, error: String(e) }; }
      if (bytes.length < 32) return { label: t.label, error: 'short' };
      const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      const w = dv.getUint32(8, true), h = dv.getUint32(12, true);
      const texel = dv.getUint32(20, true), pitch = dv.getUint32(24, true);
      const data = bytes.subarray(32);
      let nz = 0;
      for (let i = 0; i < data.length; i++) if (data[i]) nz++;
      const res = { label: t.label, w, h, texel, nzFrac: +(nz / data.length).toFixed(4) };
      if ((t.label || '').includes('depth') && texel === 4) {
        const fdv = new DataView(data.buffer, data.byteOffset, data.byteLength);
        let written = 0, total = 0, dmin = 1e30, dmax = -1e30;
        const sy = Math.max(1, (h / 400) | 0), sx = Math.max(1, (w / 400) | 0);
        for (let y = 0; y < h; y += sy) for (let x = 0; x < w; x += sx) {
          const f = fdv.getFloat32(y * pitch + x * 4, true);
          total++; if (f < 0.9999) written++;
          if (f < dmin) dmin = f; if (f > dmax) dmax = f;
        }
        res.writtenFrac = +(written / total).toFixed(4); res.min = dmin; res.max = dmax;
      }
      return res;
    });
  }, targets);
} catch (e) { analyses = [{ error: String(e) }]; }

await page.screenshot({ path: `${EVID}/m4-r32-${LABEL}-shot.png`, clip });
writeFileSync(`${OUTDIR}/r32-${LABEL}.all.log`, all.join('\n') + '\n');
writeFileSync(`${OUTDIR}/r32-${LABEL}.analyses.json`, JSON.stringify({ pool, dones, analyses }, null, 2));

console.log(`\n==== BW_POOL (${pool.length}) ====`);
pool.slice(0, 40).forEach((l) => console.log('  ' + l));
console.log(`\n==== prepass_depth analyses ====`);
analyses.forEach((a) => console.log('  ' + JSON.stringify(a)));
console.log(`\n==== GPU errors: ${gpuErrors.length} ====`);
gpuErrors.slice(0, 6).forEach((e) => console.log('  ! ' + e.slice(0, 200)));

await ctx.close();
await browser.close();
log('done');
