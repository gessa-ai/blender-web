// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r31 — tick-pumped diagnostic GPU readback driver + gbuffer discriminator.
// Boots the windowed opt build with a ?pyexpr= that (1) sets BW_DIAG=1 to arm the
// diagnostic, (2) kicks VIEW_3D redraws every 0.3s so WGPUContext::activate keeps
// pumping instance.ProcessEvents (the "consume" half), and (3) writes /tmp/bw_diag_cmd
// commands on a schedule: `arm 2` (capture the gbuffer right after the next 2 workbench
// prepass submits = state (a)), then a batch of `readback <target>` (state (b) + the
// viewport_color self-test). The backend writes each readback to /tmp/bw_readback_<n>.bin
// with a header + one raw-fd-2 stderr line; this driver captures those lines, then reads
// each file back via window.__bwModule.FS.readFile and analyses it in-page.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r31/diag_readback.mjs [label] [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'r31').trim();
const PORT = parseInt(process.argv[3] || '8124', 10);
const SETTLE_MS = parseInt(process.argv[4] || '30000', 10);
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r31';
const EVID = '/Users/paws/blender-web/platform_web/shell/evidence';
const BOOT_MS = 240000;

const PYEXPR = [
  'import bpy, os',
  'os.environ["BW_DIAG"] = "1"',
  'os.environ["BW_DIAG_ARM"] = "3"',  // capture the boot render's prepass = state (a)
  'bpy.context.preferences.view.show_splash = False',
  '_bw = {"n": 0}',
  'def _bw_kick():',
  '    _bw["n"] += 1',
  '    n = _bw["n"]',
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
  '    if n == 30:',
  '        cmds = "readback viewport_color\\nreadback gbuffer_depth\\nreadback gbuffer_material\\nreadback gbuffer_normal\\nreadback gbuffer_objectid\\n"',
  '        open("/tmp/bw_diag_cmd", "w").write(cmds)',
  '        os.write(2, b"[bw-diag] scheduled: readback batch (state b + self-test)\\n")',
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
const kicks = [];       // BW_READBACK_KICK
const dones = [];       // BW_READBACK_DONE (with file=)
const diag = [];        // [bw-diag]/BW_DIAG lines
const gpuErrors = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.includes('BW_READBACK_KICK')) kicks.push(t);
  if (t.includes('BW_READBACK_DONE')) dones.push(t);
  if (t.includes('[bw-diag]') || t.startsWith('BW_DIAG')) diag.push(t);
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

log(`settling ${SETTLE_MS} ms (kick + scheduled diag commands)…`);
await page.waitForTimeout(SETTLE_MS);

// Parse the DONE lines for (seq,label,file,status).
function parseKV(line) {
  const o = {};
  for (const m of line.matchAll(/(\w+)=([^\s]+)/g)) o[m[1]] = m[2];
  return o;
}
const fileTargets = dones.map(parseKV).filter((o) => o.file);

// Read + analyse each dumped file in-page via FS.readFile.
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
      const magic = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
      const ver = dv.getUint32(4, true), w = dv.getUint32(8, true), h = dv.getUint32(12, true);
      const fmt = dv.getUint32(16, true), texel = dv.getUint32(20, true);
      const pitch = dv.getUint32(24, true), dbytes = dv.getUint32(28, true);
      const HDR = 32;
      const data = bytes.subarray(HDR);
      let nz = 0, mn = 255, mx = 0;
      const step = Math.max(1, (data.length / 400000) | 0); // sample large buffers
      let sampled = 0;
      for (let i = 0; i < data.length; i += step) {
        const v = data[i]; sampled++;
        if (v) nz++; if (v < mn) mn = v; if (v > mx) mx = v;
      }
      const cx = (w / 2) | 0, cy = (h / 2) | 0;
      const coff = cy * pitch + cx * texel;
      const centerTexel = Array.from(data.subarray(coff, coff + texel));
      const res = {
        path, label, magic, ver, w, h, fmt, texel, pitch, dbytes,
        dataLen: data.length, nzFrac: +(nz / sampled).toFixed(4), mn, mx, centerTexel,
      };
      if (label.includes('depth') && texel === 4) {
        const fdv = new DataView(data.buffer, data.byteOffset, data.byteLength);
        let written = 0, total = 0, dmin = 1e30, dmax = -1e30;
        const sy = Math.max(1, (h / 400) | 0), sx = Math.max(1, (w / 400) | 0);
        for (let y = 0; y < h; y += sy) for (let x = 0; x < w; x += sx) {
          const f = fdv.getFloat32(y * pitch + x * 4, true);
          total++; if (f < 0.9999) written++;
          if (f < dmin) dmin = f; if (f > dmax) dmax = f;
        }
        res.depth = {
          centerF32: fdv.getFloat32(coff, true),
          writtenFrac: +(written / total).toFixed(4), min: dmin, max: dmax,
        };
      }
      return res;
    }
    return targets.map(analyze);
  }, fileTargets);
} catch (e) {
  analyses = [{ error: 'page.evaluate failed: ' + String(e) }];
}

await page.screenshot({ path: `${EVID}/m4-r31-${LABEL}-shot.png`, clip });

writeFileSync(`${OUTDIR}/r31-${LABEL}.all.log`, all.join('\n') + '\n');
writeFileSync(`${OUTDIR}/r31-${LABEL}.analyses.json`, JSON.stringify({ kicks, dones, diag, analyses }, null, 2));

console.log(`\n==== BW_DIAG lines (${diag.length}) ====`);
diag.forEach((l) => console.log('  ' + l));
console.log(`\n==== KICK lines (${kicks.length}) ====`);
kicks.forEach((l) => console.log('  ' + l));
console.log(`\n==== DONE lines (${dones.length}) ====`);
dones.forEach((l) => console.log('  ' + l));
console.log(`\n==== FILE ANALYSES (${analyses.length}) ====`);
for (const a of analyses) console.log('  ' + JSON.stringify(a));
console.log(`\n==== GPU errors: ${gpuErrors.length} ====`);
gpuErrors.slice(0, 8).forEach((e) => console.log('  ! ' + e.slice(0, 200)));

await ctx.close();
await browser.close();
log('done');
