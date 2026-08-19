// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Browser evidence driver for the temporary L-B exact async texture-readback probe.
// The matching wasm binary must contain the temporary BW_LB_ASYNC probe hook. This
// file deliberately lives under sandbox/ and does not modify production sources.
//
// Start the standard COOP/COEP server separately:
//   BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin \
//   BLENDER_WEB_SHELL=$PWD/platform_web/shell \
//     /opt/homebrew/bin/bash scripts/serve-web.sh 8149
//
// Run from /Users/paws/blender-web:
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/gpu-r61/lb-async-probe/drive_lb_async.mjs [port] [timeout_ms] [label]
//
// The driver accepts only the two exact receipt shapes documented by the L-B
// design. It also requires a real WM-turn boundary, a clean browser/GPU console,
// and an exact 1280x720 DPR-1 gate before writing a PASS manifest.

import { createHash } from 'crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'fs';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';

const ROOT = '/Users/paws/blender-web';
const OUTDIR = `${ROOT}/sandbox/gpu-r61/lb-async-probe/evidence`;
const DRIVER_PATH = fileURLToPath(import.meta.url);
const WIDTH = 1280;
const HEIGHT = 720;
const BOOT_MS = 300000;
const DEFAULT_RECEIPT_MS = 120000;
const CC0 =
  'SPDX-FileCopyrightText: 2026 blender-web contributors\n' +
  'SPDX-License-Identifier: CC0-1.0\n';

const KICK_RE = /^BW_LB_ASYNC phase=kick tick=(\d+) primary=PENDING error=NONE raw=8 host=16 rel_mip=0 abs_mip=1 abs_layer=1 source_freed=1 view_freed=1 cancel_before=PENDING cancel_after=NULL verdict=PASS$/;
const SETTLE_RE = /^BW_LB_ASYNC phase=settle kick_tick=(\d+) settle_tick=(\d+) tick_delta=(\d+) status=READY error=NONE size=16 rgba=0\.25,0\.5,0\.75,1 consume1=1 ptr_null=1 consume2=0 verdict=PASS$/;
const PROBE_FAIL_RE = /\bBW_LB_ASYNC\b.*\b(?:verdict=FAIL|FAIL)\b/i;
const FAIL_RE = /\b(?:FAIL|FAILED|FAILURE)\b/i;
const GPU_ERROR_RE = /GPU[- _]?ERROR|ValidationError|validation error|uncaptured error|DeviceLost|device lost|Aborted|abort\(|RuntimeError|table index is out of bounds|WebGPU[^\n]*error/i;
const BENIGN_BOOT_RE = /^(?:Failed to load resource: the server responded with a status of 404 \(File not found\)|.*OpenImageIO-3\.1\.13\.1\/src\/libutil\/sysutil\.cpp:214: physical_memory: Assertion '0 && "Need to implement Sysutil::physical_memory on this platform"' failed\.)$/;

function parseKick(line) {
  const match = KICK_RE.exec(line);
  return match ? { line, tick: Number(match[1]) } : null;
}

function parseSettle(line) {
  const match = SETTLE_RE.exec(line);
  return match ? {
    line,
    kickTick: Number(match[1]),
    settleTick: Number(match[2]),
    tickDelta: Number(match[3]),
  } : null;
}

if (process.argv[2] === '--selfcheck') {
  const kick = parseKick(
    'BW_LB_ASYNC phase=kick tick=41 primary=PENDING error=NONE raw=8 host=16 rel_mip=0 abs_mip=1 abs_layer=1 source_freed=1 view_freed=1 cancel_before=PENDING cancel_after=NULL verdict=PASS',
  );
  const settle = parseSettle(
    'BW_LB_ASYNC phase=settle kick_tick=41 settle_tick=43 tick_delta=2 status=READY error=NONE size=16 rgba=0.25,0.5,0.75,1 consume1=1 ptr_null=1 consume2=0 verdict=PASS',
  );
  const checks = [
    kick?.tick === 41,
    settle?.kickTick === 41,
    settle?.settleTick === 43,
    settle?.tickDelta === 2,
    !parseKick(`${kick?.line} trailing`),
    !parseSettle(settle?.line.replace('size=16', 'size=8')),
    PROBE_FAIL_RE.test('BW_LB_ASYNC phase=settle verdict=FAIL reason=timeout'),
    GPU_ERROR_RE.test('WebGPU ValidationError: bad texture descriptor'),
  ];
  if (checks.every(Boolean)) {
    console.log('SELF_CHECK_PASS probe=lb-async exact_receipts=2 distinct_ticks=required gate=1280x720');
    process.exit(0);
  }
  console.error('SELF_CHECK_FAIL probe=lb-async');
  process.exit(1);
}

const PORT = Number.parseInt(process.argv[2] || '8149', 10);
const RECEIPT_MS = Number.parseInt(process.argv[3] || String(DEFAULT_RECEIPT_MS), 10);
const LABEL = (process.argv[4] || 'lb-async').trim();
if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) {
  console.error(`invalid port: ${process.argv[2] || ''}`);
  process.exit(2);
}
if (!Number.isInteger(RECEIPT_MS) || RECEIPT_MS < 1000) {
  console.error(`invalid timeout_ms: ${process.argv[3] || ''}`);
  process.exit(2);
}
if (!/^[A-Za-z0-9._-]+$/.test(LABEL)) {
  console.error(`invalid label: ${LABEL}`);
  process.exit(2);
}

const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const pythonExpr = [
  'import bpy, os',
  'os.environ["BW_DIAG"] = "1"',
  'os.environ["BW_LB_ASYNC_PROBE"] = "1"',
  'bpy.context.preferences.view.show_splash = False',
  'def _bw_lb_redraw():',
  '    try:',
  '        for win in bpy.context.window_manager.windows:',
  '            if win.screen:',
  '                for area in win.screen.areas:',
  '                    area.tag_redraw()',
  '    except Exception as exc:',
  '        os.write(2, ("BW_LB_DRIVER_FAIL redraw=" + repr(exc) + "\\n").encode())',
  '        return None',
  '    return 0.05',
  'bpy.app.timers.register(_bw_lb_redraw, first_interval=0.05)',
].join('\n');

const base = `http://127.0.0.1:${PORT}`;
const url = `${base}/windowed.html?gate=${WIDTH}x${HEIGHT}&pyexpr=${encodeURIComponent(pythonExpr)}`;
const prefix = `${OUTDIR}/${LABEL}`;
const consolePath = `${prefix}-console.log`;
const consoleLicensePath = `${consolePath}.license`;
const manifestPath = `${prefix}-manifest.json`;
const manifestLicensePath = `${manifestPath}.license`;
const screenshotPath = `${prefix}-${WIDTH}x${HEIGHT}.png`;
const screenshotLicensePath = `${screenshotPath}.license`;

const consoleEntries = [];
const exactKickLines = [];
const exactSettleLines = [];
const probeFailLines = [];
const failLines = [];
const gpuErrors = [];
const pageErrors = [];
const marks = [];
let pageCrashed = false;
let runError = null;
let gateReceipt = null;
let screenshotSha256 = null;
let screenshotCaptured = false;
let kickReceipt = null;
let settleReceipt = null;

function mark(label, extra = {}) {
  const entry = { label, iso: new Date().toISOString(), ...extra };
  marks.push(entry);
  console.log(`[${entry.iso}] ${label}`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function firstBlockingReason() {
  if (pageCrashed) return 'page crashed';
  if (pageErrors.length > 0) return `page error: ${pageErrors[0]}`;
  if (probeFailLines.length > 0) return `probe FAIL: ${probeFailLines[0]}`;
  if (failLines.length > 0) return `console FAIL: ${failLines[0]}`;
  if (gpuErrors.length > 0) return `GPU/browser error: ${gpuErrors[0]}`;
  return null;
}

async function waitForReceipts(timeoutMs) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const blocker = firstBlockingReason();
    if (blocker) throw new Error(blocker);
    if (exactKickLines.length > 1 || exactSettleLines.length > 1) {
      throw new Error(
        `duplicate exact receipts: kick=${exactKickLines.length} settle=${exactSettleLines.length}`,
      );
    }
    if (exactKickLines.length === 1 && exactSettleLines.length === 1) return;
    await sleep(100);
  }
  throw new Error(
    `receipt timeout after ${timeoutMs} ms: kick=${exactKickLines.length} settle=${exactSettleLines.length}`,
  );
}

mkdirSync(OUTDIR, { recursive: true });
const browser = await chromium.launch({
  headless: false,
  args: ['--enable-unsafe-webgpu', '--use-angle=metal'],
});
const context = await browser.newContext({
  viewport: { width: WIDTH + 120, height: HEIGHT + 120 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();

page.on('console', (message) => {
  const text = message.text();
  const entry = `[${new Date().toISOString()}] [console:${message.type()}] ${text}`;
  consoleEntries.push(entry);
  if (KICK_RE.test(text)) exactKickLines.push(text);
  if (SETTLE_RE.test(text)) exactSettleLines.push(text);
  if (PROBE_FAIL_RE.test(text) || /\bBW_LB_DRIVER_FAIL\b/.test(text)) probeFailLines.push(text);
  /* Chromium requests an optional favicon and this Emscripten build retains OIIO's
   * known non-fatal physical-memory fallback assertion. Neither is a probe/runtime
   * failure; keep both in the raw console evidence but exclude only these exact lines. */
  if (FAIL_RE.test(text) && !BENIGN_BOOT_RE.test(text)) failLines.push(text);
  if (GPU_ERROR_RE.test(text)) gpuErrors.push(text);
});
page.on('pageerror', (error) => {
  const text = error.stack || error.message || String(error);
  pageErrors.push(text);
  consoleEntries.push(`[${new Date().toISOString()}] [pageerror] ${text}`);
});
page.on('crash', () => {
  pageCrashed = true;
  consoleEntries.push(`[${new Date().toISOString()}] [crash] Playwright page crashed`);
});

try {
  mark('boot begin', { port: PORT, timeoutMs: RECEIPT_MS });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
  await page.waitForFunction(
    () => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'),
    undefined,
    { timeout: BOOT_MS },
  );
  mark('WM_main reached');

  await page.waitForFunction(
    ({ width, height }) => {
      const canvas = document.querySelector('#canvas');
      if (!canvas) return false;
      const rect = canvas.getBoundingClientRect();
      return canvas.width === width && canvas.height === height &&
        Math.round(rect.width) === width && Math.round(rect.height) === height &&
        window.devicePixelRatio === 1 && document.body.classList.contains('bw-gate');
    },
    { width: WIDTH, height: HEIGHT },
    { timeout: 30000 },
  );
  gateReceipt = await page.evaluate(() => {
    const canvas = document.querySelector('#canvas');
    const rect = canvas.getBoundingClientRect();
    return {
      backingWidth: canvas.width,
      backingHeight: canvas.height,
      cssWidth: Math.round(rect.width),
      cssHeight: Math.round(rect.height),
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      dpr: window.devicePixelRatio,
      gateClass: document.body.classList.contains('bw-gate'),
      crossOriginIsolated: window.crossOriginIsolated,
    };
  });
  mark('gate exact', gateReceipt);

  await waitForReceipts(RECEIPT_MS);
  /* Let one more activation/console turn pass so a same-tick validation error or
   * accidentally duplicated receipt cannot race the PASS decision. */
  await page.waitForTimeout(750);
  const blocker = firstBlockingReason();
  if (blocker) throw new Error(blocker);
  if (exactKickLines.length !== 1 || exactSettleLines.length !== 1) {
    throw new Error(
      `non-unique receipts after cooldown: kick=${exactKickLines.length} settle=${exactSettleLines.length}`,
    );
  }

  kickReceipt = parseKick(exactKickLines[0]);
  settleReceipt = parseSettle(exactSettleLines[0]);
  if (!kickReceipt || !settleReceipt) throw new Error('internal exact-receipt parse failure');
  if (settleReceipt.kickTick !== kickReceipt.tick) {
    throw new Error(
      `kick tick mismatch: kick=${kickReceipt.tick} settle.kick=${settleReceipt.kickTick}`,
    );
  }
  if (settleReceipt.settleTick <= kickReceipt.tick) {
    throw new Error(
      `receipts did not cross a WM turn: kick=${kickReceipt.tick} settle=${settleReceipt.settleTick}`,
    );
  }
  if (settleReceipt.tickDelta !== settleReceipt.settleTick - kickReceipt.tick ||
      settleReceipt.tickDelta < 1)
  {
    throw new Error(
      `tick_delta mismatch: reported=${settleReceipt.tickDelta} computed=${settleReceipt.settleTick - kickReceipt.tick}`,
    );
  }

  const rect = gateReceipt.rect;
  await page.mouse.move(Math.round(rect.x + 16), Math.round(rect.y + rect.height - 16));
  await page.waitForTimeout(250);
  await page.screenshot({
    path: screenshotPath,
    clip: {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: WIDTH,
      height: HEIGHT,
    },
  });
  screenshotCaptured = true;
  screenshotSha256 = createHash('sha256').update(readFileSync(screenshotPath)).digest('hex');
  writeFileSync(screenshotLicensePath, CC0);
  mark('acceptance screenshot captured', { screenshotPath, screenshotSha256 });
} catch (error) {
  runError = error.stack || error.message || String(error);
  console.error(runError);
  /* A failure screenshot is still useful evidence when the canvas reached the gate. */
  if (!screenshotCaptured && gateReceipt?.rect && !pageCrashed) {
    try {
      const rect = gateReceipt.rect;
      await page.screenshot({
        path: screenshotPath,
        clip: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: WIDTH,
          height: HEIGHT,
        },
      });
      screenshotCaptured = true;
      screenshotSha256 = createHash('sha256').update(readFileSync(screenshotPath)).digest('hex');
      writeFileSync(screenshotLicensePath, CC0);
    } catch (captureError) {
      consoleEntries.push(
        `[${new Date().toISOString()}] [capture-error] ${captureError.stack || captureError}`,
      );
    }
  }
} finally {
  await context.close();
  await browser.close();
}

const consoleText = `${consoleEntries.join('\n')}\n`;
writeFileSync(consolePath, consoleText);
writeFileSync(consoleLicensePath, CC0);
const consoleSha256 = createHash('sha256').update(consoleText).digest('hex');
const driverSha256 = createHash('sha256').update(readFileSync(DRIVER_PATH)).digest('hex');
const exactGate = gateReceipt?.backingWidth === WIDTH &&
  gateReceipt?.backingHeight === HEIGHT &&
  gateReceipt?.cssWidth === WIDTH &&
  gateReceipt?.cssHeight === HEIGHT &&
  gateReceipt?.dpr === 1 &&
  gateReceipt?.gateClass === true &&
  gateReceipt?.crossOriginIsolated === true;
const accepted = !runError && !pageCrashed && pageErrors.length === 0 &&
  probeFailLines.length === 0 && failLines.length === 0 && gpuErrors.length === 0 &&
  exactKickLines.length === 1 &&
  exactSettleLines.length === 1 && kickReceipt && settleReceipt && exactGate &&
  settleReceipt.kickTick === kickReceipt.tick && settleReceipt.settleTick > kickReceipt.tick &&
  settleReceipt.tickDelta === settleReceipt.settleTick - kickReceipt.tick &&
  screenshotCaptured && Boolean(screenshotSha256);

const manifest = {
  schema: 'blender-web.lb-async-probe.v1',
  verdict: accepted ? 'PASS' : 'FAIL',
  generatedAt: new Date().toISOString(),
  driver: { path: DRIVER_PATH, sha256: driverSha256 },
  server: { base, port: PORT, shell: 'platform_web/shell', bin: 'build-wasm-windowed-opt/bin' },
  browser: { engine: 'playwright-chromium', headed: true, args: ['--enable-unsafe-webgpu', '--use-angle=metal'] },
  url,
  gate: { expected: `${WIDTH}x${HEIGHT}@1`, receipt: gateReceipt, exact: Boolean(exactGate) },
  timeoutMs: RECEIPT_MS,
  receipts: {
    kick: kickReceipt,
    settle: settleReceipt,
    exactKickCount: exactKickLines.length,
    exactSettleCount: exactSettleLines.length,
    distinctWmTurns: Boolean(
      kickReceipt && settleReceipt && settleReceipt.settleTick > kickReceipt.tick
    ),
    tickDeltaMatches: Boolean(
      kickReceipt && settleReceipt &&
      settleReceipt.tickDelta === settleReceipt.settleTick - kickReceipt.tick
    ),
  },
  assertions: {
    noProbeFail: probeFailLines.length === 0,
    noConsoleFail: failLines.length === 0,
    noGpuError: gpuErrors.length === 0,
    noPageError: pageErrors.length === 0,
    noPageCrash: !pageCrashed,
    sourceAndViewFreed: Boolean(kickReceipt),
    raw8ToHost16: Boolean(kickReceipt && settleReceipt),
    pendingCancelNull: Boolean(kickReceipt),
    consumeExactlyOnce: Boolean(settleReceipt),
  },
  evidence: {
    console: {
      path: consolePath,
      sha256: consoleSha256,
      entries: consoleEntries.length,
      licensePath: consoleLicensePath,
    },
    screenshot: {
      path: screenshotCaptured ? screenshotPath : null,
      sha256: screenshotSha256,
      licensePath: screenshotCaptured ? screenshotLicensePath : null,
    },
  },
  failures: { runError, pageCrashed, pageErrors, probeFailLines, failLines, gpuErrors },
  marks,
};
writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
writeFileSync(manifestLicensePath, CC0);

if (!accepted) {
  console.error(`LB_ASYNC_DRIVER_FAIL manifest=${manifestPath} console=${consolePath}`);
  process.exit(1);
}
console.log(
  `LB_ASYNC_DRIVER_PASS manifest=${manifestPath} console=${consolePath} screenshot=${screenshotPath}`,
);
