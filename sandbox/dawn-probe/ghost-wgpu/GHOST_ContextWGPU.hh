/* SPDX-FileCopyrightText: 2022-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from intern/ghost/intern/GHOST_ContextVK.hh @ fbe6228777e7 */

/** \file
 * \ingroup GHOST
 *
 * Native (this-Mac) offscreen WebGPU drawing context backed by Dawn. Radically
 * simpler than GHOST_ContextVK: WebGPU's implicit driver model means bring-up is
 * just instance -> adapter -> device (no surface, headless). This is the M3
 * vehicle that lets Blender's gpu-module gtests run against a real Dawn device.
 *
 * NOTE: this file's committed home is upstream/intern/ghost/intern/ via a
 * patch; the copy under sandbox/dawn-probe/ghost-wgpu/ is the compile+device
 * proof for T3 (built against Blender's real GHOST headers, see build_verify.sh).
 */

#pragma once

#ifndef WITH_WEBGPU_BACKEND
#  error "ContextWGPU requires WITH_WEBGPU_BACKEND"
#endif

#include "GHOST_Context.hh"

#include <string>
#include <webgpu/webgpu_cpp.h>

class GHOST_ContextWGPU : public GHOST_Context {
 public:
  /**
   * Constructor. Offscreen only — no window/surface handles (mirrors the
   * headless GHOST_ContextVK construction path in GHOST_SystemHeadless).
   */
  GHOST_ContextWGPU(const GHOST_ContextParams &context_params);
  ~GHOST_ContextWGPU() override;

  GHOST_TSuccess swapBufferAcquire() override;
  GHOST_TSuccess swapBufferRelease() override;
  GHOST_TSuccess activateDrawingContext() override;
  GHOST_TSuccess releaseDrawingContext() override;
  GHOST_TSuccess initializeDrawingContext() override;
  GHOST_TSuccess releaseNativeHandles() override;

  /**
   * WebGPU handle accessors for the GPU backend (mirrors GHOST_ContextVK's
   * getVulkanHandles): the WGPUBackend / WGPUContext pull the live device and
   * queue from here at GPU_context_create() time.
   */
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

  /** Human-readable adapter name, for logging / the T3 verify. */
  const char *getAdapterName() const
  {
    return adapter_name_.c_str();
  }

 private:
  wgpu::Instance instance_ = nullptr;
  wgpu::Adapter adapter_ = nullptr;
  wgpu::Device device_ = nullptr;
  wgpu::Queue queue_ = nullptr;
  std::string adapter_name_;
};
