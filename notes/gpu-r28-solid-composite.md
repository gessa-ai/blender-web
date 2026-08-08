<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 28b TAKE 3 (gpu-backend worker) — the workbench SOLID cube: TWO bugs. Bug A (deferred composite read stale textures) FIXED as patch 0116; Bug B (opaque-group prepass writes no gbuffer depth) ISOLATED, still open.

Continues notes/gpu-r28-solid-and-gizmo.md (r28a) + the r28b FORCE_GBUF_CLEAR finding
("composite does not gate on scene depth"). Rig = the r23 visible recipe (headed
Playwright, bundled Chromium, `?gate=1280x720` + `?pyexpr=` splash-off + a per-0.3s
VIEW_3D `tag_redraw()` kick), opt tree `build-wasm-windowed-opt` port 8124. Method:
temporary once-per-tuple stderr fingerprints ([bw-r28c-*]) in the OWNED webgpu backend,
visible boots, read the console, fix, revert. All diagnostics reverted before landing
(grep `bw-r28c` across the webgpu backend is empty).

Ground-truth capture note: programmatic `page.screenshot` of the WebGPU OffscreenCanvas
returns BLACK until the workbench viewport has actually presented (needs a ~60s kick-timer
settle, present>=2). A 2D-canvas `drawImage`+`getImageData` pixel probe reads real pixels
once settled — the viewport 3D background samples ~63,63,63; a composited studio-lit cube
would read ~120-150. Center stayed 63 through every fix = cube never composited.

## THE COMPOSITE READS STALE GARBAGE — root cause (Bug A, FIXED patch 0116)

The workbench deferred resolve/composite (`workbench_composite.bsl.hh`) samples
`depth_tx`(sampler 3) / `normal_tx`(4) / `material_tx`(5) and discards `depth == 1.0`.
Tint dense-packs those three samplers to WGSL `@binding(0/1/2)` (dumped live:
`depth_tx_image:@binding(0)`, `normal_tx_image:@binding(1)`, `material_tx_image:@binding(2)`).
`build_interface` (wgpu_shader.cc:679-680) assigns each sampler's frontend location =
its DENSE binding, so the DRW manager binds the gbuffer depth/normal/material at frontend
slots **0/1/2**, NOT their create-info slots 3/4/5.

`append_resource_bind_entries` then bound the WRONG textures for the resolve — proven with
identity fingerprints ([bw-r28c-rs]/[bw-r28c-fb]/[bw-r28c-win]): the gbuffer depth(fmt49)/
normal(fmt21)/material(fmt40) sat at frontend slots 0/1/2 while THREE stale fmt-22 textures
(leftover context-wide binds from an earlier draw) sat at slots 3/4/5, and BOTH sets
remapped onto bindings 0/1/2. Two independent defects in the two-pass assembler let the
stale binds win:

1. **claim-before-kind-check (all buffer/image loops).** `claimed.insert(b)` ran BEFORE
   the resource-kind guard. A stale WRONG-kind bind (a leftover UBO/SSBO/image whose
   frontend slot is, for THIS shader, a *texture* binding at dense 0/1/2) reserved the
   binding and then bailed on `!is_uniform_binding(b)` — but the claim persisted and blocked
   the real texture. Trace proof: pass-1 sampler slots 0/1/2 saw `claimed(n)=1` before the
   sampler loop ran, claimed by the earlier buffer/image loops in the same pass.
2. **sampler create-info-slot remap = stale (sampler loop).** The stale textures at frontend
   slots 3/4/5 are "mapped" for the resolve (its create-info declares samplers there), so
   pass-0 treated them as the real binds and claimed 0/1/2 via the create-info->dense remap,
   while the true dense-slot binds (0/1/2) were mis-classified as fallback.

### FIX (patch 0116) — pure runtime bind change, no shader/codegen touched

`upstream/source/blender/gpu/webgpu/wgpu_context.cc` `append_resource_bind_entries`:
(a) claim a binding ONLY when an entry of the matching kind is actually emitted (moved
`claimed.insert` past the kind + validity checks in the UBO / SSBO / buffer-SSBO / image /
sampler loops); (b) a sampler dense-slot guard — a create-info-slot->dense remap
(`item.first != n`) never displaces a live identity bind that exists at the dense slot n.

VERIFIED live ([bw-r28c-win], instrumented boot): all three resolve bindings now resolve to
the real gbuffer — bind0=gbuffer depth(fmt49), bind1=normal(fmt21), bind2=material(fmt40),
byte-identical to the `Opaque.Gbuffer` attachment ptrs. Zero GPU validation errors.
Census GREEN with 0116 applied: 148 PASS/8 FAIL/2 CRASH + static 956/973, patches_series
attests 0116:applied, m3.json regenerated. Patch applies + reverse-applies clean; lane-a
mirror synced (`sandbox/lane-a-staging/webgpu/wgpu_context.cc`, -p5).

## Bug B (STILL OPEN) — the opaque-group prepass writes NO cube depth into the gbuffer

With the composite now reading the real gbuffer depth, the cube is STILL discarded
(center pixel 63 = viewport background; grid visible through the outline). The composite
reads the correct depth texture (bind0 == `Opaque.Gbuffer` D), so the gbuffer depth must be
1.0 at the cube — i.e. the workbench opaque prepass never wrote the cube's depth. Isolation:

- Prepass pipeline is fine: `workbench_prepass_mesh_opaque_studio_material_no_clip`
  color_count=3, depthWrite=1, LESS_EQUAL, PIPE=OK.
- The prepass DRAW executes: `[bw-r28c-mdi]` shows one `DrawIndexedIndirect` (count=1) into
  `Opaque.Gbuffer`, in the correct order (prepass BEFORE the composite reads depth).
- The shared gbuffer depth IS cleared to 1.0 (`[bw-r28c-seq]`: `#SC4 Clear Main ... D=CLEAR
  cv=1.0`, then `#1 Opaque.Gbuffer D=load`), and nothing re-clears it between the prepass and
  the composite (only color-only `submit_clear`s follow). So the depth 1.0-at-cube is because
  the prepass produced NO cube fragments in the gbuffer, not because it was wiped.
- The **outline** prepass (`overlay_outline_prepass_mesh`, same cube batch, mdi count=1) DOES
  write depth — but to its OWN depth (`outline.prepass_fb` D=0x…510), a DIFFERENT texture
  from the shared workbench/overlay gbuffer depth (0x…ad0). So "the outline works" does NOT
  prove the opaque group draws; it draws into a different target.

Conclusion: the OPAQUE group's GPU-generated `DrawIndexedIndirect` args (instance_count /
index_count for the workbench opaque group) are almost certainly 0, or its per-group
DrawCommand/resource setup is wrong — a DRW GPU-driven command-generation defect, NOT a
webgpu bind-assembly one. NB: the command-generate COMPUTE dispatch shares the same fixed
`append_resource_bind_entries` (wgpu_backend.cc:156), so patch 0116 already covers its bind
group — yet the opaque group still produces nothing, so the defect is upstream of the bind
assembly (the group descriptor / visibility / resource-id chain for the opaque group).

Discriminator caveat (do not repeat): forcing a direct `DrawIndexed` in place of the opaque
mdi is INCONCLUSIVE — the DRW resource-id rides `firstInstance` in the indirect args, so
`firstInstance=0` reads the wrong ObjectMatrices. Any Bug-B probe must read the opaque
group's indirect-buffer contents (blocked by the F9-D windowed readback gap) or instrument
the DRW command-generate compute output.

## Landing checklist (this round)
- [x] Patch 0116 written; applies + reverse-applies clean; series entry + comment added.
- [x] All [bw-r28c-*] instrumentation reverted (grep empty across webgpu backend + batch).
- [x] Native census GREEN with 0116: 148/158 + static 956/973; m3.json regenerated.
- [x] lane-a mirror synced (wgpu_context.cc).
- [ ] Bug B (opaque-group prepass depth) — handed off; DRW GPU-driven command-generation lane.
