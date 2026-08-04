// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M3.T3 verify — drive the real GHOST_ContextWGPU (compiled against Blender's
// own GHOST headers) through the offscreen bring-up path a headless
// GHOST_SystemHeadless::createOffscreenContext would use, and confirm a LIVE
// WGPUDevice + adapter name. This is the sandbox standalone-main form of the T3
// gate (the full gpu-test-binary form is wired by patches 0011-00xx).

#include "GHOST_ContextWGPU.hh"

#include <cstdio>

int main()
{
  GHOST_ContextParams params = {};  // offscreen defaults; no window/surface.
  GHOST_ContextWGPU ctx(params);

  if (ctx.initializeDrawingContext() != GHOST_kSuccess) {
    fprintf(stderr, "GHOST_ContextWGPU::initializeDrawingContext FAILED\n");
    return 1;
  }
  printf("GHOST_ContextWGPU adapter: %s\n", ctx.getAdapterName());

  if (ctx.getDevice() == nullptr || ctx.getQueue() == nullptr) {
    fprintf(stderr, "device/queue is null after init\n");
    return 2;
  }
  if (ctx.activateDrawingContext() != GHOST_kSuccess ||
      ctx.releaseDrawingContext() != GHOST_kSuccess) {
    fprintf(stderr, "activate/release failed\n");
    return 3;
  }

  printf(
      "T3 VERIFY PASS: live WGPUDevice obtained through GHOST_ContextWGPU "
      "(offscreen, headless, Metal).\n");
  return 0;
}
