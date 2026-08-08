<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 r44r2 (bind-namespace lane) - the F12 BindGroup entry-count mismatch family. The r43
# ROOT CAUSE (a frontend bind-unit namespace collision) is FIXED backend-first by patch 0122;
# the remaining bindgroup-6v7 cluster is a DISTINCT pre-existing bug (create-info/WGSL resource
# coverage), not the namespace collision - characterized here and flagged for a follow-up.

Pin: Blender 5.2 `fbe6228777e7`. Builds: `build-native-gpu` (census) + `build-wasm-windowed-opt`
(rebuilt with 0122 2026-08-08). Rigs: sandbox/gpu-r44-r2 (diag_boot.mjs F12; matcap_interactive.mjs;
bridge_boot.mjs + rescore.sh 20-scene). Port 8128. r43 diagnosis: notes/gpu-r43-f12-bindgroup.md.

## ROOT CAUSE (r43, backend-first fix landed): frontend bind-unit NAMESPACE collision
The workbench deferred resolve binds gbuffer textures BY NAME
(`bind_texture("depth_tx"/"normal_tx"/"material_tx")`) but matcap BY FIXED create-info slot
(`bind_texture(WB_MATCAP_SLOT=2, ...)`). On the web backend `build_interface` returned each
resource's DENSE group-0 binding as its frontend unit (`in->location = dense_binding`), while
fixed-slot binds use the literal create-info slot. Two namespaces landed in the single
context-wide bind maps. When a name-resolved dense binding numerically equalled a fixed
create-info slot (matcap resolve: material's dense binding 2 == matcap's create-info slot 2),
they collided in `bound_textures_[2]`: the later material bind overwrote matcap, and the
emit-time remap (slot 2 -> matcap's dense 3) routed material onto matcap's binding b3, leaving
b2 and matcap unfilled -> Dawn "6 vs 10" -> black F12 matcap render. The studio_material COMPUTE
1-vs-4 is the same class. Vulkan never sees this because its interface locations ARE the
create-info slots (`GPU_shader_get_*_binding` returns the create-info slot on vk/GL) - the web
backend's dense return was itself the divergence.

## FIX (patch 0122; wgpu_shader.cc + wgpu_context.cc only) - vk-faithful, backend-only
Unify the frontend bind-unit namespace to the CREATE-INFO SLOT, matching Vulkan:
1. `WGPUShaderInterface::init`: UBO/SSBO/SAMPLER/IMAGE `in->location = in->binding = res.slot`
   (was `dense_binding_of(...)`). Name binds now return the create-info slot, same namespace as
   fixed-slot binds. `enabled_*_mask_` still tracks the dense binding (inert; no consumer).
2. Emit (`append_resource_bind_entries`): every legitimate bind is now MAPPED (its create-info
   slot is in `dense_bindings_`), so the two-pass claim-first logic protects it; the
   dense-namespace sampler STALE-SKIP (which existed only because name binds used to be identity)
   is removed. `remap_*_binding` is unchanged (already keyed by create-info slot -> dense).
3. Buffer-SSBO loop: a texel buffer (`bind_as_texture`) keys on a SAMPLER create-info slot, so it
   remaps via the sampler map (SSBO first, else SAMPLER) - keeps the emulated texel buffer on its
   real dense storage binding.

WGSL/BGL numbering stays DENSE throughout; only the frontend unit-table keying and the
name-resolution output move to the slot namespace, with slot->dense translation at emit. This is
DIFFERENT from the reverted M4.T15 remap-skip, which changed the emit side only (the frontend
still passed dense) and regressed 4 compute tests: a consistent both-sides change does not.

## The remaining bindgroup-6v7 is a DISTINCT bug (NOT the namespace collision)
Proven by the fix outcome: 0122 cleared 6v10 (matcap) and 1v4 (compute) to PASS but did NOT
change any 6v7 scene. Live dump (create_bind_group_checked + append census, reverted):
`workbench_prepass_mesh_opaque_{studio,flat}_material_no_clip` emits bindings [0,1,2,3,4,5]
(pc at 5) while Dawn's layout is 7 ([0..6]) -> b6 unfilled. The layout is
[UBO,UBO,SSBO,SSBO,SSBO,SSBO,UBO]: the materials storage buffer (`Materials.materials_data`,
WB_MATERIAL_SLOT=0, declared in workbench_material.bsl.hh) is present in the WGSL but ABSENT from
the shader's create-info resource list, so `build_dense_bindings` undercounts (5 resources instead
of 6), the push-constant fallback binding lands on a real resource's dense slot, and the last WGSL
binding (b6) never gets bound. This is a create-info/WGSL resource-COVERAGE mismatch in the
workbench prepass, upstream of the bind emit - a separate fix (add the materials buffer to the
prepass create-info, or make the interface map/dense count follow the WGSL survivor set). It hits
~10 scenes (aa-*, dof, in_front*, light_flat_custom/random, light_studio_object*). Flagged for a
follow-up round. (The x-ray cluster is a THIRD, unrelated `gpu-validation` bug.)

## Verification
- **Census (build-native-gpu, run.sh --scope m3):** 149 PASS / 7 FAIL / 2 CRASH / 158 +
  static_shaders 956/973 - HELD. Only the known-spurious I10 un-defer RED. The compute/vertex
  tripwires (compute_direct/indirect, push_constants, specialization, vertex-rw) are clean, so the
  namespace change is consistent (unlike M4.T15).
- **F12 matcap render (diag_boot.mjs, light_matcap.blend):** 0 GPU errors (was the Dawn 6-vs-10
  Invalid CommandBuffer), render completes.
- **Interactive matcap (matcap_interactive.mjs):** switching the viewport to MATCAP light mode
  renders the cube (70 distinct luminances, min 53 max 153) with 0 GPU errors (would fail before).
- **20-scene workbench re-score (bridge_boot.mjs + score.py, verbatim m6 thresholds):** matcap
  6v10 (light_matcap, light_matcap_no_specular) and studio_material 1v4 -> PASS with pixels
  matching the golden (mean ~0.0008); light_flat_attribute -> PASS (round-1 TAA fix, now in tree).
  The 9-10 bindgroup-6v7 scenes and the x-ray gpu-validation scenes still FAIL (distinct bugs, see
  above / cluster column). Table: sandbox/gpu-r44-r2/results.tsv.

## DO-NOT-RE-RUN
1. The matcap 6v10 / compute 1v4 collision is the frontend dense-vs-create-info-slot namespace
   split. FIXED (0122). Do NOT re-attempt an emitter-only or remap-skip fix (M4.T15 regressed
   compute by changing one side only). The fix must keep interface + emit + stale-skip consistent.
2. bindgroup-6v7 is NOT the namespace collision - the namespace fix leaves it unchanged. Its root
   is the workbench prepass materials SSBO missing from the create-info resource list (imap
   undercount / pc-binding collision). Chase it in the create-info / interface-map coverage, not
   the bind emit.
3. Known spurious census RED (do not chase): vertex_buffer_fetch_mode GPU_COMP_I10
   INT_TO_FLOAT_UNIT un-defer candidate (human-owed).

## Evidence (`sandbox/gpu-r44-r2/`)
`diag_boot.mjs`, `matcap_interactive.mjs`, `bridge_boot.mjs`, `rescore.sh`; `results.tsv`
(20-scene table); `matcap_live.png` (+ .license) interactive matcap; `caps/matcap_f12/`
(0-error F12 render); `census-final.log`. Patch
`patches/0122-gpu-webgpu-bind-unit-create-info-slot-namespace.patch` (git apply --check --reverse
OK inside upstream). All BW_DIAG_BIND instrumentation reverted grep-clean.
