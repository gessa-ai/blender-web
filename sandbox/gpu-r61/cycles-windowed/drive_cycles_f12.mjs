// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Physical-F12 Cycles-CPU acceptance rig. Blender's pinned factory startup
// file is seeded into OPFS and opened by startup argv, so no live open_mainfile
// can perturb render state.
// Python configures the already-loaded scene and installs passive render
// handlers; only Playwright's one trusted F12 event invokes the render.
//
// Start the normal COOP/COEP server separately, then run from the repo root:
//   BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin \
//   BLENDER_WEB_SHELL=$PWD/platform_web/shell \
//     /opt/homebrew/bin/bash scripts/serve-web.sh 8151
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/gpu-r61/cycles-windowed/drive_cycles_f12.mjs \
//       [port] [timeout_ms] [label]
//
// This is a browser/evidence driver only. It does not patch or build Blender.

import { spawnSync } from 'child_process';
import { createHash } from 'crypto';
import {
  closeSync, existsSync, mkdirSync, openSync, readFileSync, readdirSync, statSync, writeFileSync,
} from 'fs';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';

const ROOT = '/Users/paws/blender-web';
const DRIVER_PATH = fileURLToPath(import.meta.url);
const OUTDIR = `${ROOT}/sandbox/gpu-r61/cycles-windowed/evidence`;
const BLEND_HOST = `${ROOT}/upstream/release/datafiles/startup.blend`;
const GOLDEN_HOST = `${ROOT}/sandbox/m6-prep/wasm-first-render/native_ref/cube_.png`;
const OPFS_NAME = 'bw_cycles_factory_startup.blend';
const BLEND_GUEST = `/projects/${OPFS_NAME}`;
const PNG_GUEST = '/tmp/bw_cycles_factory_cube.png';
const CONFIG_GUEST = '/tmp/bw_cycles_factory_config.json';
const DONE_GUEST = '/tmp/bw_cycles_factory_done.json';
const WIDTH = 1280;
const HEIGHT = 720;
const RENDER_WIDTH = 64;
const RENDER_HEIGHT = 64;
const BOOT_MS = 300000;
const DEFAULT_RENDER_MS = 300000;
const HEARTBEAT_MS = 40;
const FAIL_THRESHOLD = '0.016';
const FAIL_PERCENT = '1';
const MIN_COMPUTE_WORKGROUP_STORAGE_SIZE = 32768;
const CYCLES_SETUP_SCHEMA = 'blender-web.cycles-windowed-factory-cube.v2';
const PRODUCT_MODE = process.env.BW_CYCLES_PRODUCT_SMOKE === '1';
const WGPU_PREINIT_PREFIX = '[bw] WM-worker WebGPU device pre-acquired (ADR-007);';
const OIIOTOOL = process.env.OIIOTOOL || '/opt/homebrew/bin/oiiotool';
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
const ADDON_HOST = `${ROOT}/upstream/intern/cycles/blender/addon`;
const ADDON_GUEST = '/bw/scripts/addons_core/cycles/__init__.py';
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
  schemaStatus: 'LIVE_LEGACY_ENGINE_SEMANTIC_ORDER_ROOT_CONFIRMED',
  successGrammar:
    'INVOKE>ENQUEUED(ok=1)>TURN>[WRITE]?>PIPELINE_TERMINAL>READY>WORKER_RETURN>QUEUE_DESTROY',
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

function sha256Tree(root) {
  const hash = createHash('sha256');
  const visit = (directory, prefix = '') => {
    for (const name of readdirSync(directory).sort()) {
      const path = `${directory}/${name}`;
      const relative = prefix ? `${prefix}/${name}` : name;
      const stat = statSync(path);
      if (stat.isDirectory()) visit(path, relative);
      else if (stat.isFile()) {
        hash.update(relative); hash.update('\0'); hash.update(readFileSync(path)); hash.update('\0');
      }
    }
  };
  visit(root);
  return hash.digest('hex');
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

  const finalTurn = take('TURN');
  if (finalTurn) requireExactKeys(finalTurn, 'TURN', errors);
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

  const wmEvents = [invoke, finalTurn, ready, queueDestroy].filter(Boolean);
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
  for (const turn of [finalTurn].filter(Boolean)) {
    if (turn.fields.same_wm !== '1' || turn.fields.abort !== '0') {
      errors.push(`TURN: same_wm/abort=${turn.fields.same_wm}/${turn.fields.abort}`);
    }
  }
  if (write && (write.fields.frame !== '1' || write.fields.status !== 'complete')) {
    errors.push(`WRITE: frame/status=${write.fields.frame}/${write.fields.status}`);
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

  /* Cycles is a legacy blocking render engine. Unlike EEVEE's render_step path,
   * it does not yield TURN/PENDING pairs while its CPU render is running. Keep
   * heartbeat samples as evidence, but do not misrepresent UI responsiveness as
   * an acceptance condition for Preview 0. */
  const uiHeartbeat = null;

  return {
    ok: errors.length === 0,
    errors,
    actualStates,
    sequence,
    wmThread,
    workerThread,
    yieldPairCount: 0,
    optionalWrite: Boolean(write),
    uiHeartbeat,
    gpuWorkIdentity: pipeline && finalTurn && ready ? {
      inferredWmThread: wmThread,
      enclosingTurnTick: finalTurn.fields.tick,
      readyTick: ready.fields.tick,
    } : null,
  };
}

function makePythonExpr() {
  return [
    'import bpy, os, json, math, sys',
    ...(PRODUCT_MODE ? [] : [
      `os.environ[${JSON.stringify(ASYNC.envKey)}] = ${JSON.stringify(ASYNC.envValue)}`,
    ]),
    'bpy.context.preferences.view.show_splash = False',
    '_bw_ca_scene = bpy.context.scene',
    'import _cycles',
    'import cycles',
    '_bw_ca_addon_was_registered = bool(cycles.CyclesRender.is_registered)',
    'if not _bw_ca_addon_was_registered:',
    '    cycles.register()',
    '_bw_ca_addon_registered = bool(cycles.CyclesRender.is_registered)',
    '_bw_ca_scene.render.engine = "CYCLES"',
    '_bw_ca_scene.view_settings.view_transform = "AgX"',
    '_bw_ca_scene.cycles.device = "CPU"',
    '_bw_ca_scene.cycles.samples = 16',
    '_bw_ca_scene.cycles.use_adaptive_sampling = False',
    '_bw_ca_scene.cycles.sampling_pattern = "AUTOMATIC"',
    'try:',
    '    _bw_ca_scene.cycles.use_denoising = False',
    'except Exception:',
    '    pass',
    '_bw_ca_scene.cycles.seed = 0',
    '_bw_ca_scene.render.threads_mode = "FIXED"',
    '_bw_ca_scene.render.threads = 1',
    `_bw_ca_scene.render.resolution_x = ${RENDER_WIDTH}`,
    `_bw_ca_scene.render.resolution_y = ${RENDER_HEIGHT}`,
    '_bw_ca_scene.render.resolution_percentage = 100',
    '_bw_ca_scene.render.image_settings.file_format = "PNG"',
    '_bw_ca_scene.render.image_settings.color_mode = "RGBA"',
    '_bw_ca_scene.frame_set(1)',
    '_bw_ca_device_types = list(_cycles.get_device_types())',
    '_bw_ca_devices = [list(item) for item in _cycles.available_devices("NONE")]',
    '_bw_ca_vendor_devices = [item for item in _bw_ca_devices if len(item) > 1 and item[1] != "CPU"]',
    `_bw_ca_png = ${JSON.stringify(PNG_GUEST)}`,
    `_bw_ca_done = ${JSON.stringify(DONE_GUEST)}`,
    `_bw_ca_config = ${JSON.stringify(CONFIG_GUEST)}`,
    `_bw_ca_setup_schema = ${JSON.stringify(CYCLES_SETUP_SCHEMA)}`,
    '_bw_ca_setup_receipt = {"schema":_bw_ca_setup_schema, "addon_file":cycles.__file__, "addon_was_registered":_bw_ca_addon_was_registered, "addon_registered":_bw_ca_addon_registered, "build_options_cycles":bool(bpy.app.build_options.cycles), "with_osl":bool(_cycles.with_osl), "with_embree":bool(_cycles.with_embree), "with_embree_gpu":bool(_cycles.with_embree_gpu), "device_types":_bw_ca_device_types, "devices":_bw_ca_devices, "vendor_devices":_bw_ca_vendor_devices, "engine":_bw_ca_scene.render.engine, "view_transform":_bw_ca_scene.view_settings.view_transform, "device":_bw_ca_scene.cycles.device, "samples":_bw_ca_scene.cycles.samples, "adaptive":_bw_ca_scene.cycles.use_adaptive_sampling, "sampling_pattern":_bw_ca_scene.cycles.sampling_pattern, "denoise":_bw_ca_scene.cycles.use_denoising, "seed":_bw_ca_scene.cycles.seed, "threads_mode":_bw_ca_scene.render.threads_mode, "threads":_bw_ca_scene.render.threads, "resolution":[_bw_ca_scene.render.resolution_x,_bw_ca_scene.render.resolution_y], "color_mode":_bw_ca_scene.render.image_settings.color_mode}',
    '_bw_ca_pre_count = 0',
    '_bw_ca_complete_count = 0',
    '_bw_ca_cancel_count = 0',
    '_bw_ca_export_armed = False',
    'def _bw_ca_write(path, obj):',
    '    tmp = path + ".tmp"',
    '    with open(tmp, "w") as f: json.dump(obj, f, sort_keys=True)',
    '    os.replace(tmp, path)',
    'def _bw_ca_pre(*_args):',
    '    global _bw_ca_pre_count',
    '    _bw_ca_pre_count += 1',
    '    print("BW_CYCLES_ACCEPT phase=RENDER_PRE count=%d" % _bw_ca_pre_count)',
    'def _bw_ca_export():',
    '    global _bw_ca_export_armed',
    '    try:',
    '        rr = bpy.data.images.get("Render Result")',
    '        if rr is None:',
    '            raise RuntimeError("Render Result missing")',
    '        rr.save_render(filepath=_bw_ca_png, scene=bpy.context.scene)',
    '        for win in bpy.context.window_manager.windows:',
    '            if not win.screen: continue',
    '            for area in win.screen.areas:',
    '                if area.type == "VIEW_3D":',
    '                    area.type = "IMAGE_EDITOR"',
    '                    area.spaces.active.image = rr',
    '        receipt = {"status":"OK", "engine":bpy.context.scene.render.engine, "resolution":[bpy.context.scene.render.resolution_x,bpy.context.scene.render.resolution_y], "blend":bpy.data.filepath, "pre_count":_bw_ca_pre_count, "complete_count":_bw_ca_complete_count, "cancel_count":_bw_ca_cancel_count, "png":_bw_ca_png, "png_size":os.path.getsize(_bw_ca_png), "setup":_bw_ca_setup_receipt}',
    '        _bw_ca_write(_bw_ca_done, receipt)',
    '        print("BW_CYCLES_ACCEPT phase=PNG_SAVED bytes=%d" % receipt["png_size"])',
    '    except Exception as e:',
    '        _bw_ca_write(_bw_ca_done, {"status":"FAIL", "error":repr(e), "pre_count":_bw_ca_pre_count, "complete_count":_bw_ca_complete_count, "cancel_count":_bw_ca_cancel_count})',
    '        print("BW_CYCLES_ACCEPT phase=EXPORT_FAIL error=%r" % e)',
    '    _bw_ca_export_armed = False',
    '    return None',
    'def _bw_ca_complete(*_args):',
    '    global _bw_ca_complete_count, _bw_ca_export_armed',
    '    _bw_ca_complete_count += 1',
    '    print("BW_CYCLES_ACCEPT phase=RENDER_COMPLETE count=%d" % _bw_ca_complete_count)',
    '    if not _bw_ca_export_armed:',
    '        _bw_ca_export_armed = True',
    '        bpy.app.timers.register(_bw_ca_export, first_interval=0.0)',
    'def _bw_ca_cancel(*_args):',
    '    global _bw_ca_cancel_count',
    '    _bw_ca_cancel_count += 1',
    '    _bw_ca_write(_bw_ca_done, {"status":"FAIL", "error":"render cancelled", "pre_count":_bw_ca_pre_count, "complete_count":_bw_ca_complete_count, "cancel_count":_bw_ca_cancel_count})',
    '    print("BW_CYCLES_ACCEPT phase=RENDER_CANCEL count=%d" % _bw_ca_cancel_count)',
    'bpy.app.handlers.render_pre.append(_bw_ca_pre)',
    'bpy.app.handlers.render_complete.append(_bw_ca_complete)',
    'bpy.app.handlers.render_cancel.append(_bw_ca_cancel)',
    '_bw_ca_write(_bw_ca_config, {"status":"ARMED", "engine":_bw_ca_scene.render.engine, "resolution":[_bw_ca_scene.render.resolution_x,_bw_ca_scene.render.resolution_y], "blend":bpy.data.filepath, "async_env":os.environ.get(' + JSON.stringify(ASYNC.envKey) + '), "setup":_bw_ca_setup_receipt})',
    'print("BW_CYCLES_ACCEPT phase=ARMED engine=%s res=%dx%d blend=%s" % (_bw_ca_scene.render.engine, _bw_ca_scene.render.resolution_x, _bw_ca_scene.render.resolution_y, bpy.data.filepath))',
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

function parseWebGpuPreinitReceipt(text) {
  if (!text.startsWith(WGPU_PREINIT_PREFIX)) return null;
  const readLimit = (key) => {
    const match = new RegExp(`(?:^|\\s)${key}=(\\d+)(?:\\s|$)`).exec(text);
    return match ? Number.parseInt(match[1], 10) : null;
  };
  const adapter = readLimit('adapterMaxComputeWorkgroupStorageSize');
  const requested = readLimit('requestedMaxComputeWorkgroupStorageSize');
  const device = readLimit('deviceMaxComputeWorkgroupStorageSize');
  const pass = Number.isInteger(adapter) && Number.isInteger(requested) &&
    Number.isInteger(device) && adapter >= MIN_COMPUTE_WORKGROUP_STORAGE_SIZE &&
    requested >= MIN_COMPUTE_WORKGROUP_STORAGE_SIZE && requested <= adapter &&
    device >= requested;
  return {
    adapterMaxComputeWorkgroupStorageSize: adapter,
    requestedMaxComputeWorkgroupStorageSize: requested,
    deviceMaxComputeWorkgroupStorageSize: device,
    requiredMinimum: MIN_COMPUTE_WORKGROUP_STORAGE_SIZE,
    pass,
    line: text,
  };
}

function validateCyclesSetupReceipt(setup) {
  const errors = [];
  const equal = (actual, expected, label) => {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      errors.push(`${label}=${JSON.stringify(actual)} expected=${JSON.stringify(expected)}`);
    }
  };
  if (setup?.schema !== CYCLES_SETUP_SCHEMA) errors.push(`schema=${setup?.schema}`);
  if (setup?.addon_file !== ADDON_GUEST) errors.push(`addon_file=${setup?.addon_file}`);
  if (typeof setup?.addon_was_registered !== 'boolean') {
    errors.push(`addon_was_registered=${setup?.addon_was_registered}`);
  }
  if (setup?.addon_registered !== true) errors.push(`addon_registered=${setup?.addon_registered}`);
  if (setup?.build_options_cycles !== true) {
    errors.push(`build_options_cycles=${setup?.build_options_cycles}`);
  }
  for (const key of ['with_osl', 'with_embree', 'with_embree_gpu']) {
    if (setup?.[key] !== false) errors.push(`${key}=${setup?.[key]}`);
  }
  equal(setup?.device_types, [false, false, false, false, false, false], 'device_types');
  if (!Array.isArray(setup?.devices) || setup.devices.length < 1 ||
      setup.devices.some((device) => !Array.isArray(device) || device[1] !== 'CPU'))
  {
    errors.push(`devices=${JSON.stringify(setup?.devices)}`);
  }
  equal(setup?.vendor_devices, [], 'vendor_devices');
  if (setup?.engine !== 'CYCLES') errors.push(`engine=${setup?.engine}`);
  if (setup?.view_transform !== 'AgX') errors.push(`view_transform=${setup?.view_transform}`);
  if (setup?.device !== 'CPU') errors.push(`device=${setup?.device}`);
  if (setup?.samples !== 16) errors.push(`samples=${setup?.samples}`);
  if (setup?.adaptive !== false) errors.push(`adaptive=${setup?.adaptive}`);
  if (setup?.sampling_pattern !== 'AUTOMATIC') {
    errors.push(`sampling_pattern=${setup?.sampling_pattern}`);
  }
  if (setup?.denoise !== false) errors.push(`denoise=${setup?.denoise}`);
  if (setup?.seed !== 0) errors.push(`seed=${setup?.seed}`);
  if (setup?.threads_mode !== 'FIXED') errors.push(`threads_mode=${setup?.threads_mode}`);
  if (setup?.threads !== 1) errors.push(`threads=${setup?.threads}`);
  equal(setup?.resolution, [RENDER_WIDTH, RENDER_HEIGHT], 'resolution');
  if (setup?.color_mode !== 'RGBA') errors.push(`color_mode=${setup?.color_mode}`);
  return { ok: errors.length === 0, errors };
}

if (process.argv[2] === '--selfcheck') {
  const samples = [
    ['phase=INVOKE seq=91 main=1 thread=11 tick=99', 5],
    ['phase=ENQUEUED seq=91 main=0 thread=22 tick=100 ok=1', 10],
    ['phase=TURN seq=91 main=1 thread=11 tick=105 same_wm=1 abort=0', 50],
    ['status=complete phase=WRITE frame=1', 53],
    ['phase=PIPELINE_TERMINAL frame=1 status=complete', 54],
    ['terminal=1 phase=READY tick=105 thread=11 main=1 seq=91', 60],
    ['phase=WORKER_RETURN status=complete seq=91 main=0 thread=22 tick=105', 70],
    ['phase=QUEUE_DESTROY seq=91 main=1 thread=11 tick=106', 80],
  ];
  const events = samples.map(([tokens, atMs], index) =>
    parseAsyncLine(`${ASYNC.prefix}${tokens}`, atMs, index));
  const heartbeats = [{ atMs: 25, tick: '102' }];
  const acceptedTopology = validateAsync(events, heartbeats);
  const withoutWrite = validateAsync(events.filter((event) => event.state !== 'WRITE'), heartbeats);
  const wrongOrder = validateAsync([events[1], events[0], ...events.slice(2)], heartbeats);
  const wrongWorkerEvents = events.map((event) => ({ ...event, fields: { ...event.fields } }));
  wrongWorkerEvents.find((event) => event.state === 'WORKER_RETURN').fields.thread = '11';
  const wrongWorker = validateAsync(wrongWorkerEvents, heartbeats);
  const failed = validateAsync([
    ...events.slice(0, 3),
    parseAsyncLine(`${ASYNC.prefix}phase=FAILED seq=91 main=1 thread=11 tick=105 reason=boom`, 50, 3),
    ...events.slice(4),
  ], heartbeats);
  const pyexpr = makePythonExpr();
  const pySyntax = spawnSync(
    'python3',
    ['-c', 'import ast, sys; ast.parse(sys.stdin.read())'],
    { input: pyexpr, encoding: 'utf8' },
  );
  const setupSample = {
    schema: CYCLES_SETUP_SCHEMA,
    addon_file: ADDON_GUEST,
    addon_was_registered: false,
    addon_registered: true,
    build_options_cycles: true,
    with_osl: false,
    with_embree: false,
    with_embree_gpu: false,
    device_types: [false, false, false, false, false, false],
    devices: [['CPU', 'CPU', 'CPU', false, false, false, false, false]],
    vendor_devices: [],
    engine: 'CYCLES',
    view_transform: 'AgX',
    device: 'CPU',
    samples: 16,
    adaptive: false,
    sampling_pattern: 'AUTOMATIC',
    denoise: false,
    seed: 0,
    threads_mode: 'FIXED',
    threads: 1,
    resolution: [RENDER_WIDTH, RENDER_HEIGHT],
    color_mode: 'RGBA',
  };
  const badSetupSample = { ...setupSample, threads: 2 };
  const validLimitReceipt = parseWebGpuPreinitReceipt(
    `${WGPU_PREINIT_PREFIX} features=18 ` +
    'adapterMaxComputeWorkgroupStorageSize=65536 ' +
    'requestedMaxComputeWorkgroupStorageSize=65536 ' +
    'deviceMaxComputeWorkgroupStorageSize=65536');
  const checks = [
    acceptedTopology.ok,
    acceptedTopology.actualStates.join('>') ===
      'INVOKE>ENQUEUED>TURN>WRITE>PIPELINE_TERMINAL>READY>WORKER_RETURN>QUEUE_DESTROY',
    acceptedTopology.sequence === '91',
    acceptedTopology.wmThread === '11',
    acceptedTopology.workerThread === '22',
    acceptedTopology.yieldPairCount === 0,
    acceptedTopology.uiHeartbeat === null,
    withoutWrite.ok && withoutWrite.optionalWrite === false,
    !wrongOrder.ok,
    !wrongWorker.ok,
    !failed.ok,
    pySyntax.status === 0,
    !/bpy\.ops\.render/.test(pyexpr),
    !/\bbpy\.ops\./.test(pyexpr),
    pyexpr.includes('import _cycles'),
    pyexpr.includes('import cycles'),
    pyexpr.includes('_bw_ca_addon_was_registered = bool(cycles.CyclesRender.is_registered)'),
    pyexpr.includes('_bw_ca_addon_registered = bool(cycles.CyclesRender.is_registered)'),
    !pyexpr.includes('hasattr(bpy.types, "CyclesRender")'),
    pyexpr.includes('_bw_ca_scene.render.engine = "CYCLES"'),
    pyexpr.includes('_bw_ca_scene.view_settings.view_transform = "AgX"'),
    pyexpr.includes('_bw_ca_scene.cycles.samples = 16'),
    pyexpr.includes('_bw_ca_scene.cycles.sampling_pattern = "AUTOMATIC"'),
    pyexpr.includes('_bw_ca_scene.render.threads_mode = "FIXED"'),
    pyexpr.includes('_bw_ca_scene.render.threads = 1'),
    pyexpr.includes('bpy.app.handlers.render_complete.append(_bw_ca_complete)'),
    validateCyclesSetupReceipt(setupSample).ok,
    !validateCyclesSetupReceipt(badSetupSample).ok,
    validLimitReceipt?.pass === true,
    parseWebGpuPreinitReceipt('unrelated console line') === null,
    parseComparator('Max error = 0.00392\n0 pixels (0%) over 0.016', 0).pass,
    sha256Bytes(readFileSync(BLEND_HOST)) ===
      '1335899143c7e77bcb0f6e3680fd99078c0af481a1238e4ed7d4eb1ddd7dd353',
    sha256Bytes(readFileSync(GOLDEN_HOST)) ===
      '45a49c27b39340d7ad248144adaa10ba9de70b2dd5682daaec528573519b9ba2',
    sha256Tree(ADDON_HOST).length === 64,
    Object.values(BINARY_PATHS).every((path) => statSync(path).size > 0),
    Object.keys(localShellReceipts()).sort().join(',') === 'boot,fileBridge,index,preinit,windowed',
  ];
  if (checks.every(Boolean)) {
    console.log(`SELF_CHECK_PASS probe=f12-cycles schema=${ASYNC.schemaStatus} physical_f12=one bpy_exec=none factory_cube=${RENDER_WIDTH}x${RENDER_HEIGHT}@16spp threads=1 comparator=${FAIL_THRESHOLD}/${FAIL_PERCENT}`);
    process.exit(0);
  }
  console.error(`SELF_CHECK_FAIL probe=f12-cycles topology=${JSON.stringify(acceptedTopology.errors)} no_write=${JSON.stringify(withoutWrite.errors)} wrong_order=${JSON.stringify(wrongOrder.errors)} wrong_worker=${JSON.stringify(wrongWorker.errors)} failed=${JSON.stringify(failed.errors)} py_syntax=${JSON.stringify(pySyntax.stderr || pySyntax.error?.message || '')}`);
  process.exit(1);
}

const PORT = Number.parseInt(process.argv[2] || '8151', 10);
const RENDER_MS = Number.parseInt(process.argv[3] || String(DEFAULT_RENDER_MS), 10);
const LABEL = (process.argv[4] || 'cycles-factory-cube-f12').trim();
if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) {
  console.error(`invalid port: ${process.argv[2] || ''}`);
  process.exit(2);
}
if (!Number.isInteger(RENDER_MS) || RENDER_MS < 2000) {
  console.error(`invalid timeout_ms: ${process.argv[3] || ''}`);
  process.exit(2);
}
if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(LABEL)) {
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
const binaryReceipts = Object.fromEntries(Object.entries(BINARY_PATHS).map(([name, path]) => {
  const bytes = readFileSync(path);
  return [name, { path, bytes: bytes.length, sha256: sha256Bytes(bytes) }];
}));
const expectedServedShell = localShellReceipts();
const addonReceipt = { hostPath: ADDON_HOST, guestEntry: ADDON_GUEST, sha256Tree: sha256Tree(ADDON_HOST) };
const url = `${base}/windowed.html?gate=${WIDTH}x${HEIGHT}&args=${encodeURIComponent(BLEND_GUEST)}&pyexpr=${encodeURIComponent(pythonExpr)}`;
const prefix = `${OUTDIR}/${LABEL}`;
const consolePath = `${prefix}-console.log`;
const manifestPath = `${prefix}-manifest.json`;
const screenshotPath = `${prefix}-${WIDTH}x${HEIGHT}.png`;
const renderPath = `${prefix}-render-result.png`;
const comparatorPath = `${prefix}-comparator.txt`;

mkdirSync(OUTDIR, { recursive: true });
for (const path of [
  consolePath,
  `${consolePath}.license`,
  manifestPath,
  `${manifestPath}.license`,
  screenshotPath,
  `${screenshotPath}.license`,
  renderPath,
  `${renderPath}.license`,
  comparatorPath,
  `${comparatorPath}.license`,
]) {
  if (existsSync(path)) {
    throw new Error(`refusing to overwrite evidence path; choose a unique label: ${path}`);
  }
}
// Reserve the final manifest atomically before launching a browser. A crashed
// attempt remains immutable and cannot be reused under the same label.
closeSync(openSync(manifestPath, 'wx'));
const startedAt = Date.now();
const marks = [];
const consoleEntries = [];
const asyncEvents = [];
const acceptLines = [];
const gpuErrors = [];
const pageErrors = [];
const renderErrors = [];
const heartbeats = [];
let pageCrashed = false;
let renderDispatched = false;
let heartbeatError = null;
let stopHeartbeat = false;
let runError = null;
let seedReceipt = null;
let gateReceipt = null;
let servedShell = null;
let configReceipt = null;
let doneReceipt = null;
let physicalKeyReceipt = null;
let webGpuPreinitReceipt = null;
let topology = null;
let pngStats = null;
let comparator = null;
let comparatorText = '';
let screenshotSha256 = null;
let renderSha256 = null;
let screenshotCaptured = false;
let renderCaptured = false;
let tickBeforeF12 = null;
let tickAfterRender = null;

function mark(label, extra = {}) {
  const entry = { label, iso: new Date().toISOString(), atMs: elapsedMs(startedAt), ...extra };
  marks.push(entry);
  console.log(`[${entry.iso}] ${label}`);
}

function firstBlockingReason() {
  if (pageCrashed) return 'page crashed';
  if (pageErrors.length) return `page error: ${pageErrors[0]}`;
  if (gpuErrors.length) return `GPU/browser error: ${gpuErrors[0]}`;
  if (renderErrors.length) return `render-window error: ${renderErrors[0]}`;
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
  if (text.startsWith('BW_CYCLES_ACCEPT ')) acceptLines.push(text);
  const benignDeviceReceipt = text.startsWith(WGPU_PREINIT_PREFIX);
  const markerOnStderr = text.startsWith(ASYNC.prefix) || text.startsWith('BW_CYCLES_ACCEPT ');
  if (!benignDeviceReceipt && !markerOnStderr &&
      (GPU_ERROR_RE.test(text) ||
       (message.type() === 'error' && /\b(?:gpu|webgpu|wgpu|dawn)\b/i.test(text))))
  {
    gpuErrors.push(text);
  }
  if (renderDispatched && !markerOnStderr &&
      /\b(?:error|exception|traceback|failed|fatal)\b/i.test(text))
  {
    renderErrors.push(text);
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

  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
  servedShell = await captureServedShell(page, expectedServedShell);
  await page.waitForFunction(
    () => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'),
    undefined,
    { timeout: BOOT_MS },
  );
  mark('WM_main reached');
  const preinitReceiptDeadline = Date.now() + 5000;
  while (!webGpuPreinitReceipt && Date.now() < preinitReceiptDeadline) {
    await sleep(25);
  }
  if (webGpuPreinitReceipt?.pass !== true) {
    throw new Error(
      `WebGPU compute workgroup storage receipt invalid: ${JSON.stringify(webGpuPreinitReceipt)}`);
  }
  mark('WebGPU compute workgroup storage limit verified', webGpuPreinitReceipt);
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
  const configDeadline = Date.now() + 30000;
  while (!configReceipt && Date.now() < configDeadline) {
    await sleep(50);
    configReceipt = await readJsonIfPresent(page, CONFIG_GUEST);
  }
  const sceneSetup = validateCyclesSetupReceipt(configReceipt?.setup);
  if (configReceipt?.status !== 'ARMED' || configReceipt.engine !== 'CYCLES' ||
      JSON.stringify(configReceipt.resolution) !== JSON.stringify([RENDER_WIDTH, RENDER_HEIGHT]) ||
      configReceipt.blend !== BLEND_GUEST ||
      (!PRODUCT_MODE && configReceipt.async_env !== ASYNC.envValue) ||
      !sceneSetup.ok)
  {
    throw new Error(
      `startup/config receipt invalid: ${JSON.stringify(configReceipt)} setup=${sceneSetup.errors.join('; ')}`,
    );
  }
  mark('startup file and render config verified', configReceipt);

  const canvas = page.locator('#canvas');
  await page.bringToFront();
  /* Click inside the 3D viewport, not the editor-type selector at the
   * canvas's top-left corner. A second top-left click after Escape reopens
   * that menu and Blender correctly consumes F12 without starting a render. */
  await canvas.click({ position: { x: WIDTH / 2, y: HEIGHT / 2 } });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(250);
  await canvas.click({ position: { x: WIDTH / 2, y: HEIGHT / 2 } });
  const focusReceipt = await page.evaluate(() => ({
    hasFocus: document.hasFocus(),
    activeId: document.activeElement?.id || null,
  }));
  if (!focusReceipt.hasFocus || focusReceipt.activeId !== 'canvas') {
    throw new Error(`canvas focus unavailable: ${JSON.stringify(focusReceipt)}`);
  }
  await page.evaluate(() => {
    window.__bwCyclesF12KeyEvents = [];
    window.addEventListener('keydown', (event) => {
      if (event.key === 'F12' || event.code === 'F12') {
        window.__bwCyclesF12KeyEvents.push({
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
    productMode: PRODUCT_MODE,
  });
  renderDispatched = true;
  await page.keyboard.press('F12');
  physicalKeyReceipt = await page.evaluate(() => window.__bwCyclesF12KeyEvents || []);

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
  physicalKeyReceipt = await page.evaluate(() => window.__bwCyclesF12KeyEvents || []);
  const physicalF12 = physicalKeyReceipt.length === 1 && physicalKeyReceipt[0].key === 'F12' &&
    physicalKeyReceipt[0].code === 'F12' && physicalKeyReceipt[0].isTrusted === true &&
    physicalKeyReceipt[0].repeat === false && physicalKeyReceipt[0].targetId === 'canvas' &&
    physicalKeyReceipt[0].activeId === 'canvas';
  if (!physicalF12) throw new Error(`physical F12 receipt invalid: ${JSON.stringify(physicalKeyReceipt)}`);
  if (doneReceipt.status !== 'OK' || doneReceipt.engine !== 'CYCLES' ||
      JSON.stringify(doneReceipt.resolution) !== JSON.stringify([RENDER_WIDTH, RENDER_HEIGHT]) ||
      doneReceipt.blend !== BLEND_GUEST || doneReceipt.pre_count !== 1 ||
      doneReceipt.complete_count !== 1 || doneReceipt.cancel_count !== 0 ||
      doneReceipt.png !== PNG_GUEST || !(doneReceipt.png_size > 0))
  {
    throw new Error(`render handler receipt invalid: ${JSON.stringify(doneReceipt)}`);
  }
  topology = PRODUCT_MODE ? {
    ok: true,
    productMode: true,
    actualStates: [],
    errors: [],
    uiHeartbeat: null,
  } : validateAsync(asyncEvents, heartbeats);
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

  /* Preserve and score the completed Render Result before the post-render UI
   * settle. A later redraw validation error must still fail the overall run,
   * but it must not destroy the decisive CPU-render pixel evidence with MEMFS. */
  await page.waitForTimeout(500);
  const blocker = firstBlockingReason();
  if (blocker) throw new Error(blocker);

  const rect = gateReceipt.rect;
  await page.mouse.move(Math.round(rect.x + 16), Math.round(rect.y + rect.height - 16));
  await page.waitForTimeout(250);
  tickAfterRender = await readWmTick(page);
  if (PRODUCT_MODE &&
      !(Number.isFinite(Number(tickBeforeF12)) && Number.isFinite(Number(tickAfterRender)) &&
        Number(tickAfterRender) > Number(tickBeforeF12)))
  {
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
      physicalKeyReceipt = await page.evaluate(() => window.__bwCyclesF12KeyEvents || []);
    }
    catch {
      /* The page may already be gone; the error and crash receipts remain authoritative. */
    }
  }
  if (!topology) {
    topology = PRODUCT_MODE ? {
      ok: true,
      productMode: true,
      actualStates: [],
      errors: [],
      uiHeartbeat: null,
    } : validateAsync(asyncEvents, heartbeats);
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
const physicalF12 = physicalKeyReceipt?.length === 1 && physicalKeyReceipt[0].key === 'F12' &&
  physicalKeyReceipt[0].code === 'F12' && physicalKeyReceipt[0].isTrusted === true &&
  physicalKeyReceipt[0].repeat === false && physicalKeyReceipt[0].targetId === 'canvas' &&
  physicalKeyReceipt[0].activeId === 'canvas';
const handlerComplete = doneReceipt?.status === 'OK' && doneReceipt.pre_count === 1 &&
  doneReceipt.complete_count === 1 && doneReceipt.cancel_count === 0;
const accepted = !runError && !pageCrashed && pageErrors.length === 0 && gpuErrors.length === 0 &&
  renderErrors.length === 0 &&
  !heartbeatError && webGpuPreinitReceipt?.pass === true && exactGate && physicalF12 &&
  handlerComplete && topology?.ok === true &&
  validateCyclesSetupReceipt(configReceipt?.setup).ok === true &&
  pngStats?.nonBlackPixels > 0 && pngStats?.finitePixels === true &&
  comparator?.pass === true && renderCaptured &&
  screenshotCaptured && Boolean(renderSha256) && Boolean(screenshotSha256);
const manifest = {
  schema: 'blender-web.cycles-windowed-f12-acceptance.v2',
  verdict: accepted ? 'PASS' : 'FAIL',
  generatedAt: new Date().toISOString(),
  driver: { path: DRIVER_PATH, sha256: sha256Bytes(readFileSync(DRIVER_PATH)) },
  inputs: {
    blend: { hostPath: BLEND_HOST, guestPath: BLEND_GUEST, sha256: blendSha256, bytes: blendBytes.length },
    golden: { path: GOLDEN_HOST, sha256: goldenSha256 },
    shippingBinary: binaryReceipts,
    servedShell,
    expectedServedShell,
    cyclesAddonPreload: addonReceipt,
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
    bpyExecUsed: false,
    pythonExprSha256: sha256Bytes(pythonExpr),
    pythonExprRenderOperatorAbsent: !/bpy\.ops\.render/.test(pythonExpr),
    pythonExprOperatorAbsent: !/\bbpy\.ops\./.test(pythonExpr),
    pythonRole: 'configure scene, register passive render handlers, save Render Result',
    keyReceipt: physicalKeyReceipt,
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
  render: {
    engine: 'CYCLES',
    resolution: [RENDER_WIDTH, RENDER_HEIGHT],
    configReceipt,
    completionReceipt: doneReceipt,
    handlerComplete,
    acceptLines,
    pngStats,
  },
  comparator: {
    executable: OIIOTOOL,
    argv: [GOLDEN_HOST, renderPath, '--fail', FAIL_THRESHOLD, '--failpercent', FAIL_PERCENT, '--diff'],
    threshold: FAIL_THRESHOLD,
    failPercent: FAIL_PERCENT,
    result: comparator,
  },
  gate: { expected: `${WIDTH}x${HEIGHT}@1`, receipt: gateReceipt, exact: Boolean(exactGate) },
  heartbeat: {
    acceptanceRole: 'evidence-only',
    uiResponsiveDuringCpuRenderClaimed: false,
    limitation: 'legacy Cycles CPU render blocks its enclosing WM turn',
    intervalMs: HEARTBEAT_MS,
    sampleCount: heartbeats.length,
    samples: heartbeats,
    error: heartbeatError,
    betweenEnqueuedAndFirstTurn: topology?.uiHeartbeat || null,
    tickBeforeF12,
    tickAfterRender,
  },
  assertions: {
    opfsStartupFile: seedReceipt?.sha256 === blendSha256 && configReceipt?.blend === BLEND_GUEST,
    physicalTrustedF12ExactlyOnce: Boolean(physicalF12),
    noBpyExec: true,
    computeWorkgroupStorageAtLeast32768: webGpuPreinitReceipt?.pass === true,
    cyclesAddonRegisteredAndCpuOnly:
      validateCyclesSetupReceipt(configReceipt?.setup).ok === true,
    exactAsyncSemanticOrder: PRODUCT_MODE ? null : topology?.ok === true,
    markerIndependentProductMode: PRODUCT_MODE,
    wmTickAdvancedAfterRender: !PRODUCT_MODE || Number(tickAfterRender) > Number(tickBeforeF12),
    renderHandlerCompletedExactlyOnce: handlerComplete,
    nonBlack: pngStats?.nonBlackPixels > 0 && pngStats?.rgbMax > 0,
    finitePng: pngStats?.finitePixels === true,
    comparatorPass: comparator?.pass === true,
    noGpuError: gpuErrors.length === 0,
    noRenderWindowError: renderErrors.length === 0,
    noPageError: pageErrors.length === 0,
    noPageCrash: !pageCrashed,
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
  },
  failures: { runError, heartbeatError, pageCrashed, pageErrors, gpuErrors, renderErrors },
  marks,
};
writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
writeFileSync(`${manifestPath}.license`, CC0);

if (!accepted) {
  console.error(`F12_CYCLES_ACCEPT_FAIL manifest=${manifestPath} console=${consolePath}`);
  process.exit(1);
}
console.log(`F12_CYCLES_ACCEPT_PASS manifest=${manifestPath} render=${renderPath} screenshot=${screenshotPath}`);
