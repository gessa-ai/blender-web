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

#include <functional>
#include <string>

#include <webgpu/webgpu_cpp.h>

#include "GHOST_Context.hh"

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
  /** Called once with success=true after device+surface are ready, or false on failure. */
  using ReadyCallback = std::function<void(bool success)>;

  GHOST_ContextWGPUWeb(const GHOST_ContextParams &context_params, const char *canvas_selector);
  ~GHOST_ContextWGPUWeb() override;

  /* --- GHOST_Context surface (6 pure virtuals) -------------------------------- */

  /** Synchronous GHOST entry. Requires the device to be pre-acquired via a startup
   * initAsync() await (see class note); returns success once ready. */
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
   * Acquire instance -> adapter -> device -> queue and the canvas surface, then
   * invoke \a on_ready. Returns immediately; the work completes off the event loop.
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

 private:
  void requestAdapter();
  void requestDevice();
  void finishSetup();

  std::string canvas_selector_;
  uint32_t width_ = 0;
  uint32_t height_ = 0;
  bool configured_ = false; /* surface_.Configure has run at width_ x height_ */

  wgpu::Instance instance_;
  wgpu::Adapter adapter_;
  wgpu::Device device_;
  wgpu::Queue queue_;
  wgpu::Surface surface_;
  wgpu::TextureFormat surface_format_ = wgpu::TextureFormat::BGRA8Unorm;

  ReadyCallback on_ready_;
  bool ready_ = false;
};
