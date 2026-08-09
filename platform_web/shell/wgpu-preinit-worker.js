// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M4.T11 (ADR-007) — worker-side pre-main WebGPU device acquisition.
//
// Baked into blender_browser.js as a --post-js, so it runs at the END of the module
// body in BOTH the browser main thread and every pthread Web Worker. It only acts in a
// pthread worker, and only for the PROXY_TO_PTHREAD "application main thread".
//
// Why here: under ADR-006 (no -sJSPI / no -sASYNCIFY) the emdawnwebgpu port cannot
// acquire a WebGPU device synchronously (its blocking WaitAny needs asyncify and a
// worker cannot resolve its own promise while Atomics-blocked — notes/m4-integration.md
// "M4.T11" probe (ii)). And a GPUDevice cannot cross Worker realms (probe (i):
// DataCloneError), so it MUST be acquired on the very worker that will use it. The one
// window where that worker's event loop is free is BEFORE main() runs straight-line.
// Emscripten runs the proxied main via the worker's cmd:2 message → invokeEntryPoint
// (blender_browser.js). We intercept that message, await navigator.gpu.request{Adapter,
// Device}() (probe (iii): a dedicated worker HAS navigator.gpu here), stash the device
// in this worker's Module.preinitializedWebGPUDevice, and only THEN dispatch cmd:2 so
// main() runs. GHOST_ContextWGPUWeb::initializeDrawingContext() then pulls it
// synchronously via emscripten_webgpu_get_device().
//
// Interception mechanism: we OWN self.onmessage via an accessor. Emscripten registers
// its handler (handleMessage) at self.onmessage in the module body (BEFORE this post-js)
// and RE-assigns it in the cmd:1 handler (startWorker). Neither a self.onmessage wrapper
// (clobbered by the reassignment) nor an addEventListener (fires AFTER the position-0
// onmessage listener, so it cannot pre-empt main()) works. Instead we shadow the
// onmessage accessor: every Emscripten assignment updates our stored `inner` handler,
// while the ACTUAL registered listener stays our `wrapper`. wrapper is therefore the
// sole handler and runs first; for the main thread it defers `inner` until the device is
// ready, then invokes it exactly once.
//
// Discriminator: the PROXY_TO_PTHREAD application main thread runs _main_thread with a
// NULL arg (crt1_proxy_main.c:52; empirically cmd:2 arg=0); worker/TBB threads carry a
// non-null arg. Gate on cmd:2 with a falsy arg, once per worker.

(function () {
  if (typeof ENVIRONMENT_IS_PTHREAD === "undefined" || !ENVIRONMENT_IS_PTHREAD) {
    return;
  }
  if (typeof self === "undefined" || typeof navigator === "undefined" || !navigator.gpu) {
    return;
  }

  // On a DedicatedWorkerGlobalScope, `onmessage` is an OWN accessor on `self` (the
  // [Global] interface special case), NOT on the prototype — so walk from self.
  var target = self;
  while (target && !Object.getOwnPropertyDescriptor(target, "onmessage")) {
    target = Object.getPrototypeOf(target);
  }
  var nativeDesc = target && Object.getOwnPropertyDescriptor(target, "onmessage");
  if (!nativeDesc || !nativeDesc.set || !nativeDesc.get) {
    return; // unexpected environment — do not break message delivery
  }

  var log = function (m) {
    try { if (typeof err === "function") { err(m); return; } } catch (e) {}
    try { postMessage({ cmd: 9, handler: "printErr", args: [m] }); } catch (e) {}
  };

  var inner = nativeDesc.get.call(self); // Emscripten's current handler (handleMessage)
  var done = false;

  var wrapper = function (e) {
    var d = e && e.data;
    if (d && d.cmd === 2 && !d.arg && !done && typeof inner === "function") {
      done = true;
      var h = inner;
      (async function () {
        try {
          var adapter = await navigator.gpu.requestAdapter({ powerPreference: "high-performance" });
          if (!adapter) {
            throw new Error("navigator.gpu.requestAdapter() returned null");
          }
          // Enable every feature the adapter advertises. Blender's WebGPU backend
          // feature-gates on what the DEVICE actually exposes (wgpu_texture_format.cc
          // FeatureGate::*), so an imported device with no features cannot create e.g.
          // a `depth32float-stencil8` depth buffer (SFLOAT_32_DEPTH_UINT_8) — the window
          // depth attachment GPU_init builds — and throws
          // "requires the 'depth32float-stencil8' feature to be enabled". Requesting the
          // full supported set (the native GHOST_ContextWGPU adapter-guards a subset;
          // in the browser only the adapter's own features can be requested, so all of
          // them is always valid) matches the device Blender expects. Mirrors
          // GHOST_ContextWGPU.cc:93-107's adapter-guarded RequestDevice, widened.
          var requiredFeatures = [];
          try {
            if (adapter.features && typeof adapter.features.forEach === "function") {
              adapter.features.forEach(function (f) { requiredFeatures.push(f); });
            }
          } catch (e) {}
          // Request only the two adapter-supported ceilings EEVEE needs. Omitting every
          // other key preserves the browser defaults for all unrelated device limits.
          var requiredLimits = {
            maxStorageTexturesPerShaderStage: adapter.limits.maxStorageTexturesPerShaderStage,
            maxStorageBuffersPerShaderStage: adapter.limits.maxStorageBuffersPerShaderStage,
          };
          var device = await adapter.requestDevice({
            requiredFeatures: requiredFeatures,
            requiredLimits: requiredLimits,
          });
          // VISIBILITY (M4.T18, r21): route the WM-worker device's uncaptured
          // validation/OOM errors to the PAGE console. This worker owns all GPU work, but
          // its console.error is NOT proxied to the tab — only log() (Emscripten err() ->
          // printErr) is. Dawn's uncaptured errors during viewport draw are otherwise
          // invisible from the main thread (notes/gpu-r20-cube-blocker.md hyp. 2). The
          // imported C++ wgpu::Device cannot set this post-creation (DeviceDescriptor-only),
          // so attach the browser-native listener on the raw GPUDevice here, at creation.
          try {
            device.addEventListener("uncapturederror", function (ev) {
              var er = ev && ev.error;
              var nm = (er && er.constructor && er.constructor.name) ? er.constructor.name
                                                                     : "GPUError";
              log("[bw][GPU-ERROR] " + nm + ": " + (er && er.message ? er.message : er));
            });
            device.lost.then(function (info) {
              log("[bw][GPU-LOST] reason=" + (info && info.reason) + " " +
                  (info && info.message ? info.message : ""));
            });
          }
          catch (e) {}
          Module["preinitializedWebGPUDevice"] = device;
          log("[bw] WM-worker WebGPU device pre-acquired (ADR-007); features=" +
              requiredFeatures.length +
              " tier1=" + requiredFeatures.includes("texture-formats-tier1") +
              " tier2=" + requiredFeatures.includes("texture-formats-tier2") +
              " maxStorageTexturesPerShaderStage=" +
              requiredLimits.maxStorageTexturesPerShaderStage +
              " maxStorageBuffersPerShaderStage=" +
              requiredLimits.maxStorageBuffersPerShaderStage);
        }
        catch (ex) {
          log("[bw] WM-worker WebGPU preinit FAILED: " + (ex && ex.message ? ex.message : ex));
        }
        // NOTE: the M7 project store OPFS mount is intentionally NOT done here. A
        // synchronous WasmFS OPFS backend creation at this pre-invokeEntryPoint point
        // deadlocks the worker (it blocks the message loop before the pthread/OPFS
        // backend-thread machinery is ready). It is mounted instead from
        // GHOST_SystemWeb::init() (inside main(), on this same WM worker, before
        // WM_init runs BKE_tempdir_init / reads the config dir) - the proven-safe
        // "inside main()" context (notes/m7-opfs-probe.md, notes/m7-store-wired.md).
        h.call(self, e); // run the pthread entry (invokeEntryPoint → main()) exactly once
      })();
      return;
    }
    if (typeof inner === "function") {
      return inner.call(self, e);
    }
  };

  // Register our wrapper as the real onmessage listener, then shadow the accessor so
  // Emscripten's future `self.onmessage = handleMessage` only updates `inner`.
  nativeDesc.set.call(self, wrapper);
  Object.defineProperty(self, "onmessage", {
    configurable: true,
    get: function () { return inner; },
    set: function (v) { inner = v; nativeDesc.set.call(self, wrapper); },
  });
})();
