// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const sourcePath = process.argv[2];
if (!sourcePath) {
  throw new Error(
    "usage: node preinit_worker_test.mjs <wgpu-preinit-worker.js> [--selfcheck]",
  );
}
const source = fs.readFileSync(sourcePath, "utf8");
const selfcheck = process.argv.includes("--selfcheck");

const cases = [
  { name: "device", adapterMissing: true, status: 0, device: false },
  { name: "canvas", canvasMissing: true, status: 1, device: true },
  { name: "surface", surfaceMissing: true, status: 2, device: true },
  { name: "configuration_sync_telemetry", configurationError: true, telemetry: "sync",
    status: 3, device: true, presentation: true },
  { name: "configuration_delayed_telemetry", configurationError: true, telemetry: "delayed",
    status: 3, device: true, presentation: true },
  { name: "configuration_omitted_telemetry", configurationError: true, telemetry: "omitted",
    status: 3, device: true, presentation: true },
  { name: "backbuffer_error", backbufferError: true, status: 4, device: true },
  { name: "backbuffer_null", backbufferNull: true, status: 4, device: true },
  { name: "ready", status: 5, device: true, ready: true, presentation: true },
  { name: "fallback_ready", fallback: true, status: 5, device: true, ready: true,
    presentation: true },
  { name: "current_hardware_precedence", infoFallback: false, legacyFallback: true,
    status: 5, device: true, ready: true, presentation: true },
  { name: "current_fallback_precedence", fallback: true, infoFallback: true,
    legacyFallback: false, status: 5, device: true, ready: true, presentation: true },
  { name: "legacy_fallback_ready", fallback: true, omitInfoFallback: true,
    legacyFallback: true, status: 5, device: true, ready: true, presentation: true },
  { name: "legacy_hardware_ready", omitInfoFallback: true, legacyFallback: false,
    status: 5, device: true, ready: true, presentation: true },
  { name: "unknown_status_ready", omitInfoFallback: true,
    status: 5, device: true, ready: true, presentation: true },
  { name: "lost_preentry", lossBeforeEntry: "unknown", status: 4, device: true, lossStatus: 1 },
  { name: "lost_unknown", lossAfterEntry: "unknown", status: 5, device: true, ready: true,
    lossStatus: 1, presentation: true },
  { name: "lost_destroyed", lossAfterEntry: "destroyed", status: 5, device: true, ready: true,
    lossStatus: 2, presentation: true },
  { name: "lost_stale", lossAfterEntry: "destroyed", staleLoss: true, status: 5, device: true,
    ready: true, lossStatus: 0, presentation: true },
];

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function run(test) {
  const moduleState = {};
  const logs = [];
  const glState = { offscreenCanvases: {} };
  let entryCalls = 0;
  let resolveEntry;
  const entryReached = new Promise((resolve) => { resolveEntry = resolve; });
  const entryHandler = (event) => {
    // Emscripten's cmd:2 handler publishes transferred canvases only after the
    // pre-main wrapper forwards the message. The wrapper must therefore consume
    // the transfer payload itself while it is still free to await WebGPU scopes.
    Object.assign(glState.offscreenCanvases, event.data.offscreenCanvases || {});
    entryCalls++;
    resolveEntry();
  };
  let registeredHandler = entryHandler;
  const selfObject = {};
  Object.defineProperty(selfObject, "onmessage", {
    configurable: true,
    get() { return registeredHandler; },
    set(value) { registeredHandler = value; },
  });

  let unconfigureCalls = 0;
  let rejectedBackbufferDestroys = 0;
  let surfaceConfigured = false;
  let telemetryDispatches = 0;
  let presentationSubmits = 0;
  let presentationCompletions = 0;
  let popScopeCalls = 0;
  const uncapturedErrorHandlers = new Set();
  const dispatchConfigurationError = () => {
    telemetryDispatches++;
    for (const handler of uncapturedErrorHandlers) {
      handler({ error: new Error("configuration rejected") });
    }
  };
  const surface = {
    configure() {
      surfaceConfigured = true;
      if (test.configurationError && test.telemetry === "sync") {
        dispatchConfigurationError();
      }
      else if (test.configurationError && test.telemetry === "delayed") {
        setTimeout(dispatchConfigurationError, 20);
      }
    },
    getCurrentTexture() {
      const texture = {
        kind: "surface-texture",
        valid: !test.configurationError,
        createView() { return { kind: "surface-view", texture }; },
      };
      return texture;
    },
    unconfigure() { unconfigureCalls++; },
  };
  const canvas = {
    width: 1280,
    height: 720,
    getContext() { return test.surfaceMissing ? null : surface; },
  };

  const popErrors = [
    test.backbufferError ? new Error("backbuffer rejected") : null, null, null,
    test.configurationError ? new Error("configuration rejected") : null, null, null,
  ];
  let resolveLoss;
  const pendingLoss = new Promise((resolve) => { resolveLoss = resolve; });
  const device = {
    limits: {
      maxStorageTexturesPerShaderStage: 8,
      maxSampledTexturesPerShaderStage: 16,
      maxSamplersPerShaderStage: 16,
      maxStorageBuffersPerShaderStage: 8,
      maxBufferSize: 1 << 20,
      maxStorageBufferBindingSize: 1 << 19,
      maxColorAttachmentBytesPerSample: 32,
      maxComputeWorkgroupStorageSize: 16384,
      maxComputeInvocationsPerWorkgroup: 256,
      maxComputeWorkgroupSizeX: 256,
    },
    lost: test.lossBeforeEntry ?
      Promise.resolve({ reason: test.lossBeforeEntry, message: "lost before entry" }) : pendingLoss,
    addEventListener(type, handler) {
      if (type === "uncapturederror") {
        uncapturedErrorHandlers.add(handler);
      }
    },
    removeEventListener(type, handler) {
      if (type === "uncapturederror") {
        uncapturedErrorHandlers.delete(handler);
      }
    },
    pushErrorScope() {},
    async popErrorScope() {
      popScopeCalls++;
      if (surfaceConfigured && test.fallback) {
        throw new Error("Instance dropped in popErrorScope");
      }
      return popErrors.shift() ?? null;
    },
    createTexture() {
      if (test.backbufferNull) {
        return null;
      }
      return {
        kind: "backbuffer",
        destroy() { rejectedBackbufferDestroys++; },
      };
    },
    createCommandEncoder() {
      let renderView = null;
      let clearValue = null;
      let renderEnded = false;
      return {
        beginRenderPass(descriptor) {
          assert(descriptor.colorAttachments.length === 1,
                 `${test.name}: wrong presentation attachment count`);
          const attachment = descriptor.colorAttachments[0];
          assert(attachment.loadOp === "clear" && attachment.storeOp === "store",
                 `${test.name}: presentation probe does not clear and store`);
          renderView = attachment.view;
          clearValue = attachment.clearValue;
          return { end() { renderEnded = true; } };
        },
        finish() { return { renderView, clearValue, renderEnded }; },
      };
    },
    queue: {
      submit(commands) {
        presentationSubmits++;
        const command = commands[0];
        const texture = command && command.renderView && command.renderView.texture;
        assert(command && command.renderEnded && texture,
               `${test.name}: incomplete presentation-use transaction`);
        assert(command.clearValue.r === 1 && command.clearValue.g === 1 &&
                 command.clearValue.b === 1 && command.clearValue.a === 1,
               `${test.name}: presentation probe must clear opaque white`);
      },
      async onSubmittedWorkDone() { presentationCompletions++; },
    },
  };
  const adapterInfo = {};
  if (!test.omitInfoFallback) {
    adapterInfo.isFallbackAdapter = Object.prototype.hasOwnProperty.call(test, "infoFallback") ?
      test.infoFallback : Boolean(test.fallback);
  }
  const adapter = test.adapterMissing ? null : {
    features: new Set(),
    info: adapterInfo,
    limits: device.limits,
    async requestDevice() { return device; },
  };
  if (adapter && Object.prototype.hasOwnProperty.call(test, "legacyFallback")) {
    adapter.isFallbackAdapter = test.legacyFallback;
  }

  const context = vm.createContext({
    ENVIRONMENT_IS_PTHREAD: true,
    GL: glState,
    GPUTextureUsage: { RENDER_ATTACHMENT: 1, TEXTURE_BINDING: 2, COPY_SRC: 4 },
    Module: moduleState,
    navigator: { gpu: { async requestAdapter() { return adapter; } } },
    postMessage() {},
    self: selfObject,
    setTimeout,
    specialHTMLTargets: {},
    err(message) { logs.push(String(message)); },
  });
  new vm.Script(source, { filename: sourcePath }).runInContext(context);
  registeredHandler({
    data: {
      cmd: 2,
      arg: 0,
      moduleCanvasId: "canvas",
      offscreenCanvases: test.canvasMissing ? {} : {
        canvas: { id: "canvas", canvasSharedPtr: 256, offscreenCanvas: canvas },
      },
    },
  });
  await Promise.race([
    entryReached,
    new Promise((_, reject) => setTimeout(() => reject(new Error(`${test.name}: entry timeout`)),
                                         1000)),
  ]);

  assert(entryCalls === 1, `${test.name}: entry was not forwarded exactly once`);
  assert((moduleState.preinitializedWebGPUPresentationStatus || 0) === test.status,
         `${test.name}: wrong presentation status`);
  assert(Boolean(moduleState.preinitializedWebGPUDevice) === test.device,
         `${test.name}: wrong device publication`);
  assert(Boolean(moduleState.preinitializedWebGPUSurface) === Boolean(test.ready),
         `${test.name}: wrong surface publication`);
  assert(Boolean(moduleState.preinitializedWebGPUBackbuffer) === Boolean(test.ready),
         `${test.name}: wrong backbuffer publication`);
  assert((moduleState.preinitializedWebGPUSurfaceWidth || 0) === (test.ready ? 1280 : 0),
         `${test.name}: wrong width publication`);
  assert((moduleState.preinitializedWebGPUSurfaceHeight || 0) === (test.ready ? 720 : 0),
         `${test.name}: wrong height publication`);
  assert(unconfigureCalls === (test.status >= 3 && test.status < 5 ? 1 : 0),
         `${test.name}: wrong surface cleanup`);
  assert(rejectedBackbufferDestroys ===
           (test.backbufferError || test.configurationError || test.lossBeforeEntry ? 1 : 0),
         `${test.name}: rejected backbuffer was not discarded`);
  assert(presentationSubmits === (test.presentation ? 1 : 0),
         `${test.name}: presentation use was not submitted exactly once`);
  assert(presentationCompletions === (test.ready && !test.fallback ? 1 : 0),
         `${test.name}: wrong strict presentation-completion count`);
  const expectedScopePops = test.status <= 2 ? 0 :
    (test.presentation && !test.fallback ? 6 : 3);
  assert(popScopeCalls === expectedScopePops,
         `${test.name}: wrong pre/post-configuration scope count`);
  assert((moduleState.preinitializedWebGPUPresentationValidation || "") ===
           (test.ready ? (test.fallback ? "fallback-diagnostic" : "strict") : ""),
         `${test.name}: wrong presentation-validation mode`);
  if (test.telemetry === "delayed") {
    await new Promise((resolve) => setTimeout(resolve, 30));
  }
  assert(telemetryDispatches === (test.telemetry === "omitted" ? 0 : test.telemetry ? 1 : 0),
         `${test.name}: wrong optional telemetry control`);
  const initialLossSignal = moduleState.preinitializedWebGPUDeviceLoss;
  assert(Boolean(initialLossSignal) === test.device,
         `${test.name}: wrong device-loss signal publication`);
  if (test.device) {
    assert((initialLossSignal.generation >>> 0) === 1,
           `${test.name}: wrong initial device-loss generation`);
    if (test.staleLoss) {
      moduleState.preinitializedWebGPUDeviceLoss = {
        generation: 2,
        status: 0,
        reason: "",
        message: "",
      };
    }
    if (test.lossAfterEntry) {
      resolveLoss({ reason: test.lossAfterEntry, message: "lost after entry" });
      await Promise.resolve();
    }
    const finalLossSignal = moduleState.preinitializedWebGPUDeviceLoss;
    assert((finalLossSignal.status | 0) === (test.lossStatus || 0),
           `${test.name}: wrong final device-loss status`);
    assert((finalLossSignal.generation >>> 0) === (test.staleLoss ? 2 : 1),
           `${test.name}: stale device-loss callback changed the current generation`);
    if (test.lossAfterEntry && !test.staleLoss) {
      assert(finalLossSignal.reason === test.lossAfterEntry &&
               finalLossSignal.message === "lost after entry",
             `${test.name}: device-loss detail was not retained`);
    }
  }
  assert(logs.length > 0, `${test.name}: expected a diagnostic`);
}

for (const test of cases) {
  await run(test);
}
console.log("CONTRACT ghost_preinit_worker PASS cases=19 statuses=0,1,2,3,4,5 " +
            "partial=unpublished device_only=preserved loss=pending,unknown,destroyed " +
            "stale=ignored preentry=unpublished entry=once " +
            "presentation=scoped-work-done fallback=diagnostic " +
            "telemetry=sync,delayed,omitted " +
            "adapter=current,legacy,precedence,unknown");

function replaceExactlyOnce(input, before, after, name) {
  const pieces = input.split(before);
  assert(pieces.length === 2, `${name}: source anchor count was ${pieces.length - 1}, expected 1`);
  return pieces[0] + after + pieces[1];
}

if (selfcheck) {
  const extraction = `var currentFallbackStatus =
            adapter.info && typeof adapter.info.isFallbackAdapter === "boolean" ?
              adapter.info.isFallbackAdapter :
              (typeof adapter.isFallbackAdapter === "boolean" ?
                 adapter.isFallbackAdapter : null);`;
  const mutations = [
    [
      "legacy_only",
      replaceExactlyOnce(
        source,
        extraction,
        `var currentFallbackStatus =
            typeof adapter.isFallbackAdapter === "boolean" ?
              adapter.isFallbackAdapter : null;`,
        "legacy_only",
      ),
    ],
    [
      "legacy_precedence",
      replaceExactlyOnce(
        source,
        extraction,
        `var currentFallbackStatus =
            typeof adapter.isFallbackAdapter === "boolean" ?
              adapter.isFallbackAdapter :
              (adapter.info && typeof adapter.info.isFallbackAdapter === "boolean" ?
                 adapter.info.isFallbackAdapter : null);`,
        "legacy_precedence",
      ),
    ],
    [
      "unknown_as_fallback",
      replaceExactlyOnce(
        source,
        "var adapterIsFallback = currentFallbackStatus === true;",
        "var adapterIsFallback = currentFallbackStatus !== false;",
        "unknown_as_fallback",
      ),
    ],
  ];

  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), "bw-preinit-adapter-info-"));
  try {
    for (const [name, mutatedSource] of mutations) {
      const mutatedPath = path.join(temporaryRoot, `${name}.js`);
      fs.writeFileSync(mutatedPath, mutatedSource);
      const result = spawnSync(
        process.execPath,
        [fileURLToPath(import.meta.url), mutatedPath],
        { encoding: "utf8", timeout: 10000 },
      );
      assert(result.error === undefined, `${name}: mutation runner failed: ${result.error}`);
      assert(result.status !== 0, `${name}: source mutation was accepted`);
    }
  }
  finally {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
  console.log("SELFCHECK ghost_preinit_adapter_info PASS positive=1 negative=3");
}
