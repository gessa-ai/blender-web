/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_common.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * Shared GPU<->WebGPU conversion helpers + constants (the WebGPU analog of
 * vk_common). Owned by integration lane A; other backend files (buffers, and
 * lane B's texture/pipeline modules) include this. Kept dependency-light: only
 * Dawn's C++ header + libc. Proven standalone in sandbox/wgpu-buffers/ and
 * documented in notes/gpu-t6-t10pre-findings.md.
 */

#pragma once

#include <cstddef>
#include <cstdint>

#include "webgpu/webgpu_cpp.h"

namespace blender::gpu::webgpu {

/** Which GPU buffer role — selects the kind-specific `wgpu::BufferUsage` bit. */
enum class BufferKind : uint8_t { Vertex, Index, Uniform, Storage };

/** Mirror of Blender's `GPUUsageType` (GPU_vertex_buffer.hh:44). */
enum class UsageType : uint8_t {
  Stream,     /* GPU_USAGE_STREAM: frequently re-uploaded. */
  Static,     /* GPU_USAGE_STATIC: uploaded once; host copy dropped. */
  Dynamic,    /* GPU_USAGE_DYNAMIC: updated occasionally. */
  DeviceOnly, /* GPU_USAGE_DEVICE_ONLY: no host->device transfer (compute target). */
};

/** WebGPU offset/size granularity: writeBuffer + CopyBufferToBuffer both require
 * 4-byte alignment; uniform binding offsets need 256
 * (minUniformBufferOffsetAlignment). */
constexpr uint32_t kCopyAlignment = 4u;
constexpr uint32_t kUniformOffsetAlignment = 256u;

/** Above this many bytes, buffer sub-updates route through a dedicated staging
 * buffer + CopyBufferToBuffer instead of `queue.writeBuffer`. Mirrors Blender's
 * Vulkan inline `vkCmdUpdateBuffer` fast-path (asserts size <= 65536,
 * vk_buffer.cc:146) — so 64 KiB is the faithful boundary, not arbitrary. */
constexpr size_t kWriteBufferStagingThreshold = 65536u;

/** WebGPU index format for Blender's 16-/32-bit index buffers
 * (GPU_index_buffer.hh: GPU_INDEX_U16/U32). */
inline wgpu::IndexFormat to_wgpu_index_format(bool is_32bit)
{
  return is_32bit ? wgpu::IndexFormat::Uint32 : wgpu::IndexFormat::Uint16;
}

/** Round up to the next multiple of `a` (a power of two). */
inline size_t align_up(size_t v, size_t a)
{
  return (v + (a - 1)) & ~(a - 1);
}

}  // namespace blender::gpu::webgpu
