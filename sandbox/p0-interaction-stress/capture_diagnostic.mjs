// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Diagnostic-only fallback-adapter capture for P0-I. This binds no hardware receipt.

import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const outDir = resolve(process.env.BW_P0I_STRESS_OUT ||
  resolve(root, "sandbox/p0-interaction-stress/artifacts"));
mkdirSync(outDir, { recursive: true });

const moduleRoots = [
  process.env.BW_NODE_MODULES,
  resolve(root, ".m4-node/node_modules"),
].filter(Boolean);
let chromium = null;
let PNG = null;
for (const candidate of moduleRoots) {
  try {
    const require = createRequire(resolve(candidate, "package.json"));
    chromium = require("playwright").chromium;
    PNG = require("pngjs").PNG;
    break;
  }
  catch (_) {}
}
if (!chromium) {
  throw new Error(`playwright is unavailable; checked ${moduleRoots.join(", ")}`);
}

const port = Number(process.argv[2] || 8123);
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

const browser = await chromium.launch({
  headless: false,
  args: [
    "--enable-unsafe-webgpu",
    "--use-webgpu-adapter=swiftshader",
    "--use-gpu-in-tests",
    ...(process.platform === "linux" && process.env.DISPLAY ? ["--ozone-platform=x11"] : []),
  ],
});

let page = null;
try {
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

  await page.goto(`http://127.0.0.1:${port}/windowed.html?gate=1280x720`, {
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

  const capture = async (name, metadata = {}) => {
    const buffer = await canvas.screenshot({path: resolve(outDir, `${name}.png`)});
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

  /* Return to Layout, then distinguish a legitimately off-screen Cube from a dropped mesh draw.
   * NumpadDecimal is Blender's stock Frame Selected command and does not mutate scene data. */
  await waitForState((state) => state.workspace === "Layout" && state.view,
    "return to Layout", 10000);
  await page.waitForTimeout(700);
  await capture("60-layout-return");
  const center = viewCenter();
  await page.mouse.move(center.x, center.y);
  const frameSelectedStart = latestState()?.sequence || 0;
  const distanceBeforeFrameSelected = latestState()?.view_distance;
  await page.keyboard.press("NumpadDecimal");
  await waitForState((state) => state.sequence > frameSelectedStart &&
    state.workspace === "Layout" && state.view_distance < distanceBeforeFrameSelected / 2,
  "Frame Selected state", 10000);
  await page.waitForTimeout(500);
  await capture("61a-frame-selected-500ms");
  await page.waitForTimeout(2500);
  await capture("61b-frame-selected-3s");
  await page.waitForTimeout(3000);
  await capture("61c-frame-selected-6s");
  /* Repeat the same operator without changing its target. If this alone makes the first camera
   * state visible, the preceding six-second frame was stale rather than legitimately different. */
  await page.keyboard.press("NumpadDecimal");
  await page.waitForTimeout(1000);
  await capture("62-frame-selected-retrigger");
  await middleDrag(34, 20);
  await capture("63-final-orbit");

  const hardCompletenessWarnings = consoleLines.filter((line) =>
    /assembled group-0 resources do not match surviving WGSL bindings/i.test(line));
  const relevantWarnings = consoleLines.filter((line) =>
    /WGPUShader|WebGPU|reject|validation|device lost|Pointer Lock/i.test(line));
  const diagnostic = {
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
    hardCompletenessWarnings,
    relevantWarnings: relevantWarnings.slice(-300),
    lifecycleEvents,
    pageErrors,
  };
  writeFileSync(resolve(outDir, "diagnostic.json"), `${JSON.stringify(diagnostic, null, 2)}\n`);
  console.log(`P0S_DIAGNOSTIC_DONE steps=${steps.length} states=${states.length} ` +
    `hard_warnings=${hardCompletenessWarnings.length} page_errors=${pageErrors.length} ` +
    `presents=${diagnostic.product.presents}`);
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
  writeFileSync(resolve(outDir, "diagnostic-failure.json"), `${JSON.stringify(failure, null, 2)}\n`);
  if (page) {
    await page.screenshot({path: resolve(outDir, "diagnostic-failure.png")}).catch(() => {});
  }
  throw error;
}
finally {
  await browser.close();
}
