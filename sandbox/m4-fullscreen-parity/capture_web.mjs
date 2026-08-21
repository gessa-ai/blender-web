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
//   BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin bash scripts/serve-web.sh 8129
// Then use the pinned repository-local Node and Playwright install:
//   BW_NODE_MODULES=$PWD/.m4-node/node_modules \
//     tools/emsdk/node/22.16.0_64bit/bin/node \
//     sandbox/m4-fullscreen-parity/capture_web.mjs [WxH] [port] [settleMs]
// Browser-free portability check:
//   BW_NODE_MODULES=$PWD/.m4-node/node_modules \
//     tools/emsdk/node/22.16.0_64bit/bin/node \
//     sandbox/m4-fullscreen-parity/capture_web.mjs --selfcheck
//
// The binary may be rebuilt mid-session by another lane; if a boot aborts, retry
// in ~5 min (GOAL / task note).

import { existsSync, readFileSync } from 'fs';
import { createRequire } from 'module';
import { delimiter, dirname, isAbsolute, join, relative, resolve } from 'path';
import { fileURLToPath } from 'url';

const DRIVER_PATH = fileURLToPath(import.meta.url);
const HERE = dirname(DRIVER_PATH);
const ROOT = resolve(HERE, '../..');
const OUTDIR = join(HERE, 'artifacts');
const LOCAL_MODULE_ROOTS = Object.freeze([
  join(ROOT, '.m4-node/node_modules'),
  join(ROOT, 'node_modules'),
]);
const MODULE_ROOTS = Object.freeze([...new Set([
  process.env.BW_NODE_MODULES,
  process.env.NODE_PATH,
  ...LOCAL_MODULE_ROOTS,
]
  .filter(Boolean)
  .flatMap((entry) => entry.split(delimiter))
  .filter(Boolean)
  .map((entry) => resolve(entry)))]);
const NODE_VERSION = 'v22.16.0';
const PLAYWRIGHT_VERSION = '1.61.1';
const BROWSER_ARGS = Object.freeze([
  '--enable-unsafe-webgpu',
  ...(process.platform === 'darwin' ? ['--use-angle=metal'] : []),
]);

function resolvePlaywright(
  roots = MODULE_ROOTS,
  load = (root) => {
    const require = createRequire(join(root, 'package.json'));
    return {
      chromium: require('playwright').chromium,
      version: require('playwright/package.json').version,
    };
  },
) {
  const errors = [];
  for (const root of roots) {
    try {
      const loaded = load(root);
      if (!loaded?.chromium) throw new Error('playwright export lacks chromium');
      if (loaded.version !== PLAYWRIGHT_VERSION) {
        throw new Error(
          `playwright version ${loaded.version || 'unknown'} != ${PLAYWRIGHT_VERSION}`);
      }
      return { chromium: loaded.chromium, root, version: loaded.version };
    }
    catch (error) {
      errors.push(`${root}: ${error.message}`);
    }
  }
  throw new Error(`cannot resolve Playwright; set BW_NODE_MODULES\n${errors.join('\n')}`);
}

function isRepositoryDescendant(path) {
  const rel = relative(ROOT, resolve(path));
  return rel !== '' && !isAbsolute(rel) && rel.split(/[\\/]/)[0] !== '..';
}

function parseSize(raw) {
  const match = /^(\d+)x(\d+)$/.exec(raw.trim());
  if (!match) throw new Error(`bad size "${raw}" - want WxH`);
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width < 1 || height < 1) {
    throw new Error(`bad size "${raw}" - dimensions must be positive safe integers`);
  }
  return { width, height };
}

function parseInteger(raw, label, minimum, maximum) {
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new Error(`bad ${label} "${raw}" - want integer ${minimum}..${maximum}`);
  }
  return value;
}

function assertSelfcheck(condition, message) {
  if (!condition) throw new Error(`selfcheck: ${message}`);
}

function runSelfcheck() {
  assertSelfcheck(process.version === NODE_VERSION,
    `node version ${process.version} != ${NODE_VERSION}`);
  assertSelfcheck(existsSync(join(ROOT, 'GOAL.md')) && HERE === dirname(DRIVER_PATH),
    'repository root is not derived from the driver');
  assertSelfcheck(MODULE_ROOTS.every(isAbsolute) &&
    new Set(MODULE_ROOTS).size === MODULE_ROOTS.length,
  'module roots are not absolute and unique');
  assertSelfcheck(LOCAL_MODULE_ROOTS.every((root) =>
    MODULE_ROOTS.includes(root) && isRepositoryDescendant(root)),
  'repository-local module fallback is incomplete or escaped');
  assertSelfcheck(OUTDIR === join(ROOT, 'sandbox/m4-fullscreen-parity/artifacts') &&
    isRepositoryDescendant(OUTDIR),
  'capture output is not confined to the repository artifact directory');
  assertSelfcheck(JSON.stringify(parseSize('1600x900')) ===
    JSON.stringify({ width: 1600, height: 900 }),
  'size parser drift');
  for (const value of ['1600X900', '0x900', '1600x0', '1600x900junk']) {
    let rejected = false;
    try { parseSize(value); }
    catch (_) { rejected = true; }
    assertSelfcheck(rejected, `unsafe size was accepted: ${value}`);
  }
  assertSelfcheck(parseInteger('8129', 'port', 1, 65535) === 8129,
    'port parser drift');
  const expectedBrowserArgs = process.platform === 'darwin' ?
    ['--enable-unsafe-webgpu', '--use-angle=metal'] : ['--enable-unsafe-webgpu'];
  assertSelfcheck(JSON.stringify(BROWSER_ARGS) === JSON.stringify(expectedBrowserArgs),
    'platform browser arguments drift');
  const chromiumToken = {};
  const synthetic = resolvePlaywright(['/missing', '/fixture'], (root) => {
    if (root === '/missing') throw new Error('fixture miss');
    return { chromium: chromiumToken, version: PLAYWRIGHT_VERSION };
  });
  assertSelfcheck(synthetic.chromium === chromiumToken && synthetic.root === '/fixture' &&
    synthetic.version === PLAYWRIGHT_VERSION,
  'Playwright fallback resolution drift');
  let versionRejected = false;
  try {
    resolvePlaywright(['/fixture'], () => ({ chromium: chromiumToken, version: '0.0.0' }));
  }
  catch (error) {
    versionRejected = String(error).includes(`!= ${PLAYWRIGHT_VERSION}`);
  }
  assertSelfcheck(versionRejected, 'Playwright version drift was accepted');
  let livePlaywrightRoot = null;
  if (process.env.BW_NODE_MODULES) {
    const live = resolvePlaywright();
    assertSelfcheck(live.chromium && MODULE_ROOTS.includes(live.root) &&
      live.version === PLAYWRIGHT_VERSION,
    'live Playwright resolution drift');
    livePlaywrightRoot = live.root;
  }
  const source = readFileSync(DRIVER_PATH, 'utf8');
  assertSelfcheck(!source.includes('/Users/' + 'paws') &&
    !source.includes('/opt/' + 'homebrew'),
  'retired macOS path remains in the active producer');
  console.log(
    `SELF_CHECK_PASS root=${ROOT} output=sandbox/m4-fullscreen-parity/artifacts ` +
    `node=${NODE_VERSION} playwright=${PLAYWRIGHT_VERSION} ` +
    `live_playwright=${livePlaywrightRoot || 'not-requested'} ` +
    `browser_args=${JSON.stringify(BROWSER_ARGS)} browser_launches=0`);
}

if (process.argv[2] === '--selfcheck') {
  runSelfcheck();
  process.exit(0);
}

if (process.version !== NODE_VERSION) {
  throw new Error(`node version ${process.version} != ${NODE_VERSION}`);
}
const { chromium, root: playwrightRoot, version: playwrightVersion } = resolvePlaywright();

const SIZE = (process.argv[2] || '1600x900').trim();
const { width: W, height: H } = parseSize(SIZE);
const PORT = parseInteger(process.argv[3] || '8129', 'port', 1, 65535);
const SETTLE_MS = parseInteger(
  process.argv[4] || '60000', 'settle milliseconds', 0, 3600000);

const BASE = `http://127.0.0.1:${PORT}`;
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

log(
  `runtime Node ${process.version}, Playwright ${playwrightVersion} at ${playwrightRoot}, ` +
  `browser args ${JSON.stringify(BROWSER_ARGS)}`);
const browser = await chromium.launch({ headless: false, args: BROWSER_ARGS });
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
