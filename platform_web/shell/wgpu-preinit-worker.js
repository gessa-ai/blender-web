// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M4.T11 / audit R6 — worker-side pre-main WebGPU device and presentation acquisition.
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
// main() runs. While the event loop is still available, it also validates the transferred
// canvas, configuration, and initial backbuffer. GHOST_ContextWGPUWeb then imports the
// complete bundle synchronously; a presentable window is never published from device-only
// state.
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

  // Run one synchronous WebGPU operation under all three implementation error
  // scopes, then await their browser promises while this worker is still pre-main.
  // C++ cannot truthfully perform this wait once Blender enters its straight-line
  // PROXY_TO_PTHREAD main loop (ADR-006/007).
  var validateScoped = async function (device, operation, discard) {
    device.pushErrorScope("internal");
    device.pushErrorScope("out-of-memory");
    device.pushErrorScope("validation");
    var result;
    var failure = null;
    try {
      result = operation();
    }
    catch (ex) {
      failure = ex;
    }
    for (var i = 0; i < 3; i++) {
      try {
        var scopedError = await device.popErrorScope();
        if (!failure && scopedError) {
          failure = scopedError;
        }
      }
      catch (ex) {
        if (!failure) {
          failure = ex;
        }
      }
    }
    if (failure) {
      try { if (discard) { discard(result); } } catch (ignored) {}
      throw failure;
    }
    return result;
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
          var currentFallbackStatus =
            adapter.info && typeof adapter.info.isFallbackAdapter === "boolean" ?
              adapter.info.isFallbackAdapter :
              (typeof adapter.isFallbackAdapter === "boolean" ?
                 adapter.isFallbackAdapter : null);
          // Only an exact browser-reported fallback status may use the diagnostic
          // compatibility path below. Missing/unknown status stays on strict
          // validation and cannot manufacture a hardware-capable result.
          var adapterIsFallback = currentFallbackStatus === true;
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
          // Imported emdawnwebgpu devices cannot use wgpuDeviceGetLostFuture (the port
          // rejects that call). Own the browser-native promise here, before publication,
          // and bind it to one monotonically numbered device record. The promise callback
          // retains no C++ pointer and a stale device cannot poison a newer record.
          var priorLossGeneration = Module["preinitializedWebGPUDeviceLossGeneration"] >>> 0;
          var deviceLossGeneration = (priorLossGeneration + 1) >>> 0;
          if (!deviceLossGeneration) {
            deviceLossGeneration = 1;
          }
          Module["preinitializedWebGPUDeviceLossGeneration"] = deviceLossGeneration;
          var deviceLossSignal = {
            "generation": deviceLossGeneration,
            "status": 0,
            "reason": "",
            "message": "",
          };
          Module["preinitializedWebGPUDeviceLoss"] = deviceLossSignal;
          device.lost.then(function (info) {
            if (Module["preinitializedWebGPUDeviceLoss"] !== deviceLossSignal ||
                (deviceLossSignal["status"] | 0) !== 0) {
              return;
            }
            var reason = info && info.reason ? String(info.reason) : "unknown";
            var message = info && info.message ? String(info.message) : "";
            deviceLossSignal["status"] = reason === "destroyed" ? 2 : 1;
            deviceLossSignal["reason"] = reason;
            deviceLossSignal["message"] = message;
            log("[bw][GPU-LOST] reason=" + reason + " " + message);
          });
          var requireDeviceActive = function (stage) {
            if (Module["preinitializedWebGPUDeviceLoss"] !== deviceLossSignal ||
                (deviceLossSignal["status"] | 0) !== 0) {
              throw new Error("WebGPU device lost during " + stage);
            }
          };

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
          }
          catch (e) {}
          Module["preinitializedWebGPUDevice"] = device;
          log("[bw] WM-worker WebGPU device pre-acquired (ADR-007); features=" +
              requiredFeatures.length +
              " tier1=" + requiredFeatures.includes("texture-formats-tier1") +
              " tier2=" + requiredFeatures.includes("texture-formats-tier2") +
              " fallback=" + String(currentFallbackStatus) +
              " maxStorageTexturesPerShaderStage=" +
              requiredLimits.maxStorageTexturesPerShaderStage +
              " maxStorageBuffersPerShaderStage=" +
              requiredLimits.maxStorageBuffersPerShaderStage);

          // A presentable GHOST window is a stronger contract than a live device.
          // Resolve/configure the transferred canvas and validate its first persistent
          // backbuffer while this worker can still await promises. Only a complete bundle
          // is published for the synchronous C++ constructor to import.
          Module["preinitializedWebGPUPresentationStatus"] = 1;
          var surface = null;
          var backbuffer = null;
          try {
            try {
              if (typeof PThread !== "undefined" &&
                  typeof PThread.receiveOffscreenCanvases === "function" &&
                  d && d.offscreenCanvases) {
                PThread.receiveOffscreenCanvases(d);
              }
            }
            catch (registrationError) {
              log("[bw] early receiveOffscreenCanvases failed: " +
                  (registrationError && registrationError.message ?
                     registrationError.message : registrationError));
            }
            var canvas = null;
            // cmd:2 carries the OffscreenCanvas transfer, but Emscripten does not
            // publish it into GL.offscreenCanvases until `inner` handles this same
            // message. Invoke the runtime's own registration contract before the
            // preflight; `inner` repeats this idempotently when it receives cmd:2.
            if (typeof GL !== "undefined" && GL.offscreenCanvases) {
              canvas = GL.offscreenCanvases["canvas"] || null;
            }
            if (!canvas && typeof specialHTMLTargets !== "undefined") {
              canvas = specialHTMLTargets["#canvas"] || null;
            }
            if (canvas && canvas.offscreenCanvas) {
              canvas = canvas.offscreenCanvas;
            }
            if (!canvas || typeof canvas.getContext !== "function") {
              throw new Error("transferred #canvas is not resolvable on the WM worker");
            }

            Module["preinitializedWebGPUPresentationStatus"] = 2;
            surface = canvas.getContext("webgpu");
            if (!surface) {
              throw new Error("#canvas.getContext('webgpu') returned null");
            }

            var surfaceWidth = canvas.width | 0;
            var surfaceHeight = canvas.height | 0;
            if (surfaceWidth <= 0 || surfaceHeight <= 0) {
              throw new Error("#canvas has a zero drawing-buffer extent");
            }

            // Validate the ordinary texture while the device is still independent
            // of the canvas. Chromium's fallback adapter invalidates its raw external
            // instance when a WebGPU promise follows OffscreenCanvas.configure(), so
            // only that exact adapter shape uses the explicitly diagnostic synchronous
            // submission below. Non-fallback and unknown-status adapters additionally
            // require scoped validation and queue completion before C++ can import the
            // complete bundle after main starts.
            Module["preinitializedWebGPUPresentationStatus"] = 4;
            backbuffer = await validateScoped(
              device,
              function () {
                return device.createTexture({
                  label: "wgpu_web_backbuffer",
                  size: { width: surfaceWidth, height: surfaceHeight, depthOrArrayLayers: 1 },
                  dimension: "2d",
                  format: "bgra8unorm",
                  mipLevelCount: 1,
                  sampleCount: 1,
                  usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING |
                         GPUTextureUsage.COPY_SRC,
                });
              },
              function (candidate) { if (candidate) { candidate.destroy(); } });
            requireDeviceActive("initial backbuffer creation");
            if (!backbuffer) {
              throw new Error("initial backbuffer creation returned null");
            }

            Module["preinitializedWebGPUPresentationStatus"] = 3;
            var configureAndSubmitPresentationProbe = function () {
              surface.configure({
                device: device,
                format: "bgra8unorm",
                usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC,
                alphaMode: "opaque",
              });
              var initialSurfaceTexture = surface.getCurrentTexture();
              if (!initialSurfaceTexture) {
                throw new Error("initial surface texture acquisition returned null");
              }
              var initialSurfaceView = initialSurfaceTexture.createView();
              if (!initialSurfaceView) {
                throw new Error("initial surface texture view creation returned null");
              }
              var presentationEncoder = device.createCommandEncoder({
                label: "wgpu_web_presentation_probe_encoder",
              });
              if (!presentationEncoder) {
                throw new Error("presentation probe encoder creation returned null");
              }
              var presentationPass = presentationEncoder.beginRenderPass({
                label: "wgpu_web_presentation_probe_pass",
                colorAttachments: [{
                  view: initialSurfaceView,
                  clearValue: { r: 1, g: 1, b: 1, a: 1 },
                  loadOp: "clear",
                  storeOp: "store",
                }],
              });
              if (!presentationPass) {
                throw new Error("presentation probe render pass creation returned null");
              }
              presentationPass.end();
              var presentationCommands = presentationEncoder.finish();
              if (!presentationCommands) {
                throw new Error("presentation probe command finish returned null");
              }
              device.queue.submit([presentationCommands]);
            };

            if (adapterIsFallback) {
              // Chromium's software adapter invalidates its external Instance when
              // any WebGPU promise is created after OffscreenCanvas.configure().
              // Keep this compatibility path explicitly diagnostic: it submits the
              // same presentation use but cannot bind a receipt or claim strict
              // validation. Hardware and unknown-status adapters never enter it.
              configureAndSubmitPresentationProbe();
              Module["preinitializedWebGPUPresentationValidation"] =
                "fallback-diagnostic";
            }
            else {
              await validateScoped(device, configureAndSubmitPresentationProbe, null);
              await device.queue.onSubmittedWorkDone();
              requireDeviceActive("initial surface presentation completion");
              Module["preinitializedWebGPUPresentationValidation"] = "strict";
            }

            Module["preinitializedWebGPUSurface"] = surface;
            Module["preinitializedWebGPUBackbuffer"] = backbuffer;
            Module["preinitializedWebGPUSurfaceWidth"] = surfaceWidth;
            Module["preinitializedWebGPUSurfaceHeight"] = surfaceHeight;
            Module["preinitializedWebGPUPresentationStatus"] = 5;
            log("[bw] WM-worker WebGPU presentation pre-acquired; canvas=" +
                surfaceWidth + "x" + surfaceHeight + " validation=" +
                Module["preinitializedWebGPUPresentationValidation"]);
          }
          catch (ex) {
            try { if (backbuffer) { backbuffer.destroy(); } } catch (ignored) {}
            try { if (surface) { surface.unconfigure(); } } catch (ignored) {}
            log("[bw] WM-worker WebGPU presentation preinit FAILED stage=" +
                Module["preinitializedWebGPUPresentationStatus"] + ": " +
                (ex && ex.message ? ex.message : ex));
          }
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
