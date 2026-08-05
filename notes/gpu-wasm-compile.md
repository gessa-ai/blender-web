<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# cycle-6 step 1 — WebGPU backend compiles for WASM (emdawnwebgpu)

Goal: make `bf_gpu` with `WITH_WEBGPU_BACKEND=ON` COMPILE for the browser wasm
target — all 18 `upstream/source/blender/gpu/webgpu/` TUs against
`--use-port=emdawnwebgpu` + the cross-compiled `lib/wasm/{tint,shaderc}` include
paths — and archive them into `libbf_gpu.a`. (The LINK with the full binary is a
later step; this round is compile + archive.)

Pin: Blender 5.2 `fbe6228777e7`; emdawnwebgpu port (emcc 6.0.5 cache); Dawn/Tint
`chromium/7989 @ 36cf1fae` (Tint headers); wasm shaderc v2025.4 harvest.

## RESULT — all 18 webgpu TUs compile clean, ZERO source changes

| | |
|---|---|
| webgpu TUs compiled | **18 / 18 OK** |
| source changes needed | **0** (no `__EMSCRIPTEN__` guards, no patch 0034) |
| only warnings | `-Wunused-template` ×12 from `blenlib/BLI_binary_search.hh` (pre-existing, backend-unrelated) |
| header actually used | emdawnwebgpu port `.../ports/emdawnwebgpu/emdawnwebgpu_pkg/webgpu_cpp/include/webgpu/webgpu_cpp.h` (header-trace verified — NOT native Dawn) |
| `libbf_gpu.a` (wasm) | 74 members incl. all 18 `wgpu_*.o`, 8.5 MB |

The three emdawnwebgpu-vs-native-Dawn deltas the context class hit
(`notes/ghost-web-wgpu-context.md` §"API deltas") were expected to recur across the
backend. **They do not** — because every one lives at the device/surface-CREATION
boundary, which is the GHOST context's job, not the backend's. The backend consumes
only the API-STABLE `wgpu::` core object surface (`Device`/`Queue`/`Buffer`/
`Texture`/`CommandEncoder`/`RenderPipeline`/`BindGroup`/…), which is identical
between native Dawn and emdawnwebgpu at this pin — both track the same chromium/7989
C++ spelling the backend was written against.

## Delta table — every documented emdawnwebgpu-vs-Dawn delta vs. the backend

| # | delta (from ghost-web-wgpu-context.md) | in a `gpu/webgpu/` TU? | why / where handled |
|---|---|---|---|
| 1 | `SurfaceSourceCanvasHTMLSelector` → **`EmscriptenSurfaceSourceCanvasHTMLSelector`** | **No** | Surface creation is `GHOST_ContextWGPUWeb`'s (platform_web/ghost). `wgpu_context.cc` *borrows* the device/surface from GHOST (gpu/CMakeLists.txt:520-522), never constructs the surface source. |
| 2 | Device acquisition async-only (no synchronous `WaitAny`/`TimedWaitAny`) | **No** | Also GHOST-layer (`GHOST_ContextWGPUWeb::initAsync`). The backend receives an already-ready `wgpu::Device` handle. `WaitAny`/`TimedWaitAny` symbols are never referenced in any backend TU (compile is unaffected regardless). |
| 3 | No `Surface::Present()` (emdawnwebgpu aborts; browser auto-presents) | **No** | `swapBufferRelease()` is a GHOST no-op on web. The backend never calls `Present`. |
| — | Current-Dawn struct spelling (`TexelCopyTextureInfo`, `ShaderSourceWGSL`, …) | n/a | emdawnwebgpu TRACKS the current spelling, and the backend was written to it — so these match, not diverge. |

Net: the compile-surface delta between native Dawn and emdawnwebgpu for the backend
is **empty**. The runtime deltas (1-3) are confined to the GHOST context (owned by
the ghost-web lane, already handled in `GHOST_ContextWGPUWeb`), so they need no arm
in the backend and no upstream-file guard here.

## Build wiring (patches/platform_wasm.cmake — additive, default OFF)

`gpu/CMakeLists.txt`'s `WITH_WEBGPU_BACKEND` arm (:476) consumes `DAWN_INCLUDE_DIRS`
/ `TINT_INCLUDE_DIRS` / `SHADERC_INCLUDE_DIR` (INC_SYS) + `DAWN_LIBRARIES` /
`WGPU_TINT_LIBS` (LIB). `build-native-gpu` points those at a native Dawn checkout;
the wasm arm (new block in `platform_wasm.cmake`) maps them to the browser world:

| native (`build-native-gpu`) | wasm (this arm, when `WITH_WEBGPU_BACKEND=ON`) |
|---|---|
| `DAWN_INCLUDE_DIRS` = Dawn `include/` + gen | **empty** — webgpu.h/webgpu_cpp.h come from the emdawnwebgpu PORT via `--use-port=emdawnwebgpu` on the compile+link flags |
| `TINT_INCLUDE_DIRS` = `build-dawn/dawn` | same (`src/tint/...` from the pinned Dawn source) |
| `SHADERC_INCLUDE_DIR` = `lib/macos_arm64/shaderc/include` | `lib/wasm/shaderc/include` (the cross-compiled harvest) |
| `DAWN_LIBRARIES` = `libwebgpu_dawn.a` + Metal frameworks | **empty** — emdawnwebgpu provides the device binding at link |
| `WGPU_TINT_LIBS` = native Tint+shaderc archives | `lib/wasm/{shaderc,tint}` ordered lists (LINK step — later) |

`WITH_WEBGPU_BACKEND` defaults OFF (root CMakeLists.txt:961) and is declared before
`platform_wasm` is included (:1555), so the arm is INERT in the shared headless
`build-wasm` — that configure is byte-untouched. A WebGPU compile tree opts in with:

    emcmake cmake -S upstream -B build-wasm-gpu -G Ninja -C patches/blender_web.cmake \
      -DCMAKE_BUILD_TYPE=Release -DWITH_WEBGPU_BACKEND=ON

`WITH_HEADLESS` stays ON — this is the GPU-backend arm ONLY; it does NOT pull the
windowed GHOST/UI stack that `WITH_BLENDER_WEB_WINDOWED` does.

## How the compile was exercised (this round)

The 18 TUs were compiled with build-wasm's EXACT `bf_gpu` flag set (its generated
DNA/RNA include dirs included) plus the arm's additions:
`--use-port=emdawnwebgpu  -DWITH_WEBGPU_BACKEND  -I<gpu/webgpu>  -I<intern/ghost/intern>
 -isystem<build-dawn/dawn>  -isystem<lib/wasm/shaderc/include>` — i.e. exactly the
flags the `platform_wasm.cmake` arm produces. Objects archived into a copy of
`build-wasm/lib/libbf_gpu.a` → `libbf_gpu.a` with the webgpu TUs in it (build tree:
`build-deps/wgpu-iso/`). ccache is OFF in build-wasm, so isolation-compiling the 18
new TUs (rather than a fresh full-tree rebuild of ~100 GPU TUs) is the resource-lean
path; the arm is validated end-to-end by a dedicated `build-wasm-gpu` configure.

## Not in scope this round (flagged, not done)

- **LINK** of the webgpu backend into the full `blender` binary (the M2 boundary
  batch owns `blender.js` — NOT relinked here). The arm wires `WGPU_TINT_LIBS` +
  `--use-port` link flag so the eventual link is ready.
- **Runtime**: the async device-init bridge + per-frame present are the GHOST/main-
  loop lane's (ADR-003 / notes/ghost-web-wgpu-context.md §wait-shape).
