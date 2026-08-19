// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r28b — depth-path diagnostic capture. Boots the windowed opt build, drives a
// VIEW_3D redraw kick, and collects every [bw-r28b] stderr line the backend emits
// (begin_load_pass tuples, submit_clear tuples, SAMPLED-DEPTH binds) so we can
// compare the gbuffer-prepass depth-attachment handle against the composite's
// sampled-depth handle. Screenshots the viewport once settled.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r28b/diag_depth.mjs <label> [port] [settleMs]

import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'diag').trim();
const PORT = parseInt(process.argv[3] || '8124', 10);
const SETTLE_MS = parseInt(process.argv[4] || '20000', 10);
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/platform_web/shell/evidence';
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
  '    return 1.0',
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

const diag = [];
const gpuErrors = [];
const shaderMsgs = [];
const SHADER_RE = /workbench|prepass|compil|Tint|WGSL|shader.*(fail|error)|failed to (create|compile)/i;
page.on('console', (m) => {
  const t = m.text();
  if (t.includes('bw-r28b')) diag.push(t);
  if (t.includes('GPU-ERROR') || t.includes('ValidationError')) gpuErrors.push(t);
  if (SHADER_RE.test(t)) shaderMsgs.push(`[${m.type()}] ${t}`);
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
await page.screenshot({ path: `${OUTDIR}/m4-r28b-${LABEL}-shot.png`, clip });

console.log('\n==== [bw-r28b] diagnostic lines (deduped by backend) ====');
for (const d of diag) console.log(d);
console.log(`\n==== GPU errors: ${gpuErrors.length} ====`);
gpuErrors.slice(0, 5).forEach((e) => console.log('  ! ' + e.slice(0, 200)));

console.log(`\n==== shader/workbench msgs: ${shaderMsgs.length} (first 25) ====`);
const seenS = new Set();
for (const s of shaderMsgs) {
  const k = s.slice(0, 120);
  if (seenS.has(k)) continue;
  seenS.add(k);
  console.log('  # ' + s.slice(0, 220));
  if (seenS.size >= 25) break;
}

await ctx.close();
await browser.close();
log('done');
