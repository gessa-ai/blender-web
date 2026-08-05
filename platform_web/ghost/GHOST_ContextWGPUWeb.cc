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

#include <cstdint>
#include <cstdio>
#include <utility>

#include <emscripten/html5.h>

GHOST_ContextWGPUWeb::GHOST_ContextWGPUWeb(const GHOST_ContextParams &context_params,
                                           const char *canvas_selector)
    : GHOST_Context(context_params),
      canvas_selector_(canvas_selector ? canvas_selector : "#canvas")
{
}

GHOST_ContextWGPUWeb::~GHOST_ContextWGPUWeb() = default;

/* --- GHOST_Context surface --------------------------------------------------- */

GHOST_TSuccess GHOST_ContextWGPUWeb::initializeDrawingContext()
{
  /* If a prior initAsync() already acquired the device (callback path, e.g. the
   * standalone harness), we are done. */
  if (ready_) {
    return GHOST_kSuccess;
  }

  /* Windowed (GHOST) path: acquire the device SYNCHRONOUSLY via wgpu WaitAny. Under
   * -sJSPI (the windowed browser link) WaitAny SUSPENDS — it yields to the browser
   * event loop that resolves the future and then resumes — instead of blocking the
   * main thread (which would deadlock). This is the one-time top-level startup await
   * ADR-003 permits; it mirrors the native GHOST_ContextWGPU acquisition. */
  wgpu::InstanceDescriptor idesc = {};
  static constexpr auto kTimedWaitAny = wgpu::InstanceFeatureName::TimedWaitAny;
  idesc.requiredFeatureCount = 1;
  idesc.requiredFeatures = &kTimedWaitAny;
  instance_ = wgpu::CreateInstance(&idesc);
  if (instance_ == nullptr) {
    std::printf("WGPUWeb: CreateInstance failed\n");
    return GHOST_kFailure;
  }

  wgpu::RequestAdapterOptions aopts = {};
  aopts.powerPreference = wgpu::PowerPreference::HighPerformance;
  instance_.WaitAny(
      instance_.RequestAdapter(
          &aopts,
          wgpu::CallbackMode::WaitAnyOnly,
          [this](wgpu::RequestAdapterStatus status, wgpu::Adapter a, wgpu::StringView /*msg*/) {
            if (status == wgpu::RequestAdapterStatus::Success) {
              adapter_ = std::move(a);
            }
          }),
      UINT64_MAX);
  if (adapter_ == nullptr) {
    std::printf("WGPUWeb: RequestAdapter failed (sync)\n");
    return GHOST_kFailure;
  }

  wgpu::DeviceDescriptor ddesc = {};
  ddesc.SetUncapturedErrorCallback(
      [](const wgpu::Device & /*d*/, wgpu::ErrorType type, wgpu::StringView msg) {
        std::printf("WGPUWeb: uncaptured error (%d): %.*s\n", int(type), int(msg.length), msg.data);
      });
  instance_.WaitAny(
      adapter_.RequestDevice(
          &ddesc,
          wgpu::CallbackMode::WaitAnyOnly,
          [this](wgpu::RequestDeviceStatus status, wgpu::Device d, wgpu::StringView /*msg*/) {
            if (status == wgpu::RequestDeviceStatus::Success) {
              device_ = std::move(d);
            }
          }),
      UINT64_MAX);
  if (device_ == nullptr) {
    std::printf("WGPUWeb: RequestDevice failed (sync)\n");
    return GHOST_kFailure;
  }
  queue_ = device_.GetQueue();

  /* Canvas size from the DOM (the GHOST_WindowWeb already sized the canvas). */
  int cw = 0, ch = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &cw, &ch);
  width_ = uint32_t(cw > 0 ? cw : 1);
  height_ = uint32_t(ch > 0 ? ch : 1);
  finishSetup(); /* creates + configures the surface, sets ready_ */
  return ready_ ? GHOST_kSuccess : GHOST_kFailure;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::releaseNativeHandles()
{
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferAcquire()
{
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferRelease()
{
  /* Browser auto-presents the configured canvas on event-loop yield — no Present(). */
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::activateDrawingContext()
{
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::releaseDrawingContext()
{
  return GHOST_kSuccess;
}

void GHOST_ContextWGPUWeb::initAsync(uint32_t width, uint32_t height, ReadyCallback on_ready)
{
  width_ = width;
  height_ = height;
  on_ready_ = std::move(on_ready);

  /* No TimedWaitAny feature here: the browser drives callbacks off the event loop
   * (AllowSpontaneous), so we never block-wait. */
  instance_ = wgpu::CreateInstance(nullptr);
  if (instance_ == nullptr) {
    std::printf("WGPUWeb: CreateInstance failed\n");
    if (on_ready_) {
      on_ready_(false);
    }
    return;
  }
  requestAdapter();
}

void GHOST_ContextWGPUWeb::requestAdapter()
{
  wgpu::RequestAdapterOptions opts = {};
  opts.powerPreference = wgpu::PowerPreference::HighPerformance;

  instance_.RequestAdapter(
      &opts,
      wgpu::CallbackMode::AllowSpontaneous,
      [this](wgpu::RequestAdapterStatus status, wgpu::Adapter a, wgpu::StringView msg) {
        if (status != wgpu::RequestAdapterStatus::Success || a == nullptr) {
          std::printf("WGPUWeb: RequestAdapter failed: %.*s\n", int(msg.length), msg.data);
          if (on_ready_) {
            on_ready_(false);
          }
          return;
        }
        adapter_ = std::move(a);
        requestDevice();
      });
}

void GHOST_ContextWGPUWeb::requestDevice()
{
  wgpu::DeviceDescriptor desc = {};
  desc.SetUncapturedErrorCallback(
      [](const wgpu::Device & /*d*/, wgpu::ErrorType type, wgpu::StringView msg) {
        std::printf("WGPUWeb: uncaptured error (%d): %.*s\n", int(type), int(msg.length), msg.data);
      });

  adapter_.RequestDevice(
      &desc,
      wgpu::CallbackMode::AllowSpontaneous,
      [this](wgpu::RequestDeviceStatus status, wgpu::Device d, wgpu::StringView msg) {
        if (status != wgpu::RequestDeviceStatus::Success || d == nullptr) {
          std::printf("WGPUWeb: RequestDevice failed: %.*s\n", int(msg.length), msg.data);
          if (on_ready_) {
            on_ready_(false);
          }
          return;
        }
        device_ = std::move(d);
        queue_ = device_.GetQueue();
        finishSetup();
      });
}

void GHOST_ContextWGPUWeb::finishSetup()
{
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
    if (on_ready_) {
      on_ready_(false);
    }
    return;
  }

  /* BGRA8Unorm is the universally-supported browser canvas format; keep it fixed so
   * one render pipeline serves the surface. (GetCapabilities().formats[0] would be the
   * more general query — noted as a follow-up in the design doc.) */
  surface_format_ = wgpu::TextureFormat::BGRA8Unorm;
  configureSurface(width_, height_);

  ready_ = true;
  if (on_ready_) {
    on_ready_(true);
  }
}

void GHOST_ContextWGPUWeb::configureSurface(uint32_t width, uint32_t height)
{
  if (surface_ == nullptr || device_ == nullptr) {
    return;
  }
  width_ = width;
  height_ = height;

  wgpu::SurfaceConfiguration config = {};
  config.device = device_;
  config.format = surface_format_;
  config.usage = wgpu::TextureUsage::RenderAttachment;
  config.width = width_;
  config.height = height_;
  config.presentMode = wgpu::PresentMode::Fifo;
  config.alphaMode = wgpu::CompositeAlphaMode::Opaque;
  surface_.Configure(&config);
}
