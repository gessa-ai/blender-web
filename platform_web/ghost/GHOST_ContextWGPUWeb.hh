/* SPDX-FileCopyrightText: 2022-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from intern/ghost/intern/GHOST_ContextWGPU.hh (native Dawn,
 * patch 0011) @ fbe6228777e7. */

/** \file
 * \ingroup GHOST-web
 *
 * GHOST_ContextWGPUWeb — the BROWSER twin of the native GHOST_ContextWGPU: a WebGPU
 * drawing context obtained through emdawnwebgpu (--use-port=emdawnwebgpu) against the
 * browser's own WebGPU, with a real <canvas> surface.
 *
 * The load-bearing difference from the native context (which this file otherwise
 * mirrors) is ASYNC DEVICE ACQUISITION. Native Dawn drives instance->adapter->device
 * synchronously with `instance.WaitAny(..., TimedWaitAny)` on the calling thread. In
 * the browser that is impossible: `requestAdapter`/`requestDevice` are genuine JS
 * promises, and blocking the main thread with a finite WaitAny would deadlock the very
 * event loop that resolves them. So we use `CallbackMode::AllowSpontaneous` and let the
 * callbacks fire off the event loop — `initAsync()` returns immediately and invokes the
 * ready-callback once the device + surface exist. See notes/ghost-web-wgpu-context.md
 * for how this maps onto GHOST_Context's synchronous initializeDrawingContext() for M4
 * (a one-time top-level await, per ADR-003).
 *
 * Standalone (like the event layer / GPU sandbox modules): does NOT subclass
 * GHOST_Context here, to keep the async lifecycle honest and avoid dragging the GHOST
 * base link into a context-only proof. The accessors mirror GHOST_ContextWGPU so the
 * WebGPU backend can pull the same live handles.
 */

#pragma once

#include <atomic>
#include <functional>
#include <memory>
#include <string>

#include <webgpu/webgpu_cpp.h>

#include "GHOST_Context.hh"
#include "GHOST_WGPUTransaction.hh"

/* M4 T4: promoted to derive GHOST_Context so it can be returned from
 * GHOST_WindowWeb::newDrawingContext() / GHOST_SystemWeb::createOffscreenContext()
 * (which must return GHOST_Context*). The six GHOST_Context pure virtuals are
 * implemented below. Async device acquisition (initAsync) is bridged to the
 * SYNCHRONOUS initializeDrawingContext() contract by a one-time startup await:
 * the GHOST-web system runs initAsync and gates the WM main-loop start on the
 * ready-callback, so by the time createWindow -> newDrawingContext ->
 * initializeDrawingContext runs, the device is already acquired. See
 * notes/ghost-web-wgpu-context.md + notes/m4-integration.md. */
class GHOST_ContextWGPUWeb : public GHOST_Context {
 public:
  /** Called once after the selected device-only or presentable initialization settles. */
  using ReadyCallback = std::function<void(bool success)>;

  GHOST_ContextWGPUWeb(const GHOST_ContextParams &context_params,
                       const char *canvas_selector,
                       ghost_web::DrawingContextMode mode);
  ~GHOST_ContextWGPUWeb() override;

  /* --- GHOST_Context surface (6 pure virtuals) -------------------------------- */

  /** Synchronous GHOST entry. The pre-main worker supplies a device for every mode and a
   * validated surface/backbuffer bundle for PresentableWindow mode. */
  GHOST_TSuccess initializeDrawingContext() override;
  GHOST_TSuccess releaseNativeHandles() override;
  GHOST_TSuccess swapBufferAcquire() override;
  /** No-op on the web: the browser auto-presents the configured canvas on
   * event-loop yield (wgpu-context note delta #3). */
  GHOST_TSuccess swapBufferRelease() override;
  /** No-op: WebGPU's implicit device model has no "current context" to activate. */
  GHOST_TSuccess activateDrawingContext() override;
  GHOST_TSuccess releaseDrawingContext() override;

  /**
   * Acquire instance -> adapter -> device -> queue and, for PresentableWindow mode,
   * the canvas surface plus initial backbuffer, then invoke \a on_ready. Returns
   * immediately; the work completes off the event loop.
   */
  void initAsync(uint32_t width, uint32_t height, ReadyCallback on_ready);

  bool isReady() const
  {
    return ready_;
  }

  /** (Re)configure the canvas surface for the current size. */
  void configureSurface(uint32_t width, uint32_t height);

  wgpu::Instance getInstance() const
  {
    return instance_;
  }
  wgpu::Adapter getAdapter() const
  {
    return adapter_;
  }
  wgpu::Device getDevice() const
  {
    return device_;
  }
  wgpu::Queue getQueue() const
  {
    return queue_;
  }
  wgpu::Surface getSurface() const
  {
    return surface_;
  }
  wgpu::TextureFormat getSurfaceFormat() const
  {
    return surface_format_;
  }
  /* The PERSISTENT offscreen back-buffer the WebGPU backend renders into every frame
   * (M4.T21). Unlike the surface's per-frame GetCurrentTexture() — which the browser
   * destroys on event-loop yield, so any command buffer that outlives the rAF tick
   * submits a "Destroyed texture … WebgpuSwapChainTexture" — this texture has NO
   * per-frame lifetime: the backend adopts it once into back_left/front_left and every
   * viewport/overlay/UI pass accumulates here with zero surface references. It is
   * blitted to the real surface as the LAST op of each frame in swapBufferRelease().
   * Null until configureSurface() has run. */
  wgpu::Texture getBackbufferTexture() const
  {
    return backbuffer_;
  }

 private:
  using ErrorScopeCallback = std::function<void(bool)>;

  void requestAdapter();
  void requestDevice();
  void finishSetup();
  void completeInitialization(bool success);
  /** Push/pop the validation, OOM, and internal scopes used by every fallible present
   * transaction. Completion is asynchronous in the browser. */
  static void pushErrorScopes(const wgpu::Device &device);
  static void popErrorScopes(const wgpu::Device &device,
                             std::string label,
                             ErrorScopeCallback on_complete);
  /* (Re)create the persistent offscreen back-buffer for the latest requested extent. */
  void ensureBackbuffer();
  /* Lazily build the fullscreen-triangle present pipeline (once). */
  void ensurePresentPipeline();
  /* Present: render-pass blit the offscreen back-buffer onto the surface's current texture
   * and submit, within the caller's rAF tick (swapBufferRelease). */
  void presentBackbuffer();

  std::string canvas_selector_;
  ghost_web::DrawingContextMode mode_ = ghost_web::DrawingContextMode::PresentableWindow;
  uint32_t width_ = 0;
  uint32_t height_ = 0;
  bool configured_ = false; /* surface_.Configure has run at width_ x height_ */
  /* Latest live-canvas extent requested by configureSurface(). This remains
   * separate from the authoritative configured extent until a validated
   * backbuffer candidate can publish the complete size-bound state. */
  uint32_t requested_width_ = 0;
  uint32_t requested_height_ = 0;

  wgpu::Instance instance_;
  wgpu::Adapter adapter_;
  wgpu::Device device_;
  wgpu::Queue queue_;
  wgpu::Surface surface_;
  wgpu::TextureFormat surface_format_ = wgpu::TextureFormat::BGRA8Unorm;
  /* Persistent offscreen back-buffer (see getBackbufferTexture). Recreated on resize. */
  wgpu::Texture backbuffer_;
  uint32_t backbuffer_w_ = 0;
  uint32_t backbuffer_h_ = 0;
  bool backbuffer_pending_ = false;

  /* Present blit: a fullscreen-triangle render pass that textureLoad()s the offscreen
   * back-buffer 1:1 into the surface's RenderAttachment. Uses only RenderAttachment (dst)
   * + TextureBinding (src) — both universally supported for a browser canvas — so it does
   * NOT depend on the surface accepting a CopyDst (which emdawnwebgpu rejects, leaving the
   * canvas stuck on its last render-pass content). Built lazily, once. */
  wgpu::RenderPipeline present_pipeline_;
  wgpu::BindGroupLayout present_bgl_;
  bool present_pipeline_pending_ = false;
  bool present_pending_ = false;

  ReadyCallback on_ready_;
  bool ready_ = false;
  bool initialization_settled_ = false;
  /** Error-scope callbacks may resolve after this C++ object starts destruction. */
  std::shared_ptr<std::atomic<bool>> callback_lifetime_ =
      std::make_shared<std::atomic<bool>>(true);
};
