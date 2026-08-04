<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M3.T3 — GHOST WebGPU offscreen context + native harness (findings)

Uncommitted worker notes for orchestrator review. Pin: Blender 5.2 `fbe6228777e7`;
Dawn `chromium/7989 @ 36cf1fae`.

## Per-stage status

| stage | result | evidence |
|---|---|---|
| libs-fetch | **PASS** | `lib/macos_arm64` cloned OUT-OF-TREE at the pinned submodule SHA `5a140a8` (branch tip had moved to `a76ef91`; checked out the exact pin), 2.4 GB, real archives (not LFS pointers). `upstream/` untouched — the submodule is left uninitialised, so HEAD (`fbe6228`) and the gitlink are unchanged. |
| configure | **PASS (11 s)** | native headless gpu-test configure: `-DWITH_HEADLESS=ON -DWITH_GTESTS=ON -DWITH_PYTHON=OFF -DWITH_METAL_BACKEND=ON -DLIBDIR=.../lib/macos_arm64`. `build-native-gpu/`. |
| ghost-context | **PASS** | `GHOST_ContextWGPU` compiles against Blender's REAL GHOST headers (GHOST_Context interface + guardedalloc); patch 0011 applies clean on 0001-0010. |
| device-live | **PASS** | `GHOST_ContextWGPU::initializeDrawingContext()` → live WGPUDevice+queue on **"Apple M4 Pro"** (Metal, offscreen), via `sandbox/dawn-probe/ghost-wgpu/build_verify.sh`. |
| backend-skeleton | **PENDING** | GPU_BACKEND_WEBGPU registration + WGPUBackend/WGPUContext skeleton + gpu/CMakeLists block not yet written/built (budget). Cited edits below. |
| full gpu-test verify | **PENDING** | needs backend-skeleton + a full native gpu-test link with WITH_WEBGPU_BACKEND. Not attempted. |

Both feasibility gates the orchestrator flagged (libs, native configure) are GREEN
on this Mac — the native harness is viable; no macOS-specific blocker found.

## Key facts / deltas

- **Blender 5.2 is C++20** (`CMakeLists.txt:2310`), so GHOST/gpu can use Dawn's
  `webgpu_cpp.h` directly (no C++17 landmine). GHOST_ContextWGPU is ~130 LOC vs
  GHOST_ContextVK's hundreds — WebGPU's implicit model erases the surface/
  swapchain/semaphore machinery.
- **"never write under upstream/" is harness-enforced** (Write tool blocked).
  So the libs live at top-level `lib/macos_arm64` (LIBDIR override), and the
  GHOST class was proven in `sandbox/` first; the committed form is patch 0011,
  applied by the build via `git -C upstream apply` (same mechanism as 0001-0010,
  see harness/run.sh:124).
- GHOST_Context pure set to override: `swapBufferAcquire`, `swapBufferRelease`
  (5.2 naming, NOT swapBuffers), `activateDrawingContext`,
  `releaseDrawingContext`, `initializeDrawingContext`, `releaseNativeHandles`.
- gpu_testing.cc bootstrap needs GHOST/GPU only — **WITH_PYTHON not required**
  for the gpu test binary (confirmed by recon + the python-off configure).

## DAWN_ROOT / link mechanism (documented)

Patch 0011's ghost CMake block consumes `DAWN_INCLUDE_DIRS` + `DAWN_LIBRARIES`.
The harness scope sets them (proven working by the part-1 verify link):

```
DAWN_INCLUDE_DIRS = build-dawn/dawn/include ; build-dawn/probe-build/dawn/gen/include
DAWN_LIBRARIES    = build-dawn/probe-build/dawn/src/dawn/native/libwebgpu_dawn.a
                    (monolithic bundle) + frameworks: Cocoa CoreGraphics Foundation
                    IOKit IOSurface Metal QuartzCore
```

A cleaner future form: a `find_package`-style resolver keyed on a single
`DAWN_ROOT` cache var (or `cmake --install` Dawn into `build-dawn/install`). For
T3 the explicit two-var set is sufficient and matches the verified link. Tint is
NOT needed for T3 (device bring-up only); it enters at T7 (WGPUShader).

## Remaining work (part 3) — cited edits for the full gpu-test verify

1. `GPU_platform_backend_enum.h:14-20` — `GPU_BACKEND_WEBGPU = 1 << 2` (the free
   bit); mirror the DNA value in `DNA_userdef_types.h` `eUserPref_GPUBackendType`
   (additive value, not a layout change → no ABI stop-condition).
2. `gpu_context.cc` switch arms: `:38-40` include, `:455` name, `:487` detect,
   `:520` supported, `:559` create (`new WGPUBackend`), `:612` get_type,
   `:646` → `GHOST_kDrawingContextTypeWebGPU`. Each an additive
   `#ifdef WITH_WEBGPU_BACKEND` case mirroring VULKAN.
3. `source/blender/gpu/webgpu/` — `WGPUBackend` (21 pure-virtual stubs:
   `BLI_assert_unreachable` for T4's full set; for T3 only `context_alloc`
   returns a real `WGPUContext` that pulls the device from the GHOST context via
   `GHOST_ContextWGPU::getDevice()`), `WGPUContext`.
4. `gpu/CMakeLists.txt:462-474` mirror block (`WEBGPU_SRC`, link
   `DAWN_LIBRARIES`, `-DWITH_WEBGPU_BACKEND`); test block `:961-973`,
   suite `gpu` `:980-982` with `WITH_GPU_BACKEND_TESTS`.
5. Configure `build-native-gpu` with `-DWITH_WEBGPU_BACKEND=ON` +
   DAWN_INCLUDE_DIRS/DAWN_LIBRARIES, `ninja` the `gpu` suite binary, run with
   `GPU_backend_type_selection_set(GPU_BACKEND_WEBGPU)` → SetUpTestSuite gets the
   device through GHOST_SystemHeadless::createOffscreenContext.

## Deliverables committed

- `66500f0` patch `0011-ghost-webgpu-context.patch` (applies clean).
- `8607fac` `sandbox/dawn-probe/ghost-wgpu/` (verified GHOST_ContextWGPU + device-live).
- `.gitignore`: `lib/macos_arm64/`, `build-native-gpu/`. Build trees gitignored;
  `upstream/` HEAD untouched.
