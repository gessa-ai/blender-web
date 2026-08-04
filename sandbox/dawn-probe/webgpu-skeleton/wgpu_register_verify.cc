/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup gpu
 *
 * M3.T4 verify — drive the REGISTERED WebGPU backend through the same calls as
 * GPUTest::SetUpTestSuite (gpu_testing.cc:38-51), stopping BEFORE GPU_init
 * (the skeleton's resource allocators are assert-unreachable placeholders, and
 * GPU_init's gpu_batch_presets_init / shader warm-up would allocate). Confirms:
 *   GPU_backend_type_selection_set(GPU_BACKEND_WEBGPU) -> supported ->
 *   createOffscreenContext(WebGPU) -> GPU_context_create -> WGPUBackend::
 *   context_alloc -> WGPUContext holding GHOST_ContextWGPU's live Dawn device.
 * Prints the registered backend name + adapter.
 */

#include <cstdio>
#include <cstring>

#include "CLG_log.h"

#include "GPU_context.hh"
#include "gpu_context_private.hh"

#include "webgpu/wgpu_backend.hh"
#include "webgpu/wgpu_context.hh"

#include "GHOST_ISystem.hh"

using namespace blender;
using namespace blender::gpu;

int main()
{
  /* GPUTest::SetUpTestSuite calls bke::gtest_setup() first; here we only need
   * the CLOG init it performs (the GHOST/GPU bring-up path logs through CLG). */
  CLG_init();

  GPU_backend_type_selection_set(GPU_BACKEND_WEBGPU);
  if (!GPU_backend_supported()) {
    fprintf(stderr, "FAIL: GPU_backend_supported() == false for WebGPU\n");
    return 1;
  }

  GHOST_GPUSettings gpu_settings = {};
  gpu_settings.context_type = GHOST_kDrawingContextTypeWebGPU;
  GHOST_ISystem::createSystemBackground();
  GHOST_ISystem *ghost_system = GHOST_ISystem::getSystem();
  GPU_backend_ghost_system_set(ghost_system);

  GHOST_IContext *ghost_context = ghost_system->createOffscreenContext(gpu_settings);
  if (ghost_context == nullptr) {
    fprintf(stderr, "FAIL: createOffscreenContext(WebGPU) returned null\n");
    return 2;
  }
  ghost_context->activateDrawingContext();

  /* The registered-backend path: GPU_context_create() -> gpu_backend_create()'s
   * WITH_WEBGPU_BACKEND arm (`new WGPUBackend`) -> WGPUBackend::context_alloc()
   * -> WGPUContext holding GHOST_ContextWGPU's live device -> activate ->
   * DebugDraw::acquire (which the T4 texturepool/storagebuf allocators survive).
   * Stops BEFORE GPU_init() (batch presets / shader warm-up would hit the
   * still-asserting allocators = T6-T10). */
  GPUContext *context = GPU_context_create(nullptr, ghost_context);
  if (context == nullptr) {
    fprintf(stderr, "FAIL: GPU_context_create returned null\n");
    return 3;
  }

  const char *backend_name = GPU_backend_get_name();
  WGPUContext *wgpu_context = static_cast<WGPUContext *>(unwrap(context));

  printf("registered backend name : %s\n", backend_name);
  printf("WGPUContext adapter     : %s\n", wgpu_context->adapter_name());
  printf("WGPUContext device      : %s\n", wgpu_context->device_get() ? "LIVE" : "null");

  const bool ok = backend_name && std::strcmp(backend_name, "WebGPU") == 0 &&
                  wgpu_context->device_get() != nullptr;
  printf("%s\n",
         ok ? "T4 VERIFY PASS: live context created through the REGISTERED WebGPU backend "
              "(GPU_backend_type_selection_set -> GPU_context_create -> WGPUBackend::"
              "context_alloc -> WGPUContext; pre-GPU_init subset)." :
              "T4 VERIFY FAIL");
  /* Intentionally do NOT call GPU_init()/GPU_render_begin() — the skeleton
   * allocators assert; that is the resource work of T6-T10. */
  return ok ? 0 : 4;
}
