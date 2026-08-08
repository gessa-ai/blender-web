<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# r43 - workbench F12 render BindGroup ENTRY-COUNT MISMATCH: root cause (frontend bind-unit collision)

Redo of dead lane r40. Mission: root-cause and fix the F12 offscreen "BindGroup has N
entries, layout expects M" family (notes/m6-gpu-suite-real-scores.md clusters
bindgroup-6v7 / 6v10 / 1v4). OUTCOME: root-caused with a decisive live dump; the true
root is a FRONTEND bind-unit namespace collision under source/blender/draw/ (r44's fence /
forbidden for this lane), NOT the wgpu_context.cc two-pass assembly. Per the mission
protocol for a forbidden-file root, this lane is DIAGNOSIS-ONLY: no 0122 patch, all
instrumentation reverted, native census re-confirmed green.

## Reproduction

Representative scene: workbench/light_matcap (128x128 F12 render, startup-file boot,
the r35 render bridge flow). Driver: sandbox/gpu-r43/diag_boot.mjs (captures the FULL
browser console so the BW_DIAG-gated bind dump survives). GPU error, every boot:

    Number of entries (6) did not match the expected number of entries (10)
    for [BindGroupLayoutInternal (unlabeled)]   (x8 per render -> Invalid CommandBuffer)

Expected layout (from Dawn): TEX b0(depth,2D) b1(normal,2D) b2(material,2D)
b3(matcap,2D-ARRAY); UBO b4 b5; SAMP b256 b257 b258 b259.

## THE KEY DISCRIMINATOR (resolves the "interactive works, F12 fails" premise)

The interactive viewport was NEVER running the failing shader. Timeline of the same boot
(sandbox/gpu-r43/caps/matcap/console.all.log):

- BEFORE "RENDER START": the viewport draws `workbench_resolve_opaque_studio...` -> 8/8
  entries, 0 errors. (This .blend's VIEW3D shading is STUDIO.)
- AFTER "RENDER START" (the F12 render, which uses the scene RENDER shading = MATCAP):
  `workbench_resolve_opaque_matcap...` -> 6/10 entries, error.
- AFTER "RENDER DONE": viewport returns to the studio resolve -> 8/8 again.

So the bug is not offscreen-vs-interactive. It is the MATCAP resolve variant, which for
this .blend only the F12 render exercises. The matcap composite fails identically wherever
it runs (a real interactive session set to matcap shading would fail too).

## ROOT CAUSE (live-proven, sandbox/gpu-r43/evidence/matcap-resolve-6of10.dump.txt)

The workbench deferred RESOLVE pass (source/blender/draw/engines/workbench/
workbench_mesh_passes.cc:133-138) binds gbuffer textures BY NAME
(`bind_texture("depth_tx"/"normal_tx"/"material_tx", ...)`) but binds the matcap texture
BY A FIXED CREATE-INFO SLOT (`bind_texture(WB_MATCAP_SLOT, resources.matcap_tx)`,
WB_MATCAP_SLOT == 2).

In the WebGPU backend two bind conventions land in the SINGLE context-wide
`bound_textures_` map, keyed by the raw frontend unit:
- name-resolved binds use the DENSE group-0 binding as their unit (build_interface sets
  in->location = dense_binding). For the matcap resolve: depth->0, normal->1, MATERIAL->2,
  matcap-would-be->3.
- the fixed-slot matcap bind uses its literal create-info slot as the unit: matcap->unit 2.

matcap's create-info slot (2) NUMERICALLY EQUALS material's dense binding (2). Both bind
into `bound_textures_[2]`. In the composite the matcap bind is issued first and the
name-resolved material bind second, so MATERIAL overwrites MATCAP at key 2. The map now
holds material at unit 2 and matcap is GONE.

Live census at the failing draw (type=2 is GPU_TEXTURE_2D, type=18 is 2D_ARRAY):

    BND TEX slot=2 ->b=3 mapped=1 type=2  fmt=40   <- MATERIAL (2D), routed to b3
    BND TEX slot=0 ->b=0 mapped=0 type=2  fmt=49   <- depth
    BND TEX slot=1 ->b=1 mapped=0 type=2  fmt=21   <- normal
    BND TEX slot=3 ->b=0 mapped=1 type=2  fmt=22   <- stale prepass dummy (WB_TEXTURE_SLOT)
    BND TEX slot=4 ->b=1 mapped=1 type=18 fmt=22   <- stale dummy (WB_TILE_ARRAY)
    BND TEX slot=5 ->b=2 mapped=1 type=17 fmt=22   <- stale dummy (WB_TILE_DATA, 1D_ARRAY)
    (matcap 2D_ARRAY texture: ABSENT)

Because unit 2 IS matcap's create-info slot, the shader remap sends WHATEVER sits at unit 2
(now material) to binding 3 (matcap's dense). So:
- b3 wants a 2D-ARRAY (matcap): only unit 2 remaps here, holding material (2D). WRONG kind
  and the texture the shader needs (matcap) no longer exists.
- b2 wants material (2D): only unit 5 remaps here, holding the WB_TILE_DATA dummy, which is
  a 1D_ARRAY - wrong view dimension for a 2D binding.

Then the emitter's texture stale-skip guard (wgpu_context.cc, texture loop, the
`pass == 0 && item.first != n && is_texture_binding(n) && bound_textures().find(n)!=end()`
block) drops BOTH survivors: the material-at-unit-2 -> b3 is skipped (a texture exists at
frontend slot 3, the dummy), and the dummy-at-unit-5 -> b2 is skipped (a texture exists at
frontend slot 2, material). Net emitted textures = b0, b1 only; samplers b256, b257 only;
+ UBO b4, b5 = 6. Missing b2, b3, b258, b259 -> 6 vs 10.

## Why the studio variant binds fine (factory-default path)

The matcap sampler is `[[sampler(WB_MATCAP_SLOT), condition(lighting_mode == MATCAP)]]`, so
it is in the interface ONLY for the matcap variant. In the studio variant create-info slot 2
is NOT a dense-map key, so the texture bound at unit 2 (material, name-resolved) is IDENTITY
(mapped=0), remaps to b2, and emits correctly: 8/8 (evidence
studio-resolve-8of8.dump.txt). The collision is unique to the matcap variant because only
there does a fixed create-info slot (2) overlap a name-resolved dense binding (2).

## Why this is NOT fixable in wgpu_context.cc / wgpu_batch.cc (the fence)

The collision destroys the matcap texture and mis-routes material in `bound_textures_`
BEFORE `append_resource_bind_entries` runs. By emit time:
- the matcap 2D_ARRAY texture is not in any bind space (unrecoverable);
- material can only reach b3 (unit 2 remap), never its intended b2;
- the only texture remapping to b2 is a 1D_ARRAY dummy (wrong view dimension).
No emitter logic can conjure the missing matcap texture or move material to b2, and the
`slot_is_mapped` inference cannot disambiguate "name-resolved bind that landed on unit 2"
from "fixed create-info-slot-2 bind" because unit 2 is legitimately both. A valid,
count-matching, dimension-correct 10-entry group is IMPOSSIBLE to assemble from the
collided map. (A tightened stale-skip guard was traced and rejected: it would emit the
1D_ARRAY dummy at the 2D binding b2, trading the count error for a view-dimension error.)

Systemic, not one-off: the same root shows in other clusters. light_studio_material F12
shows `workbench_resolve_opaque_studio_cavity_curvature...` at 9/13 (adds the curvature
object_id_tx name-resolved sampler colliding the same way) and a separate COMPUTE dispatch
at 1/4 (storage-image bind space, same raw-unit-namespace class). All are frontend/interface
bind-unit collisions, not two-pass assembly defects.

## PROPOSED FIX (for the driver - lands in forbidden files)

Cleanest, mirrors the gbuffer textures (RECOMMENDED):
- In source/blender/draw/engines/workbench/workbench_mesh_passes.cc, bind matcap BY NAME in
  the composite/resolve pass: `deferred_ps_.bind_texture("matcap_tx", resources.matcap_tx)`
  instead of `bind_texture(WB_MATCAP_SLOT, ...)`. Name resolution returns matcap's dense
  binding (3), so it stores at unit 3 (no overlap with material's dense unit 2), and both
  emit correctly. (The prepass fixed-slot bind is safe: the prepass binds ONLY fixed slots,
  no name-resolved sampler collides there. The collision is specific to the resolve pass,
  which mixes name-resolved gbuffer textures with the fixed matcap slot.)
- This is source/blender/draw/ = r44's fence this round and outside r43's fence.

Alternative (interface layer, riskier): make name resolution return the create-info slot
rather than the dense binding (build_interface: in->location), so all texture binds share
the create-info namespace and the emit-time remap handles both. This is
wgpu_shader_compiler.cc / wgpu_shader_interface_map.cc and would unravel the 0112/0116
two-pass design (which is built on in->location == dense_binding); not recommended.

## What was falsified

- "F12 offscreen path assembles bind groups differently from the viewport." FALSE. The
  explicit BGL is shader-global (built once at finalize from the WGSL survivor set,
  identical in both paths). The divergence is the SHADER VARIANT (matcap vs studio), not
  the render path. The viewport just happened to run studio for this .blend.
- "The two-pass mapped/identity claim machinery drops a recoverable entry." FALSE. The
  entry is not recoverable at emit time; the texture is already destroyed at bind time.
- Tightened texture stale-skip guard as the fix. FALSIFIED (produces a view-dimension error
  at b2 from the only available 1D_ARRAY dummy).

## DO-NOT-RE-RUN

- Do NOT re-attempt an emitter-only fix in wgpu_context.cc/wgpu_batch.cc for this family;
  proven impossible above.
- Do NOT re-add the has_explicit_layout()-gated dump condition first tried; the failing
  resolve DOES have an explicit layout, but UI shaders (pc=1) exhaust any low cap before the
  render runs. Gate on `!has_pc && entries.size() >= 3` and split on the RENDER markers.
- Known spurious census RED (do not chase): vertex_buffer_fetch_mode GPU_COMP_I10
  INT_TO_FLOAT_UNIT un-defer candidate (harness EXPECT map stale; human-owed).

## Evidence index

- sandbox/gpu-r43/evidence/matcap-resolve-6of10.dump.txt - the failing draw: layout,
  interface map, emitted entries, and full bound-resource census (material at unit 2).
- sandbox/gpu-r43/evidence/studio-resolve-8of8.dump.txt - the working studio variant.
- sandbox/gpu-r43/evidence/gpu-error-6v10.txt - the raw Dawn validation error (BASELINE
  build, no instrumentation - proves the bug is not an instrumentation artifact).
- sandbox/gpu-r43/caps/matcap/console.all.log - full timeline (studio before RENDER START,
  matcap after).
- sandbox/gpu-r43/caps/studiomat/console.all.log - breadth: 9v13 resolve + 1v4 compute.
- sandbox/gpu-r43/diag_boot.mjs - the capture driver.

## Census (final tree = baseline, all r43 instrumentation reverted)

build-native-gpu blender_test rebuilt; harness/run.sh --scope m3:
149 PASS / 7 FAIL / 2 CRASH / 158 GPUWebGPUTest; static_shaders 956/973. The scope reports
pass:false SOLELY on the known-spurious I10 un-defer candidate. No regression.
