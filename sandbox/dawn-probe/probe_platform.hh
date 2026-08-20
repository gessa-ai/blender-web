// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include "webgpu/webgpu_cpp.h"

namespace blender_web::dawn_probe {

#if defined(__APPLE__)
inline constexpr wgpu::BackendType kBackendType = wgpu::BackendType::Metal;
inline constexpr const char *kBackendName = "Metal";
#elif defined(__linux__)
inline constexpr wgpu::BackendType kBackendType = wgpu::BackendType::Vulkan;
inline constexpr const char *kBackendName = "Vulkan";
#else
#  error "The Dawn probe supports only macOS/Metal and Linux/Vulkan"
#endif

inline bool is_hardware_adapter(const wgpu::AdapterInfo &info)
{
  return info.backendType == kBackendType &&
         (info.adapterType == wgpu::AdapterType::DiscreteGPU ||
          info.adapterType == wgpu::AdapterType::IntegratedGPU);
}

}  // namespace blender_web::dawn_probe
