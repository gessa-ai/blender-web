// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// D-9 M4 gate capture rig.
//
// Boots the final windowed-opt Blender build in headed bundled Chromium at the
// operative 1280x720 gate size and DPR 1. Captures through Playwright's CDP
// screenshot path because the WebGPU surface is a worker-owned OffscreenCanvas.
// Output is restricted to sandbox/m4-d9-gate/evidence.
//
// Usage:
//   npm install --prefix .m4-node --no-save @playwright/test@1.61.1
//   BW_NODE_MODULES=$PWD/.m4-node/node_modules \
//     node sandbox/m4-d9-gate/capture_m4.mjs <splash|workspace> [port] [label]
//   node sandbox/m4-d9-gate/capture_m4.mjs --selfcheck

import { createHash } from 'crypto';
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, writeFileSync } from 'fs';
import { createRequire } from 'module';
import { delimiter, dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const moduleRoots = [process.env.BW_NODE_MODULES, process.env.NODE_PATH, `${ROOT}/node_modules`]
  .filter(Boolean)
  .flatMap((entry) => entry.split(delimiter))
  .filter(Boolean);
let chromium = null;
let playwrightRoot = null;
for (const root of moduleRoots) {
  try {
    chromium = createRequire(`${resolve(root)}/package.json`)('playwright').chromium;
    playwrightRoot = resolve(root);
    break;
  }
  catch {
    // Try the next explicit/local module root.
  }
}
if (chromium === null) {
  throw new Error(`playwright is unavailable; checked module roots: ${moduleRoots.join(', ')}`);
}
const DRIVER_PATH = `${ROOT}/sandbox/m4-d9-gate/capture_m4.mjs`;
const OUTDIR = `${ROOT}/sandbox/m4-d9-gate/evidence`;
const BIN_DIR = process.env.BLENDER_WEB_BIN || `${ROOT}/build-wasm-windowed-opt/bin`;
const DEFERRED_WASM_FILENAME =
  process.env.BW_DEFERRED_WASM_FILENAME || 'blender_browser.deferred.wasm';
if (!/^blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm$/.test(DEFERRED_WASM_FILENAME) ||
    ['blender_browser.wasm', 'blender_browser.wasm.orig'].includes(DEFERRED_WASM_FILENAME)) {
  throw new Error(`unsafe deferred Wasm filename: ${DEFERRED_WASM_FILENAME}`);
}
const BINARY_PATHS = Object.freeze({
  javascript: `${BIN_DIR}/blender_browser.js`,
  wasm: `${BIN_DIR}/blender_browser.wasm`,
  deferred: `${BIN_DIR}/${DEFERRED_WASM_FILENAME}`,
  preload: `${BIN_DIR}/blender_browser.data`,
});
const SHELL_PATHS = Object.freeze({
  index: `${ROOT}/platform_web/shell/index.html`,
  windowed: `${ROOT}/platform_web/shell/windowed.html`,
  diagnostics: `${ROOT}/platform_web/shell/diagnostics-bootstrap.js`,
  boot: `${ROOT}/platform_web/shell/boot-windowed.js`,
  fileBridge: `${ROOT}/platform_web/shell/file-bridge.js`,
  preinit: `${ROOT}/platform_web/shell/wgpu-preinit-worker.js`,
});
const WIDTH = 1280;
const HEIGHT = 720;
const SETTLE_MS = 60000;
const BOOT_MS = 300000;
const HEADLESS = false;
const VALID_MODES = new Set(['splash', 'workspace']);

if (process.argv[2] === '--selfcheck') {
  const checks = [
    OUTDIR === `${ROOT}/sandbox/m4-d9-gate/evidence`,
    WIDTH === 1280,
    HEIGHT === 720,
    SETTLE_MS === 60000,
    HEADLESS === false,
    Object.keys(BINARY_PATHS).join(',') === 'javascript,wasm,deferred,preload',
    Object.keys(SHELL_PATHS).join(',') === 'index,windowed,diagnostics,boot,fileBridge,preinit',
    VALID_MODES.has('splash'),
    VALID_MODES.has('workspace'),
    playwrightRoot !== null,
  ];
  if (checks.every(Boolean)) {
    console.log('SELF_CHECK_PASS output=m4-d9-gate/evidence gate=1280x720 dpr=1 settle_ms=60000 modes=splash,workspace');
    process.exit(0);
  }
  console.error('SELF_CHECK_FAIL');
  process.exit(1);
}

const MODE = (process.argv[2] || '').trim();
if (!VALID_MODES.has(MODE)) {
  console.error('usage: capture_m4.mjs <splash|workspace> [port] [unique-label]');
  process.exit(2);
}

const PORT = Number.parseInt(process.argv[3] || '8141', 10);
if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) {
  console.error(`invalid port: ${process.argv[3] || ''}`);
  process.exit(2);
}

const LABEL = (process.argv[4] || '').trim();
if (!/^[a-z0-9][a-z0-9._-]*$/i.test(LABEL)) {
  console.error('a safe, non-empty unique label is required');
  process.exit(2);
}

const PYTHON_LINES = ['import bpy'];
if (MODE === 'workspace') {
  PYTHON_LINES.push('bpy.context.preferences.view.show_splash = False');
}
PYTHON_LINES.push(
  'def _bw_d9_kick():',
  '    try:',
  '        for win in bpy.context.window_manager.windows:',
  '            scr = win.screen',
  '            if not scr: continue',
  '            for area in scr.areas:',
  '                for region in area.regions:',
  '                    region.tag_redraw()',
  '    except Exception as e:',
  '        import os',
  '        os.write(2, ("BW_D9_KICK_ERROR " + repr(e) + "\\n").encode())',
  '    return 1.0',
  'bpy.app.timers.register(_bw_d9_kick, first_interval=1.0)',
);

const BASE = `http://127.0.0.1:${PORT}`;
const url = `${BASE}/windowed.html?gate=${WIDTH}x${HEIGHT}&pyexpr=${encodeURIComponent(PYTHON_LINES.join('\n'))}`;
const outputStem = `${LABEL}-${MODE}`;
const output = `${OUTDIR}/${outputStem}_${WIDTH}x${HEIGHT}.png`;
const licensePath = `${output}.license`;
const receiptPath = `${OUTDIR}/${outputStem}_${WIDTH}x${HEIGHT}.receipt.json`;
const consoleErrors = [];
const blockingErrors = [];
const marks = [];
let pageCrashed = false;
let presentCount = 0;

function stamp(label, extra = {}) {
  const mark = { label, iso: new Date().toISOString(), ...extra };
  marks.push(mark);
  console.log(`[${mark.iso}] [${MODE}] ${label}`);
}

function recordError(text, kind) {
  const entry = { kind, text: String(text) };
  consoleErrors.push(entry);
  if (/GPU-ERROR|ValidationError|Aborted|table index is out of bounds/i.test(entry.text)) {
    blockingErrors.push(entry);
  }
}

function artifactReceipt(path) {
  const bytes = readFileSync(path);
  return { path, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
}

mkdirSync(OUTDIR, { recursive: true });
for (const path of [output, licensePath, receiptPath]) {
  if (existsSync(path)) {
    console.error(`refusing to overwrite existing evidence: ${path}`);
    process.exit(2);
  }
}
const shippingBinary = Object.fromEntries(
  Object.entries(BINARY_PATHS).map(([name, path]) => [name, artifactReceipt(path)]),
);
const sources = { capture: artifactReceipt(DRIVER_PATH) };
const expectedServedShell = Object.fromEntries(
  Object.entries(SHELL_PATHS).map(([name, path]) => [name, artifactReceipt(path)]),
);
// The receipt is the atomic reservation for this label/mode pair. If a capture
// crashes, the empty receipt intentionally prevents that immutable attempt from
// being silently reused.
closeSync(openSync(receiptPath, 'wx'));
stamp('shipping artifacts bound', {
  javascript: shippingBinary.javascript.sha256,
  wasm: shippingBinary.wasm.sha256,
  deferred: shippingBinary.deferred.sha256,
  preload: shippingBinary.preload.sha256,
});
const browser = await chromium.launch({ headless: HEADLESS });
const context = await browser.newContext({
  viewport: { width: WIDTH + 120, height: HEIGHT + 120 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();

page.on('console', (message) => {
  const text = message.text();
  if (text.includes('presentBackbuffer')) {
    presentCount += 1;
  }
  if (message.type() === 'error' || /GPU-ERROR|ValidationError/i.test(text)) {
    recordError(text, `console:${message.type()}`);
  }
});
page.on('pageerror', (error) => recordError(error.stack || error.message, 'pageerror'));
page.on('crash', () => {
  pageCrashed = true;
  recordError('Playwright page crashed', 'crash');
});

let bootMs = null;
let gate = null;
let rect = null;
let sha256 = null;
let runError = null;
let servedShell = null;

try {
  stamp('boot', { url });
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  servedShell = await page.evaluate(async () => {
    const specs = { index: '/index.html', windowed: '/windowed.html', diagnostics: '/diagnostics-bootstrap.js', boot: '/boot-windowed.js',
      fileBridge: '/file-bridge.js', preinit: '/wgpu-preinit-worker.js' };
    const result = {};
    for (const [name, path] of Object.entries(specs)) {
      const response = await fetch(path, { cache: 'no-store' });
      if (!response.ok) throw new Error(`served shell fetch failed: ${path} status=${response.status}`);
      const bytes = new Uint8Array(await response.arrayBuffer());
      const digest = await crypto.subtle.digest('SHA-256', bytes);
      result[name] = {
        url: new URL(path, location.href).href,
        bytes: bytes.length,
        sha256: Array.from(new Uint8Array(digest),
          (value) => value.toString(16).padStart(2, '0')).join(''),
      };
    }
    return result;
  });
  for (const [name, expected] of Object.entries(expectedServedShell)) {
    const actual = servedShell?.[name];
    if (!actual || actual.bytes !== expected.bytes || actual.sha256 !== expected.sha256) {
      throw new Error(`served shell differs from local ${name}: ${JSON.stringify({ actual, expected })}`);
    }
  }
  stamp('served shell bound', Object.fromEntries(
    Object.entries(servedShell).map(([name, value]) => [name, value.sha256])));
  const bootStart = Date.now();
  await page.waitForFunction(() => {
    const state = document.querySelector('#state');
    return state && state.textContent.includes('main loop (WM_main)');
  }, undefined, { timeout: BOOT_MS });
  bootMs = Date.now() - bootStart;
  stamp('WM_main', { bootMs });

  gate = await page.evaluate(() => {
    const canvas = document.getElementById('canvas');
    const bounds = canvas.getBoundingClientRect();
    return {
      backingWidth: canvas.width,
      backingHeight: canvas.height,
      cssWidth: Math.round(bounds.width),
      cssHeight: Math.round(bounds.height),
      dpr: window.devicePixelRatio,
      gateClass: document.body.classList.contains('bw-gate'),
    };
  });
  const exactGate = gate.backingWidth === WIDTH && gate.backingHeight === HEIGHT
    && gate.cssWidth === WIDTH && gate.cssHeight === HEIGHT
    && gate.dpr === 1 && gate.gateClass;
  if (!exactGate) {
    throw new Error(`gate mismatch: ${JSON.stringify(gate)}`);
  }
  stamp('gate exact', gate);

  stamp('settle begin', { settleMs: SETTLE_MS });
  await page.waitForTimeout(SETTLE_MS);

  rect = await page.evaluate(() => {
    const bounds = document.getElementById('canvas').getBoundingClientRect();
    return { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height };
  });
  await page.mouse.move(Math.round(rect.x + 12), Math.round(rect.y + rect.height - 12));
  await page.waitForTimeout(400);
  await page.mouse.move(Math.round(rect.x + 16), Math.round(rect.y + rect.height - 16));

  await page.screenshot({
    path: output,
    clip: {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: WIDTH,
      height: HEIGHT,
    },
  });
  sha256 = createHash('sha256').update(readFileSync(output)).digest('hex');
  writeFileSync(
    licensePath,
    'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n',
  );
  stamp('capture complete', { output, sha256, presentCount });
} catch (error) {
  runError = error.stack || error.message || String(error);
  recordError(runError, 'run');
  console.error(runError);
} finally {
  const receipt = {
    mode: MODE,
    label: LABEL,
    url,
    output,
    licensePath,
    sha256,
    gate: `${WIDTH}x${HEIGHT}`,
    deviceScaleFactor: 1,
    settleMs: SETTLE_MS,
    bootMs,
    gateReceipt: gate,
    clipReceipt: rect,
    presentCount,
    pageCrashed,
    runError,
    consoleErrors,
    blockingErrors,
    shippingBinary,
    servedShell,
    expectedServedShell,
    sources,
    marks,
  };
  writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`);
  await context.close();
  await browser.close();
}

if (runError || pageCrashed || blockingErrors.length > 0 || !sha256) {
  console.error(`CAPTURE_FAIL receipt=${receiptPath}`);
  process.exit(1);
}
console.log(`CAPTURE_PASS image=${output} receipt=${receiptPath}`);
