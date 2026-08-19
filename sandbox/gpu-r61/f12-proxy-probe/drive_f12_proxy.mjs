// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Browser topology proof for the temporary BW_F12_PROXY probe in
// editors/render/render_internal.cc. This driver invokes Render through a real,
// trusted F12 key event. It never calls bpy.ops.render or any EXEC seam.
//
// Start the standard COOP/COEP server separately:
//   BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin \
//   BLENDER_WEB_SHELL=$PWD/platform_web/shell \
//     /opt/homebrew/bin/bash scripts/serve-web.sh 8150
//
// Run from /Users/paws/blender-web:
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/gpu-r61/f12-proxy-probe/drive_f12_proxy.mjs \
//       [port] [timeout_ms] [label] [happy|force]

import { createHash } from 'crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'fs';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';

const ROOT = '/Users/paws/blender-web';
const OUTDIR = `${ROOT}/sandbox/gpu-r61/f12-proxy-probe/evidence`;
const DRIVER_PATH = fileURLToPath(import.meta.url);
const WIDTH = 1280;
const HEIGHT = 720;
const BOOT_MS = 300000;
const DEFAULT_PROBE_MS = 120000;
const HEARTBEAT_MS = 40;
const WORKER_PHASES = new Set(['WORKER_ARM', 'ENQUEUED', 'WORKER_RETURN']);
const COMMON_DETAILS = {
  INVOKE: {},
  WORKER_ARM: {},
  ENQUEUED: { ok: '1' },
  BEGIN: { same_wm: '1' },
  YIELD: { timeout_armed: '1' },
  QUEUE_DESTROY: {},
};
const CONTRACTS = {
  happy: {
    probeValue: '1',
    phases: [
      'INVOKE', 'WORKER_ARM', 'ENQUEUED', 'BEGIN', 'YIELD',
      'RESUME', 'SIGNAL', 'WORKER_RETURN', 'QUEUE_DESTROY',
    ],
    wmPhases: new Set(['INVOKE', 'BEGIN', 'YIELD', 'RESUME', 'SIGNAL', 'QUEUE_DESTROY']),
    details: new Map(Object.entries({
      ...COMMON_DETAILS,
      RESUME: { same_wm: '1', g_break: '0', abort: '0' },
      SIGNAL: { reason: 'resume' },
      WORKER_RETURN: { reason: 'resume' },
    })),
    heartbeatEndPhase: 'RESUME',
  },
  force: {
    probeValue: 'force',
    phases: [
      'INVOKE', 'WORKER_ARM', 'ENQUEUED', 'BEGIN', 'YIELD', 'FORCE_KILL_ENTER',
      'PREJOIN_ABORT', 'TIMEOUT_CLEAR', 'WORKER_RETURN', 'QUEUE_DESTROY',
    ],
    wmPhases: new Set([
      'INVOKE', 'BEGIN', 'YIELD', 'FORCE_KILL_ENTER', 'PREJOIN_ABORT',
      'TIMEOUT_CLEAR', 'QUEUE_DESTROY',
    ]),
    details: new Map(Object.entries({
      ...COMMON_DETAILS,
      FORCE_KILL_ENTER: { same_wm: '1' },
      PREJOIN_ABORT: { same_wm: '1', drain: '0' },
      TIMEOUT_CLEAR: {},
      WORKER_RETURN: { reason: 'abort' },
    })),
    heartbeatEndPhase: 'FORCE_KILL_ENTER',
  },
};
const BASE_KEYS = new Set(['seq', 'phase', 'main', 'thread', 'tick']);
const CC0 =
  'SPDX-FileCopyrightText: 2026 blender-web contributors\n' +
  'SPDX-License-Identifier: CC0-1.0\n';
const GPU_ERROR_RE = /GPU[- _]?ERROR|Dawn[^\n]*error|WGPU[^\n]*error|WebGPU[^\n]*error|ValidationError|validation error|uncaptured error|DeviceLost|device lost|Aborted|abort\(|RuntimeError|table index is out of bounds/i;

function elapsedMs(startedAt) {
  return Date.now() - startedAt;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Parse key=value tokens independently of their printed order. */
function parseProxyLine(text, receivedAtMs = 0, consoleIndex = 0) {
  const prefix = 'BW_F12_PROXY ';
  if (!text.startsWith(prefix)) return null;
  const fields = {};
  const errors = [];
  for (const token of text.slice(prefix.length).trim().split(/\s+/)) {
    if (!token) continue;
    const split = token.indexOf('=');
    if (split < 1 || split === token.length - 1) {
      errors.push(`malformed token ${token}`);
      continue;
    }
    const key = token.slice(0, split);
    const value = token.slice(split + 1);
    if (Object.hasOwn(fields, key)) errors.push(`duplicate key ${key}`);
    fields[key] = value;
  }
  for (const key of BASE_KEYS) {
    if (!Object.hasOwn(fields, key)) errors.push(`missing ${key}`);
  }
  if (fields.seq && !/^\d+$/.test(fields.seq)) errors.push(`invalid seq ${fields.seq}`);
  if (fields.phase && !/^[A-Z_]+$/.test(fields.phase)) errors.push(`invalid phase ${fields.phase}`);
  if (fields.main && !/^[01]$/.test(fields.main)) errors.push(`invalid main ${fields.main}`);
  if (fields.thread && !/^\d+$/.test(fields.thread)) errors.push(`invalid thread ${fields.thread}`);
  if (fields.tick && !/^\d+$/.test(fields.tick)) errors.push(`invalid tick ${fields.tick}`);
  return { text, fields, receivedAtMs, consoleIndex, parseErrors: errors };
}

function sameDetails(event, expected) {
  const actual = Object.fromEntries(
    Object.entries(event.fields).filter(([key]) => !BASE_KEYS.has(key)),
  );
  const actualKeys = Object.keys(actual).sort();
  const expectedKeys = Object.keys(expected).sort();
  return actualKeys.length === expectedKeys.length &&
    actualKeys.every((key, index) => key === expectedKeys[index] && actual[key] === expected[key]);
}

function validateTopology(events, heartbeats, mode = 'happy') {
  const contract = CONTRACTS[mode];
  if (!contract) return { ok: false, errors: [`unknown mode ${mode}`] };
  const phases = contract.phases;
  const wmPhases = contract.wmPhases;
  const errors = [];
  for (const event of events) errors.push(...event.parseErrors.map((error) => `${event.fields.phase || '?'}: ${error}`));
  const actualPhases = events.map((event) => event.fields.phase);
  if (actualPhases.length !== phases.length ||
      actualPhases.some((phase, index) => phase !== phases[index]))
  {
    errors.push(`phase order ${actualPhases.join('>')} expected ${phases.join('>')}`);
  }

  const byPhase = new Map();
  for (const event of events) {
    if (byPhase.has(event.fields.phase)) errors.push(`duplicate phase ${event.fields.phase}`);
    byPhase.set(event.fields.phase, event);
  }
  for (const phase of phases) {
    const event = byPhase.get(phase);
    if (!event) continue;
    if (!sameDetails(event, contract.details.get(phase))) {
      errors.push(`${phase}: detail fields differ from ${JSON.stringify(contract.details.get(phase))}`);
    }
    const expectedMain = wmPhases.has(phase) ? '1' : '0';
    if (event.fields.main !== expectedMain) {
      errors.push(`${phase}: main=${event.fields.main} expected ${expectedMain}`);
    }
  }

  const present = phases.map((phase) => byPhase.get(phase)).filter(Boolean);
  const structurallyComplete = present.length === phases.length &&
    events.length === phases.length && present.every((event) => event.parseErrors.length === 0);
  if (structurallyComplete) {
    const sequences = new Set(present.map((event) => event.fields.seq));
    if (sequences.size !== 1 || present[0].fields.seq === '0') {
      errors.push(`sequence identity invalid: ${[...sequences].join(',')}`);
    }
    const wmThreads = new Set(
      present.filter((event) => wmPhases.has(event.fields.phase)).map((event) => event.fields.thread),
    );
    const workerThreads = new Set(
      present.filter((event) => WORKER_PHASES.has(event.fields.phase)).map((event) => event.fields.thread),
    );
    if (wmThreads.size !== 1 || wmThreads.has('0')) {
      errors.push(`WM thread identity invalid: ${[...wmThreads].join(',')}`);
    }
    if (workerThreads.size !== 1 || workerThreads.has('0')) {
      errors.push(`worker thread identity invalid: ${[...workerThreads].join(',')}`);
    }
    if (wmThreads.size === 1 && workerThreads.size === 1 &&
        [...wmThreads][0] === [...workerThreads][0])
    {
      errors.push(`WM and worker threads are identical: ${[...wmThreads][0]}`);
    }

    const ticks = present.map((event) => BigInt(event.fields.tick));
    for (let index = 1; index < ticks.length; index++) {
      if (ticks[index] < ticks[index - 1]) {
        errors.push(`${phases[index]} tick ${ticks[index]} precedes ${phases[index - 1]} ${ticks[index - 1]}`);
      }
    }
    const beginTick = BigInt(byPhase.get('BEGIN').fields.tick);
    const yieldTick = BigInt(byPhase.get('YIELD').fields.tick);
    if (beginTick !== yieldTick) errors.push(`BEGIN/YIELD ticks differ: ${beginTick}/${yieldTick}`);
    if (mode === 'happy') {
      const resumeTick = BigInt(byPhase.get('RESUME').fields.tick);
      const signalTick = BigInt(byPhase.get('SIGNAL').fields.tick);
      if (resumeTick !== signalTick) errors.push(`RESUME/SIGNAL ticks differ: ${resumeTick}/${signalTick}`);
      if (resumeTick <= yieldTick) errors.push(`RESUME did not cross a WM tick: ${yieldTick}->${resumeTick}`);
    }
    else {
      const forceTick = BigInt(byPhase.get('FORCE_KILL_ENTER').fields.tick);
      const abortTick = BigInt(byPhase.get('PREJOIN_ABORT').fields.tick);
      const clearTick = BigInt(byPhase.get('TIMEOUT_CLEAR').fields.tick);
      if (forceTick <= yieldTick) {
        errors.push(`FORCE_KILL_ENTER did not cross a WM tick: ${yieldTick}->${forceTick}`);
      }
      if (forceTick !== abortTick || abortTick !== clearTick) {
        errors.push(`force/prejoin/clear ticks differ: ${forceTick}/${abortTick}/${clearTick}`);
      }
    }
  }

  let uiHeartbeat = null;
  const yieldEvent = byPhase.get('YIELD');
  const heartbeatEndEvent = byPhase.get(contract.heartbeatEndPhase);
  if (yieldEvent && heartbeatEndEvent && /^\d+$/.test(yieldEvent.fields.tick || '') &&
      /^\d+$/.test(heartbeatEndEvent.fields.tick || ''))
  {
    const yieldTick = BigInt(yieldEvent.fields.tick);
    const heartbeatEndTick = BigInt(heartbeatEndEvent.fields.tick);
    uiHeartbeat = heartbeats.find((sample) =>
      sample.atMs > yieldEvent.receivedAtMs && sample.atMs < heartbeatEndEvent.receivedAtMs &&
      /^\d+$/.test(sample.tick || '') &&
      BigInt(sample.tick) > yieldTick && BigInt(sample.tick) <= heartbeatEndTick
    ) || null;
    if (!uiHeartbeat) {
      errors.push(`no rising WM heartbeat sample strictly between YIELD and ${contract.heartbeatEndPhase}`);
    }
  }
  else {
    errors.push(`cannot validate UI heartbeat without valid YIELD/${contract.heartbeatEndPhase} ticks`);
  }

  return {
    ok: errors.length === 0,
    errors,
    sequence: present.length ? present[0].fields.seq : null,
    mode,
    wmThread: present.length === phases.length ? byPhase.get('INVOKE').fields.thread : null,
    workerThread: present.length === phases.length ? byPhase.get('WORKER_ARM').fields.thread : null,
    uiHeartbeat,
  };
}

if (process.argv[2] === '--selfcheck') {
  const happySamples = [
    ['phase=INVOKE seq=77 thread=11 tick=100 main=1', 10],
    ['tick=101 main=0 phase=WORKER_ARM thread=22 seq=77', 20],
    ['ok=1 thread=22 seq=77 phase=ENQUEUED main=0 tick=101', 30],
    ['same_wm=1 main=1 seq=77 tick=102 phase=BEGIN thread=11', 35],
    ['timeout_armed=1 tick=102 thread=11 phase=YIELD seq=77 main=1', 40],
    ['same_wm=1 g_break=0 abort=0 thread=11 seq=77 tick=110 main=1 phase=RESUME', 80],
    ['reason=resume phase=SIGNAL tick=110 main=1 thread=11 seq=77', 81],
    ['main=0 reason=resume seq=77 thread=22 phase=WORKER_RETURN tick=110', 82],
    ['seq=77 main=1 phase=QUEUE_DESTROY tick=111 thread=11', 90],
  ];
  const happyEvents = happySamples.map(([tokens, atMs], index) =>
    parseProxyLine(`BW_F12_PROXY ${tokens}`, atMs, index)
  );
  const happyHeartbeats = [{ atMs: 55, tick: '105' }];
  const happy = validateTopology(happyEvents, happyHeartbeats, 'happy');
  const wrongOrder = validateTopology(
    [happyEvents[1], happyEvents[0], ...happyEvents.slice(2)], happyHeartbeats, 'happy'
  );
  const wrongThreadEvents = happyEvents.map((event) => ({
    ...event,
    fields: { ...event.fields },
  }));
  wrongThreadEvents[8].fields.thread = '99';
  const wrongThread = validateTopology(wrongThreadEvents, happyHeartbeats, 'happy');

  const forceSamples = [
    ['phase=INVOKE seq=88 thread=11 tick=200 main=1', 100],
    ['tick=201 main=0 phase=WORKER_ARM thread=22 seq=88', 110],
    ['ok=1 thread=22 seq=88 phase=ENQUEUED main=0 tick=201', 120],
    ['same_wm=1 main=1 seq=88 tick=202 phase=BEGIN thread=11', 130],
    ['timeout_armed=1 tick=202 thread=11 phase=YIELD seq=88 main=1', 140],
    ['same_wm=1 tick=206 thread=11 phase=FORCE_KILL_ENTER seq=88 main=1', 200],
    ['drain=0 seq=88 phase=PREJOIN_ABORT thread=11 same_wm=1 main=1 tick=206', 201],
    ['phase=TIMEOUT_CLEAR thread=11 tick=206 seq=88 main=1', 202],
    ['reason=abort seq=88 main=0 phase=WORKER_RETURN tick=206 thread=22', 203],
    ['seq=88 main=1 phase=QUEUE_DESTROY tick=207 thread=11', 210],
  ];
  const forceEvents = forceSamples.map(([tokens, atMs], index) =>
    parseProxyLine(`BW_F12_PROXY ${tokens}`, atMs, index)
  );
  const forceHeartbeats = [{ atMs: 170, tick: '204' }];
  const force = validateTopology(forceEvents, forceHeartbeats, 'force');
  const missingTimeoutClear = validateTopology(
    forceEvents.filter((event) => event.fields.phase !== 'TIMEOUT_CLEAR'), forceHeartbeats, 'force'
  );
  const wrongAbortReasonEvents = forceEvents.map((event) => ({
    ...event,
    fields: { ...event.fields },
  }));
  wrongAbortReasonEvents[8].fields.reason = 'resume';
  const wrongAbortReason = validateTopology(wrongAbortReasonEvents, forceHeartbeats, 'force');
  const checks = [
    happy.ok,
    happy.sequence === '77',
    happy.wmThread === '11',
    happy.workerThread === '22',
    happy.uiHeartbeat?.tick === '105',
    !wrongOrder.ok,
    !wrongThread.ok,
    force.ok,
    force.sequence === '88',
    force.uiHeartbeat?.tick === '204',
    !missingTimeoutClear.ok,
    !wrongAbortReason.ok,
  ];
  if (checks.every(Boolean)) {
    console.log('SELF_CHECK_PASS probe=f12-proxy modes=happy,force phases=9,10 token_order=independent physical_key=required prejoin_abort=exact timeout_clear=required');
    process.exit(0);
  }
  console.error(`SELF_CHECK_FAIL probe=f12-proxy happy=${JSON.stringify(happy.errors)} force=${JSON.stringify(force.errors)}`);
  process.exit(1);
}

const PORT = Number.parseInt(process.argv[2] || '8150', 10);
const PROBE_MS = Number.parseInt(process.argv[3] || String(DEFAULT_PROBE_MS), 10);
const MODE = (process.argv[5] || 'happy').trim();
const CONTRACT = CONTRACTS[MODE];
const LABEL = (process.argv[4] || (MODE === 'force' ? 'f12-proxy-force' : 'f12-proxy')).trim();
if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) {
  console.error(`invalid port: ${process.argv[2] || ''}`);
  process.exit(2);
}
if (!Number.isInteger(PROBE_MS) || PROBE_MS < 2000) {
  console.error(`invalid timeout_ms: ${process.argv[3] || ''}`);
  process.exit(2);
}
if (!CONTRACT) {
  console.error(`invalid mode: ${MODE}; expected happy or force`);
  process.exit(2);
}
if (!/^[A-Za-z0-9._-]+$/.test(LABEL)) {
  console.error(`invalid label: ${LABEL}`);
  process.exit(2);
}

const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const base = `http://127.0.0.1:${PORT}`;
/* Binding requirement: pyexpr only arms the topology probe. It does not invoke
 * render, register a timer, redraw an area, or mutate the scene. */
const pythonExpr = `import os; os.environ["BW_F12_PROXY_PROBE"] = "${CONTRACT.probeValue}"`;
const url = `${base}/windowed.html?gate=${WIDTH}x${HEIGHT}&pyexpr=${encodeURIComponent(pythonExpr)}`;
const prefix = `${OUTDIR}/${LABEL}`;
const consolePath = `${prefix}-console.log`;
const consoleLicensePath = `${consolePath}.license`;
const manifestPath = `${prefix}-manifest.json`;
const manifestLicensePath = `${manifestPath}.license`;
const screenshotPath = `${prefix}-${WIDTH}x${HEIGHT}.png`;
const screenshotLicensePath = `${screenshotPath}.license`;

const startedAt = Date.now();
const consoleEntries = [];
const proxyEvents = [];
const gpuErrors = [];
const pageErrors = [];
const heartbeats = [];
const marks = [];
let pageCrashed = false;
let runError = null;
let heartbeatError = null;
let stopHeartbeat = false;
let gateReceipt = null;
let physicalKeyReceipt = null;
let topology = null;
let screenshotSha256 = null;
let screenshotCaptured = false;

function mark(label, extra = {}) {
  const entry = { label, iso: new Date().toISOString(), atMs: elapsedMs(startedAt), ...extra };
  marks.push(entry);
  console.log(`[${entry.iso}] ${label}`);
}

function firstBlockingReason() {
  if (pageCrashed) return 'page crashed';
  if (pageErrors.length) return `page error: ${pageErrors[0]}`;
  if (gpuErrors.length) return `GPU/browser error: ${gpuErrors[0]}`;
  if (heartbeatError) return `heartbeat error: ${heartbeatError}`;
  return null;
}

async function readWmTick(page) {
  return page.evaluate(() => {
    const module = window.__bwModule;
    if (!module || typeof module._bw_wm_tick_count !== 'function') return null;
    return String(Math.trunc(Number(module._bw_wm_tick_count())));
  });
}

mkdirSync(OUTDIR, { recursive: true });
const browser = await chromium.launch({
  headless: false,
  /* Keep Chromium's developer-tools accelerator from consuming F12 before the
   * focused canvas can deliver the trusted event to GHOST. */
  args: ['--enable-unsafe-webgpu', '--use-angle=metal', '--disable-dev-tools'],
});
const context = await browser.newContext({
  viewport: { width: WIDTH + 120, height: HEIGHT + 120 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();

page.on('console', (message) => {
  const text = message.text();
  const atMs = elapsedMs(startedAt);
  const index = consoleEntries.length;
  consoleEntries.push(`[${new Date().toISOString()}] [console:${message.type()}] ${text}`);
  const event = parseProxyLine(text, atMs, index);
  if (event) proxyEvents.push(event);
  const benignDeviceReceipt = /^\[bw\] WM-worker WebGPU device pre-acquired \(ADR-007\); features=\d+ tier1=(?:true|false) tier2=(?:true|false) maxStorageTexturesPerShaderStage=\d+ maxStorageBuffersPerShaderStage=\d+ maxBufferSize=\d+ maxStorageBufferBindingSize=\d+$/.test(text);
  if (!benignDeviceReceipt &&
      (GPU_ERROR_RE.test(text) ||
       (message.type() === 'error' && /\b(?:gpu|webgpu|wgpu|dawn)\b/i.test(text))))
  {
    gpuErrors.push(text);
  }
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

let heartbeatPromise = null;
try {
  mark('boot begin', { port: PORT, timeoutMs: PROBE_MS, mode: MODE });
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
        window.devicePixelRatio === 1 && document.body.classList.contains('bw-gate') &&
        window.crossOriginIsolated === true &&
        typeof window.__bwModule?._bw_wm_tick_count === 'function';
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

  /* Dismiss the startup splash through input, not Python, then restore canvas focus. */
  const canvas = page.locator('#canvas');
  await page.bringToFront();
  await canvas.click({ position: { x: 32, y: 32 } });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);
  await page.bringToFront();
  await canvas.click({ position: { x: 32, y: 32 } });
  const focusReceipt = await page.evaluate(() => ({
    hasFocus: document.hasFocus(),
    activeId: document.activeElement?.id || null,
  }));
  if (!focusReceipt.hasFocus || focusReceipt.activeId !== 'canvas') {
    throw new Error(`canvas focus unavailable: ${JSON.stringify(focusReceipt)}`);
  }
  await page.evaluate(() => {
    window.__bwF12DriverKeyEvents = [];
    window.addEventListener('keydown', (event) => {
      if (event.key === 'F12' || event.code === 'F12') {
        window.__bwF12DriverKeyEvents.push({
          key: event.key,
          code: event.code,
          isTrusted: event.isTrusted,
          repeat: event.repeat,
          targetId: event.target?.id || null,
          activeId: document.activeElement?.id || null,
        });
      }
    }, { capture: true });
  });

  heartbeatPromise = (async () => {
    while (!stopHeartbeat) {
      try {
        const tick = await readWmTick(page);
        heartbeats.push({ atMs: elapsedMs(startedAt), tick });
      } catch (error) {
        if (!stopHeartbeat) heartbeatError = error.stack || error.message || String(error);
        return;
      }
      await sleep(HEARTBEAT_MS);
    }
  })();

  const tickBefore = await readWmTick(page);
  const dispatchAtMs = elapsedMs(startedAt);
  mark('physical F12 dispatch', { tickBefore, method: 'page.keyboard.press(F12)' });
  await page.keyboard.press('F12');

  const deadline = Date.now() + PROBE_MS;
  while (Date.now() < deadline) {
    const blocker = firstBlockingReason();
    if (blocker) throw new Error(blocker);
    if (proxyEvents.some((event) => event.fields.phase === 'QUEUE_DESTROY')) break;
    await sleep(50);
  }
  if (!proxyEvents.some((event) => event.fields.phase === 'QUEUE_DESTROY')) {
    throw new Error(`topology timeout after ${PROBE_MS} ms; phases=${proxyEvents.map((event) => event.fields.phase).join('>')}`);
  }
  await page.waitForTimeout(500);
  const blocker = firstBlockingReason();
  if (blocker) throw new Error(blocker);

  physicalKeyReceipt = await page.evaluate(() => window.__bwF12DriverKeyEvents || []);
  if (physicalKeyReceipt.length !== 1 || physicalKeyReceipt[0].key !== 'F12' ||
      physicalKeyReceipt[0].code !== 'F12' || physicalKeyReceipt[0].isTrusted !== true ||
      physicalKeyReceipt[0].repeat !== false || physicalKeyReceipt[0].targetId !== 'canvas' ||
      physicalKeyReceipt[0].activeId !== 'canvas')
  {
    throw new Error(`physical F12 receipt invalid: ${JSON.stringify(physicalKeyReceipt)}`);
  }

  topology = validateTopology(proxyEvents, heartbeats, MODE);
  if (!topology.ok) throw new Error(`topology invalid: ${topology.errors.join('; ')}`);
  const tickAfter = await readWmTick(page);
  if (!/^\d+$/.test(tickBefore || '') || !/^\d+$/.test(tickAfter || '') ||
      BigInt(tickAfter) <= BigInt(tickBefore))
  {
    throw new Error(`WM tick did not advance across F12: ${tickBefore}->${tickAfter}`);
  }
  mark('topology accepted', {
    sequence: topology.sequence,
    wmThread: topology.wmThread,
    workerThread: topology.workerThread,
    dispatchAtMs,
    tickBefore,
    tickAfter,
  });

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
  if (!topology) topology = validateTopology(proxyEvents, heartbeats, MODE);
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
  stopHeartbeat = true;
  if (heartbeatPromise) await heartbeatPromise;
  await context.close();
  await browser.close();
}

const consoleText = `${consoleEntries.join('\n')}\n`;
writeFileSync(consolePath, consoleText);
writeFileSync(consoleLicensePath, CC0);
const consoleSha256 = createHash('sha256').update(consoleText).digest('hex');
const driverSha256 = createHash('sha256').update(readFileSync(DRIVER_PATH)).digest('hex');
const exactGate = gateReceipt?.backingWidth === WIDTH && gateReceipt?.backingHeight === HEIGHT &&
  gateReceipt?.cssWidth === WIDTH && gateReceipt?.cssHeight === HEIGHT &&
  gateReceipt?.dpr === 1 && gateReceipt?.gateClass === true &&
  gateReceipt?.crossOriginIsolated === true;
const physicalF12 = physicalKeyReceipt?.length === 1 && physicalKeyReceipt[0].key === 'F12' &&
  physicalKeyReceipt[0].code === 'F12' && physicalKeyReceipt[0].isTrusted === true &&
  physicalKeyReceipt[0].repeat === false && physicalKeyReceipt[0].targetId === 'canvas' &&
  physicalKeyReceipt[0].activeId === 'canvas';
const accepted = !runError && !pageCrashed && pageErrors.length === 0 && gpuErrors.length === 0 &&
  !heartbeatError && topology?.ok === true && physicalF12 && exactGate &&
  screenshotCaptured && Boolean(screenshotSha256);
const serializableEvents = proxyEvents.map((event) => ({
  line: event.text,
  fields: event.fields,
  receivedAtMs: event.receivedAtMs,
  consoleIndex: event.consoleIndex,
  parseErrors: event.parseErrors,
}));
const manifest = {
  schema: 'blender-web.f12-proxy-probe.v1',
  verdict: accepted ? 'PASS' : 'FAIL',
  generatedAt: new Date().toISOString(),
  driver: { path: DRIVER_PATH, sha256: driverSha256 },
  server: { base, port: PORT, shell: 'platform_web/shell', bin: 'build-wasm-windowed-opt/bin' },
  browser: {
    engine: 'playwright-chromium',
    headed: true,
    args: ['--enable-unsafe-webgpu', '--use-angle=metal'],
  },
  invocation: {
    mode: MODE,
    method: 'page.keyboard.press(F12)',
    pythonExpr,
    bpyExecUsed: false,
    keyReceipt: physicalKeyReceipt,
    physicalTrustedF12: Boolean(physicalF12),
  },
  url,
  timeoutMs: PROBE_MS,
  gate: { expected: `${WIDTH}x${HEIGHT}@1`, receipt: gateReceipt, exact: Boolean(exactGate) },
  topology: {
    mode: MODE,
    expectedPhases: CONTRACT.phases,
    result: topology,
    events: serializableEvents,
  },
  heartbeat: {
    intervalMs: HEARTBEAT_MS,
    sampleCount: heartbeats.length,
    samples: heartbeats,
    error: heartbeatError,
    interval: `YIELD..${CONTRACT.heartbeatEndPhase}`,
    betweenYieldAndEnd: topology?.uiHeartbeat || null,
  },
  assertions: {
    physicalTrustedF12: Boolean(physicalF12),
    strictPhaseOrder: topology?.ok === true,
    stableSequence: Boolean(topology?.sequence),
    distinctWmAndWorkerThreads: Boolean(
      topology?.wmThread && topology?.workerThread && topology.wmThread !== topology.workerThread
    ),
    uiHeartbeatBetweenYieldAndEnd: Boolean(topology?.uiHeartbeat),
    forcePrejoinAbortExact: MODE !== 'force' ||
      proxyEvents.some((event) => event.fields.phase === 'PREJOIN_ABORT' &&
        event.fields.same_wm === '1' && event.fields.drain === '0'),
    forceTimeoutClearObserved: MODE !== 'force' ||
      proxyEvents.some((event) => event.fields.phase === 'TIMEOUT_CLEAR'),
    forceWorkerReturnAbort: MODE !== 'force' ||
      proxyEvents.some((event) => event.fields.phase === 'WORKER_RETURN' &&
        event.fields.reason === 'abort'),
    queueDestroyed: proxyEvents.some((event) => event.fields.phase === 'QUEUE_DESTROY'),
    noGpuError: gpuErrors.length === 0,
    noPageError: pageErrors.length === 0,
    noPageCrash: !pageCrashed,
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
  failures: { runError, heartbeatError, pageCrashed, pageErrors, gpuErrors },
  marks,
};
writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
writeFileSync(manifestLicensePath, CC0);

if (!accepted) {
  console.error(`F12_PROXY_DRIVER_FAIL manifest=${manifestPath} console=${consolePath}`);
  process.exit(1);
}
console.log(
  `F12_PROXY_DRIVER_PASS manifest=${manifestPath} console=${consolePath} screenshot=${screenshotPath}`,
);
