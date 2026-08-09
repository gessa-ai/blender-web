// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Capture the WebGPU workspace with the native 3D cursor either at the world origin or
// translated along +X. The pair proves that the repaired overlay follows scene cursor data.
//
// Usage: node capture_cursor.mjs <origin|moved|hidden> [port] [settleMs] [tag]

import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const MODE = (process.argv[2] || 'origin').trim();
const PORT = parseInt(process.argv[3] || '8142', 10);
const SETTLE_MS = parseInt(process.argv[4] || '30000', 10);
const TAG = (process.argv[5] || '').trim();
if (!['origin', 'moved', 'hidden'].includes(MODE)) {
  console.error(`bad mode "${MODE}"`);
  process.exit(2);
}

const W = 1280;
const H = 720;
const BOOT_MS = 300000;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-m4-cursor-upload';
const CURSOR = MODE === 'moved' ? '(3.0, 0.0, 0.0)' : '(0.0, 0.0, 0.0)';
const PY = [
  'import bpy',
  'bpy.context.preferences.view.show_splash = False',
  `bpy.context.scene.cursor.location = ${CURSOR}`,
  ...(MODE === 'hidden' ? [
    'for _area in bpy.context.screen.areas:',
    '    if _area.type == "VIEW_3D": _area.spaces.active.overlay.show_cursor = False',
  ] : []),
  'def _bw_cursor_kick():',
  '    try:',
  '        for win in bpy.context.window_manager.windows:',
  '            if not win.screen: continue',
  '            for area in win.screen.areas:',
  '                for region in area.regions:',
  '                    region.tag_redraw()',
  '    except Exception as e:',
  '        print("[bw-cursor-kick] " + repr(e))',
  '    return 1.0',
  'bpy.app.timers.register(_bw_cursor_kick, first_interval=1.0)',
].join('\n');

const url = `http://localhost:${PORT}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PY)}`;
const browser = await chromium.launch({ headless: false });
const context = await browser.newContext({
  viewport: { width: W + 120, height: H + 120 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();
const gpuErrors = [];
const pageErrors = [];
let presents = 0;

page.on('console', (message) => {
  const line = message.text();
  if (line.includes('presentBackbuffer')) presents++;
  if (line.includes('[BW-CURSOR-DIAG]')) console.log(line);
  if (/GPU-ERROR|ValidationError|uncaptured WebGPU|WebGPU uncaptured/i.test(line)) {
    gpuErrors.push(line);
  }
});
page.on('pageerror', (error) => pageErrors.push(String(error)));

console.log(`mode=${MODE} cursor=${CURSOR} url=${url.slice(0, 96)}...`);
const bootStart = Date.now();
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
await page.waitForFunction(() => {
  const state = document.querySelector('#state');
  return state && state.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
console.log(`WM_main_ms=${Date.now() - bootStart}`);

const canvas = await page.evaluate(() => {
  const element = document.getElementById('canvas');
  const rect = element.getBoundingClientRect();
  return {
    bufferWidth: element.width,
    bufferHeight: element.height,
    x: rect.x,
    y: rect.y,
    width: rect.width,
    height: rect.height,
  };
});
if (canvas.bufferWidth !== W || canvas.bufferHeight !== H) {
  throw new Error(`canvas gate ${canvas.bufferWidth}x${canvas.bufferHeight}, expected ${W}x${H}`);
}

await page.waitForTimeout(SETTLE_MS);
await page.mouse.move(Math.round(canvas.x + 12), Math.round(canvas.y + canvas.height - 12));
await page.waitForTimeout(400);
await page.mouse.move(Math.round(canvas.x + 16), Math.round(canvas.y + canvas.height - 16));
await page.waitForTimeout(1000);

const suffix = TAG ? `_${TAG}` : '';
const output = `${OUTDIR}/cursor_${MODE}${suffix}_${W}x${H}.png`;
await page.screenshot({
  path: output,
  clip: {
    x: Math.round(canvas.x),
    y: Math.round(canvas.y),
    width: W,
    height: H,
  },
});

console.log(`capture=${output}`);
console.log(`presents=${presents}`);
console.log(`gpu_errors=${gpuErrors.length}`);
console.log(`page_errors=${pageErrors.length}`);
for (const line of gpuErrors) console.log(`GPU_ERROR: ${line}`);
for (const line of pageErrors) console.log(`PAGE_ERROR: ${line}`);

await context.close();
await browser.close();
if (gpuErrors.length || pageErrors.length) process.exit(1);
