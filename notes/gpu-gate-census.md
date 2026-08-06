<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3 GPU backend — full-suite gate census (round 15)

**Measured on** `build-native-gpu/bin/tests/blender_test` (native Dawn/Metal, macOS arm64),
patches through **0091** (this round: 0089 fallthrough GLSL, 0090 customdata inliner,
0091 bind_as_texture). Every test in the `GPUWebGPUTest` suite run **one-per-process**
(crash isolation — the imageAtomic / vertex-RW crashers cannot poison siblings).

## Outcome (the gate measurement)

**158 tests — 148 PASS / 8 FAIL / 2 CRASH.** Every non-PASS is characterized below; none is
an un-diagnosed backend defect. No test result regressed this round; `static_shaders`
internal shader count rose **909 → 951 / 973** (customdata 26→0, switch-fallthrough 16→0).

| Family | Total | PASS | FAIL | CRASH |
|---|---|---|---|---|
| blend | 12 | 12 | | |
| push_constants | 10 | 10 | | |
| preprocess | 28 | 28 | | |
| immediate | 2 | 2 | | |
| compute (direct/indirect) | 2 | 2 | | |
| shader_compute (1d/2d/ibo/ssbo/vbo) | 5 | 5 | | |
| storage_buffer | 5 | 5 | | |
| texture (1d/2d/3d/cube/pool/read/copy/…) | 13 | 13 | | |
| texture_roundtrip | 53 | 51 | 2 | |
| vertex_buffer_fetch_mode | 6 | 5 | 1 | |
| framebuffer | 8 | 6 | 2 | |
| index_buffer_subbuilders / math_lib / eevee_lib | 3 | 3 | | |
| shader (create_info/preprocessor/python/ssbo/…) | 7 | 5 | 1 | 1 |
| specialization_constants (compute/graphic) | 2 | 1 | | 1 |
| buffer_texture | 1 | | 1 | |
| static_shaders | 1 | | 1 | |
| **Total** | **158** | **148** | **8** | **2** |

## The 10 non-PASS, characterized

### FAIL

1. **static_shaders** — 951/973 shaders compile. The 22 remaining, by class:
   - imageAtomic **8** — `tint ReadIR: unhandled SPIR-V OpImageTexelPointer` → **deferral**
     (WGSL has no storage-texture atomics).
   - vertex-stage read_write SSBO **4** — `var 'storage'/'read_write' cannot be used by vertex
     pipeline stage` (draw_curves_test, draw_debug_draw_display, eevee_shadow_tag_update,
     gpu_graphic_specialization_test) → **deferral** (WebGPU forbids it).
   - uniformity **5** — `'workgroupBarrier' must only be called from uniform control flow`
     (eevee_depth_of_field_resolve_{lut,no_lut}, eevee_shadow_tilemap_{init,finalize},
     eevee_shadow_page_mask) → **escalate** (see task-4 finding below).
   - subdiv **4** — `'OsdPatchParamIsRegular' : no matching overloaded function`
     (subdiv_patch_evaluation_{verts,verts_orcos,fvar,fdots_normals}) → **census artifact**
     (runtime-generated OpenSubdiv source; see task-5 finding).
   - fullscreen_blit **1** — Metal-only create-info swept into the census → **census artifact**.
2. **buffer_texture** — bind path now works (patch 0091: `Number of entries` Dawn error gone);
   fails only on the **R32F texel format** — the storage emulation reads a FloatBuffer texel as
   vec4 (16-byte stride) but the source VertBuf is R32F (4-byte). → **blacklist candidate**
   (format-generic access needs a per-pipeline override constant; M3.F12 fallback taken).
3. **shader_sampler_argument_buffer_binding** — guarded `#ifdef WITH_METAL_BACKEND`
   (shader_test.cc:308); a Metal argument-buffer test on a *regular 2D texture*, not a WebGPU
   path. → **census artifact** (Metal-only test).
4/5. **framebuffer_subpass_input / _clearops** — subpass-input / input-attachment gap
   (honest FAIL, characterized r10). → decide fix-or-defer.
6/7. **texture_roundtrip GPU_DEPTH32F_STENCIL8 / GPU_DEPTH_COMPONENT32F** — depth-aspect
   buffer→texture upload; `max_used_bias 0.875 > 0`. → **deferral** (WebGPU forbids writing the
   depth aspect via buffer copy; clear+read work).
8. **vertex_buffer_fetch_mode GPU_COMP_I10 INT_TO_FLOAT_UNIT** — got (160,256,255,0), want
   (321,**-511**,511,0). `wgpu_pipeline.cc:86` maps `GPU_COMP_I10` (signed 2_10_10_10_REV, used
   for packed mesh normals) to `VF::Unorm10_10_10_2` because **WebGPU has no snorm10-10-10-2**
   vertex format; the unsigned read drops the sign. → **deferral or later fix** (NEW; see below).

### CRASH (signal 11 — compile fails → null module → bind/dispatch segfault; honest)

9. **shader_texture_atomic** — imageAtomic (OpImageTexelPointer) → **deferral**.
10. **specialization_constants_graphic** — vertex-stage read_write SSBO → **deferral**.

## (i) Deferral-registry candidates (named WebGPU blocker)

| Candidate | Tests / shaders | Named blocker |
|---|---|---|
| Storage-texture atomics (imageAtomic) | shader_texture_atomic + 8 static | WGSL has no image atomics; Tint rejects OpImageTexelPointer |
| Vertex-stage read_write storage | specialization_constants_graphic + 4 static | WebGPU forbids `var<storage, read_write>` in the vertex stage |
| Depth-aspect buffer→texture upload | 2 texture_roundtrip | WebGPU forbids writing the depth aspect via buffer copy |
| Signed 2_10_10_10 vertex format (GPU_COMP_I10) | vertex_buffer_fetch I10 | WebGPU has no `snorm10-10-10-2` vertex format (NEW this round) |
| Subpass input / input attachment | framebuffer_subpass_input ×2 | no input-attachment equivalent (characterized r10) |

## (ii) Blacklist candidates (with justification)

- **buffer_texture (gpu_buffer_texture_test)** — R32F / non-RGBA32F texel formats need a
  per-pipeline override-constant component count (0079 re-specialization mechanism); the vec4
  storage emulation is correct only for RGBA32F. bind_as_texture is wired (RGBA32F path live),
  so this is format-completeness, not a missing runtime path. M3.F12-authorized fallback.
- **subdiv_patch_evaluation ×4** — `osd_patch_basis.glsl` is a `#pragma runtime_generated`
  placeholder (its header: "This file must be replaced at runtime"). It defines only the
  OsdPatch* *structs*; the *functions* (`OsdPatchParamIsRegular`, `OsdEvaluatePatchBasis`) are
  injected at runtime from `openSubdiv_getGLSLPatchBasisSource()`. The static compile is
  inherently incomplete **for every backend** — not a WebGPU dialect gap. Needs the M6 subdiv
  runtime-injection path, or exclusion from the static census.
- **fullscreen_blit** + **shader_sampler_argument_buffer_binding** — Metal-backend-only. The
  create-info `fullscreen_blit` (`metal/kernels/gpu_shader_fullscreen_blit_infos.hh`, sampler
  literally named `imageTexture`) is registered by **CMakeLists.txt:457 `if(WITH_METAL_BACKEND)`**;
  the test is `#ifdef WITH_METAL_BACKEND`. Because the reference native tree builds with Metal
  available, both are swept into the WebGPU suite through a path they were never meant for.

## (iii) Remaining work for gate-green (driver)

1. **Register deferrals** in `ledger/deferred.json` (M3-boundary): the 5 candidates in (i) with
   their named blockers.
2. **Blacklist** buffer_texture (R32F) and subdiv ×4 (runtime-generated), OR implement the
   override-constant format-generic texel access + OpenSubdiv runtime injection (later rounds).
3. **Filter Metal-only registrations from the WebGPU census** — fullscreen_blit (create-info
   under `WITH_METAL_BACKEND`) and shader_sampler_argument_buffer_binding (`#ifdef
   WITH_METAL_BACKEND` test). `gpu/metal/**` + CMakeLists are off-limits to this worker →
   **escalated**. Cleanest lever: the gate build should not register Metal-backend-only
   create-infos/tests, or the census filters them.
4. **uniformity 5** — needs a driver decision (task-4 finding): a narrow GLSL-restructure
   exception (make the condition provably uniform via `workgroupUniformLoad`, or hoist the
   barrier out of the branch) — same exception class as the fallthrough families — OR a
   deferral. No clean in-bound Tint lever exists (see below).
5. **subpass_input ×2** — decide fix-or-defer.

## Task-4 finding (uniformity, not fixed — needs decision)

The 5 failures are Tint's **conservative uniformity analysis** rejecting `workgroupBarrier()`
inside control flow that depends on a value loaded via `global_invocation_id`. Concrete example
(`eevee_shadow_page_mask:59-65`): the barrier is inside `if (tilemap.projection_type == …)`
where `tilemap = tilemaps_buf[global_id.z]`. Blender's own comment on the line above reads
*"Barriers are ok since this branch is taken by all threads"* — it IS workgroup-uniform in
practice (`global_id.z` is constant across the 2D workgroup), but Tint cannot prove
`global_invocation_id.z` uniform, so it flags the barrier.

**No clean in-bound lever.** `allow_non_uniform_derivatives` (already set,
wgpu_shader_compiler.cc:90) only relaxes *derivative* uniformity — a separate, softer rule with
a `diagnostic(off, derivative_uniformity)` escape. Barrier-in-uniform-control-flow is a **hard
WGSL validation** with no disable option (it is a shader-creation error, re-checked by Dawn).
The faithful fix is a source change to make the condition provably uniform (`workgroupUniformLoad`
of the projection type, or hoisting the barrier) — a GLSL restructure, off-limits this round.
→ Driver decision: GLSL-restructure exception vs. deferral.

## Task-5 findings (root-caused, escalated — not edited)

- **subdiv ×4**: runtime-generated OpenSubdiv source (above). `draw/intern/shaders` +
  `intern/opensubdiv` off-limits → escalate.
- **fullscreen_blit ×1**: Metal-only create-info registered under `WITH_METAL_BACKEND`
  (CMakeLists.txt:457). `gpu/metal/**` off-limits → escalate.
