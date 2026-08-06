<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M6 Cycles-CPU wasm32 compile probe

Pin: `blender-v5.2-release` @ `fbe6228777e7`. Toolchain: emcmake / emcc 6.0.5
(emsdk), node 22.16.0 emulator. This is the M1.3 "revisit at M6" of the
`WITH_CYCLES OFF` deferral. **Probe only — nothing landed in `upstream/`; no
patches written.** Disposable tree: `build-wasm-cycles/`.

## Verdict: COMPILES CLEAN

**Cycles-CPU compiles for wasm32 at the pin against the existing `lib/wasm`
dep set, with ZERO source changes and ZERO compile errors.** No dep wall at
configure; no error buckets at compile. The entire CPU render library set —
kernel, device (incl. `device/cpu`), util, scene, bvh, subd, graph, integrator,
session — **and** the Blender↔Cycles integration layer `bf_intern_cycles` all
build to wasm32 static libs. The M6 "can Cycles even compile?" unknown is
retired: **it can, as-is.**

The single enabler is arch detection: under emcc, `check_cxx_compiler_flag`
for `-msse4.2` / `-mavx2` / `-mf16c` all **FAIL**, so Cycles selects the
**scalar `KERNEL_ARCH`** (no `WITH_KERNEL_SSE42` / `WITH_KERNEL_AVX2` defined).
This sidesteps the whole SSE-intrinsics / sse2neon question — the SIMD kernel
variants are never compiled with intrinsics. `kernel_avx2.cpp` is still listed
as a TU but compiles as a near-empty define-off stub (its body is `#ifdef
WITH_KERNEL_AVX2`-gated).

## What actually built (receipts)

All through `harness/buildwrap.sh`, `nice -19`, in `build-wasm-cycles/`.

| wave | ninja target(s) | cycles TU compiles | libs linked | errors |
|------|-----------------|--------------------|-------------|--------|
| configure | `emcmake cmake … -C cycles_probe.cmake` | — | Configuring+Generating done (46 s) | 0 |
| 1 | `cycles_kernel_cpu cycles_device` | 31 | `libcycles_kernel_cpu.a` (1.7 MB), `libcycles_device.a` (314 KB) | 0 |
| 2 | `cycles_util cycles_graph cycles_bvh cycles_subd cycles_scene cycles_integrator cycles_session` | 115 | 7 libs (scene 4.2 MB/42 obj, integrator 862 KB/21 obj, util 24 obj, bvh 13 obj, subd 5 obj, graph 3 obj, session 7 obj) | 0 |
| 3 | `bf_intern_cycles` (Blender sync/export) | 23 | `libbf_intern_cycles.a` (3.3 MB) | 0 |

~170 genuine Cycles-render TU compiles across the waves. **Anti-cache proof:**
`ccache -s` showed 113 misses / 0 hits (real compiles, not replay), and a
forced `CCACHE_DISABLE=1` rebuild of `scene/shader_nodes.cpp` — one of Cycles'
heaviest, most template-dense TUs (SVM node compilation) — took 27 s and
succeeded. `device/cpu/{device,device_impl,kernel}.cpp` (the CPU device) all
compiled.

`kernel.cpp.o` (the scalar CPU mega-TU) is 1.69 MB — the genuine full kernel,
not a stub.

## Error-bucket table

**EMPTY.** No LP64/int-width, no missing-intrinsics, no pthread/TLS, no
exceptions bucket. Nothing needed characterizing into the M1 grind taxonomy —
every wave was clean on the first pass.

Only warnings observed (benign):

| warning | count | note |
|---------|-------|------|
| `-Wunused-template` | ~132 | `util/map.h:17 map_free_memory` unused in most TUs; cosmetic |
| `-Wswitch` | 2 | unhandled enum case; cosmetic |
| `-Wpthreads-mem-growth` | 2 | **posture item, not a blocker** — see below |

### `-Wpthreads-mem-growth`

Emscripten warns that a growable heap (`ALLOW_MEMORY_GROWTH`, which the port
uses) combined with pthreads can force JS-side `HEAP*` view re-acquisition on
every access in worker threads. Cycles is the fleet's most thread-and-alloc
intensive subsystem (TBB task arena + per-thread render state + large tile
buffers), so this is a **runtime performance flag to watch at M6-render**, not a
compile blocker. It matches the standing Emscripten posture in GOAL.md
(`-pthread` + memory growth) and is already accepted elsewhere in the build.

## Configure toggle recipe (the one that worked, first try)

Init-cache = canonical `patches/blender_web.cmake` (verbatim `include()`) with
one flip and the CPU-only re-assertions. Command:

```
emcmake cmake -S upstream -B build-wasm-cycles -G Ninja \
  -C <probe>/cycles_probe.cmake -DCMAKE_BUILD_TYPE=Release
```

| toggle | value | why |
|--------|-------|-----|
| `WITH_CYCLES` | **ON** | the flip under test |
| `WITH_CYCLES_EMBREE` | OFF | x86/arm SIMD BVH; no wasm build. Cycles falls back to its own BVH2 (built: `libcycles_bvh.a`) — **no Embree needed to compile** |
| `WITH_CYCLES_OSL` | OFF | needs LLVM JIT; no JIT in the sandbox (D-6 deferral) |
| `WITH_CYCLES_PATH_GUIDING` | OFF | OpenPGL; unported |
| `WITH_OPENIMAGEDENOISE` | OFF | OIDN; unported |
| `WITH_OPENVDB` / `WITH_NANOVDB` | OFF | volumes; unported |
| `WITH_OPENSUBDIV` | OFF | `libcycles_subd.a` still builds (Cycles' own subd) |
| `WITH_CYCLES_HYDRA_RENDER_DELEGATE` | OFF | USD/Hydra off |
| `WITH_CYCLES_DEVICE_{CUDA,HIP,HIPRT,METAL,ONEAPI,OPTIX}` | OFF | GPU device paths forced off (GOAL standing decision) |
| `WITH_CYCLES_{CUDA,HIP,ONEAPI}_BINARIES` | OFF | no offline kernel compilers |
| `WITH_CYCLES_STANDALONE` / `_GUI` | OFF | Blender-embedded only |
| `WITH_CYCLES_NATIVE_ONLY` | OFF | deliberately let CMake probe `-msse4.2` the normal way so we characterize the real (scalar) `KERNEL_ARCH` — do **not** force `-march=native` |

All toggles above already existed OFF in `blender_web.cmake`; the probe only
re-asserts them for auditability and flips `WITH_CYCLES` ON. Inherited from the
base config and load-bearing: `WITH_PYTHON ON`, `WITH_TBB ON` (root
`CMakeLists.txt:1319,1330` force `WITH_CYCLES OFF` if either is off).

## Dep accounting — the shopping list is EMPTY

Cycles' find_package surface is entirely WITH-gated. `external_libs.cmake`
handles only CUDA/HIP/Metal/oneAPI (all OFF → no-op). Embree/OIDN/OpenPGL/OSL
are found in the platform layer under their WITH-toggles, which the port's
`patches/platform_wasm.cmake` deliberately does **not** call (it comments the
Cycles/OSL/Embree deps as "forced OFF in blender_web.cmake, need nothing here",
platform_wasm.cmake:592-594). So no missing find_package fires.

Every mandatory Cycles dep was **already in `lib/wasm`** from the M1/M2 dep
waves:

| dep | status | provenance |
|-----|--------|------------|
| OpenImageIO | present | M1.6 |
| OpenColorIO | present | M2 |
| TBB | present | M1.4/M1.7 |
| Imath / OpenEXR | present | M1.4/M1.5 |
| Eigen3 (header) | present | lib/wasm/include/eigen3 |
| robin-map / `tsl` (header) | present | lib/wasm/include/tsl |
| fmt, zlib, zstd, png, jpeg, tiff | present | M1.4/M1.5 |
| Python 3.13 | present | M2.3 |
| **Embree** | **not needed** | OFF → BVH2 fallback compiles |
| **OpenImageDenoise** | **not needed** | OFF |
| **OpenPGL** | **not needed** | OFF |
| **OSL / LLVM** | **not needed** | OFF (deferred) |

**Nothing to cross-compile for a compiling Cycles-CPU.** This is the headline:
the dep wall we feared at M1.3 does not exist for the CPU compile path.

## What this probe did NOT prove (the real M6-render work)

Compile ≠ render. The probe stopped at "objects + static libs build." Still
open, in rough effort order:

1. **LINK a Cycles-enabled `blender.wasm`** — the executable was not linked
   with Cycles in. Expect undefined-symbol / init-registration work where
   `bf_intern_cycles` and `cycles_kernel_cpu` wire into the `blender` binary
   (kernel function-pointer tables, `device_cpu` registration). *Est: 0.5–1.5
   days; likely a few missing-symbol fixes, not a redesign.*
2. **Kernel EXECUTION under wasm** — the scalar CPU kernel compiled, but has it
   ever *run*? Risks: (a) TBB task-arena over `-pthread`/SharedArrayBuffer at
   Cycles' thread intensity (the `-Wpthreads-mem-growth` flag lives here); (b)
   float determinism / `-ffp-contract` differences vs the native oracle inside
   the path tracer; (c) the JSPI-during-static-ctor class (porting-patterns
   Class 4) if any Cycles global blocks. *Est: 1–3 days to first correct pixel
   on a trivial scene.*
3. **Small-scene render parity** (the actual M6 launch-tier gate) — one-light
   one-cube path-trace within Blender's own idiff thresholds vs the oracle.
   *Est: 2–4 days incl. tile/buffer readback and tolerance triage.*
4. **Performance** — scalar-only kernel (no SIMD) will be slow; acceptable for
   "small scenes" launch tier. wasm SIMD (`-msimd128` + widening the SSE arch
   guard, cf. porting-patterns Class 3 shader_tool) is a **later optimization**,
   not a correctness prerequisite. Not attempted here.

## Recommendation

**Feasible as-is for compile; no dep cross-compiles, no upstream patches
required to build.** Recommend M6 promotes Cycles-CPU from "unknown" to
"scheduled": the M1.3 deferral can be closed as *compile-clear*. Flip
`WITH_CYCLES ON` in `blender_web.cmake` behind a build knob when M6 starts, and
spend the budget on **link + kernel-execution + render-parity** (items 1–3, est.
~4–8 days total), not on dependency archaeology. Keep the scalar `KERNEL_ARCH`;
defer wasm-SIMD to a post-parity speed pass.

Suggested `ledger/deferred.json` update: Cycles-CPU is NOT deferred for
compile/dep reasons — only Cycles-*final* (GPU hardware RT / bindless) stays
deferred per GOAL.md.
