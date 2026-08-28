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
        if event.type in {'MOUSEMOVE','LEFTMOUSE','MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE'}:
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
    for (const type of ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "dblclick"]) {
      window.addEventListener(type, (event) => {
        events.push({
          type,
          detail: event.detail,
          button: event.button,
          buttons: event.buttons,
          clientX: event.clientX,
          clientY: event.clientY,
          timeStamp: event.timeStamp,
        });
      }, true);
    }
    Object.defineProperty(window, "__bwP0DomInputs", {
      value: {snapshot: () => events.map((event) => ({...event}))},
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
      ...metadata,
    };
    steps.push(sample);
    console.log(`P0S_STEP ${name} bytes=${sample.bytes} workspace=${sample.state?.workspace || "none"} ` +
      `cube_in_view=${sample.state?.cube_in_view ?? false} presents=${sample.presents}`);
    return sample;
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
  const attemptWorkspaceClick = async (workspace, x, timeout = 3000) => {
    const stateStart = latestState()?.sequence || 0;
    await page.mouse.click(x, 13);
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
    location: state?.location || null,
    rotation: state?.rotation || null,
    scale: state?.scale || null,
    view: state?.view || null,
    viewDistance: state?.view_distance ?? null,
    viewLocation: state?.view_location || null,
    viewRotation: state?.view_rotation || null,
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
  const locationBeforeMove = [...latestState().location];
  const moveStart = latestState()?.sequence || 0;
  await canvas.focus();
  await page.keyboard.press("g");
  await page.keyboard.press("x");
  await page.keyboard.type("2");
  await page.keyboard.press("Enter");
  const movedState = await waitForState((state) => state.sequence > moveStart &&
    Math.abs(state.location?.[0] - (locationBeforeMove[0] + 2)) < 0.0001,
  "post-stress G X 2", 10000);
  await page.waitForTimeout(700);
  await capture("62a-post-stress-move");
  const undoStart = latestState()?.sequence || 0;
  await page.keyboard.press("Control+z");
  const undoneState = await waitForState((state) => state.sequence > undoStart &&
    Math.abs(state.location?.[0] - locationBeforeMove[0]) < 0.0001,
  "post-stress transform undo", 10000);
  await page.waitForTimeout(700);
  await capture("62b-post-stress-undo");
  postStressOperatorCanary = {
    operation: "G X 2 Enter; Control+Z",
    before: locationBeforeMove,
    moved: movedState.location,
    undone: undoneState.location,
  };
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
  const relevantWarnings = consoleLines.filter((line) =>
    /WGPUShader|WebGPU|reject|validation|device lost|Pointer Lock/i.test(line));
  const diagnostic = {
    schema: "blender-web.p0ij-interaction-stress.v1",
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
        Number(window.__bwModule?._bw_viewport_content_count?.() ?? -1)),
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
    samePoseCanaries,
    postStressOperatorCanary,
    hardCompletenessWarnings,
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
  const failure = {
    error: {name: String(error?.name || "Error"), message: String(error?.message || error)},
    pageErrors,
    lifecycleEvents,
    states: states.slice(-20),
    inputEvents: inputEvents.slice(-100),
    consoleTail: consoleLines.slice(-100),
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
