// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Adapted from sandbox/p0-widget-shadow/capture_diagnostic.mjs.
// Diagnostic-only fallback-adapter capture for P0-I. This binds no receipt.

import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const outDir = resolve(root, "sandbox/p0-modal-extrude/artifacts");
mkdirSync(outDir, { recursive: true });

const moduleRoots = [
  process.env.BW_NODE_MODULES,
  resolve(root, ".m4-node/node_modules"),
].filter(Boolean);
let chromium = null;
for (const candidate of moduleRoots) {
  try {
    chromium = createRequire(resolve(candidate, "package.json"))("playwright").chromium;
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
const states = [];
let nextProbeId = 1;
const probeWorkers = new Map();

const PY_MONITOR = String.raw`
import bpy,json,os,time
_bwp0i={"last":None,"started":time.perf_counter()}
def _bwp0i_poll():
    o=bpy.data.objects.get("Cube")
    if o is None or o.type != 'MESH': return 0.02
    w=bpy.context.window
    if w is None or w.screen is None: return 0.02
    a=next((x for x in w.screen.areas if x.type == 'VIEW_3D'),None)
    if a is None: return 0.02
    r=next((x for x in a.regions if x.type == 'WINDOW'),None)
    if r is None: return 0.02
    s={"mode":o.mode,"verts":len(o.data.vertices),"view":{"x":r.x,"y":r.y,"width":r.width,"height":r.height}}
    key=(s["mode"],s["verts"],s["view"]["x"],s["view"]["y"],s["view"]["width"],s["view"]["height"])
    if key != _bwp0i["last"]:
        _bwp0i["last"]=key
        s["elapsed_ms"]=round((time.perf_counter()-_bwp0i["started"])*1000,3)
        os.write(2,("P0I_STATE "+json.dumps(s,sort_keys=True,separators=(",",":"))+"\n").encode())
    return 0.02
bpy.app.timers.register(_bwp0i_poll,first_interval=0.0,persistent=True)
`.trim();

async function installWorkerProbe(worker) {
  const probeId = nextProbeId++;
  const installed = await worker.evaluate((probeId) => {
    if (self.__bwP0IModalProbeInstalled || typeof GPUDevice === "undefined") {
      return false;
    }
    self.__bwP0IModalProbeInstalled = true;
    self.__bwP0IModalProbeArmed = false;

    const devicePrototype = GPUDevice.prototype;
    const createShaderModule = devicePrototype.createShaderModule;
    const createRenderPipeline = devicePrototype.createRenderPipeline;
    const createBuffer = devicePrototype.createBuffer;
    const createTexture = devicePrototype.createTexture;
    const createBindGroup = devicePrototype.createBindGroup;
    const createCommandEncoder = devicePrototype.createCommandEncoder;
    const createView = GPUTexture.prototype.createView;
    const beginRenderPass = GPUCommandEncoder.prototype.beginRenderPass;
    const finish = GPUCommandEncoder.prototype.finish;
    const setPipeline = GPURenderPassEncoder.prototype.setPipeline;
    const setBindGroup = GPURenderPassEncoder.prototype.setBindGroup;
    const setViewport = GPURenderPassEncoder.prototype.setViewport;
    const setScissorRect = GPURenderPassEncoder.prototype.setScissorRect;
    const draw = GPURenderPassEncoder.prototype.draw;
    const drawIndexed = GPURenderPassEncoder.prototype.drawIndexed;
    const writeBuffer = GPUQueue.prototype.writeBuffer;
    const submit = GPUQueue.prototype.submit;

    const moduleKind = new WeakMap();
    const pipelineKind = new WeakMap();
    const bufferInfo = new WeakMap();
    const textureInfo = new WeakMap();
    const viewInfo = new WeakMap();
    const bindGroupInfo = new WeakMap();
    const encoderInfo = new WeakMap();
    const passInfo = new WeakMap();
    const commandInfo = new WeakMap();
    const lastBufferWrite = new WeakMap();
    let nextBufferId = 1;
    let nextTextureId = 1;
    let traceCount = 0;
    let submitSequence = 0;
    const submitPassTraceCounts = new Map();
    self.__bwP0IModalTraces = [];
    self.__bwP0IQueueSubmits = [];

    const trace = (kind, payload) => {
      if (traceCount >= 2000) {
        return;
      }
      if (kind === "submit-pass") {
        const key = `${self.__bwP0IModalProbePhase || "boot"}/${payload.kind || "unknown"}`;
        const count = submitPassTraceCounts.get(key) || 0;
        if (count >= 160) {
          return;
        }
        submitPassTraceCounts.set(key, count + 1);
      }
      traceCount++;
      const record = {
        probeId,
        phase: self.__bwP0IModalProbePhase || "boot",
        at: Number(performance.now().toFixed(3)),
        ...payload,
      };
      self.__bwP0IModalTraces.push({event: kind, ...record});
      /* One low-volume beacon identifies the canvas-owning WebGPU worker. The detailed
       * per-submit trace remains worker-local so console serialization cannot manufacture
       * the very queue backlog this diagnostic is measuring. */
      if (kind === "shader") {
        console.log(`[P0I] ${kind} ${JSON.stringify(record)}`);
      }
    };

    const classifyModule = (code) => {
      if (code.includes("smoothline") && code.includes("lineWidth") &&
          code.includes("gpu_vert_stride_count_offset")) {
        return "polyline";
      }
      if (code.includes("stipple_start") && code.includes("dash_width")) {
        return "dashed";
      }
      if (code.includes("shadowFalloff") && code.includes("innerMask")) {
        return "widget-shadow";
      }
      if (code.includes("checkerColorAndSize") && code.includes("alpha_discard")) {
        return "widget-base";
      }
      if (code.includes("rect_icon") && code.includes("rect_geom")) {
        return "image-rect";
      }
      if (code.includes("var src: texture_2d") && code.includes("textureLoad(src,")) {
        return "surface-present";
      }
      if (code.includes("discardFac") && code.includes("cornerLen")) {
        return "area-border";
      }
      return null;
    };

    devicePrototype.createShaderModule = function (descriptor) {
      const code = String(descriptor?.code || "");
      const kind = classifyModule(code);
      const module = createShaderModule.call(this, descriptor);
      if (kind) {
        moduleKind.set(module, kind);
        const resources = code.split("\n").filter((line) =>
          /@group|@binding|var<uniform>|lineWidth|viewportSize|dash_width|stipple|shadowFalloff/.test(line));
        trace("shader", {
          kind,
          label: String(descriptor?.label || ""),
          resources: resources.slice(0, 80),
        });
      }
      return module;
    };

    devicePrototype.createRenderPipeline = function (descriptor) {
      const vertexKind = moduleKind.get(descriptor?.vertex?.module) || null;
      const fragmentKind = moduleKind.get(descriptor?.fragment?.module) || null;
      const kind = vertexKind || fragmentKind;
      const pipeline = createRenderPipeline.call(this, descriptor);
      if (kind) {
        pipelineKind.set(pipeline, kind);
        trace("pipeline", {
          kind,
          label: String(descriptor?.label || ""),
          topology: String(descriptor?.primitive?.topology),
        });
      }
      return pipeline;
    };

    devicePrototype.createBuffer = function (descriptor) {
      const buffer = createBuffer.call(this, descriptor);
      bufferInfo.set(buffer, {
        id: nextBufferId++,
        label: String(descriptor?.label || ""),
        size: Number(descriptor?.size || 0),
        usage: Number(descriptor?.usage || 0),
      });
      return buffer;
    };

    devicePrototype.createTexture = function (descriptor) {
      const texture = createTexture.call(this, descriptor);
      const size = descriptor?.size || {};
      textureInfo.set(texture, {
        id: nextTextureId++,
        label: String(descriptor?.label || ""),
        width: Number(size.width ?? size[0] ?? 0),
        height: Number(size.height ?? size[1] ?? 0),
        depth: Number(size.depthOrArrayLayers ?? size[2] ?? 1),
        format: String(descriptor?.format || ""),
        usage: Number(descriptor?.usage || 0),
      });
      return texture;
    };

    GPUTexture.prototype.createView = function (descriptor) {
      const view = createView.call(this, descriptor);
      viewInfo.set(view, textureInfo.get(this) || null);
      return view;
    };

    devicePrototype.createBindGroup = function (descriptor) {
      const group = createBindGroup.call(this, descriptor);
      bindGroupInfo.set(group, Array.from(descriptor?.entries || [], (entry) => ({
        binding: Number(entry.binding),
        bufferObject: entry.resource?.buffer || null,
        buffer: entry.resource?.buffer ? bufferInfo.get(entry.resource.buffer) || null : null,
        offset: Number(entry.resource?.offset || 0),
        size: Number(entry.resource?.size || 0),
        texture: entry.resource ? viewInfo.get(entry.resource) || null : null,
      })));
      return group;
    };

    devicePrototype.createCommandEncoder = function (...args) {
      const encoder = createCommandEncoder.call(this, ...args);
      if (self.__bwP0IModalProbeArmed) {
        encoderInfo.set(encoder, {passes: []});
      }
      return encoder;
    };

    GPUCommandEncoder.prototype.beginRenderPass = function (descriptor) {
      const pass = beginRenderPass.call(this, descriptor);
      const info = {
        label: String(descriptor?.label || ""),
        kind: null,
        bindGroups: [],
        viewport: null,
        scissor: null,
        draws: [],
        attachments: Array.from(descriptor?.colorAttachments || [], (attachment) =>
          attachment?.view ? viewInfo.get(attachment.view) || null : null),
        unresolvedColorAttachment: Array.from(descriptor?.colorAttachments || []).some(
          (attachment) => attachment?.view && !viewInfo.has(attachment.view)),
      };
      const encoder = encoderInfo.get(this);
      if (encoder) {
        passInfo.set(pass, info);
        encoder.passes.push(info);
      }
      return pass;
    };

    GPURenderPassEncoder.prototype.setPipeline = function (pipeline) {
      const info = passInfo.get(this);
      if (info) {
        info.kind = pipelineKind.get(pipeline) || null;
      }
      return setPipeline.call(this, pipeline);
    };

    GPURenderPassEncoder.prototype.setBindGroup = function (index, group, ...rest) {
      const info = passInfo.get(this);
      if (info) {
        info.bindGroups[Number(index)] = bindGroupInfo.get(group) || [];
      }
      return setBindGroup.call(this, index, group, ...rest);
    };

    GPURenderPassEncoder.prototype.setViewport = function (...args) {
      const info = passInfo.get(this);
      if (info) {
        info.viewport = args.map(Number);
      }
      return setViewport.call(this, ...args);
    };

    GPURenderPassEncoder.prototype.setScissorRect = function (...args) {
      const info = passInfo.get(this);
      if (info) {
        info.scissor = args.map(Number);
      }
      return setScissorRect.call(this, ...args);
    };

    GPURenderPassEncoder.prototype.draw = function (...args) {
      const info = passInfo.get(this);
      if (info) {
        info.draws.push({indexed: false, args: args.map(Number)});
      }
      return draw.call(this, ...args);
    };

    GPURenderPassEncoder.prototype.drawIndexed = function (...args) {
      const info = passInfo.get(this);
      if (info) {
        info.draws.push({indexed: true, args: args.map(Number)});
      }
      return drawIndexed.call(this, ...args);
    };

    GPUCommandEncoder.prototype.finish = function (...args) {
      const command = finish.call(this, ...args);
      const info = encoderInfo.get(this);
      if (info) {
        commandInfo.set(command, info);
      }
      return command;
    };

    GPUQueue.prototype.writeBuffer = function (buffer, bufferOffset, data, dataOffset, size) {
      const info = bufferInfo.get(buffer);
      if (self.__bwP0IModalProbeArmed && info && info.size <= 2048) {
        const sourceOffset = Number(dataOffset || 0);
        const sourceSize = Number(size ?? (data.byteLength - sourceOffset));
        const bytes = new Uint8Array(data.buffer, data.byteOffset + sourceOffset, sourceSize);
        lastBufferWrite.set(buffer, new Uint8Array(bytes));
      }
      return writeBuffer.call(this, buffer, bufferOffset, data, dataOffset, size);
    };

    GPUQueue.prototype.submit = function (commands) {
      const sequence = ++submitSequence;
      const targetedKinds = [];
      if (self.__bwP0IModalProbeArmed) {
        for (const command of commands) {
          const info = commandInfo.get(command);
          for (const pass of info?.passes || []) {
            if (!pass.kind && pass.unresolvedColorAttachment && pass.viewport === null &&
                pass.scissor === null && pass.draws.some((item) =>
                  !item.indexed && item.args[0] === 3 && item.args[1] === 1)) {
              pass.kind = "surface-present";
            }
            if (!pass.kind) {
              continue;
            }
            targetedKinds.push(pass.kind);
            const groups = pass.bindGroups.map((entries) => (entries || []).map((entry) => {
              const bytes = entry.bufferObject ? lastBufferWrite.get(entry.bufferObject) : null;
              const floats = bytes ? Array.from(
                new Float32Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 4)),
                (value) => Number.isFinite(value) ? Number(value.toFixed(5)) : String(value),
              ).slice(0, 128) : null;
              const ints = bytes ? Array.from(
                new Int32Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 4)),
              ).slice(0, 128) : null;
              return {
                binding: entry.binding,
                buffer: entry.buffer,
                offset: entry.offset,
                size: entry.size,
                floats,
                ints,
              };
            }));
            trace("submit-pass", {
              submitSequence: sequence,
              kind: pass.kind,
              label: pass.label,
              viewport: pass.viewport,
              scissor: pass.scissor,
              draws: pass.draws,
              groups,
              attachments: pass.attachments,
            });
          }
        }
      }
      if (self.__bwP0IModalProbeArmed && targetedKinds.length > 0) {
        self.__bwP0IQueueSubmits.push({
          probeId,
          phase: self.__bwP0IModalProbePhase || "boot",
          at: Number(performance.now().toFixed(3)),
          sequence,
          commandCount: commands.length,
          targetedKinds,
        });
        /* Preserve both the beginning and the most recent tail of a long modal episode. */
        if (self.__bwP0IQueueSubmits.length > 2000) {
          self.__bwP0IQueueSubmits.splice(500, 1);
        }
      }
      return submit.call(this, commands);
    };
    return true;
  }, probeId);
  if (installed) {
    probeWorkers.set(probeId, worker);
  }
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
  await page.addInitScript((monitor) => { window.__BW_PYEXPR = monitor; }, PY_MONITOR);
  page.on("worker", (worker) => {
    installWorkerProbe(worker).catch((error) => {
      consoleLines.push(`[P0I] worker-probe-error ${error.message}`);
    });
  });
  page.on("console", (message) => {
    const line = message.text();
    consoleLines.push(line);
    const match = /^P0I_STATE (\{.*\})$/.exec(line);
    if (match) {
      states.push(JSON.parse(match[1]));
    }
  });
  page.on("pageerror", (error) => pageErrors.push(`${error.name}: ${error.message}`));

  await page.goto(`http://127.0.0.1:${port}/windowed.html?gate=1280x720`, {
    waitUntil: "domcontentloaded",
    timeout: 180000,
  });
  console.log("P0I_STAGE dom-ready");
  await page.waitForFunction(() => ["running", "error"].includes(
    document.querySelector("#state")?.dataset.state), undefined, {
    timeout: 180000,
    polling: 250,
  });
  const bootState = await page.evaluate(() => document.querySelector("#state")?.dataset.state);
  if (bootState !== "running") {
    throw new Error(`boot failed before running: ${bootState || "absent"}`);
  }
  console.log("P0I_STAGE wm-running");
  await page.waitForFunction(() => document.querySelector("#loader")?.classList.contains("bw-gone"),
    undefined, {timeout: 60000, polling: 250});
  console.log("P0I_STAGE viewport-ready");

  /* The driver repro begins from a settled idle viewport. Let boot's bounded shader-recovery
   * episode drain before arming so its queue tail is not misattributed to modal interaction. */
  await page.waitForTimeout(5000);

  const waitState = async (predicate, label, after = 0) => {
    const deadline = Date.now() + 60000;
    while (Date.now() < deadline) {
      const state = states.slice(after).reverse().find(predicate);
      if (state) return state;
      await page.waitForTimeout(20);
    }
    throw new Error(`timeout waiting for ${label}; states=${JSON.stringify(states)}`);
  };
  const objectReady = await waitState((state) => state.mode === "OBJECT" && state.verts === 8,
    "object ready");

  const canvas = page.locator("#canvas");
  await canvas.focus();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(1000);
  const box = await canvas.boundingBox();
  if (!box) {
    throw new Error("canvas has no bounding box");
  }
  const center = {
    x: box.x + objectReady.view.x + objectReady.view.width / 2,
    y: box.y + box.height - (objectReady.view.y + objectReady.view.height / 2),
  };
  await page.mouse.move(center.x, center.y);

  const polylineTrace = consoleLines.findLast((line) =>
    line.startsWith("[P0I] shader") && line.includes('"kind":"polyline"'));
  const probeMatch = polylineTrace?.match(/"probeId":(\d+)/);
  const gpuWorker = probeMatch ? probeWorkers.get(Number(probeMatch[1])) : null;
  if (!gpuWorker) {
    throw new Error(`WebGPU worker probe is unavailable: ${polylineTrace || "no polyline trace"}`);
  }
  await gpuWorker.evaluate(() => { self.__bwP0IModalProbeArmed = true; });
  console.log(`P0I_STAGE armed-probe-${probeMatch[1]}`);

  const setPhase = async (phase) => {
    await gpuWorker.evaluate((value) => { self.__bwP0IModalProbePhase = value; }, phase);
  };
  await setPhase("enter-edit");
  let stateStart = states.length;
  await page.keyboard.press("Tab");
  await waitState((state) => state.mode === "EDIT", "edit mode", stateStart);
  await page.waitForTimeout(300);
  await canvas.screenshot({path: resolve(outDir, "edit-mode.png")});
  await setPhase("modal-extrude");
  await page.keyboard.press("e");
  await page.mouse.move(center.x + 100, center.y - 110, {steps: 10});
  await page.waitForTimeout(500);
  await canvas.screenshot({path: resolve(outDir, "mid-extrude.png")});
  await setPhase("confirm-extrude");
  stateStart = states.length;
  await page.mouse.down({button: "left"});
  await page.mouse.up({button: "left"});
  await setPhase("settle");
  await page.waitForTimeout(500);
  await canvas.screenshot({path: resolve(outDir, "settled-500ms.png")});
  await page.waitForTimeout(2500);
  await canvas.screenshot({path: resolve(outDir, "settled-3s.png")});
  await page.waitForTimeout(3000);
  await canvas.screenshot({path: resolve(outDir, "settled-6s.png")});

  /* The owner's discovery bar covers the modal family, not only extrusion. Exercise each
   * remaining transform under an explicit axis constraint, capture it, then cancel so only the
   * already-confirmed extrusion survives the diagnostic. */
  const exerciseConstrainedModal = async (phase, operator, axis, dx, dy) => {
    await page.mouse.move(center.x, center.y);
    await setPhase(phase);
    await page.keyboard.press(operator);
    await page.keyboard.press(axis);
    await page.mouse.move(center.x + dx, center.y + dy, {steps: 8});
    await page.waitForTimeout(350);
    await canvas.screenshot({path: resolve(outDir, `${phase}.png`)});
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
  };
  await exerciseConstrainedModal("modal-move", "g", "x", 120, 40);
  await exerciseConstrainedModal("modal-rotate", "r", "z", 90, -80);
  await exerciseConstrainedModal("modal-scale", "s", "x", 110, 30);
  await setPhase("post-modal");

  /* Object-data topology is synchronized only when edit mode exits. Attest the click really
   * confirmed an extrusion after preserving the requested six-second edit-mode settle window. */
  stateStart = states.length;
  await page.keyboard.press("Tab");
  await waitState((state) => state.mode === "OBJECT" && state.verts > 8,
    "confirmed extrusion topology", stateStart);

  const workerTrace = await gpuWorker.evaluate(() => ({
    traces: self.__bwP0IModalTraces || [],
    queueSubmits: self.__bwP0IQueueSubmits || [],
  }));

  const diagnostic = {
    state: await page.evaluate(() => document.querySelector("#state")?.dataset.state || null),
    ticks: await page.evaluate(() => Number(window.__bwModule?._bw_wm_tick_count?.() ?? -1)),
    presents: await page.evaluate(() => Number(window.__bwModule?._bw_present_count?.() ?? -1)),
    p0iLines: consoleLines.filter((line) => line.startsWith("[P0I]")),
    p0iTraces: workerTrace.traces,
    queueSubmits: workerTrace.queueSubmits,
    states,
    relevantWarnings: consoleLines.filter((line) =>
      /polyline|line_dashed|area_borders|bind.group|validation|reject/i.test(line)).slice(-200),
    pageErrors,
  };
  writeFileSync(resolve(outDir, "diagnostic.json"), `${JSON.stringify(diagnostic, null, 2)}\n`);
  console.log(`P0I_DIAGNOSTIC_DONE p0i_lines=${diagnostic.p0iLines.length} ` +
    `page_errors=${pageErrors.length} ticks=${diagnostic.ticks} presents=${diagnostic.presents}`);
}
catch (error) {
  const failure = {
    error: {name: String(error?.name || "Error"), message: String(error?.message || error)},
    pageErrors,
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
