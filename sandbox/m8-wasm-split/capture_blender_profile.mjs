// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Capture the Binaryen split profile from a real headed Blender boot plus the
// launch-hot viewport workload: orbit, Tab into Edit Mode, extrude, Tab out.

import { createHash } from 'crypto';
import { createRequire } from 'module';
import {
  existsSync, mkdirSync, readFileSync, statSync, writeFileSync,
} from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import { validateCaptureProbeGeneratedSource } from './capture_probe_contract.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const DEFAULT_MODULES = '/Users/paws/plushly/game-platform/node_modules';
const PROFILE_MARKER = 'BW_SPLIT_PROFILE_EXPORT_V1';
const FINALIZER = join(REPO, 'scripts/finalize-wasm-split.py');

const PY_MONITOR = String.raw`
import bpy,json,os,sys,time,traceback
_bwsp={"last":None,"started":time.perf_counter(),"io_done":False}
os.write(2,("BW_SPLIT_CAPTURE_ARGV "+json.dumps({"argv":sys.argv},sort_keys=True,separators=(",",":"))+"\n").encode())
def _bwsp_state():
    o=bpy.data.objects.get("Cube")
    if o is None or o.type != 'MESH': return None
    w=bpy.context.window
    if w is None or w.screen is None: return None
    a=next((x for x in w.screen.areas if x.type == 'VIEW_3D'),None)
    if a is None: return None
    r=next((x for x in a.regions if x.type == 'WINDOW'),None)
    if r is None: return None
    return {"mode":o.mode,"verts":len(o.data.vertices),"edges":len(o.data.edges),"polys":len(o.data.polygons),"selected":sorted(x.name for x in bpy.context.selected_objects),"view":{"x":r.x,"y":r.y,"width":r.width,"height":r.height}}
def _bwsp_poll():
    s=_bwsp_state()
    if s is not None:
        key=(s["mode"],s["verts"],s["edges"],s["polys"],tuple(s["selected"]))
        if key != _bwsp["last"]:
            _bwsp["last"]=key
            s["elapsed_ms"]=round((time.perf_counter()-_bwsp["started"])*1000,3)
            os.write(2,("BW_SPLIT_STATE "+json.dumps(s,sort_keys=True,separators=(",",":"))+"\n").encode())
    return 0.02
bpy.app.timers.register(_bwsp_poll,first_interval=0.0,persistent=True)
def _bwsp_io_poll():
    signal="/tmp/bw-profile-io.go"
    if _bwsp["io_done"] or not os.path.exists(signal): return 0.02
    _bwsp["io_done"]=True
    result={"ok":False,"ops":{},"files":{}}
    try:
        o=bpy.data.objects.get("Cube")
        # Force a real evaluated subdivision path so the shared profile includes
        # work reached through Blender's pooled worker scheduler.
        mod=o.modifiers.new("BW_PROFILE_SUBSURF",'SUBSURF'); mod.levels=2
        dg=bpy.context.evaluated_depsgraph_get(); dg.update()
        evaluated=bpy.data.meshes.new_from_object(o.evaluated_get(dg)); bpy.data.meshes.remove(evaluated)
        o.modifiers.remove(mod)
        paths={"blend":"/tmp/bw-profile.blend","usd":"/tmp/bw-profile.usda","obj":"/tmp/bw-profile.obj","gltf":"/tmp/bw-profile.glb"}
        result["ops"]["blend_save"]=sorted(bpy.ops.wm.save_as_mainfile(filepath=paths["blend"],copy=True,compress=True))
        result["ops"]["usd_export"]=sorted(bpy.ops.wm.usd_export(filepath=paths["usd"],selected_objects_only=True))
        result["ops"]["obj_export"]=sorted(bpy.ops.wm.obj_export(filepath=paths["obj"],export_selected_objects=True))
        result["ops"]["gltf_export"]=sorted(bpy.ops.export_scene.gltf(filepath=paths["gltf"],export_format='GLB',use_selection=True))
        result["ops"]["usd_import"]=sorted(bpy.ops.wm.usd_import(filepath=paths["usd"]))
        result["ops"]["obj_import"]=sorted(bpy.ops.wm.obj_import(filepath=paths["obj"]))
        result["ops"]["gltf_import"]=sorted(bpy.ops.import_scene.gltf(filepath=paths["gltf"]))
        result["files"]={name:os.path.getsize(path) for name,path in paths.items()}
        result["ok"]=all(value == ['FINISHED'] for value in result["ops"].values()) and all(value > 0 for value in result["files"].values())
    except Exception:
        result["error"]=traceback.format_exc()
    os.write(2,("BW_SPLIT_IO "+json.dumps(result,sort_keys=True,separators=(",",":"))+"\n").encode())
    return None
bpy.app.timers.register(_bwsp_io_poll,first_interval=0.0,persistent=True)
`.trim();

function parseArgs(argv) {
  const out = { port: 8165, run: null, outRoot: join(HERE, 'profile-evidence'), timeoutMs: 180000,
    scenario: null, threads: 1 };
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === '--port') out.port = Number(argv[++index]);
    else if (arg === '--run') out.run = argv[++index];
    else if (arg === '--out-root') out.outRoot = resolve(argv[++index]);
    else if (arg === '--timeout-ms') out.timeoutMs = Number(argv[++index]);
    else if (arg === '--scenario') out.scenario = argv[++index];
    else if (arg === '--threads') out.threads = Number(argv[++index]);
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (!out.run || !/^[a-z0-9][a-z0-9._-]*$/i.test(out.run)) throw new Error('safe --run required');
  if (!['success', 'terminal-error'].includes(out.scenario)) {
    throw new Error('--scenario success|terminal-error required');
  }
  if (out.threads !== 1) throw new Error('two-phase CAPTURE requires exact --threads 1');
  if (!Number.isInteger(out.port) || out.port < 1 || out.port > 65535) throw new Error('bad port');
  return out;
}

function shaBytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function fileReceipt(path) {
  const stat = statSync(path);
  return { path: path.startsWith(REPO) ? path.slice(REPO.length + 1) : path, bytes: stat.size,
    sha256: shaBytes(readFileSync(path)) };
}

const occurrences = (source, needle) => source.split(needle).length - 1;

function playwright() {
  for (const root of [process.env.BW_NODE_MODULES, process.env.NODE_PATH, DEFAULT_MODULES].filter(Boolean)) {
    try {
      const require = createRequire(join(root, 'package.json'));
      return { chromium: require('playwright').chromium, root };
    } catch (_) {}
  }
  throw new Error('Playwright unavailable');
}

const sleep = (milliseconds) => new Promise((done) => setTimeout(done, milliseconds));

function pixelProof(PNG, buffer) {
  const png = PNG.sync.read(buffer);
  let samples = 0;
  let nonblack = 0;
  const colors = new Set();
  for (let y = 0; y < png.height; y += 3) {
    for (let x = 0; x < png.width; x += 3) {
      const at = (y * png.width + x) * 4;
      const r = png.data[at];
      const g = png.data[at + 1];
      const b = png.data[at + 2];
      samples++;
      if (r + g + b > 30) nonblack++;
      colors.add(`${r >> 3},${g >> 3},${b >> 3}`);
    }
  }
  const nonblackRatio = nonblack / samples;
  return {
    width: png.width,
    height: png.height,
    nonblackRatio,
    quantizedColors: colors.size,
    pass: png.width >= 1000 && png.height >= 600 && nonblackRatio > 0.1 && colors.size > 128,
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const outDir = join(options.outRoot, options.run);
  if (existsSync(outDir)) throw new Error(`refusing overwrite: ${outDir}`);
  mkdirSync(options.outRoot, { recursive: true });
  mkdirSync(outDir);

  const bin = resolve(process.env.BLENDER_WEB_BIN || join(REPO, 'build-wasm-windowed-opt/bin'));
  const paths = Object.fromEntries(['js', 'wasm', 'wasm.orig', 'data', 'split-build.json'].map((suffix) =>
    [suffix, join(bin, `blender_browser.${suffix}`)]));
  for (const path of Object.values(paths)) if (!existsSync(path)) throw new Error(`missing ${path}`);
  const splitBuild = JSON.parse(readFileSync(paths['split-build.json'], 'utf8'));
  const generatedJs = readFileSync(paths.js, 'utf8');
  const currentFinalizer = fileReceipt(FINALIZER);
  const currentProfileExport = fileReceipt(join(REPO, 'platform_web/split/profile-export.js'));
  const refresh = splitBuild.shared_memory_view_refresh;
  const rangeSync = splitBuild.pthread_memory_range_sync;
  if (splitBuild.mode !== 'capture' || splitBuild.verdict !== 'PASS' ||
      splitBuild.original.sha256 !== fileReceipt(paths['wasm.orig']).sha256 ||
      splitBuild.js.bytes !== fileReceipt(paths.js).bytes ||
      splitBuild.js.sha256 !== fileReceipt(paths.js).sha256 ||
      splitBuild.instrumented.sha256 !== fileReceipt(paths.wasm).sha256 ||
      splitBuild.instrumented.bytes !== fileReceipt(paths.wasm).bytes ||
      splitBuild.profile_export?.sha256 !== currentProfileExport.sha256 ||
      splitBuild.profile_export?.bytes !== currentProfileExport.bytes ||
      splitBuild.profile_export?.persisted_pre_entry_attestation !== true ||
      splitBuild.profile_export?.post_apply_probe_counter !== true ||
      splitBuild.profile_export?.pre_entry_marker !== 'BW_SPLIT_CAPTURE_PREENTRY_ATTESTATION_V1' ||
      splitBuild.profile_export?.pre_entry_marker_count !== 1 ||
      splitBuild.capture_probe_dispatch?.contract !== 'capture-worker-core-probe-ack-v1' ||
      splitBuild.capture_probe_dispatch?.marker !== 'BW_SPLIT_CAPTURE_PROBE_CORE_DISPATCH_V1' ||
      splitBuild.capture_probe_dispatch?.anchor_count_before !== 1 ||
      splitBuild.capture_probe_dispatch?.anchor_count_after !== 0 ||
      splitBuild.capture_probe_dispatch?.marker_count_after !== 1 ||
      splitBuild.capture_probe_dispatch?.probe_branch_count_after !== 1 ||
      splitBuild.capture_probe_dispatch?.core_branch_count_after !== 1 ||
      splitBuild.capture_probe_dispatch?.postjs_probe_handler_count_after !== 1 ||
      splitBuild.capture_probe_dispatch?.postjs_outgoing_ack_count_after !== 1 ||
      splitBuild.capture_probe_dispatch?.main_ack_listener_count_after !== 1 ||
      splitBuild.capture_atomic_diagnostics?.contract !==
        'capture-mailbox-atomic-diagnostics-v1' ||
      splitBuild.capture_atomic_diagnostics?.marker !== 'BW_SPLIT_CAPTURE_ATOMIC_DIAG_V1' ||
      splitBuild.capture_atomic_diagnostics?.anchor_count_before !== 1 ||
      splitBuild.capture_atomic_diagnostics?.anchor_count_after !== 0 ||
      splitBuild.capture_atomic_diagnostics?.marker_count_after !== 1 ||
      splitBuild.capture_atomic_diagnostics?.wait_tag_count_after !== 1 ||
      splitBuild.capture_atomic_diagnostics?.store_tag_count_after !== 1 ||
      splitBuild.capture_atomic_diagnostics?.range_sync_tag_count_after !== 1 ||
      splitBuild.capture_atomic_diagnostics?.listener_count_after !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.contract !==
        'capture-pthread-entry-stack-diagnostics-v1' ||
      splitBuild.capture_thread_entry_diagnostics?.marker !==
        'BW_SPLIT_CAPTURE_THREAD_ENTRY_DIAG_V1' ||
      splitBuild.capture_thread_entry_diagnostics?.entry_anchor_count_before !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.entry_anchor_count_after !== 0 ||
      splitBuild.capture_thread_entry_diagnostics?.marker_count_after !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.stage_marker !==
        'BW_SPLIT_CAPTURE_THREAD_ENTRY_STAGE_V1' ||
      splitBuild.capture_thread_entry_diagnostics?.stage_anchor_count_before !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.stage_anchor_count_after !== 0 ||
      splitBuild.capture_thread_entry_diagnostics?.stage_marker_count_after !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.stage_count_after !== 5 ||
      splitBuild.capture_thread_entry_diagnostics?.main_dispatch_marker !==
        'BW_SPLIT_CAPTURE_MAIN_DIAGNOSTIC_DISPATCH_V1' ||
      splitBuild.capture_thread_entry_diagnostics?.main_dispatch_anchor_count_before !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.main_dispatch_anchor_count_after !== 0 ||
      splitBuild.capture_thread_entry_diagnostics?.main_dispatch_marker_count_after !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.main_atomic_case_count_after !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.main_entry_case_count_after !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.post_count_after !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.listener_count_after !== 1 ||
      splitBuild.capture_thread_entry_diagnostics?.stack_high_offset !== 48 ||
      splitBuild.capture_thread_entry_diagnostics?.stack_size_offset !== 52 ||
      splitBuild.finalizer?.sha256 !== currentFinalizer.sha256 ||
      refresh?.contract !== 'shared-memory-fixed-view-refresh-v2' ||
      refresh?.refresh_marker !== 'BW_SPLIT_SHARED_MEMORY_VIEW_REFRESH_V1' ||
      refresh?.guard_marker !== 'BW_SPLIT_SHARED_MEMORY_GROWABLE_VIEW_GUARD_V1' ||
      refresh?.refresh_anchor_count_before !== 1 ||
      refresh?.refresh_anchor_count_after !== 0 ||
      refresh?.refresh_marker_count_after !== 1 ||
      refresh?.refresh_replacement_count_after !== 1 ||
      refresh?.guard_anchor_count_before !== 1 ||
      refresh?.guard_anchor_count_after !== 0 ||
      refresh?.guard_marker_count_after !== 1 ||
      refresh?.guard_replacement_count_after !== 1 ||
      refresh?.identity_predicate_count_after !== 1 ||
      refresh?.byte_length_predicate_count_after !== 1 ||
      refresh?.growable_length_guard_count_after !== 1) {
    throw new Error('capture build receipt/original binding failed');
  }
  if (rangeSync?.contract !== 'pthread-cross-realm-memory-range-sync-v1' ||
      rangeSync?.helper_marker !== 'BW_SPLIT_PTHREAD_MEMORY_RANGE_SYNC_V1' ||
      rangeSync?.stack_marker !== 'BW_SPLIT_PTHREAD_STACK_RANGE_SYNC_V1' ||
      rangeSync?.mailbox_marker !== 'BW_SPLIT_PTHREAD_MAILBOX_RANGE_SYNC_V1' ||
      rangeSync?.helper_anchor_count_before !== 1 ||
      rangeSync?.helper_anchor_count_after !== 0 ||
      rangeSync?.helper_marker_count_after !== 1 ||
      rangeSync?.stack_anchor_count_before !== 1 ||
      rangeSync?.stack_anchor_count_after !== 0 ||
      rangeSync?.stack_marker_count_after !== 1 ||
      rangeSync?.mailbox_anchor_count_before !== 1 ||
      rangeSync?.mailbox_anchor_count_after !== 0 ||
      rangeSync?.mailbox_marker_count_after !== 1 ||
      rangeSync?.grow_zero_count_after !== 1 ||
      rangeSync?.bounded_attempt_count !== 3 ||
      rangeSync?.metadata_end_offset !== 116 ||
      rangeSync?.stack_high_offset !== 48 ||
      rangeSync?.stack_size_offset !== 52) {
    throw new Error('capture build pthread memory range-sync binding failed');
  }
  const exactRefresh =
    'function growMemViews(){/*BW_SPLIT_SHARED_MEMORY_VIEW_REFRESH_V1*/' +
    'var b=wasmMemory.buffer;if(b!=HEAP8.buffer||b.byteLength!=HEAP8.byteLength){updateMemoryViews()}}';
  const exactGuard =
    'if(HEAP8?.buffer?.growable&&HEAP8.byteLength==getMemoryBuffer().byteLength){/*' +
    'BW_SPLIT_SHARED_MEMORY_GROWABLE_VIEW_GUARD_V1*/return}';
  if (occurrences(generatedJs, exactRefresh) !== 1 ||
      occurrences(generatedJs, exactGuard) !== 1 ||
      occurrences(generatedJs, 'BW_SPLIT_SHARED_MEMORY_VIEW_REFRESH_V1') !== 1 ||
      occurrences(generatedJs, 'BW_SPLIT_SHARED_MEMORY_GROWABLE_VIEW_GUARD_V1') !== 1 ||
      occurrences(generatedJs, 'BW_SPLIT_CAPTURE_MAIN_DIAGNOSTIC_DISPATCH_V1') !== 1 ||
      occurrences(generatedJs, 'BW_SPLIT_CAPTURE_PREENTRY_ATTESTATION_V1') !== 1 ||
      occurrences(generatedJs, 'case "bwCaptureAtomicError"') !== 1 ||
      occurrences(generatedJs, 'case "bwCaptureThreadEntryError"') !== 1 ||
      occurrences(generatedJs,
        'function growMemViews(){if(wasmMemory.buffer!=HEAP8.buffer){updateMemoryViews()}}') !== 0 ||
      occurrences(generatedJs, 'if(HEAP8?.buffer?.growable)return;') !== 0) {
    throw new Error('capture generated JS shared-memory guard binding failed');
  }
  if (occurrences(generatedJs, 'BW_SPLIT_PTHREAD_MEMORY_RANGE_SYNC_V1') !== 1 ||
      occurrences(generatedJs, 'BW_SPLIT_PTHREAD_STACK_RANGE_SYNC_V1') !== 1 ||
      occurrences(generatedJs, 'BW_SPLIT_PTHREAD_MAILBOX_RANGE_SYNC_V1') !== 1 ||
      occurrences(generatedJs, 'wasmMemory.grow(0)') !== 1 ||
      occurrences(generatedJs,
        'function bwSyncPthreadMemoryRange(ptr,end){/*BW_SPLIT_PTHREAD_MEMORY_RANGE_SYNC_V1*/') !== 1 ||
      occurrences(generatedJs,
        'function establishStackSpace(pthread_ptr){/*BW_SPLIT_PTHREAD_STACK_RANGE_SYNC_V1*/') !== 1 ||
      occurrences(generatedJs,
        'var heap32;try{heap32=bwSyncPthreadMemoryRange(pthread_ptr,pthread_ptr+116)') !== 1 ||
      occurrences(generatedJs,
        'function establishStackSpace(pthread_ptr){var stackHigh=(growMemViews(),HEAPU32)') !== 0 ||
      occurrences(generatedJs,
        'Atomics.waitAsync((growMemViews(),HEAP32),pthread_ptr>>2,pthread_ptr)') !== 0 ||
      occurrences(generatedJs,
        'Atomics.store((growMemViews(),HEAP32),waitingAsync>>2,1)') !== 0) {
    throw new Error('capture generated JS pthread memory range-sync binding failed');
  }
  const generatedProbeContract = validateCaptureProbeGeneratedSource(generatedJs);

  const consoleLines = [];
  const states = [];
  const pageErrors = [];
  const requests = [];
  const trustedInputs = [];
  let ioReceipt = null;
  let profileBefore;
  let profileHot;
  let profileAfter;
  let canvasReceipt;
  let initialPixelReceipt;
  let settledPixelReceipt;
  let bridgeHotReceipt;
  let runtimeArgv = null;
  let interactionDoneMs = null;
  let controller = null;
  let lastNativeStatus = null;
  let atomicDiagnostics = [];
  let threadEntryDiagnostics = [];
  const transitions = [];
  let successCoverageComplete = false;
  let fatal = null;
  const { chromium, root: playwrightRoot } = playwright();
  const { PNG } = createRequire(join(playwrightRoot, 'package.json'))('pngjs');
  const browser = await chromium.launch({ headless: false });
  const browserVersion = browser.version();
  const started = Date.now();
  let page;
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
    page = await context.newPage();
    page.on('console', (message) => {
      const line = message.text();
      consoleLines.push(line);
      const match = /^BW_SPLIT_STATE (\{.*\})$/.exec(line);
      if (match) states.push(JSON.parse(match[1]));
      const ioMatch = /^BW_SPLIT_IO (\{.*\})$/.exec(line);
      if (ioMatch) ioReceipt = JSON.parse(ioMatch[1]);
      const argvMatch = /^BW_SPLIT_CAPTURE_ARGV (\{.*\})$/.exec(line);
      if (argvMatch) runtimeArgv = JSON.parse(argvMatch[1]).argv;
      const atomicMatch = /^BW_SPLIT_CAPTURE_ATOMIC (\{.*\})$/.exec(line);
      if (atomicMatch) atomicDiagnostics.push(JSON.parse(atomicMatch[1]));
      const entryMatch = /^BW_SPLIT_CAPTURE_THREAD_ENTRY (\{.*\})$/.exec(line);
      if (entryMatch) threadEntryDiagnostics.push(JSON.parse(entryMatch[1]));
    });
    page.on('pageerror', (error) => pageErrors.push({ name: error.name, message: error.message,
      stack: error.stack || null, filename: error.filename || null,
      lineNumber: error.lineNumber ?? null, columnNumber: error.columnNumber ?? null,
      location: error.location || null }));
    page.on('crash', () => pageErrors.push({ name: 'PageCrash', message: 'PAGE_CRASH', stack: null }));
    page.on('request', (request) => requests.push(request.url()));
    await page.addInitScript(({ monitor, threads }) => {
      window.__BW_ARGS = ['--threads', String(threads)];
      window.__BW_PYEXPR = monitor;
      window.__bwSplitInputs = [];
      for (const type of ['keydown', 'mousedown', 'mousemove', 'mouseup']) {
        addEventListener(type, (event) => {
          if (event.target?.id === 'canvas') window.__bwSplitInputs.push({
            type, key: event.key || null, button: event.button ?? null, isTrusted: event.isTrusted,
          });
        }, true);
      }
    }, { monitor: PY_MONITOR, threads: options.threads });
    await page.goto(`http://127.0.0.1:${options.port}/windowed.html?gate=1280x720`, {
      waitUntil: 'domcontentloaded', timeout: options.timeoutMs,
    });
    await page.waitForFunction(() => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'),
      null, { timeout: options.timeoutMs, polling: 100 });
    await page.waitForFunction(() => window.__bwModule?.bwSplitProfileContract?.marker ===
      'BW_SPLIT_PROFILE_EXPORT_V1', null, { timeout: options.timeoutMs });

    const waitState = async (predicate, label, after = 0) => {
      const deadline = Date.now() + options.timeoutMs;
      while (Date.now() < deadline) {
        const state = states.slice(after).reverse().find(predicate);
        if (state) return state;
        await sleep(20);
      }
      throw new Error(`timeout waiting for ${label}; states=${JSON.stringify(states)}`);
    };
    const ready = await waitState((state) => state.mode === 'OBJECT' && state.verts === 8, 'object ready');
    const canvas = page.locator('#canvas');
    const pixelDeadline = Date.now() + options.timeoutMs;
    while (Date.now() < pixelDeadline) {
      const screenshot = await canvas.screenshot();
      const proof = pixelProof(PNG, screenshot);
      if (proof.pass) {
        initialPixelReceipt = { ...proof, atMs: Date.now() - started };
        writeFileSync(join(outDir, 'initial-semantic-pixels.png'), screenshot, { flag: 'wx' });
        writeFileSync(join(outDir, 'initial-semantic-pixels.png.license'),
          'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n',
          { flag: 'wx' });
        break;
      }
      await sleep(100);
    }
    if (!initialPixelReceipt) throw new Error('semantic first pixels not reached before profile capture');
    profileBefore = Uint8Array.from(await page.evaluate(() =>
      Array.from(window.__bwModule.bwWriteSplitProfile())));

    const box = await canvas.boundingBox();
    if (!box) throw new Error('canvas has no box');
    const center = {
      x: box.x + ready.view.x + ready.view.width / 2,
      y: box.y + box.height - (ready.view.y + ready.view.height / 2),
    };
    await page.mouse.move(center.x, center.y);
    await canvas.focus();
    await page.keyboard.press('Escape');

    // Trusted physical orbit.
    await page.mouse.down({ button: 'middle' });
    await page.mouse.move(center.x + 70, center.y + 35, { steps: 8 });
    await page.mouse.up({ button: 'middle' });

    // First execute the exact tight runtime-gate sequence. Enter confirms a
    // zero-distance extrusion, which still exercises the real mesh operator and
    // changes topology.
    let stateStart = states.length;
    await page.keyboard.press('Tab');
    await waitState((state) => state.mode === 'EDIT', 'first edit mode', stateStart);
    await page.keyboard.press('e');
    await page.keyboard.press('Enter');
    await page.keyboard.press('Tab');
    let extruded = await waitState((state) => state.mode === 'OBJECT' && state.verts > 8,
      'first extruded object', stateStart);

    trustedInputs.push(...await page.evaluate(() => window.__bwSplitInputs || []));
    interactionDoneMs = Date.now() - started;
    if (!trustedInputs.length || !trustedInputs.every((event) => event.isTrusted) ||
        !trustedInputs.some((event) => event.type === 'keydown' && event.key === 'Tab') ||
        !trustedInputs.some((event) => event.type === 'keydown' && event.key === 'e') ||
        !trustedInputs.some((event) => event.type === 'mousedown' && event.button === 1)) {
      throw new Error(`trusted semantic interaction proof failed: ${JSON.stringify(trustedInputs)}`);
    }
    const earlyShard = requests.filter((url) => new URL(url).pathname.endsWith('.deferred.wasm'));
    if (earlyShard.length) throw new Error(`shard requested before trusted interaction: ${JSON.stringify(earlyShard)}`);
    const at = runtimeArgv?.findIndex((value, index) => value === '--threads' &&
      runtimeArgv[index + 1] === String(options.threads));
    if (!(at >= 0)) throw new Error(`runtime argv did not bind --threads 1: ${JSON.stringify(runtimeArgv)}`);

    const generation = 1;
    const status = async (label) => {
      const value = await page.evaluate(() => window.__bwModule.bwCaptureSplitStatus());
      transitions.push({ label, atMs: Date.now() - started, value });
      lastNativeStatus = value;
      return value;
    };
    const waitGeneration = async (field, expected) => {
      const deadline = Date.now() + options.timeoutMs;
      while (Date.now() < deadline) {
        const value = await status(`poll-${field}`);
        if (value.errorGeneration === generation && field !== 'errorGeneration') {
          throw new Error(`controller terminal error while waiting ${field}: ${JSON.stringify(value)}`);
        }
        if (value[field] === expected) return value;
        await sleep(10);
      }
      throw new Error(`controller timeout waiting ${field}=${expected}`);
    };
    const call = async (name, args) => {
      const result = await page.evaluate(({ name, args }) =>
        window.__bwModule.bwCaptureSplitCall(name, args), { name, args });
      transitions.push({ label: `call-${name}`, atMs: Date.now() - started, result, args });
      return result;
    };
    controller = { status: 'IN_PROGRESS', scenario: options.scenario, generation, transitions };
    controller.bootstrap = await status('bootstrap');
    if (await call('BW_web_split_request_park', [generation]) !== 1) throw new Error('PARK rejected');
    const parked = await waitGeneration('parkedGeneration', generation);
    controller.parked = parked;
    const workerStatus = await page.evaluate((generation) =>
      window.__bwModule.bwCaptureStabilizeWorkers(generation), generation);
    controller.workerStatus = workerStatus;
    if (workerStatus.workers < 8) throw new Error(`fewer than eight loaded workers: ${JSON.stringify(workerStatus)}`);

    if (options.scenario === 'terminal-error') {
      const rejected = await call('BW_web_split_request_apply', [generation, 8]);
      if (!(rejected < 0)) throw new Error(`out-of-order APPLY was not rejected: ${rejected}`);
      const terminal = await waitGeneration('errorGeneration', generation);
      controller.terminal = terminal;
      const terminalPass = terminal.phase === 11 && terminal.errorGeneration === generation &&
        terminal.offendingGeneration === generation && terminal.errorCode !== 0 &&
        terminal.appliedGeneration === 0 && terminal.resumedGeneration === 0;
      controller = { status: terminalPass ? 'PASS' : 'FAIL', scenario: options.scenario,
        generation, workerStatus, transitions, parked, terminal };
      if (!terminalPass) throw new Error(`terminal error contract failed: ${JSON.stringify(controller)}`);
      profileHot = Uint8Array.from(await page.evaluate(() =>
        Array.from(window.__bwModule.bwWriteSplitProfile())));
      profileAfter = profileHot.slice();
      settledPixelReceipt = initialPixelReceipt;
    } else {
      const preparedEpoch = workerStatus.stabilizationEpoch;
      if (await call('BW_web_split_request_prepared', [generation, workerStatus.workers,
        workerStatus.acknowledgements, workerStatus.instances, workerStatus.localInstances,
        workerStatus.pending, workerStatus.protocolErrors, preparedEpoch]) !== 1) {
        throw new Error('PREPARED rejected');
      }
      const prepared = await waitGeneration('preparedGeneration', generation);
      controller.prepared = prepared;
      if (await call('BW_web_split_request_apply', [generation, 8]) !== 1) throw new Error('APPLY rejected');
      const applied = await waitGeneration('appliedGeneration', generation);
      controller.applied = applied;
      const finalWorkers = await page.evaluate(({ generation, preparedWorkerIds }) =>
        window.__bwModule.bwCaptureAttestPageReady(generation, preparedWorkerIds),
      { generation, preparedWorkerIds: workerStatus.workerIds });
      if (finalWorkers.workers < workerStatus.workers) throw new Error('post-APPLY worker set shrank');
      const expectedLateWorkerIds = finalWorkers.workerIds.filter((id) =>
        !workerStatus.workerIds.includes(id));
      const lateWorkers = expectedLateWorkerIds.length;
      if (finalWorkers.preparedWorkerIds.join(',') !== workerStatus.workerIds.join(',') ||
          finalWorkers.lateWorkerIds.join(',') !== expectedLateWorkerIds.join(',') ||
          finalWorkers.latePreEntryLoadIds.join(',') !== expectedLateWorkerIds.join(',') ||
          finalWorkers.pendingWorkerIds.length !== 0 || finalWorkers.errorWorkerIds.length !== 0 ||
          finalWorkers.pending !== 0 || finalWorkers.protocolErrors !== 0 ||
          finalWorkers.postApplyProbeCount !== 0) {
        throw new Error(`PAGE_READY non-messaging attestation failed: ${JSON.stringify(finalWorkers)}`);
      }
      const pageReadyEpoch = finalWorkers.stabilizationEpoch;
      if (await call('BW_web_split_request_page_ready', [generation, finalWorkers.workers,
        finalWorkers.acknowledgements, finalWorkers.instances, finalWorkers.localInstances,
        finalWorkers.pending, finalWorkers.protocolErrors, lateWorkers, pageReadyEpoch]) !== 1) {
        throw new Error('PAGE_READY rejected');
      }
      const pageReady = await waitGeneration('pageReadyGeneration', generation);
      controller.pageReady = pageReady;
      const postPageReadyWorkers = await page.evaluate(({ generation, workerIds }) =>
        window.__bwModule.bwCaptureResumeAfterStable(generation, workerIds),
      { generation, workerIds: finalWorkers.workerIds });
      if (postPageReadyWorkers.workers !== finalWorkers.workers ||
          postPageReadyWorkers.workerIds.join(',') !== finalWorkers.workerIds.join(',') ||
          postPageReadyWorkers.preparedWorkerIds.join(',') !== finalWorkers.preparedWorkerIds.join(',') ||
          postPageReadyWorkers.lateWorkerIds.join(',') !== finalWorkers.lateWorkerIds.join(',') ||
          postPageReadyWorkers.latePreEntryLoadIds.join(',') !== finalWorkers.latePreEntryLoadIds.join(',') ||
          postPageReadyWorkers.pending !== 0 || postPageReadyWorkers.protocolErrors !== 0 ||
          postPageReadyWorkers.postApplyProbeCount !== 0 ||
          pageReady.pageReadyStabilizationEpoch !== pageReadyEpoch) {
        throw new Error(`PAGE_READY post-ACK drift: ${JSON.stringify({ finalWorkers, postPageReadyWorkers, pageReady })}`);
      }
      const resumed = await waitGeneration('resumedGeneration', generation);
      controller.resumed = resumed;
      const successPass = resumed.phase === 10 && resumed.requestGeneration === generation &&
        resumed.parkedGeneration === generation && resumed.preparedGeneration === generation &&
        resumed.appliedGeneration === generation && resumed.pageReadyGeneration === generation &&
        resumed.resumedGeneration === generation && resumed.errorGeneration === 0 &&
        resumed.activeThreads === 8 && resumed.nativeReady === 1 && resumed.openexrThreads === 8 &&
        resumed.oiioThreads === 8 && resumed.reloadRequired === 0;
      controller = { status: successPass ? 'PASS' : 'FAIL', scenario: options.scenario,
        generation, workerStatus, finalWorkers, postPageReadyWorkers, lateWorkers,
        preparedEpoch, pageReadyEpoch,
        transitions, parked, prepared,
        applied, pageReady, resumed };
      if (!successPass) throw new Error(`success controller contract failed: ${JSON.stringify(controller)}`);

    // Repeat the launch-only interaction only after the exact RESUME ACK. This
    // proves ordinary WM work and subsequent coverage remain gated while parked.
    // scheduled on a different pooled worker without pulling file IO/rendering
    // into the critical module.
    await sleep(500);
    await page.mouse.down({ button: 'middle' });
    await page.mouse.move(center.x - 45, center.y + 20, { steps: 6 });
    await page.mouse.up({ button: 'middle' });
    stateStart = states.length;
    await page.keyboard.press('Tab');
    await waitState((state) => state.mode === 'EDIT', 'second edit mode', stateStart);
    await page.keyboard.press('e');
    await page.keyboard.press('Enter');
    await sleep(500);
    await page.keyboard.press('Tab');
    extruded = await waitState((state) => state.mode === 'OBJECT' && state.verts > 16,
      'second extruded object', stateStart);

    // Freeze the launch-hot profile only after the actual product pixels remain
    // semantic following the trusted interaction and the browser has had a
    // bounded quiet interval to execute post-present work.
    await sleep(2000);
    const settledScreenshot = await canvas.screenshot();
    settledPixelReceipt = { ...pixelProof(PNG, settledScreenshot), atMs: Date.now() - started };
    if (!settledPixelReceipt.pass) {
      throw new Error(`semantic pixels did not survive hot interaction: ${JSON.stringify(settledPixelReceipt)}`);
    }
    writeFileSync(join(outDir, 'settled-hot-pixels.png'), settledScreenshot, { flag: 'wx' });
    writeFileSync(join(outDir, 'settled-hot-pixels.png.license'),
      'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n',
      { flag: 'wx' });
    // Public file staging calls the exported WasmFS bridge on the browser page
    // main thread. Keep only this small write/read/unlink seam in the launch
    // module so an import can stage bytes before the deferred shard is ready;
    // the actual Blender format operators remain deferred coverage below.
    bridgeHotReceipt = await page.evaluate(() => {
      const path = '/tmp/bw-split-hot-bridge.bin';
      const expected = new Uint8Array([0x42, 0x57, 0x53, 0x46]);
      window.__bwModule.FS.writeFile(path, expected);
      const actual = window.__bwModule.FS.readFile(path);
      window.__bwModule.FS.unlink(path);
      let removed = false;
      try { window.__bwModule.FS.readFile(path); }
      catch { removed = true; }
      return { bytes: Array.from(actual), removed };
    });
    if (JSON.stringify(bridgeHotReceipt.bytes) !== JSON.stringify([0x42, 0x57, 0x53, 0x46]) ||
        bridgeHotReceipt.removed !== true) {
      throw new Error(`main-thread WasmFS bridge hot proof failed: ${JSON.stringify(bridgeHotReceipt)}`);
    }
    profileHot = Uint8Array.from(await page.evaluate(() =>
      Array.from(window.__bwModule.bwWriteSplitProfile())));

    // Trigger the real project-file and launch-tier interchange paths only after
    // first pixels and trusted viewport interaction. The Python timer performs
    // genuine Blender operators; the signal is not an operator injection.
    await page.evaluate(() => window.__bwModule.FS.writeFile('/tmp/bw-profile-io.go', new Uint8Array([1])));
    const ioDeadline = Date.now() + options.timeoutMs;
    while (!ioReceipt && Date.now() < ioDeadline) await sleep(50);
    if (!ioReceipt?.ok) throw new Error(`profile IO workload failed: ${JSON.stringify(ioReceipt)}`);

    profileAfter = Uint8Array.from(await page.evaluate(() =>
      Array.from(window.__bwModule.bwWriteSplitProfile())));
    trustedInputs.splice(0, trustedInputs.length, ...await page.evaluate(() => window.__bwSplitInputs || []));
    canvasReceipt = await page.evaluate(() => {
      const canvas = document.querySelector('#canvas');
      return { backing: [canvas.width, canvas.height], presents: window.__bwModule._bw_present_count?.(),
        contract: window.__bwModule.bwSplitProfileContract, crossOriginIsolated };
    });
    await page.screenshot({ path: join(outDir, 'profile-workload.png') });
    writeFileSync(join(outDir, 'profile-workload.png.license'),
      'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n');
    if (extruded.verts <= 16) throw new Error('repeated extrude did not change topology twice');
    successCoverageComplete = true;
    }
  } catch (error) {
    fatal = error?.stack || String(error);
  } finally {
    if (page) {
      try {
        lastNativeStatus = await page.evaluate(() => window.__bwModule?.bwCaptureSplitStatus?.() || null);
      } catch (_) {}
      try {
        const exactDiagnostics = await page.evaluate(() =>
          window.__bwModule?.bwCaptureAtomicDiagnostics?.() || []);
        if (exactDiagnostics.length) atomicDiagnostics = exactDiagnostics;
      } catch (_) {}
      try {
        const exactEntryDiagnostics = await page.evaluate(() =>
          window.__bwModule?.bwCaptureThreadEntryDiagnostics?.() || []);
        if (exactEntryDiagnostics.length) threadEntryDiagnostics = exactEntryDiagnostics;
      } catch (_) {}
    }
    if (controller && fatal && controller.status === 'IN_PROGRESS') controller.status = 'FAIL';
    await browser.close();
  }

  if (profileBefore) writeFileSync(join(outDir, 'profile-before.data'), profileBefore, { flag: 'wx' });
  if (profileHot) writeFileSync(join(outDir, 'profile-hot.data'), profileHot, { flag: 'wx' });
  if (profileAfter) writeFileSync(join(outDir, 'profile.data'), profileAfter, { flag: 'wx' });
  const hotChanged = profileBefore && profileHot && profileBefore.length === profileHot.length ?
    profileHot.reduce((count, byte, index) => count + (byte !== profileBefore[index] ? 1 : 0), 0) : 0;
  const changed = profileBefore && profileAfter && profileBefore.length === profileAfter.length ?
    profileAfter.reduce((count, byte, index) => count + (byte !== profileBefore[index] ? 1 : 0), 0) : 0;
  const external = requests.filter((url) => !['127.0.0.1', 'localhost'].includes(new URL(url).hostname));
  const trustedPass = trustedInputs.length > 10 && trustedInputs.every((event) => event.isTrusted) &&
    trustedInputs.some((event) => event.type === 'keydown' && event.key === 'Tab') &&
    trustedInputs.some((event) => event.type === 'keydown' && event.key === 'e') &&
    trustedInputs.some((event) => event.type === 'mousedown' && event.button === 1);
  const gpuErrors = consoleLines.filter((line) => /\[bw\]\[GPU-(?:ERROR|LOST)\]/.test(line));
  const commonPass = !fatal && pageErrors.length === 0 && external.length === 0 && gpuErrors.length === 0 &&
    profileAfter?.length > splitBuild.facts.total_functions &&
    profileAfter?.length <= splitBuild.reserve_bytes && trustedPass &&
    initialPixelReceipt?.pass === true && controller?.status === 'PASS';
  const successPass = options.scenario === 'success' && hotChanged > 0 && changed > hotChanged &&
    canvasReceipt?.contract?.marker === PROFILE_MARKER && canvasReceipt?.contract?.sharedMainMemory === true &&
    canvasReceipt?.crossOriginIsolated === true && canvasReceipt?.presents >= 2 &&
    settledPixelReceipt?.pass === true && bridgeHotReceipt?.removed === true && ioReceipt?.ok === true &&
    successCoverageComplete;
  const terminalPass = options.scenario === 'terminal-error' && changed === hotChanged &&
    controller?.terminal?.phase === 11 && controller?.terminal?.errorGeneration === 1 && ioReceipt === null;
  const pass = commonPass && (successPass || terminalPass);

  writeFileSync(join(outDir, 'console.log'), consoleLines.join('\n') + '\n');
  writeFileSync(join(outDir, 'states.json'), JSON.stringify(states, null, 2) + '\n');
  writeFileSync(join(outDir, 'trusted-inputs.json'), JSON.stringify(trustedInputs, null, 2) + '\n');
  writeFileSync(join(outDir, 'requests.json'), JSON.stringify(requests, null, 2) + '\n');
  const artifacts = {};
  for (const name of ['profile-before.data', 'profile-hot.data', 'profile.data', 'profile-workload.png',
    'initial-semantic-pixels.png', 'initial-semantic-pixels.png.license', 'settled-hot-pixels.png',
    'settled-hot-pixels.png.license', 'console.log', 'states.json',
    'trusted-inputs.json', 'requests.json']) {
    if (existsSync(join(outDir, name))) artifacts[name] = fileReceipt(join(outDir, name));
  }
  const receipt = {
    schema: 'blender-web.wasm-split-profile.v1', status: pass ? 'PASS' : 'FAIL', run: options.run,
    scenario: options.scenario,
    fatal, browser: { version: browserVersion, playwrightRoot, headed: true },
    workload: ['boot-to-decoded-semantic-pixels', 'trusted-middle-mouse-orbit',
      'trusted-Tab-edit', 'trusted-E-extrude-confirm', 'trusted-Tab-object',
      'repeat-orbit-edit-extrude-across-worker-schedule', 'post-interaction-semantic-pixel-settle',
      'page-main-WasmFS-write-read-unlink',
      'pooled-evaluated-subsurf', 'blend-save', 'USD-export-import', 'OBJ-export-import',
      'glTF-export-import', 'PARK', options.scenario === 'success' ? 'PREPARED-APPLY-PAGE_READY-RESUME' :
        'terminal-out-of-order-APPLY-error'],
    result: { profileLength: profileAfter?.length || 0, changedBytesHotInteraction: hotChanged,
      changedBytesAfterCoverageWorkload: changed,
      stateCount: states.length, trustedInputCount: trustedInputs.length, trustedPass,
      pageErrors, externalRequestCount: external.length, gpuErrors, canvas: canvasReceipt,
      initialSemanticPixels: initialPixelReceipt, settledHotPixels: settledPixelReceipt,
      bridgeHot: bridgeHotReceipt, runtimeArgv, threadsOverride: options.threads,
      interactionDoneMs, controller, lastNativeStatus, atomicDiagnostics, threadEntryDiagnostics },
    io: ioReceipt,
    provenance: { driver: fileReceipt(fileURLToPath(import.meta.url)),
        finalizer: currentFinalizer, profileExport: currentProfileExport,
      sharedMemoryViewRefresh: refresh,
      pthreadMemoryRangeSync: rangeSync,
      generatedProbeContract,
      splitBuild: fileReceipt(paths['split-build.json']),
      binaries: Object.fromEntries(Object.entries(paths).map(([key, path]) => [key, fileReceipt(path)])) },
    artifacts,
  };
  writeFileSync(join(outDir, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx' });
  process.stdout.write(JSON.stringify({ status: receipt.status, outDir, result: receipt.result }, null, 2) + '\n');
  if (!pass) process.exitCode = 1;
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
