<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M1 wave-2 — worker P1 (gpu / draw / window / media) report

Partition P1 from `notes/m1-wave2-partition.md §P1`: the HIGH-NOVELTY lane —
gpu frontend with all backends OFF, draw, windowmanager, headless GHOST NULL,
render, blenfont, imbuf + external codecs, and 8 intern/extern leaves.
**19 targets, 341 TU.**

## Result: 19/19 GREEN, ZERO source fixes

Single `-k 0` build of the full partition list compiled clean:
`BUILD OK (149 s)`, ninja `[2296/2297]`, **0 `error:` / 0 `FAILED:`**
(buildlog `20260804T015530.log`). No patches 0100–0119 were created — the
surface needed no `#ifdef __EMSCRIPTEN__` seams at all. Zero edits to any
`upstream/` file under this partition (verified `git -C upstream diff` clean
over all P1 dirs; the lone diff there, `gpu/shader_tool/CMakeLists.txt`, is the
pre-applied patch 0007 native-codegen wiring, not P1's).

### Archive sizes on disk (`build-wasm/lib/`)

| archive | bytes | archive | bytes |
|---|---:|---|---:|
| libbf_gpu.a | 8,565,696 | libbf_imbuf_openexr.a | 171,340 |
| libbf_draw.a | 15,792,762 | libbf_intern_sky.a | 69,582 |
| libbf_windowmanager.a | 1,610,026 | libbf_intern_opensubdiv.a | 1,614 |
| libbf_intern_ghost.a | 122,318 | libbf_intern_libmv.a | 4,340 |
| libbf_blenfont.a | 154,624 | libbf_intern_memutil.a | 21,130 |
| libbf_render.a | 866,140 | libextern_rangetree.a | 8,786 |
| libbf_imbuf.a | 716,514 | libextern_nanosvg.a | 68,826 |
| libbf_imbuf_opencolorio.a | 538,548 | libextern_curve_fit_nd.a | 67,476 |
| libbf_imbuf_movie.a | 34,660 | libbf_ikplugin.a | 1,486 |
| libbf_imbuf_openimageio.a | 40,900 | | |

### Error-class table

| class | count | note |
|---|---:|---|
| compile `error:` | **0** | whole partition |
| link `FAILED:` | **0** | (archive builds; final link is driver's `bmesh_core_test`) |
| `#ifdef __EMSCRIPTEN__` fixes needed | **0** | — |
| patches created (0100–0119) | **0** | none required |

## Seams found (owned per the brief) — all pre-handled, none required a fix

1. **gpu frontend with all backends OFF (the single most novel item).**
   `WITH_OPENGL_BACKEND` / `WITH_VULKAN_BACKEND` / `WITH_METAL_BACKEND` are all
   undefined in the wasm config, so in `gpu/intern/gpu_context.cc`
   `gpu_backend_create()` the three `#ifdef WITH_*_BACKEND` cases compile out and
   selection falls to `GPU_BACKEND_NONE → MEM_new<DummyBackend>()`. The dummy
   backend is **upstream's own headless/test fallback** (`gpu/intern/gpu_dummy/`),
   so the backend-agnostic frontend + `DummyBackend` compile with no seam. epoxy
   is already patched out upstream-config-side (recon), so no GL-loader includes
   leak in. `libbf_gpu.a` (8.5 MB) and `libbf_draw.a` (15.8 MB, the largest P1
   archive — draw-manager couples heavily to gpu headers) both clean.

2. **GHOST headless NULL backend.** `intern/ghost` builds `GHOST_SystemNULL` /
   `GHOST_WindowNULL` with X11/Wayland/Cocoa/Metal compiled out; `libbf_intern_ghost.a`
   is a tiny 122 KB — clean, no platform-syscall seam surfaced (matches recon:
   all windowing hazards config-gated out).

3. **imbuf external-codec seam.** OIIO / OpenEXR / OCIO / freetype link from the
   harvested `lib/wasm` deps; `bf_imbuf_movie` builds **without ffmpeg**
   (`WITH_CODEC_FFMPEG=OFF`) as a 35 KB no-codec archive. All five imbuf archives
   (`bf_imbuf`, `_opencolorio`, `_movie`, `_openimageio`, `_openexr`) compiled
   with no libc/codec seam — the find_package graph already resolves every dep to
   a real `lib/wasm` archive (recon: zero NOTFOUND).

4. **intern/extern leaves** (sky, opensubdiv, libmv, memutil, rangetree, nanosvg,
   curve_fit_nd, ikplugin): all trivially clean, as recon scanned. opensubdiv /
   libmv are stub archives (1.6 KB / 4.3 KB), confirming the "stubs" recon note.

## Confirmation of recon thesis

P1 was designated the HIGH-novelty lane on the theory that its libs are the
fix-magnets. In the event the whole lane compiled first-try with zero fixes:
the novelty is real but **entirely absorbed by upstream's own config guards +
DummyBackend + the already-harvested deps** — the actual novel WebGPU work is
M3 (a new `gpu/webgpu/` backend), not compiling the M1 frontend. The
"wide-not-deep, every-hazard-scan-clean" recon prediction held across all 341 TU.
