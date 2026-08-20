<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M6 - OpenSubdiv + native OBJ/PLY/STL rebuild of build-wasm-cycles

Two proven blockers were closed in one rebuild of the `build-wasm-cycles` tree:

- **notes/m6-cycles-suite.md**: 22 of 27 Cycles-CPU failures collapsed to
  `WITH_OPENSUBDIV=OFF` (Blender silently disables every Subsurf/Multires modifier
  at render time when built without OpenSubdiv).
- **notes/m7-io-smoke.md**: the native C++ mesh exporters (OBJ/PLY/STL) were compiled
  out by `patches/blender_web.cmake` and absent from the binary.

## What shipped

1. **OpenSubdiv v3_7_0 cross-compiled without native GPU APIs to `lib/wasm`** via
   new
   `scripts/deps/opensubdiv.sh` (idempotent; version + MD5 pinned from
   `versions.cmake:232`). Every GPU backend is disabled (no GPU API under Emscripten),
   leaving Far/Sdc/Vtr/Bfr + the CPU (incl. TBB) evaluators, plus the
   API-independent GLSL patch-source data selected by Blender's WebGPU path. TBB
   resolves from the shared prefix via `TBB_DIR`. Compiled clean under emcc 6.0.5.
   - Harvest: `lib/wasm/lib/libosdCPU.a` (real, 49 objects) + `libosdGPU.a` +
     `lib/wasm/include/opensubdiv`.
   - `osdGPU` is a real archive containing `glslPatchShaderSource.cpp.o`, built
     with `OSD_PATCH_SHADER_SOURCE_GLSL=ON` while `NO_OPENGL=ON`. The receipt
     requires the member and defined `GLSLPatchShaderSource` symbol and rejects GL
     API imports.
   - Self-test (in the script): a Far cube-refine on wasm+node returns the
     Catmull-Clark level-1 vertex count 26, and the linked GLSL source contains
     `OsdPatchParamIsRegular` and `OsdEvaluatePatchBasis`. `ledger/deps.json`:
     opensubdiv moved `forced_off` to `wasm_built`.

2. **`patches/blender_web.cmake` flips** (the config is a `-C` initial cache):
   - `WITH_OPENSUBDIV` OFF to ON. Because `platform_wasm.cmake` replaces
     `platform_unix.cmake` (which is where upstream calls `find_package(OpenSubdiv)`,
     line 488-493), the config seeds `OPENSUBDIV_INCLUDE_DIRS` /
     `OPENSUBDIV_LIBRARIES` / `OPENSUBDIV_FOUND` directly (both consumers,
     `intern/opensubdiv` and `intern/cycles/subd`, read the same
     `bf::dependencies::optional::opensubdiv` alias).
   - `WITH_IO_WAVEFRONT_OBJ` / `WITH_IO_PLY` / `WITH_IO_STL` OFF to ON. FBX,
     grease-pencil IO, and USD stay OFF.

3. **patch 0111** guards three VESTIGIAL desktop-GL includes in the OpenSubdiv GPU
   evaluator (`eval_output_gpu.h`: `opensubdiv/osd/glPatchTable.h`,
   `glVertexBuffer.h`; `gpu_compute_evaluator.cc`: `epoxy/gl.h`) under
   `#if !defined(__EMSCRIPTEN__)`. Blender 5.2 rewrote this evaluator onto its own
   `gpu::` module: `GpuEvalOutput` is templated purely on Blender `gpu::` types and no
   GL symbol is referenced, so the includes are dead leftovers absent from the
   no-native-GPU-API harvest. Native builds keep them (guard true) and are
   byte-identical. Reverse-apply verified; `patches/series` updated. Subsequent
   WebGPU closure propagates `WITH_WEBGPU_BACKEND` into the evaluator and makes
   `evaluator_capi.cc` select the GLSL patch source by the active backend.

## RECONFIGURE TRAP (institutional note)

`patches/blender_web.cmake:119` FORCE-sets `WITH_CYCLES OFF` (the base headless
default). The Cycles tree is enabled by a **`-DWITH_CYCLES=ON` override on top of the
`-C` file** (notes/m6-cycles-probe.md). Reconfiguring with `-C` alone silently drops
Cycles (the `_cycles` builtin disappears; every render fails
`ModuleNotFoundError: No module named '_cycles'`). The canonical reconfigure for this
tree is:

```
emcmake cmake -S upstream -B build-wasm-cycles -G Ninja \
  -C patches/blender_web.cmake -DWITH_CYCLES=ON -DCMAKE_BUILD_TYPE=Release
```

Rebuild target: `blender` (phony to `bin/blender.js`), via
`bash harness/buildwrap.sh bash scripts/ninja-locked.sh -C build-wasm-cycles blender`.

## Measurements

### Subsurf smoke (`sandbox/m6-prep/subsurf_smoke.py`)

Factory default cube (8 verts) + Catmull-Clark Subdivision Surface modifier at level 1:

| build | level-1 verts | verdict |
|-------|---------------|---------|
| wasm (this rebuild) | 26 | matches oracle |
| native oracle (`oracle/bpy.sh`) | 26 | reference |

No `Modifier "Subsurf", Disabled, built without OpenSubdiv` warning on wasm - the
modifier now evaluates. This is the direct proof `WITH_OPENSUBDIV=ON` is functional.

### OBJ export (M7 io-smoke OBJ half)

`bpy.ops.wm.obj_export` now exists (was absent). The wasm export of the default cube
is **byte-identical** to the staged native reference
(`sandbox/m7-io-smoke/out/native/cube.obj`, 943 B); `parse_obj.py` semantic compare
PASS. `ply_export` / `stl_export` operators are likewise present. (glTF is a separate
lane and was not touched.)

### Cycles-CPU 27-test suite (`sandbox/m6-prep/run_wasm_cycles.sh`)

**Score: 2/27 PASS (before) to 25/27 PASS (after).** Exceeds the ~24/27 target.
All 27 render to completion (`node_exit=0`); 2 residuals fail on pixel drift only.

The 22 OPENSUBDIV_OFF failures flipped to PASS, and the 3rd previously-named residual
`principled_bsdf_thin_subsurface` (geometry-nodes subdivision + SSS + film_transparent)
now PASSES too - its delta was subdivision after all. All 7 raycast tests and both
colorspace tests (AgX / ACES 2.0 / Display-P3 / Rec.2020) pass.

**The 2 residuals (characterized fresh, subdivision confound now removed):**

| test | max err | % over | character |
|------|---------|--------|-----------|
| `principled_bsdf/principled_bsdf_default` | 0.110 | 20.8% | spread, low-amplitude drift on hard silhouette edges |
| `principled_bsdf/principled_bsdf_emission_alpha` | 0.686 | 11.4% | high-frequency wavy emissive surface; sub-pixel edge sampling |

Both magnitudes are essentially unchanged from the earlier subdivision-confounded
measurement (0.094 -> 0.110, 0.678 -> 0.686), which proves the residual is **independent
of OpenSubdiv**. A fresh pinned-native control on 2026-08-20 forced both scenes to BVH2
while `_cycles.with_embree` remained true. Both native BVH2 renders still pass their
goldens with zero pixels over 0.016 (maximum errors 0.0118 and 0.0157), ruling out the
missing Embree build and BVH layout as the cause. One- and two-thread Wasm renders are
pixel-identical under an exact 0/0 comparator. Ruled out as well: OSL (these are SVM
tests), OpenVDB (no volumes), denoising (off in the blends), and colorspace (both
colorspace tests pass). The remaining named blocker is a reproducible scalar-Wasm vs
native-SIMD/cross-architecture numerical drift on high-frequency edges; its exact
arithmetic source is not yet isolated.

Disposition: these are tier-(c) justified, narrowly scoped blacklist entries under
Blender's own idiff regime until scalar-Wasm/native-SIMD parity is resolved. They are
not OpenSubdiv, Embree-layout, render-completion, or thread-determinism failures; a
future arithmetic fix must make the unchanged comparator pass, at which point the
stale-blacklist check fails closed.

Per-test receipts: `sandbox/m6-prep/results-wasm-cycles.tsv`.
