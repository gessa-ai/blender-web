// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Physical Escape cancellation/recovery rig for browser EEVEE F12. It cancels
// two separate renders immediately after observing a PENDING yield. The second
// render must acquire a fresh continuation sequence, proving the first cancel
// did not strand the WM job or its proxy queue. Python only configures the
// already-loaded scene and records passive handler receipts: it never invokes,
// cancels, or re-enters rendering.
//
// Start the normal COOP/COEP server separately, then run from the repo root:
//   BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin \
//   BLENDER_WEB_SHELL=$PWD/platform_web/shell \
//     /opt/homebrew/bin/bash scripts/serve-web.sh 8151
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/gpu-r61/f12-eevee-acceptance/drive_eevee_escape_recovery.mjs \
//       [port] [stage_timeout_ms] [label]

import { createHash } from 'crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'fs';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';

const ROOT = '/Users/paws/blender-web';
const DRIVER_PATH = fileURLToPath(import.meta.url);
const OUTDIR = `${ROOT}/sandbox/gpu-r61/f12-eevee-acceptance/evidence`;
const BLEND_HOST = `${ROOT}/upstream/tests/files/render/principled_bsdf/principled_bsdf_default.blend`;
const OPFS_NAME = 'bw_f12_eevee_escape_recovery.blend';
const BLEND_GUEST = `/projects/${OPFS_NAME}`;
const CONFIG_GUEST = '/tmp/bw_f12_escape_config.json';
const RECEIPT_GUEST = '/tmp/bw_f12_escape_receipt.json';
const WIDTH = 1280;
const HEIGHT = 720;
const RENDER_WIDTH = 128;
const RENDER_HEIGHT = 128;
const BOOT_MS = 300000;
const DEFAULT_STAGE_MS = 120000;
const CC0 =
  'SPDX-FileCopyrightText: 2026 blender-web contributors\n' +
  'SPDX-License-Identifier: CC0-1.0\n';

const ASYNC = Object.freeze({
  prefix: 'BW_F12_ASYNC ',
  envKey: 'BW_F12_ASYNC_PROBE',
  envValue: '1',
  knownStates: new Set([
    'INVOKE', 'QUEUE_CREATE_FAILED', 'ENQUEUED', 'TURN', 'PENDING', 'CONSUME',
    'END_RESULT', 'WRITE', 'PIPELINE_TERMINAL', 'READY', 'FAILED', 'FATAL',
    'WRONG_WM_REQUEUE', 'PREJOIN_ABORT', 'WORKER_RETURN', 'QUEUE_DESTROY',
    'ANIMATION_UNSUPPORTED',
  ]),
  fatalStates: new Set([
    'FATAL', 'QUEUE_CREATE_FAILED', 'WRONG_WM_REQUEUE', 'ANIMATION_UNSUPPORTED',
  ]),
  exactKeys: Object.freeze({
    INVOKE: ['seq', 'phase', 'main', 'thread', 'tick'],
    ENQUEUED: ['seq', 'phase', 'main', 'thread', 'tick', 'ok'],
    TURN: ['seq', 'phase', 'main', 'thread', 'tick', 'same_wm', 'abort'],
    PENDING: ['seq', 'phase', 'main', 'thread', 'tick', 'yield'],
    FAILED_REASON: ['seq', 'phase', 'main', 'thread', 'tick', 'reason'],
    PREJOIN_ABORT: ['seq', 'phase', 'main', 'thread', 'tick', 'drain'],
    WORKER_RETURN: ['seq', 'phase', 'main', 'thread', 'tick', 'status'],
    QUEUE_DESTROY: ['seq', 'phase', 'main', 'thread', 'tick'],
  }),
});
const GPU_ERROR_RE = /GPU[- _]?ERROR|GPUValidationError|Dawn[^\n]*error|WGPU[^\n]*error|WebGPU[^\n]*error|ValidationError|validation error|uncaptured error|DeviceLost|device lost|RuntimeError|table index is out of bounds/i;

function sha256Bytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseAsyncLine(text, receivedAtMs = 0, consoleIndex = 0) {
  if (!text.startsWith(ASYNC.prefix)) return null;
  const fields = {};
  const errors = [];
  let bareState = null;
  for (const token of text.slice(ASYNC.prefix.length).trim().split(/\s+/)) {
    if (!token) continue;
    const split = token.indexOf('=');
    if (split < 0 && ASYNC.knownStates.has(token) && bareState === null) {
      bareState = token;
      continue;
    }
    if (split < 1 || split === token.length - 1) {
      errors.push(`malformed token ${token}`);
      continue;
    }
    const key = token.slice(0, split);
    const value = token.slice(split + 1);
    if (Object.hasOwn(fields, key)) errors.push(`duplicate key ${key}`);
    fields[key] = value;
  }
  const keyedState = [fields.state, fields.event].find((value) => ASYNC.knownStates.has(value));
  const state = bareState || keyedState ||
    (ASYNC.knownStates.has(fields.phase) ? fields.phase : null);
  if (bareState && keyedState && bareState !== keyedState) {
    errors.push(`conflicting state ${bareState}/${keyedState}`);
  }
  if (!state) errors.push('missing marker state');
  if (fields.seq && !/^\d+$/.test(fields.seq)) errors.push(`invalid seq ${fields.seq}`);
  if (fields.main && !/^[01]$/.test(fields.main)) errors.push(`invalid main ${fields.main}`);
  if (fields.thread && !/^\d+$/.test(fields.thread)) errors.push(`invalid thread ${fields.thread}`);
  if (fields.tick && !/^\d+$/.test(fields.tick)) errors.push(`invalid tick ${fields.tick}`);
  return { text, state, fields, receivedAtMs, consoleIndex, parseErrors: errors };
}

function requireExactKeys(event, keyClass, errors) {
  const actual = Object.keys(event.fields).sort();
  const expected = [...ASYNC.exactKeys[keyClass]].sort();
  if (actual.length !== expected.length ||
      actual.some((key, index) => key !== expected[index]))
  {
    errors.push(`${event.state}: keys=${actual.join(',')} expected=${expected.join(',')}`);
  }
}

function validateCanceledSequence(events, sequence, escapeConsoleCutoff, handlerCancelAdvanced) {
  const errors = [];
  const sequenceEvents = events.filter((event) => event.fields.seq === sequence);
  const states = sequenceEvents.map((event) => event.state);
  for (const event of sequenceEvents) {
    errors.push(...event.parseErrors.map((error) => `${event.state || '?'}: ${error}`));
    if (ASYNC.fatalStates.has(event.state)) errors.push(`${event.state} marker observed`);
  }
  if (!sequence || sequence === '0') errors.push(`invalid sequence ${sequence}`);
  if (states[0] !== 'INVOKE' || states[1] !== 'ENQUEUED') {
    errors.push(`sequence must start INVOKE>ENQUEUED; states=${states.join('>')}`);
  }
  const invoke = sequenceEvents[0]?.state === 'INVOKE' ? sequenceEvents[0] : null;
  const enqueued = sequenceEvents[1]?.state === 'ENQUEUED' ? sequenceEvents[1] : null;
  if (invoke) requireExactKeys(invoke, 'INVOKE', errors);
  if (enqueued) {
    requireExactKeys(enqueued, 'ENQUEUED', errors);
    if (enqueued.fields.ok !== '1') errors.push(`ENQUEUED: ok=${enqueued.fields.ok}`);
  }

  const preEscapePending = sequenceEvents.find((event) =>
    event.state === 'PENDING' && event.consoleIndex < escapeConsoleCutoff);
  if (!preEscapePending) errors.push('no PENDING yield observed before physical Escape');
  if (states.includes('READY') || states.includes('CONSUME') || states.includes('END_RESULT') ||
      states.includes('PIPELINE_TERMINAL'))
  {
    errors.push(`render reached success-only marker during cancel: ${states.join('>')}`);
  }

  for (let index = 0; index < sequenceEvents.length; index++) {
    const event = sequenceEvents[index];
    if (event.state === 'TURN') {
      requireExactKeys(event, 'TURN', errors);
      if (event.fields.same_wm !== '1' || !/^[01]$/.test(event.fields.abort || '')) {
        errors.push(`TURN: same_wm/abort=${event.fields.same_wm}/${event.fields.abort}`);
      }
    }
    else if (event.state === 'PENDING') {
      requireExactKeys(event, 'PENDING', errors);
      if (event.fields.yield !== 'timeout') errors.push(`PENDING: yield=${event.fields.yield}`);
      const prior = sequenceEvents[index - 1];
      if (prior?.state !== 'TURN' || prior.fields.tick !== event.fields.tick ||
          prior.fields.abort !== '0')
      {
        errors.push(`PENDING is not paired with a non-abort TURN at tick ${event.fields.tick}`);
      }
    }
    else if (event.state === 'FAILED') {
      requireExactKeys(event, 'FAILED_REASON', errors);
      if (!['abort', 'abort_after_turn'].includes(event.fields.reason)) {
        errors.push(`FAILED: unexpected reason=${event.fields.reason}`);
      }
    }
    else if (event.state === 'PREJOIN_ABORT') {
      requireExactKeys(event, 'PREJOIN_ABORT', errors);
      if (!/^[01]$/.test(event.fields.drain || '')) {
        errors.push(`PREJOIN_ABORT: drain=${event.fields.drain}`);
      }
    }
    else if (event.state === 'WORKER_RETURN') {
      requireExactKeys(event, 'WORKER_RETURN', errors);
      if (event.fields.status !== 'failed') {
        errors.push(`WORKER_RETURN: status=${event.fields.status}`);
      }
    }
    else if (event.state === 'QUEUE_DESTROY') {
      requireExactKeys(event, 'QUEUE_DESTROY', errors);
    }
  }

  const cancelEvents = sequenceEvents.filter((event) =>
    event.state === 'FAILED' || event.state === 'PREJOIN_ABORT');
  if (cancelEvents.some((event) => event.consoleIndex < escapeConsoleCutoff)) {
    errors.push('async cancellation preceded the physical Escape');
  }
  if (cancelEvents.length === 0 && !handlerCancelAdvanced) {
    errors.push('no FAILED/PREJOIN_ABORT marker or render_cancel terminal receipt');
  }
  const workerReturns = sequenceEvents.filter((event) => event.state === 'WORKER_RETURN');
  const queueDestroys = sequenceEvents.filter((event) => event.state === 'QUEUE_DESTROY');
  if (workerReturns.length !== 1) errors.push(`WORKER_RETURN count=${workerReturns.length}`);
  if (queueDestroys.length !== 1) errors.push(`QUEUE_DESTROY count=${queueDestroys.length}`);
  if (sequenceEvents.at(-1)?.state !== 'QUEUE_DESTROY') {
    errors.push(`QUEUE_DESTROY is not terminal; states=${states.join('>')}`);
  }
  const workerIndex = sequenceEvents.findIndex((event) => event.state === 'WORKER_RETURN');
  const destroyIndex = sequenceEvents.findIndex((event) => event.state === 'QUEUE_DESTROY');
  if (workerIndex < 0 || destroyIndex <= workerIndex) {
    errors.push(`terminal order is not WORKER_RETURN>QUEUE_DESTROY; states=${states.join('>')}`);
  }

  const wmThread = invoke?.fields.thread || null;
  const workerThread = enqueued?.fields.thread || null;
  if (!wmThread || wmThread === '0') errors.push(`invalid WM thread ${wmThread}`);
  if (!workerThread || workerThread === '0') errors.push(`invalid worker thread ${workerThread}`);
  if (wmThread && workerThread && wmThread === workerThread) {
    errors.push(`WM and worker threads are identical: ${wmThread}`);
  }
  for (const event of sequenceEvents) {
    const workerEvent = event.state === 'ENQUEUED' || event.state === 'WORKER_RETURN';
    const expectedMain = workerEvent ? '0' : '1';
    const expectedThread = workerEvent ? workerThread : wmThread;
    if (event.fields.main !== expectedMain || event.fields.thread !== expectedThread) {
      errors.push(`${event.state}: main/thread=${event.fields.main}/${event.fields.thread} expected ${expectedMain}/${expectedThread}`);
    }
  }
  const ticked = sequenceEvents.filter((event) => /^\d+$/.test(event.fields.tick || ''));
  for (let index = 1; index < ticked.length; index++) {
    if (BigInt(ticked[index].fields.tick) < BigInt(ticked[index - 1].fields.tick)) {
      errors.push(`${ticked[index].state} tick ${ticked[index].fields.tick} precedes ${ticked[index - 1].state} ${ticked[index - 1].fields.tick}`);
    }
  }
  return {
    ok: errors.length === 0,
    errors,
    sequence,
    states,
    wmThread,
    workerThread,
    pendingBeforeEscape: Boolean(preEscapePending),
    cancellationStates: cancelEvents.map((event) => event.state),
    handlerCancelAdvanced,
  };
}

function makePythonExpr() {
  return [
    'import bpy, os, json',
    `os.environ[${JSON.stringify(ASYNC.envKey)}] = ${JSON.stringify(ASYNC.envValue)}`,
    'bpy.context.preferences.view.show_splash = False',
    '_bw_er_scene = bpy.context.scene',
    '_bw_er_scene.render.engine = "BLENDER_EEVEE"',
    `_bw_er_scene.render.resolution_x = ${RENDER_WIDTH}`,
    `_bw_er_scene.render.resolution_y = ${RENDER_HEIGHT}`,
    '_bw_er_scene.render.resolution_percentage = 100',
    '_bw_er_scene.frame_set(1)',
    `_bw_er_config = ${JSON.stringify(CONFIG_GUEST)}`,
    `_bw_er_receipt = ${JSON.stringify(RECEIPT_GUEST)}`,
    '_bw_er_pre_count = 0',
    '_bw_er_complete_count = 0',
    '_bw_er_cancel_count = 0',
    'def _bw_er_write(path, obj):',
    '    tmp = path + ".tmp"',
    '    with open(tmp, "w") as f: json.dump(obj, f, sort_keys=True)',
    '    os.replace(tmp, path)',
    'def _bw_er_snapshot(event):',
    '    _bw_er_write(_bw_er_receipt, {"event":event, "pre_count":_bw_er_pre_count, "complete_count":_bw_er_complete_count, "cancel_count":_bw_er_cancel_count})',
    'def _bw_er_pre(*_args):',
    '    global _bw_er_pre_count',
    '    _bw_er_pre_count += 1',
    '    _bw_er_snapshot("render_pre")',
    '    print("BW_EEVEE_ESCAPE phase=RENDER_PRE count=%d" % _bw_er_pre_count)',
    'def _bw_er_complete(*_args):',
    '    global _bw_er_complete_count',
    '    _bw_er_complete_count += 1',
    '    _bw_er_snapshot("render_complete")',
    '    print("BW_EEVEE_ESCAPE phase=RENDER_COMPLETE count=%d" % _bw_er_complete_count)',
    'def _bw_er_cancel(*_args):',
    '    global _bw_er_cancel_count',
    '    _bw_er_cancel_count += 1',
    '    _bw_er_snapshot("render_cancel")',
    '    print("BW_EEVEE_ESCAPE phase=RENDER_CANCEL count=%d" % _bw_er_cancel_count)',
    'bpy.app.handlers.render_pre.append(_bw_er_pre)',
    'bpy.app.handlers.render_complete.append(_bw_er_complete)',
    'bpy.app.handlers.render_cancel.append(_bw_er_cancel)',
    '_bw_er_write(_bw_er_config, {"status":"ARMED", "engine":_bw_er_scene.render.engine, "resolution":[_bw_er_scene.render.resolution_x,_bw_er_scene.render.resolution_y], "blend":bpy.data.filepath, "async_env":os.environ.get(' + JSON.stringify(ASYNC.envKey) + ')})',
    '_bw_er_snapshot("armed")',
    'print("BW_EEVEE_ESCAPE phase=ARMED engine=%s" % _bw_er_scene.render.engine)',
  ].join('\n');
}

if (process.argv[2] === '--selfcheck') {
  const lines = [
    'phase=INVOKE seq=71 main=1 thread=11 tick=10',
    'phase=ENQUEUED seq=71 main=0 thread=22 tick=11 ok=1',
    'phase=TURN seq=71 main=1 thread=11 tick=12 same_wm=1 abort=0',
    'phase=PENDING seq=71 main=1 thread=11 tick=12 yield=timeout',
    'phase=PREJOIN_ABORT seq=71 main=1 thread=11 tick=13 drain=0',
    'phase=WORKER_RETURN seq=71 main=0 thread=22 tick=14 status=failed',
    'phase=QUEUE_DESTROY seq=71 main=1 thread=11 tick=15',
  ];
  const prejoinEvents = lines.map((line, index) =>
    parseAsyncLine(`${ASYNC.prefix}${line}`, index * 10, index));
  const prejoin = validateCanceledSequence(prejoinEvents, '71', 4, false);
  const failedEvents = [
    ...prejoinEvents.slice(0, 4),
    parseAsyncLine(`${ASYNC.prefix}phase=TURN seq=71 main=1 thread=11 tick=13 same_wm=1 abort=1`, 40, 4),
    parseAsyncLine(`${ASYNC.prefix}phase=FAILED seq=71 main=1 thread=11 tick=13 reason=abort`, 41, 5),
    ...prejoinEvents.slice(5).map((event, index) => ({
      ...event,
      consoleIndex: index + 6,
      receivedAtMs: 50 + index * 10,
    })),
  ];
  const failed = validateCanceledSequence(failedEvents, '71', 4, false);
  const missingTerminal = validateCanceledSequence(prejoinEvents.slice(0, -1), '71', 4, false);
  const wrongRealm = prejoinEvents.map((event) => ({ ...event, fields: { ...event.fields } }));
  wrongRealm.find((event) => event.state === 'TURN').fields.same_wm = '0';
  const wrong = validateCanceledSequence(wrongRealm, '71', 4, false);
  const pyexpr = makePythonExpr();
  const checks = [
    prejoin.ok,
    failed.ok,
    !missingTerminal.ok,
    !wrong.ok,
    !/bpy\.ops\./.test(pyexpr),
    !/WM_jobs|RE_Render|render_cancel\(/.test(pyexpr),
    pyexpr.includes('bpy.app.handlers.render_cancel.append(_bw_er_cancel)'),
    sha256Bytes(readFileSync(BLEND_HOST)) === '39db218041e5d1f8338a666f78e3d06d93f6e7cbd1029390c8e1c646c7ddea5a',
  ];
  if (checks.every(Boolean)) {
    console.log('SELF_CHECK_PASS probe=f12-eevee-escape physical_keys=F12,Escape,F12,Escape handler_role=passive sequences=fresh');
    process.exit(0);
  }
  console.error(`SELF_CHECK_FAIL probe=f12-eevee-escape prejoin=${JSON.stringify(prejoin.errors)} failed=${JSON.stringify(failed.errors)} missing=${JSON.stringify(missingTerminal.errors)} wrong=${JSON.stringify(wrong.errors)}`);
  process.exit(1);
}

const PORT = Number.parseInt(process.argv[2] || '8151', 10);
const STAGE_MS = Number.parseInt(process.argv[3] || String(DEFAULT_STAGE_MS), 10);
const LABEL = (process.argv[4] || 'eevee-f12-escape-recovery').trim();
if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) {
  console.error(`invalid port: ${process.argv[2] || ''}`);
  process.exit(2);
}
if (!Number.isInteger(STAGE_MS) || STAGE_MS < 2000) {
  console.error(`invalid stage_timeout_ms: ${process.argv[3] || ''}`);
  process.exit(2);
}
if (!/^[A-Za-z0-9._-]+$/.test(LABEL)) {
  console.error(`invalid label: ${LABEL}`);
  process.exit(2);
}

const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const base = `http://127.0.0.1:${PORT}`;
const pythonExpr = makePythonExpr();
if (/bpy\.ops\./.test(pythonExpr)) throw new Error('driver invariant violated: bpy operator in pyexpr');
const blendBytes = readFileSync(BLEND_HOST);
const blendSha256 = sha256Bytes(blendBytes);
const url = `${base}/windowed.html?gate=${WIDTH}x${HEIGHT}&args=${encodeURIComponent(BLEND_GUEST)}&pyexpr=${encodeURIComponent(pythonExpr)}`;
const prefix = `${OUTDIR}/${LABEL}`;
const consolePath = `${prefix}-console.log`;
const manifestPath = `${prefix}-manifest.json`;
const screenshotPath = `${prefix}-${WIDTH}x${HEIGHT}.png`;
mkdirSync(OUTDIR, { recursive: true });

const startedAt = Date.now();
const consoleEntries = [];
const asyncEvents = [];
const acceptLines = [];
const pageErrors = [];
const gpuErrors = [];
const marks = [];
const asyncWaiters = new Set();
let pageCrashed = false;
let runError = null;
let seedReceipt = null;
let configReceipt = null;
let gateReceipt = null;
let keyReceipt = null;
let firstReceipt = null;
let secondReceipt = null;
let firstTopology = null;
let secondTopology = null;
let screenshotSha256 = null;
let screenshotCaptured = false;

function elapsedMs() {
  return Date.now() - startedAt;
}

function mark(label, extra = {}) {
  const entry = { label, atMs: elapsedMs(), iso: new Date().toISOString(), ...extra };
  marks.push(entry);
  console.log(`[${entry.iso}] ${label}`);
}

function notifyAsyncWaiters(event) {
  for (const waiter of [...asyncWaiters]) {
    if (!waiter.predicate(event)) continue;
    asyncWaiters.delete(waiter);
    clearTimeout(waiter.timeout);
    waiter.resolve(event);
  }
}

function waitForAsyncEvent(predicate, label) {
  const existing = asyncEvents.find(predicate);
  if (existing) return Promise.resolve(existing);
  return new Promise((resolve, reject) => {
    const waiter = { predicate, resolve, timeout: null };
    waiter.timeout = setTimeout(() => {
      asyncWaiters.delete(waiter);
      reject(new Error(`${label} timeout after ${STAGE_MS} ms; states=${asyncEvents.map((event) => event.state).join('>')}`));
    }, STAGE_MS);
    asyncWaiters.add(waiter);
  });
}

async function readJsonIfPresent(page, path) {
  return page.evaluate((guestPath) => {
    try {
      return JSON.parse(window.__bwModule.FS.readFile(guestPath, { encoding: 'utf8' }));
    }
    catch (_) {
      return null;
    }
  }, path);
}

async function waitForJson(page, path, predicate, label) {
  const deadline = Date.now() + STAGE_MS;
  while (Date.now() < deadline) {
    const receipt = await readJsonIfPresent(page, path);
    if (receipt && predicate(receipt)) return receipt;
    await sleep(25);
  }
  throw new Error(`${label} timeout after ${STAGE_MS} ms`);
}

const browser = await chromium.launch({
  headless: false,
  args: ['--enable-unsafe-webgpu', '--use-angle=metal', '--disable-dev-tools'],
});
const context = await browser.newContext({
  viewport: { width: WIDTH + 120, height: HEIGHT + 120 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();

page.on('console', (message) => {
  const text = message.text();
  const index = consoleEntries.length;
  consoleEntries.push(`[${new Date().toISOString()}] [console:${message.type()}] ${text}`);
  const event = parseAsyncLine(text, elapsedMs(), index);
  if (event) {
    asyncEvents.push(event);
    notifyAsyncWaiters(event);
  }
  if (text.startsWith('BW_EEVEE_ESCAPE ')) acceptLines.push(text);
  const benignDeviceReceipt = /^\[bw\] WM-worker WebGPU device pre-acquired \(ADR-007\);/.test(text);
  const expectedMarker = text.startsWith(ASYNC.prefix) || text.startsWith('BW_EEVEE_ESCAPE ');
  if (!benignDeviceReceipt && !expectedMarker &&
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

try {
  mark('OPFS seed begin', { opfsName: OPFS_NAME, bytes: blendBytes.length, blendSha256 });
  await page.goto(`${base}/bin/bw_seed.html`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  seedReceipt = await page.evaluate(async ({ b64, name }) => {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
    const root = await navigator.storage.getDirectory();
    const handle = await root.getFileHandle(name, { create: true });
    const writable = await handle.createWritable();
    await writable.write(bytes);
    await writable.close();
    const file = await (await root.getFileHandle(name)).getFile();
    const stored = new Uint8Array(await file.arrayBuffer());
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', stored));
    return {
      ok: file.size === bytes.length,
      size: file.size,
      sha256: [...digest].map((byte) => byte.toString(16).padStart(2, '0')).join(''),
    };
  }, { b64: blendBytes.toString('base64'), name: OPFS_NAME });
  if (!seedReceipt.ok || seedReceipt.size !== blendBytes.length || seedReceipt.sha256 !== blendSha256) {
    throw new Error(`OPFS seed mismatch: ${JSON.stringify(seedReceipt)}`);
  }

  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
  await page.waitForFunction(
    () => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'),
    undefined,
    { timeout: BOOT_MS },
  );
  await page.waitForFunction(
    ({ width, height }) => {
      const canvas = document.querySelector('#canvas');
      if (!canvas) return false;
      const rect = canvas.getBoundingClientRect();
      return canvas.width === width && canvas.height === height &&
        Math.round(rect.width) === width && Math.round(rect.height) === height &&
        window.devicePixelRatio === 1 && document.body.classList.contains('bw-gate') &&
        window.crossOriginIsolated === true;
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
      dpr: window.devicePixelRatio,
      gateClass: document.body.classList.contains('bw-gate'),
      crossOriginIsolated: window.crossOriginIsolated,
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    };
  });
  configReceipt = await waitForJson(page, CONFIG_GUEST, (receipt) => receipt.status === 'ARMED', 'startup config');
  if (configReceipt.engine !== 'BLENDER_EEVEE' || configReceipt.blend !== BLEND_GUEST ||
      configReceipt.async_env !== ASYNC.envValue ||
      JSON.stringify(configReceipt.resolution) !== JSON.stringify([RENDER_WIDTH, RENDER_HEIGHT]))
  {
    throw new Error(`startup config invalid: ${JSON.stringify(configReceipt)}`);
  }

  const canvas = page.locator('#canvas');
  await page.bringToFront();
  await canvas.click({ position: { x: 32, y: 32 } });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(250);
  await canvas.click({ position: { x: 32, y: 32 } });
  await page.evaluate(() => {
    window.__bwEscapeRecoveryKeys = [];
    window.addEventListener('keydown', (event) => {
      if (event.key === 'F12' || event.code === 'F12' || event.key === 'Escape') {
        window.__bwEscapeRecoveryKeys.push({
          key: event.key,
          code: event.code,
          isTrusted: event.isTrusted,
          repeat: event.repeat,
          targetId: event.target?.id || null,
          activeId: document.activeElement?.id || null,
          at: performance.now(),
        });
      }
    }, { capture: true });
  });

  const firstPendingPromise = waitForAsyncEvent(
    (event) => event.state === 'PENDING' && event.fields.seq,
    'first PENDING');
  mark('first physical F12 dispatch');
  await page.keyboard.press('F12');
  const firstPending = await firstPendingPromise;
  const firstSequence = firstPending.fields.seq;
  const firstEscapeCutoff = consoleEntries.length;
  mark('first physical Escape dispatch after PENDING', { sequence: firstSequence });
  await page.keyboard.press('Escape');
  await waitForAsyncEvent(
    (event) => event.state === 'QUEUE_DESTROY' && event.fields.seq === firstSequence,
    'first QUEUE_DESTROY');
  firstReceipt = await waitForJson(
    page,
    RECEIPT_GUEST,
    (receipt) => receipt.cancel_count >= 1 || receipt.complete_count >= 1,
    'first render terminal handler');
  firstTopology = validateCanceledSequence(
    asyncEvents, firstSequence, firstEscapeCutoff, firstReceipt.cancel_count >= 1);
  if (!firstTopology.ok) {
    throw new Error(`first cancel topology invalid: ${firstTopology.errors.join('; ')}`);
  }
  mark('first cancel terminal and queue cleanup observed', {
    sequence: firstSequence,
    receipt: firstReceipt,
  });

  await page.waitForTimeout(250);
  await canvas.click({ position: { x: 32, y: 32 } });
  const secondPendingPromise = waitForAsyncEvent(
    (event) => event.state === 'PENDING' && event.fields.seq && event.fields.seq !== firstSequence,
    'second PENDING');
  mark('second physical F12 dispatch');
  await page.keyboard.press('F12');
  const secondPending = await secondPendingPromise;
  const secondSequence = secondPending.fields.seq;
  if (secondSequence === firstSequence) throw new Error(`continuation sequence reused: ${secondSequence}`);
  const secondEscapeCutoff = consoleEntries.length;
  mark('second render acquired fresh sequence; physical Escape cleanup', { sequence: secondSequence });
  await page.keyboard.press('Escape');
  await waitForAsyncEvent(
    (event) => event.state === 'QUEUE_DESTROY' && event.fields.seq === secondSequence,
    'second QUEUE_DESTROY');
  secondReceipt = await waitForJson(
    page,
    RECEIPT_GUEST,
    (receipt) => receipt.cancel_count >= 2 || receipt.complete_count >= 1,
    'second render terminal handler');
  secondTopology = validateCanceledSequence(
    asyncEvents, secondSequence, secondEscapeCutoff, secondReceipt.cancel_count > firstReceipt.cancel_count);
  if (!secondTopology.ok) {
    throw new Error(`second cancel topology invalid: ${secondTopology.errors.join('; ')}`);
  }

  keyReceipt = await page.evaluate(() => window.__bwEscapeRecoveryKeys || []);
  const expectedKeys = ['F12', 'Escape', 'F12', 'Escape'];
  if (keyReceipt.length !== expectedKeys.length || keyReceipt.some((event, index) =>
    event.key !== expectedKeys[index] || event.isTrusted !== true || event.repeat !== false ||
    event.targetId !== 'canvas' || event.activeId !== 'canvas'))
  {
    throw new Error(`physical key receipt invalid: ${JSON.stringify(keyReceipt)}`);
  }
  if (pageCrashed || pageErrors.length || gpuErrors.length) {
    throw new Error(`browser errors: crash=${pageCrashed} page=${JSON.stringify(pageErrors)} gpu=${JSON.stringify(gpuErrors)}`);
  }

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
  screenshotSha256 = sha256Bytes(readFileSync(screenshotPath));
  writeFileSync(`${screenshotPath}.license`, CC0);
  mark('second cancellation terminal; recovery proved', { firstSequence, secondSequence });
}
catch (error) {
  runError = error.stack || error.message || String(error);
  console.error(runError);
  if (!keyReceipt && !pageCrashed) {
    try {
      keyReceipt = await page.evaluate(() => window.__bwEscapeRecoveryKeys || []);
    }
    catch (_) {
      keyReceipt = null;
    }
  }
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
      screenshotSha256 = sha256Bytes(readFileSync(screenshotPath));
      writeFileSync(`${screenshotPath}.license`, CC0);
    }
    catch (captureError) {
      consoleEntries.push(`[${new Date().toISOString()}] [capture-error] ${captureError.stack || captureError}`);
    }
  }
}
finally {
  for (const waiter of asyncWaiters) {
    clearTimeout(waiter.timeout);
    waiter.resolve(null);
  }
  asyncWaiters.clear();
  await context.close();
  await browser.close();
}

const consoleText = `${consoleEntries.join('\n')}\n`;
writeFileSync(consolePath, consoleText);
writeFileSync(`${consolePath}.license`, CC0);
const exactGate = gateReceipt?.backingWidth === WIDTH && gateReceipt?.backingHeight === HEIGHT &&
  gateReceipt?.cssWidth === WIDTH && gateReceipt?.cssHeight === HEIGHT && gateReceipt?.dpr === 1 &&
  gateReceipt?.gateClass === true && gateReceipt?.crossOriginIsolated === true;
const keyPattern = keyReceipt?.length === 4 &&
  keyReceipt.map((event) => event.key).join('>') === 'F12>Escape>F12>Escape' &&
  keyReceipt.every((event) => event.isTrusted === true && event.repeat === false &&
    event.targetId === 'canvas' && event.activeId === 'canvas');
const accepted = !runError && !pageCrashed && pageErrors.length === 0 && gpuErrors.length === 0 &&
  exactGate && keyPattern && firstTopology?.ok === true && secondTopology?.ok === true &&
  firstTopology.sequence !== secondTopology.sequence && screenshotCaptured;
const manifest = {
  schema: 'blender-web.f12-eevee-escape-recovery.v1',
  verdict: accepted ? 'PASS' : 'FAIL',
  generatedAt: new Date().toISOString(),
  driver: { path: DRIVER_PATH, sha256: sha256Bytes(readFileSync(DRIVER_PATH)) },
  input: { hostPath: BLEND_HOST, guestPath: BLEND_GUEST, bytes: blendBytes.length, sha256: blendSha256 },
  server: { base, port: PORT, shell: 'platform_web/shell', bin: 'build-wasm-windowed-opt/bin' },
  browser: {
    engine: 'playwright-chromium',
    headed: true,
    args: ['--enable-unsafe-webgpu', '--use-angle=metal', '--disable-dev-tools'],
  },
  invocation: {
    methods: ['page.keyboard.press(F12)', 'page.keyboard.press(Escape)',
      'page.keyboard.press(F12)', 'page.keyboard.press(Escape)'],
    physicalTrustedKeys: Boolean(keyPattern),
    keyReceipt,
    bpyOperatorUsed: false,
    pythonExprSha256: sha256Bytes(pythonExpr),
    pythonRole: 'configure scene and record passive render handlers only',
  },
  asyncContract: {
    prefix: ASYNC.prefix.trim(),
    environment: { key: ASYNC.envKey, value: ASYNC.envValue },
    first: firstTopology,
    second: secondTopology,
    freshSequence: firstTopology?.sequence !== secondTopology?.sequence,
    events: asyncEvents.map((event) => ({
      line: event.text,
      state: event.state,
      fields: event.fields,
      receivedAtMs: event.receivedAtMs,
      consoleIndex: event.consoleIndex,
      parseErrors: event.parseErrors,
    })),
  },
  opfsSeed: seedReceipt,
  startupConfig: configReceipt,
  handlers: { firstReceipt, secondReceipt, acceptLines },
  gate: { expected: `${WIDTH}x${HEIGHT}@1`, receipt: gateReceipt, exact: Boolean(exactGate) },
  assertions: {
    physicalF12EscapeTwice: Boolean(keyPattern),
    firstCancelReachedTerminalWithoutHang: firstTopology?.ok === true,
    secondF12StartedWithFreshSequence: secondTopology?.ok === true &&
      firstTopology?.sequence !== secondTopology?.sequence,
    secondCleanupReachedTerminalWithoutHang: secondTopology?.ok === true,
    noReentrantPythonOperator: true,
    noGpuError: gpuErrors.length === 0,
    noPageError: pageErrors.length === 0,
    noPageCrash: !pageCrashed,
  },
  evidence: {
    console: { path: consolePath, sha256: sha256Bytes(consoleText), licensePath: `${consolePath}.license` },
    manifest: { path: manifestPath, licensePath: `${manifestPath}.license` },
    screenshot: {
      path: screenshotCaptured ? screenshotPath : null,
      sha256: screenshotSha256,
      licensePath: screenshotCaptured ? `${screenshotPath}.license` : null,
    },
  },
  failures: { runError, pageCrashed, pageErrors, gpuErrors },
  marks,
};
writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
writeFileSync(`${manifestPath}.license`, CC0);

if (!accepted) {
  console.error(`F12_EEVEE_ESCAPE_RECOVERY_FAIL manifest=${manifestPath} console=${consolePath}`);
  process.exit(1);
}
console.log(`F12_EEVEE_ESCAPE_RECOVERY_PASS manifest=${manifestPath} screenshot=${screenshotPath}`);
