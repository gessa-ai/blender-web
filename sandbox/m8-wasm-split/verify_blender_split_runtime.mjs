// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Fail-closed production split proof: a fresh browser profile must reach varied
// Blender pixels and a trusted viewport interaction before the secondary is
// requested. EEVEE then demands it on the WM worker; Cycles follows through the
// pooled CPU-worker path. Every shard response is hashed and MIME-checked.

import { createHash } from 'crypto';
import { createRequire } from 'module';
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import {
  validateMinimumWorkerCensus,
  validateSplitArtifactIdentity,
} from './runtime_split_preflight.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const FINALIZER = join(REPO, 'scripts/finalize-wasm-split.py');
const MODULES = '/Users/paws/plushly/game-platform/node_modules';
const require = createRequire(join(process.env.NODE_PATH || MODULES, 'package.json'));
const { chromium } = require('playwright');
const { PNG } = require('pngjs');

const PY_MONITOR = String.raw`
import bpy,hashlib,json,os,sys,time,traceback
_bwsr={"phase":"idle","started":time.perf_counter(),"hot_at":None,"done":[],"armed":False,"complete_at":None}
def _bwsr_emit(kind,value): os.write(2,(kind+" "+json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode())
_bwsr_emit("BW_SPLIT_RUNTIME_ARGV",{"argv":sys.argv})
def _bwsr_state():
    o=bpy.data.objects.get("Cube"); w=bpy.context.window
    if o is None or w is None or w.screen is None: return None
    a=next((x for x in w.screen.areas if x.type=='VIEW_3D'),None)
    r=next((x for x in a.regions if x.type=='WINDOW'),None) if a else None
    if r is None: return None
    return {"mode":o.mode,"verts":len(o.data.vertices),"view":{"x":r.x,"y":r.y,"width":r.width,"height":r.height}}
def _bwsr_complete(scene):
    if _bwsr["phase"] != "eevee": return
    _bwsr["phase"]="eevee_settle"; _bwsr["complete_at"]=time.perf_counter()
def _bwsr_cancel(scene):
    if _bwsr["phase"] != "eevee": return
    _bwsr["done"].append("eevee"); _bwsr["phase"]="idle"
    _bwsr_emit("BW_SPLIT_RUNTIME_COLD",{"phase":"eevee","ok":False,"engine":scene.render.engine,"handler":"render_cancel"})
bpy.app.handlers.render_complete.append(_bwsr_complete)
bpy.app.handlers.render_cancel.append(_bwsr_cancel)
def _bwsr_export_png(image,path,scene):
    if image is None: raise RuntimeError("Render Result missing")
    render_result_size=list(image.size); render_result_channels=int(image.channels)
    image.save_render(filepath=path,scene=scene)
    with open(path,"rb") as handle: raw=handle.read()
    if len(raw)<26 or raw[:8] != b"\x89PNG\r\n\x1a\n": raise RuntimeError("Render Result export is not PNG")
    width=int.from_bytes(raw[16:20],"big"); height=int.from_bytes(raw[20:24],"big")
    bit_depth=int(raw[24]); color_type=int(raw[25])
    if [width,height] != [32,32]: raise RuntimeError("Render Result export has wrong dimensions")
    if bit_depth != 8 or color_type != 6: raise RuntimeError("Render Result export is not RGBA8")
    return {"path":path,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
            "width":width,"height":height,"bit_depth":bit_depth,"color_type":color_type,
            "render_result_size":render_result_size,"render_result_channels":render_result_channels}
def _bwsr_cycles_fileio():
    all_runs=[]
    for index in range(2):
        run={"index":index+1,"ops":{},"files":{},"cycles":{}}
        scene=bpy.context.scene; scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=1
        scene.cycles.use_adaptive_sampling=False; scene.cycles.sampling_pattern='AUTOMATIC'; scene.cycles.seed=0
        try: scene.cycles.use_denoising=False
        except Exception: pass
        # The scene request remains one, but the accepted native APPLY override is authoritative:
        # BKE_render_num_threads/rna_RenderSettings_threads_get must report the active value eight.
        scene.render.threads_mode='FIXED'; scene.render.threads=1
        run["cycles"]["configuration"]={"device":scene.cycles.device,"samples":scene.cycles.samples,
            "adaptive":scene.cycles.use_adaptive_sampling,"sampling_pattern":scene.cycles.sampling_pattern,
            "denoise":scene.cycles.use_denoising,"seed":scene.cycles.seed,
            "threads_mode":scene.render.threads_mode,"requested_threads":1,
            "effective_threads":scene.render.threads}
        started=time.perf_counter(); run["cycles"]["operator"]=sorted(bpy.ops.render.render())
        run["cycles"]["elapsed_ms"]=round((time.perf_counter()-started)*1000,3)
        run["cycles"]["render"]=_bwsr_export_png(bpy.data.images.get('Render Result'),
                                                  "/tmp/bw-split-cycles-%d.png"%(index+1),scene)
        cube=bpy.data.objects.get('Cube')
        bpy.ops.object.select_all(action='DESELECT'); cube.select_set(True); bpy.context.view_layer.objects.active=cube
        prefix="/tmp/bw-split-runtime-%d"%(index+1)
        paths={"blend":prefix+".blend","usd":prefix+".usda","obj":prefix+".obj","gltf":prefix+".glb"}
        run["ops"]["blend_save"]=sorted(bpy.ops.wm.save_as_mainfile(filepath=paths["blend"],copy=True,compress=True))
        run["ops"]["usd_export"]=sorted(bpy.ops.wm.usd_export(filepath=paths["usd"],selected_objects_only=True))
        run["ops"]["obj_export"]=sorted(bpy.ops.wm.obj_export(filepath=paths["obj"],export_selected_objects=True))
        run["ops"]["gltf_export"]=sorted(bpy.ops.export_scene.gltf(filepath=paths["gltf"],export_format='GLB',use_selection=True))
        run["ops"]["usd_import"]=sorted(bpy.ops.wm.usd_import(filepath=paths["usd"]))
        run["ops"]["obj_import"]=sorted(bpy.ops.wm.obj_import(filepath=paths["obj"]))
        run["ops"]["gltf_import"]=sorted(bpy.ops.import_scene.gltf(filepath=paths["gltf"]))
        run["files"]={name:os.path.getsize(path) for name,path in paths.items()}
        run["ok"]=(run["cycles"]["operator"]==['FINISHED'] and
                   run["cycles"]["configuration"]=={"device":"CPU","samples":1,"adaptive":False,
                       "sampling_pattern":"AUTOMATIC","denoise":False,"seed":0,
                       "threads_mode":"FIXED","requested_threads":1,"effective_threads":8} and
                   run["cycles"]["render"]["width"]==32 and
                   run["cycles"]["render"]["height"]==32 and
                   all(value==['FINISHED'] for value in run["ops"].values()) and
                   all(value>0 for value in run["files"].values()))
        all_runs.append(run)
    return {"phase":"cycles_fileio","ok":all(run["ok"] for run in all_runs),"runs":all_runs}
def _bwsr_poll():
    s=_bwsr_state()
    signature=(s["mode"],s["verts"]) if s is not None else None
    if signature is not None and _bwsr.get("last_signature") != signature:
        _bwsr["last_signature"]=signature; _bwsr_emit("BW_SPLIT_RUNTIME_STATE",s)
    if s is not None and s["mode"] == "OBJECT" and s["verts"] > 8 and _bwsr["hot_at"] is None:
        _bwsr["hot_at"]=time.perf_counter()
    if (_bwsr["hot_at"] is not None and time.perf_counter()-_bwsr["hot_at"] >= 0.5 and
        os.path.exists("/tmp/bw-split-ready") and not _bwsr["armed"] and _bwsr["phase"] == "idle"):
        try:
            scene=bpy.context.scene; scene.render.engine='BLENDER_EEVEE'
            scene.render.resolution_x=32; scene.render.resolution_y=32; scene.render.resolution_percentage=100
            scene.render.image_settings.file_format='PNG'; scene.render.image_settings.color_mode='RGBA'
            scene.render.image_settings.color_depth='8'
            _bwsr["phase"]="eevee"; _bwsr["armed"]=True
            _bwsr_emit("BW_SPLIT_RUNTIME_ARMED",{"phase":"eevee","ok":True,"engine":scene.render.engine})
        except Exception:
            _bwsr["done"].append("eevee")
            _bwsr_emit("BW_SPLIT_RUNTIME_COLD",{"phase":"eevee","ok":False,"error":traceback.format_exc()})
    if _bwsr["phase"] == "eevee_settle":
        elapsed=time.perf_counter()-_bwsr["complete_at"]
        if elapsed >= 0.1:
            try:
                render=_bwsr_export_png(bpy.data.images.get('Render Result'),"/tmp/bw-split-eevee.png",bpy.context.scene)
                result={"phase":"eevee","ok":True,"engine":"BLENDER_EEVEE","handler":"render_complete_png",
                        "post_complete_settle_ms":round(elapsed*1000,3),"render":render}
                _bwsr_emit("BW_SPLIT_RUNTIME_COLD",result); _bwsr["done"].append("eevee"); _bwsr["phase"]="cold_ready"
            except Exception:
                result={"phase":"eevee","ok":False,"engine":"BLENDER_EEVEE","handler":"render_export_failed",
                        "post_complete_settle_ms":round(elapsed*1000,3),"error":traceback.format_exc()}
                _bwsr_emit("BW_SPLIT_RUNTIME_COLD",result); _bwsr["done"].append("eevee"); _bwsr["phase"]="idle"
    if _bwsr["phase"] == "cold_ready" and "cycles_fileio" not in _bwsr["done"]:
        _bwsr["phase"]="cycles_fileio"
        try:
            result=_bwsr_cycles_fileio()
        except Exception: result={"phase":"cycles_fileio","ok":False,"error":traceback.format_exc()}
        _bwsr_emit("BW_SPLIT_RUNTIME_COLD",result); _bwsr["done"].append("cycles_fileio"); _bwsr["phase"]="idle"
    return 0.02
bpy.app.timers.register(_bwsr_poll,first_interval=0.0,persistent=True)
`.trim();

function parseArgs(argv) {
  const value = { port: 8165, run: null, outRoot: join(HERE, 'runtime-evidence'), timeoutMs: 240000,
    serverLog: null, threads: 1, expectedWorkers: 8 };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--port') value.port = Number(argv[++i]);
    else if (arg === '--run') value.run = argv[++i];
    else if (arg === '--out-root') value.outRoot = resolve(argv[++i]);
    else if (arg === '--timeout-ms') value.timeoutMs = Number(argv[++i]);
    else if (arg === '--server-log') value.serverLog = resolve(argv[++i]);
    else if (arg === '--threads') value.threads = Number(argv[++i]);
    else if (arg === '--expected-workers') value.expectedWorkers = Number(argv[++i]);
    else throw new Error(`unknown arg ${arg}`);
  }
  if (!value.run || !/^[a-z0-9][a-z0-9._-]*$/i.test(value.run)) throw new Error('safe --run required');
  if (!value.serverLog) throw new Error('--server-log from serve_split.py is required');
  if (value.threads !== null && (!Number.isSafeInteger(value.threads) || value.threads < 1 || value.threads > 64)) {
    throw new Error('safe --threads in [1,64] required');
  }
  if (value.expectedWorkers !== null && (!Number.isSafeInteger(value.expectedWorkers) ||
      value.expectedWorkers < 1 || value.expectedWorkers > 128)) {
    throw new Error('safe --expected-workers in [1,128] required');
  }
  return value;
}

const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
function fileReceipt(path) {
  const stat = statSync(path); return { path: path.startsWith(REPO) ? path.slice(REPO.length + 1) : path,
    bytes: stat.size, sha256: sha(readFileSync(path)) };
}
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
const sortedIds = (ids) => ids.slice().sort((a, b) => a - b);
const sameIds = (left, right) => sortedIds(left).join(',') === sortedIds(right).join(',');
const differenceIds = (all, subset) => {
  const excluded = new Set(subset); return sortedIds(all.filter((id) => !excluded.has(id)));
};

function pixelProof(buffer) {
  const png = PNG.sync.read(buffer);
  let samples = 0; let nonblack = 0; const colors = new Set();
  for (let y = 0; y < png.height; y += 3) for (let x = 0; x < png.width; x += 3) {
    const at = (y * png.width + x) * 4; const r = png.data[at]; const g = png.data[at + 1]; const b = png.data[at + 2];
    samples++; if (r + g + b > 30) nonblack++; colors.add(`${r >> 3},${g >> 3},${b >> 3}`);
  }
  return { width: png.width, height: png.height, nonblackRatio: nonblack / samples,
    quantizedColors: colors.size, pass: png.width >= 1000 && png.height >= 600 &&
      nonblack / samples > 0.1 && colors.size > 128 };
}

function renderPngProof(buffer, expectedWidth = 32, expectedHeight = 32) {
  const png = PNG.sync.read(buffer);
  let nonblackPixels = 0; let rgbMax = 0;
  for (let offset = 0; offset < png.data.length; offset += 4) {
    const pixelMax = Math.max(png.data[offset], png.data[offset + 1], png.data[offset + 2]);
    if (pixelMax !== 0) nonblackPixels++;
    rgbMax = Math.max(rgbMax, pixelMax);
  }
  return { width: png.width, height: png.height, bytes: buffer.length, nonblackPixels,
    nonblackFraction: nonblackPixels / (png.width * png.height), rgbMax,
    pass: png.width === expectedWidth && png.height === expectedHeight &&
      nonblackPixels > 0 && rgbMax > 0 };
}

async function preserveGuestRender(page, producer, hostPath) {
  if (!producer?.path || !Number.isSafeInteger(producer.bytes) || producer.bytes <= 0 ||
      !/^[0-9a-f]{64}$/.test(producer.sha256 || '')) {
    throw new Error(`invalid render producer receipt: ${JSON.stringify(producer)}`);
  }
  const encoded = await page.evaluate((path) => {
    const bytes = window.__bwModule.FS.readFile(path);
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return btoa(binary);
  }, producer.path);
  const bytes = Buffer.from(encoded, 'base64');
  if (bytes.length !== producer.bytes || sha(bytes) !== producer.sha256) {
    throw new Error(`render producer/readback identity mismatch: ${JSON.stringify(producer)}`);
  }
  const proof = renderPngProof(bytes);
  writeFileSync(hostPath, bytes, { flag: 'wx' });
  writeFileSync(`${hostPath}.license`,
    'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n',
    { flag: 'wx' });
  return { contract: 'saved-render-png-authoritative-readback-v1', guestPath: producer.path,
    producer, artifact: fileReceipt(hostPath), ...proof };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const outDir = join(options.outRoot, options.run);
  if (existsSync(outDir)) throw new Error(`refusing overwrite ${outDir}`);
  if (!existsSync(options.serverLog)) throw new Error(`missing active server log ${options.serverLog}`);
  mkdirSync(options.outRoot, { recursive: true }); mkdirSync(outDir);
  const browserProfile = join(outDir, 'chromium-profile'); mkdirSync(browserProfile);
  const bin = resolve(process.env.BLENDER_WEB_BIN || join(REPO, 'build-wasm-windowed-opt/bin'));
  const splitPath = join(bin, 'blender_browser.split-build.json');
  const split = JSON.parse(readFileSync(splitPath, 'utf8'));
  const splitArtifactIdentity = validateSplitArtifactIdentity(split, bin);
  const rangeSync = split.pthread_memory_range_sync;
  const controllerClosure = split.controller_closure;
  const controllerKeep = controllerClosure?.keep_functions;
  const controllerProof = controllerClosure?.transitive_direct_call_proof;
  const controllerExports = controllerClosure?.exports;
  const keepExportNames = Object.keys(controllerKeep?.exports || {});
  const exactControllerKeep =
    controllerClosure?.contract === 'all-pre-shard-controller-exports-primary-v2' &&
    controllerClosure?.verdict === 'PASS' &&
    Array.isArray(controllerExports) && controllerExports.length > 0 &&
    new Set(controllerExports).size === controllerExports.length &&
    Array.isArray(controllerClosure?.missing_primary_exports) &&
    controllerClosure.missing_primary_exports.length === 0 &&
    Array.isArray(controllerClosure?.deferred_controller_symbols) &&
    controllerClosure.deferred_controller_symbols.length === 0 &&
    controllerKeep?.contract === 'exact-controller-export-defined-function-keep-set-v1' &&
    keepExportNames.length === controllerExports.length &&
    controllerExports.every((name) => keepExportNames.includes(name)) &&
    Array.isArray(controllerKeep?.functions) && controllerKeep.functions.length > 0 &&
    new Set(controllerKeep.functions).size === controllerKeep.functions.length &&
    controllerKeep.function_count === controllerKeep.functions.length &&
    controllerProof?.contract === 'binary-index-callgraph-streamed-wat-closure-v1' &&
    controllerProof?.verdict === 'PASS' &&
    Array.isArray(controllerProof?.reachable_placeholder_paths) &&
    controllerProof.reachable_placeholder_paths.length === 0 &&
    Array.isArray(controllerProof?.forbidden_indirect_ref_table_ops) &&
    controllerProof.forbidden_indirect_ref_table_ops.length === 0 &&
    Array.isArray(controllerProof?.unresolved_nodes) && controllerProof.unresolved_nodes.length === 0 &&
    controllerProof.inspected_reachable_defined_count === controllerProof.reachable_function_count;
  if (split.mode !== 'apply' || split.verdict !== 'PASS' ||
      split.single_flight?.contract !== 'page-single-fetch-compile-pthread-module-fanout-v1' ||
      split.single_flight?.late_worker_delivery !== 'fifo-initial-install-before-thread-entry' ||
      split.single_flight?.worker_initial_install_marker !==
        'BW_SPLIT_WORKER_INITIAL_INSTALL_FIFO_V1' ||
      split.single_flight?.initial_install_post_count !== 1 ||
      split.single_flight?.initial_install_dispatch_count !== 1 ||
      split.single_flight?.cmd1_secondary_piggyback_absent !== true ||
      split.js?.stock_sync_loader_absent !== true ||
      split.finalizer?.sha256 !== fileReceipt(FINALIZER).sha256 ||
      !exactControllerKeep ||
      rangeSync?.contract !== 'pthread-cross-realm-memory-range-sync-v1' ||
      rangeSync?.helper_marker_count_after !== 1 ||
      rangeSync?.stack_marker_count_after !== 1 ||
      rangeSync?.mailbox_marker_count_after !== 1 ||
      rangeSync?.grow_zero_count_after !== 1) {
    throw new Error('not a current closure-proved range-synchronized single-flight APPLY artifact');
  }
  const shardPath = resolve(split.secondary.path);
  const primaryPath = resolve(split.primary.path);
  const jsPath = resolve(split.js.path);
  const dataPath = join(bin, 'blender_browser.data');

  const started = Date.now(); const requests = []; const responses = []; const consoleLines = [];
  const pageErrors = []; const states = []; const cold = []; const armed = []; const trusted = [];
  let runtimeArgv = null;
  let firstPixels = null; let interactionDoneMs = null; let fatal = null;
  let preloadStartedMs = null; let preloadCompleteMs = null; let splitBefore = null;
  let splitReady = null; let splitFinal = null;
  let prepareFailure = null;
  let parked = null; let applied = null; let pageReady = null; let resumed = null;
  let postPageReady = null; let queuedInput = null;
  let pageReadyWorkerIdentity = null;
  let lateWorkerReconciliation = null;
  let nativeFinal = null;
  let prePrepareWorkerCensus = null;
  let renderOutputProof = null;
  const transitionTimeline = [];
  const responsePromises = [];
  let context = null; let browserVersion = null;
  let page;
  try {
    context = await chromium.launchPersistentContext(browserProfile, {
      headless: false, viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1,
    });
    browserVersion = context.browser()?.version();
    page = context.pages()[0] || await context.newPage();
    const cdpResponses = new Map();
    const cdp = await context.newCDPSession(page);
    await cdp.send('Network.enable', {
      maxTotalBufferSize: 536870912,
      maxResourceBufferSize: 134217728,
      maxPostDataSize: 65536,
    });
    cdp.on('Network.responseReceived', (event) => {
      if (new URL(event.response.url).pathname.endsWith('.wasm')) cdpResponses.set(event.requestId, event.response);
    });
    cdp.on('Network.loadingFinished', (event) => {
      const response = cdpResponses.get(event.requestId);
      if (!response) return;
      responsePromises.push((async () => {
        const encoded = await cdp.send('Network.getResponseBody', { requestId: event.requestId });
        const body = Buffer.from(encoded.body, encoded.base64Encoded ? 'base64' : 'utf8');
        const contentType = Object.entries(response.headers).find(([key]) => key.toLowerCase() === 'content-type')?.[1] ||
          response.mimeType || '';
        responses.push({ url: response.url, atMs: Date.now() - started,
          status: response.status, contentType, bytes: body.length, sha256: sha(body),
          requestId: event.requestId, encodedDataLength: event.encodedDataLength,
          fromDiskCache: response.fromDiskCache || false,
          fromPrefetchCache: response.fromPrefetchCache || false,
          fromServiceWorker: response.fromServiceWorker || false });
      })().catch((error) => pageErrors.push(`CDP response body: ${error.message}`)));
    });
    page.on('console', (message) => {
      const line = message.text(); consoleLines.push(line);
      if (line.startsWith('BW_SPLIT_RUNTIME_STATE ')) {
        states.push(JSON.parse(line.slice('BW_SPLIT_RUNTIME_STATE '.length)));
      }
      if (line.startsWith('BW_SPLIT_RUNTIME_COLD ')) {
        cold.push({ ...JSON.parse(line.slice('BW_SPLIT_RUNTIME_COLD '.length)), observedAtMs: Date.now() - started });
      }
      if (line.startsWith('BW_SPLIT_RUNTIME_ARMED ')) {
        armed.push({ ...JSON.parse(line.slice('BW_SPLIT_RUNTIME_ARMED '.length)), observedAtMs: Date.now() - started });
      }
      if (line.startsWith('BW_SPLIT_RUNTIME_ARGV ')) {
        runtimeArgv = JSON.parse(line.slice('BW_SPLIT_RUNTIME_ARGV '.length)).argv;
      }
    });
    page.on('pageerror', (error) => pageErrors.push({ message: error.message, stack: error.stack || null,
      atMs: Date.now() - started }));
    page.on('crash', () => pageErrors.push({ message: 'PAGE_CRASH', stack: null, atMs: Date.now() - started }));
    page.on('request', (request) => requests.push({ url: request.url(), atMs: Date.now() - started }));
    await page.addInitScript(({ monitor, threads }) => {
      if (threads !== null) window.__BW_ARGS = ['--threads', String(threads)];
      window.__BW_PYEXPR = monitor; window.__bwSplitRuntimeInputs = [];
      for (const type of ['keydown', 'mousedown', 'mousemove', 'mouseup']) addEventListener(type, (event) => {
        if (event.target?.id === 'canvas') window.__bwSplitRuntimeInputs.push({ type, key: event.key || null,
          button: event.button ?? null, isTrusted: event.isTrusted });
      }, true);
    }, { monitor: PY_MONITOR, threads: options.threads });
    await page.goto(`http://127.0.0.1:${options.port}/windowed.html?gate=1280x720`, {
      waitUntil: 'domcontentloaded', timeout: options.timeoutMs,
    });
    await page.waitForFunction(() => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'),
      null, { timeout: options.timeoutMs });

    const pixelDeadline = Date.now() + options.timeoutMs;
    while (Date.now() < pixelDeadline) {
      const screenshot = await page.locator('#canvas').screenshot(); const proof = pixelProof(screenshot);
      if (proof.pass) { firstPixels = { ...proof, atMs: Date.now() - started, screenshot };
        writeFileSync(join(outDir, 'first-pixels.png'), screenshot); break; }
      await sleep(100);
    }
    if (!firstPixels) throw new Error('semantic first pixels not reached');
    const earlyDeferred = requests.filter((row) => new URL(row.url).pathname.endsWith('.deferred.wasm') &&
      row.atMs <= firstPixels.atMs);
    if (earlyDeferred.length) throw new Error(`secondary requested before pixels: ${JSON.stringify(earlyDeferred)}`);

    const readyDeadline = Date.now() + options.timeoutMs;
    while (!states.some((state) => state.mode === 'OBJECT') && Date.now() < readyDeadline) await sleep(20);
    const ready = states.find((state) => state.mode === 'OBJECT'); if (!ready) throw new Error('no object state');
    const box = await page.locator('#canvas').boundingBox(); if (!box) throw new Error('no canvas box');
    const center = { x: box.x + ready.view.x + ready.view.width / 2,
      y: box.y + box.height - (ready.view.y + ready.view.height / 2) };
    await page.mouse.move(center.x, center.y); await page.locator('#canvas').focus(); await page.keyboard.press('Escape');
    await page.mouse.down({ button: 'middle' }); await page.mouse.move(center.x + 60, center.y + 30, { steps: 6 });
    await page.mouse.up({ button: 'middle' }); await page.keyboard.press('Tab');
    const editDeadline = Date.now() + options.timeoutMs;
    while (!states.some((state) => state.mode === 'EDIT') && Date.now() < editDeadline) await sleep(20);
    await page.keyboard.press('e'); await page.keyboard.press('Enter');
    await page.keyboard.press('Tab');
    const objectDeadline = Date.now() + options.timeoutMs;
    while (!states.some((state) => state.mode === 'OBJECT' && state.verts > 8) && Date.now() < objectDeadline) {
      await sleep(20);
    }
    if (!states.some((state) => state.mode === 'OBJECT' && state.verts > 8)) {
      throw new Error(`trusted extrude did not change topology: ${JSON.stringify(states)}`);
    }
    trusted.push(...await page.evaluate(() => window.__bwSplitRuntimeInputs || []));
    interactionDoneMs = Date.now() - started;
    const beforeInteraction = requests.filter((row) => new URL(row.url).pathname.endsWith('.deferred.wasm') &&
      row.atMs <= interactionDoneMs);
    if (beforeInteraction.length) throw new Error(`secondary requested before interaction: ${JSON.stringify(beforeInteraction)}`);
    if (options.threads !== null) {
      const at = runtimeArgv?.findIndex((value, index) => value === '--threads' &&
        runtimeArgv[index + 1] === String(options.threads));
      if (!(at >= 0)) throw new Error(`runtime argv did not bind --threads ${options.threads}: ${JSON.stringify(runtimeArgv)}`);
    }
    splitBefore = await page.evaluate(() => window.__bwModule.bwSplitSecondaryStatus());
    if (options.expectedWorkers !== null) {
      prePrepareWorkerCensus = validateMinimumWorkerCensus(splitBefore, options.expectedWorkers);
    }

    // The page main owns the sole network fetch/compile, but may not begin it
    // until the trusted semantic interaction and exact native PARK ACK.
    const generation = 1;
    const transition = async (label, operation) => {
      const beginMs = Date.now() - started;
      try {
        const value = await operation();
        transitionTimeline.push({ label, beginMs, endMs: Date.now() - started, ok: true, value });
        return value;
      } catch (error) {
        transitionTimeline.push({ label, beginMs, endMs: Date.now() - started, ok: false,
          error: { message: error?.message || String(error), stack: error?.stack || null } });
        throw error;
      }
    };
    parked = await transition('PARK', () => page.evaluate((generation) =>
      window.__bwModule.bwRequestSplitPark(generation), generation));
    if (parked.parkedGeneration !== generation || parked.phase !== 2 ||
        parked.activeThreads !== 1 || parked.openexrThreads !== 0 || parked.oiioThreads !== 1 ||
        parked.errorGeneration !== 0) {
      throw new Error(`PARK contract failed: ${JSON.stringify(parked)}`);
    }
    preloadStartedMs = Date.now() - started;
    await page.evaluate((generation) => {
      if (typeof window.__bwModule?.bwPrepareSplitSecondary !== 'function') {
        throw new Error('single-flight readiness API is absent');
      }
      window.__bwSplitPrepareOutcome = window.__bwModule.bwPrepareSplitSecondary(generation).then(
        (value) => ({ ok: true, value }),
        (error) => ({ ok: false, error: { message: error?.message || String(error), stack: error?.stack || null },
          splitStatus: window.__bwModule.bwSplitSecondaryStatus(),
          nativeStatus: window.__bwModule.bwSplitNativeStatus() }),
      );
    }, generation);
    const prepareOutcome = await transition('PREPARED', () =>
      page.evaluate(() => window.__bwSplitPrepareOutcome));
    preloadCompleteMs = Date.now() - started;
    if (!prepareOutcome.ok) {
      prepareFailure = prepareOutcome;
      splitFinal = prepareOutcome.splitStatus;
      throw new Error(`single-flight prepare failed: ${JSON.stringify(prepareOutcome)}`);
    }
    splitReady = prepareOutcome.value.split;
    const preparedNative = prepareOutcome.value.native;
    if (!splitReady?.ready || splitReady.workerCount < 8 ||
        splitReady.workerAckCount !== splitReady.workerCount ||
        splitReady.workerInstanceCount !== splitReady.workerCount || splitReady.localInstanceCount !== 1 ||
        splitReady.stats?.fetchCount !== 1 || splitReady.stats?.compileCount !== 1 ||
        splitReady.stats?.pageInstanceCount !== 1 || preparedNative.preparedGeneration !== generation ||
        preparedNative.phase !== 4 || preparedNative.preparedWorkers !== splitReady.workerCount ||
        preparedNative.preparedAcknowledgements !== splitReady.workerAckCount ||
        preparedNative.preparedInstances !== splitReady.workerInstanceCount ||
        preparedNative.preparedLocalInstances !== 1 || preparedNative.preparedPending !== 0 ||
        preparedNative.preparedProtocolErrors !== 0 || preparedNative.preparedStabilizationEpoch <= 0) {
      throw new Error(`single-flight PREPARED failed: ${JSON.stringify({ splitReady, preparedNative })}`);
    }
    if (!sameIds(splitReady.preparedWorkerIds, splitReady.workerIds) ||
        splitReady.lateWorkerIds.length !== 0 || splitReady.pendingWorkerIds.length !== 0 ||
        splitReady.errorWorkerIds.length !== 0 ||
        splitReady.workerLifecycle.some((row) => row.readyGeneration !== generation ||
          row.ackGeneration !== generation || row.instanceCount !== 1 ||
          !['command', 'initial-before-start'].includes(row.installDelivery))) {
      throw new Error(`PREPARED exact worker identity failed: ${JSON.stringify(splitReady)}`);
    }
    applied = await transition('APPLY', () => page.evaluate((generation) =>
      window.__bwModule.bwApplySplitScheduler(generation), generation));
    if (applied.appliedGeneration !== generation || applied.phase !== 6 || applied.activeThreads !== 8 ||
        applied.targetThreads !== 8 || applied.nativeReady !== 1 || applied.openexrThreads !== 8 ||
        applied.oiioThreads !== 8 || applied.reloadRequired !== 0 || applied.errorGeneration !== 0) {
      throw new Error(`APPLY contract failed: ${JSON.stringify(applied)}`);
    }

    // Queue a rapid real input sequence while PARK is still control-only. It
    // must not affect Blender state until the exact RESUME ACK/following tick.
    const queuedAtStateCount = states.length;
    const vertsBeforeQueue = states.at(-1)?.verts;
    const queueBeginMs = Date.now() - started;
    await page.keyboard.press('Tab'); await page.keyboard.press('e');
    await page.keyboard.press('Enter'); await page.keyboard.press('Tab');
    await sleep(100);
    const parkedStateCount = states.length;
    if (parkedStateCount !== queuedAtStateCount) {
      throw new Error(`queued input executed while parked: ${queuedAtStateCount} -> ${parkedStateCount}`);
    }
    pageReady = await transition('PAGE_READY', () => page.evaluate((generation) =>
      window.__bwModule.bwMarkSplitPageReady(generation), generation));
    if (pageReady.native.pageReadyGeneration !== generation || pageReady.native.phase !== 8 ||
        pageReady.native.pageReadyWorkers !== pageReady.split.workerCount ||
        pageReady.native.pageReadyAcknowledgements !== pageReady.split.workerAckCount ||
        pageReady.native.pageReadyInstances !== pageReady.split.workerInstanceCount ||
        pageReady.native.pageReadyLocalInstances !== 1 || pageReady.native.pageReadyPending !== 0 ||
        pageReady.native.pageReadyProtocolErrors !== 0 ||
        pageReady.native.pageReadyLateWorkers !== pageReady.lateWorkers ||
        pageReady.native.pageReadyStabilizationEpoch <= preparedNative.preparedStabilizationEpoch) {
      throw new Error(`PAGE_READY contract failed: ${JSON.stringify(pageReady)}`);
    }
    const expectedLateWorkerIds = differenceIds(pageReady.split.workerIds, splitReady.preparedWorkerIds);
    if (!sameIds(pageReady.split.preparedWorkerIds, splitReady.preparedWorkerIds) ||
        !sameIds(pageReady.split.lateWorkerIds, expectedLateWorkerIds) ||
        !sameIds(pageReady.split.lateInitialAckWorkerIds, expectedLateWorkerIds) ||
        pageReady.split.errorWorkerIds.length !== 0 ||
        pageReady.split.workerLifecycle.some((row) => expectedLateWorkerIds.includes(row.workerId) &&
          (row.installDelivery !== 'initial-before-start' ||
           row.initialAckGeneration !== generation || row.readyGeneration !== generation ||
           row.ackGeneration !== generation || row.instanceCount !== 1))) {
      throw new Error(`PAGE_READY exact initial-delivery attestation failed: ${JSON.stringify(pageReady)}`);
    }
    postPageReady = await page.evaluate(() => ({
      split: window.__bwModule.bwSplitSecondaryStatus(),
      native: window.__bwModule.bwSplitNativeStatus(),
    }));
    pageReadyWorkerIdentity = {
      preparedEpoch: preparedNative.preparedStabilizationEpoch,
      pageReadyEpoch: pageReady.native.pageReadyStabilizationEpoch,
      preparedWorkerIds: sortedIds(splitReady.preparedWorkerIds),
      lateWorkerIds: expectedLateWorkerIds,
      lateInitialAckWorkerIds: sortedIds(pageReady.split.lateInitialAckWorkerIds),
      beforeAckWorkerIds: pageReady.split.workerIds.slice(),
      afterAckWorkerIds: postPageReady.split.workerIds.slice(),
    };
    if (!postPageReady.split.ready || postPageReady.split.protocolError !== null ||
        postPageReady.split.pendingWorkerIds.length !== 0 ||
        !sameIds(postPageReady.split.workerIds, pageReady.split.workerIds) ||
        !sameIds(postPageReady.split.preparedWorkerIds, splitReady.preparedWorkerIds) ||
        !sameIds(postPageReady.split.lateWorkerIds, expectedLateWorkerIds) ||
        !sameIds(postPageReady.split.lateInitialAckWorkerIds, expectedLateWorkerIds) ||
        postPageReady.native.pageReadyGeneration !== generation) {
      throw new Error(`post-PAGE_READY worker drift: ${JSON.stringify({ pageReady, postPageReady })}`);
    }
    resumed = await transition('RESUME', () => page.evaluate((generation) =>
      window.__bwModule.bwResumeSplitScheduler(generation), generation));
    if (resumed.native.resumedGeneration !== generation || resumed.native.phase !== 10 ||
        resumed.native.errorGeneration !== 0) throw new Error(`RESUME contract failed: ${JSON.stringify(resumed)}`);
    const replayDeadline = Date.now() + options.timeoutMs;
    while (!states.slice(queuedAtStateCount).some((state) => state.mode === 'OBJECT' &&
      state.verts > vertsBeforeQueue) && Date.now() < replayDeadline) await sleep(20);
    const replayed = states.slice(queuedAtStateCount).some((state) => state.mode === 'OBJECT' &&
      state.verts > vertsBeforeQueue);
    queuedInput = { queueBeginMs, queuedAtStateCount, parkedStateCount,
      resumeAckMs: transitionTimeline.find((row) => row.label === 'RESUME')?.endMs || null,
      replayObservedMs: replayed ? Date.now() - started : null, vertsBeforeQueue,
      vertsAfterReplay: states.at(-1)?.verts, replayed };
    if (!replayed) throw new Error(`queued input did not replay after RESUME: ${JSON.stringify(queuedInput)}`);

    await page.evaluate(() => {
      window.__bwModule.FS.writeFile('/tmp/bw-split-ready', new Uint8Array([1]));
    });

    // The trusted topology change arms EEVEE on Blender's WM worker after a
    // 500-ms gap. Use the real asynchronous frame-job entry point exactly once.
    const armedDeadline = Date.now() + options.timeoutMs;
    while (!armed.some((row) => row.phase === 'eevee') && Date.now() < armedDeadline) await sleep(20);
    if (!armed.find((row) => row.phase === 'eevee')?.ok) throw new Error(`EEVEE did not arm ${JSON.stringify(armed)}`);
    await page.keyboard.press('F12');
    const eeveeDeadline = Date.now() + options.timeoutMs;
    while (!cold.some((row) => row.phase === 'eevee') && Date.now() < eeveeDeadline) await sleep(50);
    const eevee = cold.find((row) => row.phase === 'eevee'); if (!eevee?.ok) throw new Error(`EEVEE cold failed ${JSON.stringify(eevee)}`);
    const eeveeRender = await preserveGuestRender(page, eevee.render, join(outDir, 'eevee-render.png'));
    eevee.renderEvidence = eeveeRender;
    if (!eeveeRender.pass) throw new Error(`EEVEE PNG is invalid or black: ${JSON.stringify(eeveeRender)}`);
    // The timer begins two Cycles renders plus two complete file-IO passes only
    // after the WM-worker EEVEE result has published nonzero pixels.
    const cyclesDeadline = Date.now() + options.timeoutMs;
    while (!cold.some((row) => row.phase === 'cycles_fileio') && Date.now() < cyclesDeadline) await sleep(50);
    const cycles = cold.find((row) => row.phase === 'cycles_fileio');
    if (!cycles?.ok || cycles.runs?.length !== 2 || !cycles.runs.every((row) => row.ok)) {
      throw new Error(`Cycles/file IO cold failed ${JSON.stringify(cycles)}`);
    }
    const cyclesRenderEvidence = [];
    for (const run of cycles.runs) {
      const evidence = await preserveGuestRender(page, run.cycles.render,
        join(outDir, `cycles-${run.index}-render.png`));
      run.cycles.renderEvidence = evidence; cyclesRenderEvidence.push(evidence);
      if (!evidence.pass) throw new Error(`Cycles ${run.index} PNG is invalid or black: ${JSON.stringify(evidence)}`);
    }
    renderOutputProof = { contract: 'saved-render-png-authoritative-readback-v1', eevee: eeveeRender,
      cycles: cyclesRenderEvidence, pass: eeveeRender.pass && cyclesRenderEvidence.length === 2 &&
        cyclesRenderEvidence.every((row) => row.pass) };
    splitFinal = await page.evaluate(() => window.__bwModule.bwSplitSecondaryStatus());
    nativeFinal = await page.evaluate(() => window.__bwModule.bwSplitNativeStatus());
    const newWorkerIds = splitFinal.workerIds.filter((id) => !splitReady.workerIds.includes(id));
    const newWorkerLifecycle = splitFinal.workerLifecycle.filter((row) => newWorkerIds.includes(row.workerId));
    const lateWorkerAckBaseline = splitReady.stats?.lateWorkerAckCount;
    const lateWorkerAckDelta = splitFinal.stats?.lateWorkerAckCount - lateWorkerAckBaseline;
    lateWorkerReconciliation = { preparedAckBaseline: lateWorkerAckBaseline,
      finalAckCount: splitFinal.stats?.lateWorkerAckCount, ackDelta: lateWorkerAckDelta,
      newWorkerIds: sortedIds(newWorkerIds) };
    if (!splitFinal.ready || splitFinal.workerAckCount !== splitFinal.workerCount ||
        splitFinal.workerInstanceCount !== splitFinal.workerCount || splitFinal.localInstanceCount !== 1 ||
        splitFinal.protocolError !== null || splitFinal.stats?.duplicateAckCount !== 0 ||
        splitFinal.stats?.rejectedAckCount !== 0 ||
        splitFinal.stats?.ackTimeoutCount !== 0 ||
        !Number.isSafeInteger(lateWorkerAckBaseline) || lateWorkerAckBaseline < 0 ||
        lateWorkerAckDelta !== newWorkerIds.length ||
        !sameIds(splitFinal.lateWorkerIds, newWorkerIds) ||
        !sameIds(splitFinal.lateInitialAckWorkerIds, newWorkerIds) ||
        newWorkerLifecycle.length !== newWorkerIds.length ||
        newWorkerLifecycle.some((row) => row.installDelivery !== 'initial-before-start' ||
          row.initialAckGeneration !== generation || row.readyGeneration !== generation ||
          row.ackGeneration !== generation || row.instanceCount !== 1) || nativeFinal.phase !== 10 ||
        nativeFinal.resumedGeneration !== 1 || nativeFinal.errorGeneration !== 0 ||
        nativeFinal.activeThreads !== 8 || nativeFinal.openexrThreads !== 8 ||
        nativeFinal.oiioThreads !== 8 || nativeFinal.reloadRequired !== 0) {
      throw new Error(`final single-flight status failed: ${JSON.stringify({ splitReady, splitFinal, nativeFinal, newWorkerIds })}`);
    }
    trusted.splice(0, trusted.length, ...await page.evaluate(() => window.__bwSplitRuntimeInputs || []));
    await sleep(1000); await Promise.all(responsePromises);
  } catch (error) { fatal = error?.stack || String(error); }
  finally {
    try { if (context) await context.close(); }
    finally { if (existsSync(browserProfile)) rmSync(browserProfile, { recursive: true }); }
  }

  await Promise.all(responsePromises);
  const expectedShardPath = '/blender_browser.deferred.wasm';
  const expectedShardQuery = `sha256=${split.secondary.sha256}`;
  const isShardUrl = (url) => {
    const parsed = new URL(url); return parsed.pathname.endsWith(expectedShardPath) &&
      parsed.searchParams.toString() === expectedShardQuery;
  };
  const shardRequests = requests.filter((row) => isShardUrl(row.url));
  const shardResponses = responses.filter((row) => isShardUrl(row.url));
  const serverRows = readFileSync(options.serverLog, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse);
  const shardServerRows = serverRows.filter((row) => row.path === '/bin/blender_browser.deferred.wasm');
  const trustedPass = trusted.length > 8 && trusted.every((row) => row.isTrusted) &&
    trusted.some((row) => row.key === 'Tab') && trusted.some((row) => row.key === 'e') &&
    trusted.filter((row) => row.key === 'F12').length === 1 && trusted.some((row) => row.button === 1);
  const external = requests.filter((row) => !['127.0.0.1', 'localhost'].includes(new URL(row.url).hostname));
  const shardPass = shardRequests.length === 1 && shardResponses.length === 1 && shardResponses.every((row) => row.status === 200 &&
    row.contentType.startsWith('application/wasm') && row.bytes === split.secondary.bytes &&
    row.sha256 === split.secondary.sha256) && shardServerRows.length === 1 &&
    shardServerRows[0].status === 200 && shardServerRows[0].complete === true &&
    shardServerRows[0].bytes_sent === split.secondary.bytes &&
    shardServerRows[0].sha256 === split.secondary.sha256 &&
    shardServerRows[0].request_target ===
      `/bin/blender_browser.deferred.wasm?sha256=${split.secondary.sha256}`;
  const gpuErrors = consoleLines.filter((line) => /\[bw\]\[GPU-(?:ERROR|LOST)\]/.test(line));
  const firstShardResponse = shardResponses.slice().sort((a, b) => a.atMs - b.atMs)[0];
  const eeveeComplete = cold.find((row) => row.phase === 'eevee');
  const cyclesComplete = cold.find((row) => row.phase === 'cycles_fileio');
  const pass = !fatal && firstPixels?.pass && interactionDoneMs > firstPixels.atMs && trustedPass &&
    cold.length === 2 && cold.every((row) => row.ok) && renderOutputProof?.pass === true &&
    shardPass && splitReady?.ready === true &&
    splitFinal?.ready === true && splitFinal.workerAckCount === splitFinal.workerCount &&
    splitFinal.workerInstanceCount === splitFinal.workerCount && splitFinal.protocolError === null &&
    splitFinal.stats?.duplicateAckCount === 0 && splitFinal.stats?.rejectedAckCount === 0 &&
    splitFinal.stats?.ackTimeoutCount === 0 &&
    splitReady.workerCount >= 8 && splitReady.workerAckCount === splitReady.workerCount &&
    splitReady.workerInstanceCount === splitReady.workerCount &&
    splitReady.stats?.fetchCount === 1 && splitReady.stats?.compileCount === 1 &&
    parked?.parkedGeneration === 1 && applied?.appliedGeneration === 1 &&
    pageReady?.native?.pageReadyGeneration === 1 && resumed?.native?.resumedGeneration === 1 &&
    queuedInput?.replayed === true && nativeFinal?.phase === 10 && nativeFinal?.errorGeneration === 0 &&
    pageErrors.length === 0 &&
    external.length === 0 && gpuErrors.length === 0 && shardRequests.every((row) => row.atMs > interactionDoneMs);

  for (const [name, value] of [['console.log', consoleLines.join('\n') + '\n'],
    ['requests.json', JSON.stringify(requests, null, 2) + '\n'], ['responses.json', JSON.stringify(responses, null, 2) + '\n'],
    ['states.json', JSON.stringify(states, null, 2) + '\n'], ['armed.json', JSON.stringify(armed, null, 2) + '\n'],
    ['cold.json', JSON.stringify(cold, null, 2) + '\n'],
    ['server.json', JSON.stringify(serverRows, null, 2) + '\n'],
    ['trusted-inputs.json', JSON.stringify(trusted, null, 2) + '\n']]) writeFileSync(join(outDir, name), value);
  if (firstPixels) writeFileSync(join(outDir, 'first-pixels.png.license'),
    'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n');
  const receipt = { schema: 'blender-web.wasm-split-runtime.v1', status: pass ? 'PASS' : 'FAIL', fatal,
    browser: { version: browserVersion, headed: true, freshPersistentProfile: true },
    timing: { firstPixelsMs: firstPixels?.atMs || null, interactionDoneMs,
      preloadStartedMs, preloadCompleteMs,
      firstShardRequestMs: shardRequests[0]?.atMs || null,
      interactionToFirstShardRequestMs: shardRequests[0] && interactionDoneMs !== null ?
        shardRequests[0].atMs - interactionDoneMs : null,
      firstShardResponseMs: firstShardResponse?.atMs || null,
      firstRequestToFirstResponseMs: firstShardResponse && shardRequests[0] ?
        firstShardResponse.atMs - shardRequests[0].atMs : null,
      eeveeCompleteMs: eeveeComplete?.observedAtMs || null,
      cyclesCompleteMs: cyclesComplete?.observedAtMs || null,
      interactionToEeveeCompleteMs: eeveeComplete && interactionDoneMs !== null ?
        eeveeComplete.observedAtMs - interactionDoneMs : null },
    result: { pixelProof: firstPixels && Object.fromEntries(Object.entries(firstPixels).filter(([key]) => key !== 'screenshot')),
      trustedPass, trustedInputCount: trusted.length, runtimeArgv, threadsOverride: options.threads,
      expectedWorkers: options.expectedWorkers, prepareFailure, cold, splitBefore, splitReady, splitFinal,
      parked, applied, pageReady, postPageReady, pageReadyWorkerIdentity, resumed, nativeFinal,
      queuedInput, transitionTimeline, lateWorkerReconciliation, prePrepareWorkerCensus,
      renderOutputProof,
      shardRequestCount: shardRequests.length,
      shardResponseCount: shardResponses.length, shardPass, shardResponses, pageErrors,
      shardServerRows, externalRequestCount: external.length, gpuErrors },
    provenance: { driver: fileReceipt(fileURLToPath(import.meta.url)), splitBuild: fileReceipt(splitPath),
      finalizer: fileReceipt(FINALIZER), pthreadMemoryRangeSync: rangeSync,
      controllerClosure, splitArtifactIdentity,
      server: fileReceipt(join(HERE, 'serve_split.py')), serverLog: fileReceipt(join(outDir, 'server.json')),
      primary: fileReceipt(primaryPath), secondary: fileReceipt(shardPath), js: fileReceipt(jsPath), data: fileReceipt(dataPath) },
  };
  writeFileSync(join(outDir, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx' });
  process.stdout.write(JSON.stringify({ status: receipt.status, outDir, timing: receipt.timing, result: receipt.result }, null, 2) + '\n');
  if (!pass) process.exitCode = 1;
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
