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

#include <cstdio>
#include <utility>

GHOST_ContextWGPUWeb::GHOST_ContextWGPUWeb(const char *canvas_selector)
    : canvas_selector_(canvas_selector ? canvas_selector : "#canvas")
{
}

GHOST_ContextWGPUWeb::~GHOST_ContextWGPUWeb() = default;

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
