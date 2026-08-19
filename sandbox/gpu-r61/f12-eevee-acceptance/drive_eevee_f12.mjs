// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Physical-F12 EEVEE acceptance rig. The .blend is seeded into OPFS and opened
// by Blender's startup argv, so no live open_mainfile can perturb GPU state.
// Python configures the already-loaded scene and installs passive render
// handlers; only Playwright's one trusted F12 event invokes the render.
//
// Start the normal COOP/COEP server separately, then run from the repo root:
//   BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin \
//   BLENDER_WEB_SHELL=$PWD/platform_web/shell \
//     /opt/homebrew/bin/bash scripts/serve-web.sh 8151
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   BW_EEVEE_PRODUCT_SMOKE=1 \
//     node sandbox/gpu-r61/f12-eevee-acceptance/drive_eevee_f12.mjs \
//       [port] [timeout_ms] [label]
// Add BW_EEVEE_CANONICAL_PROBES=1 to the driver command to reproduce the
// upstream SPHERE/VOLUME/ACTIVE-bake setup before the trusted F12 dispatch.
// BW_EEVEE_RENDER_SAMPLES_OVERRIDE=N is a product/no-probe diagnostic only;
// it never relaxes or replaces the default 64-sample comparator acceptance.
//
// This is a browser/evidence driver only. It does not patch or build Blender.

import { spawnSync } from 'child_process';
import { createHash } from 'crypto';
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'fs';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';

const ROOT = '/Users/paws/blender-web';
const DRIVER_PATH = fileURLToPath(import.meta.url);
const OUTDIR = `${ROOT}/sandbox/gpu-r61/f12-eevee-acceptance/evidence`;
const BLEND_HOST = `${ROOT}/upstream/tests/files/render/principled_bsdf/principled_bsdf_default.blend`;
const GOLDEN_HOST = `${ROOT}/sandbox/m6-prep/goldens/eevee/principled_bsdf/principled_bsdf_default.png`;
const OPFS_NAME = 'bw_f12_eevee_principled_default.blend';
const BLEND_GUEST = `/projects/${OPFS_NAME}`;
const PNG_GUEST = '/tmp/bw_f12_eevee_render.png';
const CONFIG_GUEST = '/tmp/bw_f12_eevee_config.json';
const PRE_GUEST = '/tmp/bw_f12_eevee_pre.json';
const DONE_GUEST = '/tmp/bw_f12_eevee_done.json';
const PROBE_GUEST = '/tmp/bw_f12_eevee_probe.json';
const BAKED_BLEND_GUEST = '/tmp/bw_f12_eevee_browser_baked.blend';
const WIDTH = 1280;
const HEIGHT = 720;
const RENDER_WIDTH = 128;
const RENDER_HEIGHT = 128;
const BOOT_MS = 300000;
const DEFAULT_RENDER_MS = 300000;
const DEFAULT_PROBE_MS = 30000;
const HEARTBEAT_MS = 40;
const FAIL_THRESHOLD = '0.0156862745';
const FAIL_PERCENT = '0.09';
const MIN_COMPUTE_WORKGROUP_STORAGE_SIZE = 32768;
const MIN_COLOR_ATTACHMENT_BYTES_PER_SAMPLE = 36;
const EEVEE_SETUP_SCHEMA = 'blender-web.eevee-passive-upstream-setup.v1';
const CANONICAL_PROBE_SCHEMA = 'blender-web.eevee-canonical-probe-setup.v2';
const EEVEE_TEST_SCRIPT_HOST = `${ROOT}/upstream/tests/python/eevee_render_tests.py`;
const WGPU_PREINIT_PREFIX = '[bw] WM-worker WebGPU device pre-acquired (ADR-007);';
const PRODUCT_MODE = process.env.BW_EEVEE_PRODUCT_SMOKE === '1';
const CANONICAL_PROBES = process.env.BW_EEVEE_CANONICAL_PROBES === '1';
const EXPORT_BAKED_BLEND = process.env.BW_EEVEE_EXPORT_BAKED_BLEND === '1';
const PROBE_BAKE_SAMPLES_OVERRIDE_RAW = process.env.BW_EEVEE_PROBE_BAKE_SAMPLES_OVERRIDE;
const PROBE_BAKE_SAMPLES_OVERRIDE = /^\d+$/.test(PROBE_BAKE_SAMPLES_OVERRIDE_RAW || '') ?
  Number.parseInt(PROBE_BAKE_SAMPLES_OVERRIDE_RAW, 10) : null;
const PROBE_BAKE_DIAGNOSTIC_MODE = PROBE_BAKE_SAMPLES_OVERRIDE_RAW !== undefined;
const EXPECTED_PROBE_BAKE_SAMPLES = PROBE_BAKE_SAMPLES_OVERRIDE ?? 128;
const RENDER_SAMPLES_OVERRIDE_RAW = process.env.BW_EEVEE_RENDER_SAMPLES_OVERRIDE;
const RENDER_SAMPLES_OVERRIDE = /^\d+$/.test(RENDER_SAMPLES_OVERRIDE_RAW || '') ?
  Number.parseInt(RENDER_SAMPLES_OVERRIDE_RAW, 10) : null;
const SAMPLE_DIAGNOSTIC_MODE = RENDER_SAMPLES_OVERRIDE_RAW !== undefined;
const EXPECTED_RENDER_SAMPLES = RENDER_SAMPLES_OVERRIDE ?? 64;
const EXPECTED_VIEW_TRANSFORM = 'Standard';
const EXPECTED_COLOR_MODE = 'RGB';
const PROBE_MS = Number.parseInt(
  process.env.BW_EEVEE_CANONICAL_PROBE_TIMEOUT_MS || String(DEFAULT_PROBE_MS), 10);
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
  boot: `${ROOT}/platform_web/shell/boot-windowed.js`,
  fileBridge: `${ROOT}/platform_web/shell/file-bridge.js`,
  preinit: `${ROOT}/platform_web/shell/wgpu-preinit-worker.js`,
});
const OIIOTOOL = process.env.OIIOTOOL || '/opt/homebrew/bin/oiiotool';
const READBACK_CAPTURE = process.env.BW_READBACK_CAPTURE === '1';
const EEVEE_INPUT_CAPTURE = process.env.BW_EEVEE_INPUT_CAPTURE === '1';
const EEVEE_FILM_TRANSPARENT = process.env.BW_EEVEE_FILM_TRANSPARENT === '1';
const EEVEE_PASS_CAPTURE = process.env.BW_EEVEE_PASS_CAPTURE === '1';
const EEVEE_DEPTH_ALWAYS_DIAG = process.env.BW_EEVEE_DEPTH_ALWAYS_DIAG === '1';
const STRIPPED_DIAGNOSTIC_ENV_KEYS = Object.freeze([
  'BW_F12_ASYNC_PROBE',
  'BW_READBACK_CAPTURE',
  'BW_EEVEE_INPUT_CAPTURE',
  'BW_EEVEE_PASS_CAPTURE',
  'BW_EEVEE_DEPTH_ALWAYS_DIAG',
]);
const CC0 =
  'SPDX-FileCopyrightText: 2026 blender-web contributors\n' +
  'SPDX-License-Identifier: CC0-1.0\n';

/*
 * Production marker contract. Keep this as the one schema-edit seam when the
 * BW_F12_ASYNC producer freezes. The parser accepts tokens independent of print
 * order, while validateAsync enforces the root-confirmed live semantic grammar,
 * exact field sets, WM/worker identity, and terminal cleanup.
 */
const ASYNC = Object.freeze({
  prefix: 'BW_F12_ASYNC ',
  envKey: 'BW_F12_ASYNC_PROBE',
  envValue: '1',
  schemaStatus: 'LIVE_SEMANTIC_ORDER_ROOT_CONFIRMED',
  successGrammar:
    'INVOKE>ENQUEUED(ok=1)>[TURN>PENDING(yield=timeout)]+>TURN>CONSUME>END_RESULT>[WRITE]?>PIPELINE_TERMINAL>READY>WORKER_RETURN>QUEUE_DESTROY',
  failureStates: new Set([
    'FAILED', 'FATAL', 'QUEUE_CREATE_FAILED', 'WRONG_WM_REQUEUE', 'PREJOIN_ABORT',
    'ANIMATION_UNSUPPORTED',
  ]),
  knownStates: new Set([
    'INVOKE', 'QUEUE_CREATE_FAILED', 'ENQUEUED', 'PENDING', 'TURN', 'READY', 'FAILED',
    'FATAL', 'WRONG_WM_REQUEUE', 'CONSUME', 'END_RESULT', 'WRITE', 'PIPELINE_TERMINAL',
    'WORKER_RETURN', 'PREJOIN_ABORT', 'QUEUE_DESTROY', 'ANIMATION_UNSUPPORTED',
  ]),
  exactKeys: Object.freeze({
    INVOKE: ['seq', 'phase', 'main', 'thread', 'tick'],
    ENQUEUED: ['seq', 'phase', 'main', 'thread', 'tick', 'ok'],
    TURN: ['seq', 'phase', 'main', 'thread', 'tick', 'same_wm', 'abort'],
    PENDING_YIELD: ['seq', 'phase', 'main', 'thread', 'tick', 'yield'],
    CONSUME: ['phase', 'status'],
    END_RESULT: ['phase', 'status'],
    WRITE: ['phase', 'frame', 'status'],
    PIPELINE_TERMINAL: ['phase', 'frame', 'status'],
    READY: ['seq', 'phase', 'main', 'thread', 'tick', 'terminal'],
    WORKER_RETURN: ['seq', 'phase', 'main', 'thread', 'tick', 'status'],
    QUEUE_DESTROY: ['seq', 'phase', 'main', 'thread', 'tick'],
  }),
  terminalState: 'QUEUE_DESTROY',
});
const GPU_ERROR_RE = /GPU[- _]?ERROR|GPUValidationError|Dawn[^\n]*error|WGPU[^\n]*error|WebGPU[^\n]*error|ValidationError|validation error|uncaptured error|DeviceLost|device lost|Aborted|abort\(|RuntimeError|table index is out of bounds/i;

function sha256Bytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function localShellReceipts() {
  return Object.fromEntries(Object.entries(SHELL_PATHS).map(([name, path]) => {
    const bytes = readFileSync(path);
    return [name, {path, bytes: bytes.length, sha256: sha256Bytes(bytes)}];
  }));
}

async function captureServedShell(page, expected) {
  const served = await page.evaluate(async () => {
    const paths = {index: '/index.html', windowed: '/windowed.html', boot: '/boot-windowed.js',
      fileBridge: '/file-bridge.js', preinit: '/wgpu-preinit-worker.js'};
    const result = {};
    for (const [name, path] of Object.entries(paths)) {
      const response = await fetch(path, {cache: 'no-store'});
      if (!response.ok) throw new Error(`served shell fetch failed: ${path} status=${response.status}`);
      const bytes = new Uint8Array(await response.arrayBuffer());
      const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
      result[name] = {url: new URL(path, location.href).href, bytes: bytes.length,
        sha256: [...digest].map((byte) => byte.toString(16).padStart(2, '0')).join('')};
    }
    return result;
  });
  for (const [name, local] of Object.entries(expected)) {
    if (served?.[name]?.bytes !== local.bytes || served?.[name]?.sha256 !== local.sha256) {
      throw new Error(`served shell differs from local ${name}`);
    }
  }
  return served;
}

function elapsedMs(startedAt) {
  return Date.now() - startedAt;
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

function validateAsync(events, heartbeats) {
  const errors = [];
  for (const event of events) {
    errors.push(...event.parseErrors.map((error) => `${event.state || '?'}: ${error}`));
  }
  const actualStates = events.map((event) => event.state);
  for (const failureState of ASYNC.failureStates) {
    if (actualStates.includes(failureState)) errors.push(`${failureState} marker observed`);
  }
  for (const event of events) {
    if (event.fields.status === 'failed') errors.push(`${event.state}: status=failed`);
  }
  let cursor = 0;
  const take = (state) => {
    const event = events[cursor];
    if (!event || event.state !== state) {
      errors.push(`expected ${state} at ${cursor}; states=${actualStates.join('>')}`);
      return null;
    }
    cursor += 1;
    return event;
  };

  const invoke = take('INVOKE');
  const enqueued = take('ENQUEUED');
  if (invoke) requireExactKeys(invoke, 'INVOKE', errors);
  if (enqueued) {
    requireExactKeys(enqueued, 'ENQUEUED', errors);
    if (enqueued.fields.ok !== '1') errors.push(`ENQUEUED: ok=${enqueued.fields.ok}`);
  }

  const yieldPairs = [];
  while (events[cursor]?.state === 'TURN' && events[cursor + 1]?.state === 'PENDING' &&
         events[cursor + 1]?.fields.yield === 'timeout')
  {
    const turn = take('TURN');
    const pending = take('PENDING');
    requireExactKeys(turn, 'TURN', errors);
    requireExactKeys(pending, 'PENDING_YIELD', errors);
    yieldPairs.push({ turn, pending });
  }
  if (yieldPairs.length === 0) errors.push('no TURN/PENDING(yield=timeout) pair observed');

  const finalTurn = take('TURN');
  if (finalTurn) requireExactKeys(finalTurn, 'TURN', errors);
  const consume = take('CONSUME');
  const endResult = take('END_RESULT');
  if (consume) requireExactKeys(consume, 'CONSUME', errors);
  if (endResult) requireExactKeys(endResult, 'END_RESULT', errors);
  let write = null;
  if (events[cursor]?.state === 'WRITE') {
    write = take('WRITE');
    requireExactKeys(write, 'WRITE', errors);
  }
  const pipeline = take('PIPELINE_TERMINAL');
  const ready = take('READY');
  const workerReturn = take('WORKER_RETURN');
  const queueDestroy = take('QUEUE_DESTROY');
  if (pipeline) requireExactKeys(pipeline, 'PIPELINE_TERMINAL', errors);
  if (ready) requireExactKeys(ready, 'READY', errors);
  if (workerReturn) requireExactKeys(workerReturn, 'WORKER_RETURN', errors);
  if (queueDestroy) requireExactKeys(queueDestroy, 'QUEUE_DESTROY', errors);
  if (cursor !== events.length) {
    errors.push(`unexpected trailing markers at ${cursor}: ${actualStates.slice(cursor).join('>')}`);
  }

  const wmThread = invoke?.fields.thread || null;
  const sequence = invoke?.fields.seq || null;
  const workerThread = enqueued?.fields.thread || null;
  if (!sequence || sequence === '0') errors.push(`invalid sequence identity ${sequence}`);
  if (!wmThread || wmThread === '0') errors.push(`invalid WM thread ${wmThread}`);
  if (!workerThread || workerThread === '0') errors.push(`invalid worker thread ${workerThread}`);
  if (wmThread && workerThread && wmThread === workerThread) {
    errors.push(`WM and worker threads are identical: ${wmThread}`);
  }

  const wmEvents = [invoke, ...yieldPairs.flatMap((pair) => [pair.turn, pair.pending]),
    finalTurn, ready, queueDestroy].filter(Boolean);
  for (const event of wmEvents) {
    if (event.fields.seq !== sequence || event.fields.main !== '1' ||
        event.fields.thread !== wmThread)
    {
      errors.push(`${event.state}: WM identity seq/main/thread=${event.fields.seq}/${event.fields.main}/${event.fields.thread} expected ${sequence}/1/${wmThread}`);
    }
  }
  for (const event of [enqueued, workerReturn].filter(Boolean)) {
    if (event.fields.seq !== sequence || event.fields.main !== '0' ||
        event.fields.thread !== workerThread)
    {
      errors.push(`${event.state}: worker identity seq/main/thread=${event.fields.seq}/${event.fields.main}/${event.fields.thread} expected ${sequence}/0/${workerThread}`);
    }
  }
  for (const turn of [...yieldPairs.map((pair) => pair.turn), finalTurn].filter(Boolean)) {
    if (turn.fields.same_wm !== '1' || turn.fields.abort !== '0') {
      errors.push(`TURN: same_wm/abort=${turn.fields.same_wm}/${turn.fields.abort}`);
    }
  }
  for (const pair of yieldPairs) {
    if (pair.pending.fields.yield !== 'timeout') errors.push(`PENDING: yield=${pair.pending.fields.yield}`);
    if (pair.turn.fields.tick !== pair.pending.fields.tick) {
      errors.push(`TURN/PENDING ticks differ: ${pair.turn.fields.tick}/${pair.pending.fields.tick}`);
    }
  }
  if (write && (write.fields.frame !== '1' || write.fields.status !== 'complete')) {
    errors.push(`WRITE: frame/status=${write.fields.frame}/${write.fields.status}`);
  }
  if (consume?.fields.status !== 'complete') {
    errors.push(`CONSUME: status=${consume?.fields.status}`);
  }
  if (endResult?.fields.status !== 'complete') {
    errors.push(`END_RESULT: status=${endResult?.fields.status}`);
  }
  if (pipeline && (pipeline.fields.frame !== '1' || pipeline.fields.status !== 'complete')) {
    errors.push(`PIPELINE_TERMINAL: frame/status=${pipeline.fields.frame}/${pipeline.fields.status}`);
  }
  if (ready?.fields.terminal !== '1') errors.push(`READY: terminal=${ready?.fields.terminal}`);
  if (workerReturn?.fields.status !== 'complete') {
    errors.push(`WORKER_RETURN: status=${workerReturn?.fields.status}`);
  }
  if (finalTurn && ready && finalTurn.fields.tick !== ready.fields.tick) {
    errors.push(`final TURN/READY ticks differ: ${finalTurn.fields.tick}/${ready.fields.tick}`);
  }

  const tickedEvents = events.filter((event) => /^\d+$/.test(event.fields.tick || ''));
  for (let index = 1; index < tickedEvents.length; index++) {
    if (BigInt(tickedEvents[index].fields.tick) < BigInt(tickedEvents[index - 1].fields.tick)) {
      errors.push(`${tickedEvents[index].state} tick ${tickedEvents[index].fields.tick} precedes ${tickedEvents[index - 1].state} ${tickedEvents[index - 1].fields.tick}`);
    }
  }

  let uiHeartbeat = null;
  if (enqueued && yieldPairs[0]) {
    const firstTurn = yieldPairs[0].turn;
    uiHeartbeat = heartbeats.find((sample) =>
      sample.atMs > enqueued.receivedAtMs && sample.atMs < firstTurn.receivedAtMs &&
      /^\d+$/.test(sample.tick || '')) || null;
  }

  return {
    ok: errors.length === 0,
    errors,
    actualStates,
    sequence,
    wmThread,
    workerThread,
    yieldPairCount: yieldPairs.length,
    optionalWrite: Boolean(write),
    uiHeartbeat,
    gpuWorkIdentity: pipeline && finalTurn && ready ? {
      inferredWmThread: wmThread,
      enclosingTurnTick: finalTurn.fields.tick,
      readyTick: ready.fields.tick,
    } : null,
  };
}

function makePythonExpr({
  productMode = PRODUCT_MODE,
  readbackCapture = READBACK_CAPTURE,
  eeveeInputCapture = EEVEE_INPUT_CAPTURE,
  eeveePassCapture = EEVEE_PASS_CAPTURE,
  eeveeDepthAlwaysDiag = EEVEE_DEPTH_ALWAYS_DIAG,
  canonicalProbes = CANONICAL_PROBES,
  probeBakeSamples = EXPECTED_PROBE_BAKE_SAMPLES,
  renderSamplesOverride = SAMPLE_DIAGNOSTIC_MODE ? RENDER_SAMPLES_OVERRIDE : null,
} = {}) {
  if (canonicalProbes && !productMode) {
    throw new Error('BW_EEVEE_CANONICAL_PROBES requires BW_EEVEE_PRODUCT_SMOKE');
  }
  if (renderSamplesOverride !== null &&
      (!Number.isSafeInteger(renderSamplesOverride) || renderSamplesOverride < 1))
  {
    throw new Error('BW_EEVEE_RENDER_SAMPLES_OVERRIDE must be a positive integer');
  }
  if (renderSamplesOverride !== null && !productMode) {
    throw new Error('BW_EEVEE_RENDER_SAMPLES_OVERRIDE requires BW_EEVEE_PRODUCT_SMOKE');
  }
  if (renderSamplesOverride !== null && canonicalProbes) {
    throw new Error('BW_EEVEE_RENDER_SAMPLES_OVERRIDE diagnostic requires canonical probes off');
  }
  if (!Number.isSafeInteger(probeBakeSamples) || probeBakeSamples < 1) {
    throw new Error('BW_EEVEE_PROBE_BAKE_SAMPLES_OVERRIDE must be a positive integer');
  }
  if (productMode &&
      (readbackCapture || eeveeInputCapture || eeveePassCapture || eeveeDepthAlwaysDiag))
  {
    throw new Error('BW_EEVEE_PRODUCT_SMOKE forbids stripped diagnostic environment flags');
  }
  return [
    'import bpy, os, json, struct, math, hashlib, time',
    ...(productMode ? [] : [
      `os.environ[${JSON.stringify(ASYNC.envKey)}] = ${JSON.stringify(ASYNC.envValue)}`,
      ...(readbackCapture ? ['os.environ["BW_READBACK_CAPTURE"] = "1"'] : []),
      ...(eeveeInputCapture ? ['os.environ["BW_EEVEE_INPUT_CAPTURE"] = "1"'] : []),
      ...(eeveePassCapture ? ['os.environ["BW_EEVEE_PASS_CAPTURE"] = "1"'] : []),
      ...(eeveeDepthAlwaysDiag ? ['os.environ["BW_EEVEE_DEPTH_ALWAYS_DIAG"] = "1"'] : []),
    ]),
    'bpy.context.preferences.view.show_splash = False',
    '_bw_ea_scene = bpy.context.scene',
    '_bw_ea_scene.render.engine = "BLENDER_EEVEE"',
    `_bw_ea_scene.render.resolution_x = ${RENDER_WIDTH}`,
    `_bw_ea_scene.render.resolution_y = ${RENDER_HEIGHT}`,
    '_bw_ea_scene.render.resolution_percentage = 100',
    ...(renderSamplesOverride === null ? [] : [
      `bpy.context.view_layer.samples = ${renderSamplesOverride}`,
    ]),
    '_bw_ea_scene.render.image_settings.file_format = "PNG"',
    `_bw_ea_scene.render.image_settings.color_mode = ${JSON.stringify(EXPECTED_COLOR_MODE)}`,
    /* Passive parity with tests/python/eevee_render_tests.py::setup. Probe creation and baking
     * are intentionally excluded: they are operators, while this rig reserves the one render
     * invocation for Playwright's trusted physical F12. Existing probe data remains untouched. */
    '_bw_ea_skip_hair = bool(_bw_ea_scene.get("EEVEE_skip_hair_setup", False))',
    '_bw_ea_skip_probes = bool(_bw_ea_scene.get("EEVEE_skip_probes_setup", False))',
    '_bw_ea_skip_raytracing = bool(_bw_ea_scene.get("EEVEE_skip_raytracing_setup", False))',
    '_bw_ea_skip_shadow = bool(_bw_ea_scene.get("EEVEE_skip_shadow_setup", False))',
    '_bw_ea_skip_subsurface = bool(_bw_ea_scene.get("EEVEE_skip_subsurface_setup", False))',
    '_bw_ea_eevee = _bw_ea_scene.eevee',
    '_bw_ea_eevee.use_overscan = True',
    '_bw_ea_eevee.overscan_size = 50.0',
    'for _bw_ea_layer in _bw_ea_scene.view_layers:',
    '    _bw_ea_layer.eevee.ambient_occlusion_distance = 1',
    '_bw_ea_eevee.light_threshold = 0.001',
    'if not _bw_ea_skip_hair:',
    '    _bw_ea_scene.render.hair_type = "STRIP"',
    'if not _bw_ea_skip_shadow:',
    '    _bw_ea_eevee.shadow_step_count = 16',
    '    _bw_ea_eevee.shadow_pool_size = "1024"',
    '_bw_ea_eevee.volumetric_tile_size = "2"',
    '_bw_ea_eevee.volumetric_start = 1.0',
    '_bw_ea_eevee.volumetric_end = 50.0',
    '_bw_ea_eevee.volumetric_samples = 128',
    '_bw_ea_eevee.use_volumetric_shadows = True',
    '_bw_ea_eevee.clamp_volume_indirect = 0.0',
    'if _bw_ea_scene.render.use_motion_blur:',
    '    _bw_ea_eevee.motion_blur_steps = 10',
    'if not _bw_ea_skip_raytracing:',
    '    _bw_ea_eevee.use_raytracing = True',
    '    _bw_ea_eevee.ray_tracing_method = "SCREEN"',
    '    _bw_ea_ray_options = _bw_ea_eevee.ray_tracing_options',
    '    _bw_ea_ray_options.resolution_scale = "1"',
    '    _bw_ea_ray_options.screen_trace_quality = 1.0',
    '    _bw_ea_ray_options.screen_trace_thickness = 1.0',
    '    _bw_ea_eevee.fast_gi_quality = 0.8',
    'if not _bw_ea_skip_probes:',
    '    _bw_ea_eevee.gi_cubemap_resolution = "256"',
    '_bw_ea_eevee.direct_light_intensity = 1.0',
    '_bw_ea_eevee.indirect_light_intensity = 1.0',
    '_bw_ea_shadow_light_count = 0',
    '_bw_ea_probe_hidden_count = 0',
    '_bw_ea_thickness_materials = set()',
    'for _bw_ea_object in _bw_ea_scene.objects:',
    '    if _bw_ea_object.type == "LIGHT" and not _bw_ea_skip_shadow:',
    '        _bw_ea_object.data.shadow_maximum_resolution = 0.0',
    '        _bw_ea_shadow_light_count += 1',
    '    if _bw_ea_object.name != "Plane" and _bw_ea_object.type != "LIGHT" and not _bw_ea_skip_probes:',
    '        _bw_ea_object.hide_probe_volume = True',
    '        _bw_ea_object.hide_probe_sphere = True',
    '        _bw_ea_probe_hidden_count += 1',
    '    if not _bw_ea_skip_subsurface:',
    '        for _bw_ea_slot in _bw_ea_object.material_slots:',
    '            if _bw_ea_slot.material:',
    '                _bw_ea_slot.material.thickness_mode = "SPHERE"',
    '                _bw_ea_thickness_materials.add(_bw_ea_slot.material.name)',
    ...(canonicalProbes ? [
      `_bw_ea_probe_path = ${JSON.stringify(PROBE_GUEST)}`,
      `_bw_ea_probe_schema = ${JSON.stringify(CANONICAL_PROBE_SCHEMA)}`,
      '_bw_ea_probe_operators_used = False',
      '_bw_ea_probe_receipt = {"schema":_bw_ea_probe_schema,"requested":True,"state":"PENDING","skip_probes":_bw_ea_skip_probes,"context_mode":bpy.context.mode,"operators_used":False}',
      'def _bw_ea_probe_write():',
      '    _bw_ea_probe_tmp = _bw_ea_probe_path + ".tmp"',
      '    with open(_bw_ea_probe_tmp, "w") as _bw_ea_probe_file: json.dump(_bw_ea_probe_receipt, _bw_ea_probe_file, sort_keys=True)',
      '    os.replace(_bw_ea_probe_tmp, _bw_ea_probe_path)',
      '_bw_ea_probe_write()',
      'try:',
      '    if bpy.data.objects.get("Volume_Probe_Baked") is not None:',
      '        _bw_ea_probe_existing = bpy.data.objects.get("Volume_Probe_Baked")',
      '        _bw_ea_probe_receipt.update({"state":"PREEXISTING","existing_object":_bw_ea_probe_existing.name,"existing_type":_bw_ea_probe_existing.data.type,"bake_result":None})',
      ...(EXPORT_BAKED_BLEND ? [
        `        _bw_ea_baked_blend_path = ${JSON.stringify(BAKED_BLEND_GUEST)}`,
        '        _bw_ea_save_result = sorted(bpy.ops.wm.save_as_mainfile(filepath=_bw_ea_baked_blend_path, check_existing=False, copy=True))',
        '        if _bw_ea_save_result != ["FINISHED"]: raise RuntimeError("browser-baked blend export did not finish")',
        '        _bw_ea_probe_receipt.update({"baked_blend_path":_bw_ea_baked_blend_path,"baked_blend_size":os.path.getsize(_bw_ea_baked_blend_path),"save_result":_bw_ea_save_result})',
      ] : []),
      '        _bw_ea_probe_write()',
      '    elif bpy.context.mode == "OBJECT" and not _bw_ea_skip_probes:',
      '        _bw_ea_probe_receipt["state"] = "CREATING_SPHERE"',
      '        _bw_ea_probe_write()',
      "        bpy.ops.object.lightprobe_add(type='SPHERE', location=(0.0, 0.1, 1.0))",
      '        _bw_ea_probe_operators_used = True',
      '        cubemap = bpy.context.selected_objects[0]',
      '        cubemap.scale = (5.0, 5.0, 2.0)',
      '        cubemap.data.falloff = 0.0',
      '        cubemap.data.clip_start = 0.8',
      '        cubemap.data.influence_distance = 1.2',
      '        _bw_ea_probe_receipt["state"] = "CREATING_VOLUME"',
      '        _bw_ea_probe_write()',
      "        bpy.ops.object.lightprobe_add(type='VOLUME', location=(0.0, 0.0, 2.0))",
      '        grid = bpy.context.selected_objects[0]',
      '        grid.scale = (8.0, 4.5, 4.5)',
      '        grid.data.resolution_x = 32',
      '        grid.data.resolution_y = 16',
      '        grid.data.resolution_z = 8',
      `        grid.data.bake_samples = ${probeBakeSamples}`,
      '        grid.data.capture_world = True',
      '        grid.data.surfel_density = 100',
      '        grid.data.dilation_threshold = 1.0',
      '        _bw_ea_probe_receipt.update({"state":"BAKING_ACTIVE","operators_used":True,"sphere":{"name":cubemap.name,"type":cubemap.data.type,"location":list(cubemap.location),"scale":list(cubemap.scale),"falloff":cubemap.data.falloff,"clip_start":cubemap.data.clip_start,"influence_distance":cubemap.data.influence_distance},"volume":{"name":grid.name,"type":grid.data.type,"location":list(grid.location),"scale":list(grid.scale),"resolution":[grid.data.resolution_x,grid.data.resolution_y,grid.data.resolution_z],"bake_samples":grid.data.bake_samples,"capture_world":grid.data.capture_world,"surfel_density":grid.data.surfel_density,"dilation_threshold":grid.data.dilation_threshold},"active_object":bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None})',
      '        _bw_ea_probe_write()',
      "        _bw_ea_probe_bake_result = sorted(bpy.ops.object.lightprobe_cache_bake(subset='ACTIVE'))",
      '        if _bw_ea_probe_bake_result != ["RUNNING_MODAL"]:',
      '            _bw_ea_probe_receipt.update({"state":"FAILED","bake_result":_bw_ea_probe_bake_result,"error":"WebGPU ACTIVE lightprobe cache bake did not enter RUNNING_MODAL"})',
      '            _bw_ea_probe_write()',
      '            raise RuntimeError(_bw_ea_probe_receipt["error"])',
      `        _bw_ea_probe_timeout_s = ${PROBE_MS} / 1000.0`,
      '        _bw_ea_probe_started = time.monotonic()',
      '        _bw_ea_probe_receipt.update({"state":"BAKING_MODAL","bake_result":_bw_ea_probe_bake_result,"job_seen_running":False,"job_completed":False,"cache_ready":False,"poll_count":0})',
      '        _bw_ea_probe_write()',
      '        def _bw_ea_probe_poll():',
      '            try:',
      '                _bw_ea_probe_receipt["poll_count"] += 1',
      '                _bw_ea_probe_running = bpy.app.is_job_running("LIGHT_BAKE")',
      '                _bw_ea_probe_receipt["job_seen_running"] = _bw_ea_probe_receipt["job_seen_running"] or _bw_ea_probe_running',
      '                _bw_ea_probe_receipt["cache_ready"] = bool(grid.lightprobe_cache_ready)',
      '                _bw_ea_probe_receipt["elapsed_ms"] = int((time.monotonic() - _bw_ea_probe_started) * 1000)',
      '                if _bw_ea_probe_running:',
      '                    if (time.monotonic() - _bw_ea_probe_started) >= _bw_ea_probe_timeout_s:',
      '                        _bw_ea_probe_receipt.update({"state":"FAILED","error":"LIGHT_BAKE job timeout before cache publication"})',
      '                        _bw_ea_probe_write()',
      '                        return None',
      '                    _bw_ea_probe_write()',
      '                    return 0.05',
      '                _bw_ea_probe_receipt["job_completed"] = True',
      '                if not _bw_ea_probe_receipt["cache_ready"]:',
      '                    _bw_ea_probe_receipt.update({"state":"FAILED","error":"LIGHT_BAKE job ended without a packed probe cache"})',
      '                    _bw_ea_probe_write()',
      '                    return None',
      ...(EXPORT_BAKED_BLEND ? [
        `                _bw_ea_baked_blend_path = ${JSON.stringify(BAKED_BLEND_GUEST)}`,
        '                _bw_ea_save_result = sorted(bpy.ops.wm.save_as_mainfile(filepath=_bw_ea_baked_blend_path, check_existing=False, copy=True))',
        '                if _bw_ea_save_result != ["FINISHED"]:',
        '                    _bw_ea_probe_receipt.update({"state":"FAILED","error":"browser-baked blend export did not finish","save_result":_bw_ea_save_result})',
        '                    _bw_ea_probe_write()',
        '                    return None',
        '                _bw_ea_probe_receipt.update({"baked_blend_path":_bw_ea_baked_blend_path,"baked_blend_size":os.path.getsize(_bw_ea_baked_blend_path),"save_result":_bw_ea_save_result})',
      ] : []),
      '                _bw_ea_probe_receipt["state"] = "BAKE_COMPLETE"',
      '                _bw_ea_probe_write()',
      '                return None',
      '            except Exception as _bw_ea_probe_poll_error:',
      '                _bw_ea_probe_receipt.update({"state":"FAILED","error":repr(_bw_ea_probe_poll_error)})',
      '                _bw_ea_probe_write()',
      '                return None',
      '        bpy.app.timers.register(_bw_ea_probe_poll, first_interval=0.0)',
      '    elif _bw_ea_skip_probes:',
      '        _bw_ea_probe_receipt.update({"state":"SKIPPED_BY_SCENE","bake_result":None})',
      '        _bw_ea_probe_write()',
      '    else:',
      '        _bw_ea_probe_receipt.update({"state":"UNSUPPORTED_CONTEXT","bake_result":None,"error":"canonical probes require OBJECT mode"})',
      '        _bw_ea_probe_write()',
      '        raise RuntimeError(_bw_ea_probe_receipt["error"])',
      'except Exception as _bw_ea_probe_error:',
      '    if _bw_ea_probe_receipt.get("state") != "FAILED": _bw_ea_probe_receipt.update({"state":"FAILED","error":repr(_bw_ea_probe_error)})',
      '    _bw_ea_probe_receipt["operators_used"] = _bw_ea_probe_operators_used',
      '    _bw_ea_probe_write()',
      '    raise',
    ] : []),
    `_bw_ea_setup_schema = ${JSON.stringify(EEVEE_SETUP_SCHEMA)}`,
    '_bw_ea_setup_receipt = {"schema":_bw_ea_setup_schema, "passive_only":True, "probe_operators_used":False, "skip":{"hair":_bw_ea_skip_hair,"probes":_bw_ea_skip_probes,"raytracing":_bw_ea_skip_raytracing,"shadow":_bw_ea_skip_shadow,"subsurface":_bw_ea_skip_subsurface}, "overscan":[_bw_ea_eevee.use_overscan,_bw_ea_eevee.overscan_size], "ambient_occlusion_distances":[layer.eevee.ambient_occlusion_distance for layer in _bw_ea_scene.view_layers], "light_threshold":_bw_ea_eevee.light_threshold, "hair_type":None if _bw_ea_skip_hair else _bw_ea_scene.render.hair_type, "shadow":None if _bw_ea_skip_shadow else [_bw_ea_eevee.shadow_step_count,_bw_ea_eevee.shadow_pool_size], "volumetric":[_bw_ea_eevee.volumetric_tile_size,_bw_ea_eevee.volumetric_start,_bw_ea_eevee.volumetric_end,_bw_ea_eevee.volumetric_samples,_bw_ea_eevee.use_volumetric_shadows,_bw_ea_eevee.clamp_volume_indirect], "motion_blur_steps":_bw_ea_eevee.motion_blur_steps if _bw_ea_scene.render.use_motion_blur else None, "raytracing":None if _bw_ea_skip_raytracing else [_bw_ea_eevee.use_raytracing,_bw_ea_eevee.ray_tracing_method,_bw_ea_ray_options.resolution_scale,_bw_ea_ray_options.screen_trace_quality,_bw_ea_ray_options.screen_trace_thickness,_bw_ea_eevee.fast_gi_quality], "gi_cubemap_resolution":None if _bw_ea_skip_probes else _bw_ea_eevee.gi_cubemap_resolution, "light_intensity":[_bw_ea_eevee.direct_light_intensity,_bw_ea_eevee.indirect_light_intensity], "object_updates":{"shadow_lights":_bw_ea_shadow_light_count,"probe_hidden":_bw_ea_probe_hidden_count,"thickness_materials":len(_bw_ea_thickness_materials)}}',
    ...(canonicalProbes ? [
      '_bw_ea_setup_receipt["passive_only"] = not _bw_ea_probe_operators_used',
      '_bw_ea_setup_receipt["probe_operators_used"] = _bw_ea_probe_operators_used',
      '_bw_ea_probe_receipt["operators_used"] = _bw_ea_probe_operators_used',
    ] : []),
    ...(EEVEE_FILM_TRANSPARENT ? ['_bw_ea_scene.render.film_transparent = True'] : []),
    ...(!productMode && eeveePassCapture ? [
      '_bw_ea_view_layer = bpy.context.view_layer',
      '_bw_ea_view_layer.use_pass_normal = True',
      '_bw_ea_view_layer.use_pass_diffuse_direct = True',
      '_bw_ea_view_layer.use_pass_diffuse_color = True',
    ] : []),
    '_bw_ea_scene.frame_set(1)',
    `_bw_ea_png = ${JSON.stringify(PNG_GUEST)}`,
    `_bw_ea_done = ${JSON.stringify(DONE_GUEST)}`,
    `_bw_ea_config = ${JSON.stringify(CONFIG_GUEST)}`,
    `_bw_ea_pre_path = ${JSON.stringify(PRE_GUEST)}`,
    '_bw_ea_pre_count = 0',
    '_bw_ea_complete_count = 0',
    '_bw_ea_cancel_count = 0',
    '_bw_ea_export_armed = False',
    'def _bw_ea_write(path, obj):',
    '    tmp = path + ".tmp"',
    '    with open(tmp, "w") as f: json.dump(obj, f, sort_keys=True)',
    '    os.replace(tmp, path)',
    'def _bw_ea_readback_capture_one(sequence, encoding):',
    '    if os.environ.get("BW_READBACK_CAPTURE") != "1": return None',
    '    path = "/tmp/bw_prod_readback_%d.bin" % sequence',
    '    if not os.path.exists(path): return {"status":"MISSING", "path":path}',
    '    raw = open(path, "rb").read()',
    '    if len(raw) < 32: return {"status":"SHORT", "path":path, "bytes":len(raw)}',
    '    header = struct.unpack("<8I", raw[:32])',
    '    payload = raw[32:]',
    '    result = {"status":"OK", "path":path, "sha256":hashlib.sha256(raw).hexdigest(), "bytes":len(raw), "magic":raw[:4].decode("ascii", "replace"), "version":header[1], "tight_row_bytes":header[2], "height":header[3], "kind":header[4], "row_bytes":header[6], "payload_bytes":header[7], "encoding":encoding}',
    '    if len(payload) != header[7]:',
    '        result["status"] = "BAD_PAYLOAD"; result["actual_payload_bytes"] = len(payload); return result',
    '    if encoding == "f16x4" and len(payload) % 8 == 0:',
    '        values = [item[0] for item in struct.iter_unpack("<e", payload)]',
    '        result["texel_count"] = len(values) // 4',
    '        result["channels"] = []',
    '        for channel_index in range(4):',
    '            channel = values[channel_index::4]',
    '            finite = [value for value in channel if math.isfinite(value)]',
    '            result["channels"].append({"index":channel_index, "min":min(finite) if finite else None, "max":max(finite) if finite else None, "nonzero":sum(value != 0.0 for value in finite), "finite":len(finite), "nan":sum(math.isnan(value) for value in channel), "inf":sum(math.isinf(value) for value in channel)})',
    '    elif encoding == "f32" and len(payload) % 4 == 0:',
    '        values = [item[0] for item in struct.iter_unpack("<f", payload)]',
    '        finite = [value for value in values if math.isfinite(value)]',
    '        result["texel_count"] = len(values)',
    '        result["stats"] = {"min":min(finite) if finite else None, "max":max(finite) if finite else None, "nonzero":sum(value != 0.0 for value in finite), "unique_sample":sorted(set(finite))[:16], "finite":len(finite), "nan":sum(math.isnan(value) for value in values), "inf":sum(math.isinf(value) for value in values)}',
    '    else:',
    '        result["status"] = "BAD_ENCODING"',
    '    return result',
    'def _bw_ea_readback_captures():',
    '    if os.environ.get("BW_READBACK_CAPTURE") != "1": return None',
    '    encodings = ["f16x4", "f16x4", "f32"] + (["f16x4", "f16x4", "f16x4"] if os.environ.get("BW_EEVEE_PASS_CAPTURE") == "1" else [])',
    '    return [_bw_ea_readback_capture_one(sequence, encoding) for sequence, encoding in enumerate(encodings)]',
    'def _bw_ea_pre(*_args):',
    '    global _bw_ea_pre_count',
    '    _bw_ea_pre_count += 1',
    '    _bw_ea_write(_bw_ea_pre_path, {"status":"RENDER_PRE", "count":_bw_ea_pre_count, "engine":bpy.context.scene.render.engine, "blend":bpy.data.filepath})',
    '    print("BW_EEVEE_ACCEPT phase=RENDER_PRE count=%d" % _bw_ea_pre_count)',
    'def _bw_ea_export():',
    '    global _bw_ea_export_armed',
    '    try:',
    '        rr = bpy.data.images.get("Render Result")',
    '        if rr is None:',
    '            raise RuntimeError("Render Result missing")',
    '        rr.save_render(filepath=_bw_ea_png, scene=bpy.context.scene)',
    '        for win in bpy.context.window_manager.windows:',
    '            if not win.screen: continue',
    '            for area in win.screen.areas:',
    '                if area.type == "VIEW_3D":',
    '                    area.type = "IMAGE_EDITOR"',
    '                    area.spaces.active.image = rr',
    '        _bw_ea_render_samples = bpy.context.view_layer.samples if bpy.context.view_layer.samples > 0 else bpy.context.scene.eevee.taa_render_samples',
        '        receipt = {"status":"OK", "engine":bpy.context.scene.render.engine, "resolution":[bpy.context.scene.render.resolution_x,bpy.context.scene.render.resolution_y], "blend":bpy.data.filepath, "pre_count":_bw_ea_pre_count, "complete_count":_bw_ea_complete_count, "cancel_count":_bw_ea_cancel_count, "png":_bw_ea_png, "png_size":os.path.getsize(_bw_ea_png), "render_samples":_bw_ea_render_samples, "view_transform":bpy.context.scene.view_settings.view_transform, "color_mode":bpy.context.scene.render.image_settings.color_mode, "readback_captures":_bw_ea_readback_captures()}',
    '        _bw_ea_write(_bw_ea_done, receipt)',
    '        print("BW_EEVEE_ACCEPT phase=PNG_SAVED bytes=%d" % receipt["png_size"])',
    '    except Exception as e:',
    '        _bw_ea_write(_bw_ea_done, {"status":"FAIL", "error":repr(e), "pre_count":_bw_ea_pre_count, "complete_count":_bw_ea_complete_count, "cancel_count":_bw_ea_cancel_count})',
    '        print("BW_EEVEE_ACCEPT phase=EXPORT_FAIL error=%r" % e)',
    '    _bw_ea_export_armed = False',
    '    return None',
    'def _bw_ea_complete(*_args):',
    '    global _bw_ea_complete_count, _bw_ea_export_armed',
    '    _bw_ea_complete_count += 1',
    '    print("BW_EEVEE_ACCEPT phase=RENDER_COMPLETE count=%d" % _bw_ea_complete_count)',
    '    if not _bw_ea_export_armed:',
    '        _bw_ea_export_armed = True',
    '        bpy.app.timers.register(_bw_ea_export, first_interval=0.0)',
    'def _bw_ea_cancel(*_args):',
    '    global _bw_ea_cancel_count',
    '    _bw_ea_cancel_count += 1',
    '    _bw_ea_write(_bw_ea_done, {"status":"FAIL", "error":"render cancelled", "pre_count":_bw_ea_pre_count, "complete_count":_bw_ea_complete_count, "cancel_count":_bw_ea_cancel_count})',
    '    print("BW_EEVEE_ACCEPT phase=RENDER_CANCEL count=%d" % _bw_ea_cancel_count)',
    'bpy.app.handlers.render_pre.append(_bw_ea_pre)',
    'bpy.app.handlers.render_complete.append(_bw_ea_complete)',
    'bpy.app.handlers.render_cancel.append(_bw_ea_cancel)',
    ...(canonicalProbes ? [
      '_bw_ea_write(_bw_ea_config, {"status":"ARMED", "engine":_bw_ea_scene.render.engine, "resolution":[_bw_ea_scene.render.resolution_x,_bw_ea_scene.render.resolution_y], "blend":bpy.data.filepath, "async_env":os.environ.get(' + JSON.stringify(ASYNC.envKey) + '), "stripped_diag_envs":{key:os.environ.get(key) for key in ' + JSON.stringify(STRIPPED_DIAGNOSTIC_ENV_KEYS) + '}, "render_sampling":{"scene":_bw_ea_scene.eevee.taa_render_samples,"view_layer_override":bpy.context.view_layer.samples,"effective":bpy.context.view_layer.samples if bpy.context.view_layer.samples > 0 else _bw_ea_scene.eevee.taa_render_samples}, "view_transform":_bw_ea_scene.view_settings.view_transform, "color_mode":_bw_ea_scene.render.image_settings.color_mode, "upstream_setup":_bw_ea_setup_receipt, "probe_preparation":_bw_ea_probe_receipt})',
    ] : [
      '_bw_ea_write(_bw_ea_config, {"status":"ARMED", "engine":_bw_ea_scene.render.engine, "resolution":[_bw_ea_scene.render.resolution_x,_bw_ea_scene.render.resolution_y], "blend":bpy.data.filepath, "async_env":os.environ.get(' + JSON.stringify(ASYNC.envKey) + '), "stripped_diag_envs":{key:os.environ.get(key) for key in ' + JSON.stringify(STRIPPED_DIAGNOSTIC_ENV_KEYS) + '}, "render_sampling":{"scene":_bw_ea_scene.eevee.taa_render_samples,"view_layer_override":bpy.context.view_layer.samples,"effective":bpy.context.view_layer.samples if bpy.context.view_layer.samples > 0 else _bw_ea_scene.eevee.taa_render_samples}, "view_transform":_bw_ea_scene.view_settings.view_transform, "color_mode":_bw_ea_scene.render.image_settings.color_mode, "upstream_setup":_bw_ea_setup_receipt})',
    ]),
    'print("BW_EEVEE_ACCEPT phase=ARMED engine=%s res=%dx%d blend=%s" % (_bw_ea_scene.render.engine, _bw_ea_scene.render.resolution_x, _bw_ea_scene.render.resolution_y, bpy.data.filepath))',
  ].join('\n');
}

function parseComparator(text, returnCode) {
  let maxError = null;
  let percentOver = null;
  for (const line of text.split(/\r?\n/)) {
    const maxMatch = /Max error\s*=\s*([0-9.eE+-]+)/.exec(line);
    if (maxMatch) maxError = maxMatch[1];
    const overMatch = /\(([0-9.]+%)\s*\)\s*over/.exec(line);
    if (overMatch) percentOver = overMatch[1];
  }
  return { returnCode, maxError, percentOver, pass: returnCode === 0 };
}

function parseWebGpuPreinitReceipt(text, { requireColor = PRODUCT_MODE } = {}) {
  if (!text.startsWith(WGPU_PREINIT_PREFIX)) return null;
  const readLimit = (key) => {
    const match = new RegExp(`(?:^|\\s)${key}=(\\d+)(?:\\s|$)`).exec(text);
    return match ? Number.parseInt(match[1], 10) : null;
  };
  const adapter = readLimit('adapterMaxComputeWorkgroupStorageSize');
  const requested = readLimit('requestedMaxComputeWorkgroupStorageSize');
  const device = readLimit('deviceMaxComputeWorkgroupStorageSize');
  const adapterColor = readLimit('adapterMaxColorAttachmentBytesPerSample');
  const requestedColor = readLimit('requestedMaxColorAttachmentBytesPerSample');
  const deviceColor = readLimit('deviceMaxColorAttachmentBytesPerSample');
  const computePass = Number.isInteger(adapter) && Number.isInteger(requested) &&
    Number.isInteger(device) && adapter >= MIN_COMPUTE_WORKGROUP_STORAGE_SIZE &&
    requested >= MIN_COMPUTE_WORKGROUP_STORAGE_SIZE && requested <= adapter &&
    device >= requested;
  const colorPass = Number.isInteger(adapterColor) && Number.isInteger(requestedColor) &&
    Number.isInteger(deviceColor) && adapterColor >= MIN_COLOR_ATTACHMENT_BYTES_PER_SAMPLE &&
    requestedColor >= MIN_COLOR_ATTACHMENT_BYTES_PER_SAMPLE && requestedColor <= adapterColor &&
    deviceColor >= requestedColor;
  return {
    adapterMaxComputeWorkgroupStorageSize: adapter,
    requestedMaxComputeWorkgroupStorageSize: requested,
    deviceMaxComputeWorkgroupStorageSize: device,
    requiredMinimum: MIN_COMPUTE_WORKGROUP_STORAGE_SIZE,
    adapterMaxColorAttachmentBytesPerSample: adapterColor,
    requestedMaxColorAttachmentBytesPerSample: requestedColor,
    deviceMaxColorAttachmentBytesPerSample: deviceColor,
    requiredColorAttachmentBytesPerSample: MIN_COLOR_ATTACHMENT_BYTES_PER_SAMPLE,
    requireColor,
    computePass,
    colorPass,
    pass: computePass && (!requireColor || colorPass),
    line: text,
  };
}

function trustedPhysicalF12(receipt) {
  return receipt?.length === 1 && receipt[0].key === 'F12' && receipt[0].code === 'F12' &&
    receipt[0].isTrusted === true && receipt[0].repeat === false &&
    receipt[0].targetId === 'canvas' && receipt[0].activeId === 'canvas';
}

function exactRenderConfiguration(
  receipt, expectedEffective = 64, { requireViewLayerOverride = false } = {})
{
  return receipt?.render_sampling?.effective === expectedEffective &&
    Number.isInteger(receipt.render_sampling.scene) && receipt.render_sampling.scene > 0 &&
    Number.isInteger(receipt.render_sampling.view_layer_override) &&
    (!requireViewLayerOverride ||
      receipt.render_sampling.view_layer_override === expectedEffective) &&
    receipt.view_transform === EXPECTED_VIEW_TRANSFORM &&
    receipt.color_mode === EXPECTED_COLOR_MODE;
}

function exactHandlerCompletion(receipt, expectedRenderSamples = 64) {
  return receipt?.status === 'OK' && receipt.engine === 'BLENDER_EEVEE' &&
    JSON.stringify(receipt.resolution) === JSON.stringify([RENDER_WIDTH, RENDER_HEIGHT]) &&
    receipt.blend === BLEND_GUEST && receipt.pre_count === 1 &&
    receipt.complete_count === 1 && receipt.cancel_count === 0 &&
    receipt.png === PNG_GUEST && receipt.png_size > 0 &&
    receipt.render_samples === expectedRenderSamples &&
    receipt.view_transform === EXPECTED_VIEW_TRANSFORM &&
    receipt.color_mode === EXPECTED_COLOR_MODE;
}

function validateWmTickProgress(before, after) {
  if (before === null || before === undefined || before === '' ||
      after === null || after === undefined || after === '')
  {
    return false;
  }
  const beforeNumber = Number(before);
  const afterNumber = Number(after);
  return Number.isFinite(beforeNumber) && Number.isFinite(afterNumber) && afterNumber > beforeNumber;
}

function productTopologyReceipt() {
  return { ok: true, productMode: true, markerIndependent: true, actualStates: [], errors: [], uiHeartbeat: null };
}

function strippedDiagnosticEnvironmentAbsent(receipt) {
  const values = receipt?.stripped_diag_envs;
  return values && STRIPPED_DIAGNOSTIC_ENV_KEYS.every((key) =>
    Object.hasOwn(values, key) && values[key] === null);
}

function validateCanonicalProbeReceipt(receipt, expectedBakeSamples = 128) {
  const errors = [];
  const equivalent = (actual, expected) => {
    if (typeof expected === 'number') {
      return typeof actual === 'number' && Number.isFinite(actual) &&
        Math.abs(actual - expected) <= 1e-6;
    }
    if (Array.isArray(expected)) {
      return Array.isArray(actual) && actual.length === expected.length &&
        expected.every((value, index) => equivalent(actual[index], value));
    }
    return actual === expected;
  };
  const equal = (actual, expected, label) => {
    if (!equivalent(actual, expected)) {
      errors.push(`${label}=${JSON.stringify(actual)} expected=${JSON.stringify(expected)}`);
    }
  };
  if (receipt?.schema !== CANONICAL_PROBE_SCHEMA) errors.push(`schema=${receipt?.schema}`);
  if (receipt?.requested !== true) errors.push(`requested=${receipt?.requested}`);
  if (receipt?.state === 'BAKE_COMPLETE') {
    if (receipt.skip_probes !== false) errors.push(`skip_probes=${receipt.skip_probes}`);
    if (receipt.context_mode !== 'OBJECT') errors.push(`context_mode=${receipt.context_mode}`);
    if (receipt.operators_used !== true) errors.push(`operators_used=${receipt.operators_used}`);
    equal(receipt.bake_result, ['RUNNING_MODAL'], 'bake_result');
    if (receipt.job_completed !== true) errors.push(`job_completed=${receipt.job_completed}`);
    if (receipt.cache_ready !== true) errors.push(`cache_ready=${receipt.cache_ready}`);
    if (!Number.isInteger(receipt.poll_count) || receipt.poll_count < 1) {
      errors.push(`poll_count=${receipt.poll_count}`);
    }
    equal(receipt.sphere?.type, 'SPHERE', 'sphere.type');
    equal(receipt.sphere?.location, [0, 0.1, 1], 'sphere.location');
    equal(receipt.sphere?.scale, [5, 5, 2], 'sphere.scale');
    equal(receipt.sphere?.falloff, 0, 'sphere.falloff');
    equal(receipt.sphere?.clip_start, 0.8, 'sphere.clip_start');
    equal(receipt.sphere?.influence_distance, 1.2, 'sphere.influence_distance');
    equal(receipt.volume?.type, 'VOLUME', 'volume.type');
    equal(receipt.volume?.location, [0, 0, 2], 'volume.location');
    equal(receipt.volume?.scale, [8, 4.5, 4.5], 'volume.scale');
    equal(receipt.volume?.resolution, [32, 16, 8], 'volume.resolution');
    equal(receipt.volume?.bake_samples, expectedBakeSamples, 'volume.bake_samples');
    equal(receipt.volume?.capture_world, true, 'volume.capture_world');
    equal(receipt.volume?.surfel_density, 100, 'volume.surfel_density');
    equal(receipt.volume?.dilation_threshold, 1, 'volume.dilation_threshold');
    if (!receipt.volume?.name || receipt.active_object !== receipt.volume.name) {
      errors.push(`active_object=${receipt.active_object} volume.name=${receipt.volume?.name}`);
    }
  }
  else if (receipt?.state === 'PREEXISTING') {
    if (receipt.existing_object !== 'Volume_Probe_Baked') {
      errors.push(`existing_object=${receipt.existing_object}`);
    }
    if (receipt.operators_used !== false) errors.push(`operators_used=${receipt.operators_used}`);
  }
  else if (receipt?.state === 'SKIPPED_BY_SCENE') {
    if (receipt.skip_probes !== true) errors.push(`skip_probes=${receipt.skip_probes}`);
    if (receipt.operators_used !== false) errors.push(`operators_used=${receipt.operators_used}`);
  }
  else {
    errors.push(`terminal_state=${receipt?.state}`);
  }
  return { ok: errors.length === 0, errors };
}

function canonicalProbePreparationBlockingReason(
  receipt, { pageCrashed = false, pageErrors = [], gpuErrors = [] } = {})
{
  if (receipt?.state === 'FAILED' || receipt?.state === 'UNSUPPORTED_CONTEXT') {
    return `probe receipt entered ${receipt.state}: ${receipt.error || 'no error detail'}`;
  }
  if (pageCrashed) return 'page crashed';
  if (pageErrors.length) return `page/runtime error: ${pageErrors[0]}`;
  if (gpuErrors.length) return `GPU/browser error: ${gpuErrors[0]}`;
  return null;
}

function canonicalProbePreparationTerminal(receipt) {
  return ['BAKE_COMPLETE', 'PREEXISTING', 'SKIPPED_BY_SCENE'].includes(receipt?.state);
}

function validateEeveeSetupReceipt(setup, { probeOperatorsUsed = false } = {}) {
  const errors = [];
  const equivalent = (actual, expected) => {
    if (typeof expected === 'number') {
      return typeof actual === 'number' && Number.isFinite(actual) &&
        Math.abs(actual - expected) <= 1e-6;
    }
    if (Array.isArray(expected)) {
      return Array.isArray(actual) && actual.length === expected.length &&
        expected.every((value, index) => equivalent(actual[index], value));
    }
    return actual === expected;
  };
  const equal = (actual, expected, label) => {
    if (!equivalent(actual, expected)) {
      errors.push(`${label}=${JSON.stringify(actual)} expected=${JSON.stringify(expected)}`);
    }
  };
  if (setup?.schema !== EEVEE_SETUP_SCHEMA) errors.push(`schema=${setup?.schema}`);
  if (setup?.passive_only !== !probeOperatorsUsed) {
    errors.push(`passive_only=${setup?.passive_only}`);
  }
  if (setup?.probe_operators_used !== probeOperatorsUsed) {
    errors.push(`probe_operators_used=${setup?.probe_operators_used}`);
  }
  const skip = setup?.skip;
  for (const key of ['hair', 'probes', 'raytracing', 'shadow', 'subsurface']) {
    if (typeof skip?.[key] !== 'boolean') errors.push(`skip.${key}=${skip?.[key]}`);
  }
  equal(setup?.overscan, [true, 50], 'overscan');
  if (!Array.isArray(setup?.ambient_occlusion_distances) ||
      setup.ambient_occlusion_distances.length === 0 ||
      setup.ambient_occlusion_distances.some((value) => !equivalent(value, 1)))
  {
    errors.push(`ambient_occlusion_distances=${JSON.stringify(setup?.ambient_occlusion_distances)}`);
  }
  if (!equivalent(setup?.light_threshold, 0.001)) {
    errors.push(`light_threshold=${setup?.light_threshold}`);
  }
  equal(setup?.volumetric, ['2', 1, 50, 128, true, 0], 'volumetric');
  equal(setup?.light_intensity, [1, 1], 'light_intensity');
  if (skip?.hair === false && setup?.hair_type !== 'STRIP') {
    errors.push(`hair_type=${setup?.hair_type}`);
  }
  if (skip?.shadow === false) equal(setup?.shadow, [16, '1024'], 'shadow');
  if (skip?.raytracing === false) {
    equal(setup?.raytracing, [true, 'SCREEN', '1', 1, 1, 0.8], 'raytracing');
  }
  if (skip?.probes === false && setup?.gi_cubemap_resolution !== '256') {
    errors.push(`gi_cubemap_resolution=${setup?.gi_cubemap_resolution}`);
  }
  if (setup?.motion_blur_steps !== null && setup?.motion_blur_steps !== 10) {
    errors.push(`motion_blur_steps=${setup?.motion_blur_steps}`);
  }
  for (const key of ['shadow_lights', 'probe_hidden', 'thickness_materials']) {
    const value = setup?.object_updates?.[key];
    if (!Number.isInteger(value) || value < 0) errors.push(`object_updates.${key}=${value}`);
  }
  return { ok: errors.length === 0, errors };
}

if (process.argv[2] === '--selfcheck') {
  const samples = [
    ['phase=INVOKE seq=91 main=1 thread=11 tick=99', 5],
    ['phase=ENQUEUED seq=91 main=0 thread=22 tick=100 ok=1', 10],
    ['same_wm=1 phase=TURN abort=0 tick=104 seq=91 main=1 thread=11', 40],
    ['yield=timeout thread=11 tick=104 phase=PENDING seq=91 main=1', 41],
    ['phase=TURN seq=91 main=1 thread=11 tick=105 same_wm=1 abort=0', 50],
    ['phase=CONSUME status=complete', 51],
    ['status=complete phase=END_RESULT', 52],
    ['status=complete phase=WRITE frame=1', 53],
    ['phase=PIPELINE_TERMINAL frame=1 status=complete', 54],
    ['terminal=1 phase=READY tick=105 thread=11 main=1 seq=91', 60],
    ['phase=WORKER_RETURN status=complete seq=91 main=0 thread=22 tick=105', 70],
    ['phase=QUEUE_DESTROY seq=91 main=1 thread=11 tick=106', 80],
  ];
  const events = samples.map(([tokens, atMs], index) =>
    parseAsyncLine(`${ASYNC.prefix}${tokens}`, atMs, index));
  const heartbeats = [{ atMs: 25, tick: '102' }];
  const accepted = validateAsync(events, heartbeats);
  const withoutWrite = validateAsync(
    events.filter((event) => event.state !== 'WRITE'), heartbeats);
  const wrongOrder = validateAsync([events[1], events[0], ...events.slice(2)], heartbeats);
  const wrongWorkerEvents = events.map((event) => ({ ...event, fields: { ...event.fields } }));
  wrongWorkerEvents.find((event) => event.state === 'WORKER_RETURN').fields.thread = '11';
  const wrongWorker = validateAsync(wrongWorkerEvents, heartbeats);
  const failed = validateAsync([
    ...events.slice(0, 3),
    parseAsyncLine(`${ASYNC.prefix}phase=FAILED seq=91 main=1 thread=11 tick=105 reason=boom`, 50, 3),
    ...events.slice(4),
  ], heartbeats);
  const pyexpr = makePythonExpr({
    productMode: false, canonicalProbes: false, renderSamplesOverride: null,
  });
  const productPyexpr = makePythonExpr({
    productMode: true,
    readbackCapture: false,
    eeveeInputCapture: false,
    eeveePassCapture: false,
    eeveeDepthAlwaysDiag: false,
    canonicalProbes: false,
    renderSamplesOverride: null,
  });
  const canonicalProbePyexpr = makePythonExpr({
    productMode: true,
    readbackCapture: false,
    eeveeInputCapture: false,
    eeveePassCapture: false,
    eeveeDepthAlwaysDiag: false,
    canonicalProbes: true,
    probeBakeSamples: 128,
    renderSamplesOverride: null,
  });
  const oneSamplePyexpr = makePythonExpr({
    productMode: true,
    readbackCapture: false,
    eeveeInputCapture: false,
    eeveePassCapture: false,
    eeveeDepthAlwaysDiag: false,
    canonicalProbes: false,
    renderSamplesOverride: 1,
  });
  let productDiagRejected = false;
  let nonProductProbeRejected = false;
  let nonProductSamplesRejected = false;
  let canonicalSamplesRejected = false;
  let invalidSamplesRejected = false;
  try {
    makePythonExpr({
      productMode: true,
      readbackCapture: true,
      eeveeInputCapture: false,
      eeveePassCapture: false,
      eeveeDepthAlwaysDiag: false,
      renderSamplesOverride: null,
    });
  }
  catch (error) {
    productDiagRejected = /forbids stripped diagnostic/.test(String(error));
  }
  try {
    makePythonExpr({
      productMode: false, canonicalProbes: true, renderSamplesOverride: null,
    });
  }
  catch (error) {
    nonProductProbeRejected = /requires BW_EEVEE_PRODUCT_SMOKE/.test(String(error));
  }
  for (const [options, pattern, record] of [
    [{ productMode: false, canonicalProbes: false, renderSamplesOverride: 1 },
      /requires BW_EEVEE_PRODUCT_SMOKE/, (value) => { nonProductSamplesRejected = value; }],
    [{ productMode: true, canonicalProbes: true, renderSamplesOverride: 1 },
      /requires canonical probes off/, (value) => { canonicalSamplesRejected = value; }],
    [{ productMode: true, canonicalProbes: false, renderSamplesOverride: 0 },
      /must be a positive integer/, (value) => { invalidSamplesRejected = value; }],
  ]) {
    try {
      makePythonExpr(options);
    }
    catch (error) {
      record(pattern.test(String(error)));
    }
  }
  const pySyntax = spawnSync(
    'python3',
    ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'],
    { input: pyexpr, encoding: 'utf8' },
  );
  const productPySyntax = spawnSync(
    'python3',
    ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'],
    { input: productPyexpr, encoding: 'utf8' },
  );
  const canonicalProbePySyntax = spawnSync(
    'python3',
    ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'],
    { input: canonicalProbePyexpr, encoding: 'utf8' },
  );
  const oneSamplePySyntax = spawnSync(
    'python3',
    ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'],
    { input: oneSamplePyexpr, encoding: 'utf8' },
  );
  const upstreamEeveeTestScript = readFileSync(EEVEE_TEST_SCRIPT_HOST, 'utf8');
  const driverSource = readFileSync(DRIVER_PATH, 'utf8');
  const manifestRow = readFileSync(`${ROOT}/sandbox/m6-prep/manifest.tsv`, 'utf8')
    .split(/\r?\n/).find((line) => line.startsWith('eevee\tprincipled_bsdf\tprincipled_bsdf_default\t'));
  const validLimitReceipt = parseWebGpuPreinitReceipt(
    `${WGPU_PREINIT_PREFIX} features=18 ` +
    'adapterMaxComputeWorkgroupStorageSize=65536 ' +
    'requestedMaxComputeWorkgroupStorageSize=65536 ' +
    'deviceMaxComputeWorkgroupStorageSize=65536 ' +
    'adapterMaxColorAttachmentBytesPerSample=128 ' +
    'requestedMaxColorAttachmentBytesPerSample=128 ' +
    'deviceMaxColorAttachmentBytesPerSample=128',
    { requireColor: true });
  const lowLimitReceipt = parseWebGpuPreinitReceipt(
    `${WGPU_PREINIT_PREFIX} features=18 ` +
    'adapterMaxComputeWorkgroupStorageSize=16384 ' +
    'requestedMaxComputeWorkgroupStorageSize=16384 ' +
    'deviceMaxComputeWorkgroupStorageSize=16384 ' +
    'adapterMaxColorAttachmentBytesPerSample=128 ' +
    'requestedMaxColorAttachmentBytesPerSample=128 ' +
    'deviceMaxColorAttachmentBytesPerSample=128',
    { requireColor: true });
  const lowColorLimitReceipt = parseWebGpuPreinitReceipt(
    `${WGPU_PREINIT_PREFIX} features=18 ` +
    'adapterMaxComputeWorkgroupStorageSize=65536 ' +
    'requestedMaxComputeWorkgroupStorageSize=65536 ' +
    'deviceMaxComputeWorkgroupStorageSize=65536 ' +
    'adapterMaxColorAttachmentBytesPerSample=32 ' +
    'requestedMaxColorAttachmentBytesPerSample=32 ' +
    'deviceMaxColorAttachmentBytesPerSample=32',
    { requireColor: true });
  const trustedF12Sample = [{
    key: 'F12', code: 'F12', isTrusted: true, repeat: false,
    targetId: 'canvas', activeId: 'canvas',
  }];
  const handlerSample = {
    status: 'OK', engine: 'BLENDER_EEVEE',
    resolution: [RENDER_WIDTH, RENDER_HEIGHT], blend: BLEND_GUEST,
    pre_count: 1, complete_count: 1, cancel_count: 0,
    png: PNG_GUEST, png_size: 128, render_samples: 64,
    view_transform: EXPECTED_VIEW_TRANSFORM, color_mode: EXPECTED_COLOR_MODE,
  };
  const renderConfigurationSample = {
    render_sampling: { scene: 64, view_layer_override: 0, effective: 64 },
    view_transform: EXPECTED_VIEW_TRANSFORM,
    color_mode: EXPECTED_COLOR_MODE,
  };
  const cleanProductEnvironmentSample = {
    stripped_diag_envs: Object.fromEntries(
      STRIPPED_DIAGNOSTIC_ENV_KEYS.map((key) => [key, null])),
  };
  const canonicalProbeSample = {
    schema: CANONICAL_PROBE_SCHEMA,
    requested: true,
    state: 'BAKE_COMPLETE',
    skip_probes: false,
    context_mode: 'OBJECT',
    operators_used: true,
    bake_result: ['RUNNING_MODAL'],
    job_seen_running: true,
    job_completed: true,
    cache_ready: true,
    poll_count: 3,
    sphere: {
      name: 'LightProbe', type: 'SPHERE', location: [0, 0.1, 1], scale: [5, 5, 2],
      falloff: 0, clip_start: 0.8, influence_distance: 1.2,
    },
    volume: {
      name: 'LightProbe.001', type: 'VOLUME', location: [0, 0, 2], scale: [8, 4.5, 4.5],
      resolution: [32, 16, 8], bake_samples: 128, capture_world: true,
      surfel_density: 100, dilation_threshold: 1,
    },
    active_object: 'LightProbe.001',
  };
  const canonicalProbeAssignments = [
    "bpy.ops.object.lightprobe_add(type='SPHERE', location=(0.0, 0.1, 1.0))",
    'cubemap.scale = (5.0, 5.0, 2.0)',
    'cubemap.data.falloff = 0.0',
    'cubemap.data.clip_start = 0.8',
    'cubemap.data.influence_distance = 1.2',
    "bpy.ops.object.lightprobe_add(type='VOLUME', location=(0.0, 0.0, 2.0))",
    'grid.scale = (8.0, 4.5, 4.5)',
    'grid.data.resolution_x = 32',
    'grid.data.resolution_y = 16',
    'grid.data.resolution_z = 8',
    'grid.data.bake_samples = 128',
    'grid.data.capture_world = True',
    'grid.data.surfel_density = 100',
    'grid.data.dilation_threshold = 1.0',
    "bpy.ops.object.lightprobe_cache_bake(subset='ACTIVE')",
  ];
  const setupSample = {
    schema: EEVEE_SETUP_SCHEMA,
    passive_only: true,
    probe_operators_used: false,
    skip: { hair: false, probes: false, raytracing: false, shadow: false, subsurface: false },
    overscan: [true, 50],
    ambient_occlusion_distances: [1],
    light_threshold: 0.001,
    hair_type: 'STRIP',
    shadow: [16, '1024'],
    volumetric: ['2', 1, 50, 128, true, 0],
    motion_blur_steps: null,
    raytracing: [true, 'SCREEN', '1', 1, 1, 0.8],
    gi_cubemap_resolution: '256',
    light_intensity: [1, 1],
    object_updates: { shadow_lights: 1, probe_hidden: 2, thickness_materials: 3 },
  };
  const badSetupSample = { ...setupSample, overscan: [false, 50] };
  const float32SetupSample = {
    ...setupSample,
    light_threshold: 0.0010000000474974513,
    raytracing: [true, 'SCREEN', '1', 1, 1, 0.800000011920929],
  };
  const outOfToleranceSetupSample = {
    ...setupSample,
    raytracing: [true, 'SCREEN', '1', 1, 1, 0.80001],
  };
  const canonicalSetupSample = {
    ...setupSample,
    passive_only: false,
    probe_operators_used: true,
  };
  const canonicalSetupAssignments = [
    '_bw_ea_eevee.use_overscan = True',
    '_bw_ea_layer.eevee.ambient_occlusion_distance = 1',
    '_bw_ea_eevee.shadow_pool_size = "1024"',
    '_bw_ea_eevee.volumetric_samples = 128',
    '_bw_ea_eevee.ray_tracing_method = "SCREEN"',
    '_bw_ea_eevee.fast_gi_quality = 0.8',
    '_bw_ea_eevee.gi_cubemap_resolution = "256"',
    '_bw_ea_eevee.direct_light_intensity = 1.0',
    '_bw_ea_object.data.shadow_maximum_resolution = 0.0',
    '_bw_ea_slot.material.thickness_mode = "SPHERE"',
  ];
  const checks = [
    accepted.ok,
    accepted.actualStates.join('>') === 'INVOKE>ENQUEUED>TURN>PENDING>TURN>CONSUME>END_RESULT>WRITE>PIPELINE_TERMINAL>READY>WORKER_RETURN>QUEUE_DESTROY',
    accepted.sequence === '91',
    accepted.wmThread === '11',
    accepted.workerThread === '22',
    accepted.yieldPairCount === 1,
    accepted.optionalWrite === true,
    withoutWrite.ok,
    withoutWrite.optionalWrite === false,
    accepted.uiHeartbeat?.tick === '102',
    !wrongOrder.ok,
    !wrongWorker.ok,
    !failed.ok,
    pySyntax.status === 0,
    productPySyntax.status === 0,
    canonicalProbePySyntax.status === 0,
    oneSamplePySyntax.status === 0,
    !/bpy\.ops\.render/.test(pyexpr),
    !/\bbpy\.ops\./.test(pyexpr),
    !/\bbpy\.ops\./.test(productPyexpr),
    !/bpy\.ops\.render/.test(canonicalProbePyexpr),
    !/\bbpy\.ops\./.test(oneSamplePyexpr),
    oneSamplePyexpr.includes('bpy.context.view_layer.samples = 1'),
    !productPyexpr.includes('bpy.context.view_layer.samples ='),
    canonicalProbeAssignments.every((assignment) =>
      canonicalProbePyexpr.includes(assignment) && upstreamEeveeTestScript.includes(assignment)),
    canonicalProbePyexpr.includes('_bw_ea_probe_bake_result != ["RUNNING_MODAL"]'),
    canonicalProbePyexpr.includes('bpy.app.is_job_running("LIGHT_BAKE")'),
    canonicalProbePyexpr.includes('bool(grid.lightprobe_cache_ready)'),
    canonicalProbePyexpr.includes('bpy.app.timers.register(_bw_ea_probe_poll, first_interval=0.0)'),
    canonicalProbePyexpr.indexOf("bpy.ops.object.lightprobe_cache_bake(subset='ACTIVE')") <
      canonicalProbePyexpr.indexOf('bpy.app.timers.register(_bw_ea_probe_poll') &&
      canonicalProbePyexpr.indexOf('bpy.app.timers.register(_bw_ea_probe_poll') <
      canonicalProbePyexpr.indexOf('_bw_ea_write(_bw_ea_config'),
    pyexpr.includes(`os.environ[${JSON.stringify(ASYNC.envKey)}]`),
    STRIPPED_DIAGNOSTIC_ENV_KEYS.every((key) =>
      !productPyexpr.includes(`os.environ[${JSON.stringify(key)}] =`)),
    productDiagRejected,
    nonProductProbeRejected,
    nonProductSamplesRejected,
    canonicalSamplesRejected,
    invalidSamplesRejected,
    canonicalSetupAssignments.every((assignment) => pyexpr.includes(assignment)),
    pyexpr.includes(`_bw_ea_setup_schema = ${JSON.stringify(EEVEE_SETUP_SCHEMA)}`),
    validateEeveeSetupReceipt(setupSample).ok,
    validateEeveeSetupReceipt(float32SetupSample).ok,
    validateEeveeSetupReceipt(canonicalSetupSample, { probeOperatorsUsed: true }).ok,
    !validateEeveeSetupReceipt(badSetupSample).ok,
    !validateEeveeSetupReceipt(outOfToleranceSetupSample).ok,
    pyexpr.includes('bpy.app.handlers.render_complete.append(_bw_ea_complete)'),
    manifestRow?.endsWith(`\t${FAIL_THRESHOLD}\t${FAIL_PERCENT}`),
    validLimitReceipt?.pass === true && validLimitReceipt.computePass && validLimitReceipt.colorPass,
    lowLimitReceipt?.pass === false,
    lowColorLimitReceipt?.pass === false,
    parseWebGpuPreinitReceipt('unrelated console line') === null,
    trustedPhysicalF12(trustedF12Sample),
    !trustedPhysicalF12([{ ...trustedF12Sample[0], isTrusted: false }]),
    !trustedPhysicalF12([...trustedF12Sample, ...trustedF12Sample]),
    exactHandlerCompletion(handlerSample),
    !exactHandlerCompletion({ ...handlerSample, complete_count: 2 }),
    !exactHandlerCompletion({ ...handlerSample, cancel_count: 1 }),
    exactRenderConfiguration(renderConfigurationSample),
    exactRenderConfiguration({
      render_sampling: { scene: 64, view_layer_override: 1, effective: 1 },
      view_transform: EXPECTED_VIEW_TRANSFORM,
      color_mode: EXPECTED_COLOR_MODE,
    }, 1, { requireViewLayerOverride: true }),
    !exactRenderConfiguration({
      ...renderConfigurationSample,
      render_sampling: { ...renderConfigurationSample.render_sampling, effective: 1 },
    }),
    !exactRenderConfiguration({
      ...renderConfigurationSample,
      view_transform: EXPECTED_VIEW_TRANSFORM === 'Standard' ? 'AgX' : 'Standard',
    }),
    !exactRenderConfiguration({
      ...renderConfigurationSample,
      color_mode: EXPECTED_COLOR_MODE === 'RGB' ? 'RGBA' : 'RGB',
    }),
    validateCanonicalProbeReceipt(canonicalProbeSample).ok,
    !validateCanonicalProbeReceipt({ ...canonicalProbeSample, state: 'BAKING_ACTIVE' }).ok,
    !validateCanonicalProbeReceipt({ ...canonicalProbeSample, cache_ready: false }).ok,
    !validateCanonicalProbeReceipt({ ...canonicalProbeSample, job_completed: false }).ok,
    !validateCanonicalProbeReceipt({ ...canonicalProbeSample, bake_result: ['FINISHED'] }).ok,
    !validateCanonicalProbeReceipt({
      ...canonicalProbeSample,
      sphere: { ...canonicalProbeSample.sphere, scale: [4, 5, 2] },
    }).ok,
    validateCanonicalProbeReceipt({
      schema: CANONICAL_PROBE_SCHEMA,
      requested: true,
      state: 'SKIPPED_BY_SCENE',
      skip_probes: true,
      operators_used: false,
    }).ok,
    Object.keys(localShellReceipts()).sort().join(',') === 'boot,fileBridge,index,preinit,windowed',
    DEFAULT_PROBE_MS === 30000,
    canonicalProbePreparationTerminal(canonicalProbeSample),
    !canonicalProbePreparationTerminal({ state: 'BAKING_MODAL' }),
    !canonicalProbePreparationTerminal({ state: 'FAILED' }),
    canonicalProbePreparationBlockingReason({ state: 'BAKING_ACTIVE' }) === null,
    canonicalProbePreparationBlockingReason(
      { state: 'BAKING_ACTIVE' }, { pageErrors: ['RuntimeError: Aborted()'] }) ===
      'page/runtime error: RuntimeError: Aborted()',
    canonicalProbePreparationBlockingReason(
      { state: 'BAKING_ACTIVE' }, { gpuErrors: ['WGPU device lost'] }) ===
      'GPU/browser error: WGPU device lost',
    canonicalProbePreparationBlockingReason(
      { state: 'FAILED', error: 'shader compile failed' }) ===
      'probe receipt entered FAILED: shader compile failed',
    driverSource.indexOf("mark('canonical probe preparation terminal and F12-unblocked'") <
      driverSource.indexOf("await page.keyboard.press('F12', { delay: 100 })"),
    strippedDiagnosticEnvironmentAbsent(cleanProductEnvironmentSample),
    !strippedDiagnosticEnvironmentAbsent({
      stripped_diag_envs: { ...cleanProductEnvironmentSample.stripped_diag_envs, BW_READBACK_CAPTURE: '1' },
    }),
    validateWmTickProgress('100', '101'),
    !validateWmTickProgress('100', '100'),
    !validateWmTickProgress(null, '101'),
    sha256Bytes(readFileSync(BLEND_HOST)) === '39db218041e5d1f8338a666f78e3d06d93f6e7cbd1029390c8e1c646c7ddea5a',
    sha256Bytes(readFileSync(GOLDEN_HOST)) === '1677fddfb42b592e62be8e29b6aa1bbcb575d3fd45e890e89901d28b8d269ca5',
  ];
  if (checks.every(Boolean)) {
    console.log(`SELF_CHECK_PASS probe=f12-eevee schema=${ASYNC.schemaStatus} product=marker-independent canonical_probes=modal-job-cache-blocking sample_override=positive-product-diagnostic diagnostic=legacy physical_f12=one bpy_render_op=none opfs=startup limits=compute+color comparator=${FAIL_THRESHOLD}/${FAIL_PERCENT}`);
    process.exit(0);
  }
  console.error(`SELF_CHECK_FAIL probe=f12-eevee accepted=${JSON.stringify(accepted.errors)} no_write=${JSON.stringify(withoutWrite.errors)} wrong_order=${JSON.stringify(wrongOrder.errors)} wrong_worker=${JSON.stringify(wrongWorker.errors)} failed=${JSON.stringify(failed.errors)} py_syntax=${JSON.stringify(pySyntax.stderr || pySyntax.error?.message || '')} product_py_syntax=${JSON.stringify(productPySyntax.stderr || productPySyntax.error?.message || '')} canonical_probe_py_syntax=${JSON.stringify(canonicalProbePySyntax.stderr || canonicalProbePySyntax.error?.message || '')} one_sample_py_syntax=${JSON.stringify(oneSamplePySyntax.stderr || oneSamplePySyntax.error?.message || '')}`);
  process.exit(1);
}

const PORT = Number.parseInt(process.argv[2] || '8151', 10);
const RENDER_MS = Number.parseInt(process.argv[3] || String(DEFAULT_RENDER_MS), 10);
const DEFAULT_LABEL = SAMPLE_DIAGNOSTIC_MODE ?
  `eevee-principled-default-f12-samples-${RENDER_SAMPLES_OVERRIDE_RAW}` :
  'eevee-principled-default-f12';
const LABEL = (process.argv[4] || DEFAULT_LABEL).trim();
if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) {
  console.error(`invalid port: ${process.argv[2] || ''}`);
  process.exit(2);
}
if (!Number.isInteger(RENDER_MS) || RENDER_MS < 2000) {
  console.error(`invalid timeout_ms: ${process.argv[3] || ''}`);
  process.exit(2);
}
if (CANONICAL_PROBES && (!Number.isInteger(PROBE_MS) || PROBE_MS < 2000)) {
  console.error(`invalid BW_EEVEE_CANONICAL_PROBE_TIMEOUT_MS: ${process.env.BW_EEVEE_CANONICAL_PROBE_TIMEOUT_MS || ''}`);
  process.exit(2);
}
if (EXPORT_BAKED_BLEND && (!PRODUCT_MODE || !CANONICAL_PROBES)) {
  console.error('BW_EEVEE_EXPORT_BAKED_BLEND requires product smoke with canonical probes on');
  process.exit(2);
}
if (PROBE_BAKE_DIAGNOSTIC_MODE &&
    (!/^\d+$/.test(PROBE_BAKE_SAMPLES_OVERRIDE_RAW) ||
      !Number.isSafeInteger(PROBE_BAKE_SAMPLES_OVERRIDE) || PROBE_BAKE_SAMPLES_OVERRIDE < 1))
{
  console.error(`invalid BW_EEVEE_PROBE_BAKE_SAMPLES_OVERRIDE: ${PROBE_BAKE_SAMPLES_OVERRIDE_RAW || ''}`);
  process.exit(2);
}
if (PROBE_BAKE_DIAGNOSTIC_MODE && (!PRODUCT_MODE || !CANONICAL_PROBES)) {
  console.error('BW_EEVEE_PROBE_BAKE_SAMPLES_OVERRIDE requires product smoke with canonical probes on');
  process.exit(2);
}
if (SAMPLE_DIAGNOSTIC_MODE &&
    (!/^\d+$/.test(RENDER_SAMPLES_OVERRIDE_RAW) ||
      !Number.isSafeInteger(RENDER_SAMPLES_OVERRIDE) || RENDER_SAMPLES_OVERRIDE < 1))
{
  console.error(`invalid BW_EEVEE_RENDER_SAMPLES_OVERRIDE: ${RENDER_SAMPLES_OVERRIDE_RAW || ''}`);
  process.exit(2);
}
if (SAMPLE_DIAGNOSTIC_MODE && (!PRODUCT_MODE || CANONICAL_PROBES)) {
  console.error('BW_EEVEE_RENDER_SAMPLES_OVERRIDE requires product smoke with canonical probes off');
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
if (/bpy\.ops\.render/.test(pythonExpr)) throw new Error('driver invariant violated: bpy render operator in pyexpr');
const blendBytes = readFileSync(BLEND_HOST);
const blendB64 = blendBytes.toString('base64');
const blendSha256 = sha256Bytes(blendBytes);
const goldenBytes = readFileSync(GOLDEN_HOST);
const goldenSha256 = sha256Bytes(goldenBytes);
const canonicalProbeSourceReceipt = CANONICAL_PROBES ? (() => {
  const bytes = readFileSync(EEVEE_TEST_SCRIPT_HOST);
  return { path: EEVEE_TEST_SCRIPT_HOST, sha256: sha256Bytes(bytes), bytes: bytes.length };
})() : null;
const binaryReceipts = Object.fromEntries(Object.entries(BINARY_PATHS).map(([name, path]) => {
  const bytes = readFileSync(path);
  return [name, { path, sha256: sha256Bytes(bytes), bytes: bytes.length }];
}));
const expectedServedShell = localShellReceipts();
const url = `${base}/windowed.html?gate=${WIDTH}x${HEIGHT}&args=${encodeURIComponent(BLEND_GUEST)}&pyexpr=${encodeURIComponent(pythonExpr)}`;
const prefix = `${OUTDIR}/${LABEL}`;
const consolePath = `${prefix}-console.log`;
const manifestPath = `${prefix}-manifest.json`;
const screenshotPath = `${prefix}-${WIDTH}x${HEIGHT}.png`;
const renderPath = `${prefix}-render-result.png`;
const comparatorPath = `${prefix}-comparator.txt`;
const bakedBlendPath = `${prefix}-browser-baked.blend`;

mkdirSync(OUTDIR, { recursive: true });
for (const path of [
  consolePath,
  manifestPath,
  screenshotPath,
  `${screenshotPath}.license`,
  renderPath,
  `${renderPath}.license`,
  comparatorPath,
  `${comparatorPath}.license`,
  ...(EXPORT_BAKED_BLEND ? [bakedBlendPath] : []),
]) {
  rmSync(path, { force: true });
}
const startedAt = Date.now();
const marks = [];
const consoleEntries = [];
const asyncEvents = [];
const acceptLines = [];
const gpuErrors = [];
const pageErrors = [];
const heartbeats = [];
let pageCrashed = false;
let heartbeatError = null;
let stopHeartbeat = false;
let runError = null;
let seedReceipt = null;
let gateReceipt = null;
let servedShell = null;
let configReceipt = null;
let preReceipt = null;
let probeReceipt = null;
let probeValidation = null;
let probeReadyAtMs = null;
let bakedBlendReceipt = null;
let doneReceipt = null;
let physicalKeyReceipt = null;
let webGpuPreinitReceipt = null;
let topology = null;
let tickBeforeF12 = null;
let tickAfterRender = null;
let pngStats = null;
let comparator = null;
let comparatorText = '';
let screenshotSha256 = null;
let renderSha256 = null;
let screenshotCaptured = false;
let renderCaptured = false;

function mark(label, extra = {}) {
  const entry = { label, iso: new Date().toISOString(), atMs: elapsedMs(startedAt), ...extra };
  marks.push(entry);
  console.log(`[${entry.iso}] ${label}`);
}

function firstBlockingReason() {
  if (pageCrashed) return 'page crashed';
  if (pageErrors.length) return `page error: ${pageErrors[0]}`;
  if (gpuErrors.length) return `GPU/browser error: ${gpuErrors[0]}`;
  const asyncFailure = asyncEvents.find((event) =>
    ASYNC.failureStates.has(event.state) || event.fields.status === 'failed');
  if (asyncFailure) return `async failure marker: ${asyncFailure.text}`;
  const handlerFailure = acceptLines.find((line) =>
    /phase=(?:EXPORT_FAIL|RENDER_CANCEL)\b/.test(line));
  if (handlerFailure) return `render handler failure: ${handlerFailure}`;
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
  const atMs = elapsedMs(startedAt);
  const index = consoleEntries.length;
  consoleEntries.push(`[${new Date().toISOString()}] [console:${message.type()}] ${text}`);
  const event = parseAsyncLine(text, atMs, index);
  if (event) asyncEvents.push(event);
  const preinitReceipt = parseWebGpuPreinitReceipt(text);
  if (preinitReceipt) webGpuPreinitReceipt = preinitReceipt;
  if (text.startsWith('BW_EEVEE_ACCEPT ')) acceptLines.push(text);
  const benignDeviceReceipt = text.startsWith(WGPU_PREINIT_PREFIX);
  const markerOnStderr = text.startsWith(ASYNC.prefix) || text.startsWith('BW_EEVEE_ACCEPT ');
  if (!benignDeviceReceipt && !markerOnStderr &&
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
  mark('OPFS seed begin', { opfsName: OPFS_NAME, hostBytes: blendBytes.length, blendSha256 });
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
    const sha256 = [...digest].map((byte) => byte.toString(16).padStart(2, '0')).join('');
    return { ok: file.size === bytes.length, name, size: file.size, sha256 };
  }, { b64: blendB64, name: OPFS_NAME });
  if (!seedReceipt.ok || seedReceipt.size !== blendBytes.length || seedReceipt.sha256 !== blendSha256) {
    throw new Error(`OPFS seed mismatch: ${JSON.stringify(seedReceipt)}`);
  }
  mark('OPFS seed verified', seedReceipt);

  const startupTimeoutMs = CANONICAL_PROBES ? Math.max(BOOT_MS, PROBE_MS) : BOOT_MS;
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: startupTimeoutMs });
  servedShell = await captureServedShell(page, expectedServedShell);
  await page.waitForFunction(
    () => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'),
    undefined,
    { timeout: startupTimeoutMs },
  );
  mark('WM_main reached');
  const preinitReceiptDeadline = Date.now() + 5000;
  while (!webGpuPreinitReceipt && Date.now() < preinitReceiptDeadline) {
    await sleep(25);
  }
  if (webGpuPreinitReceipt?.pass !== true) {
    throw new Error(
      `WebGPU compute/color device-limit receipt invalid: ${JSON.stringify(webGpuPreinitReceipt)}`);
  }
  mark('WebGPU compute/color device limits verified', webGpuPreinitReceipt);
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
  configReceipt = await readJsonIfPresent(page, CONFIG_GUEST);
  if (CANONICAL_PROBES) {
    probeReceipt = await readJsonIfPresent(page, PROBE_GUEST);
    const blockingReason = canonicalProbePreparationBlockingReason(
      probeReceipt, { pageCrashed, pageErrors, gpuErrors });
    if (blockingReason) {
      throw new Error(
        `canonical probe preparation failed before terminal receipt: ${blockingReason}; ` +
        `receipt=${JSON.stringify(probeReceipt)}`);
    }
  }
  const configDeadline = Date.now() + (CANONICAL_PROBES ? PROBE_MS : 30000);
  while ((!configReceipt ||
          (CANONICAL_PROBES && !canonicalProbePreparationTerminal(probeReceipt))) &&
         Date.now() < configDeadline)
  {
    await sleep(50);
    configReceipt ||= await readJsonIfPresent(page, CONFIG_GUEST);
    if (CANONICAL_PROBES) {
      probeReceipt = await readJsonIfPresent(page, PROBE_GUEST);
      const blockingReason = canonicalProbePreparationBlockingReason(
        probeReceipt, { pageCrashed, pageErrors, gpuErrors });
      if (blockingReason) {
        throw new Error(
          `canonical probe preparation failed before terminal receipt: ${blockingReason}; ` +
          `receipt=${JSON.stringify(probeReceipt)}`);
      }
    }
  }
  if (CANONICAL_PROBES &&
      (!configReceipt || !canonicalProbePreparationTerminal(probeReceipt)))
  {
    throw new Error(
      `canonical probe preparation timeout after ${PROBE_MS} ms: ${JSON.stringify(probeReceipt)}`);
  }
  if (CANONICAL_PROBES && !probeReceipt) {
    probeReceipt = configReceipt?.probe_preparation || null;
  }
  probeValidation = CANONICAL_PROBES ?
    validateCanonicalProbeReceipt(probeReceipt, EXPECTED_PROBE_BAKE_SAMPLES) :
      { ok: true, errors: [], state: 'DISABLED' };
  const probeOperatorsUsed = CANONICAL_PROBES && probeReceipt?.operators_used === true;
  const sceneSetup = validateEeveeSetupReceipt(
    configReceipt?.upstream_setup, { probeOperatorsUsed });
  const expectedAsyncEnv = PRODUCT_MODE ? null : ASYNC.envValue;
  if (configReceipt?.status !== 'ARMED' || configReceipt.engine !== 'BLENDER_EEVEE' ||
      JSON.stringify(configReceipt.resolution) !== JSON.stringify([RENDER_WIDTH, RENDER_HEIGHT]) ||
      configReceipt.blend !== BLEND_GUEST || configReceipt.async_env !== expectedAsyncEnv ||
      (PRODUCT_MODE && !strippedDiagnosticEnvironmentAbsent(configReceipt)) ||
      !exactRenderConfiguration(configReceipt, EXPECTED_RENDER_SAMPLES, {
        requireViewLayerOverride: SAMPLE_DIAGNOSTIC_MODE,
      }) ||
      !probeValidation.ok ||
      !sceneSetup.ok)
  {
    throw new Error(
      `startup/config receipt invalid: ${JSON.stringify(configReceipt)} ` +
      `setup=${sceneSetup.errors.join('; ')} probes=${probeValidation.errors.join('; ')}`,
    );
  }
  if (CANONICAL_PROBES) {
    probeReadyAtMs = elapsedMs(startedAt);
    mark('canonical probe preparation terminal and F12-unblocked', {
      probeState: probeReceipt.state,
      probeOperatorsUsed,
      bakeResult: probeReceipt.bake_result,
    });
    if (EXPORT_BAKED_BLEND) {
      if (probeReceipt.baked_blend_path !== BAKED_BLEND_GUEST ||
          !Number.isSafeInteger(probeReceipt.baked_blend_size) ||
          probeReceipt.baked_blend_size <= 0 ||
          JSON.stringify(probeReceipt.save_result) !== JSON.stringify(['FINISHED']))
      {
        throw new Error(`browser-baked blend receipt invalid: ${JSON.stringify(probeReceipt)}`);
      }
      const bakedBlendBase64 = await page.evaluate((guestPath) => {
        const bytes = window.__bwModule.FS.readFile(guestPath);
        let binary = '';
        for (let offset = 0; offset < bytes.length; offset += 0x8000) {
          binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
        }
        return btoa(binary);
      }, BAKED_BLEND_GUEST);
      const bakedBlendBytes = Buffer.from(bakedBlendBase64, 'base64');
      if (bakedBlendBytes.length !== probeReceipt.baked_blend_size) {
        throw new Error(
          `browser-baked blend size mismatch: receipt=${probeReceipt.baked_blend_size} ` +
          `actual=${bakedBlendBytes.length}`);
      }
      writeFileSync(bakedBlendPath, bakedBlendBytes);
      bakedBlendReceipt = {
        guestPath: BAKED_BLEND_GUEST,
        hostPath: bakedBlendPath,
        bytes: bakedBlendBytes.length,
        sha256: sha256Bytes(bakedBlendBytes),
      };
      mark('browser-baked blend extracted before F12', bakedBlendReceipt);
    }
  }
  mark('startup file and render config verified', configReceipt);

  /* The probe-skipped row can publish its ARMED receipt from the same startup timer turn that
   * finishes loading the .blend. A trusted browser key delivered before that turn returns is
   * visible to JavaScript but is not consumed by Blender's next WM event pump. Wake the idle loop
   * with the same harmless focus/click prelude used by the product path, then require one real WM
   * turn after the terminal setup receipt before dispatching the single F12. */
  const canvas = page.locator('#canvas');
  await page.bringToFront();
  await canvas.focus();
  await page.keyboard.press('Escape', { delay: 50 });
  await canvas.click({ position: { x: Math.floor(WIDTH / 2), y: Math.floor(HEIGHT / 2) } });
  await canvas.focus();

  const setupReceiptTick = await readWmTick(page);
  const setupTurnDeadline = Date.now() + 60000;
  let postSetupTick = setupReceiptTick;
  while (postSetupTick === setupReceiptTick && Date.now() < setupTurnDeadline) {
    await sleep(20);
    postSetupTick = await readWmTick(page);
  }
  if (postSetupTick === setupReceiptTick) {
    throw new Error(`WM turn did not advance after setup receipt: tick=${setupReceiptTick}`);
  }
  mark('post-setup WM turn observed', { setupReceiptTick, postSetupTick });

  await page.waitForTimeout(250);
  const focusReceipt = await page.evaluate(() => ({
    hasFocus: document.hasFocus(),
    activeId: document.activeElement?.id || null,
  }));
  if (!focusReceipt.hasFocus || focusReceipt.activeId !== 'canvas') {
    throw new Error(`canvas focus unavailable: ${JSON.stringify(focusReceipt)}`);
  }
  await page.evaluate(() => {
    window.__bwEeveeF12KeyEvents = [];
    window.addEventListener('keydown', (event) => {
      if (event.key === 'F12' || event.code === 'F12') {
        window.__bwEeveeF12KeyEvents.push({
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

  heartbeatPromise = (async () => {
    while (!stopHeartbeat) {
      try {
        heartbeats.push({ atMs: elapsedMs(startedAt), tick: await readWmTick(page) });
      }
      catch (error) {
        if (!stopHeartbeat) heartbeatError = error.stack || error.message || String(error);
        return;
      }
      await sleep(HEARTBEAT_MS);
    }
  })();

  tickBeforeF12 = await readWmTick(page);
  mark('physical F12 dispatch', {
    tickBefore: tickBeforeF12,
    method: 'page.keyboard.press(F12)',
    mode: PRODUCT_MODE ? 'product-marker-independent' : 'diagnostic-marker',
  });
  await page.keyboard.press('F12', { delay: 100 });
  physicalKeyReceipt = await page.evaluate(() => window.__bwEeveeF12KeyEvents || []);

  const preDeadline = Date.now() + 10000;
  while (Date.now() < preDeadline) {
    const blocker = firstBlockingReason();
    if (blocker) throw new Error(blocker);
    preReceipt = await readJsonIfPresent(page, PRE_GUEST);
    if (preReceipt) break;
    await sleep(20);
  }
  if (preReceipt?.status !== 'RENDER_PRE' || preReceipt.count !== 1 ||
      preReceipt.engine !== 'BLENDER_EEVEE' || preReceipt.blend !== BLEND_GUEST)
  {
    throw new Error(`Blender render_pre receipt missing or invalid: ${JSON.stringify(preReceipt)}`);
  }

  const renderDeadline = Date.now() + RENDER_MS;
  while (Date.now() < renderDeadline) {
    const blocker = firstBlockingReason();
    if (blocker) throw new Error(blocker);
    doneReceipt = await readJsonIfPresent(page, DONE_GUEST);
    const asyncDone = PRODUCT_MODE ||
      asyncEvents.some((event) => event.state === ASYNC.terminalState);
    if (doneReceipt && asyncDone) break;
    await sleep(50);
  }
  if (!doneReceipt) throw new Error(`render completion handler timeout after ${RENDER_MS} ms`);
  if (!PRODUCT_MODE && !asyncEvents.some((event) => event.state === ASYNC.terminalState)) {
    throw new Error(`async marker timeout after ${RENDER_MS} ms; states=${asyncEvents.map((event) => event.state).join('>')}`);
  }
  await page.waitForTimeout(500);
  const blocker = firstBlockingReason();
  if (blocker) throw new Error(blocker);

  physicalKeyReceipt = await page.evaluate(() => window.__bwEeveeF12KeyEvents || []);
  const physicalF12 = trustedPhysicalF12(physicalKeyReceipt);
  if (!physicalF12) throw new Error(`physical F12 receipt invalid: ${JSON.stringify(physicalKeyReceipt)}`);
  if (!exactHandlerCompletion(doneReceipt, EXPECTED_RENDER_SAMPLES)) {
    throw new Error(`render handler receipt invalid: ${JSON.stringify(doneReceipt)}`);
  }
  topology = PRODUCT_MODE ? productTopologyReceipt() : validateAsync(asyncEvents, heartbeats);
  if (!topology.ok) throw new Error(`async topology invalid: ${topology.errors.join('; ')}`);

  const captured = await page.evaluate(async ({ path, width, height }) => {
    const bytes = window.__bwModule.FS.readFile(path);
    const blob = new Blob([bytes], { type: 'image/png' });
    const bitmap = await createImageBitmap(blob);
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(bitmap, 0, 0);
    const pixels = context.getImageData(0, 0, bitmap.width, bitmap.height).data;
    let nonBlackPixels = 0;
    let rgbMax = 0;
    let finitePixels = true;
    for (let offset = 0; offset < pixels.length; offset += 4) {
      finitePixels = finitePixels && Number.isFinite(pixels[offset]) &&
        Number.isFinite(pixels[offset + 1]) && Number.isFinite(pixels[offset + 2]) &&
        Number.isFinite(pixels[offset + 3]);
      const pixelMax = Math.max(pixels[offset], pixels[offset + 1], pixels[offset + 2]);
      if (pixelMax !== 0) nonBlackPixels += 1;
      rgbMax = Math.max(rgbMax, pixelMax);
    }
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return {
      width: bitmap.width,
      height: bitmap.height,
      byteLength: bytes.length,
      nonBlackPixels,
      nonBlackFraction: nonBlackPixels / (bitmap.width * bitmap.height),
      rgbMax,
      finitePixels,
      b64: btoa(binary),
    };
  }, { path: PNG_GUEST, width: RENDER_WIDTH, height: RENDER_HEIGHT });
  const renderBytes = Buffer.from(captured.b64, 'base64');
  delete captured.b64;
  pngStats = captured;
  /* Preserve the exact produced PNG even when the nonblack gate rejects it;
   * black-output failures need an inspectable receipt, not only a number. */
  writeFileSync(renderPath, renderBytes);
  renderCaptured = true;
  renderSha256 = sha256Bytes(renderBytes);
  writeFileSync(`${renderPath}.license`, CC0);
  if (pngStats.width !== RENDER_WIDTH || pngStats.height !== RENDER_HEIGHT ||
      pngStats.byteLength !== renderBytes.length || pngStats.nonBlackPixels === 0 ||
      pngStats.nonBlackFraction === 0 || pngStats.rgbMax === 0 || !pngStats.finitePixels)
  {
    throw new Error(`render PNG is invalid or black: ${JSON.stringify(pngStats)}`);
  }
  mark('nonblack Render Result exported', { renderPath, renderSha256, pngStats });

  if (SAMPLE_DIAGNOSTIC_MODE) {
    comparatorText =
      `SKIPPED: render-sample diagnostic effective=${EXPECTED_RENDER_SAMPLES}; ` +
      'the pinned M6 golden comparator is not an acceptance gate for this verdict.\n';
    comparator = {
      skipped: true,
      pass: null,
      reason: 'render-sample diagnostic is output/error evidence, not golden acceptance',
    };
    writeFileSync(comparatorPath, comparatorText);
    writeFileSync(`${comparatorPath}.license`, CC0);
    mark('pinned M6 comparator intentionally skipped for sample diagnostic', comparator);
  }
  else {
    const diff = spawnSync(
      OIIOTOOL,
      [GOLDEN_HOST, renderPath, '--fail', FAIL_THRESHOLD, '--failpercent', FAIL_PERCENT, '--diff'],
      { encoding: 'utf8' },
    );
    comparatorText = `${diff.stdout || ''}${diff.stderr || ''}`;
    comparator = parseComparator(comparatorText, diff.status);
    writeFileSync(comparatorPath, comparatorText);
    writeFileSync(`${comparatorPath}.license`, CC0);
    if (diff.error) throw new Error(`oiiotool failed to launch: ${diff.error.message}`);
    if (!comparator.pass) {
      throw new Error(`pixel comparator failed rc=${diff.status} max=${comparator.maxError} over=${comparator.percentOver}`);
    }
    mark('pinned M6 comparator passed', comparator);
  }

  const rect = gateReceipt.rect;
  await page.mouse.move(Math.round(rect.x + 16), Math.round(rect.y + rect.height - 16));
  await page.waitForTimeout(250);
  tickAfterRender = await readWmTick(page);
  if (PRODUCT_MODE && !validateWmTickProgress(tickBeforeF12, tickAfterRender)) {
    throw new Error(
      `WM tick did not advance after render: before=${tickBeforeF12} after=${tickAfterRender}`);
  }
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
  mark('acceptance screenshot captured', { screenshotPath, screenshotSha256 });
}
catch (error) {
  runError = error.stack || error.message || String(error);
  console.error(runError);
  if (!physicalKeyReceipt && !pageCrashed) {
    try {
      physicalKeyReceipt = await page.evaluate(() => window.__bwEeveeF12KeyEvents || []);
    }
    catch {
      /* The page may already be gone; the error and crash receipts remain authoritative. */
    }
  }
  if (!topology) {
    topology = PRODUCT_MODE ? productTopologyReceipt() : validateAsync(asyncEvents, heartbeats);
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
  stopHeartbeat = true;
  if (heartbeatPromise) await heartbeatPromise;
  await context.close();
  await browser.close();
}

const consoleText = `${consoleEntries.join('\n')}\n`;
writeFileSync(consolePath, consoleText);
writeFileSync(`${consolePath}.license`, CC0);
const consoleSha256 = sha256Bytes(consoleText);
const exactGate = gateReceipt?.backingWidth === WIDTH && gateReceipt?.backingHeight === HEIGHT &&
  gateReceipt?.cssWidth === WIDTH && gateReceipt?.cssHeight === HEIGHT &&
  gateReceipt?.dpr === 1 && gateReceipt?.gateClass === true &&
  gateReceipt?.crossOriginIsolated === true;
const physicalF12 = trustedPhysicalF12(physicalKeyReceipt);
const renderPreStarted = preReceipt?.status === 'RENDER_PRE' && preReceipt.count === 1 &&
  preReceipt.engine === 'BLENDER_EEVEE' && preReceipt.blend === BLEND_GUEST;
const handlerComplete = exactHandlerCompletion(doneReceipt, EXPECTED_RENDER_SAMPLES);
const wmTickAdvanced = validateWmTickProgress(tickBeforeF12, tickAfterRender);
const probeOperatorsUsed = CANONICAL_PROBES && probeReceipt?.operators_used === true;
const finalSceneSetup = validateEeveeSetupReceipt(
  configReceipt?.upstream_setup, { probeOperatorsUsed });
const f12DispatchAtMs = marks.find((entry) => entry.label === 'physical F12 dispatch')?.atMs ?? null;
const noF12BeforeProbeTerminal = !CANONICAL_PROBES ||
  (probeReadyAtMs !== null && f12DispatchAtMs !== null && f12DispatchAtMs > probeReadyAtMs);
const accepted = !runError && !pageCrashed && pageErrors.length === 0 && gpuErrors.length === 0 &&
  !heartbeatError && webGpuPreinitReceipt?.pass === true && exactGate && physicalF12 &&
  renderPreStarted && handlerComplete && topology?.ok === true &&
  (!PRODUCT_MODE || wmTickAdvanced) &&
  (!CANONICAL_PROBES || probeValidation?.ok === true) && noF12BeforeProbeTerminal &&
  (!EXPORT_BAKED_BLEND || Boolean(bakedBlendReceipt?.sha256)) &&
  exactRenderConfiguration(configReceipt, EXPECTED_RENDER_SAMPLES, {
    requireViewLayerOverride: SAMPLE_DIAGNOSTIC_MODE,
  }) && finalSceneSetup.ok === true &&
  pngStats?.nonBlackPixels > 0 && pngStats?.finitePixels === true &&
  (SAMPLE_DIAGNOSTIC_MODE ? comparator?.skipped === true : comparator?.pass === true) &&
  renderCaptured &&
  screenshotCaptured && Boolean(renderSha256) && Boolean(screenshotSha256);
const manifest = {
  schema: 'blender-web.f12-eevee-acceptance.v4',
  verdict: accepted ?
    (SAMPLE_DIAGNOSTIC_MODE ? 'DIAGNOSTIC_PASS' : 'PASS') :
    (SAMPLE_DIAGNOSTIC_MODE ? 'DIAGNOSTIC_FAIL' : 'FAIL'),
  generatedAt: new Date().toISOString(),
  driver: { path: DRIVER_PATH, sha256: sha256Bytes(readFileSync(DRIVER_PATH)) },
  inputs: {
    blend: { hostPath: BLEND_HOST, guestPath: BLEND_GUEST, sha256: blendSha256, bytes: blendBytes.length },
    golden: { path: GOLDEN_HOST, sha256: goldenSha256 },
    shippingBinary: binaryReceipts,
    servedShell,
    expectedServedShell,
    canonicalProbeSource: canonicalProbeSourceReceipt,
  },
  server: { base, port: PORT, shell: 'platform_web/shell', bin: BIN_DIR },
  browser: {
    engine: 'playwright-chromium',
    headed: true,
    args: ['--enable-unsafe-webgpu', '--use-angle=metal', '--disable-dev-tools'],
  },
  webGpuPreinit: webGpuPreinitReceipt,
  invocation: {
    method: 'page.keyboard.press(F12)',
    count: physicalKeyReceipt?.length || 0,
    physicalTrustedF12: Boolean(physicalF12),
    bpyExecUsed: probeOperatorsUsed,
    bpyRenderOperatorUsed: false,
    bpySetupOperatorsPresent: CANONICAL_PROBES,
    bpySetupOperatorsExecuted: probeOperatorsUsed,
    pythonExprSha256: sha256Bytes(pythonExpr),
    pythonExprRenderOperatorAbsent: !/bpy\.ops\.render/.test(pythonExpr),
    pythonExprOperatorAbsent: !/\bbpy\.ops\./.test(pythonExpr),
    pythonRole: CANONICAL_PROBES ?
      'configure scene, synchronously prepare canonical probes, register passive render handlers, save Render Result' :
      'configure scene, register passive render handlers, save Render Result',
    keyReceipt: physicalKeyReceipt,
    renderPreReceipt: preReceipt,
  },
  asyncContract: {
    mode: PRODUCT_MODE ? 'product-marker-independent' : 'diagnostic-marker',
    prefix: ASYNC.prefix.trim(),
    environment: PRODUCT_MODE ? null : { key: ASYNC.envKey, value: ASYNC.envValue },
    schemaStatus: ASYNC.schemaStatus,
    successGrammar: ASYNC.successGrammar,
    exactKeys: ASYNC.exactKeys,
    result: topology,
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
  probePreparation: {
    requested: CANONICAL_PROBES,
    timeoutMs: CANONICAL_PROBES ? PROBE_MS : null,
    receiptPath: CANONICAL_PROBES ? PROBE_GUEST : null,
    receipt: probeReceipt,
    validation: probeValidation,
    readyAtMs: probeReadyAtMs,
    f12DispatchAtMs,
    noF12BeforeTerminal: noF12BeforeProbeTerminal,
    exportedBakedBlend: bakedBlendReceipt,
  },
  render: {
    engine: 'BLENDER_EEVEE',
    verdictClass: SAMPLE_DIAGNOSTIC_MODE ? 'sample-diagnostic' : 'acceptance',
    requestedSamplesOverride: RENDER_SAMPLES_OVERRIDE,
    expectedEffectiveSamples: EXPECTED_RENDER_SAMPLES,
    expectedViewTransform: EXPECTED_VIEW_TRANSFORM,
    expectedColorMode: EXPECTED_COLOR_MODE,
    resolution: [RENDER_WIDTH, RENDER_HEIGHT],
    configReceipt,
    completionReceipt: doneReceipt,
    handlerComplete,
    acceptLines,
    pngStats,
  },
  comparator: {
    acceptanceGate: !SAMPLE_DIAGNOSTIC_MODE,
    executable: SAMPLE_DIAGNOSTIC_MODE ? null : OIIOTOOL,
    argv: SAMPLE_DIAGNOSTIC_MODE ? null :
      [GOLDEN_HOST, renderPath, '--fail', FAIL_THRESHOLD, '--failpercent', FAIL_PERCENT, '--diff'],
    threshold: FAIL_THRESHOLD,
    failPercent: FAIL_PERCENT,
    result: comparator,
  },
  gate: { expected: `${WIDTH}x${HEIGHT}@1`, receipt: gateReceipt, exact: Boolean(exactGate) },
  heartbeat: {
    acceptanceRole: PRODUCT_MODE ? 'post-render-WM-liveness' : 'diagnostic-marker-correlation',
    intervalMs: HEARTBEAT_MS,
    sampleCount: heartbeats.length,
    samples: heartbeats,
    error: heartbeatError,
    betweenEnqueuedAndFirstTurn: topology?.uiHeartbeat || null,
    tickBeforeF12,
    tickAfterRender,
    advanced: wmTickAdvanced,
  },
  assertions: {
    opfsStartupFile: seedReceipt?.sha256 === blendSha256 && configReceipt?.blend === BLEND_GUEST,
    physicalTrustedF12ExactlyOnce: Boolean(physicalF12),
    blenderRenderPreStartedExactlyOnce: renderPreStarted,
    noBpyRenderOperator: !/bpy\.ops\.render/.test(pythonExpr),
    setupOperatorsPresentOnlyWhenCanonical:
      /\bbpy\.ops\./.test(pythonExpr) === CANONICAL_PROBES,
    computeWorkgroupStorageAtLeast32768: webGpuPreinitReceipt?.computePass === true,
    colorAttachmentBytesPerSampleAtLeast36:
      !PRODUCT_MODE || webGpuPreinitReceipt?.colorPass === true,
    exactRenderSamplesAndViewTransform: exactRenderConfiguration(
      configReceipt, EXPECTED_RENDER_SAMPLES,
      { requireViewLayerOverride: SAMPLE_DIAGNOSTIC_MODE }),
    canonicalUpstreamEeveeSetup: finalSceneSetup.ok === true,
    canonicalPassiveEeveeSetup: CANONICAL_PROBES ? null : finalSceneSetup.ok === true,
    canonicalProbePreparation: CANONICAL_PROBES ? probeValidation?.ok === true : null,
    canonicalBakedBlendExport:
      EXPORT_BAKED_BLEND ? Boolean(bakedBlendReceipt?.sha256) : null,
    noF12BeforeCanonicalProbeTerminal: CANONICAL_PROBES ? noF12BeforeProbeTerminal : null,
    exactAsyncSemanticOrder: PRODUCT_MODE ? null : topology?.ok === true,
    markerIndependentProductMode: PRODUCT_MODE,
    strippedDiagnosticEnvironmentAbsent:
      !PRODUCT_MODE || strippedDiagnosticEnvironmentAbsent(configReceipt),
    wmTickAdvancedAfterRender: PRODUCT_MODE ? wmTickAdvanced : null,
    renderHandlerCompletedExactlyOnce: handlerComplete,
    finitePng: pngStats?.finitePixels === true,
    nonBlack: pngStats?.nonBlackPixels > 0 && pngStats?.rgbMax > 0,
    comparatorPass: SAMPLE_DIAGNOSTIC_MODE ? null : comparator?.pass === true,
    comparatorIntentionallyNotAnAcceptanceGate:
      SAMPLE_DIAGNOSTIC_MODE ? comparator?.skipped === true : null,
    noGpuError: gpuErrors.length === 0,
    noPageError: pageErrors.length === 0,
    noPageCrash: !pageCrashed,
    noHeartbeatError: !heartbeatError,
    noRunError: !runError,
  },
  evidence: {
    console: { path: consolePath, sha256: consoleSha256, licensePath: `${consolePath}.license` },
    manifest: { path: manifestPath, licensePath: `${manifestPath}.license` },
    screenshot: {
      path: screenshotCaptured ? screenshotPath : null,
      sha256: screenshotSha256,
      licensePath: screenshotCaptured ? `${screenshotPath}.license` : null,
    },
    renderResult: {
      path: renderCaptured ? renderPath : null,
      sha256: renderSha256,
      licensePath: renderCaptured ? `${renderPath}.license` : null,
    },
    comparator: {
      path: comparatorText || comparator ? comparatorPath : null,
      sha256: comparatorText || comparator ? sha256Bytes(comparatorText) : null,
      licensePath: comparatorText || comparator ? `${comparatorPath}.license` : null,
    },
    browserBakedBlend: EXPORT_BAKED_BLEND ? bakedBlendReceipt : null,
  },
  failures: { runError, heartbeatError, pageCrashed, pageErrors, gpuErrors },
  marks,
};
writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
writeFileSync(`${manifestPath}.license`, CC0);

if (!accepted) {
  console.error(`${SAMPLE_DIAGNOSTIC_MODE ? 'F12_EEVEE_DIAGNOSTIC_FAIL' : 'F12_EEVEE_ACCEPT_FAIL'} manifest=${manifestPath} console=${consolePath}`);
  process.exit(1);
}
console.log(`${SAMPLE_DIAGNOSTIC_MODE ? 'F12_EEVEE_DIAGNOSTIC_PASS' : 'F12_EEVEE_ACCEPT_PASS'} manifest=${manifestPath} render=${renderPath} screenshot=${screenshotPath}`);
