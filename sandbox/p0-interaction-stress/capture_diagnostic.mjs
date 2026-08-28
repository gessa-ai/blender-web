// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Fallback diagnostic by default; --hardware binds an exact Apple/product evidence run.

import { createHash } from "node:crypto";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { delimiter, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const defaultOutRoot = resolve(root, "sandbox/p0-interaction-stress/hardware-evidence");
const defaultBinDir = resolve(root, "build-wasm-windowed-opt/bin");
const NODE_VERSION = "v22.16.0";
const PLAYWRIGHT_VERSION = "1.61.1";
const PNGJS_VERSION = "7.0.0";
const CHROMIUM_VERSION = "149.0.7827.55";
const ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1";
const HARDWARE_EVIDENCE_CLASS = "apple-hardware-interaction-v1";
const FALLBACK_EVIDENCE_CLASS = "diagnostic-software-fallback";
const SOFTWARE_ADAPTER_TOKENS = Object.freeze([
  "swiftshader",
  "llvmpipe",
  "lavapipe",
  "softpipe",
  "software rasterizer",
  "microsoft basic render",
  "warp",
]);
const REQUIRED_PRODUCT_FILES = Object.freeze([
  "blender_browser.js",
  "blender_browser.wasm",
  "blender_browser.wasm.orig",
  "blender_browser.data",
  "blender_browser.split-build.json",
]);
const SAME_POSE_CHANGED_FRACTION_LIMIT = 0.01;
const TEXT_REGION_CHANGED_FRACTION_LIMIT = 0.002;
const PIXEL_RECOVERY_TIMEOUT_MS = 12000;
const PIXEL_STABLE_WINDOW_MS = 3000;
const PIXEL_STABLE_SAMPLE_MS = 250;
const ISOLATED_VIEW_KEYS = Object.freeze(["Numpad1", "Numpad3", "Numpad7", "Numpad0", "Numpad4"]);

function isDescendant(parent, candidate) {
  const rel = relative(resolve(parent), resolve(candidate));
  return rel !== "" && rel !== ".." && !rel.startsWith(`..${process.platform === "win32" ? "\\" : "/"}`);
}

function requireDirectDescendantPath(parent, candidate, label) {
  if (!isDescendant(parent, candidate)) {
    throw new Error(`${label} escapes the checkout: ${candidate}`);
  }
  const parts = relative(resolve(parent), resolve(candidate)).split(/[\\/]+/);
  let cursor = resolve(parent);
  for (const part of parts) {
    cursor = join(cursor, part);
    if (existsSync(cursor) && lstatSync(cursor).isSymbolicLink()) {
      throw new Error(`${label} traverses a symlink: ${cursor}`);
    }
  }
}

function parseOptions(argv = process.argv.slice(2)) {
  if (argv.length <= 1 && (argv.length === 0 || /^\d+$/.test(argv[0]))) {
    return {
      hardware: false,
      port: Number(argv[0] || 8123),
      outDir: resolve(process.env.BW_P0I_STRESS_OUT ||
        resolve(root, "sandbox/p0-interaction-stress/artifacts")),
      binDir: defaultBinDir,
      expectedWasmOrigSha256: null,
      run: null,
    };
  }
  const options = {
    hardware: false,
    port: 8123,
    outRoot: defaultOutRoot,
    binDir: defaultBinDir,
    expectedWasmOrigSha256: null,
    run: null,
  };
  for (let index = 0; index < argv.length; index++) {
    const flag = argv[index];
    if (flag === "--hardware") {
      options.hardware = true;
      continue;
    }
    const value = argv[++index];
    if (value === undefined) throw new Error(`missing value for ${flag}`);
    if (flag === "--port") options.port = Number(value);
    else if (flag === "--run") options.run = value;
    else if (flag === "--out-root") options.outRoot = resolve(value);
    else if (flag === "--bin-dir") options.binDir = resolve(value);
    else if (flag === "--expected-wasm-orig-sha256") {
      options.expectedWasmOrigSha256 = value.toLowerCase();
    }
    else throw new Error(`unknown argument: ${flag}`);
  }
  if (!options.hardware) {
    throw new Error("flag form requires --hardware; fallback usage is capture_diagnostic.mjs [port]");
  }
  if (process.platform !== "darwin") {
    throw new Error(`--hardware binds the Apple acceptance lane; got ${process.platform}`);
  }
  if (process.version !== NODE_VERSION) {
    throw new Error(`Node ${NODE_VERSION} required, got ${process.version}`);
  }
  if (!Number.isInteger(options.port) || options.port < 1 || options.port > 65535) {
    throw new Error(`invalid --port: ${options.port}`);
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(options.run || "")) {
    throw new Error("--run must be a safe 1-80 character evidence label");
  }
  if (!/^[0-9a-f]{64}$/.test(options.expectedWasmOrigSha256 || "")) {
    throw new Error("--expected-wasm-orig-sha256 must be an exact lowercase SHA-256");
  }
  requireDirectDescendantPath(root, options.outRoot, "--out-root");
  requireDirectDescendantPath(root, options.binDir, "--bin-dir");
  options.outDir = join(options.outRoot, options.run);
  return options;
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function parseGenerationManifest(source) {
  const manifest = typeof source === "string" ? JSON.parse(source) : source;
  const generation = {
    mode: manifest?.mode,
    originalWasmSha256: manifest?.original?.sha256,
    instrumentedWasmSha256: manifest?.instrumented?.sha256,
    javascriptSha256: manifest?.js?.sha256,
  };
  if (generation.mode !== "capture") {
    throw new Error(`split manifest mode is not capture: ${generation.mode}`);
  }
  for (const [name, value] of Object.entries(generation).slice(1)) {
    if (!/^[0-9a-f]{64}$/.test(value || "")) {
      throw new Error(`split manifest ${name} is not an exact SHA-256`);
    }
  }
  return generation;
}

function readProductIdentity(binDir, expectedWasmOrigSha256) {
  const files = {};
  for (const name of REQUIRED_PRODUCT_FILES) {
    const path = join(binDir, name);
    if (!existsSync(path)) throw new Error(`canonical product file is absent: ${path}`);
    const info = lstatSync(path);
    if (!info.isFile() || info.isSymbolicLink()) {
      throw new Error(`canonical product file is not a direct regular file: ${path}`);
    }
    files[name] = {bytes: statSync(path).size, sha256: sha256File(path)};
  }
  if (files["blender_browser.wasm.orig"].sha256 !== expectedWasmOrigSha256) {
    throw new Error(
      `wasm.orig generation mismatch: expected ${expectedWasmOrigSha256}, ` +
      `got ${files["blender_browser.wasm.orig"].sha256}`,
    );
  }
  const generation = parseGenerationManifest(
    readFileSync(join(binDir, "blender_browser.split-build.json"), "utf8"),
  );
  if (generation.originalWasmSha256 !== expectedWasmOrigSha256) {
    throw new Error(
      `split manifest generation mismatch: expected ${expectedWasmOrigSha256}, ` +
      `got ${generation.originalWasmSha256}`,
    );
  }
  return {binDir: relative(root, binDir).replaceAll("\\", "/"), files, generation};
}

function classifyAdapterProbe(raw, platform = process.platform) {
  const info = Object.fromEntries(["vendor", "architecture", "device", "description"]
    .map((key) => [key, typeof raw?.info?.[key] === "string" ? raw.info[key] : ""]));
  const identity = Object.values(info).join(" ").trim().toLowerCase();
  const details = [info.architecture, info.device, info.description].join(" ").trim();
  const softwareMatches = SOFTWARE_ADAPTER_TOKENS.filter((token) => identity.includes(token));
  if (/(^|[^a-z0-9])cpu([^a-z0-9]|$)/.test(identity)) softwareMatches.push("cpu");
  const present = raw?.present === true;
  const isFallbackAdapter = typeof raw?.isFallbackAdapter === "boolean" ?
    raw.isFallbackAdapter : null;
  let reason = "accepted-hardware";
  if (!present) reason = "adapter-absent";
  else if (isFallbackAdapter === true) reason = "fallback-adapter";
  else if (isFallbackAdapter !== false) reason = "fallback-status-absent";
  else if (!identity || !details) reason = "adapter-info-absent";
  else if (softwareMatches.length) reason = "software-adapter";
  return {
    contract: ADAPTER_CONTRACT,
    status: reason === "accepted-hardware" ? "ACCEPTED" : "REJECTED",
    reason,
    present,
    platform,
    powerPreference: "high-performance",
    isFallbackAdapter,
    info,
    softwareMatches,
  };
}

async function probeAdapter(page) {
  const raw = await page.evaluate(async () => {
    const adapter = await navigator.gpu?.requestAdapter({powerPreference: "high-performance"});
    if (!adapter) return {present: false, isFallbackAdapter: null, info: null};
    const info = adapter.info || {};
    return {
      present: true,
      isFallbackAdapter: typeof info.isFallbackAdapter === "boolean" ?
        info.isFallbackAdapter :
        (typeof adapter.isFallbackAdapter === "boolean" ? adapter.isFallbackAdapter : null),
      info: Object.fromEntries(["vendor", "architecture", "device", "description"]
        .map((key) => [key, typeof info[key] === "string" ? info[key] : ""])),
    };
  });
  return classifyAdapterProbe(raw);
}

async function fetchServedGeneration(origin, expectedWasmOrigSha256) {
  const response = await fetch(`${origin}/blender_browser.split-build.json`, {cache: "no-store"});
  if (!response.ok) throw new Error(`served split manifest returned HTTP ${response.status}`);
  const generation = parseGenerationManifest(await response.text());
  if (generation.originalWasmSha256 !== expectedWasmOrigSha256) {
    throw new Error(
      `served generation mismatch: expected ${expectedWasmOrigSha256}, ` +
      `got ${generation.originalWasmSha256}`,
    );
  }
  return generation;
}

const options = parseOptions();
const outDir = options.outDir;
let evidenceAllocated = false;

const moduleRoots = [
  process.env.BW_NODE_MODULES,
  process.env.NODE_PATH,
  resolve(root, ".m4-node/node_modules"),
].filter(Boolean).flatMap((entry) => entry.split(delimiter)).filter(Boolean);
let chromium = null;
let PNG = null;
let playwrightVersion = null;
let pngjsVersion = null;
for (const candidate of moduleRoots) {
  try {
    const require = createRequire(resolve(candidate, "package.json"));
    chromium = require("playwright").chromium;
    PNG = require("pngjs").PNG;
    playwrightVersion = require("playwright/package.json").version;
    pngjsVersion = require("pngjs/package.json").version;
    break;
  }
  catch (_) {}
}
if (!chromium) {
  throw new Error(`playwright is unavailable; checked ${moduleRoots.join(", ")}`);
}
if (options.hardware &&
    (playwrightVersion !== PLAYWRIGHT_VERSION || pngjsVersion !== PNGJS_VERSION)) {
  throw new Error(
    `exact browser dependencies required: playwright=${playwrightVersion} pngjs=${pngjsVersion}`,
  );
}

const port = options.port;
const consoleLines = [];
const pageErrors = [];
const lifecycleEvents = [];
const states = [];
const steps = [];
const inputEvents = [];

const PY_MONITOR = String.raw`
import bpy,json,os,time
from bpy_extras import view3d_utils
_bwp0s={"last":None,"started":time.perf_counter(),"sequence":0}
_bwp0s_input_sequence=0
class WM_OT_bwp0s_input_probe(bpy.types.Operator):
    bl_idname="wm.bwp0s_input_probe"
    bl_label="P0 input probe"
    bl_options={'INTERNAL'}
    def invoke(self,context,event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def modal(self,context,event):
        global _bwp0s_input_sequence
        if event.type in {'MOUSEMOVE','LEFTMOUSE','MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE','A'}:
            _bwp0s_input_sequence+=1
            payload={
              "sequence":_bwp0s_input_sequence,
              "elapsed_ms":round((time.perf_counter()-_bwp0s["started"])*1000,3),
              "type":event.type,
              "value":event.value,
              "x":event.mouse_x,"y":event.mouse_y,
              "prev_x":event.mouse_prev_x,"prev_y":event.mouse_prev_y,
              "region_x":event.mouse_region_x,"region_y":event.mouse_region_y,
              "shift":event.shift,"ctrl":event.ctrl,"alt":event.alt,"oskey":event.oskey,
              "area":context.area.type if context.area else None,
              "region":context.region.type if context.region else None,
            }
            os.write(2,("P0S_INPUT "+json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n").encode())
        return {'PASS_THROUGH'}
def _bwp0s_start_input_probe():
    if bpy.context.window is None: return 0.05
    bpy.ops.wm.bwp0s_input_probe('INVOKE_DEFAULT')
    return None
bpy.utils.register_class(WM_OT_bwp0s_input_probe)
def _bwp0s_round(values):
    return [round(float(value),5) for value in values]
def _bwp0s_poll():
    window=bpy.context.window
    if window is None or window.screen is None: return 0.05
    obj=bpy.data.objects.get("Cube")
    area=next((item for item in window.screen.areas if item.type == 'VIEW_3D'),None)
    region=next((item for item in area.regions if item.type == 'WINDOW'),None) if area else None
    space=area.spaces.active if area else None
    rv3d=space.region_3d if space else None
    cube_screen=None
    cube_in_view=False
    if obj and region and rv3d:
        projected=view3d_utils.location_3d_to_region_2d(region,rv3d,obj.matrix_world.translation)
        if projected is not None:
            cube_screen=[round(float(projected.x),3),round(float(projected.y),3)]
            cube_in_view=(0 <= projected.x < region.width and 0 <= projected.y < region.height)
    state={
      "sequence":_bwp0s["sequence"],
      "elapsed_ms":round((time.perf_counter()-_bwp0s["started"])*1000,3),
      "workspace":window.workspace.name if window.workspace else None,
      "modal_operators":[operator.bl_idname for operator in window.modal_operators],
      "screen":window.screen.name,
      "areas":[item.type for item in window.screen.areas],
      "mode":obj.mode if obj else None,
      "verts":len(obj.data.vertices) if obj and obj.type == 'MESH' else None,
      "selected":bool(obj.select_get()) if obj else False,
      "selected_count":len(bpy.context.selected_objects),
      "active_object":bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
      "location":_bwp0s_round(obj.location) if obj else None,
      "rotation":_bwp0s_round(obj.rotation_euler) if obj else None,
      "scale":_bwp0s_round(obj.scale) if obj else None,
      "view":({"x":region.x,"y":region.y,"width":region.width,"height":region.height}
              if region else None),
      "cube_screen":cube_screen,
      "cube_in_view":cube_in_view,
      "view_distance":round(float(rv3d.view_distance),5) if rv3d else None,
      "view_location":_bwp0s_round(rv3d.view_location) if rv3d else None,
      "view_rotation":_bwp0s_round(rv3d.view_rotation) if rv3d else None,
      "view_perspective":rv3d.view_perspective if rv3d else None,
    }
    key=json.dumps({key:value for key,value in state.items() if key not in {"sequence","elapsed_ms"}},
                   sort_keys=True,separators=(",",":"))
    if key != _bwp0s["last"]:
        _bwp0s["last"]=key
        _bwp0s["sequence"]+=1
        state["sequence"]=_bwp0s["sequence"]
        os.write(2,("P0S_STATE "+json.dumps(state,sort_keys=True,separators=(",",":"))+"\n").encode())
    return 0.05
bpy.app.timers.register(_bwp0s_poll,first_interval=0.0,persistent=True)
bpy.app.timers.register(_bwp0s_start_input_probe,first_interval=0.0,persistent=True)
`.trim();

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function semanticPixels(bytes) {
  const png = PNG.sync.read(bytes);
  const colors = new Set();
  let nonWhite = 0;
  for (let offset = 0; offset < png.data.length; offset += 4) {
    const red = png.data[offset];
    const green = png.data[offset + 1];
    const blue = png.data[offset + 2];
    colors.add(`${red >> 4},${green >> 4},${blue >> 4}`);
    if (red < 245 || green < 245 || blue < 245) nonWhite++;
  }
  return {
    quantizedColors: colors.size,
    nonWhiteRatio: nonWhite / (png.width * png.height),
  };
}

function samePosePixelDiff(referenceBytes, candidateBytes, view) {
  const reference = PNG.sync.read(referenceBytes);
  const candidate = PNG.sync.read(candidateBytes);
  if (reference.width !== candidate.width || reference.height !== candidate.height) {
    throw new Error(
      `same-pose dimensions differ: ${reference.width}x${reference.height} vs ` +
      `${candidate.width}x${candidate.height}`,
    );
  }
  const roi = {
    x0: Math.max(0, Math.floor(view.x)),
    x1: Math.min(reference.width, Math.ceil(view.x + view.width)),
    y0: Math.max(0, Math.floor(reference.height - (view.y + view.height))),
    y1: Math.min(reference.height, Math.ceil(reference.height - view.y)),
  };
  const detailRegions = {
    viewHeader: {
      x0: Math.floor(reference.width * 0.005),
      x1: Math.ceil(reference.width * 0.25),
      y0: Math.floor(reference.height * 0.065),
      y1: Math.ceil(reference.height * 0.21),
    },
    leftToolbar: {
      x0: Math.floor(reference.width * 0.005),
      x1: Math.ceil(reference.width * 0.085),
      y0: Math.floor(reference.height * 0.065),
      y1: Math.ceil(reference.height * 0.66),
    },
    outlinerText: {
      x0: Math.floor(reference.width * 0.825),
      x1: Math.ceil(reference.width * 0.997),
      y0: Math.floor(reference.height * 0.07),
      /* End immediately before the selected Cube row. Canvas focus legitimately changes that
       * row's blue highlight; the stable Collection/Camera text rows above it are the canary. */
      y1: Math.floor(reference.height * 0.135),
    },
    workspaceTabs: {
      x0: Math.floor(reference.width * 0.19),
      x1: Math.ceil(reference.width * 0.75),
      y0: 0,
      y1: Math.ceil(reference.height * 0.037),
    },
  };
  const detailCounts = Object.fromEntries(Object.keys(detailRegions).map((name) => [name, {
    changed: 0,
    samples: 0,
  }]));
  let fullChanged = 0;
  let viewChanged = 0;
  let viewSamples = 0;
  for (let y = 0; y < reference.height; y++) {
    for (let x = 0; x < reference.width; x++) {
      const offset = (y * reference.width + x) * 4;
      const changed = Math.max(
        Math.abs(reference.data[offset] - candidate.data[offset]),
        Math.abs(reference.data[offset + 1] - candidate.data[offset + 1]),
        Math.abs(reference.data[offset + 2] - candidate.data[offset + 2]),
        Math.abs(reference.data[offset + 3] - candidate.data[offset + 3]),
      ) > 8;
      if (changed) fullChanged++;
      if (x >= roi.x0 && x < roi.x1 && y >= roi.y0 && y < roi.y1) {
        viewSamples++;
        if (changed) viewChanged++;
      }
      for (const [name, region] of Object.entries(detailRegions)) {
        if (x >= region.x0 && x < region.x1 && y >= region.y0 && y < region.y1) {
          detailCounts[name].samples++;
          if (changed) detailCounts[name].changed++;
        }
      }
    }
  }
  const fullSamples = reference.width * reference.height;
  return {
    threshold: 8,
    limit: SAME_POSE_CHANGED_FRACTION_LIMIT,
    roi,
    fullSamples,
    fullChanged,
    fullChangedFraction: fullChanged / fullSamples,
    viewSamples,
    viewChanged,
    viewChangedFraction: viewSamples ? viewChanged / viewSamples : 1,
    detailRegionLimit: TEXT_REGION_CHANGED_FRACTION_LIMIT,
    detailRegions: Object.fromEntries(Object.entries(detailRegions).map(([name, region]) => [name, {
      ...region,
      samples: detailCounts[name].samples,
      changed: detailCounts[name].changed,
      changedFraction: detailCounts[name].samples ?
        detailCounts[name].changed / detailCounts[name].samples : 1,
    }])),
  };
}

const productIdentity = options.hardware ?
  readProductIdentity(options.binDir, options.expectedWasmOrigSha256) : null;
if (!options.hardware) {
  mkdirSync(outDir, { recursive: true });
  evidenceAllocated = true;
}
const browser = await chromium.launch({
  headless: false,
  args: [
    "--enable-unsafe-webgpu",
    ...(options.hardware ? ["--use-angle=metal"] : [
      "--use-webgpu-adapter=swiftshader",
      "--use-gpu-in-tests",
    ]),
    ...(process.platform === "linux" && process.env.DISPLAY ? ["--ozone-platform=x11"] : []),
  ],
});

let page = null;
let adapter = null;
try {
  const browserVersion = browser.version();
  const origin = `http://127.0.0.1:${port}`;
  if (options.hardware) {
    if (browserVersion !== CHROMIUM_VERSION) {
      throw new Error(`Chromium ${CHROMIUM_VERSION} required, got ${browserVersion}`);
    }
    const probeContext = await browser.newContext();
    const probePage = await probeContext.newPage();
    await probePage.route(`${origin}/__bw_p0ij_adapter_probe__`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<!doctype html><meta charset=utf-8><title>adapter probe</title>",
      });
    });
    await probePage.goto(`${origin}/__bw_p0ij_adapter_probe__`, {
      waitUntil: "domcontentloaded",
    });
    adapter = await probeAdapter(probePage);
    await probeContext.close();
    if (adapter.status !== "ACCEPTED") {
      throw new Error(`hardware adapter rejected: ${adapter.reason}`);
    }
    productIdentity.servedGeneration = await fetchServedGeneration(
      origin, options.expectedWasmOrigSha256,
    );
    if (existsSync(outDir)) throw new Error(`immutable evidence run already exists: ${outDir}`);
    mkdirSync(outDir, { recursive: true });
    evidenceAllocated = true;
  }
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720},
    deviceScaleFactor: 1,
  });
  page = await context.newPage();
  browser.on("disconnected", () => lifecycleEvents.push("browser-disconnected"));
  page.on("close", () => lifecycleEvents.push("page-closed"));
  page.on("crash", () => lifecycleEvents.push("page-crashed"));
  /* Apple hardware takes diagnostics-bootstrap.js's production rejection fallback, while local
   * SwiftShader successfully locks and headed Playwright disconnects during repeated relative
   * moves. Reproduce the filed hardware path by making the native call reject before the shell
   * captures and wraps it; the shipping rejection consumer remains the code under test. */
  if (!options.hardware) {
    await page.addInitScript(() => {
      Object.defineProperty(HTMLCanvasElement.prototype, "requestPointerLock", {
        configurable: true,
        value() {
          return Promise.reject(new DOMException(
            "The root document of this element is not valid for pointer lock.",
            "WrongDocumentError"));
        },
      });
    });
  }
  await page.addInitScript((monitor) => { window.__BW_PYEXPR = monitor; }, PY_MONITOR);
  await page.addInitScript(() => {
    const events = [];
    const propagationStops = [];
    for (const method of ["stopPropagation", "stopImmediatePropagation"]) {
      const native = Event.prototype[method];
      Object.defineProperty(Event.prototype, method, {
        configurable: true,
        writable: true,
        value(...args) {
          if (this.type === "keydown" || this.type === "keyup") {
            propagationStops.push({
              method,
              type: this.type,
              code: this.code || null,
              target: this.target?.id || this.target?.tagName || null,
              stack: String(new Error().stack || "").split("\n").slice(1, 6),
            });
          }
          return native.apply(this, args);
        },
      });
    }
    const recordKeyPhase = (listener) => (event) => {
      events.push({
        type: event.type,
        listener,
        code: event.code || null,
        key: event.key || null,
        eventPhase: event.eventPhase,
        target: event.target?.id || event.target?.tagName || null,
        timeStamp: event.timeStamp,
      });
    };
    document.addEventListener("keydown", recordKeyPhase("document-capture"), true);
    document.addEventListener("keyup", recordKeyPhase("document-capture"), true);
    document.addEventListener("keydown", recordKeyPhase("document-bubble"), false);
    document.addEventListener("keyup", recordKeyPhase("document-bubble"), false);
    window.addEventListener("keydown", recordKeyPhase("window-bubble"), false);
    window.addEventListener("keyup", recordKeyPhase("window-bubble"), false);
    for (const type of [
      "pointerdown", "pointerup", "mousemove", "mousedown", "mouseup", "click", "dblclick",
      "keydown", "keyup",
    ]) {
      window.addEventListener(type, (event) => {
        events.push({
          type,
          detail: event.detail,
          button: event.button,
          buttons: event.buttons,
          clientX: event.clientX,
          clientY: event.clientY,
          code: event.code || null,
          key: event.key || null,
          ctrlKey: event.ctrlKey === true,
          shiftKey: event.shiftKey === true,
          altKey: event.altKey === true,
          metaKey: event.metaKey === true,
          timeStamp: event.timeStamp,
        });
      }, true);
    }
    for (const type of ["pointerlockchange", "pointerlockerror"]) {
      document.addEventListener(type, () => {
        events.push({
          type,
          pointerLockOwned: document.pointerLockElement === document.querySelector("canvas"),
          timeStamp: performance.now(),
        });
      }, true);
    }
    Object.defineProperty(window, "__bwP0DomInputs", {
      value: {snapshot: () => events.map((event) => ({...event}))},
      configurable: false,
      writable: false,
    });
    Object.defineProperty(window, "__bwP0PropagationStops", {
      value: {snapshot: () => propagationStops.map((item) => ({...item}))},
      configurable: false,
      writable: false,
    });
  });
  page.on("console", (message) => {
    const line = message.text();
    consoleLines.push(line);
    const match = /^P0S_STATE (\{.*\})$/.exec(line);
    if (match) {
      states.push(JSON.parse(match[1]));
    }
    const inputMatch = /^P0S_INPUT (\{.*\})$/.exec(line);
    if (inputMatch) {
      inputEvents.push(JSON.parse(inputMatch[1]));
    }
  });
  page.on("pageerror", (error) => pageErrors.push(`${error.name}: ${error.message}`));

  await page.goto(`${origin}/windowed.html?gate=1280x720`, {
    waitUntil: "domcontentloaded",
    timeout: 180000,
  });
  await page.waitForFunction(() => ["running", "error"].includes(
    document.querySelector("#state")?.dataset.state), undefined, {
    timeout: 180000,
    polling: 250,
  });
  const bootState = await page.evaluate(() => document.querySelector("#state")?.dataset.state);
  if (bootState !== "running") {
    throw new Error(`boot failed before running: ${bootState || "absent"}`);
  }
  await page.waitForFunction(() => document.querySelector("#loader")?.classList.contains("bw-gone"),
    undefined, {timeout: 90000, polling: 250});
  await page.waitForTimeout(5000);

  const canvas = page.locator("#canvas");
  await canvas.focus();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(1000);
  await page.waitForFunction(() => Boolean(window.__bwModule?._bw_wm_tick_count?.()),
    undefined, {timeout: 30000, polling: 100});

  const latestState = () => states.at(-1) || null;
  const waitForState = async (predicate, label, timeout = 15000) => {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const state = [...states].reverse().find(predicate);
      if (state) return state;
      await page.waitForTimeout(50);
    }
    throw new Error(`timeout waiting for ${label}; latest=${JSON.stringify(latestState())}`);
  };
  const waitForInputEvent = async (start, predicate, label, timeout = 5000) => {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const event = inputEvents.slice(start).find(predicate);
      if (event) return event;
      await page.waitForTimeout(25);
    }
    throw new Error(`timeout waiting for ${label}; tail=${JSON.stringify(inputEvents.slice(-12))}`);
  };
  await waitForState((state) => state.workspace === "Layout" && state.view,
    "initial Layout VIEW_3D");

  /* A transferred OffscreenCanvas can briefly screenshot as a single white compositor tile even
   * after the shell's readiness DOM changes. Do not start trusted input against that intermediate
   * automation state; require semantic pixels without using byte size as an artifact verdict. */
  const semanticDeadline = Date.now() + 30000;
  while (true) {
    const pixels = semanticPixels(await canvas.screenshot());
    if (pixels.quantizedColors >= 128 && pixels.nonWhiteRatio >= 0.5) break;
    if (Date.now() >= semanticDeadline) {
      throw new Error(`semantic canvas did not arrive: ${JSON.stringify(pixels)}`);
    }
    await page.waitForTimeout(250);
  }

  const captureBuffers = new Map();
  const capture = async (name, metadata = {}) => {
    const buffer = await canvas.screenshot({path: resolve(outDir, `${name}.png`)});
    captureBuffers.set(name, buffer);
    const sample = {
      name,
      sha256: sha256(buffer),
      bytes: buffer.length,
      semanticPixels: semanticPixels(buffer),
      state: latestState(),
      ticks: await page.evaluate(() => Number(window.__bwModule?._bw_wm_tick_count?.() ?? -1)),
      presents: await page.evaluate(() => Number(window.__bwModule?._bw_present_count?.() ?? -1)),
      redrawRetries: await page.evaluate(() =>
        Number(window.__bwModule?._bw_redraw_retry_count?.() ?? -1)),
      ...metadata,
    };
    steps.push(sample);
    console.log(`P0S_STEP ${name} bytes=${sample.bytes} workspace=${sample.state?.workspace || "none"} ` +
      `cube_in_view=${sample.state?.cube_in_view ?? false} presents=${sample.presents}`);
    return sample;
  };
  const waitForCanvasChange = async (beforeSha256, label) => {
    const started = Date.now();
    while (Date.now() - started <= PIXEL_RECOVERY_TIMEOUT_MS) {
      if (sha256(await canvas.screenshot()) !== beforeSha256) return Date.now() - started;
      await page.waitForTimeout(250);
    }
    throw new Error(`${label} stayed pixel-identical for ${PIXEL_RECOVERY_TIMEOUT_MS}ms`);
  };
  const waitForCanvasStable = async (label) => {
    const started = Date.now();
    let previous = sha256(await canvas.screenshot());
    let stableSince = Date.now();
    while (Date.now() - started <= PIXEL_RECOVERY_TIMEOUT_MS) {
      await page.waitForTimeout(PIXEL_STABLE_SAMPLE_MS);
      const current = sha256(await canvas.screenshot());
      if (current !== previous) {
        previous = current;
        stableSince = Date.now();
      }
      if (Date.now() - stableSince >= PIXEL_STABLE_WINDOW_MS) {
        return Date.now() - started;
      }
    }
    throw new Error(`${label} did not hold stable pixels for ${PIXEL_STABLE_WINDOW_MS}ms`);
  };
  const canvasBox = await canvas.boundingBox();
  if (!canvasBox) throw new Error("canvas has no bounding box");
  const viewCenter = (state = latestState()) => {
    if (!state?.view) throw new Error(`no VIEW_3D in state ${JSON.stringify(state)}`);
    return {
      x: canvasBox.x + state.view.x + state.view.width / 2,
      y: canvasBox.y + canvasBox.height - (state.view.y + state.view.height / 2),
    };
  };
  const cubeScreenPoint = (state = latestState()) => {
    if (!state?.view || !Array.isArray(state.cube_screen) || state.cube_screen.length !== 2 ||
        state.cube_in_view !== true) {
      throw new Error(`Cube has no clickable VIEW_3D projection: ${JSON.stringify(state)}`);
    }
    return {
      /* The projected origin is covered by Blender's 3D-cursor overlay. Offset onto the visible
       * Cube face so this is an object-selection canary, not a cursor-overlay hit test. */
      x: Math.round(canvasBox.x + state.view.x + state.cube_screen[0] - 32),
      y: Math.round(canvasBox.y + canvasBox.height - (state.view.y + state.cube_screen[1]) + 18),
    };
  };
  const middleDrag = async (dx, dy, shift = false) => {
    const center = viewCenter();
    await page.mouse.move(center.x, center.y);
    if (shift) await page.keyboard.down("ShiftLeft");
    await page.mouse.down({button: "middle"});
    await page.mouse.move(center.x + dx, center.y + dy, {steps: 8});
    await page.mouse.up({button: "middle"});
    if (shift) await page.keyboard.up("ShiftLeft");
    await page.waitForTimeout(700);
  };
  const orderedLeftClick = async (x, y, label, receiptTimeout = 5000) => {
    const moveStart = inputEvents.length;
    await page.mouse.move(x, y);
    await waitForInputEvent(moveStart,
      (event) => event.type === "MOUSEMOVE" && event.x === Math.round(x),
      `${label} target move`, receiptTimeout);
    const pressStart = inputEvents.length;
    await page.mouse.down({button: "left"});
    await waitForInputEvent(pressStart,
      (event) => event.type === "LEFTMOUSE" && event.value === "PRESS" &&
        event.x === Math.round(x),
      `${label} press`, receiptTimeout);
    const releaseStart = inputEvents.length;
    await page.mouse.up({button: "left"});
    await waitForInputEvent(releaseStart,
      (event) => event.type === "LEFTMOUSE" && event.value === "RELEASE" &&
        event.x === Math.round(x),
      `${label} release`, receiptTimeout);
  };
  const attemptWorkspaceClick = async (workspace, x, timeout = 3000) => {
    const stateStart = latestState()?.sequence || 0;
    /* Shading workspace construction can monopolize SwiftShader's WM worker for more than five
     * seconds after the press. Keep the hardware evidence bar at five seconds; only the named
     * software fallback gets a longer, still-bounded input-receipt window. */
    const receiptTimeout = options.hardware ? 5000 : 15000;
    await orderedLeftClick(x, 13, `workspace ${workspace}`, receiptTimeout);
    try {
      await waitForState((state) => state.sequence > stateStart && state.workspace === workspace,
        `workspace ${workspace}`, timeout);
      return true;
    }
    catch (_) {
      return false;
    }
  };
  let referencePoseState = null;
  const establishKnownPose = async (label) => {
    const center = viewCenter();
    await page.mouse.move(center.x, center.y);
    await canvas.focus();
    await page.keyboard.press("Escape");
    const viewStart = latestState()?.sequence || 0;
    const rotationBefore = JSON.stringify(latestState()?.view_rotation || null);
    await page.keyboard.press("Numpad1");
    await waitForState((state) => state.sequence > viewStart && state.workspace === "Layout" &&
      JSON.stringify(state.view_rotation || null) !== rotationBefore,
    `${label} front view`, 10000);
    const frameStart = latestState()?.sequence || 0;
    const distanceBefore = latestState()?.view_distance;
    const locationBefore = latestState()?.view_location;
    const alreadyFramed = referencePoseState !== null &&
      Math.abs(distanceBefore - referencePoseState.view_distance) < 0.0001 &&
      JSON.stringify(locationBefore) === JSON.stringify(referencePoseState.view_location);
    await page.keyboard.press("NumpadDecimal");
    if (alreadyFramed) {
      /* Frame Selected is intentionally a no-op when orbit changed orientation but retained the
       * already-framed distance/location. The preceding Numpad1 transition proves input liveness;
       * bind this no-op to the exact saved pose instead of waiting for a fabricated state change. */
      await page.waitForTimeout(500);
      if (latestState()?.cube_in_view !== true ||
          Math.abs(latestState().view_distance - referencePoseState.view_distance) >= 0.0001 ||
          JSON.stringify(latestState().view_location) !==
            JSON.stringify(referencePoseState.view_location)) {
        throw new Error(`${label} already-framed pose changed unexpectedly`);
      }
    }
    else {
      await waitForState((state) => state.sequence > frameStart && state.workspace === "Layout" &&
        state.cube_in_view === true && state.view_distance < distanceBefore,
      `${label} Frame Selected`, 10000);
    }
  };
  const samePoseState = (state) => ({
    workspace: state?.workspace || null,
    mode: state?.mode || null,
    selected: state?.selected ?? null,
    selectedCount: state?.selected_count ?? null,
    activeObject: state?.active_object || null,
    location: state?.location || null,
    rotation: state?.rotation || null,
    scale: state?.scale || null,
    view: state?.view || null,
    viewDistance: state?.view_distance ?? null,
    viewLocation: state?.view_location || null,
    viewRotation: state?.view_rotation || null,
    viewPerspective: state?.view_perspective || null,
  });
  const makeSamePoseCanary = (name, referenceName, candidateName) => {
    const reference = steps.find((step) => step.name === referenceName);
    const candidate = steps.find((step) => step.name === candidateName);
    if (!reference || !candidate) {
      throw new Error(`same-pose samples are absent: ${referenceName}, ${candidateName}`);
    }
    return {
      name,
      reference: referenceName,
      candidate: candidateName,
      referenceSha256: reference.sha256,
      candidateSha256: candidate.sha256,
      referenceState: samePoseState(reference.state),
      candidateState: samePoseState(candidate.state),
      pixelDiff: samePosePixelDiff(
        captureBuffers.get(referenceName), captureBuffers.get(candidateName), candidate.state.view,
      ),
    };
  };
  const moveCubeAndUndo = async (label, moveStep, undoStep) => {
    const before = [...latestState().location];
    const moveStart = latestState()?.sequence || 0;
    const center = viewCenter();
    await page.mouse.move(center.x, center.y);
    await canvas.focus();
    await page.keyboard.press("Escape");
    await page.keyboard.press("g");
    await page.keyboard.press("x");
    await page.keyboard.type("2");
    await page.keyboard.press("Enter");
    const movedState = await waitForState((state) => state.sequence > moveStart &&
      Math.abs(state.location?.[0] - (before[0] + 2)) < 0.0001,
    `${label} G X 2`, 10000);
    await page.waitForTimeout(700);
    await capture(moveStep);
    const undoStart = latestState()?.sequence || 0;
    await page.keyboard.press("Control+z");
    const undoneState = await waitForState((state) => state.sequence > undoStart &&
      Math.abs(state.location?.[0] - before[0]) < 0.0001,
    `${label} transform undo`, 10000);
    await page.waitForTimeout(700);
    await capture(undoStep);
    return {
      operation: "G X 2 Enter; Control+Z",
      before,
      moved: movedState.location,
      undone: undoneState.location,
    };
  };
  const samePoseCanaries = [];
  let postStressOperatorCanary = null;

  await capture("00-baseline");
  /* The driver reported that this exact workspace coordinate works before cumulative navigation
   * but not afterward. Bind that distinction to Blender's own active-workspace state, and use the
   * stock keyboard cycle only as an independent control when the pointer hit test fails. */
  const preflightModelingClick = await attemptWorkspaceClick("Modeling", 352, 3000);
  await capture("01-preflight-modeling-click", {workspaceRequested: "Modeling",
    workspaceAccepted: preflightModelingClick});
  let preflightModelingKeyboard = false;
  if (!preflightModelingClick) {
    await canvas.focus();
    const stateStart = latestState()?.sequence || 0;
    await page.keyboard.press("Control+PageDown");
    try {
      await waitForState((state) => state.sequence > stateStart && state.workspace === "Modeling",
        "keyboard workspace Modeling", 5000);
      preflightModelingKeyboard = true;
    }
    catch (_) {}
    await capture("02-preflight-modeling-keyboard", {workspaceRequested: "Modeling",
      workspaceAccepted: preflightModelingKeyboard});
  }
  if (latestState()?.workspace === "Modeling") {
    await canvas.focus();
    const stateStart = latestState()?.sequence || 0;
    await page.keyboard.press("Control+PageUp");
    await waitForState((state) => state.sequence > stateStart && state.workspace === "Layout",
      "keyboard return to Layout", 10000);
    await page.waitForTimeout(500);
  }

  /* Replay the driver's tighter total-freeze isolation before the broader cumulative battery:
   * five stock view transitions, select-all/deselect-all, an orbit, click-select, a native
   * transform/undo, and another orbit. Every action is bound to Blender-native state so a colorful
   * but frozen retained canvas cannot pass. */
  const isolatedViewSteps = [
    ["Numpad1", "02a-isolated-front"],
    ["Numpad3", "02b-isolated-right"],
    ["Numpad7", "02c-isolated-top"],
    ["Numpad0", "02d-isolated-camera"],
    ["Numpad4", "02e-isolated-camera-orbit-cancelled"],
  ];
  const isolatedCenter = viewCenter();
  await page.mouse.move(isolatedCenter.x, isolatedCenter.y);
  await canvas.focus();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(250);
  const isolatedViews = [];
  for (const [key, name] of isolatedViewSteps) {
    const before = latestState();
    const sequenceStart = before?.sequence || 0;
    const rotationBefore = JSON.stringify(before?.view_rotation || null);
    const perspectiveBefore = before?.view_perspective || null;
    await canvas.focus();
    await page.keyboard.press(key);
    let state;
    let expectedEffect = "view-change";
    if (key === "Numpad4" && perspectiveBefore === "CAMERA") {
      /* Blender's stock VIEW3D_OT_view_orbit returns OPERATOR_CANCELLED in an unlocked camera
       * view. Preserve the driver's exact key while binding the native no-op rather than
       * fabricating a transition. The following trusted MMB orbit is the liveness check. */
      expectedEffect = "cancelled-in-camera-view";
      await page.waitForTimeout(750);
      state = latestState();
      if (state?.view_perspective !== perspectiveBefore ||
          JSON.stringify(state?.view_rotation || null) !== rotationBefore) {
        throw new Error("isolated Numpad4 unexpectedly changed the unlocked camera view");
      }
    }
    else if (key === "Numpad0") {
      /* Camera view publishes an intermediate PERSP state before CAMERA. Do not bind the
       * diagnostic to that transient state and misattribute the later transition to Numpad4. */
      state = await waitForState((candidate) => candidate.sequence > sequenceStart &&
        candidate.view_perspective === "CAMERA",
      "isolated Numpad0 camera view transition", 10000);
    }
    else {
      state = await waitForState((candidate) => candidate.sequence > sequenceStart &&
        (JSON.stringify(candidate.view_rotation || null) !== rotationBefore ||
         candidate.view_perspective !== perspectiveBefore),
      `isolated ${key} view transition`, 10000);
    }
    await page.waitForTimeout(500);
    const pixelSettleMs = (key === "Numpad0" || key === "Numpad4") ?
      await waitForCanvasStable(`isolated ${key} camera pixels`) : null;
    const sample = await capture(name, {
      isolatedInput: key,
      expectedEffect,
      ...(pixelSettleMs === null ? {} : {pixelSettleMs}),
    });
    isolatedViews.push({
      key,
      expectedEffect,
      /* View transitions can animate through one or more diagnostic states. Bind the native
       * record to the same settled state as the screenshot, not the first transition sample. */
      sequence: sample.state.sequence,
      perspective: sample.state.view_perspective,
      rotation: sample.state.view_rotation,
      sha256: sample.sha256,
      ...(pixelSettleMs === null ? {} : {pixelSettleMs}),
    });
  }

  const selectStart = latestState()?.sequence || 0;
  await canvas.focus();
  await page.keyboard.press("a");
  const selectAllState = await waitForState((state) => state.sequence > selectStart &&
    state.selected === true && state.selected_count === 3,
  "isolated select all", 10000);
  await page.waitForTimeout(500);
  await capture("02f-isolated-select-all");

  const deselectStart = latestState()?.sequence || 0;
  await page.keyboard.press("Alt+a");
  const deselectAllState = await waitForState((state) => state.sequence > deselectStart &&
    state.selected === false && state.selected_count === 0,
  "isolated deselect all", 10000);
  await page.waitForTimeout(500);
  const beforeClickOrbit = await capture("02g-isolated-deselect-all");
  const beforeClickOrbitRotation = deselectAllState.view_rotation;
  await middleDrag(34, 20);
  const afterClickOrbitState = await waitForState((state) =>
    state.sequence > deselectAllState.sequence &&
    JSON.stringify(state.view_rotation || null) !== JSON.stringify(beforeClickOrbitRotation || null),
  "isolated pre-click orbit", 10000);
  const preClickOrbitPixelSettleMs = await waitForCanvasChange(
    beforeClickOrbit.sha256, "isolated pre-click orbit");
  const afterClickOrbit = await capture("02h-isolated-orbit-before-click");

  const clickPoint = cubeScreenPoint(afterClickOrbitState);
  const isolatedDomStart = await page.evaluate(() =>
    window.__bwP0DomInputs?.snapshot?.().length || 0);
  const isolatedNativeStart = inputEvents.length;
  const clickStart = latestState()?.sequence || 0;
  await orderedLeftClick(clickPoint.x, clickPoint.y, "isolated viewport Cube");
  let clickSelectState = null;
  let selectionMode = "viewport";
  try {
    clickSelectState = await waitForState((state) => state.sequence > clickStart &&
      state.selected === true && state.selected_count === 1 && state.active_object === "Cube",
    "isolated click-select Cube", 3000);
  }
  catch (error) {
    if (options.hardware) {
      throw new Error(`hardware viewport click did not select Cube: ${error.message}`);
    }
    /* SwiftShader's diagnostic lane can lack Blender's GPU-pick result. Keep the attempted
     * trusted viewport coordinates in the evidence, then use Blender's stock Select All shortcut
     * as an independent post-orbit liveness canary. Moving all three default-scene objects is
     * harmless here: the native Cube location still changes and undo still restores it. Apple
     * evidence may never take this branch. */
    selectionMode = "fallback-select-all";
    const recoveryStart = latestState()?.sequence || 0;
    await canvas.focus();
    /* A failed software GPU pick can retain VIEW3D_OT_select until its bounded asynchronous
     * readback timeout. Its RUNNING_MODAL|PASS_THROUGH status still prevents later modal handlers
     * from observing the same key event, which made an immediate fallback A a false freeze
     * signal. Cancel that diagnostic-only pick explicitly; Apple evidence may never take this
     * branch because it requires the trusted click itself to select Cube. */
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
    await page.keyboard.press("a");
    clickSelectState = await waitForState((state) => state.sequence > recoveryStart &&
      state.selected === true && state.selected_count === 3 && state.active_object === "Cube",
    "fallback post-orbit Select All liveness", 10000);
  }
  await page.waitForTimeout(500);
  await capture("02i-isolated-click-select");
  const isolatedDomClick = (await page.evaluate(() =>
    window.__bwP0DomInputs?.snapshot?.() || [])).slice(isolatedDomStart)
    .find((event) => event.type === "click" && event.button === 0);
  const isolatedNativeClick = inputEvents.slice(isolatedNativeStart)
    .find((event) => event.type === "LEFTMOUSE" && event.value === "PRESS");

  const isolatedOperator = await moveCubeAndUndo(
    "isolated post-click", "02j-isolated-move", "02k-isolated-undo",
  );
  const beforePostClickOrbitState = latestState();
  const beforePostClickOrbit = steps.find((step) => step.name === "02k-isolated-undo");
  await middleDrag(-34, 16);
  const afterPostClickOrbitState = await waitForState((state) =>
    state.sequence > beforePostClickOrbitState.sequence &&
    JSON.stringify(state.view_rotation || null) !==
      JSON.stringify(beforePostClickOrbitState.view_rotation || null),
  "isolated post-click orbit", 10000);
  const postClickOrbitPixelSettleMs = await waitForCanvasChange(
    beforePostClickOrbit.sha256, "isolated post-click orbit");
  const afterPostClickOrbit = await capture("02l-isolated-orbit-after-click");
  let fallbackSelectionRestore = null;
  if (selectionMode === "fallback-select-all") {
    /* Return the software-only diagnostic to the same Cube-only state required from hardware.
     * This is an ordinary Outliner click against the fixed 1280x720 default Layout workspace,
     * not a Python/state mutation. Otherwise NumpadDecimal faithfully frames all three objects
     * selected by the liveness fallback and invalidates the same-pose visual oracle. */
    const target = {
      x: Math.round(canvasBox.x + canvasBox.width - 130),
      y: Math.round(canvasBox.y + 106),
    };
    const domStart = await page.evaluate(() =>
      window.__bwP0DomInputs?.snapshot?.().length || 0);
    const nativeStart = inputEvents.length;
    const stateStart = latestState()?.sequence || 0;
    await orderedLeftClick(target.x, target.y, "fallback Outliner Cube");
    const restoredState = await waitForState((state) => state.sequence > stateStart &&
      state.selected === true && state.selected_count === 1 && state.active_object === "Cube",
    "fallback Outliner Cube-only restore", 10000);
    const domClick = (await page.evaluate(() =>
      window.__bwP0DomInputs?.snapshot?.() || [])).slice(domStart)
      .find((event) => event.type === "click" && event.button === 0);
    const nativeClick = inputEvents.slice(nativeStart)
      .find((event) => event.type === "LEFTMOUSE" && event.value === "PRESS");
    fallbackSelectionRestore = {
      method: "outliner-click",
      expectedX: target.x,
      expectedY: target.y,
      expectedGhostY: Math.round(canvasBox.height - (target.y - canvasBox.y) - 1),
      domX: domClick?.clientX ?? null,
      domY: domClick?.clientY ?? null,
      ghostX: nativeClick?.x ?? null,
      ghostY: nativeClick?.y ?? null,
      sequence: restoredState.sequence,
      selectedCount: restoredState.selected_count,
      activeObject: restoredState.active_object,
    };
  }
  const isolationCanary = {
    viewKeys: ISOLATED_VIEW_KEYS,
    views: isolatedViews,
    selectionCounts: [
      selectAllState.selected_count,
      deselectAllState.selected_count,
      clickSelectState.selected_count,
    ],
    click: {
      expectedX: clickPoint.x,
      domX: isolatedDomClick?.clientX ?? null,
      ghostX: isolatedNativeClick?.x ?? null,
      selectionMode,
      fallbackLivenessInput: selectionMode === "fallback-select-all" ? "A" : null,
    },
    fallbackSelectionRestore,
    preClickOrbit: {
      beforeRotation: beforeClickOrbitRotation,
      afterRotation: afterClickOrbitState.view_rotation,
      beforeSha256: beforeClickOrbit.sha256,
      afterSha256: afterClickOrbit.sha256,
      redrawRetries: [beforeClickOrbit.redrawRetries, afterClickOrbit.redrawRetries],
      pixelSettleMs: preClickOrbitPixelSettleMs,
    },
    operator: isolatedOperator,
    postClickOrbit: {
      beforeRotation: beforePostClickOrbitState.view_rotation,
      afterRotation: afterPostClickOrbitState.view_rotation,
      beforeSha256: beforePostClickOrbit?.sha256 || null,
      afterSha256: afterPostClickOrbit.sha256,
      redrawRetries: [beforePostClickOrbit?.redrawRetries ?? null,
        afterPostClickOrbit.redrawRetries],
      pixelSettleMs: postClickOrbitPixelSettleMs,
    },
  };

  /* Establish a same-run, same-device reference at a deterministic Blender-native pose. This is
   * the visual oracle the post-stress checks use; PNG size and native Cube state alone both missed
   * the driver's broken geometry/text frames. */
  await establishKnownPose("reference");
  await page.waitForTimeout(3000);
  await capture("03a-reference-pose-3s");
  await page.waitForTimeout(3000);
  await capture("03b-reference-pose-6s");
  referencePoseState = latestState();
  for (let index = 0; index < 10; index++) {
    await middleDrag(52, index % 2 === 0 ? 24 : -18);
  }
  await capture("10-after-orbit");
  for (let index = 0; index < 10; index++) {
    await middleDrag(38, 16, true);
  }
  await capture("20-after-pan");
  for (let index = 0; index < 10; index++) {
    const center = viewCenter();
    await page.mouse.move(center.x, center.y);
    await page.mouse.wheel(0, 180);
    await page.waitForTimeout(700);
  }
  await capture("30-after-zoom");

  /* Require nine genuine state transitions. An already-active tab is excluded:
   * waiting on that intentional no-op leaves its tooltip open and makes the
   * next automated click a tooltip dismissal rather than a workspace action. */
  const workspaceDomStart = await page.evaluate(() =>
    window.__bwP0DomInputs?.snapshot?.().length || 0);
  const workspaceNativeStart = inputEvents.length;
  const workspaceTabs = [
    ["Modeling", 352],
    ["Sculpting", 421],
    ["UV Editing", 494],
    ["Texture Paint", 577],
    ["Shading", 657],
    ["Animation", 727],
    ["Rendering", 805],
    ["Compositing", 891],
    ["Layout", 288],
  ];
  for (let index = 0; index < workspaceTabs.length; index++) {
    const [workspace, x] = workspaceTabs[index];
    await page.mouse.move(canvasBox.x + canvasBox.width / 2,
      canvasBox.y + canvasBox.height / 2);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(150);
    const workspaceBefore = latestState()?.workspace || null;
    const accepted = await attemptWorkspaceClick(workspace, x, 15000);
    await page.waitForTimeout(700);
    await capture(`4${index}-${workspace.replaceAll(" ", "")}`, {workspaceRequested: workspace,
      workspaceBefore, workspaceAccepted: accepted});
  }
  await page.waitForTimeout(100);
  const workspaceDomClicks = (await page.evaluate(() =>
    window.__bwP0DomInputs?.snapshot?.() || [])).slice(workspaceDomStart)
    .filter((event) => event.type === "click" && event.clientY === 13)
    .map((event) => event.clientX);
  const workspaceNativeClicks = inputEvents.slice(workspaceNativeStart)
    .filter((event) => event.type === "LEFTMOUSE" && event.value === "PRESS")
    .map((event) => event.x);

  await page.waitForTimeout(5000);
  await capture("50-after-idle");

  /* Return to Layout and restore the exact reference pose. Native scene state plus a same-pose
   * pixel comparison distinguishes a legitimately moved camera from dropped geometry, clipped
   * text, or retained grey overdraw. */
  await waitForState((state) => state.workspace === "Layout" && state.view,
    "return to Layout", 10000);
  await page.waitForTimeout(700);
  await capture("60-layout-return");
  await establishKnownPose("post-stress");
  await page.waitForTimeout(500);
  await capture("61a-frame-selected-500ms");
  await page.waitForTimeout(2500);
  await capture("61b-frame-selected-3s");
  await page.waitForTimeout(3000);
  await capture("61c-frame-selected-6s");
  samePoseCanaries.push(makeSamePoseCanary(
    "post-stress-known-pose", "03b-reference-pose-6s", "61c-frame-selected-6s",
  ));

  /* Directly bind the driver's total-freeze symptom: after cumulative navigation, a stock
   * transform must change Blender-native object state, and undo must restore it. A responsive
   * shell with a frozen WM worker can no longer pass merely because its canvas remains colorful. */
  postStressOperatorCanary = await moveCubeAndUndo(
    "post-stress", "62a-post-stress-move", "62b-post-stress-undo",
  );
  /* Repeat the same operator without changing its target. If this alone makes the first camera
   * state visible, the preceding six-second frame was stale rather than legitimately different. */
  await page.keyboard.press("NumpadDecimal");
  await page.waitForTimeout(1000);
  await capture("62-frame-selected-retrigger");
  await middleDrag(34, 20);
  await capture("63-final-orbit");
  await page.waitForTimeout(2300);
  await capture("64a-post-orbit-3s");
  await page.waitForTimeout(3000);
  await capture("64b-post-orbit-6s");
  await establishKnownPose("post-orbit");
  await page.waitForTimeout(3000);
  await capture("65a-post-orbit-known-pose-3s");
  await page.waitForTimeout(3000);
  await capture("65b-post-orbit-known-pose-6s");
  samePoseCanaries.push(makeSamePoseCanary(
    "post-orbit-known-pose", "03b-reference-pose-6s", "65b-post-orbit-known-pose-6s",
  ));

  const hardCompletenessWarnings = consoleLines.filter((line) =>
    /assembled group-0 resources do not match surviving WGSL bindings/i.test(line));
  const pendingCompletenessDiagnostics = consoleLines.filter((line) =>
    /WGPUWeb-bind-pending shader=/i.test(line));
  const relevantWarnings = consoleLines.filter((line) =>
    /WGPUShader|WebGPU|reject|validation|device lost|Pointer Lock/i.test(line));
  const diagnostic = {
    schema: "blender-web.p0ij-interaction-stress.v2",
    evidenceClass: options.hardware ? HARDWARE_EVIDENCE_CLASS : FALLBACK_EVIDENCE_CLASS,
    run: options.run,
    capturedAt: new Date().toISOString(),
    source: {
      path: relative(root, fileURLToPath(import.meta.url)).replaceAll("\\", "/"),
      sha256: sha256File(fileURLToPath(import.meta.url)),
    },
    stack: {
      platform: process.platform,
      nodeVersion: process.version,
      playwrightVersion,
      pngjsVersion,
      chromiumVersion: browserVersion,
    },
    adapter,
    productIdentity,
    contract: {
      isolatedFreeze: {
        viewKeys: [...ISOLATED_VIEW_KEYS],
        selectionCounts: [3, 0, 1],
        hardwareSelectionMode: "viewport",
        operator: "G X 2 Enter; Control+Z",
        orbits: 2,
      },
      stress: {orbit: 10, pan: 10, zoom: 10, workspaceTransitions: 9},
      samePoseChangedFractionLimit: SAME_POSE_CHANGED_FRACTION_LIMIT,
      textRegionChangedFractionLimit: TEXT_REGION_CHANGED_FRACTION_LIMIT,
      postStressOperator: "G X 2 Enter; Control+Z",
      incompleteBindGroups: 0,
      pageErrors: 0,
    },
    product: {
      state: await page.evaluate(() => document.querySelector("#state")?.dataset.state || null),
      ticks: await page.evaluate(() => Number(window.__bwModule?._bw_wm_tick_count?.() ?? -1)),
      presents: await page.evaluate(() => Number(window.__bwModule?._bw_present_count?.() ?? -1)),
      viewportContent: await page.evaluate(() =>
        Number(window.__bwModule?._bw_viewport_content_present_count?.() ?? -1)),
      redrawRetries: await page.evaluate(() =>
        Number(window.__bwModule?._bw_redraw_retry_count?.() ?? -1)),
    },
    steps,
    states,
    inputEvents,
    domInputEvents: await page.evaluate(() => window.__bwP0DomInputs?.snapshot?.() || []),
    workspaceInputCanary: {
      expectedX: workspaceTabs.map(([, x]) => x),
      domClickX: workspaceDomClicks,
      ghostPressX: workspaceNativeClicks,
    },
    isolationCanary,
    samePoseCanaries,
    postStressOperatorCanary,
    hardCompletenessWarnings,
    pendingCompletenessDiagnostics,
    relevantWarnings: relevantWarnings.slice(-300),
    lifecycleEvents,
    pageErrors,
  };
  writeFileSync(
    resolve(outDir, "diagnostic.json"),
    `${JSON.stringify(diagnostic, null, 2)}\n`,
    options.hardware ? {flag: "wx"} : undefined,
  );
  console.log(`P0S_DIAGNOSTIC_DONE steps=${steps.length} states=${states.length} ` +
    `hard_warnings=${hardCompletenessWarnings.length} page_errors=${pageErrors.length} ` +
    `presents=${diagnostic.product.presents} evidence=${diagnostic.evidenceClass} ` +
    `same_pose=${samePoseCanaries.map((item) =>
      item.pixelDiff.viewChangedFraction.toFixed(6)).join(",")}`);
}
catch (error) {
  const pageSnapshot = page ? await page.evaluate(() => ({
    state: document.querySelector("#state")?.dataset.state || null,
    activeElement: document.activeElement?.id || document.activeElement?.tagName || null,
    pointerLock: window.__bwPointerLockBridge?.snapshot?.() || null,
    focusBridge: window.__bwFocusBridge?.snapshot?.() || null,
    imeBridge: window.__bwImeBridge?.snapshot?.() || null,
    callbackRegistrations: Number(
      window.__bwModule?._bw_callback_registration_attempt_count?.() ?? -1),
    propagationStops: (window.__bwP0PropagationStops?.snapshot?.() || []).slice(-40),
    domInputTail: (window.__bwP0DomInputs?.snapshot?.() || []).slice(-100),
    ticks: Number(window.__bwModule?._bw_wm_tick_count?.() ?? -1),
    presents: Number(window.__bwModule?._bw_present_count?.() ?? -1),
    redrawEpisodes: Number(window.__bwModule?._bw_redraw_episode_count?.() ?? -1),
    redrawRetries: Number(window.__bwModule?._bw_redraw_retry_count?.() ?? -1),
  })).catch(() => null) : null;
  const failure = {
    error: {name: String(error?.name || "Error"), message: String(error?.message || error)},
    pageErrors,
    lifecycleEvents,
    states: states.slice(-20),
    inputEvents: inputEvents.slice(-100),
    pageSnapshot,
    consoleTail: consoleLines.slice(-1000),
  };
  if (evidenceAllocated) {
    writeFileSync(
      resolve(outDir, "diagnostic-failure.json"),
      `${JSON.stringify(failure, null, 2)}\n`,
      options.hardware ? {flag: "wx"} : undefined,
    );
  }
  if (page && evidenceAllocated) {
    await page.screenshot({path: resolve(outDir, "diagnostic-failure.png")}).catch(() => {});
  }
  throw error;
}
finally {
  await browser.close();
}
