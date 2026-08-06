<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3 GPU gate — blacklist justification

Transcribed from `fix_plan.md` M3.F13-DECISIONS (decision 3 + decision 4) and
`notes/gpu-gate-census.md` §(ii). The driver decided the dispositions; this doc records them
with per-group justification, evidence citation, and revisit condition.

## Blacklist is not deferral

- A **deferral** (`ledger/deferred.json`) is a shipping-scope gap with a named WebGPU blocker:
  a capability the port does not deliver, honestly logged so the dashboard shows it.
- A **blacklist** entry is a *test-harness exclusion* with a named cause: the gate measurement
  drops the test, but no shipping capability is being quietly withdrawn. Either the failure is
  not a WebGPU defect (Metal-only artifact, backend-agnostic runtime-injection gap), or the
  covered path is validated by a sibling and only a format-completeness tail remains.

This mirrors native Blender's own practice — tier-c is defined against "a justified per-test
blacklist exactly as native Blender maintains" (GOAL.md:17), and Blender's EEVEE/render suites
ship verbatim BLOCKLISTs (e.g. `eevee_render_tests.py`). The bar is a *named cause per exclusion*,
not zero exclusions.

Gate context: the full `GPUWebGPUTest` suite is **158 tests → 148 PASS / 8 FAIL / 2 CRASH**, every
non-PASS characterized, zero undiagnosed backend defects (`notes/gpu-gate-census.md`). Of the 10
non-PASS: 5 are registered deferrals (`ledger/deferred.json`, M3 gate entries), 1 aggregate
(`static_shaders`, 951/973) whose remaining shaders split across those deferrals + the approved
uniformity-5 GLSL restructure + two of the blacklist groups below, and the 3 groups here.

## (i) `gpu_buffer_texture_test` — R32F texel format

- **What:** 1 FAIL. `bind_as_texture` is wired (patch 0091) and the **RGBA32F** buffer-texture path
  is live and correct; the test still fails only on the **R32F** texel format — the vec4 storage
  emulation reads a `FloatBuffer` texel as vec4 (16-byte stride) while the source `VertBuf` is R32F
  (4-byte stride).
- **Justification:** this is **format-completeness, not a missing runtime path**. The launch
  buffer-texture path (RGBA32F) is validated indirectly through the live bind path; only
  non-RGBA32F texel formats need a per-pipeline override-constant component count (the 0079
  re-specialization mechanism). M3.F12-authorized fallback taken.
- **Evidence:** `notes/gpu-gate-census.md` §(ii) bullet 1 + FAIL #2; patch 0091 (`bind_as_texture`).
- **Revisit:** post-launch format-generic work — implement the override-constant format-generic
  texel access (per-pipeline component-count override) so R32F / other non-RGBA32F formats resolve.

## (ii) `subdiv_patch_evaluation` ×4 — runtime-generated OpenSubdiv basis

- **What:** 4 shaders in the `static_shaders` aggregate fail to compile
  (`subdiv_patch_evaluation_{verts,verts_orcos,fvar,fdots_normals}`):
  `'OsdPatchParamIsRegular' : no matching overloaded function`.
- **Justification:** `osd_patch_basis.glsl` is a `#pragma runtime_generated` placeholder (its own
  header: "This file must be replaced at runtime"). It defines only the `OsdPatch*` *structs*; the
  *functions* (`OsdPatchParamIsRegular`, `OsdEvaluatePatchBasis`) are injected at runtime from
  `openSubdiv_getGLSLPatchBasisSource()`. The static compile is therefore inherently incomplete
  **for every backend** — this is **not a WebGPU dialect gap**; the runtime OpenSubdiv basis
  injection is simply absent at this static-compile harness profile.
- **Evidence:** `notes/gpu-gate-census.md` §(ii) bullet 2 + FAIL #1 (subdiv) + Task-5 finding.
- **Revisit:** the M6 subdiv runtime-injection path (wire `openSubdiv_getGLSLPatchBasisSource()`
  into the shader assembly), or exclusion from the static census. `draw/intern/shaders` +
  `intern/opensubdiv` are off-limits to the gate worker — escalated.

## (iii) `fullscreen_blit` + `shader_sampler_argument_buffer_binding` — Metal-only registrations

- **What:** `fullscreen_blit` is 1 shader in the `static_shaders` aggregate;
  `shader_sampler_argument_buffer_binding` is 1 FAIL.
- **Justification:** both are **Metal-backend-only**, swept into the WebGPU suite through a path
  they were never meant for — **census artifacts, not WebGPU defects**. The create-info
  `fullscreen_blit` (`metal/kernels/gpu_shader_fullscreen_blit_infos.hh`, sampler literally named
  `imageTexture`) is registered by **`CMakeLists.txt:457 if(WITH_METAL_BACKEND)`**; the test
  `shader_sampler_argument_buffer_binding` is guarded `#ifdef WITH_METAL_BACKEND`
  (`shader_test.cc:308`) and exercises a Metal argument-buffer path on a regular 2D texture, not a
  WebGPU path. Because the reference native gate tree builds with Metal available, both register
  and run. Per F13 decision 3: excluded with cmake evidence, **no code change** (`gpu/metal/**` +
  `CMakeLists` are off-limits) — escalated.
- **Evidence:** `notes/gpu-gate-census.md` §(ii) bullet 3 + FAIL #3/#1 (fullscreen_blit) +
  Task-5 finding; `CMakeLists.txt:457`; `shader_test.cc:308`.
- **Revisit:** re-evaluate only if the gate build stops registering Metal-backend-only
  create-infos/tests (configure the census build without the Metal backend, or filter Metal-only
  registrations from the WebGPU census). No WebGPU-side work exists to do.
