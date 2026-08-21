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
// Then, using the pinned repository-local Node and Playwright install:
//   BW_NODE_MODULES=$PWD/.m4-node/node_modules \
//     tools/emsdk/node/22.16.0_64bit/bin/node \
//     sandbox/m8-deploy/verify_boot.mjs [WxH] [port] [settleMs]
// Browser-free portability check:
//   tools/emsdk/node/22.16.0_64bit/bin/node \
//     sandbox/m8-deploy/verify_boot.mjs --selfcheck
//
// The gate binary is a moving target in this shared checkout; if a boot aborts
// mid-rebuild, retry in a few minutes.

import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { delimiter, dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

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
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) ||
      width < 1 || height < 1 || width > 16384 || height > 16384) {
    throw new Error(`bad size "${raw}" - dimensions must be integers in 1..16384`);
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
  assertSelfcheck(existsSync(join(ROOT, 'GOAL.md')) &&
    HERE === join(ROOT, 'sandbox/m8-deploy'),
  'repository root is not derived from the driver');
  assertSelfcheck(MODULE_ROOTS.every(isAbsolute) &&
    new Set(MODULE_ROOTS).size === MODULE_ROOTS.length,
  'module roots are not absolute and unique');
  assertSelfcheck(LOCAL_MODULE_ROOTS.every((root) =>
    MODULE_ROOTS.includes(root) && isRepositoryDescendant(root)),
  'repository-local module fallback is incomplete or escaped');
  assertSelfcheck(OUTDIR === join(ROOT, 'sandbox/m8-deploy/artifacts') &&
    isRepositoryDescendant(OUTDIR),
  'capture output is not confined to the repository artifact directory');
  assertSelfcheck(JSON.stringify(parseSize('1280x720')) ===
    JSON.stringify({ width: 1280, height: 720 }),
  'size parser drift');
  for (const value of ['1280X720', '0x720', '1280x0', '1280x720junk', '16385x720']) {
    let rejected = false;
    try { parseSize(value); }
    catch (_) { rejected = true; }
    assertSelfcheck(rejected, `unsafe size was accepted: ${value}`);
  }
  assertSelfcheck(parseInteger('8130', 'port', 1, 65535) === 8130,
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
  assertSelfcheck(synthetic.chromium === chromiumToken && synthetic.root === '/fixture',
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
    `M8_DEPLOY_BOOT_SELFCHECK_PASS root=derived output=sandbox/m8-deploy/artifacts ` +
    `node=${NODE_VERSION} playwright=${PLAYWRIGHT_VERSION} ` +
    `live_playwright=${livePlaywrightRoot || 'not-requested'} ` +
    `browser_args=${JSON.stringify(BROWSER_ARGS)} browser_launches=0`);
}

if (process.argv[2] === '--selfcheck') {
  if (process.argv.length !== 3) throw new Error('--selfcheck accepts no other arguments');
  runSelfcheck();
  process.exit(0);
}

if (process.version !== NODE_VERSION) {
  throw new Error(`node version ${process.version} != ${NODE_VERSION}`);
}
if (!['darwin', 'linux'].includes(process.platform)) {
  throw new Error(`unsupported browser platform ${process.platform}`);
}
const { chromium, root: playwrightRoot, version: playwrightVersion } = resolvePlaywright();
const SIZE = (process.argv[2] || '1280x720').trim();
const { width: W, height: H } = parseSize(SIZE);
const PORT = parseInteger(process.argv[3] || '8130', 'port', 1, 65535);
const SETTLE_MS = parseInteger(
  process.argv[4] || '20000', 'settle milliseconds', 0, 3600000);

const BASE = `http://127.0.0.1:${PORT}`;
const OUT = join(OUTDIR, `bundle_boot_${W}x${H}.png`);
const BOOT_MS = 180000; // 150 MB+ wasm + 81 MB data over localhost - be generous.

mkdirSync(OUTDIR, { recursive: true });

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

log(`runtime node=${process.version} playwright=${playwrightVersion} modules=${playwrightRoot}`);
const browser = await chromium.launch({ headless: false, args: BROWSER_ARGS });
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
