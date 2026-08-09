<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# r46 - finishing the dead r44 round 3: the bindgroup-6v7 fix + a full residual re-diagnosis

Round 3 (r44 lane, session-killed 2026-08-08 ~18:16, transcript gone) left uncommitted WIP in
the webgpu backend. This lane audited that WIP, PROVED the fix, re-diagnosed every residual
cluster from live Dawn messages (overturning the standing hypotheses), and produced patch 0124.
Pin: Blender 5.2 `fbe6228777e7`. Builds: build-wasm-windowed-opt (blender_browser.wasm 18:17,
built by round 3 from the exact WIP source) + build-native-gpu (census, wgpu_shader.cc.o 18:16).
Rig: sandbox/gpu-r46 (bridge_boot.mjs + rescore.sh, repointed from r44-r2; full dedup error dump
added). Port 8128.

## WIP AUDIT VERDICT: KEEP (coherent, instrumentation-free)
The webgpu/ dir is untracked (both outer and inner git), so no git-diff. I reconstructed the
post-0123 baseline of all 5 WIP files + wgpu_texture.cc by replaying the patch series hunk-by-hunk
into a scratch tree, then diffed against the working tree. Net round-3 content:

- **wgpu_shader.cc**: ADDED one block (WGPUShaderInterface::init, after the SSBO loop) that
  populates `ssbo_attr_mask_` from `info.geometry_resources_` STORAGE_BUFFERs. THIS is the 6v7
  fix. A faithful mirror of vk_shader_interface.cc:171 / gl_shader_interface.cc:507.
- **wgpu_state_manager.cc** and **wgpu_uniform_buffer.cc**: COMMENT-ONLY updates aligning the
  `unit`/`slot` docs with the 0122 create-info-slot namespace. Correct; never captured in a patch
  (uncaptured r44r2/round-3 doc drift). Kept and folded into 0124.
- **wgpu_context.cc, wgpu_batch.cc, wgpu_texture.cc**: net-zero vs baseline (mtime bumps were
  instrumentation touch/revert). Confirmed: context.cc bind-emit == 0122 post-image exactly;
  batch.cc == baseline (the apparent diff was reconstruction missing patch 0114's index-upload,
  which the working tree correctly has); texture.cc byte-identical to the reconstructed baseline.

No BW_DIAG-style leftover instrumentation anywhere (only the pre-existing wgpu_diag_readback
"no-op unless BW_DIAG" comments). The WIP is coherent -> kept as the fix basis, no re-implement.

## 6v7 DESIGN ANSWER: neither (a) nor (b) - it is (c), and it falsifies the r44r2 premise
The mission framed the 6v7 root as "(a) interface-follows-WGSL-survivor-set vs (b) create-info
gap (the workbench prepass materials SSBO absent from the create-info resource list)". Both are
WRONG. The honest, behaviorally-proven root:

  The shared frontend `gpu_batch.cc` (draw_expand / primitive-expansion path) gates the entire
  geometry-frequency SSBO bind on `if (interface->ssbo_attr_mask_ == 0) return;` (gpu_batch.cc:263),
  then binds the index buffer as an SSBO at GPU_SSBO_INDEX_BUF_SLOT (line 273) only when its bit
  is set. vk/GL populate `ssbo_attr_mask_` in their shader-interface init from
  info.geometry_resources_; the WebGPU interface OMITTED that loop, so the mask stayed 0, the
  frontend early-returned, and the shadow/vertex-pull index buffer (the last WGSL binding, dense
  b5/b6) was NEVER bound -> Dawn "6 entries vs 7" -> Invalid CommandBuffer -> black render for
  every shadow-enabled workbench scene.

This is NOT the materials-SSBO-absent-from-create-info hypothesis: the fix touches neither the
create-info nor the interface map / survivor set. Populating ssbo_attr_mask_ (which is about the
geometry-frequency vertex-pull/index buffer, unrelated to Materials.materials_data) cleared the
6v7 signature across ALL ~10 scenes. The r44r2 "distinct materials-SSBO bug" note is superseded.

## BEFORE / AFTER (live, port 8128, 128x128 F12 bridge)
Committed r44-r2 tsv (BEFORE) vs r46 build (AFTER), representative ex-6v7 scenes:

  scene                 BEFORE (0122 tree)              AFTER (0124 tree)
  light_studio_object   FAIL 456 gpuErr bindgroup-6v7   24 gpuErr, NO bindgroup-count error
  aa-disabled           RENDER-BLACK 42 bindgroup-6v7   3 gpuErr gpu-validation (no 6v7)
  aa-single-pass        RENDER-BLACK 42 bindgroup-6v7   3 gpuErr gpu-validation (no 6v7)
  dof                   FAIL 432 bindgroup-6v7          gpu-validation (no 6v7 count error)

The "6 entries vs 7" / "N did not match expected M" BINDGROUP-COUNT error is GONE from every
ex-6v7 scene; error counts collapse 456/432/42 -> 24/3. What remains is a DIFFERENT, smaller
residual (below). (The dead lane's tsv RENDER-CRASH rows - light_matcap etc. - were harness boot
flakiness, gpuErr=0; a clean re-run renders them.)

## RESIDUALS - re-diagnosed from live Dawn messages (all standing hypotheses falsified)
Exposing the shadow index buffer uncovered TWO independent residual classes, plus the pre-existing
compute 1v4. NONE is the depth-aspect issue the mission/dead-lane predicted (M4.T16(b) FALSIFIED).

1. **x-ray cluster (x-ray, x-ray_back_cull, x-ray_in_front, rec2020_lights)** - COLOR-TARGET
   COMPACTION. Full dedup dump (sandbox/gpu-r46/caps/workbench_workbench_x-ray/gpuerrors.uniq.txt),
   one unique root, 40x cascade:
     "Color format (TextureFormat::R16Uint) base type (Uint) doesn't match the fragment module
      output type (Float). While validating targets[0] ... CreateRenderPipeline."
   Mechanism: workbench TransparentDepthPass builds framebuffers with GPU_ATTACHMENT_NONE gaps -
   `in_front_fb.ensure(depth, NONE, NONE, object_id)` (workbench_mesh_passes.cc:349,362), object_id
   (R16Uint) at COLOR SLOT 2. `WGPUFrameBuffer::target_formats` (wgpu_framebuffer.cc:382-388)
   COMPACTS - `colors[color_count++]` skips NONE slots - so R16Uint lands at targets[0], where
   wgpu_pipeline.cc pairs it against the WGSL @location(0) float output (frag_opaque writes
   material@0/normal@1/object_id@2). Native Vulkan keeps the gap (VK_ATTACHMENT_UNUSED at 0/1) and
   discards the unmatched material/normal outputs; WebGPU is strict (a @location(i) output REQUIRES
   a non-null targets[i], and vice-versa). So neither compaction NOR sparse-hole targets fixes it
   alone - the faithful fix needs framebuffer-slot-indexed targets AND framebuffer-aware fragment
   output masking (or per-framebuffer fragment variants). That lives in wgpu_framebuffer.cc +
   wgpu_pipeline.cc (OUTSIDE this lane's 6-file fence) and is a real WebGPU-strict-vs-Vulkan-lenient
   semantic gap. Per the r43 precedent for out-of-fence roots -> DIAGNOSIS-ONLY this round.

2. **ex-6v7 residual (light_studio_object, in_front, light_studio_object_no_specular, ...)** -
   depth texture at a Uint sampler slot. Dump: entries[7] vs { binding: 4, texture sampleType Uint }:
     "None of the supported sample types (UnfilterableFloat|Depth) of [Texture
      Depth32FloatStencil8] match the expected sample types (Uint)."
   A Depth32FloatStencil8 texture is bound to a BGL slot whose sampleType is Uint (the object_id
   usampler2D, R16Uint). The BGL sampleType Uint is CORRECT (the shader genuinely declares a
   usampler for object_id); the WRONG texture (a depth texture) is landing on it - a residual
   bind collision in the cavity/curvature resolve (the r43-noted 9v13 site), NOT a sample-type
   derivation bug and NOT an aspect bug. So M4.T16(b)'s "force DepthOnly aspect in
   wgpu_texture.cc sampled_view" would NOT fix it (a Uint slot, not a Float slot). This is a
   follow-up in the 0122 namespace family (a residual object_id/depth bind-unit collision).

3. **1v4 compute (light_studio_material, still PASSes on pixels, logs the errors)** - a COMPUTE
   bind group emits 1 of 4 entries. Expected layout: binding0 storageTexture RGBA8Unorm ReadOnly,
   binding1/2 storageTexture RGBA8Unorm WriteOnly, binding3 buffer Uniform; only 1 bound. A compute
   storage-image + UBO dispatch undercount (the cavity/AA compute site). In-fence candidate
   (wgpu_context.cc image bind emit) but NOT the namespace collision the 0122 fix addressed; not
   attempted this round (budget + it does not block the pixel pass).

## FENCE / SCOPE NOTE
Primary (6v7) is IN fence and DONE + proven. The three residuals are: x-ray (out of fence,
framebuffer/pipeline + WebGPU semantic gap), ex-6v7 depth-Uint (namespace follow-up), 1v4 compute
(in-fence candidate, deferred). Precise, actionable roots recorded above for the driver/next lane.
No workbench/harness/oracle/tests/threshold files touched. wgpu_texture.cc untouched (the mission's
predicted x-ray fix site does not apply - the root is color-target, not depth-sample).

## VERIFICATION
- 6v7 behavioral: see BEFORE/AFTER. 6v7 bindgroup-count error eliminated on every ex-6v7 scene.
- 20-scene rescore: sandbox/gpu-r46/results.tsv (table in the ledger entry).
- Census (build-native-gpu, run.sh --scope m3): recorded in the ledger entry; static_shaders held.
- Patch 0124 (git apply --check --reverse OK inside upstream; forward round-trip exact for all 3
  files). Applies after 0123 (regions disjoint from 0122/0123).

## DO-NOT-RE-RUN
1. 6v7 is the ssbo_attr_mask_ omission (frontend geometry-SSBO gate), NOT the materials-SSBO
   create-info gap. Fixed by mirroring vk/GL. Do not chase the create-info/survivor-set angle.
2. The x-ray residual is color-target compaction on NONE-gap framebuffers, NOT a depth aspect /
   sample-type issue. M4.T16(b) does not apply to x-ray. Fix is in wgpu_framebuffer.cc +
   wgpu_pipeline.cc + a fragment-output-masking feature.
3. The ex-6v7 depth-Uint residual is a Uint object_id slot receiving a depth texture (bind
   collision), NOT a sample-type derivation or aspect bug.
