<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# GPU fallback dialog re-triage

Status: diagnosis complete; no production patch in this round.

## Outcome

The browser did not fail a WebGPU capability check. The fallback flag is set while rejecting
an inherited OpenGL preference before WebGPU is tried and accepted.

The exact path is:

1. On every non-Apple target, `USER_GPU_BACKEND_DEFAULT` is OpenGL
   (`upstream/source/blender/makesdna/DNA_userdef_types.h:204`). Defining
   `__EMSCRIPTEN__` does not select a web default.
2. User-preference initialization copies `U.gpu_backend` into an explicit backend override
   (`upstream/source/blender/windowmanager/intern/wm_files.cc:506`).
3. Detection inserts that override even when its backend was compiled out
   (`upstream/source/blender/gpu/intern/gpu_context.cc:480`). The windowed cache has
   `WITH_OPENGL_BACKEND=OFF`, `WITH_VULKAN_BACKEND=OFF`, and `WITH_WEBGPU_BACKEND=ON`.
4. The OpenGL probe therefore returns false and line 512 sets
   `G_FLAG_GPU_BACKEND_FALLBACK`. The following WebGPU probe returns true because
   `WGPUBackend::is_supported()` is currently unconditional
   (`upstream/source/blender/gpu/webgpu/wgpu_backend.hh:30`).
5. `wm_test_gpu_backend_fallback()` later sees the stale bit and displays its native,
   hard-coded Vulkan-to-OpenGL message (`upstream/source/blender/windowmanager/intern/wm_window.cc:2417`).

This corrects patch 0107's explanation that detection ran before the imported device became live.
No device state is consulted by the current `is_supported()` implementation. Patch 0107 is
effective only because it sets the one-shot `G_FLAG_GPU_BACKEND_FALLBACK_QUIET` bit before the
window-manager test.

## Reproduction

The current product cache proves the mono-backend configuration. The compile probe
`sandbox/gpu-fallback-retriage/probe_default.cc` includes the real DNA header with
`__EMSCRIPTEN__` defined and asserts that the web build still chooses OpenGL rather than WebGPU.

Receipt: `ledger/buildlogs/20260820T151502.log` checks all three cache flags and reports a clean
`clang++-17 -fsyntax-only` run.
Existing browser evidence remains `notes/gpu-r20-cube-blocker.md` (dialog present) and
`notes/gpu-r22-cube-blocker.md` (dialog hidden by patch 0107).

## Faithful successor

Do not merely clear or quiet the fallback bit again. At the next browser-backed GPU selection
round:

- make the Emscripten default and loaded-preference normalization select WebGPU;
- add WebGPU to the command-line backend parser and RNA preference enum, both of which currently
  omit it despite the DNA enum existing;
- remove patch 0107's `BKE_global.hh` dependency and quiet-bit write;
- negative-test an intentionally unsupported command-line backend, then verify a default boot has
  no fallback flag or dialog.

That change needs a rebuilt windowed product and browser evidence. It is not part of this
diagnosis-only round, and it cannot bind an M4 receipt while the ornith-lab hardware-adapter gate
is blocked.
