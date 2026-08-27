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
 * mirrors) is that browser adapter and device requests are genuine JavaScript promises.
 * Blocking their event loop with Dawn's native finite WaitAny path would deadlock their
 * completion. The class-level contract below documents the two supported ways this port
 * crosses that asynchronous boundary.
 */

#pragma once

#include <atomic>
#include <functional>
#include <memory>
#include <string>

#include <webgpu/webgpu_cpp.h>

#include "GHOST_Context.hh"
#include "GHOST_WebDisplayState.hh"
#include "GHOST_WGPUTransaction.hh"

/**
 * The class derives from `GHOST_Context` and has two deliberately separate
 * initialization paths.
 *
 * Shipping path: `wgpu-preinit-worker.js` asynchronously acquires a device on the WM
 * worker and, for a presentable window, validates the canvas, surface, and initial
 * backbuffer before `main()`. `initializeDrawingContext()` then synchronously imports
 * the mode-appropriate pre-main bundle. The shipping path does not call `initAsync()`.
 *
 * Standalone proof path: `initAsync()` asynchronously requests an adapter and device
 * through `CallbackMode::AllowSpontaneous`, creates the requested presentation
 * resources, and invokes its ready callback when acquisition settles.
 *
 * Both paths serialize asynchronous callback delivery and public owner access through
 * the shared `CallbackLifetime` execution gate. Destruction closes admission and waits
 * for admitted work before releasing context storage.
 */
class GHOST_ContextWGPUWeb : public GHOST_Context {
 private:
  using CallbackLifetime = ghost_web::OwnerCallbackLifetime<GHOST_ContextWGPUWeb>;

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
  /** Acquire, encode, and submit the persistent-backbuffer blit synchronously. Immediate
   * failures are returned here; scoped validation settles asynchronously before publication. */
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
    const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
    auto owner_execution = lifetime->enter();
    if (!owner_execution) {
      return false;
    }
    return ready_ && ghost_web::device_state_allows_callback_work(device_state_);
  }

  /** (Re)configure the canvas surface for the current size. */
  void configureSurface(uint32_t width, uint32_t height);

  wgpu::Instance getInstance() const
  {
    const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
    auto owner_execution = lifetime->enter();
    if (!owner_execution) {
      return {};
    }
    return ghost_web::device_state_allows_callback_work(device_state_) ?
               instance_ :
               wgpu::Instance();
  }
  wgpu::Adapter getAdapter() const
  {
    const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
    auto owner_execution = lifetime->enter();
    if (!owner_execution) {
      return {};
    }
    return ghost_web::device_state_allows_callback_work(device_state_) ?
               adapter_ :
               wgpu::Adapter();
  }
  wgpu::Device getDevice() const
  {
    const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
    auto owner_execution = lifetime->enter();
    if (!owner_execution) {
      return {};
    }
    return ghost_web::device_state_allows_callback_work(device_state_) ?
               device_ :
               wgpu::Device();
  }
  wgpu::Queue getQueue() const
  {
    const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
    auto owner_execution = lifetime->enter();
    if (!owner_execution) {
      return {};
    }
    return ghost_web::device_state_allows_callback_work(device_state_) ?
               queue_ :
               wgpu::Queue();
  }
  wgpu::Surface getSurface() const
  {
    const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
    auto owner_execution = lifetime->enter();
    if (!owner_execution) {
      return {};
    }
    return ghost_web::device_state_allows_callback_work(device_state_) ?
               surface_ :
               wgpu::Surface();
  }
  wgpu::TextureFormat getSurfaceFormat() const
  {
    const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
    auto owner_execution = lifetime->enter();
    if (!owner_execution) {
      return wgpu::TextureFormat::BGRA8Unorm;
    }
    return surface_format_;
  }
  struct BackbufferFrameSnapshot {
    wgpu::Texture texture;
    wgpu::TextureFormat format = wgpu::TextureFormat::BGRA8Unorm;
    uint32_t width = 0;
    uint32_t height = 0;
    uint64_t redraw_episode = 0;
  };

  /* The PERSISTENT offscreen back-buffer the WebGPU backend renders into every frame
   * (M4.T21). Unlike the surface's per-frame GetCurrentTexture() — which the browser
   * destroys on event-loop yield, so any command buffer that outlives the rAF tick
   * submits a "Destroyed texture … WebgpuSwapChainTexture" — this texture has NO
   * per-frame lifetime: the backend adopts it once into back_left/front_left and every
   * viewport/overlay/UI pass accumulates here with zero surface references. It is
   * blitted to the real surface as the LAST op of each frame in swapBufferRelease().
   * The texture, format, extent, and resize episode are one lifetime-gated snapshot:
   * an AllowSpontaneous resize completion must not interleave an old texture with the
   * new episode. The texture is null until configureSurface() has run. */
  BackbufferFrameSnapshot getBackbufferFrameSnapshot() const
  {
    const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;
    auto owner_execution = lifetime->enter();
    if (!owner_execution) {
      return {};
    }
    if (!ghost_web::device_state_allows_callback_work(device_state_)) {
      return {};
    }
    return {backbuffer_,
            surface_format_,
            backbuffer_w_,
            backbuffer_h_,
            backbuffer_redraw_episode_};
  }

 private:
  using ErrorScopeCallback = std::function<void(bool)>;

  void requestAdapter();
  void requestDevice();
  void finishSetup();
  void completeInitialization(bool success);
  /** Sample the exact imported-device promise or fallback descriptor callback. */
  bool deviceIsUsable();
  /** Publish one terminal context transition and disable every outstanding callback. */
  void propagateDeviceLoss();
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
  bool presentBackbuffer();

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
  /* Persistent offscreen back-buffer (see getBackbufferFrameSnapshot). Recreated on resize. */
  wgpu::Texture backbuffer_;
  uint32_t backbuffer_w_ = 0;
  uint32_t backbuffer_h_ = 0;
  /** Redraw episode committed with backbuffer_ under callback_lifetime_'s execution gate. */
  uint64_t backbuffer_redraw_episode_ = 0;
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
  std::shared_ptr<ghost_web::DeviceCallbackState> device_state_ =
      std::make_shared<ghost_web::DeviceCallbackState>();
  bool device_loss_propagated_ = false;
  /** Every browser completion retains this synchronized gate, never a bare owner pointer. */
  std::shared_ptr<CallbackLifetime> callback_lifetime_;
};
