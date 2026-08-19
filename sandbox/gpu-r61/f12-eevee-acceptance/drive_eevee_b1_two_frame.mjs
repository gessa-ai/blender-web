// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// EEVEE B1 physical-F12 browser gate. Happy mode performs two trusted F12s in
// one boot, exporting before and after a fixed caster/light mutation. Failure
// mode is a separate boot and expects the probe-only forced-oversize branch.
// Python configures the loaded scene and passive handlers; it never invokes a
// render operator. Production must emit the BW_EEVEE_B1 grammar documented in
// eevee_b1_runtime_contract.md before this gate can pass.

import { spawnSync } from 'child_process';
import { createHash } from 'crypto';
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'fs';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';

const ROOT = '/Users/paws/blender-web';
const DRIVER_PATH = fileURLToPath(import.meta.url);
const OUTDIR = `${ROOT}/sandbox/gpu-r61/f12-eevee-acceptance/evidence`;
const DEFAULT_BLEND_HOST = `${ROOT}/upstream/tests/files/render/shadow/shadow_filter.blend`;
const BLEND_HOST = process.env.BW_EEVEE_B1_BLEND_HOST || DEFAULT_BLEND_HOST;
const GOLDEN_1 = process.env.BW_EEVEE_B1_GOLDEN_1 ||
  `${ROOT}/sandbox/m6-prep/goldens/eevee/shadow/shadow_filter.png`;
const GOLDEN_2 = process.env.BW_EEVEE_B1_GOLDEN_2 ||
  `${ROOT}/sandbox/gpu-r61/f12-eevee-acceptance/oracles/shadow_filter_b1_mutated_native_0001.png`;
const OPFS_NAME = 'bw_f12_eevee_b1_shadow_filter.blend';
const BLEND_GUEST = `/projects/${OPFS_NAME}`;
const CONFIG_GUEST = '/tmp/bw_eevee_b1_config.json';
const RECEIPT_GUEST = '/tmp/bw_eevee_b1_receipt.json';
const PNG_GUEST = ['/tmp/bw_eevee_b1_frame1.png', '/tmp/bw_eevee_b1_frame2.png'];
const WIDTH = 1280;
const HEIGHT = 720;
const RENDER_WIDTH = 128;
const RENDER_HEIGHT = 128;
const BOOT_MS = 300000;
const DEFAULT_STAGE_MS = 300000;
const FAIL_THRESHOLD = '0.0156862745';
const FAIL_PERCENT = '0.08';
const MIN_DELTA_OVER_FRACTION = 0.08;
const OIIOTOOL = process.env.OIIOTOOL || '/opt/homebrew/bin/oiiotool';
const PRODUCT_MODE = process.env.BW_EEVEE_B1_PRODUCT_SMOKE === '1';
const DISABLE_SHADOWS = process.env.BW_EEVEE_B1_DISABLE_SHADOWS === '1';
const RENDER_SAMPLES_OVERRIDE = process.env.BW_EEVEE_B1_RENDER_SAMPLES_OVERRIDE === undefined ?
  null : Number.parseInt(process.env.BW_EEVEE_B1_RENDER_SAMPLES_OVERRIDE, 10);
const BLENDER_WEB_BIN = process.env.BLENDER_WEB_BIN || `${ROOT}/build-wasm-windowed-opt/bin`;
const WGPU_PREINIT_PREFIX = '[bw] WM-worker WebGPU device pre-acquired (ADR-007);';
const GPU_ERROR_RE = /GPU[- _]?ERROR|GPUValidationError|Dawn[^\n]*error|WGPU[^\n]*error|WebGPU[^\n]*error|ValidationError|validation error|uncaptured error|DeviceLost|device lost|RuntimeError|table index is out of bounds/i;
const CC0 = 'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n';

if (RENDER_SAMPLES_OVERRIDE !== null &&
    (!Number.isSafeInteger(RENDER_SAMPLES_OVERRIDE) || RENDER_SAMPLES_OVERRIDE < 1))
{
  throw new Error('BW_EEVEE_B1_RENDER_SAMPLES_OVERRIDE must be a positive safe integer');
}

const ASYNC = Object.freeze({
  prefix: 'BW_F12_ASYNC ',
  envKey: 'BW_F12_ASYNC_PROBE',
  states: new Set(['INVOKE', 'ENQUEUED', 'TURN', 'PENDING', 'CONSUME', 'END_RESULT',
    'WRITE', 'PIPELINE_TERMINAL', 'READY', 'FAILED', 'FATAL', 'WORKER_RETURN',
    'QUEUE_DESTROY', 'QUEUE_CREATE_FAILED', 'WRONG_WM_REQUEUE', 'PREJOIN_ABORT']),
});

const B1 = Object.freeze({
  prefix: 'BW_EEVEE_B1 ',
  envKey: 'BW_EEVEE_B1_PROBE',
  forceKey: 'BW_EEVEE_B1_FORCE_OVERSIZE',
  exactKeys: Object.freeze({
    ATLAS_STATUS: ['phase', 'status', 'requested', 'limit', 'forced'],
    RESOLVE_SUBMIT: ['phase', 'status', 'loop'],
  }),
});

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseFields(text, prefix) {
  if (!text.startsWith(prefix)) return null;
  const fields = {};
  const errors = [];
  for (const token of text.slice(prefix.length).trim().split(/\s+/)) {
    const split = token.indexOf('=');
    if (split < 1 || split === token.length - 1) {
      errors.push(`malformed token ${token}`);
      continue;
    }
    const key = token.slice(0, split);
    if (Object.hasOwn(fields, key)) errors.push(`duplicate key ${key}`);
    fields[key] = token.slice(split + 1);
  }
  return { text, fields, errors };
}

function parseAsync(text, consoleIndex) {
  const parsed = parseFields(text, ASYNC.prefix);
  if (!parsed) return null;
  const state = ASYNC.states.has(parsed.fields.phase) ? parsed.fields.phase : null;
  if (!state) parsed.errors.push(`unknown phase ${parsed.fields.phase}`);
  return { ...parsed, state, consoleIndex };
}

function parseB1(text, consoleIndex) {
  const parsed = parseFields(text, B1.prefix);
  if (!parsed) return null;
  const phase = parsed.fields.phase;
  const expected = B1.exactKeys[phase];
  if (!expected) parsed.errors.push(`unknown phase ${phase}`);
  else {
    const actual = Object.keys(parsed.fields).sort();
    const wanted = [...expected].sort();
    if (actual.length !== wanted.length || actual.some((key, i) => key !== wanted[i])) {
      parsed.errors.push(`keys=${actual.join(',')} expected=${wanted.join(',')}`);
    }
  }
  if (phase === 'ATLAS_STATUS') {
    if (!['PENDING', 'READY', 'FAILED'].includes(parsed.fields.status)) {
      parsed.errors.push(`invalid status ${parsed.fields.status}`);
    }
    if (!/^\d+$/.test(parsed.fields.requested || '')) parsed.errors.push('invalid requested');
    if (!/^\d+$/.test(parsed.fields.limit || '')) parsed.errors.push('invalid limit');
    if (!/^[01]$/.test(parsed.fields.forced || '')) parsed.errors.push('invalid forced');
  }
  if (phase === 'RESOLVE_SUBMIT') {
    if (parsed.fields.status !== 'SUBMITTED') parsed.errors.push('resolve not submitted');
    if (!/^\d+$/.test(parsed.fields.loop || '')) parsed.errors.push('invalid loop');
  }
  return { ...parsed, phase, consoleIndex };
}

function validateB1Happy(events) {
  const errors = events.flatMap((event) => event.errors);
  const atlas = events.filter((event) => event.phase === 'ATLAS_STATUS');
  const resolves = events.filter((event) => event.phase === 'RESOLVE_SUBMIT');
  if (atlas.length < 2) errors.push(`atlas marker count=${atlas.length}`);
  if (atlas[0]?.fields.status !== 'PENDING') errors.push('first atlas status is not PENDING');
  if (atlas.at(-1)?.fields.status !== 'READY') errors.push('last atlas status is not READY');
  if (atlas.some((event) => event.fields.status === 'FAILED')) errors.push('FAILED atlas status');
  if (atlas.some((event) => event.fields.forced !== '0')) errors.push('happy marker forced != 0');
  if (resolves.length < 1) errors.push('no RESOLVE_SUBMIT marker');
  const readyIndex = events.findIndex((event) =>
    event.phase === 'ATLAS_STATUS' && event.fields.status === 'READY');
  const resolveIndex = events.findIndex((event) => event.phase === 'RESOLVE_SUBMIT');
  if (readyIndex < 0 || resolveIndex <= readyIndex) errors.push('resolve does not follow READY');
  return { ok: errors.length === 0, errors, atlasStatuses: atlas.map((e) => e.fields.status), resolveCount: resolves.length };
}

function validateB1Forced(events) {
  const errors = events.flatMap((event) => event.errors);
  const failed = events.filter((event) =>
    event.phase === 'ATLAS_STATUS' && event.fields.status === 'FAILED');
  const resolves = events.filter((event) => event.phase === 'RESOLVE_SUBMIT');
  if (failed.length !== 1) errors.push(`FAILED atlas marker count=${failed.length}`);
  if (resolves.length !== 0) errors.push(`resolve marker count=${resolves.length}`);
  const marker = failed[0];
  if (marker?.fields.forced !== '1') errors.push('failure marker forced != 1');
  if (marker && BigInt(marker.fields.requested) <= BigInt(marker.fields.limit)) {
    errors.push(`requested ${marker.fields.requested} is not over limit ${marker.fields.limit}`);
  }
  return { ok: errors.length === 0, errors };
}

function validateAsync(events, expectSuccess) {
  const errors = events.flatMap((event) => event.errors);
  const states = events.map((event) => event.state);
  for (const state of ['FATAL', 'QUEUE_CREATE_FAILED', 'WRONG_WM_REQUEUE']) {
    if (states.includes(state)) errors.push(`${state} observed`);
  }
  if (states[0] !== 'INVOKE') errors.push(`first async state=${states[0]}`);
  if (states.at(-1) !== 'QUEUE_DESTROY') errors.push(`terminal async state=${states.at(-1)}`);
  const invoke = events.find((event) => event.state === 'INVOKE');
  const sequence = invoke?.fields.seq || null;
  if (!/^\d+$/.test(sequence || '') || sequence === '0') errors.push(`invalid sequence=${sequence}`);
  if (sequence && events.some((event) => event.fields.seq && event.fields.seq !== sequence)) {
    errors.push('mixed async sequences in physical-F12 window');
  }
  const requireOrder = expectSuccess ?
    ['INVOKE', 'ENQUEUED', 'PENDING', 'CONSUME', 'END_RESULT', 'PIPELINE_TERMINAL', 'READY', 'WORKER_RETURN', 'QUEUE_DESTROY'] :
    ['INVOKE', 'ENQUEUED', 'FAILED', 'WORKER_RETURN', 'QUEUE_DESTROY'];
  let cursor = -1;
  for (const state of requireOrder) {
    cursor = states.indexOf(state, cursor + 1);
    if (cursor < 0) {
      errors.push(`missing/out-of-order ${state}: ${states.join('>')}`);
      break;
    }
  }
  return { ok: errors.length === 0, errors, states, sequence };
}

function parseComparator(text, returnCode) {
  const max = /Max error\s*=\s*([0-9.eE+-]+)/.exec(text)?.[1] || null;
  const over = /([0-9.]+)%\s*\)\s*over/.exec(text)?.[1] || null;
  return { returnCode, maxError: max, percentOver: over, pass: returnCode === 0 };
}

function parseWebGpuReceipt(text) {
  if (!text.startsWith(WGPU_PREINIT_PREFIX)) return null;
  const value = (key) => Number.parseInt(new RegExp(`(?:^|\\s)${key}=(\\d+)(?:\\s|$)`).exec(text)?.[1] || '', 10);
  const adapter = value('adapterMaxComputeWorkgroupStorageSize');
  const requested = value('requestedMaxComputeWorkgroupStorageSize');
  const device = value('deviceMaxComputeWorkgroupStorageSize');
  return { adapter, requested, device, pass: adapter >= 32768 && requested >= 32768 && device >= requested };
}

function makePythonExpr(forceFailure, productMode = PRODUCT_MODE) {
  const lines = ['import bpy, os, json'];
  if (!productMode) {
    lines.push(
      `os.environ[${JSON.stringify(ASYNC.envKey)}] = "1"`,
      `os.environ[${JSON.stringify(B1.envKey)}] = "1"`,
      forceFailure ? `os.environ[${JSON.stringify(B1.forceKey)}] = "1"` : `os.environ.pop(${JSON.stringify(B1.forceKey)}, None)`,
    );
  }
  lines.push(
    's=bpy.context.scene',
    's.render.engine="BLENDER_EEVEE"',
    `s.render.resolution_x=${RENDER_WIDTH}`, `s.render.resolution_y=${RENDER_HEIGHT}`,
    's.render.resolution_percentage=100', 's.render.image_settings.file_format="PNG"',
    's.render.image_settings.color_mode="RGB"', 's.frame_set(1)',
    `s.eevee.use_shadows=${DISABLE_SHADOWS ? 'False' : 'True'}`,
    ...(RENDER_SAMPLES_OVERRIDE === null ? [] :
      [`bpy.context.view_layer.samples=${RENDER_SAMPLES_OVERRIDE}`]),
    's.eevee.use_overscan=True', 's.eevee.overscan_size=50.0',
    '[setattr(v.eevee,"ambient_occlusion_distance",1) for v in s.view_layers]',
    's.eevee.light_threshold=0.001', 's.render.hair_type="STRIP"',
    's.eevee.shadow_step_count=16', 's.eevee.shadow_pool_size="1024"',
    's.eevee.volumetric_tile_size="2"', 's.eevee.volumetric_start=1.0',
    's.eevee.volumetric_end=50.0', 's.eevee.volumetric_samples=128',
    's.eevee.use_volumetric_shadows=True', 's.eevee.clamp_volume_indirect=0.0',
    's.eevee.use_raytracing=True', 's.eevee.ray_tracing_method="SCREEN"',
    's.eevee.ray_tracing_options.resolution_scale="1"',
    's.eevee.ray_tracing_options.screen_trace_quality=1.0',
    's.eevee.ray_tracing_options.screen_trace_thickness=1.0',
    's.eevee.fast_gi_quality=0.8', 's.eevee.gi_cubemap_resolution="256"',
    `_b1_config=${JSON.stringify(CONFIG_GUEST)}`, `_b1_receipt=${JSON.stringify(RECEIPT_GUEST)}`,
    `_b1_png=${JSON.stringify(PNG_GUEST)}`, '_b1_pre_count=0', '_b1_complete_count=0', '_b1_cancel_count=0', '_b1_timer=False',
    'def _b1_write(path,obj):', '    tmp=path+".tmp"', '    with open(tmp,"w") as f: json.dump(obj,f,sort_keys=True)', '    os.replace(tmp,path)',
    'def _b1_pre_handler(*_):', '    global _b1_pre_count', '    _b1_pre_count+=1', '    print("BW_EEVEE_B1_DRIVER phase=RENDER_PRE count=%d"%_b1_pre_count)',
    'def _b1_export():',
    '    global _b1_timer',
    '    try:',
    '        n=_b1_complete_count', '        rr=bpy.data.images.get("Render Result")',
    '        if rr is None: raise RuntimeError("Render Result missing")',
    '        path=_b1_png[n-1]', '        rr.save_render(filepath=path,scene=s)',
    '        mutated=False',
    '        if n==1:',
    '            bpy.data.objects["Cylinder.004"].location.y += 0.35',
    '            bpy.data.objects["Sun"].rotation_euler.y += 0.25',
    '            bpy.context.view_layer.update()', '            mutated=True',
    '        _b1_write(_b1_receipt,{"status":"FRAME_READY","frame":n,"pre":_b1_pre_count,"complete":_b1_complete_count,"cancel":_b1_cancel_count,"png":path,"bytes":os.path.getsize(path),"mutation_applied":mutated})',
    '        print("BW_EEVEE_B1_DRIVER phase=FRAME_READY frame=%d mutated=%d bytes=%d"%(n,int(mutated),os.path.getsize(path)))',
    '    except Exception as e:', '        _b1_write(_b1_receipt,{"status":"FAIL","error":repr(e)})',
    '    _b1_timer=False', '    return None',
    'def _b1_complete_fn(*_):', '    global _b1_complete_count,_b1_timer', '    _b1_complete_count+=1',
    '    if not _b1_timer:', '        _b1_timer=True', '        bpy.app.timers.register(_b1_export,first_interval=0.0)',
    'def _b1_cancel_fn(*_):', '    global _b1_cancel_count', '    _b1_cancel_count+=1',
    '    _b1_write(_b1_receipt,{"status":"CANCELLED","pre":_b1_pre_count,"complete":_b1_complete_count,"cancel":_b1_cancel_count})',
    'bpy.app.handlers.render_pre.append(_b1_pre_handler)',
    'bpy.app.handlers.render_complete.append(_b1_complete_fn)',
    'bpy.app.handlers.render_cancel.append(_b1_cancel_fn)',
    `_b1_write(_b1_config,{"status":"ARMED","blend":bpy.data.filepath,"engine":s.render.engine,"resolution":[s.render.resolution_x,s.render.resolution_y],"force":${forceFailure ? 'True' : 'False'},"shadows_enabled":bool(s.eevee.use_shadows),"render_samples":bpy.context.view_layer.samples if bpy.context.view_layer.samples > 0 else s.eevee.taa_render_samples})`,
    'print("BW_EEVEE_B1_DRIVER phase=ARMED")',
  );
  return lines.join('\n');
}

if (process.argv[2] === '--selfcheck') {
  const happy = [
    'phase=ATLAS_STATUS status=PENDING requested=1048576 limit=268435456 forced=0',
    'phase=ATLAS_STATUS status=READY requested=1048576 limit=268435456 forced=0',
    'phase=RESOLVE_SUBMIT status=SUBMITTED loop=0',
  ].map((s, i) => parseB1(`${B1.prefix}${s}`, i));
  const forced = [
    'phase=ATLAS_STATUS status=FAILED requested=268435460 limit=268435456 forced=1',
  ].map((s, i) => parseB1(`${B1.prefix}${s}`, i));
  const py = makePythonExpr(false);
  const productPy = makePythonExpr(false, true);
  const checks = [validateB1Happy(happy).ok, validateB1Forced(forced).ok,
    !validateB1Happy(forced).ok, !validateB1Forced(happy).ok,
    !/bpy\.ops\.render/.test(py), py.includes('Cylinder.004'), py.includes('Sun'),
    !productPy.includes(ASYNC.envKey), !productPy.includes(B1.envKey),
    sha256(readFileSync(DEFAULT_BLEND_HOST)) === '07b15caaf1ea18bf6aa48d33dbb9ef987ac9217b794a083ef9ea4e03aaf6c1d8',
    sha256(readFileSync(GOLDEN_1)) === '81ed8643c733be02d166a7c34e1caea215499925fc44de5b501f4d5ec9aab274',
    sha256(readFileSync(GOLDEN_2)) === '4848b348b8a05e4c4e2e58c44cc5828e047e8ec71dd2ea8ec2c3b74b1e6440e1'];
  if (checks.every(Boolean)) {
    console.log('SELF_CHECK_PASS probe=eevee-b1 physical_f12=two one_boot=1 mutation=caster+sun force_failure=separate_boot');
    process.exit(0);
  }
  console.error(`SELF_CHECK_FAIL checks=${JSON.stringify(checks)}`);
  process.exit(1);
}

const PORT = Number.parseInt(process.argv[2] || '8151', 10);
const STAGE_MS = Number.parseInt(process.argv[3] || String(DEFAULT_STAGE_MS), 10);
const LABEL = process.argv[4] || 'eevee-b1-shadow-filter';
const MODE = process.argv[5] || 'happy';
if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535 || !Number.isInteger(STAGE_MS) || STAGE_MS < 2000 || !/^[A-Za-z0-9._-]+$/.test(LABEL) || !['happy', 'force-failure'].includes(MODE)) {
  throw new Error('usage: node drive_eevee_b1_two_frame.mjs [port] [stage_ms] [label] [happy|force-failure]');
}

const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const forceFailure = MODE === 'force-failure';
if (PRODUCT_MODE && forceFailure) {
  throw new Error('BW_EEVEE_B1_PRODUCT_SMOKE supports happy mode only');
}
const pythonExpr = makePythonExpr(forceFailure);
if (/bpy\.ops\.render/.test(pythonExpr)) throw new Error('Python must not invoke rendering');
const blendBytes = readFileSync(BLEND_HOST);
const blendSha = sha256(blendBytes);
const base = `http://127.0.0.1:${PORT}`;
const url = `${base}/windowed.html?gate=${WIDTH}x${HEIGHT}&args=${encodeURIComponent(BLEND_GUEST)}&pyexpr=${encodeURIComponent(pythonExpr)}`;
const prefix = `${OUTDIR}/${LABEL}-${MODE}`;
const paths = {
  console: `${prefix}-console.log`, manifest: `${prefix}-manifest.json`,
  frame: [1, 2].map((n) => `${prefix}-frame${n}.png`),
  compare: [1, 2].map((n) => `${prefix}-frame${n}-comparator.txt`),
  delta: `${prefix}-frame-delta.txt`, screenshot: `${prefix}-${WIDTH}x${HEIGHT}.png`,
};
mkdirSync(OUTDIR, { recursive: true });
for (const path of [paths.console, paths.manifest, ...paths.frame, ...paths.compare, paths.delta, paths.screenshot]) {
  rmSync(path, { force: true }); rmSync(`${path}.license`, { force: true });
}

const started = Date.now();
const consoleLines = [];
const asyncEvents = [];
const b1Events = [];
const gpuErrors = [];
const pageErrors = [];
const runs = [];
let preinit = null;
let pageCrashed = false;
let gate = null;
let config = null;
let runError = null;
let screenshotSha = null;
let physicalKeys = null;
let frameDelta = null;
const browser = await chromium.launch({ headless: false, args: ['--enable-unsafe-webgpu', '--use-angle=metal', '--disable-dev-tools'] });
const context = await browser.newContext({ viewport: { width: WIDTH + 120, height: HEIGHT + 120 }, deviceScaleFactor: 1 });
const page = await context.newPage();
page.on('console', (message) => {
  const text = message.text(); const index = consoleLines.length;
  consoleLines.push(`[${new Date().toISOString()}] [console:${message.type()}] ${text}`);
  const ae = parseAsync(text, index); if (ae) asyncEvents.push(ae);
  const be = parseB1(text, index); if (be) b1Events.push(be);
  const receipt = parseWebGpuReceipt(text); if (receipt) preinit = receipt;
  if (!ae && !be && !text.startsWith('BW_EEVEE_B1_DRIVER ') && !text.startsWith(WGPU_PREINIT_PREFIX) && GPU_ERROR_RE.test(text)) gpuErrors.push(text);
});
page.on('pageerror', (error) => pageErrors.push(error.stack || error.message || String(error)));
page.on('crash', () => { pageCrashed = true; });

async function readJson(path) {
  return page.evaluate((p) => { try { return JSON.parse(window.__bwModule.FS.readFile(p, { encoding: 'utf8' })); } catch (_) { return null; } }, path);
}

async function waitReceipt(predicate, timeout) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (pageCrashed || pageErrors.length || gpuErrors.length) throw new Error('browser/GPU failure while waiting');
    const receipt = await readJson(RECEIPT_GUEST);
    if (receipt && predicate(receipt)) return receipt;
    await sleep(50);
  }
  throw new Error(`receipt timeout after ${timeout}ms`);
}

async function waitAsyncTerminal(startIndex, timeout) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const terminal = asyncEvents.find((event) => event.consoleIndex >= startIndex && event.state === 'QUEUE_DESTROY');
    if (terminal) return terminal.consoleIndex;
    if (pageCrashed || pageErrors.length || gpuErrors.length) throw new Error('browser/GPU failure while waiting async terminal');
    await sleep(50);
  }
  throw new Error('QUEUE_DESTROY timeout');
}

async function captureGuest(path, host) {
  const capture = await page.evaluate(async (p) => {
    const bytes = window.__bwModule.FS.readFile(p); const blob = new Blob([bytes], { type: 'image/png' });
    const bitmap = await createImageBitmap(blob); const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const ctx = canvas.getContext('2d', { willReadFrequently: true }); ctx.drawImage(bitmap, 0, 0);
    const rgba = ctx.getImageData(0, 0, bitmap.width, bitmap.height).data;
    let nonBlack = 0; for (let i = 0; i < rgba.length; i += 4) if (rgba[i] || rgba[i + 1] || rgba[i + 2]) nonBlack++;
    let binary = ''; for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
    return { width: bitmap.width, height: bitmap.height, bytes: bytes.length, nonBlack, b64: btoa(binary) };
  }, path);
  const bytes = Buffer.from(capture.b64, 'base64'); delete capture.b64;
  writeFileSync(host, bytes); writeFileSync(`${host}.license`, CC0);
  return { ...capture, sha256: sha256(bytes) };
}

try {
  await page.goto(`${base}/bin/bw_seed.html`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  const seeded = await page.evaluate(async ({ b64, name }) => {
    const binary = atob(b64); const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    const root = await navigator.storage.getDirectory(); const handle = await root.getFileHandle(name, { create: true });
    const writable = await handle.createWritable(); await writable.write(bytes); await writable.close();
    return (await (await root.getFileHandle(name)).getFile()).size;
  }, { b64: blendBytes.toString('base64'), name: OPFS_NAME });
  if (seeded !== blendBytes.length) throw new Error('OPFS seed mismatch');
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
  await page.waitForFunction(() => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'), undefined, { timeout: BOOT_MS });
  const preinitDeadline = Date.now() + 30000;
  while (!preinit && Date.now() < preinitDeadline) await sleep(50);
  if (preinit?.pass !== true) throw new Error(`WebGPU receipt invalid: ${JSON.stringify(preinit)}`);
  await page.waitForFunction(({ w, h }) => { const c = document.querySelector('#canvas'); const r = c?.getBoundingClientRect(); return c?.width === w && c?.height === h && Math.round(r.width) === w && Math.round(r.height) === h && window.devicePixelRatio === 1 && window.crossOriginIsolated; }, { w: WIDTH, h: HEIGHT }, { timeout: 30000 });
  gate = await page.evaluate(() => { const c = document.querySelector('#canvas'); const r = c.getBoundingClientRect(); return { width: c.width, height: c.height, cssWidth: Math.round(r.width), cssHeight: Math.round(r.height), x: r.x, y: r.y, dpr: devicePixelRatio, isolated: crossOriginIsolated }; });
  const configDeadline = Date.now() + 30000;
  while (!config && Date.now() < configDeadline) { config = await readJson(CONFIG_GUEST); if (!config) await sleep(50); }
  if (config?.status !== 'ARMED' || config.blend !== BLEND_GUEST ||
      config.engine !== 'BLENDER_EEVEE' ||
      JSON.stringify(config.resolution) !== JSON.stringify([RENDER_WIDTH, RENDER_HEIGHT]) ||
      config.force !== forceFailure || config.shadows_enabled !== !DISABLE_SHADOWS ||
      (RENDER_SAMPLES_OVERRIDE !== null && config.render_samples !== RENDER_SAMPLES_OVERRIDE)) throw new Error(`config invalid: ${JSON.stringify(config)}`);
  const canvas = page.locator('#canvas'); await page.bringToFront(); await canvas.click({ position: { x: 32, y: 32 } });
  await page.keyboard.press('Escape'); await page.waitForTimeout(200); await canvas.click({ position: { x: 32, y: 32 } });
  await page.evaluate(() => { window.__bwB1Keys = []; window.addEventListener('keydown', (e) => { if (e.key === 'F12') window.__bwB1Keys.push({ key: e.key, code: e.code, trusted: e.isTrusted, repeat: e.repeat, target: e.target?.id, active: document.activeElement?.id }); }, { capture: true }); });

  const renderCount = forceFailure ? 1 : 2;
  for (let frame = 1; frame <= renderCount; frame++) {
    const consoleStart = consoleLines.length; await page.keyboard.press('F12');
    const receipt = forceFailure ?
      await waitReceipt((r) => r.status === 'CANCELLED' || r.status === 'FAIL', STAGE_MS) :
      await waitReceipt((r) => r.status === 'FRAME_READY' && r.frame === frame, STAGE_MS);
    let consoleEnd;
    if (PRODUCT_MODE) {
      await page.waitForTimeout(500);
      consoleEnd = consoleLines.length - 1;
    }
    else {
      consoleEnd = await waitAsyncTerminal(consoleStart, STAGE_MS);
    }
    const windowAsync = asyncEvents.filter((e) => e.consoleIndex >= consoleStart && e.consoleIndex <= consoleEnd);
    const windowB1 = b1Events.filter((e) => e.consoleIndex >= consoleStart && e.consoleIndex <= consoleEnd);
    const asyncResult = PRODUCT_MODE ?
      { ok: windowAsync.length === 0, errors: windowAsync.length ? ['diagnostic async markers present in product mode'] : [], states: [], sequence: null, productMode: true } :
      validateAsync(windowAsync, !forceFailure);
    const b1Result = PRODUCT_MODE ?
      { ok: windowB1.length === 0, errors: windowB1.length ? ['diagnostic B1 markers present in product mode'] : [], productMode: true } :
      (forceFailure ? validateB1Forced(windowB1) : validateB1Happy(windowB1));
    if (!asyncResult.ok || !b1Result.ok) throw new Error(`frame ${frame} marker gate failed: ${[...asyncResult.errors, ...b1Result.errors].join('; ')}`);
    const result = { frame, receipt, consoleStart, consoleEnd, asyncResult, b1Result, asyncEvents: windowAsync, b1Events: windowB1 };
    if (!forceFailure) {
      result.image = await captureGuest(PNG_GUEST[frame - 1], paths.frame[frame - 1]);
      if (result.image.width !== RENDER_WIDTH || result.image.height !== RENDER_HEIGHT || result.image.nonBlack === 0) throw new Error(`frame ${frame} invalid/black`);
      const golden = [GOLDEN_1, GOLDEN_2][frame - 1];
      const diff = spawnSync(OIIOTOOL, [golden, paths.frame[frame - 1], '--fail', FAIL_THRESHOLD, '--failpercent', FAIL_PERCENT, '--diff'], { encoding: 'utf8' });
      const text = `${diff.stdout || ''}${diff.stderr || ''}`; writeFileSync(paths.compare[frame - 1], text); writeFileSync(`${paths.compare[frame - 1]}.license`, CC0);
      result.comparator = parseComparator(text, diff.status);
      if (!result.comparator.pass && !PRODUCT_MODE) throw new Error(`frame ${frame} comparator failed`);
    }
    runs.push(result);
  }
  physicalKeys = await page.evaluate(() => window.__bwB1Keys || []);
  if (physicalKeys.length !== (forceFailure ? 1 : 2) || physicalKeys.some((k) => !k.trusted || k.repeat || k.code !== 'F12' || k.target !== 'canvas' || k.active !== 'canvas')) throw new Error(`trusted F12 receipt invalid: ${JSON.stringify(physicalKeys)}`);
  if (!forceFailure) {
    const delta = spawnSync(OIIOTOOL, [paths.frame[0], paths.frame[1], '--fail', FAIL_THRESHOLD, '--failpercent', FAIL_PERCENT, '--diff'], { encoding: 'utf8' });
    const text = `${delta.stdout || ''}${delta.stderr || ''}`; writeFileSync(paths.delta, text); writeFileSync(`${paths.delta}.license`, CC0);
    const parsed = parseComparator(text, delta.status); const over = Number.parseFloat(parsed.percentOver || '0') / 100;
    if (delta.status === 0 || !(over > MIN_DELTA_OVER_FRACTION)) throw new Error(`frame delta not nontrivial: ${JSON.stringify(parsed)}`);
    frameDelta = { ...parsed, pass: true, requiredFractionOver: MIN_DELTA_OVER_FRACTION };
  }
  await page.screenshot({ path: paths.screenshot, clip: { x: Math.round(gate.x), y: Math.round(gate.y), width: WIDTH, height: HEIGHT } });
  writeFileSync(`${paths.screenshot}.license`, CC0); screenshotSha = sha256(readFileSync(paths.screenshot));
}
catch (error) { runError = error.stack || error.message || String(error); }
finally { await context.close(); await browser.close(); }

const consoleText = `${consoleLines.join('\n')}\n`; writeFileSync(paths.console, consoleText); writeFileSync(`${paths.console}.license`, CC0);
const pixelAccepted = forceFailure || runs.every((run) => run.comparator?.pass === true);
const accepted = !runError && !pageCrashed && !pageErrors.length && !gpuErrors.length && preinit?.pass === true && screenshotSha && runs.length === (forceFailure ? 1 : 2) && pixelAccepted;
const artifactPaths = {
  javascript: `${BLENDER_WEB_BIN}/blender_browser.js`,
  wasm: `${BLENDER_WEB_BIN}/blender_browser.wasm`,
  data: `${BLENDER_WEB_BIN}/blender_browser.data`,
};
const artifacts = Object.fromEntries(Object.entries(artifactPaths).map(([key, path]) => {
  const bytes = readFileSync(path);
  return [key, { path, bytes: bytes.length, sha256: sha256(bytes) }];
}));
const manifest = {
  schema: PRODUCT_MODE ? 'blender-web.eevee-b1-product.v2' : 'blender-web.eevee-b1-runtime.v1', verdict: accepted ? 'PASS' : 'FAIL', generatedAt: new Date().toISOString(), mode: PRODUCT_MODE ? 'product-marker-independent' : MODE,
  driver: { path: DRIVER_PATH, sha256: sha256(readFileSync(DRIVER_PATH)) },
  artifacts,
  inputs: { blend: { path: BLEND_HOST, sha256: blendSha }, goldens: forceFailure ? [] : [GOLDEN_1, GOLDEN_2].map((path) => ({ path, sha256: sha256(readFileSync(path)) })) },
  mutation: { afterFrame: 1, caster: { object: 'Cylinder.004', locationYDelta: 0.35 }, light: { object: 'Sun', rotationYDelta: 0.25 } },
  shadowControl: { enabled: !DISABLE_SHADOWS }, renderSamplesOverride: RENDER_SAMPLES_OVERRIDE,
  invocation: { physicalF12Count: forceFailure ? 1 : 2, oneBoot: true, bpyRenderOperatorAbsent: true, keyReceipts: physicalKeys },
  contracts: PRODUCT_MODE ? { diagnosticEnvironmentAbsent: true, exactAsyncSemanticOrder: null, markerIndependent: true } : { asyncPrefix: ASYNC.prefix.trim(), b1Prefix: B1.prefix.trim(), b1ExactKeys: B1.exactKeys, forceEnvironment: forceFailure ? { [B1.forceKey]: '1' } : null },
  preinit, config, gate, runs, frameDelta, screenshot: { path: screenshotSha ? paths.screenshot : null, sha256: screenshotSha },
  assertions: { noGpuErrors: gpuErrors.length === 0, noPageErrors: pageErrors.length === 0, noCrash: !pageCrashed, pixelAccepted, accepted },
  failures: { runError, pageCrashed, pageErrors, gpuErrors },
};
writeFileSync(paths.manifest, `${JSON.stringify(manifest, null, 2)}\n`); writeFileSync(`${paths.manifest}.license`, CC0);
if (!accepted) { console.error(`EEVEE_B1_FAIL manifest=${paths.manifest}`); process.exit(1); }
console.log(`EEVEE_B1_PASS mode=${MODE} manifest=${paths.manifest}`);
