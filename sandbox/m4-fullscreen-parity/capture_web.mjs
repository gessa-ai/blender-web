// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M4-fullscreen-parity - WEB-SIDE full-window capture rig.
//
// Boots the WINDOWED blender_browser wasm build in headed bundled Chromium via
// Playwright, in the shell's ?gate=WxH exact-size mode (DPR forced to 1), drives
// Blender's own workspace render (splash suppressed) with a VIEW_3D redraw kick
// timer, settles, and captures the canvas at EXACTLY WxH - the wasm-side analogue
// of the native bpy.ops.screen.screenshot golden.
//
// Recipe (notes/gpu-r23..r27): headed Playwright + bundled Chromium, fresh profile
// per launch (empty OPFS), ?gate=WxH, and a ?pyexpr= that:
//   (1) sets preferences.view.show_splash = False  -> the WORKSPACE renders (the
//       full-window gate state), no popup to dismiss;
//   (2) registers a bpy.app.timer forcing VIEW_3D region.tag_redraw() every 1 s so
//       the engine keeps drawing while it settles (the r25/r26 kick timer).
// Capture = CDP page.screenshot CLIPPED to the #canvas bounding box at
// deviceScaleFactor:1 => exact WxH device pixels (the proven r25 gate method), the
// truest analogue of the native window framebuffer read. toDataURL bitmap size is
// also decoded as an independent size receipt.
//
// Serve first (PORT 8129 is this lane's):
//   BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed/bin \
//     bash scripts/serve-web.sh 8129
// Then:
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/m4-fullscreen-parity/capture_web.mjs [WxH] [port] [settleMs]
//
// The binary may be rebuilt mid-session by another lane; if a boot aborts, retry
// in ~5 min (GOAL / task note).

import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const SIZE = (process.argv[2] || '1600x900').trim();
const PORT = parseInt(process.argv[3] || '8129', 10);
const SETTLE_MS = parseInt(process.argv[4] || '60000', 10);
const m = /^(\d+)x(\d+)$/.exec(SIZE);
if (!m) { console.error(`bad size "${SIZE}" - want WxH`); process.exit(2); }
const W = parseInt(m[1], 10), H = parseInt(m[2], 10);

const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/m4-fullscreen-parity/artifacts';
const OUT = `${OUTDIR}/web_${W}x${H}.png`;
const BOOT_MS = 240000; // 926 MB wasm + 133 MB data over localhost - be generous.

// ?pyexpr= : suppress splash (workspace renders) + VIEW_3D redraw kick timer.
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
// deviceScaleFactor:1 so a CDP clip in CSS px == device px == exact WxH.
// Viewport strictly larger than the canvas so gate's place-items:center leaves the
// full canvas on-screen (black margin trimmed by the clip).
const ctx = await browser.newContext({
  viewport: { width: W + 100, height: H + 100 },
  deviceScaleFactor: 1,
});
const page = await ctx.newPage();

const present = { seen: false, count: 0 };
const consoleErrors = [];
page.on('console', (msgObj) => {
  const t = msgObj.text();
  if (t.includes('presentBackbuffer')) { present.seen = true; present.count++; }
  if (msgObj.type() === 'error' || t.includes('GPU-ERROR') || t.includes('ValidationError')) {
    consoleErrors.push(t);
  }
});

log(`booting ${url.slice(0, 90)}... (gate ${W}x${H}, settle ${SETTLE_MS} ms)`);
await page.goto(url, { waitUntil: 'domcontentloaded' });

// (d) DOM-visible "main loop (WM_main)" marker.
const tBoot0 = Date.now();
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
const bootMs = Date.now() - tBoot0;
log(`WM_main reached in ${bootMs} ms`);

// Contract checks: gate backing is exactly WxH and window.__bwModule is exposed.
const gate = await page.evaluate(() => {
  const c = document.getElementById('canvas');
  return {
    bw: c.width, bh: c.height,
    cssW: Math.round(c.getBoundingClientRect().width),
    cssH: Math.round(c.getBoundingClientRect().height),
    dpr: window.devicePixelRatio,
    hasMod: typeof window.__bwModule === 'object' && window.__bwModule !== null,
    gateClass: document.body.classList.contains('bw-gate'),
  };
});
log(`gate: backing ${gate.bw}x${gate.bh} css ${gate.cssW}x${gate.cssH} dpr ${gate.dpr} __bwModule ${gate.hasMod}`);
if (gate.bw !== W || gate.bh !== H) {
  console.error(`FATAL: gate backing ${gate.bw}x${gate.bh} != requested ${W}x${H}`);
  await browser.close(); process.exit(1);
}

log(`settling ${SETTLE_MS} ms (engine kick timer redrawing VIEW_3D)...`);
await page.waitForTimeout(SETTLE_MS);

// Independent size receipt from the actual canvas backing store (toDataURL reads
// the WebGPU front buffer - the same bytes the native screenshot operator reads).
const png = await page.evaluate(() => {
  const c = document.getElementById('canvas');
  const data = c.toDataURL('image/png');
  const b = atob(data.split(',')[1]);
  const dv = new DataView(Uint8Array.from(b, (ch) => ch.charCodeAt(0)).buffer);
  return { w: dv.getUint32(16), h: dv.getUint32(20) }; // IHDR at offset 16
});
log(`toDataURL bitmap ${png.w}x${png.h}  (presentBackbuffer x${present.count}, seen=${present.seen})`);

// PRIMARY capture: CDP screenshot clipped to the canvas bbox (exact WxH at DSF 1).
const rect = await page.evaluate(() => {
  const r = document.getElementById('canvas').getBoundingClientRect();
  return { x: r.x, y: r.y, width: r.width, height: r.height };
});
await page.screenshot({
  path: OUT,
  clip: { x: Math.round(rect.x), y: Math.round(rect.y), width: W, height: H },
});
log(`captured -> ${OUT}`);

if (consoleErrors.length) {
  log(`console errors observed (${consoleErrors.length}); first 5:`);
  consoleErrors.slice(0, 5).forEach((e) => console.log('   ! ' + e.slice(0, 160)));
} else {
  log('no console errors / GPU validation errors observed during boot+settle');
}

await ctx.close();
await browser.close();
log('done');
