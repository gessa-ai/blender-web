// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

import {createHash} from "node:crypto";
import {createRequire} from "node:module";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const moduleRoot = process.env.BW_NODE_MODULES || resolve(root, ".m4-node/node_modules");
const {chromium} = createRequire(resolve(moduleRoot, "package.json"))("playwright");
const port = Number(process.argv[2] || 8123);
const hardwareDiagnostic = process.env.BW_P0_RAPID_HARDWARE === "1";
const SOFTWARE_ADAPTER_TOKENS = Object.freeze([
  "swiftshader", "llvmpipe", "lavapipe", "softpipe", "software rasterizer",
  "microsoft basic render", "warp",
]);
const PY_MONITOR = String.raw`
import bpy,json,os,time
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
    space=area.spaces.active if area else None
    rv3d=space.region_3d if space else None
    state={
      "modal_operators":[operator.bl_idname for operator in window.modal_operators],
      "selected_count":len(bpy.context.selected_objects),
      "active_object":bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
      "location":_bwp0r_round(obj.location) if obj else None,
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

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
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
const browser = await chromium.launch({
  headless: false,
  args: [
    "--enable-unsafe-webgpu",
    ...(hardwareDiagnostic ? ["--use-angle=metal"] : [
      "--use-webgpu-adapter=swiftshader",
      "--use-gpu-in-tests",
    ]),
  ],
});

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
  failureContext = {consoleLines, pageErrors, lifecycle, nativeInputs, nativeStates};
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
        inputRedraw: {
          published: read("_bw_input_redraw_retry_count"),
          terminal: read("_bw_input_redraw_terminal_count"),
          admitted: read("_bw_input_redraw_admitted_count"),
          episode: read("_bw_redraw_episode_count"),
        },
        suppressed: read("_bw_present_suppressed_count"),
        replays: read("_bw_present_replay_count"),
        pointerLock: window.__bwPointerLockBridge?.snapshot?.() || null,
        activeElement: document.activeElement?.id || document.activeElement?.tagName || null,
        ghostInput: {
          leftPresses: readArg("_bw_input_button_press_count", 0),
          leftReleases: readArg("_bw_input_button_release_count", 0),
          middlePresses: readArg("_bw_input_button_press_count", 1),
          middleReleases: readArg("_bw_input_button_release_count", 1),
          keyPresses: read("_bw_input_key_press_count"),
          keyReleases: read("_bw_input_key_release_count"),
          heldMask: read("_bw_input_button_mask"),
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
    (current.ghostInput.heldMask & 0x3) === 0;
  const stateArraysEqual = (left, right) =>
    Array.isArray(left) && Array.isArray(right) && left.length === right.length &&
    left.every((value, index) => Number.isFinite(value) && Number.isFinite(right[index]) &&
      Math.abs(value - right[index]) <= 0.00001);
  const stateArrayChanged = (left, right) => !stateArraysEqual(left, right);
  const nativeCubeSelected = (current) =>
    current.nativeState?.active_object === "Cube" &&
    current.nativeState?.selected_count === 1;
  const nativeViewChanged = (current, baseline) =>
    stateArrayChanged(current.nativeState?.view_rotation, baseline.nativeState?.view_rotation);
  const hardwareActionStateComplete = (current, baseline) =>
    current.nativeStateSequence > baseline.nativeStateSequence &&
    nativeCubeSelected(current) && nativeViewChanged(current, baseline) &&
    stateArrayChanged(current.nativeState?.location, baseline.nativeState?.location);
  const hardwareRecoveryStateComplete = (current, baseline) =>
    current.nativeStateSequence > baseline.nativeStateSequence &&
    nativeCubeSelected(current) && nativeViewChanged(current, baseline) &&
    stateArraysEqual(current.nativeState?.location, baseline.nativeState?.location);
  const waitForActionDrain = async (
    name, baseline, counterBaseline, nativeDeliveryComplete, nativeStateComplete, timeoutMs = 12000,
  ) => {
    const started = Date.now();
    while (Date.now() - started <= timeoutMs) {
      await page.waitForTimeout(250);
      const current = await sample(name);
      if (current.sha256 !== baseline &&
          current.ticks > counterBaseline.ticks &&
          current.presents > counterBaseline.presents &&
          current.retries > counterBaseline.retries &&
          current.inputRedraw.terminal > counterBaseline.inputRedraw.terminal &&
          current.inputRedraw.admitted >= current.inputRedraw.terminal &&
          current.inputRedraw.episode === counterBaseline.inputRedraw.episode &&
          nativeDeliveryComplete(current) &&
          (!hardwareDiagnostic || nativeStateComplete(current)) &&
          current.nativeModalOperators.every((operator) =>
            operator === "WM_OT_bwp0r_input_probe")) {
        return {...current, settleMs: Date.now() - started};
      }
    }
    throw new Error(
      `${name} did not drain terminal native input plus pixels/WM/present/retry within ${timeoutMs}ms`,
    );
  };
  const steps = [];
  failureContext.steps = steps;
  steps.push(await sample("splash-dismissed"));
  const settle = async (name) => {
    await page.waitForTimeout(350);
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

  const rapidInputBaseline = steps.at(-1).ghostInput;
  await page.mouse.down({button: "middle"});
  await page.mouse.move(center.x + 34, center.y + 20, {steps: 8});
  await page.mouse.up({button: "middle"});
  await settle("orbit-before-click");

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

  const orbitBeforeClick = steps.find((step) => step.name === "orbit-before-click");
  const drainTimeoutMs = hardwareDiagnostic ? 12000 : 30000;
  const actionDrain = await waitForActionDrain(
    "action-drain",
    orbitBeforeClick.sha256,
    orbitBeforeClick,
    (current) => ghostInputDeliveryComplete(
      current, rapidInputBaseline, {left: 2, middle: 2, keys: 1}),
    (current) => hardwareActionStateComplete(current, orbitBeforeClick),
    drainTimeoutMs,
  );
  steps.push(actionDrain);
  await page.keyboard.press("Escape");
  await page.mouse.move(center.x, center.y);
  const recoveryInputBaseline = actionDrain.ghostInput;
  await page.mouse.down({button: "middle"});
  await page.mouse.move(center.x + 24, center.y - 18, {steps: 8});
  await page.mouse.up({button: "middle"});
  steps.push(await waitForActionDrain(
    "recovery-orbit",
    actionDrain.sha256,
    actionDrain,
    (current) => ghostInputDeliveryComplete(
      current, recoveryInputBaseline, {left: 0, middle: 1, keys: 0}),
    (current) => hardwareRecoveryStateComplete(current, actionDrain),
    drainTimeoutMs,
  ));

  const retained = steps.slice(8, 13).map((step) => step.sha256);
  const evidence = {
    schema: 1,
    evidenceClass: hardwareDiagnostic ? "diagnostic-apple" : "diagnostic-software-fallback",
    adapter,
    steps,
    retainedActionFramesEqual: new Set(retained).size === 1,
    actionDrainMs: actionDrain.settleMs,
    recoveryOrbitMs: steps.at(-1).settleMs,
    nativeStateContract: {
      enforced: hardwareDiagnostic,
      actionComplete: hardwareActionStateComplete(actionDrain, orbitBeforeClick),
      recoveryComplete: hardwareRecoveryStateComplete(steps.at(-1), actionDrain),
    },
    nativeInputs,
    nativeStates,
    pageErrors,
    lifecycle,
    pointerLockLines: consoleLines.filter((line) => /Pointer Lock|pointerlock/i.test(line)),
    inputRedrawLines: consoleLines.filter((line) => /GHOST-input-redraw/.test(line)),
    eventTail: consoleLines.filter((line) => /ghost_event_proc/.test(line)).slice(-80),
  };
  if (pageErrors.length !== 0 || lifecycle.length !== 0) {
    throw new Error(`rapid input diagnostic has page/lifecycle errors: ${JSON.stringify(evidence)}`);
  }
  process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
}
catch (error) {
  const retained = (failureContext?.steps || []).slice(8, 13).map((step) => step.sha256);
  process.stderr.write(`${JSON.stringify({
    error: error?.stack || String(error),
    adapter: failureContext?.adapter || null,
    steps: failureContext?.steps || [],
    lastSample: failureContext?.lastSample || null,
    nativeInputs: failureContext?.nativeInputs || [],
    nativeStates: failureContext?.nativeStates || [],
    retainedActionFramesEqual: retained.length === 5 ? new Set(retained).size === 1 : null,
    pageErrors: failureContext?.pageErrors || [],
    lifecycle: failureContext?.lifecycle || [],
    pointerLockLines: (failureContext?.consoleLines || [])
      .filter((line) => /Pointer Lock|pointerlock/i.test(line)),
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
