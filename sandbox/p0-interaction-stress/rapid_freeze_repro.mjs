// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

import {createHash} from "node:crypto";
import {createReadStream} from "node:fs";
import {lstat, readFile, writeFile} from "node:fs/promises";
import {createRequire} from "node:module";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const moduleRoot = process.env.BW_NODE_MODULES || resolve(root, ".m4-node/node_modules");
const require = createRequire(resolve(moduleRoot, "package.json"));
const {chromium} = require("playwright");
const port = Number(process.argv[2] || 8123);
const hardwareDiagnostic = process.env.BW_P0_RAPID_HARDWARE === "1";
const sparseDiagnostic = process.env.BW_P0_SPARSE === "1";
const productSelfcheck = process.env.BW_P0_PRODUCT_SELFCHECK === "1";
const runLabel = process.env.BW_P0_RUN || "";
const expectedWasmOrigSha256 = process.env.BW_P0_EXPECTED_WASM_ORIG_SHA256 || "";
const outputPath = process.env.BW_P0_OUTPUT ? resolve(process.env.BW_P0_OUTPUT) : "";
const binDir = resolve(process.env.BLENDER_WEB_BIN ||
  resolve(root, "build-wasm-windowed-opt/bin"));
const ozonePlatform = process.env.BW_P0_OZONE || "";
const stateOnlyDiagnostic = process.env.BW_P0_STATE_ONLY === "1";
const sampleCadenceMs = sparseDiagnostic ? 650 : 350;
const REQUIRED_HARDWARE_STACK = Object.freeze({
  nodeVersion: "v22.16.0",
  playwrightVersion: "1.61.1",
  pngjsVersion: "7.0.0",
  chromiumVersion: "149.0.7827.55",
});
const PRODUCT_FILES = Object.freeze([
  "blender_browser.js",
  "blender_browser.wasm",
  "blender_browser.wasm.orig",
  "blender_browser.data",
  "blender_browser.split-build.json",
]);
const SAFE_RUN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const SOFTWARE_ADAPTER_TOKENS = Object.freeze([
  "swiftshader", "llvmpipe", "lavapipe", "softpipe", "software rasterizer",
  "microsoft basic render", "warp",
]);
const PY_MONITOR = String.raw`
import bpy,json,os,time
from bpy_extras import view3d_utils
_bwp0r={"started":time.perf_counter(),"input_sequence":0,"state_sequence":0,"last_state":None}
class WM_OT_bwp0r_input_probe(bpy.types.Operator):
    bl_idname="wm.bwp0r_input_probe"
    bl_label="P0 rapid input probe"
    bl_options={'INTERNAL'}
    def invoke(self,context,event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def modal(self,context,event):
        if event.type in {'MOUSEMOVE','LEFTMOUSE','MIDDLEMOUSE','A','G','ESC'}:
            _bwp0r["input_sequence"]+=1
            payload={
              "sequence":_bwp0r["input_sequence"],
              "elapsed_ms":round((time.perf_counter()-_bwp0r["started"])*1000,3),
              "type":event.type,"value":event.value,
              "x":event.mouse_x,"y":event.mouse_y,
              "alt":event.alt,"ctrl":event.ctrl,"shift":event.shift,"oskey":event.oskey,
              "modal_operators":[operator.bl_idname for operator in context.window.modal_operators],
            }
            os.write(2,("P0R_INPUT "+json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n").encode())
        return {'PASS_THROUGH'}
def _bwp0r_start_probe():
    if bpy.context.window is None: return 0.05
    bpy.ops.wm.bwp0r_input_probe('INVOKE_DEFAULT')
    return None
def _bwp0r_round(values):
    return [round(float(value),5) for value in values]
def _bwp0r_poll():
    window=bpy.context.window
    if window is None or window.screen is None: return 0.05
    obj=bpy.data.objects.get("Cube")
    area=next((item for item in window.screen.areas if item.type == 'VIEW_3D'),None)
    region=next((item for item in area.regions if item.type == 'WINDOW'),None) if area else None
    space=area.spaces.active if area else None
    rv3d=space.region_3d if space else None
    projection=view3d_utils.location_3d_to_region_2d(region,rv3d,obj.matrix_world.translation) if obj and region and rv3d else None
    state={
      "modal_operators":[operator.bl_idname for operator in window.modal_operators],
      "selected_count":len(bpy.context.selected_objects),
      "active_object":bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
      "location":_bwp0r_round(obj.location) if obj else None,
      "cube_window_xy":[round(region.x+projection.x,3),round(region.y+projection.y,3)] if projection else None,
      "view_rotation":_bwp0r_round(rv3d.view_rotation) if rv3d else None,
      "view_perspective":rv3d.view_perspective if rv3d else None,
    }
    key=json.dumps(state,sort_keys=True,separators=(",",":"))
    if key != _bwp0r["last_state"]:
        _bwp0r["last_state"]=key
        _bwp0r["state_sequence"]+=1
        state["sequence"]=_bwp0r["state_sequence"]
        state["elapsed_ms"]=round((time.perf_counter()-_bwp0r["started"])*1000,3)
        os.write(2,("P0R_STATE "+json.dumps(state,sort_keys=True,separators=(",",":"))+"\n").encode())
    return 0.025
bpy.utils.register_class(WM_OT_bwp0r_input_probe)
bpy.app.timers.register(_bwp0r_poll,first_interval=0.0,persistent=True)
bpy.app.timers.register(_bwp0r_start_probe,first_interval=0.0,persistent=True)
`.trim();
if (hardwareDiagnostic && process.platform !== "darwin") {
  throw new Error(`BW_P0_RAPID_HARDWARE is Apple-only; got ${process.platform}`);
}
if (hardwareDiagnostic && stateOnlyDiagnostic) {
  throw new Error("BW_P0_STATE_ONLY cannot weaken the Apple pixel diagnostic");
}
if (hardwareDiagnostic && productSelfcheck) {
  throw new Error("product identity self-check cannot allocate Apple evidence");
}
if (hardwareDiagnostic && !SAFE_RUN.test(runLabel)) {
  throw new Error("hardware diagnostic run label is invalid");
}
if ((hardwareDiagnostic || productSelfcheck) && !SHA256.test(expectedWasmOrigSha256)) {
  throw new Error("hardware diagnostic expected wasm.orig SHA-256 is invalid");
}
if (hardwareDiagnostic && !outputPath) {
  throw new Error("hardware diagnostic output path is required");
}

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const sha256File = (path) => new Promise((accept, reject) => {
  const digest = createHash("sha256");
  const stream = createReadStream(path);
  stream.on("data", (chunk) => digest.update(chunk));
  stream.on("error", reject);
  stream.on("end", () => accept(digest.digest("hex")));
});
const generationFromManifest = (manifest) => {
  const generation = {
    mode: manifest?.mode,
    originalWasmSha256: manifest?.original?.sha256,
    instrumentedWasmSha256: manifest?.instrumented?.sha256,
    javascriptSha256: manifest?.js?.sha256,
  };
  if (generation.mode !== "capture" ||
      ![generation.originalWasmSha256, generation.instrumentedWasmSha256,
        generation.javascriptSha256].every((value) => SHA256.test(value || ""))) {
    throw new Error("split manifest does not identify one CAPTURE generation");
  }
  return generation;
};
const inspectProductIdentity = async (servedPort, expectedOrig) => {
  const files = {};
  for (const name of PRODUCT_FILES) {
    const path = resolve(binDir, name);
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink()) {
      throw new Error(`hardware diagnostic product entry is not a direct file: ${name}`);
    }
    files[name] = {bytes: info.size, sha256: await sha256File(path)};
  }
  const localManifest = JSON.parse(await readFile(
    resolve(binDir, "blender_browser.split-build.json"), "utf8"));
  const generation = generationFromManifest(localManifest);
  if (generation.originalWasmSha256 !== files["blender_browser.wasm.orig"].sha256 ||
      generation.instrumentedWasmSha256 !== files["blender_browser.wasm"].sha256 ||
      generation.javascriptSha256 !== files["blender_browser.js"].sha256) {
    throw new Error("local CAPTURE manifest differs from product bytes");
  }
  if (generation.originalWasmSha256 !== expectedOrig) {
    throw new Error("local CAPTURE generation differs from expected wasm.orig");
  }
  const response = await fetch(
    `http://127.0.0.1:${servedPort}/bin/blender_browser.split-build.json`,
    {cache: "no-store"},
  );
  if (!response.ok) {
    throw new Error(`served CAPTURE manifest returned HTTP ${response.status}`);
  }
  const servedGeneration = generationFromManifest(await response.json());
  if (JSON.stringify(servedGeneration) !== JSON.stringify(generation)) {
    throw new Error("servedGeneration differs from local CAPTURE generation");
  }
  return {binDir, files, generation, servedGeneration};
};
const sourceIdentity = {
  path: "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs",
  sha256: await sha256File(fileURLToPath(import.meta.url)),
};
const productIdentity = (hardwareDiagnostic || productSelfcheck) ? await inspectProductIdentity(
  port, expectedWasmOrigSha256) : null;
if (productSelfcheck) {
  process.stdout.write(
    "P0J_RAPID_PRODUCT_IDENTITY_SELFCHECK_PASS " +
    `files=${Object.keys(productIdentity.files).length} ` +
    `wasm_orig=${productIdentity.generation.originalWasmSha256}\n`,
  );
  process.exit(0);
}
const classifyAdapter = (raw) => {
  const identity = Object.values(raw.info).join(" ").trim().toLowerCase();
  const softwareMatches = SOFTWARE_ADAPTER_TOKENS.filter((token) => identity.includes(token));
  if (/(^|[^a-z0-9])cpu([^a-z0-9]|$)/.test(identity)) softwareMatches.push("cpu");
  let reason = "accepted-hardware";
  if (!raw.present) reason = "adapter-absent";
  else if (raw.isFallbackAdapter === true) reason = "fallback-adapter";
  else if (raw.isFallbackAdapter !== false) reason = "fallback-status-absent";
  else if (!identity || !raw.info.architecture) reason = "adapter-info-absent";
  else if (softwareMatches.length) reason = "software-adapter";
  return {
    status: reason === "accepted-hardware" ? "ACCEPTED" : "REJECTED",
    reason,
    ...raw,
    softwareMatches,
  };
};
const probeAdapter = async (page) => classifyAdapter(await page.evaluate(async () => {
  const candidate = await navigator.gpu?.requestAdapter({powerPreference: "high-performance"});
  if (!candidate) {
    return {present: false, isFallbackAdapter: null, info: {}};
  }
  const info = candidate.info || {};
  return {
    present: true,
    isFallbackAdapter: typeof info.isFallbackAdapter === "boolean" ?
      info.isFallbackAdapter :
      (typeof candidate.isFallbackAdapter === "boolean" ? candidate.isFallbackAdapter : null),
    info: Object.fromEntries(["vendor", "architecture", "device", "description"]
      .map((key) => [key, typeof info[key] === "string" ? info[key] : ""])),
  };
}));

const READBACK_LIFECYCLE_FIELDS = Object.freeze([
  "submits", "mapStarts", "mapCompletes", "validationCompletes", "joinCompletes", "ready",
]);
const SELECTION_CONTINUATION_FIELDS = Object.freeze([
  "gpuAttempts", "gpuResults", "gpuFailures", "modalBegins", "modalFinishes",
]);
const classifySelectionReadbackBoundary = (baseline, current) => {
  const readbackDelta = Object.fromEntries(READBACK_LIFECYCLE_FIELDS.map((field) => [
    field,
    current?.selectionReadback?.[field] - baseline?.selectionReadback?.[field],
  ]));
  const continuationDelta = Object.fromEntries(SELECTION_CONTINUATION_FIELDS.map((field) => [
    field,
    current?.selectionContinuation?.[field] - baseline?.selectionContinuation?.[field],
  ]));
  const phase = current?.selectionContinuation?.gpuPhase;
  const active = current?.selectionContinuation?.active;
  const queuedEvents = current?.selectionContinuation?.queuedEvents;
  const result = (boundary) => ({
    boundary,
    phase,
    active,
    queuedEvents,
    readbackDelta,
    continuationDelta,
  });
  if (![...Object.values(readbackDelta), ...Object.values(continuationDelta),
        phase, active, queuedEvents].every(Number.isFinite) ||
      [...Object.values(readbackDelta), ...Object.values(continuationDelta)]
        .some((value) => value < 0)) {
    return result("invalid-counters");
  }
  if (continuationDelta.modalFinishes > 0 && active === 0) {
    if (continuationDelta.gpuResults > 0) return result("completed");
    if (continuationDelta.gpuFailures > 0) return result("failed");
    return result("finished-without-result");
  }
  if (continuationDelta.modalBegins === 0 && active === 0) return result("not-started");
  if (continuationDelta.gpuAttempts === 0) return result("selection-attempt");
  if (phase === 3 || phase === 4) return result("draw-retry");
  if (readbackDelta.submits < continuationDelta.gpuAttempts) return result("readback-submit");
  if (readbackDelta.mapStarts < readbackDelta.submits) return result("map-start");
  if (readbackDelta.mapCompletes < readbackDelta.mapStarts) return result("map-callback");
  if (readbackDelta.validationCompletes < readbackDelta.submits) {
    return result("validation-callback");
  }
  if (readbackDelta.joinCompletes <
      Math.min(readbackDelta.mapCompletes, readbackDelta.validationCompletes)) {
    return result("map-validation-join");
  }
  if (phase === 2) return result("draw-validation");
  if (readbackDelta.ready > continuationDelta.gpuResults) return result("selection-consume");
  if (continuationDelta.gpuResults > 0) return result("modal-finish");
  if (phase === 5) return result("ticket-publication");
  if (phase === 7 || continuationDelta.gpuFailures > 0) return result("failed");
  return result("active-unknown");
};

if (process.env.BW_P0_READBACK_CLASSIFIER_SELFCHECK === "1") {
  const snapshot = (selectionReadback = {}, selectionContinuation = {}) => ({
    selectionReadback: {
      submits: 0,
      mapStarts: 0,
      mapCompletes: 0,
      validationCompletes: 0,
      joinCompletes: 0,
      ready: 0,
      ...selectionReadback,
    },
    selectionContinuation: {
      gpuPhase: 0,
      gpuAttempts: 0,
      gpuResults: 0,
      gpuFailures: 0,
      modalBegins: 0,
      modalFinishes: 0,
      active: 0,
      queuedEvents: 0,
      ...selectionContinuation,
    },
  });
  const baseline = snapshot();
  const fixtures = [
    ["not-started", baseline],
    ["selection-attempt", snapshot({}, {gpuPhase: 1, modalBegins: 1, active: 1})],
    ["draw-retry", snapshot({}, {
      gpuPhase: 3, gpuAttempts: 1, modalBegins: 1, active: 1,
    })],
    ["map-start", snapshot({submits: 1}, {
      gpuPhase: 5, gpuAttempts: 1, modalBegins: 1, active: 1,
    })],
    ["map-callback", snapshot({submits: 1, mapStarts: 1, validationCompletes: 1}, {
      gpuPhase: 5, gpuAttempts: 1, modalBegins: 1, active: 1,
    })],
    ["validation-callback", snapshot({
      submits: 1, mapStarts: 1, mapCompletes: 1,
    }, {gpuPhase: 2, gpuAttempts: 1, modalBegins: 1, active: 1})],
    ["map-validation-join", snapshot({
      submits: 1, mapStarts: 1, mapCompletes: 1, validationCompletes: 1,
    }, {gpuPhase: 5, gpuAttempts: 1, modalBegins: 1, active: 1})],
    ["draw-validation", snapshot({
      submits: 2,
      mapStarts: 2,
      mapCompletes: 2,
      validationCompletes: 2,
      joinCompletes: 2,
    }, {gpuPhase: 2, gpuAttempts: 2, modalBegins: 1, active: 1})],
    ["completed", snapshot({
      submits: 5,
      mapStarts: 5,
      mapCompletes: 5,
      validationCompletes: 5,
      joinCompletes: 5,
      ready: 3,
    }, {
      gpuPhase: 0,
      gpuAttempts: 5,
      gpuResults: 3,
      modalBegins: 1,
      modalFinishes: 1,
      active: 0,
    })],
  ];
  for (const [expected, current] of fixtures) {
    const actual = classifySelectionReadbackBoundary(baseline, current).boundary;
    if (actual !== expected) {
      throw new Error(`selection readback classifier expected ${expected}, got ${actual}`);
    }
  }
  if (fixtures.length !== 9) throw new Error("selection readback classifier fixture count changed");
  process.stdout.write("P0J_SELECTION_READBACK_BOUNDARY_SELFCHECK_PASS cases=9\n");
  process.exit(0);
}

const browser = await chromium.launch({
  headless: false,
  args: [
    "--enable-unsafe-webgpu",
    ...(ozonePlatform ? [`--ozone-platform=${ozonePlatform}`] : []),
    ...(hardwareDiagnostic ? ["--use-angle=metal"] : [
      "--use-webgpu-adapter=swiftshader",
      "--use-gpu-in-tests",
    ]),
  ],
});
const stackIdentity = {
  platform: process.platform,
  nodeVersion: process.version,
  playwrightVersion: require("playwright/package.json").version,
  pngjsVersion: require("pngjs/package.json").version,
  chromiumVersion: browser.version(),
};
if (hardwareDiagnostic) {
  const differences = Object.entries(REQUIRED_HARDWARE_STACK)
    .filter(([field, value]) => stackIdentity[field] !== value)
    .map(([field, value]) => `${field}=${stackIdentity[field]} expected=${value}`);
  if (differences.length !== 0) {
    await browser.close();
    throw new Error(`rapid input hardware stack rejected: ${differences.join(", ")}`);
  }
}

let failureContext = null;
try {
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720},
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const consoleLines = [];
  const pageErrors = [];
  const lifecycle = [];
  const nativeInputs = [];
  const nativeStates = [];
  const drainTimelines = Object.create(null);
  failureContext = {consoleLines, pageErrors, lifecycle, nativeInputs, nativeStates, drainTimelines};
  await page.addInitScript(() => {
    const events = [];
    for (const type of [
      "pointerdown", "pointerup", "mousedown", "mouseup", "mousemove", "keydown", "keyup",
    ]) {
      window.addEventListener(type, (event) => events.push({
        sequence: events.length + 1,
        type,
        trusted: event.isTrusted === true,
        button: Number.isInteger(event.button) ? event.button : null,
        buttons: Number.isInteger(event.buttons) ? event.buttons : null,
        code: event.code || null,
        key: event.key || null,
        altKey: event.altKey === true,
        ctrlKey: event.ctrlKey === true,
        shiftKey: event.shiftKey === true,
        x: Number.isFinite(event.clientX) ? event.clientX : null,
        y: Number.isFinite(event.clientY) ? event.clientY : null,
        timeStamp: event.timeStamp,
      }), true);
    }
    Object.defineProperty(window, "__bwP0RapidDomInputs", {
      value: Object.freeze({snapshot: () => events.map((event) => ({...event}))}),
      writable: false,
      configurable: false,
    });
  });
  await page.addInitScript((monitor) => { window.__BW_PYEXPR = monitor; }, PY_MONITOR);
  page.on("console", (message) => {
    const line = message.text();
    consoleLines.push(line);
    const inputMatch = /^P0R_INPUT (\{.*\})$/.exec(line);
    if (inputMatch) nativeInputs.push(JSON.parse(inputMatch[1]));
    const stateMatch = /^P0R_STATE (\{.*\})$/.exec(line);
    if (stateMatch) nativeStates.push(JSON.parse(stateMatch[1]));
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("close", () => lifecycle.push("page-close"));
  page.on("crash", () => lifecycle.push("page-crash"));
  context.on("close", () => lifecycle.push("context-close"));
  await page.goto(
    `http://127.0.0.1:${port}/windowed.html?args=--debug-events&ka_idle=16`,
    {waitUntil: "domcontentloaded"},
  );
  await page.waitForFunction(
    () => document.querySelector("#state")?.dataset.state === "running" &&
      Number(window.__bwModule?._bw_viewport_content_present_count?.()) > 0,
    null,
    {timeout: 180000, polling: 100},
  );
  const adapter = await probeAdapter(page);
  failureContext.adapter = adapter;
  if (hardwareDiagnostic && adapter.status !== "ACCEPTED") {
    throw new Error(`rapid input hardware adapter rejected: ${adapter.reason}`);
  }

  const canvas = page.locator("#canvas");
  await canvas.focus();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(750);
  const monitorDeadline = Date.now() + 10000;
  while (nativeStates.length === 0 && Date.now() < monitorDeadline) {
    await page.waitForTimeout(50);
  }
  if (nativeStates.length === 0) throw new Error("native rapid-input monitor did not start");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas has no bounding box");
  const center = {x: box.x + 500, y: box.y + 330};

  const sample = async (name) => {
    const bytes = await canvas.screenshot();
    const counters = await page.evaluate(() => {
      const module = window.__bwModule;
      const read = (name) => typeof module?.[name] === "function" ? Number(module[name]()) : null;
      const readArg = (name, value) => typeof module?.[name] === "function" ?
        Number(module[name](value)) : null;
      const domInputs = window.__bwP0RapidDomInputs?.snapshot?.() || [];
      return {
        ticks: read("_bw_wm_tick_count"),
        presents: read("_bw_present_count"),
        retries: read("_bw_redraw_retry_count"),
        drawDrops: read("_bw_redraw_drop_count"),
        selectionDrawValidation: {
          pending: read("_bw_selection_draw_validation_pending_count"),
          failures: read("_bw_selection_draw_validation_failure_count"),
        },
        selectionReadback: {
          submits: read("_bw_exact_buffer_readback_submit_count"),
          mapStarts: read("_bw_exact_buffer_readback_map_start_count"),
          mapCompletes: read("_bw_exact_buffer_readback_map_complete_count"),
          validationCompletes: read("_bw_exact_buffer_readback_validation_complete_count"),
          joinCompletes: read("_bw_exact_buffer_readback_join_complete_count"),
          ready: read("_bw_exact_buffer_readback_ready_count"),
        },
        selectionContinuation: {
          gpuPhase: read("_bw_gpu_select_async_phase"),
          gpuSessions: read("_bw_gpu_select_async_session_count"),
          gpuAttempts: read("_bw_gpu_select_async_attempt_count"),
          gpuResults: read("_bw_gpu_select_async_result_count"),
          gpuReplays: read("_bw_gpu_select_async_replay_count"),
          gpuFailures: read("_bw_gpu_select_async_failure_count"),
          modalBegins: read("_bw_view3d_select_continuation_begin_count"),
          modalFinishes: read("_bw_view3d_select_continuation_finish_count"),
          replayedEvents: read("_bw_view3d_select_replayed_event_count"),
          active: read("_bw_view3d_select_continuation_active"),
          queuedEvents: read("_bw_view3d_select_queued_event_count"),
          timerTicks: read("_bw_view3d_select_modal_tick_count"),
          gpuStatus: read("_bw_view3d_select_gpu_status"),
          queryStatus: read("_bw_view3d_select_query_status"),
          combinedStatus: read("_bw_view3d_select_combined_status"),
        },
        selectionSync: {
          syncLoops: read("_bw_view3d_select_sync_loop_count"),
          completedLoops: read("_bw_view3d_select_sync_complete_count"),
          syncStage: read("_bw_view3d_select_sync_stage"),
        },
        selectionShader: {
          compileKind: read("_bw_select_shader_compile_kind"),
          compileStage: read("_bw_select_shader_compile_stage"),
        },
        inputRedraw: {
          published: read("_bw_input_redraw_retry_count"),
          terminal: read("_bw_input_redraw_terminal_count"),
          admitted: read("_bw_input_redraw_admitted_count"),
          dispatched: read("_bw_input_redraw_dispatched_count"),
          presented: read("_bw_input_redraw_presented_count"),
          contentPresented: read("_bw_input_redraw_content_presented_count"),
          episode: read("_bw_redraw_episode_count"),
        },
        suppressed: read("_bw_present_suppressed_count"),
        replays: read("_bw_present_replay_count"),
        pointerLock: window.__bwPointerLockBridge?.snapshot?.() || null,
        ghostWindow: {
          browserFocusActive: read("_bw_browser_focus_active"),
          pointerLockState: read("_bw_pointer_lock_state"),
          pointerLockRequestedMode: read("_bw_pointer_lock_requested_mode"),
          cursorGrabMode: read("_bw_cursor_grab_mode"),
        },
        activeElement: document.activeElement?.id || document.activeElement?.tagName || null,
        ghostInput: {
          leftPresses: readArg("_bw_input_button_press_count", 0),
          leftReleases: readArg("_bw_input_button_release_count", 0),
          middlePresses: readArg("_bw_input_button_press_count", 1),
          middleReleases: readArg("_bw_input_button_release_count", 1),
          keyPresses: read("_bw_input_key_press_count"),
          keyReleases: read("_bw_input_key_release_count"),
          heldMask: read("_bw_input_button_mask"),
          cursorMoves: read("_bw_input_cursor_count"),
        },
        wmInput: {
          wmLeftPresses: readArg("_bw_input_button_wm_press_count", 0),
          wmLeftReleases: readArg("_bw_input_button_wm_release_count", 0),
          wmMiddlePresses: readArg("_bw_input_button_wm_press_count", 1),
          wmMiddleReleases: readArg("_bw_input_button_wm_release_count", 1),
          wmKeyPresses: read("_bw_input_key_wm_press_count"),
          wmKeyReleases: read("_bw_input_key_wm_release_count"),
          wmHeldMask: read("_bw_input_button_wm_mask"),
          wmCursorMoves: read("_bw_input_cursor_wm_count"),
        },
        view3dRotate: {
          invokes: read("_bw_view3d_rotate_invoke_count"),
          confirms: read("_bw_view3d_rotate_confirm_count"),
          cancels: read("_bw_view3d_rotate_cancel_count"),
          terminals: read("_bw_view3d_rotate_terminal_count"),
          active: read("_bw_view3d_rotate_active_count"),
        },
        domInputSequence: domInputs.at(-1)?.sequence || 0,
        domInputTail: domInputs.slice(-16),
      };
    });
    const nativeState = nativeStates.at(-1) || null;
    const result = {
      name,
      sha256: sha256(bytes),
      ...counters,
      nativeInputSequence: nativeInputs.at(-1)?.sequence || 0,
      nativeStateSequence: nativeState?.sequence || 0,
      nativeState: nativeState ? {...nativeState} : null,
      nativeModalOperators: nativeState?.modal_operators || [],
      nativeViewRotation: nativeState?.view_rotation || null,
    };
    failureContext.lastSample = result;
    return result;
  };
  const ghostInputDeliveryComplete = (current, baseline, expected) =>
    current.ghostInput.leftPresses >= baseline.leftPresses + expected.left &&
    current.ghostInput.leftReleases >= baseline.leftReleases + expected.left &&
    current.ghostInput.middlePresses >= baseline.middlePresses + expected.middle &&
    current.ghostInput.middleReleases >= baseline.middleReleases + expected.middle &&
    current.ghostInput.keyPresses >= baseline.keyPresses + expected.keys &&
    current.ghostInput.keyReleases >= baseline.keyReleases + expected.keys &&
    current.ghostInput.cursorMoves > baseline.cursorMoves &&
    (current.ghostInput.heldMask & 0x3) === 0;
  const wmInputDeliveryComplete = (current, baseline, expected) =>
    current.wmInput.wmLeftPresses >= baseline.wmLeftPresses + expected.left &&
    current.wmInput.wmLeftReleases >= baseline.wmLeftReleases + expected.left &&
    current.wmInput.wmMiddlePresses >= baseline.wmMiddlePresses + expected.middle &&
    current.wmInput.wmMiddleReleases >= baseline.wmMiddleReleases + expected.middle &&
    current.wmInput.wmKeyPresses >= baseline.wmKeyPresses + expected.keys &&
    current.wmInput.wmKeyReleases >= baseline.wmKeyReleases + expected.keys &&
    current.wmInput.wmCursorMoves > baseline.wmCursorMoves &&
    (current.wmInput.wmHeldMask & 0x3) === 0;
  const view3dRotateRetired = (current, baseline, expected) =>
    current.view3dRotate.invokes >= baseline.view3dRotate.invokes + expected &&
    current.view3dRotate.confirms >= baseline.view3dRotate.confirms + expected &&
    current.view3dRotate.terminals >= baseline.view3dRotate.terminals + expected &&
    current.view3dRotate.active === baseline.view3dRotate.active;
  const stateArraysEqual = (left, right) =>
    Array.isArray(left) && Array.isArray(right) && left.length === right.length &&
    left.every((value, index) => Number.isFinite(value) && Number.isFinite(right[index]) &&
      Math.abs(value - right[index]) <= 0.00001);
  const stateArrayChanged = (left, right) => !stateArraysEqual(left, right);
  const nativeCubeSelected = (current) =>
    current.nativeState?.active_object === "Cube" &&
    current.nativeState?.selected_count === 1;
  const nativeCubePagePoint = (current, canvasBox) => {
    const point = current.nativeState?.cube_window_xy;
    if (!Array.isArray(point) || point.length !== 2 ||
        !point.every((value) => Number.isFinite(value))) {
      throw new Error("Blender did not publish a projected Cube selection point");
    }
    const pagePoint = {
      x: canvasBox.x + point[0],
      y: canvasBox.y + canvasBox.height - point[1],
    };
    if (pagePoint.x < canvasBox.x || pagePoint.x >= canvasBox.x + canvasBox.width ||
        pagePoint.y < canvasBox.y || pagePoint.y >= canvasBox.y + canvasBox.height) {
      throw new Error(`projected Cube selection point is outside canvas: ${JSON.stringify(pagePoint)}`);
    }
    return pagePoint;
  };
  const nativeViewChanged = (current, baseline) =>
    stateArrayChanged(current.nativeState?.view_rotation, baseline.nativeState?.view_rotation);
  const selectionContinuationRetired = (current, baseline) =>
    current.selectionContinuation.modalBegins > baseline.selectionContinuation.modalBegins &&
    current.selectionContinuation.modalFinishes > baseline.selectionContinuation.modalFinishes &&
    current.selectionContinuation.active === 0 &&
    current.selectionContinuation.queuedEvents === 0 &&
    current.selectionContinuation.gpuFailures === baseline.selectionContinuation.gpuFailures;
  const nativeSelectionReplayComplete = (current, baseline) =>
    current.selectionSync.syncLoops > baseline.selectionSync.syncLoops &&
    current.selectionSync.completedLoops > baseline.selectionSync.completedLoops &&
    current.nativeStateSequence > baseline.nativeStateSequence &&
    baseline.nativeState?.selected_count === 0 && nativeCubeSelected(current) &&
    nativeViewChanged(current, baseline) &&
    stateArrayChanged(current.nativeState?.location, baseline.nativeState?.location);
  const hardwareActionStateComplete = (current, baseline) =>
    current.nativeStateSequence > baseline.nativeStateSequence &&
    nativeCubeSelected(current) && nativeViewChanged(current, baseline) &&
    stateArrayChanged(current.nativeState?.location, baseline.nativeState?.location);
  const hardwareRecoveryStateComplete = (current, baseline) =>
    current.nativeStateSequence > baseline.nativeStateSequence &&
    nativeCubeSelected(current) && nativeViewChanged(current, baseline) &&
    stateArraysEqual(current.nativeState?.location, baseline.nativeState?.location);
  const hardwareIsolatedOrbitStateComplete = (current, baseline) =>
    current.nativeStateSequence > baseline.nativeStateSequence &&
    current.nativeState?.selected_count === baseline.nativeState?.selected_count &&
    nativeViewChanged(current, baseline) &&
    JSON.stringify(current.nativeState?.location) === JSON.stringify(baseline.nativeState?.location);
  const ghostWindowSettled = (current) =>
    current.ghostWindow.browserFocusActive === 1 &&
    current.ghostWindow.pointerLockState === 0 &&
    current.ghostWindow.pointerLockRequestedMode === 0 &&
    current.ghostWindow.cursorGrabMode === 0;
  const waitForActionDrain = async (
    name, baseline, counterBaseline, rotateBaseline, expectedRotates,
    nativeDeliveryComplete, nativeStateComplete, timeoutMs = 12000,
    requireNativeState = hardwareDiagnostic,
    allowSelectionModal = false,
    requireInputReceipt = true,
  ) => {
    const started = Date.now();
    drainTimelines[name] = [];
    while (Date.now() - started <= timeoutMs) {
      await page.waitForTimeout(250);
      const current = await sample(name);
      drainTimelines[name].push({
        elapsedMs: Date.now() - started,
        sha256: current.sha256,
        ticks: current.ticks,
        presents: current.presents,
        retries: current.retries,
        drawDrops: current.drawDrops,
        selectionDrawValidation: {...current.selectionDrawValidation},
        selectionReadback: {...current.selectionReadback},
        selectionReadbackBoundary: classifySelectionReadbackBoundary(counterBaseline, current),
        selectionContinuation: {...current.selectionContinuation},
        selectionSync: {...current.selectionSync},
        selectionShader: {...current.selectionShader},
        inputRedraw: {...current.inputRedraw},
        ghostInput: {...current.ghostInput},
        wmInput: {...current.wmInput},
        view3dRotate: {...current.view3dRotate},
        ghostWindow: {...current.ghostWindow},
        nativeInputSequence: current.nativeInputSequence,
        nativeStateSequence: current.nativeStateSequence,
        nativeState: current.nativeState ? {...current.nativeState} : null,
        nativeModalOperators: [...current.nativeModalOperators],
      });
      if ((stateOnlyDiagnostic || current.sha256 !== baseline) &&
          current.ticks > counterBaseline.ticks &&
          current.presents > counterBaseline.presents &&
          (!requireInputReceipt ||
            (current.inputRedraw.terminal > counterBaseline.inputRedraw.terminal &&
             current.inputRedraw.admitted >= current.inputRedraw.terminal &&
             current.inputRedraw.dispatched >= current.inputRedraw.terminal &&
             current.inputRedraw.presented >= current.inputRedraw.terminal &&
             current.inputRedraw.contentPresented >= current.inputRedraw.terminal &&
             current.inputRedraw.episode === counterBaseline.inputRedraw.episode)) &&
          nativeDeliveryComplete(current) &&
          view3dRotateRetired(current, rotateBaseline, expectedRotates) &&
          ghostWindowSettled(current) &&
          (!requireNativeState || nativeStateComplete(current)) &&
          current.nativeModalOperators.every((operator) =>
            operator === "WM_OT_bwp0r_input_probe" ||
            (allowSelectionModal && operator === "VIEW3D_OT_select"))) {
        return {...current, settleMs: Date.now() - started};
      }
    }
    throw new Error(
      `${name} did not drain terminal native input plus ${stateOnlyDiagnostic ? "state" : "pixels"}/WM/present within ${timeoutMs}ms`,
    );
  };
  const steps = [];
  failureContext.steps = steps;
  const splashDismissed = await sample("splash-dismissed");
  if (![splashDismissed.drawDrops,
        splashDismissed.selectionDrawValidation.pending,
        splashDismissed.selectionDrawValidation.failures].every(Number.isFinite) ||
      !Object.values(splashDismissed.selectionReadback).every(Number.isFinite) ||
      !Object.values(splashDismissed.selectionContinuation).every(Number.isFinite) ||
      !Number.isFinite(splashDismissed.selectionSync.syncLoops) ||
      !Number.isFinite(splashDismissed.selectionSync.completedLoops) ||
      !Number.isFinite(splashDismissed.selectionSync.syncStage) ||
      !Number.isFinite(splashDismissed.selectionShader.compileKind) ||
      !Number.isFinite(splashDismissed.selectionShader.compileStage)) {
    throw new Error("selection draw/drop diagnostics are unavailable in the served product");
  }
  steps.push(splashDismissed);
  const settle = async (name) => {
    await page.waitForTimeout(sampleCadenceMs);
    steps.push(await sample(name));
  };

  await page.mouse.move(center.x, center.y);
  for (const [key, name] of [
    ["Numpad1", "front"],
    ["Numpad3", "right"],
    ["Numpad7", "top"],
    ["Numpad0", "camera"],
    ["Numpad4", "camera-orbit-cancelled"],
  ]) {
    await page.keyboard.press(key);
    await settle(name);
  }
  await page.keyboard.press("a");
  await settle("select-all");
  await page.keyboard.press("Alt+a");
  await settle("deselect-all");

  const isolatedOrbitBaseline = steps.at(-1);
  const isolatedOrbitInputBaseline = isolatedOrbitBaseline.ghostInput;
  const isolatedOrbitWmInputBaseline = isolatedOrbitBaseline.wmInput;
  const rapidInputBaseline = steps.at(-1).ghostInput;
  const rapidWmInputBaseline = steps.at(-1).wmInput;
  await page.mouse.down({button: "middle"});
  await page.mouse.move(center.x + 34, center.y + 20, {steps: 8});
  await page.mouse.up({button: "middle"});
  await settle("orbit-before-click");

  const orbitBeforeClick = steps.find((step) => step.name === "orbit-before-click");
  const drainTimeoutMs = hardwareDiagnostic ? 12000 : 30000;
  let actionDrain;
  let selectionDrain = null;
  let selectionPoint = null;
  let selectionNavigationPassthroughRequired = null;
  let selectionNavigationPassedThrough = null;
  let recoveryOrbit;
  let nativeStateContract;
  let retainedActionFramesEqual = null;
  if (sparseDiagnostic) {
    actionDrain = await waitForActionDrain(
      "isolated-orbit-drain",
      isolatedOrbitBaseline.sha256,
      isolatedOrbitBaseline,
      isolatedOrbitBaseline,
      1,
      (current) => ghostInputDeliveryComplete(
        current, isolatedOrbitInputBaseline, {left: 0, middle: 1, keys: 0}) &&
        wmInputDeliveryComplete(
          current, isolatedOrbitWmInputBaseline, {left: 0, middle: 1, keys: 0}),
      (current) => hardwareIsolatedOrbitStateComplete(current, isolatedOrbitBaseline),
      drainTimeoutMs,
    );
    steps.push(actionDrain);

    /* The filed freeze changes the first orbit, then becomes permanent when the following click
     * starts VIEW3D_OT_select. Reproduce its sparse tail instead of avoiding it: after one real
     * 650 ms pause, send exactly one orbit while the asynchronous selection continuation still
     * owns the modal stack. Navigation must retire directly instead of waiting in the selection
     * FIFO and replaying after the pick settles. */
    const selectionBaseline = actionDrain;
    const selectionInputBaseline = selectionBaseline.ghostInput;
    const selectionWmInputBaseline = selectionBaseline.wmInput;
    selectionPoint = nativeCubePagePoint(selectionBaseline, box);
    await page.mouse.move(selectionPoint.x, selectionPoint.y);
    await page.mouse.click(selectionPoint.x, selectionPoint.y);
    await page.waitForTimeout(Math.max(sampleCadenceMs, 650));
    const selectionPendingWindow = await sample("isolated-selection-pending");
    steps.push(selectionPendingWindow);
    selectionNavigationPassthroughRequired =
      selectionPendingWindow.selectionContinuation.gpuSessions >
        selectionBaseline.selectionContinuation.gpuSessions &&
      selectionPendingWindow.selectionContinuation.modalFinishes ===
        selectionBaseline.selectionContinuation.modalFinishes;
    const navigationInputBaseline = selectionPendingWindow.ghostInput;
    const navigationWmInputBaseline = selectionPendingWindow.wmInput;
    await page.mouse.down({button: "middle"});
    await page.mouse.move(center.x - 34, center.y + 16, {steps: 8});
    await page.mouse.up({button: "middle"});
    const selectionNavigationWindow = await waitForActionDrain(
      "isolated-selection-navigation-passthrough",
      selectionBaseline.sha256,
      selectionPendingWindow,
      selectionBaseline,
      1,
      (current) => ghostInputDeliveryComplete(
        current, navigationInputBaseline, {left: 0, middle: 1, keys: 0}) &&
        wmInputDeliveryComplete(
          current, navigationWmInputBaseline, {left: 0, middle: 1, keys: 0}),
      (current) => hardwareIsolatedOrbitStateComplete(current, selectionBaseline),
      drainTimeoutMs,
      true,
      true,
      false,
    );
    steps.push(selectionNavigationWindow);
    selectionNavigationPassthroughRequired =
      selectionNavigationPassthroughRequired ||
      (selectionNavigationWindow.selectionContinuation.modalBegins >
         selectionBaseline.selectionContinuation.modalBegins &&
       selectionNavigationWindow.selectionContinuation.modalFinishes ===
         selectionBaseline.selectionContinuation.modalFinishes &&
       selectionNavigationWindow.selectionContinuation.active === 1);
    selectionNavigationPassedThrough =
      view3dRotateRetired(selectionNavigationWindow, selectionBaseline, 1) &&
      nativeViewChanged(selectionNavigationWindow, selectionBaseline) &&
      selectionNavigationWindow.selectionContinuation.replayedEvents ===
        selectionBaseline.selectionContinuation.replayedEvents;

    /* Match the driver's complete slow/sparse tail. While the selection continuation is still
     * live, G, its pointer motion, and confirmation must retain their original order. Passing all
     * mouse motion through as "navigation" lets the motion overtake the retained G key and turns
     * the replay into a zero-delta transform. */
    await page.keyboard.press("g");
    await page.mouse.move(center.x + 40, center.y - 20, {steps: 8});
    await page.mouse.click(center.x + 40, center.y - 20);
    selectionDrain = await waitForActionDrain(
      "isolated-selection-drain",
      selectionBaseline.sha256,
      selectionBaseline,
      selectionPendingWindow,
      1,
      (current) => ghostInputDeliveryComplete(
        current, selectionInputBaseline, {left: 2, middle: 1, keys: 1}) &&
        wmInputDeliveryComplete(
          current, selectionWmInputBaseline, {left: 2, middle: 1, keys: 1}),
      (current) => nativeSelectionReplayComplete(current, selectionBaseline) &&
        selectionContinuationRetired(current, selectionBaseline) &&
        (!selectionNavigationPassthroughRequired || selectionNavigationPassedThrough),
      drainTimeoutMs,
      true,
    );
    steps.push(selectionDrain);
    recoveryOrbit = selectionNavigationWindow;
    nativeStateContract = {
      enforced: hardwareDiagnostic,
      selectionEnforced: true,
      actionComplete: hardwareIsolatedOrbitStateComplete(actionDrain, isolatedOrbitBaseline),
      selectionComplete: selectionContinuationRetired(selectionDrain, selectionBaseline),
      recoveryComplete: nativeSelectionReplayComplete(selectionDrain, selectionBaseline),
      navigationPassedThrough: selectionNavigationPassedThrough,
    };
  }
  else {
    await page.mouse.click(center.x, center.y);
    await settle("click");
    await page.mouse.move(center.x, center.y);
    await page.mouse.down({button: "middle"});
    await page.mouse.move(center.x - 34, center.y + 16, {steps: 8});
    await page.mouse.up({button: "middle"});
    await settle("orbit-after-click");
    await page.keyboard.press("g");
    await page.mouse.move(center.x + 40, center.y - 20);
    await settle("move-pending");
    await page.mouse.click(center.x + 40, center.y - 20);
    await settle("move-confirmed");

    actionDrain = await waitForActionDrain(
      "action-drain",
      orbitBeforeClick.sha256,
      orbitBeforeClick,
      isolatedOrbitBaseline,
      2,
      (current) => ghostInputDeliveryComplete(
        current, rapidInputBaseline, {left: 2, middle: 2, keys: 1}) &&
        wmInputDeliveryComplete(
          current, rapidWmInputBaseline, {left: 2, middle: 2, keys: 1}),
      (current) => hardwareActionStateComplete(current, orbitBeforeClick),
      drainTimeoutMs,
    );
    steps.push(actionDrain);
    await page.keyboard.press("Escape");
    await page.mouse.move(center.x, center.y);
    await page.waitForTimeout(100);
    const recoveryBaseline = await sample("recovery-baseline");
    const recoveryInputBaseline = recoveryBaseline.ghostInput;
    const recoveryWmInputBaseline = recoveryBaseline.wmInput;
    await page.mouse.down({button: "middle"});
    await page.mouse.move(center.x + 24, center.y - 18, {steps: 8});
    await page.mouse.up({button: "middle"});
    recoveryOrbit = await waitForActionDrain(
      "recovery-orbit",
      recoveryBaseline.sha256,
      recoveryBaseline,
      recoveryBaseline,
      1,
      (current) => ghostInputDeliveryComplete(
        current, recoveryInputBaseline, {left: 0, middle: 1, keys: 0}) &&
        wmInputDeliveryComplete(
          current, recoveryWmInputBaseline, {left: 0, middle: 1, keys: 0}),
      (current) => hardwareRecoveryStateComplete(current, recoveryBaseline),
      drainTimeoutMs,
    );
    steps.push(recoveryOrbit);
    const retained = steps.slice(8, 13).map((step) => step.sha256);
    retainedActionFramesEqual = new Set(retained).size === 1;
    nativeStateContract = {
      enforced: hardwareDiagnostic,
      actionComplete: hardwareActionStateComplete(actionDrain, orbitBeforeClick),
      recoveryComplete: hardwareRecoveryStateComplete(recoveryOrbit, recoveryBaseline),
    };
  }

  const evidence = {
    schema: 2,
    run: hardwareDiagnostic ? runLabel : null,
    capturedAt: new Date().toISOString(),
    source: sourceIdentity,
    stack: stackIdentity,
    productIdentity,
    mode: sparseDiagnostic ? "slow-sparse" : "rapid-burst",
    sampleCadenceMs,
    evidenceClass: hardwareDiagnostic ? "diagnostic-apple" :
      (stateOnlyDiagnostic ? "diagnostic-software-fallback-state-only" :
        "diagnostic-software-fallback"),
    adapter,
    steps,
    retainedActionFramesEqual,
    selectionPoint,
    selectionNavigationPassthroughRequired,
    selectionNavigationPassedThrough,
    actionDrainMs: actionDrain.settleMs,
    selectionDrainMs: selectionDrain?.settleMs ?? null,
    recoveryOrbitMs: recoveryOrbit.settleMs,
    nativeStateContract,
    drainTimelines,
    nativeInputs,
    nativeStates,
    pageErrors,
    lifecycle,
    pointerLockLines: consoleLines.filter((line) => /Pointer Lock|pointerlock/i.test(line)),
    selectionReadbackFailureLines: consoleLines.filter(
      (line) => /WebGPU selection (?:readback failed|continuation canceled)/.test(line)),
    selectionGpuLines: consoleLines.filter(
      (line) => /WGPUWeb-(?:bind-pending|select-)|BW_SHADER_CACHE_RESULT .*select|WebGPU.*pipeline.*rejected/.test(line)),
    wmEventLines: consoleLines.filter((line) => /^wmEvent type:/.test(line)),
    inputRedrawLines: consoleLines.filter((line) => /GHOST-input-redraw/.test(line)),
    eventTail: consoleLines.filter((line) => /ghost_event_proc/.test(line)).slice(-80),
  };
  if (pageErrors.length !== 0 || lifecycle.length !== 0 ||
      evidence.selectionReadbackFailureLines.length !== 0) {
    throw new Error(`rapid input diagnostic has page/lifecycle errors: ${JSON.stringify(evidence)}`);
  }
  if (hardwareDiagnostic) {
    const finalProductIdentity = await inspectProductIdentity(port, expectedWasmOrigSha256);
    if (JSON.stringify(finalProductIdentity) !== JSON.stringify(productIdentity)) {
      throw new Error("hardware diagnostic product changed during the run");
    }
  }
  const evidenceText = `${JSON.stringify(evidence, null, 2)}\n`;
  if (outputPath) {
    await writeFile(outputPath, evidenceText, {encoding: "utf8", flag: "wx"});
  }
  else {
    process.stdout.write(evidenceText);
  }
}
catch (error) {
  const retained = sparseDiagnostic ? [] :
    (failureContext?.steps || []).slice(8, 13).map((step) => step.sha256);
  process.stderr.write(`${JSON.stringify({
    error: error?.stack || String(error),
    schema: 2,
    run: hardwareDiagnostic ? runLabel : null,
    capturedAt: new Date().toISOString(),
    source: sourceIdentity,
    stack: stackIdentity,
    productIdentity,
    mode: sparseDiagnostic ? "slow-sparse" : "rapid-burst",
    sampleCadenceMs,
    adapter: failureContext?.adapter || null,
    steps: failureContext?.steps || [],
    lastSample: failureContext?.lastSample || null,
    nativeInputs: failureContext?.nativeInputs || [],
    nativeStates: failureContext?.nativeStates || [],
    retainedActionFramesEqual: sparseDiagnostic ? null :
      (retained.length === 5 ? new Set(retained).size === 1 : null),
    drainTimelines: failureContext?.drainTimelines || {},
    pageErrors: failureContext?.pageErrors || [],
    lifecycle: failureContext?.lifecycle || [],
    pointerLockLines: (failureContext?.consoleLines || [])
      .filter((line) => /Pointer Lock|pointerlock/i.test(line)),
    selectionReadbackFailureLines: (failureContext?.consoleLines || [])
      .filter((line) => /WebGPU selection (?:readback failed|continuation canceled)/.test(line)),
    selectionGpuLines: (failureContext?.consoleLines || [])
      .filter((line) => /WGPUWeb-(?:bind-pending|select-)|BW_SHADER_CACHE_RESULT .*select|WebGPU.*pipeline.*rejected/.test(line)),
    wmEventLines: (failureContext?.consoleLines || [])
      .filter((line) => /^wmEvent type:/.test(line)),
    inputRedrawLines: (failureContext?.consoleLines || [])
      .filter((line) => /GHOST-input-redraw/.test(line)),
    eventTail: (failureContext?.consoleLines || [])
      .filter((line) => /ghost_event_proc/.test(line)).slice(-80),
    consoleTail: (failureContext?.consoleLines || []).slice(-120),
  }, null, 2)}\n`);
  throw error;
}
finally {
  await browser.close();
}
