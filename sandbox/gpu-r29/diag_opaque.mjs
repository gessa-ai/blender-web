// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r29 — opaque-group indirect isolation. Boots the windowed opt build, kicks a
// VIEW_3D redraw, and captures every [bw-r29-*] stderr line (CPU DrawGroup/Prototype
// fingerprints + translated WGSL of draw_command_generate / draw_visibility / the
// workbench opaque prepass vertex) to a file for offline diffing. Also probes the
// center viewport pixel to confirm whether the solid cube composites.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r29/diag_opaque.mjs <label> [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'diag').trim();
const PORT = parseInt(process.argv[3] || '8124', 10);
const SETTLE_MS = parseInt(process.argv[4] || '60000', 10);
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r29';
const EVID = '/Users/paws/blender-web/platform_web/shell/evidence';
const BOOT_MS = 240000;

const PYEXPR = [
  'import bpy',
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
  '    except Exception as e:',
  '        print("[bw-kick] " + repr(e))',
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
const r29 = [];
const gpuErrors = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.includes('bw-r29')) r29.push(t);
  if (t.includes('GPU-ERROR') || t.includes('ValidationError')) gpuErrors.push(t);
});

log(`booting label=${LABEL}`);
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
const ox = Math.round(rect.x), oy = Math.round(rect.y);
const clip = { x: ox, y: oy, width: W, height: H };

log(`settling ${SETTLE_MS} ms…`);
await page.waitForTimeout(SETTLE_MS);

// Center-pixel probe via a 2D canvas drawImage of the WebGPU canvas.
let probe = null;
try {
  probe = await page.evaluate(() => {
    const cv = document.getElementById('canvas');
    const oc = document.createElement('canvas');
    oc.width = cv.width; oc.height = cv.height;
    const g = oc.getContext('2d');
    g.drawImage(cv, 0, 0);
    const cx = (cv.width / 2) | 0, cy = (cv.height / 2) | 0;
    const pts = {};
    for (const [nm, dx, dy] of [['center', 0, 0], ['c_l', -80, 0], ['c_r', 80, 0],
                                ['c_u', 0, -80], ['c_d', 0, 60]]) {
      const d = g.getImageData(cx + dx, cy + dy, 1, 1).data;
      pts[nm] = [d[0], d[1], d[2], d[3]];
    }
    return { w: cv.width, h: cv.height, pts };
  });
} catch (e) { probe = { err: String(e) }; }

await page.screenshot({ path: `${EVID}/m4-r29-${LABEL}-shot.png`, clip });

const outLines = r29.join('\n');
writeFileSync(`${OUTDIR}/r29-${LABEL}.log`, outLines + '\n');
writeFileSync(`${OUTDIR}/r29-${LABEL}.all.log`, all.join('\n') + '\n');

console.log(`\n==== [bw-r29] lines: ${r29.length} (written to r29-${LABEL}.log) ====`);
// Print only the compact CPU fingerprints inline (WGSL goes to file only).
for (const l of r29) if (l.includes('bw-r29-cpu')) console.log(l);
console.log(`\n==== center-pixel probe ====`);
console.log(JSON.stringify(probe));
console.log(`\n==== GPU errors: ${gpuErrors.length} ====`);
gpuErrors.slice(0, 6).forEach((e) => console.log('  ! ' + e.slice(0, 200)));

await ctx.close();
await browser.close();
log('done');
