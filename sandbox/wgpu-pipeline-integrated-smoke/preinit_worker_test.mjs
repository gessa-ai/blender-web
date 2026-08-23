// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

import fs from "node:fs";
import vm from "node:vm";

const sourcePath = process.argv[2];
if (!sourcePath) {
  throw new Error("usage: node preinit_worker_test.mjs <wgpu-preinit-worker.js>");
}
const source = fs.readFileSync(sourcePath, "utf8");

const cases = [
  { name: "device", adapterMissing: true, status: 0, device: false },
  { name: "canvas", canvasMissing: true, status: 1, device: true },
  { name: "surface", surfaceMissing: true, status: 2, device: true },
  { name: "configuration", configurationError: true, status: 3, device: true },
  { name: "backbuffer_error", backbufferError: true, status: 4, device: true },
  { name: "backbuffer_null", backbufferNull: true, status: 4, device: true },
  { name: "ready", status: 5, device: true, ready: true },
];

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function run(test) {
  const moduleState = {};
  const logs = [];
  let entryCalls = 0;
  let resolveEntry;
  const entryReached = new Promise((resolve) => { resolveEntry = resolve; });
  const entryHandler = () => {
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
  const surface = {
    configure() {},
    getCurrentTexture() { return { kind: "surface-texture" }; },
    unconfigure() { unconfigureCalls++; },
  };
  const canvas = {
    width: 1280,
    height: 720,
    getContext() { return test.surfaceMissing ? null : surface; },
  };

  const popErrors = [
    test.configurationError ? new Error("configuration rejected") : null,
    null,
    null,
    test.backbufferError ? new Error("backbuffer rejected") : null,
    null,
    null,
  ];
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
    lost: new Promise(() => {}),
    addEventListener() {},
    pushErrorScope() {},
    async popErrorScope() { return popErrors.shift() ?? null; },
    createTexture() {
      if (test.backbufferNull) {
        return null;
      }
      return {
        kind: "backbuffer",
        destroy() { rejectedBackbufferDestroys++; },
      };
    },
  };
  const adapter = test.adapterMissing ? null : {
    features: new Set(),
    limits: device.limits,
    async requestDevice() { return device; },
  };

  const context = vm.createContext({
    ENVIRONMENT_IS_PTHREAD: true,
    GL: { offscreenCanvases: test.canvasMissing ? {} : { canvas } },
    GPUTextureUsage: { RENDER_ATTACHMENT: 1, TEXTURE_BINDING: 2, COPY_SRC: 4 },
    Module: moduleState,
    navigator: { gpu: { async requestAdapter() { return adapter; } } },
    postMessage() {},
    self: selfObject,
    specialHTMLTargets: {},
    err(message) { logs.push(String(message)); },
  });
  new vm.Script(source, { filename: sourcePath }).runInContext(context);
  registeredHandler({ data: { cmd: 2, arg: 0 } });
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
  assert(rejectedBackbufferDestroys === (test.backbufferError ? 1 : 0),
         `${test.name}: rejected backbuffer was not discarded`);
  assert(logs.length > 0, `${test.name}: expected a diagnostic`);
}

for (const test of cases) {
  await run(test);
}
console.log("CONTRACT ghost_preinit_worker PASS cases=7 statuses=0,1,2,3,4,5 " +
            "partial=unpublished device_only=preserved entry=once");
