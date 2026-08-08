// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// verify_boot.mjs - LOCAL boot verification of the assembled M8 deploy bundle.
//
// Proves the whole deploy stack end to end: the COOP/COEP static server
// (serve_bundle.py) -> index.html -> boot-windowed.js -> /bin/blender_browser.js
// -> wasm + data + pthreads + the baked-in WebGPU preinit worker -> WM_main -> real
// composited pixels. Uses the shell's proven ?gate=WxH exact-size capture path
// (DPR forced to 1) with splash suppressed and a VIEW_3D redraw kick, so the
// capture is deterministic. Additionally asserts crossOriginIsolated===true (the
// COOP/COEP contract) and that GHOST actually presented a frame
// (presentBackbuffer), not merely that the WM_main DOM marker appeared.
//
// Serve first (this lane's port 8130):
//   python3 sandbox/m8-deploy/serve_bundle.py 8130 sandbox/m8-deploy/bundle
// Then (Playwright lives in the game-platform node_modules):
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/m8-deploy/verify_boot.mjs [WxH] [port] [settleMs]
//
// The gate binary is a moving target in this shared checkout; if a boot aborts
// mid-rebuild, retry in a few minutes.

import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const SIZE = (process.argv[2] || '1280x720').trim();
const PORT = parseInt(process.argv[3] || '8130', 10);
const SETTLE_MS = parseInt(process.argv[4] || '20000', 10);
const m = /^(\d+)x(\d+)$/.exec(SIZE);
if (!m) { console.error(`bad size "${SIZE}" - want WxH`); process.exit(2); }
const W = parseInt(m[1], 10), H = parseInt(m[2], 10);

const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/m8-deploy/artifacts';
const OUT = `${OUTDIR}/bundle_boot_${W}x${H}.png`;
const BOOT_MS = 180000; // 150 MB+ wasm + 81 MB data over localhost - be generous.

const fs = require('fs');
fs.mkdirSync(OUTDIR, { recursive: true });

// Suppress splash (so the workspace renders) + keep drawing while it settles.
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

const url = `${BASE}/index.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PYEXPR)}`;

function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

let failed = false;
function fail(msg) { failed = true; console.error(`VERDICT-FAIL: ${msg}`); }

const browser = await chromium.launch({ headless: false });
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
page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + (e && e.message ? e.message : e)));

log(`booting bundle ${url.slice(0, 96)}... (gate ${W}x${H}, boot<=${BOOT_MS}ms, settle ${SETTLE_MS}ms)`);
await page.goto(url, { waitUntil: 'domcontentloaded' });

// The COOP/COEP contract: the served headers must make the page isolated, or the
// -pthread module cannot allocate a SharedArrayBuffer and aborts.
const iso = await page.evaluate(() => ({
  crossOriginIsolated: self.crossOriginIsolated === true,
  sab: typeof SharedArrayBuffer !== 'undefined',
}));
log(`crossOriginIsolated=${iso.crossOriginIsolated}  SharedArrayBuffer=${iso.sab}`);
if (!iso.crossOriginIsolated) fail('page is NOT crossOriginIsolated - COOP/COEP headers not effective');
if (!iso.sab) fail('SharedArrayBuffer unavailable - pthreads cannot run');

// (d) DOM-visible "main loop (WM_main)" marker.
const tBoot0 = Date.now();
try {
  await page.waitForFunction(() => {
    const s = document.querySelector('#state');
    return s && s.textContent.includes('main loop (WM_main)');
  }, null, { timeout: BOOT_MS }); // options is the 3rd arg; 2nd is the (unused) pageFunction arg
} catch (e) {
  fail(`WM_main not reached within ${BOOT_MS}ms (${e.message})`);
}
const bootMs = Date.now() - tBoot0;
if (!failed) log(`WM_main reached in ${bootMs} ms`);

// Contract checks: gate backing exactly WxH and window.__bwModule exposed.
const gate = await page.evaluate(() => {
  const c = document.getElementById('canvas');
  return {
    bw: c.width, bh: c.height,
    dpr: window.devicePixelRatio,
    hasMod: typeof window.__bwModule === 'object' && window.__bwModule !== null,
    gateClass: document.body.classList.contains('bw-gate'),
  };
});
log(`gate: backing ${gate.bw}x${gate.bh} dpr ${gate.dpr} __bwModule=${gate.hasMod} gateClass=${gate.gateClass}`);
if (gate.bw !== W || gate.bh !== H) fail(`gate backing ${gate.bw}x${gate.bh} != requested ${W}x${H}`);
if (!gate.hasMod) fail('window.__bwModule not exposed');

log(`settling ${SETTLE_MS} ms (VIEW_3D kick timer redrawing)...`);
await page.waitForTimeout(SETTLE_MS);

// Independent size receipt from the actual canvas backing store.
let png = { w: 0, h: 0 };
try {
  png = await page.evaluate(() => {
    const c = document.getElementById('canvas');
    const data = c.toDataURL('image/png');
    const b = atob(data.split(',')[1]);
    const dv = new DataView(Uint8Array.from(b, (ch) => ch.charCodeAt(0)).buffer);
    return { w: dv.getUint32(16), h: dv.getUint32(20) };
  });
} catch (e) { log('toDataURL size probe failed: ' + e.message); }
log(`toDataURL bitmap ${png.w}x${png.h}  (presentBackbuffer x${present.count}, seen=${present.seen})`);
if (!present.seen) fail('no presentBackbuffer seen - GHOST never composited a real frame');

// Capture: CDP screenshot clipped to the canvas bbox (exact WxH at DSF 1).
try {
  const rect = await page.evaluate(() => {
    const r = document.getElementById('canvas').getBoundingClientRect();
    return { x: r.x, y: r.y };
  });
  await page.screenshot({
    path: OUT,
    clip: { x: Math.round(rect.x), y: Math.round(rect.y), width: W, height: H },
  });
  log(`captured -> ${OUT}`);
} catch (e) { fail('screenshot failed: ' + e.message); }

if (consoleErrors.length) {
  log(`console errors observed (${consoleErrors.length}); first 5:`);
  consoleErrors.slice(0, 5).forEach((e) => console.log('   ! ' + e.slice(0, 160)));
} else {
  log('no console errors / GPU validation errors during boot+settle');
}

await ctx.close();
await browser.close();

if (failed) {
  log('VERDICT: FAIL');
  process.exit(1);
} else {
  log('VERDICT: PASS - bundle served COOP/COEP-isolated, booted to WM_main, presented real pixels, captured');
  process.exit(0);
}
