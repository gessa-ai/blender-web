/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.T6.pre — WebGPU buffer wrapper (standalone, drop-in for
 * `source/blender/gpu/webgpu/wgpu_buffer.cc`).
 *
 * The common `GPUBuffer` wrapper the vertex/index/uniform/storage buffer classes
 * share. Replaces the Vulkan backend's `vk_buffer` + VMA allocation + staging/
 * streaming plumbing with WebGPU's implicit allocation:
 *   - creation with initial data uses `mappedAtCreation` (no queue op, any size);
 *   - runtime updates use `queue.writeBuffer` (small) or a staging buffer +
 *     `CopyBufferToBuffer` (large), chosen by a size heuristic;
 *   - readback uses a MAP_READ staging buffer + `CopyBufferToBuffer` + `mapAsync`.
 *
 * Usage-flag mapping mirrors what each Blender buffer kind + GPUUsageType needs
 * (recon: vulkan/vk_*_buffer.cc — cited in notes/gpu-t6-t10pre-findings.md). */

#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

#include "webgpu/webgpu_cpp.h"

namespace blender::gpu::webgpu {

/** Which GPU buffer role — selects the kind-specific `wgpu::BufferUsage` bit. */
enum class BufferKind : uint8_t { Vertex, Index, Uniform, Storage };

/** Mirror of Blender's `GPUUsageType` (GPU_vertex_buffer.hh:44). */
enum class UsageType : uint8_t {
  Stream,      /* GPU_USAGE_STREAM: frequently re-uploaded. */
  Static,      /* GPU_USAGE_STATIC: uploaded once; host copy dropped. */
  Dynamic,     /* GPU_USAGE_DYNAMIC: updated occasionally. */
  DeviceOnly,  /* GPU_USAGE_DEVICE_ONLY: no host->device transfer (compute target). */
};

/** WebGPU offset/size granularity: writeBuffer + CopyBufferToBuffer both require
 * 4-byte alignment; uniform binding offsets need 256 (minUniformBufferOffsetAlignment). */
constexpr uint32_t kCopyAlignment = 4u;
constexpr uint32_t kUniformOffsetAlignment = 256u;

/** Above this many bytes, `update_sub` routes through a dedicated staging buffer +
 * CopyBufferToBuffer instead of `queue.writeBuffer`. The cutoff mirrors Blender's
 * Vulkan backend, whose inline `vkCmdUpdateBuffer` fast-path asserts size <= 65536
 * (vk_buffer.cc:146) and otherwise uses a staging buffer — so 64 KiB is the
 * faithful, not arbitrary, boundary between the direct write and the copy path. */
constexpr size_t kWriteBufferStagingThreshold = 65536u;

/** WebGPU index format for Blender's 16-/32-bit index buffers
 * (GPU_index_buffer.hh: GPU_INDEX_U16/U32). */
inline wgpu::IndexFormat to_wgpu_index_format(bool is_32bit) {
  return is_32bit ? wgpu::IndexFormat::Uint32 : wgpu::IndexFormat::Uint16;
}

/** Compute the `wgpu::BufferUsage` for a (kind, usage) pair. `readable` adds
 * CopySrc so the buffer can be read back to host (storage buffers, pixel packs). */
wgpu::BufferUsage usage_flags(BufferKind kind, UsageType usage, bool readable);

/** The common buffer wrapper. Non-owning of the device; owns its wgpu::Buffer. */
class Buffer {
 public:
  Buffer() = default;

  /** Create a buffer of `size` bytes. If `initial_data` is non-null it is written
   * via `mappedAtCreation` (no queue submission). `size` is rounded up to a
   * multiple of 4 (WebGPU requirement). Returns false on failure. */
  bool create(const wgpu::Device &device, BufferKind kind, UsageType usage,
              size_t size, const void *initial_data, bool readable);

  /** Partial update: writes `size` bytes at `offset`. Uses queue.writeBuffer for
   * small writes, a staging buffer + copy for large ones (kWriteBufferStagingThreshold).
   * offset and size must be 4-aligned. Returns false on misuse. */
  bool update_sub(const wgpu::Device &device, const wgpu::Queue &queue,
                  size_t offset, const void *data, size_t size);

  /** Read `size` bytes at `offset` back to host via a MAP_READ staging buffer.
   * Requires the buffer was created `readable`. Blocks on the instance. */
  std::vector<uint8_t> read(const wgpu::Instance &instance, const wgpu::Device &device,
                            const wgpu::Queue &queue, size_t offset, size_t size);

  const wgpu::Buffer &handle() const { return handle_; }
  size_t size() const { return size_; }
  BufferKind kind() const { return kind_; }
  bool valid() const { return handle_ != nullptr; }

 private:
  wgpu::Buffer handle_;
  size_t size_ = 0;        /* rounded (allocated) size */
  size_t requested_ = 0;   /* size the caller asked for */
  BufferKind kind_ = BufferKind::Vertex;
  bool readable_ = false;
};

/** Round up to the next multiple of `a` (a power of two). */
inline size_t align_up(size_t v, size_t a) { return (v + (a - 1)) & ~(a - 1); }

}  // namespace blender::gpu::webgpu
