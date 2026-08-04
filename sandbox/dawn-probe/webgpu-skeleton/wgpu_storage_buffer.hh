/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_storage_buffer.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * M3.T4 minimal no-op StorageBuf. The gpu-test bootstrap's DebugDraw allocates
 * exactly one storage buffer and `push_update()`s it, but never reads it back or
 * binds it for a draw during bring-up, so no-op methods survive. The real
 * GPUBuffer-backed implementation (writeBuffer / mapAsync) is T6.
 */

#pragma once

#include "gpu_storage_buffer_private.hh"

#include "MEM_guardedalloc.h"

namespace blender::gpu {

class WGPUStorageBuffer : public StorageBuf {
 public:
  WGPUStorageBuffer(size_t size, GPUUsageType /*usage*/, const char *name)
      : StorageBuf(size, name)
  {
  }

  void update(const void * /*data*/) override {}
  void bind(int /*slot*/) override {}
  void unbind() override {}
  void clear(uint32_t /*clear_value*/) override {}
  void copy_sub(VertBuf * /*src*/,
                uint /*dst_offset*/,
                uint /*src_offset*/,
                uint /*copy_size*/) override
  {
  }
  void read(void * /*data*/) override {}
  void async_flush_to_host() override {}
  void sync_as_indirect_buffer() override {}

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUStorageBuffer")
};

}  // namespace blender::gpu
