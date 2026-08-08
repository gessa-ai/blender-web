// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r33 - discriminator-1 field dump + error-channel probe. Boots the windowed opt build
// with BW_DIAG=1 (and, if arg2=="canary", BW_RO_CANARY=1). The backend emits, per draw:
//   [bw-r33] draw shader=... depthFmt=... writeMask=... depthTest=... stencilTest=...
//   [bw-r33] dsa depthRO=... stencilRO=... dLoad/dStore/sLoad/sStore ... fmt=... dptr=...
// (see wgpu_batch.cc / wgpu_framebuffer.cc). The canary forces depthReadOnly=true while the
// pipeline still writes depth (a DRAW/SUBMIT-class invalid pass) to test whether the JS
// uncapturederror listener (wgpu-preinit-worker.js) surfaces this class -> [bw][GPU-ERROR].
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r33/disc1.mjs [label] [canary|plain] [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'disc1').trim();
const MODE = (process.argv[3] || 'plain').trim();
const PORT = parseInt(process.argv[4] || '8124', 10);
const SETTLE_MS = parseInt(process.argv[5] || '30000', 10);
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r33';
const BOOT_MS = 240000;

const envLines = ['os.environ["BW_DIAG"] = "1"'];
if (MODE === 'canary') envLines.push('os.environ["BW_RO_CANARY"] = "1"');

const PYEXPR = [
  'import bpy, os',
  ...envLines,
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
const r33 = [];
const gpuErrors = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.includes('[bw-r33]')) r33.push(t);
  if (t.includes('GPU-ERROR') || t.includes('GPU-LOST') || t.includes('ValidationError') ||
      t.includes('Uncaptured') || t.includes('uncaptured')) {
    gpuErrors.push(t);
  }
});

log(`booting label=${LABEL} mode=${MODE} url-len=${url.length}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
const tB = Date.now();
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log(`WM_main in ${Date.now() - tB} ms`);

log(`settling ${SETTLE_MS} ms (kick + draws)...`);
await page.waitForTimeout(SETTLE_MS);

// Dedup the draw+dsa lines: keep the first pairing per distinct shader.
const seenDraw = new Set();
const distinct = [];
for (let i = 0; i < r33.length; i++) {
  const l = r33[i];
  const m = l.match(/draw shader=(\S+)/);
  if (m) {
    if (!seenDraw.has(m[1])) {
      seenDraw.add(m[1]);
      distinct.push(l);
      // the very next dsa line (if present) belongs to this draw
      if (r33[i + 1] && r33[i + 1].includes('dsa ')) distinct.push(r33[i + 1]);
    }
  }
}

writeFileSync(`${OUTDIR}/r33-${LABEL}.all.log`, all.join('\n') + '\n');
writeFileSync(`${OUTDIR}/r33-${LABEL}.r33.log`, r33.join('\n') + '\n');
writeFileSync(`${OUTDIR}/r33-${LABEL}.summary.json`,
  JSON.stringify({ mode: MODE, distinctDraws: distinct, gpuErrorCount: gpuErrors.length,
                   gpuErrors: gpuErrors.slice(0, 40), r33LineCount: r33.length }, null, 2));

console.log(`\n==== DISTINCT draw+dsa pairs (${distinct.length} lines, ${seenDraw.size} shaders) ====`);
distinct.forEach((l) => console.log('  ' + l));
console.log(`\n==== GPU errors/lost: ${gpuErrors.length} ====`);
gpuErrors.slice(0, 20).forEach((e) => console.log('  ! ' + e.slice(0, 240)));
console.log(`\n(total [bw-r33] lines: ${r33.length})`);

await ctx.close();
await browser.close();
log('done');
