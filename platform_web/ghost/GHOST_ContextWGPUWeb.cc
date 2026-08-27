/* SPDX-FileCopyrightText: 2022-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from intern/ghost/intern/GHOST_ContextWGPU.cc (native Dawn,
 * patch 0011) @ fbe6228777e7. */

/** \file
 * \ingroup GHOST-web
 * Implementation of GHOST_ContextWGPUWeb (emdawnwebgpu + HTML canvas surface). */

#include "GHOST_ContextWGPUWeb.hh"
#include "GHOST_WGPUTransaction.hh"

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <utility>

#include <emscripten/emscripten.h>
#include <emscripten/html5.h>

#include "GHOST_WebDisplayState.hh"

/* --- Present counter (ghost-keepalive) --------------------------------------- */
namespace {
ghost_web::SurfaceAcquireStatus surface_acquire_status(
    const wgpu::SurfaceGetCurrentTextureStatus status)
{
  switch (status) {
    case wgpu::SurfaceGetCurrentTextureStatus::SuccessOptimal:
      return ghost_web::SurfaceAcquireStatus::SuccessOptimal;
    case wgpu::SurfaceGetCurrentTextureStatus::SuccessSuboptimal:
      return ghost_web::SurfaceAcquireStatus::SuccessSuboptimal;
    case wgpu::SurfaceGetCurrentTextureStatus::Timeout:
      return ghost_web::SurfaceAcquireStatus::Timeout;
    case wgpu::SurfaceGetCurrentTextureStatus::Outdated:
      return ghost_web::SurfaceAcquireStatus::Outdated;
    case wgpu::SurfaceGetCurrentTextureStatus::Lost:
      return ghost_web::SurfaceAcquireStatus::Lost;
    case wgpu::SurfaceGetCurrentTextureStatus::Error:
    default:
      return ghost_web::SurfaceAcquireStatus::Error;
  }
}
}  // namespace

/* Total presents since boot, as double (avoids a BigInt hop under -sWASM_BIGINT). Exported
 * for the ghost-keepalive no-idle-burn proof: the shell polls this across an idle window and
 * shows the delta is ~0 (no GPU submits at idle) while bw_wm_tick_count keeps climbing. */
extern "C" EMSCRIPTEN_KEEPALIVE double bw_present_count(void)
{
  return double(ghost_web::present_count());
}

/* Read-only live proof that a validated replacement surface/backbuffer published a fresh redraw
 * episode. Resize regressions sample this separately from size events and presentation counts. */
extern "C" EMSCRIPTEN_KEEPALIVE double bw_redraw_episode_count(void)
{
  return double(ghost_web::redraw_episode_generation());
}

/* --- M4.T11 (ADR-007) worker-side device delivery ---------------------------- */
/* The WebGPU device cannot be acquired synchronously here (emdawnwebgpu needs an
 * event-loop turn or asyncify) and cannot cross realms, so it is acquired
 * ASYNCHRONOUSLY on THIS (WM/proxied-main) worker pre-main and stashed in
 * Module.preinitializedWebGPUDevice by platform_web/shell/wgpu-preinit-worker.js.
 * See the "M4.T11 — emdawnwebgpu port probe" section of notes/m4-integration.md. */
EM_JS(int, ghost_web_has_preinit_device, (), {
  return (typeof Module !== "undefined" && Module["preinitializedWebGPUDevice"]) ? 1 : 0;
});

EM_JS(int, ghost_web_preinit_presentation_status, (), {
  return (typeof Module !== "undefined" &&
          Module["preinitializedWebGPUPresentationStatus"]) ?
             Module["preinitializedWebGPUPresentationStatus"] | 0 :
             0;
});

EM_JS(uint32_t, ghost_web_preinit_device_loss_generation, (), {
  var signal = (typeof Module !== "undefined") ?
    Module["preinitializedWebGPUDeviceLoss"] : null;
  return signal ? signal["generation"] >>> 0 : 0;
});

EM_JS(int, ghost_web_preinit_device_loss_status, (), {
  var signal = (typeof Module !== "undefined") ?
    Module["preinitializedWebGPUDeviceLoss"] : null;
  return signal ? signal["status"] | 0 : 0;
});

namespace {
ghost_web::ImportedDeviceLossObservation imported_device_loss_observation()
{
  const int raw_status = ghost_web_preinit_device_loss_status();
  const ghost_web::ImportedDeviceLossStatus status =
      raw_status == int(ghost_web::ImportedDeviceLossStatus::Pending) ?
          ghost_web::ImportedDeviceLossStatus::Pending :
      raw_status == int(ghost_web::ImportedDeviceLossStatus::Destroyed) ?
          ghost_web::ImportedDeviceLossStatus::Destroyed :
          ghost_web::ImportedDeviceLossStatus::Unknown;
  return {ghost_web_preinit_device_loss_generation(), status};
}
}  // namespace

EM_JS(int, ghost_web_preinit_surface_width, (), {
  return (typeof Module !== "undefined" && Module["preinitializedWebGPUSurfaceWidth"]) ?
             Module["preinitializedWebGPUSurfaceWidth"] | 0 :
             0;
});

EM_JS(int, ghost_web_preinit_surface_height, (), {
  return (typeof Module !== "undefined" && Module["preinitializedWebGPUSurfaceHeight"]) ?
             Module["preinitializedWebGPUSurfaceHeight"] | 0 :
             0;
});

EM_JS(WGPUSurface, ghost_web_take_preinit_surface, (), {
  if (typeof Module === "undefined" || typeof WebGPU === "undefined") {
    return 0;
  }
  var surface = Module["preinitializedWebGPUSurface"];
  if (!surface) {
    return 0;
  }
  Module["preinitializedWebGPUSurface"] = null;
  return WebGPU.importJsSurface(surface);
});

EM_JS(WGPUTexture, ghost_web_take_preinit_backbuffer, (WGPUDevice parent_device), {
  if (typeof Module === "undefined" || typeof WebGPU === "undefined") {
    return 0;
  }
  var backbuffer = Module["preinitializedWebGPUBackbuffer"];
  if (!backbuffer) {
    return 0;
  }
  Module["preinitializedWebGPUBackbuffer"] = null;
  return WebGPU.importJsTexture(backbuffer, parent_device);
});

/* Whether the canvas selector resolves on THIS thread, mirroring emdawnwebgpu's
 * findCanvasEventTarget lookup ORDER exactly (built JS: findCanvasEventTarget). On the
 * WM worker the DOM `#canvas` is transferred as an OffscreenCanvas (OFFSCREENCANVAS_
 * SUPPORT + OFFSCREENCANVASES_TO_PTHREAD, M4.T12) and lands in GL.offscreenCanvases
 * keyed by the BARE element id (selector minus a leading '#') — NOT in
 * specialHTMLTargets — which is why the earlier specialHTMLTargets/document-only check
 * missed it and left the surface deferred. Check GL.offscreenCanvases first, then the
 * browser-main-thread paths. */
EM_JS(int, ghost_web_canvas_resolvable, (const char *selector), {
  var s = UTF8ToString(selector);
  try {
    if (typeof GL !== "undefined" && GL.offscreenCanvases &&
        GL.offscreenCanvases[s.replace(/^#/, "")]) {
      return 1;
    }
    if (typeof specialHTMLTargets !== "undefined" && specialHTMLTargets[s]) {
      return 1;
    }
    if (typeof document !== "undefined" && document && document.querySelector(s)) {
      return 1;
    }
  } catch (e) {}
  return 0;
});

GHOST_ContextWGPUWeb::GHOST_ContextWGPUWeb(const GHOST_ContextParams &context_params,
                                           const char *canvas_selector,
                                           const ghost_web::DrawingContextMode mode)
    : GHOST_Context(context_params),
      canvas_selector_(canvas_selector ? canvas_selector : "#canvas"),
      mode_(mode),
      callback_lifetime_(std::make_shared<CallbackLifetime>(*this))
{
}

GHOST_ContextWGPUWeb::~GHOST_ContextWGPUWeb()
{
  /* Close callback and owner-method admission before invalidate waits for the shared execution
   * slot. A callback that destroys this context can re-enter the recursive slot safely. */
  callback_lifetime_->cancel();
  callback_lifetime_->invalidate();
}

void GHOST_ContextWGPUWeb::pushErrorScopes(const wgpu::Device &device)
{
  /* Pop in reverse order. Validation is innermost because descriptor/command errors are the
   * common path; OOM and internal failures must also prevent publication. */
  device.PushErrorScope(wgpu::ErrorFilter::Internal);
  device.PushErrorScope(wgpu::ErrorFilter::OutOfMemory);
  device.PushErrorScope(wgpu::ErrorFilter::Validation);
}

void GHOST_ContextWGPUWeb::popErrorScopes(const wgpu::Device &device,
                                          std::string label,
                                          ErrorScopeCallback on_complete)
{
  struct ScopeResult {
    std::atomic<int> pending{3};
    std::atomic<bool> valid{true};
    std::string label;
    ErrorScopeCallback complete;
  };

  auto result = std::make_shared<ScopeResult>();
  result->label = std::move(label);
  result->complete = std::move(on_complete);
  auto settle = [result](wgpu::PopErrorScopeStatus status,
                         wgpu::ErrorType type,
                         wgpu::StringView message) {
    if (status != wgpu::PopErrorScopeStatus::Success || type != wgpu::ErrorType::NoError) {
      result->valid.store(false, std::memory_order_release);
      const size_t message_length =
          message.data == nullptr ?
              0 :
              (message.length == WGPU_STRLEN ? std::char_traits<char>::length(message.data) :
                                               message.length);
      std::printf("WGPUWeb: %s rejected (status %d, type %d): %.*s\n",
                  result->label.c_str(),
                  int(status),
                  int(type),
                  int(std::min<size_t>(message_length, size_t(INT32_MAX))),
                  message.data ? message.data : "");
    }
    if (result->pending.fetch_sub(1, std::memory_order_acq_rel) == 1) {
      result->complete(result->valid.load(std::memory_order_acquire));
    }
  };

  device.PopErrorScope(wgpu::CallbackMode::AllowSpontaneous, settle);
  device.PopErrorScope(wgpu::CallbackMode::AllowSpontaneous, settle);
  device.PopErrorScope(wgpu::CallbackMode::AllowSpontaneous, settle);
}

/* --- GHOST_Context surface --------------------------------------------------- */

GHOST_TSuccess GHOST_ContextWGPUWeb::initializeDrawingContext()
{
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  auto owner_execution = lifetime->enter();
  if (!owner_execution) {
    return GHOST_kFailure;
  }
  /* If a prior initAsync() already acquired the device (callback path, e.g. the
   * standalone harness), we are done. */
  if (ready_) {
    return deviceIsUsable() ? GHOST_kSuccess : GHOST_kFailure;
  }

  /* Windowed (GHOST) path under ADR-006/ADR-007. This runs straight-line on the
   * PROXY_TO_PTHREAD WM worker during WM_init, before any event-loop pump exists. The
   * emdawnwebgpu port cannot acquire a device synchronously here: a TimedWaitAny
   * instance needs asyncify/JSPI (webgpu.cpp:1643 → CreateInstance returns null), and a
   * blocking WaitAny would deadlock the worker (it cannot resolve its own promise while
   * Atomics-blocked). So the device was acquired ASYNCHRONOUSLY on THIS worker pre-main
   * (platform_web/shell/wgpu-preinit-worker.js) and stashed in
   * Module.preinitializedWebGPUDevice; here we just import it synchronously. The device
   * handle is per-thread (emdawnwebgpu jsObjects table) — importing on the WM worker is
   * correct because this worker will own all GPU work (M4.T11 probe (i)/(iii)). */
  if (!ghost_web_has_preinit_device()) {
    std::printf("WGPUWeb: no pre-acquired device on the WM worker "
                "(wgpu-preinit-worker.js did not run or acquisition failed)\n");
    return GHOST_kFailure;
  }

  /* A featureless instance is valid without asyncify (unlike a TimedWaitAny one). */
  instance_ = wgpu::CreateInstance(nullptr);
  if (instance_ == nullptr) {
    std::printf("WGPUWeb: CreateInstance failed\n");
    return GHOST_kFailure;
  }

  /* Import Module.preinitializedWebGPUDevice into THIS thread's object table. */
  WGPUDevice raw_device = emscripten_webgpu_get_device();
  if (raw_device == nullptr) {
    std::printf("WGPUWeb: emscripten_webgpu_get_device returned null\n");
    return GHOST_kFailure;
  }
  device_ = wgpu::Device::Acquire(raw_device);
  /* emdawnwebgpu explicitly rejects GetLostFuture() on imported devices. The pre-main
   * worker therefore owns the browser-native `device.lost` promise and publishes a
   * generation-bound monotonic signal beside the device before this import. */
  device_state_ = std::make_shared<ghost_web::DeviceCallbackState>(
      ghost_web_preinit_device_loss_generation(), imported_device_loss_observation);
  queue_ = device_.GetQueue();
  if (!deviceIsUsable()) {
    std::printf("WGPUWeb: imported device has no active owned loss signal\n");
    completeInitialization(false);
    return GHOST_kFailure;
  }

  const auto presentation_status = static_cast<ghost_web::PreinitializedPresentationStatus>(
      ghost_web_preinit_presentation_status());
  if (mode_ == ghost_web::DrawingContextMode::DeviceOnly) {
    const bool valid = ghost_web::drawing_context_status_is_ready(mode_,
                                                                  device_ != nullptr,
                                                                  presentation_status,
                                                                  false,
                                                                  false,
                                                                  0,
                                                                  0);
    completeInitialization(valid);
    return valid ? GHOST_kSuccess : GHOST_kFailure;
  }

  const uint32_t candidate_width = uint32_t(std::max(ghost_web_preinit_surface_width(), 0));
  const uint32_t candidate_height = uint32_t(std::max(ghost_web_preinit_surface_height(), 0));
  wgpu::Surface candidate_surface;
  wgpu::Texture candidate_backbuffer;
  if (presentation_status == ghost_web::PreinitializedPresentationStatus::Ready) {
    candidate_surface = wgpu::Surface::Acquire(ghost_web_take_preinit_surface());
    candidate_backbuffer =
        wgpu::Texture::Acquire(ghost_web_take_preinit_backbuffer(device_.Get()));
  }
  const bool valid = ghost_web::drawing_context_status_is_ready(mode_,
                                                                device_ != nullptr,
                                                                presentation_status,
                                                                candidate_surface != nullptr,
                                                                candidate_backbuffer != nullptr,
                                                                candidate_width,
                                                                candidate_height);
  if (!valid) {
    std::printf("WGPUWeb: presentable preinit failed for '%s' at stage %d\n",
                canvas_selector_.c_str(),
                int(presentation_status));
    completeInitialization(false);
    return GHOST_kFailure;
  }

  surface_ = std::move(candidate_surface);
  backbuffer_ = std::move(candidate_backbuffer);
  width_ = requested_width_ = backbuffer_w_ = candidate_width;
  height_ = requested_height_ = backbuffer_h_ = candidate_height;
  backbuffer_redraw_episode_ = ghost_web::redraw_episode_generation();
  configured_ = true;
  completeInitialization(true);
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::releaseNativeHandles()
{
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  auto owner_execution = lifetime->enter();
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferAcquire()
{
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  auto owner_execution = lifetime->enter();
  if (!owner_execution) {
    return GHOST_kFailure;
  }
  return deviceIsUsable() ? GHOST_kSuccess : GHOST_kFailure;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferRelease()
{
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  auto owner_execution = lifetime->enter();
  if (!owner_execution) {
    return GHOST_kFailure;
  }
  /* End-of-frame present (M4.T21): the backend renders every pass into the PERSISTENT
   * offscreen back-buffer; here — the last op of the frame, still inside the WM's rAF
   * tick (wm_draw.cc:1692 wm_window_swap_buffer_release) — we blit it onto the surface's
   * current texture and submit once. The browser then auto-presents that texture on
   * event-loop yield. Because acquire+copy+submit all happen in-tick and nothing else
   * ever references the surface, the per-frame "Destroyed texture … WebgpuSwapChainTexture
   * used in a submit" family (725x/boot pre-M4.T21) cannot occur. */
  if (!deviceIsUsable()) {
    return GHOST_kFailure;
  }
  if (mode_ == ghost_web::DrawingContextMode::DeviceOnly) {
    return GHOST_kSuccess;
  }
  if (ghost_web::redraw_present_barrier_is_scheduled()) {
    if (!ghost_web::redraw_present_barrier_is_ready()) {
      /* The resized frame is still draining through browser error scopes. Reporting swap success
       * keeps WM's synchronous contract intact while deliberately withholding an intermediate
       * persistent-backbuffer pass from the canvas. */
      return GHOST_kSuccess;
    }
    const uint64_t episode = ghost_web::redraw_present_barrier_ready_episode();
    const bool presented = presentBackbuffer();
    ghost_web::complete_redraw_present_barrier(episode, presented);
    static uint32_t barrier_log_count = 0;
    if (barrier_log_count < 8) {
      std::printf("WGPUWeb-resize-present-barrier: episode=%llu synchronous-present=%d\n",
                  static_cast<unsigned long long>(episode),
                  presented ? 1 : 0);
      barrier_log_count++;
    }
    return presented ? GHOST_kSuccess : GHOST_kFailure;
  }
  return presentBackbuffer() ? GHOST_kSuccess : GHOST_kFailure;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::activateDrawingContext()
{
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  auto owner_execution = lifetime->enter();
  if (!owner_execution) {
    return GHOST_kFailure;
  }
  return deviceIsUsable() ? GHOST_kSuccess : GHOST_kFailure;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::releaseDrawingContext()
{
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  auto owner_execution = lifetime->enter();
  return GHOST_kSuccess;
}

void GHOST_ContextWGPUWeb::initAsync(uint32_t width, uint32_t height, ReadyCallback on_ready)
{
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  auto owner_execution = lifetime->enter();
  if (!owner_execution) {
    return;
  }
  width_ = width;
  height_ = height;
  on_ready_ = std::move(on_ready);

  /* No TimedWaitAny feature here: the browser drives callbacks off the event loop
   * (AllowSpontaneous), so we never block-wait. */
  instance_ = wgpu::CreateInstance(nullptr);
  if (instance_ == nullptr) {
    std::printf("WGPUWeb: CreateInstance failed\n");
    completeInitialization(false);
    return;
  }
  requestAdapter();
}

void GHOST_ContextWGPUWeb::requestAdapter()
{
  wgpu::RequestAdapterOptions opts = {};
  opts.powerPreference = wgpu::PowerPreference::HighPerformance;
  const std::shared_ptr<CallbackLifetime> callback_lifetime = callback_lifetime_;

  instance_.RequestAdapter(
      &opts,
      wgpu::CallbackMode::AllowSpontaneous,
      [callback_lifetime](
          wgpu::RequestAdapterStatus status, wgpu::Adapter a, wgpu::StringView msg) {
        callback_lifetime->deliver([&](GHOST_ContextWGPUWeb &owner) {
          if (status != wgpu::RequestAdapterStatus::Success || a == nullptr) {
            std::printf("WGPUWeb: RequestAdapter failed: %.*s\n", int(msg.length), msg.data);
            owner.completeInitialization(false);
            return;
          }
          owner.adapter_ = std::move(a);
          owner.requestDevice();
        });
      });
}

void GHOST_ContextWGPUWeb::requestDevice()
{
  wgpu::DeviceDescriptor desc = {};
  const std::shared_ptr<ghost_web::DeviceCallbackState> device_state = device_state_;
  const std::shared_ptr<CallbackLifetime> device_loss_lifetime = callback_lifetime_;
  desc.SetDeviceLostCallback(
      wgpu::CallbackMode::AllowSpontaneous,
      [device_state, device_loss_lifetime](const wgpu::Device & /*device*/,
                                           wgpu::DeviceLostReason /*reason*/,
                                           wgpu::StringView /*message*/) {
        ghost_web::fallback_device_loss_notify(
            device_state, device_loss_lifetime, [](GHOST_ContextWGPUWeb &owner) {
              owner.propagateDeviceLoss();
            });
      });
  desc.SetUncapturedErrorCallback(
      [](const wgpu::Device & /*d*/, wgpu::ErrorType type, wgpu::StringView msg) {
        std::printf("WGPUWeb: uncaptured error (%d): %.*s\n", int(type), int(msg.length), msg.data);
      });

  /* Match the native Dawn context's resource and compute ceilings. The
   * preinitialized-worker path already requests this set, but this fallback
   * must create an equivalent device when preinitialization is unavailable. */
  wgpu::Limits supported_limits = {};
  wgpu::Limits required_limits = {};
  if (adapter_.GetLimits(&supported_limits)) {
    required_limits.maxStorageTexturesPerShaderStage =
        supported_limits.maxStorageTexturesPerShaderStage;
    required_limits.maxSampledTexturesPerShaderStage =
        supported_limits.maxSampledTexturesPerShaderStage;
    required_limits.maxSamplersPerShaderStage = supported_limits.maxSamplersPerShaderStage;
    required_limits.maxStorageBuffersPerShaderStage =
        supported_limits.maxStorageBuffersPerShaderStage;
    required_limits.maxBufferSize = supported_limits.maxBufferSize;
    required_limits.maxStorageBufferBindingSize = supported_limits.maxStorageBufferBindingSize;
    required_limits.maxColorAttachmentBytesPerSample =
        supported_limits.maxColorAttachmentBytesPerSample;
    required_limits.maxComputeWorkgroupStorageSize =
        supported_limits.maxComputeWorkgroupStorageSize;
    required_limits.maxComputeInvocationsPerWorkgroup =
        supported_limits.maxComputeInvocationsPerWorkgroup;
    required_limits.maxComputeWorkgroupSizeX = supported_limits.maxComputeWorkgroupSizeX;
    desc.requiredLimits = &required_limits;
  }

  const std::shared_ptr<CallbackLifetime> callback_lifetime = callback_lifetime_;
  adapter_.RequestDevice(
      &desc,
      wgpu::CallbackMode::AllowSpontaneous,
      [callback_lifetime](
          wgpu::RequestDeviceStatus status, wgpu::Device d, wgpu::StringView msg) {
        callback_lifetime->deliver([&](GHOST_ContextWGPUWeb &owner) {
          if (status != wgpu::RequestDeviceStatus::Success || d == nullptr) {
            std::printf("WGPUWeb: RequestDevice failed: %.*s\n", int(msg.length), msg.data);
            owner.completeInitialization(false);
            return;
          }
          owner.device_ = std::move(d);
          owner.queue_ = owner.device_.GetQueue();
          if (!owner.deviceIsUsable()) {
            owner.completeInitialization(false);
            return;
          }
          if (owner.mode_ == ghost_web::DrawingContextMode::DeviceOnly) {
            owner.completeInitialization(true);
          }
          else {
            owner.finishSetup();
          }
        });
      });
}

void GHOST_ContextWGPUWeb::completeInitialization(const bool success)
{
  if (initialization_settled_) {
    return;
  }
  initialization_settled_ = true;
  ready_ = success;
  ReadyCallback on_ready = std::move(on_ready_);
  on_ready_ = nullptr;
  if (on_ready) {
    on_ready(success);
  }
}

bool GHOST_ContextWGPUWeb::deviceIsUsable()
{
  if (!ghost_web::device_state_allows_callback_work(device_state_)) {
    propagateDeviceLoss();
    return false;
  }
  return device_ != nullptr;
}

void GHOST_ContextWGPUWeb::propagateDeviceLoss()
{
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  auto owner_execution = lifetime->enter();
  if (!owner_execution) {
    return;
  }
  if (device_loss_propagated_) {
    return;
  }
  device_loss_propagated_ = true;
  ghost_web::device_state_mark_lost(*device_state_);
  callback_lifetime_->cancel();
  ready_ = false;
  configured_ = false;
  backbuffer_pending_ = false;
  present_pipeline_pending_ = false;
  present_pending_ = false;
  present_pipeline_ = nullptr;
  present_bgl_ = nullptr;
  backbuffer_ = nullptr;
  surface_ = nullptr;
  queue_ = nullptr;
  device_ = nullptr;
  std::printf("WGPUWeb: terminal device loss propagated; context disabled\n");
  completeInitialization(false);
}

void GHOST_ContextWGPUWeb::finishSetup()
{
  if (!deviceIsUsable()) {
    completeInitialization(false);
    return;
  }
  if (!ghost_web_canvas_resolvable(canvas_selector_.c_str())) {
    std::printf("WGPUWeb: canvas '%s' is not resolvable for a presentable context\n",
                canvas_selector_.c_str());
    completeInitialization(false);
    return;
  }

  /* The canvas-surface source is the key emdawnwebgpu-specific struct: native Dawn
   * spells it `SurfaceSourceCanvasHTMLSelector` (or platform SurfaceSource*), whereas
   * emdawnwebgpu uses `EmscriptenSurfaceSourceCanvasHTMLSelector`. See notes. */
  wgpu::EmscriptenSurfaceSourceCanvasHTMLSelector canvas_src = {};
  canvas_src.selector = canvas_selector_.c_str();

  wgpu::SurfaceDescriptor surf_desc = {};
  surf_desc.nextInChain = &canvas_src;
  surface_ = instance_.CreateSurface(&surf_desc);

  if (surface_ == nullptr) {
    std::printf("WGPUWeb: CreateSurface failed for '%s'\n", canvas_selector_.c_str());
    completeInitialization(false);
    return;
  }

  /* BGRA8Unorm is the universally-supported browser canvas format; keep it fixed so
   * one render pipeline serves the surface. (GetCapabilities().formats[0] would be the
   * more general query — noted as a follow-up in the design doc.) */
  surface_format_ = wgpu::TextureFormat::BGRA8Unorm;
  configureSurface(width_, height_);

  /* NB (M4.T21): the M4.T12 "surface-proof" teal clear that used to live here was removed.
   * Now that the backend renders into the persistent offscreen back-buffer and
   * swapBufferRelease -> presentBackbuffer blits it onto the surface every frame, an
   * unconditional teal clear at setup would stomp the first presented frame(s) whenever
   * finishSetup re-runs (it can fire more than once during boot), leaving the canvas teal
   * instead of the Blender UI. The whole OffscreenCanvas -> device -> surface path is now
   * proven by the live UI compositing, not by a debug clear. */
}

void GHOST_ContextWGPUWeb::configureSurface(uint32_t width, uint32_t height)
{
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  auto owner_execution = lifetime->enter();
  if (!owner_execution) {
    return;
  }
  if (!deviceIsUsable()) {
    return;
  }
  if (surface_ == nullptr || device_ == nullptr) {
    return;
  }

  /* DETERMINISM: the WebGPU surface must match the canvas element's drawing-buffer
   * extent EXACTLY. GetCurrentTexture returns a texture sized to the live canvas, so a
   * surface configured to a stale/other size (the GHOST window's logical size, which the
   * shell or browser pane can diverge the canvas from — the r19 1800x1169-surface vs
   * 1280x720-canvas mismatch that blocked golden capture) mis-presents. Query the real
   * canvas extent HERE and prefer it; the caller's width/height is only a fallback for
   * when the canvas does not resolve (a worker without an OffscreenCanvas). */
  int cw = 0, ch = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &cw, &ch);
  const uint32_t w = (cw > 0) ? uint32_t(cw) : width;
  const uint32_t h = (ch > 0) ? uint32_t(ch) : height;
  if (w == 0 || h == 0) {
    if (!initialization_settled_) {
      completeInitialization(false);
    }
    return;
  }
  /* Keep the latest browser request separate from the last complete published
   * surface/backbuffer state. ensureBackbuffer() allocates and validates first;
   * only its current-candidate callback may configure and publish the new extent. */
  requested_width_ = w;
  requested_height_ = h;
  ensureBackbuffer();
}

/* --- Persistent offscreen back-buffer + present (M4.T21) --------------------- */

void GHOST_ContextWGPUWeb::ensureBackbuffer()
{
  if (!deviceIsUsable()) {
    return;
  }
  if (device_ == nullptr ||
      !ghost_web::surface_resize_candidate_needed(configured_,
                                                   width_,
                                                   height_,
                                                   requested_width_,
                                                   requested_height_,
                                                   backbuffer_pending_,
                                                   backbuffer_ != nullptr,
                                                   backbuffer_w_,
                                                   backbuffer_h_))
  {
    return;
  }
  const uint32_t candidate_width = requested_width_;
  const uint32_t candidate_height = requested_height_;
  wgpu::TextureDescriptor td = {};
  td.label = "wgpu_web_backbuffer";
  td.dimension = wgpu::TextureDimension::e2D;
  td.size = {candidate_width, candidate_height, 1};
  td.format = surface_format_; /* BGRA8Unorm — same format the surface presents */
  td.mipLevelCount = 1;
  td.sampleCount = 1;
  /* RenderAttachment: the backend draws/composites here. TextureBinding: the present blit
   * textureLoad()s it into the surface (presentBackbuffer). CopySrc: the in-app
   * WM_window_pixels_read path can read it back (it now reads a LIVE persistent texture
   * instead of the destroyed transient surface). */
  td.usage = wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::TextureBinding |
             wgpu::TextureUsage::CopySrc;
  backbuffer_pending_ = true;
  const wgpu::Device device = device_;
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  const std::shared_ptr<ghost_web::DeviceCallbackState> device_state = device_state_;
  ghost_web::scoped_handle_create(
      [device]() { pushErrorScopes(device); },
      [device, &td]() { return device.CreateTexture(&td); },
      [device](auto completion) {
        popErrorScopes(device, "backbuffer creation", std::move(completion));
      },
      [lifetime, device_state, candidate_width, candidate_height](
          const bool valid, wgpu::Texture candidate) mutable {
        lifetime->deliver([&](GHOST_ContextWGPUWeb &owner) {
          if (!ghost_web::device_state_allows_callback_work(device_state)) {
            return;
          }
          if (!valid || candidate == nullptr) {
            owner.backbuffer_pending_ = false;
            std::printf("WGPUWeb: CreateTexture rejected for %ux%u backbuffer\n",
                        candidate_width,
                        candidate_height);
            if (!owner.initialization_settled_) {
              owner.completeInitialization(false);
            }
            return;
          }
          if (candidate_width != owner.requested_width_ ||
              candidate_height != owner.requested_height_)
          {
            owner.backbuffer_pending_ = false;
            owner.ensureBackbuffer();
            return;
          }

          wgpu::SurfaceConfiguration config = {};
          config.device = owner.device_;
          config.format = owner.surface_format_;
          /* RenderAttachment is what the compositor draws into; CopySrc additionally
           * lets the frame be read back. CopyDst remains deliberately absent because
           * emdawnwebgpu rejects it for browser canvas surfaces. */
          config.usage = wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::CopySrc;
          config.width = candidate_width;
          config.height = candidate_height;
          config.presentMode = wgpu::PresentMode::Fifo;
          config.alphaMode = wgpu::CompositeAlphaMode::Opaque;
          const wgpu::Device device = owner.device_;
          pushErrorScopes(device);
          owner.surface_.Configure(&config);
          popErrorScopes(
              device,
              "surface configuration",
              [lifetime,
               device_state,
               candidate = std::move(candidate),
               candidate_width,
               candidate_height](const bool configuration_valid) mutable {
                lifetime->deliver([&](GHOST_ContextWGPUWeb &owner) {
                  if (!ghost_web::device_state_allows_callback_work(device_state)) {
                    return;
                  }
                  owner.backbuffer_pending_ = false;
                  const ghost_web::SurfaceResizeResult result =
                      ghost_web::surface_resize_commit_if_current(
                          configuration_valid,
                          std::move(candidate),
                          candidate_width,
                          candidate_height,
                          owner.requested_width_,
                          owner.requested_height_,
                          [](const uint32_t /*width*/, const uint32_t /*height*/) {},
                          owner.backbuffer_,
                          owner.backbuffer_w_,
                          owner.backbuffer_h_,
                          owner.width_,
                          owner.height_,
                          owner.configured_);
                  if (result == ghost_web::SurfaceResizeResult::Rejected) {
                    /* A failed Configure leaves its prior state implementation-defined.
                     * Stop presenting until a later request validates a complete replacement. */
                    owner.configured_ = false;
                    std::printf("WGPUWeb: Surface::Configure rejected for %ux%u\n",
                                candidate_width,
                                candidate_height);
                    if (!owner.initialization_settled_) {
                      owner.completeInitialization(false);
                    }
                    return;
                  }
                  if (result == ghost_web::SurfaceResizeResult::Superseded) {
                    /* Configure already ran for the stale candidate. Block presentation and
                     * immediately validate/configure the latest requested extent. */
                    owner.configured_ = false;
                    owner.ensureBackbuffer();
                  }
                  if (result == ghost_web::SurfaceResizeResult::Committed) {
                    /* The resize request's earlier WindowUpdate may have run against the old
                     * backbuffer and exhausted the tail of a prior recovery episode. Start a
                     * fresh bounded episode only now that the replacement extent is coherent. */
                    ghost_web::request_redraw_episode();
                    owner.backbuffer_redraw_episode_ = ghost_web::redraw_episode_generation();
                    if (!owner.initialization_settled_) {
                      owner.completeInitialization(true);
                    }
                  }
                });
              });
        });
      });
}

void GHOST_ContextWGPUWeb::ensurePresentPipeline()
{
  if (!deviceIsUsable()) {
    return;
  }
  if (present_pipeline_ != nullptr || present_pipeline_pending_) {
    return;
  }
  /* Fullscreen-triangle blit. The fragment shader textureLoad()s the offscreen at the
   * render target's integer pixel coordinate (@builtin(position)), so surface(x,y) =
   * backbuffer(x,y) EXACTLY: a 1:1 upright copy with no UV/clip flip to reason about and
   * no sampler needed. BGRA8Unorm textureLoad returns the un-swizzled RGBA vec4 and the
   * BGRA8Unorm target re-swizzles on store, so the colour round-trips correctly. */
  const char *wgsl =
      "@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4<f32> {\n"
      "  var p = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0),\n"
      "                              vec2<f32>(-1.0, 3.0));\n"
      "  return vec4<f32>(p[i], 0.0, 1.0);\n"
      "}\n"
      "@group(0) @binding(0) var src: texture_2d<f32>;\n"
      "@fragment fn fs(@builtin(position) c: vec4<f32>) -> @location(0) vec4<f32> {\n"
      "  return textureLoad(src, vec2<i32>(i32(c.x), i32(c.y)), 0);\n"
      "}\n";
  present_pipeline_pending_ = true;
  const wgpu::Device device = device_;
  const wgpu::TextureFormat surface_format = surface_format_;
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  const std::shared_ptr<ghost_web::DeviceCallbackState> device_state = device_state_;
  ghost_web::present_pipeline_create_scoped(
          [device]() { pushErrorScopes(device); },
          [device, wgsl]() {
            wgpu::ShaderSourceWGSL wgsl_src = {};
            wgsl_src.code = wgsl;
            wgpu::ShaderModuleDescriptor sm_desc = {};
            sm_desc.nextInChain = &wgsl_src;
            return device.CreateShaderModule(&sm_desc);
          },
          [device]() {
            wgpu::BindGroupLayoutEntry bgl_entry = {};
            bgl_entry.binding = 0;
            bgl_entry.visibility = wgpu::ShaderStage::Fragment;
            bgl_entry.texture.sampleType = wgpu::TextureSampleType::UnfilterableFloat;
            bgl_entry.texture.viewDimension = wgpu::TextureViewDimension::e2D;
            wgpu::BindGroupLayoutDescriptor bgl_desc = {};
            bgl_desc.entryCount = 1;
            bgl_desc.entries = &bgl_entry;
            return device.CreateBindGroupLayout(&bgl_desc);
          },
          [device](const wgpu::BindGroupLayout &bind_group_layout) {
            wgpu::PipelineLayoutDescriptor pl_desc = {};
            pl_desc.bindGroupLayoutCount = 1;
            pl_desc.bindGroupLayouts = &bind_group_layout;
            return device.CreatePipelineLayout(&pl_desc);
          },
          [device, surface_format](const wgpu::ShaderModule &module,
                                   const wgpu::PipelineLayout &pipeline_layout) {
            wgpu::ColorTargetState color_target = {};
            color_target.format = surface_format;
            wgpu::FragmentState frag = {};
            frag.module = module;
            frag.entryPoint = "fs";
            frag.targetCount = 1;
            frag.targets = &color_target;

            wgpu::RenderPipelineDescriptor rp_desc = {};
            rp_desc.layout = pipeline_layout;
            rp_desc.vertex.module = module;
            rp_desc.vertex.entryPoint = "vs";
            rp_desc.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
            rp_desc.fragment = &frag;
            return device.CreateRenderPipeline(&rp_desc);
          },
          [device](auto completion) {
            popErrorScopes(device, "present pipeline creation", std::move(completion));
          },
          [lifetime, device_state](const bool valid,
                                   wgpu::BindGroupLayout bind_group_layout,
                                   wgpu::RenderPipeline pipeline) mutable {
            lifetime->deliver([&](GHOST_ContextWGPUWeb &owner) {
              if (!ghost_web::device_state_allows_callback_work(device_state)) {
                return;
              }
              owner.present_pipeline_pending_ = false;
              if (!valid) {
                std::printf("WGPUWeb: present pipeline creation rejected\n");
                return;
              }
              owner.present_bgl_ = std::move(bind_group_layout);
              owner.present_pipeline_ = std::move(pipeline);
            });
          });
}

bool GHOST_ContextWGPUWeb::presentBackbuffer()
{
  if (!deviceIsUsable() || surface_ == nullptr || present_pending_) {
    return false;
  }

  /* A rejected resize remains requested. Every later frame can recreate it, so
   * recovery does not depend on the browser delivering a duplicate resize event. */
  ensureBackbuffer();
  if (backbuffer_pending_ || !configured_ || backbuffer_ == nullptr) {
    return false;
  }
  wgpu::SurfaceTexture st = {};
  surface_.GetCurrentTexture(&st);
  const ghost_web::SurfaceAcquireAction acquire_action =
      ghost_web::surface_acquire_action(surface_acquire_status(st.status), st.texture != nullptr);
  if (!ghost_web::surface_acquire_can_present(acquire_action)) {
    if (acquire_action == ghost_web::SurfaceAcquireAction::Reconfigure) {
      /* emdawnwebgpu maps a browser getCurrentTexture() exception to Error. Force
       * a fresh Configure on the next frame instead of retrying broken state forever. */
      configured_ = false;
    }
    else if (acquire_action == ghost_web::SurfaceAcquireAction::Recreate) {
      /* A lost surface cannot be repaired by Configure alone. Recreate it from the
       * still-live transferred canvas; the async backbuffer/configuration path gates use. */
      configured_ = false;
      surface_ = nullptr;
      finishSetup();
    }
    return false;
  }
  const bool reconfigure_after_present =
      acquire_action == ghost_web::SurfaceAcquireAction::PresentAndReconfigure;
  const uint32_t surface_width = st.texture.GetWidth();
  const uint32_t surface_height = st.texture.GetHeight();
  if (!ghost_web::surface_resize_present_coherent(configured_,
                                                   width_,
                                                   height_,
                                                   backbuffer_ != nullptr,
                                                   backbuffer_w_,
                                                   backbuffer_h_,
                                                   surface_width,
                                                   surface_height))
  {
    /* The live canvas can change independently of a GHOST resize callback. Record
     * what GetCurrentTexture observed and begin a coherent replacement, but never
     * sample the stale backbuffer into the mismatched surface. */
    configureSurface(surface_width, surface_height);
    return false;
  }
  ensurePresentPipeline();
  if (present_pipeline_ == nullptr) {
    return false;
  }

  const wgpu::Device device = device_;
  const wgpu::Queue queue = queue_;
  const wgpu::Texture source_texture = backbuffer_;
  const wgpu::Texture target_texture = st.texture;
  const wgpu::BindGroupLayout bind_group_layout = present_bgl_;
  const wgpu::RenderPipeline pipeline = present_pipeline_;
  const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
  const std::shared_ptr<ghost_web::DeviceCallbackState> device_state = device_state_;
  const uint64_t live_redraw_trace_episode = ghost_web::redraw_episode_generation();
  const uint64_t barrier_ready_episode = ghost_web::redraw_present_barrier_ready_episode();
  const ghost_web::RedrawTraceSnapshot barrier_redraw_trace =
      ghost_web::redraw_present_barrier_ready_trace_snapshot();
  const bool barrier_redraw_trace_available =
      barrier_ready_episode != 0 &&
      barrier_redraw_trace.episode_generation == barrier_ready_episode;
  const uint64_t redraw_trace_episode =
      barrier_redraw_trace_available ? barrier_ready_episode : live_redraw_trace_episode;
  const bool redraw_trace_active = ghost_web::redraw_trace_active(redraw_trace_episode);
  const ghost_web::RedrawTraceSnapshot live_redraw_trace = ghost_web::redraw_trace_snapshot();
  const ghost_web::RedrawTraceSnapshot redraw_trace =
      barrier_redraw_trace_available ? barrier_redraw_trace : live_redraw_trace;
  /* A correctly frame-bound barrier can outlive the 180-tick redraw heartbeat while a slow
   * software adapter drains its complete frame. Use the immutable snapshot captured at that
   * frame's end, not the later synthetic WindowUpdate's mutable plans, so a failing hardware run
   * describes the exact backbuffer content admitted to presentation. */
  const bool redraw_trace_available =
      redraw_trace.episode_generation == redraw_trace_episode &&
      (redraw_trace_active || barrier_redraw_trace_available);
  const uint32_t configured_width = width_;
  const uint32_t configured_height = height_;
  const uint32_t requested_width = requested_width_;
  const uint32_t requested_height = requested_height_;
  const uint32_t backbuffer_width = backbuffer_w_;
  const uint32_t backbuffer_height = backbuffer_h_;
  present_pending_ = true;
  ghost_web::present_frame_encode_submit_scoped(
          [device]() { pushErrorScopes(device); },
          [source_texture]() { return source_texture.CreateView(); },
          [target_texture]() { return target_texture.CreateView(); },
          [device, bind_group_layout](const wgpu::TextureView &source_view) {
            wgpu::BindGroupEntry bg_entry = {};
            bg_entry.binding = 0;
            bg_entry.textureView = source_view;
            wgpu::BindGroupDescriptor bg_desc = {};
            bg_desc.layout = bind_group_layout;
            bg_desc.entryCount = 1;
            bg_desc.entries = &bg_entry;
            return device.CreateBindGroup(&bg_desc);
          },
          [device]() { return device.CreateCommandEncoder(); },
          [](wgpu::CommandEncoder &encoder, const wgpu::TextureView &target_view) {
            wgpu::RenderPassColorAttachment ca = {};
            ca.view = target_view;
            ca.loadOp = wgpu::LoadOp::Clear;
            ca.storeOp = wgpu::StoreOp::Store;
            ca.clearValue = {0.0, 0.0, 0.0, 1.0};
            wgpu::RenderPassDescriptor rp = {};
            rp.colorAttachmentCount = 1;
            rp.colorAttachments = &ca;
            return encoder.BeginRenderPass(&rp);
          },
          [pipeline](wgpu::RenderPassEncoder &pass, const wgpu::BindGroup &bind_group) {
            pass.SetPipeline(pipeline);
            pass.SetBindGroup(0, bind_group);
            pass.Draw(3);
          },
          [device](auto completion) {
            popErrorScopes(device, "present command encoding", std::move(completion));
          },
          [device]() { pushErrorScopes(device); },
          [lifetime, device_state, queue](const wgpu::CommandBuffer &command_buffer) {
            lifetime->deliver([&](GHOST_ContextWGPUWeb & /*owner*/) {
              if (ghost_web::device_state_allows_callback_work(device_state)) {
                queue.Submit(1, &command_buffer);
              }
            });
          },
          [device](auto completion) {
            popErrorScopes(device, "present queue submission", std::move(completion));
          },
          [lifetime,
           device_state,
           surface_width,
           surface_height,
           reconfigure_after_present,
           redraw_trace_episode,
           redraw_trace_available,
           redraw_trace,
           configured_width,
           configured_height,
           requested_width,
           requested_height,
           backbuffer_width,
           backbuffer_height](const bool valid) {
            lifetime->deliver([&](GHOST_ContextWGPUWeb &owner) {
              if (!ghost_web::device_state_allows_callback_work(device_state)) {
                return;
              }
              owner.present_pending_ = false;
              if (reconfigure_after_present) {
                owner.configured_ = false;
              }
              if (!valid) {
                std::printf("WGPUWeb: present transaction rejected\n");
                return;
              }
              /* Bounded "present path live" marker (first 2 frames only): confirms a validated
               * command buffer reached the queue without a submit-scope error. */
              static int present_log_count = 0;
              if (present_log_count < 2) {
                std::printf(
                    "WGPUWeb: presentBackbuffer frame %d — surface %ux%u -> canvas "
                    "(offscreen blit)\n",
                    present_log_count,
                    surface_width,
                    surface_height);
                present_log_count++;
              }
              /* Hardware-only P0-E diagnostic: one line per successful present while the
               * coherent-resize recovery episode is active. The cumulative draw sequences show
               * whether Blender re-encoded the frame between presents; the dedicated background
               * and display records expose the exact target, viewport, and scissor that reached
               * WebGPU. Both per-episode and process caps keep this absent from steady state. */
              static uint64_t resize_trace_episode_seen = 0;
              static uint32_t resize_trace_episode_samples = 0;
              static uint32_t resize_trace_total_samples = 0;
              if (redraw_trace_available && resize_trace_total_samples < 64) {
                if (redraw_trace_episode != resize_trace_episode_seen) {
                  resize_trace_episode_seen = redraw_trace_episode;
                  resize_trace_episode_samples = 0;
                }
                if (resize_trace_episode_samples < 24) {
                  const ghost_web::RedrawTracePlan &any = redraw_trace.last;
                  const ghost_web::RedrawTracePlan &background = redraw_trace.background;
                  const ghost_web::RedrawTracePlan &display = redraw_trace.display;
                  std::printf(
                      "WGPUWeb-resize-trace: episode=%llu sample=%u present=%llu "
                      "draws=%llu window_draws=%llu surface=%ux%u configured=%ux%u "
                      "requested=%ux%u backbuffer=%ux%u "
                      "any=%llu/%d/%dx%d/vp%d,%d,%ux%u/sc%d,%u,%u,%ux%u "
                      "background=%llu/%d/%dx%d/vp%d,%d,%ux%u/sc%d,%u,%u,%ux%u "
                      "display=%llu/%d/%dx%d/vp%d,%d,%ux%u/sc%d,%u,%u,%ux%u\n",
                      static_cast<unsigned long long>(redraw_trace_episode),
                      resize_trace_episode_samples,
                      static_cast<unsigned long long>(ghost_web::present_count() + 1u),
                      static_cast<unsigned long long>(redraw_trace.draw_count),
                      static_cast<unsigned long long>(redraw_trace.window_draw_count),
                      surface_width,
                      surface_height,
                      configured_width,
                      configured_height,
                      requested_width,
                      requested_height,
                      backbuffer_width,
                      backbuffer_height,
                      static_cast<unsigned long long>(any.sequence),
                      any.window_target ? 1 : 0,
                      any.target_width,
                      any.target_height,
                      any.viewport_x,
                      any.viewport_y,
                      any.viewport_width,
                      any.viewport_height,
                      any.scissor_enabled ? 1 : 0,
                      any.scissor_x,
                      any.scissor_y,
                      any.scissor_width,
                      any.scissor_height,
                      static_cast<unsigned long long>(background.sequence),
                      background.window_target ? 1 : 0,
                      background.target_width,
                      background.target_height,
                      background.viewport_x,
                      background.viewport_y,
                      background.viewport_width,
                      background.viewport_height,
                      background.scissor_enabled ? 1 : 0,
                      background.scissor_x,
                      background.scissor_y,
                      background.scissor_width,
                      background.scissor_height,
                      static_cast<unsigned long long>(display.sequence),
                      display.window_target ? 1 : 0,
                      display.target_width,
                      display.target_height,
                      display.viewport_x,
                      display.viewport_y,
                      display.viewport_width,
                      display.viewport_height,
                      display.scissor_enabled ? 1 : 0,
                      display.scissor_x,
                      display.scissor_y,
                      display.scissor_width,
                      display.scissor_height);
                  resize_trace_episode_samples++;
                  resize_trace_total_samples++;
                  if (resize_trace_episode_samples == 24 ||
                      resize_trace_total_samples == 64)
                  {
                    ghost_web::redraw_trace_finish(redraw_trace_episode);
                  }
                }
              }
              /* ghost-keepalive advances only after the submission scope completes cleanly. */
              ghost_web::note_present();
            });
          });
  /* The browser auto-presents `st.texture` when this rAF tick yields. Acquire, render-pass
   * encoding, and queue submission happen synchronously above; only the two error-scope results
   * settle later, while present_pending_ prevents another in-flight transaction. */
  return true;
}
