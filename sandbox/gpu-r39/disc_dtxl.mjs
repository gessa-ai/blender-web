// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r39 - DEFECT A discriminator (viewport bottom-band).
// Boots windowed-opt with BW_DIAG=1 (so begin_load_pass kicks readbacks of the
// viewport render colour target dtxl_color / res.color_render_tx, RGBA16F), settles,
// then reads back the /tmp/bw_readback_*.bin files and reports, per captured dtxl_color
// texture, the ALPHA channel row means from top to bottom - to test r36's hypothesis
// that the bottom ~59-85 px of dtxl_color carry stale/negative alpha (surfaced by the
// overlay Background alpha-under blend as the +7.8/255 band).
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r39/disc_dtxl.mjs [label] [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'dtxl').trim();
const PORT = parseInt(process.argv[3] || '8123', 10);
const SETTLE_MS = parseInt(process.argv[4] || '30000', 10);
const W = 1600, H = 900;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r39';
const BOOT_MS = 240000;

const PY = [
  'import bpy, os',
  'os.environ["BW_DIAG"] = "1"',
  'bpy.context.preferences.view.show_splash = False',
  '_bw = {"n": 0}',
  'def _bw_kick():',
  '    _bw["n"] += 1',
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
  '    return 0.25',
  'bpy.app.timers.register(_bw_kick, first_interval=1.0)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PY)}`;
function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

const all = [], dones = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.includes('BW_READBACK_DONE')) dones.push(t);
});

log(`booting ${LABEL}`);
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

// Read each dtxl_color readback and compute per-row ALPHA-channel mean (RGBA16Float).
const analyses = await page.evaluate((targets) => {
  const M = window.__bwModule;
  function h2f(h) {
    const s = (h & 0x8000) >> 15, e = (h & 0x7C00) >> 10, f = h & 0x03FF;
    if (e === 0) return (s ? -1 : 1) * Math.pow(2, -14) * (f / 1024);
    if (e === 31) return f ? NaN : (s ? -Infinity : Infinity);
    return (s ? -1 : 1) * Math.pow(2, e - 15) * (1 + f / 1024);
  }
  const out = [];
  for (const t of targets) {
    let bytes; try { bytes = M.FS.readFile(t.file); } catch (e) { out.push({ label: t.label, error: String(e) }); continue; }
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const hdr = { magic: String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]),
      w: dv.getUint32(8, true), h: dv.getUint32(12, true), fmt: dv.getUint32(16, true),
      texel: dv.getUint32(20, true), pitch: dv.getUint32(24, true) };
    const base = 32, texel = hdr.texel, pitch = hdr.pitch, w = hdr.w, h = hdr.h;
    // Per-row alpha mean (alpha = 4th half-float in each RGBA16F texel).
    const rowAlpha = [];
    let negRows = 0, minAlpha = 1e9, minRow = -1;
    for (let y = 0; y < h; y++) {
      let sum = 0, cnt = 0;
      for (let x = 0; x < w; x += 4) {
        const off = base + y * pitch + x * texel;
        if (off + 8 > bytes.byteLength) break;
        const a = h2f(dv.getUint16(off + 6, true));
        sum += a; cnt++;
      }
      const m = cnt ? sum / cnt : 0;
      rowAlpha.push(+m.toFixed(4));
      if (m < -0.02) negRows++;
      if (m < minAlpha) { minAlpha = m; minRow = y; }
    }
    // Summarize: sample rows every ~5% of height + explicit bottom 100 rows in steps.
    const sampled = {};
    const marks = [0, Math.floor(h*0.25), Math.floor(h*0.5), Math.floor(h*0.75),
                   h-100, h-85, h-70, h-59, h-40, h-20, h-10, h-1];
    for (const yy of marks) { if (yy >= 0 && yy < h) sampled['y'+yy] = rowAlpha[yy]; }
    out.push({ label: t.label, w, h, fmt: hdr.fmt, texel, negRowsBelowNeg002: negRows,
      minAlpha: +minAlpha.toFixed(4), minRow, sampledRowAlpha: sampled,
      bottom20rows: rowAlpha.slice(Math.max(0, h-20)) });
  }
  return out;
}, fileTargets);

writeFileSync(`${OUTDIR}/r39-${LABEL}.all.log`, all.join('\n') + '\n');
writeFileSync(`${OUTDIR}/r39-${LABEL}.result.json`, JSON.stringify({ dones, analyses }, null, 2));

console.log('\n==== DONE lines ====');
dones.forEach(l => console.log('  ' + l));
console.log('\n==== dtxl_color ALPHA-row analysis ====');
console.log(JSON.stringify(analyses, null, 2));

await ctx.close();
await browser.close();
log('done');
