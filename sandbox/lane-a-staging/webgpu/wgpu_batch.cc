/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_batch.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 */

#include "wgpu_batch.hh"

#include "BLI_assert.h"

namespace blender::gpu {

/* lane-B: draw path — pipeline lookup + bind groups + draw encoding (incl. the
 * point-size expansion hook) land with lane B's render pipeline. No preset batch
 * is drawn during GPU_init, so these are unreached at bring-up. */
void WGPUBatch::draw(int /*vertex_first*/,
                     int /*vertex_count*/,
                     int /*instance_first*/,
                     int /*instance_count*/)
{
  BLI_assert_unreachable(); /* lane-B: draw path */
}

void WGPUBatch::draw_indirect(StorageBuf * /*indirect_buf*/, intptr_t /*offset*/)
{
  BLI_assert_unreachable(); /* lane-B: draw path */
}

void WGPUBatch::multi_draw_indirect(StorageBuf * /*indirect_buf*/,
                                    int /*count*/,
                                    intptr_t /*offset*/,
                                    intptr_t /*stride*/)
{
  BLI_assert_unreachable(); /* lane-B: draw path */
}

}  // namespace blender::gpu
