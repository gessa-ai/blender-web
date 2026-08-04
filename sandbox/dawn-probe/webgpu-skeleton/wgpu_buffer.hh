/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_buffer.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * The common `GPUBuffer` wrapper the vertex/index/uniform/storage buffer classes
 * share. Replaces the Vulkan backend's `vk_buffer` + VMA allocation + staging /
 * streaming plumbing with WebGPU's implicit allocation:
 *   - creation with initial data uses `mappedAtCreation` (no queue op, any size);
 *   - runtime updates use `queue.writeBuffer` (<=64 KiB) or a staging buffer +
 *     `CopyBufferToBuffer` (larger), chosen by kWriteBufferStagingThreshold;
 *   - readback uses a MAP_READ staging buffer + `CopyBufferToBuffer` + `mapAsync`.
 *
 * Standalone-proven (5/5 live, byte-exact incl. the 20 MiB staging path) in
 * sandbox/wgpu-buffers/; recon + rationale in notes/gpu-t6-t10pre-findings.md.
 */

#pragma once

#include <vector>

#include "wgpu_common.hh"

namespace blender::gpu::webgpu {

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
  bool create(const wgpu::Device &device,
              BufferKind kind,
              UsageType usage,
              size_t size,
              const void *initial_data,
              bool readable);

  /** Partial update: writes `size` bytes at `offset`. Uses queue.writeBuffer for
   * small writes, a staging buffer + copy for large ones. offset/size must be
   * 4-aligned. Returns false on misuse. */
  bool update_sub(const wgpu::Device &device,
                  const wgpu::Queue &queue,
                  size_t offset,
                  const void *data,
                  size_t size);

  /** Read `size` bytes at `offset` back to host via a MAP_READ staging buffer.
   * Requires the buffer was created `readable`. Blocks on the instance. */
  std::vector<uint8_t> read(const wgpu::Instance &instance,
                            const wgpu::Device &device,
                            const wgpu::Queue &queue,
                            size_t offset,
                            size_t size);

  const wgpu::Buffer &handle() const
  {
    return handle_;
  }
  size_t size() const
  {
    return size_;
  }
  BufferKind kind() const
  {
    return kind_;
  }
  bool valid() const
  {
    return handle_ != nullptr;
  }

 private:
  wgpu::Buffer handle_;
  size_t size_ = 0;      /* rounded (allocated) size */
  size_t requested_ = 0; /* size the caller asked for */
  BufferKind kind_ = BufferKind::Vertex;
  bool readable_ = false;
};

}  // namespace blender::gpu::webgpu
