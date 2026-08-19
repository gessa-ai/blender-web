// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4 r28b — UI-region interaction regression repro (menus/toolbar/topbar).
//
// Boots the WINDOWED opt build in headed bundled Chromium (gate=1280x720, DPR 1),
// splash off + VIEW_3D kick timer, then drives three interactions and captures the
// canvas after each:
//   (0) full-window settle    -> grid/geometry regression check (grid MUST render)
//   (1) click File menu (~40,12 canvas-local) -> dropdown SOLID bg + File/Edit text
//   (2) right-click mid-viewport               -> context menu SOLID bg
//   (3) hover the toolbar (left rail)          -> toolbar SOLID bg
//
// Usage (serve on 8124 first with BLENDER_WEB_BIN=build-wasm-windowed-opt/bin):
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/gpu-r28b/repro_ui.mjs <label> [port] [settleMs]
// Captures -> platform_web/shell/evidence/m4-r28b-<label>-*.png

import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'baseline').trim();
const PORT = parseInt(process.argv[3] || '8124', 10);
const SETTLE_MS = parseInt(process.argv[4] || '45000', 10);
const IWAIT = 3500; // per-interaction wait (presents are rare on this build)
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

const gpuErrors = [];
page.on('console', (m) => {
  const t = m.text();
  if (m.type() === 'error' || t.includes('GPU-ERROR') || t.includes('ValidationError')) {
    gpuErrors.push(t);
  }
});

log(`booting label=${LABEL} ${url.slice(0, 80)}…`);
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
log(`canvas origin (${ox},${oy}) size ${rect.w}x${rect.h}`);
const shot = async (name) => {
  const p = `${OUTDIR}/m4-r28b-${LABEL}-${name}.png`;
  await page.screenshot({ path: p, clip });
  log(`  captured ${name} -> ${p}`);
};

log(`settling ${SETTLE_MS} ms…`);
await page.waitForTimeout(SETTLE_MS);
await shot('00-fullwindow');

// (1) File menu: canvas-local (40,12).
log('interaction 1: click File menu (~40,12)');
await page.mouse.move(ox + 40, oy + 12);
await page.waitForTimeout(300);
await page.mouse.click(ox + 40, oy + 12);
await page.waitForTimeout(IWAIT);
await shot('01-file-menu');
// dismiss
await page.keyboard.press('Escape');
await page.waitForTimeout(1200);

// (2) right-click mid-viewport.
log('interaction 2: right-click mid-viewport');
await page.mouse.move(ox + Math.round(W / 2), oy + Math.round(H / 2));
await page.waitForTimeout(300);
await page.mouse.click(ox + Math.round(W / 2), oy + Math.round(H / 2), { button: 'right' });
await page.waitForTimeout(IWAIT);
await shot('02-context-menu');
await page.keyboard.press('Escape');
await page.waitForTimeout(1200);

// (3) hover the toolbar (left rail ~ x=14, y=200 canvas-local).
log('interaction 3: hover toolbar left rail');
await page.mouse.move(ox + 14, oy + 200);
await page.waitForTimeout(IWAIT);
await shot('03-toolbar-hover');

log(gpuErrors.length ? `GPU errors: ${gpuErrors.length} (first 3):` : 'no GPU/validation errors');
gpuErrors.slice(0, 3).forEach((e) => console.log('   ! ' + e.slice(0, 150)));

await ctx.close();
await browser.close();
log('done');
