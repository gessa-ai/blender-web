/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_batch.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * `Batch` on the WebGPU backend — bootstrap-minimal (round-4 SCOPED to lane A so
 * GPU_init's `gpu_batch_presets_init` can allocate its preset batches). The base
 * `Batch` already owns the vertex/index buffer storage (`verts[]`, `elem`) that
 * the presets fill; this subclass only supplies the three draw virtuals, which
 * are the DRAW PATH — owned by lane B. They assert until lane B lands the pipeline
 * + draw encoding. No preset is drawn during GPU_init, so the asserts are unreached
 * at bring-up.
 */

#pragma once

#include "GPU_batch.hh"

#include "MEM_guardedalloc.h"

namespace blender::gpu {

class WGPUBatch : public Batch {
 public:
  void draw(int vertex_first, int vertex_count, int instance_first, int instance_count) override;
  void draw_indirect(StorageBuf *indirect_buf, intptr_t offset) override;
  void multi_draw_indirect(StorageBuf *indirect_buf,
                           int count,
                           intptr_t offset,
                           intptr_t stride) override;

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUBatch")
};

}  // namespace blender::gpu
