<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# r52 workbench pixel unlock recovery

Pin: Blender 5.2 `fbe6228777e7`. Recovery checkout HEAD at dispatch: `519f48d`.
Browser verification uses headed bundled Chromium and port 8138.

## WIP audit

The dead lane left three useful categories of state:

- `wgpu_framebuffer.cc` and `wgpu_pipeline.cc` contained a coherent, instrumentation-free
  slot-preserving color-target implementation. It was kept and reconstructed as patch 0130.
- `wgpu_context.cc` had already had its diagnostic logging removed. The sandbox bind dump was
  retained as evidence, but there was no context fix to keep.
- `sandbox/gpu-r52` contained partial scores, a native sparse-target probe, and splash captures.
  These were treated as leads only and rerun against a stable rebuilt tree.

## Target 1: depth-stencil texture on the Uint binding

The inherited premise called this a residual object-id bind collision. The recovered bind dump
instead identified frontend sampler slot 8 remapping to dense binding 4. Direct source tracing
then proved slot 8 is `stencil_tx` in `workbench_composite.bsl.hh`, and Workbench binds
`deferred_ps_stencil_tx`, created by `shadow_depth_stencil_tx.stencil_view()`.

`WGPUTexture::init_internal(..., use_stencil)` records `use_stencil_`, but
`WGPUTexture::sampled_view()` ignores it and forces every combined depth-stencil texture view to
`DepthOnly` plus `Depth32Float`. Dawn correctly rejects that depth view against the shader's Uint
stencil binding. This is a stencil-view aspect defect, not an object-id collision. Patch 0131
honors `use_stencil_` before the generic depth branch, producing a `StencilOnly` plus `Stencil8`
view for either supported combined depth-stencil format.

The native Dawn/Metal probe in `sandbox/gpu-r52/probe/probe_stencil_view.cc` validates all
three sides of the contract:

- StencilOnly Stencil8 view against a Uint sampled-texture binding: OK;
- the old DepthOnly Depth32Float view against Uint: expected validation failure with the
  exact production sample-type mismatch;
- DepthOnly Depth32Float view against a Depth binding: OK, proving the ordinary depth path
  remains valid.

Fresh rebuilt browser receipts:

- `aa-disabled`: GPU errors 3 before to 0 after; render advances from black/validation failure
  to real pixels, with an independent residual pixel delta (7.5% over threshold);
- `light_studio_object`: GPU errors 24 before to 0 after; real pixels, with an independent
  residual pixel delta (4.4% over threshold).

Patch 0131 reverse-checks and round-trips exact inside `upstream/`.

## Target 3: compute storage-image 1-vs-4 undercount

A fresh post-0131 run reproduced 18 GPU errors. Six dispatches each created a bind group with
one entry against a four-entry layout: three RGBA8Unorm storage textures at bindings 0, 1, and
2 plus one UBO at binding 3. Source matching identifies Blender's generic 2D mipmap compute,
which binds `mip_in`, `mip_out1`, and `mip_out2` as per-mip texture views.

The context emitter was not undercounting mapped images. `WGPUTexture::image_view()` returned
null whenever the Blender texture was a view because it checked only the view object's empty
`texture_`; unlike `sampled_view()`, it never resolved `source_`. The UBO was therefore the only
entry that survived.

Patch 0132 resolves the aliased source texture, preserves the texture view's mip and layer
offsets, and gives native 2D, 2D-array, and cube-array storage views explicit layer counts. An
e2D view exposes one layer. An e2DArray view exposes exactly the requested subset length rather
than all remaining source layers; base cube types use their stored face count when lowered to
e2DArray.

The native Dawn probe in `sandbox/gpu-r52/probe/probe_storage_view_subset.cc` creates a four-layer
source and a non-final one-layer view at layer 2. The view and bind group validate, a dispatch
writes source layer 2 red, and an attempted out-of-view write leaves layer 3 untouched. Fresh
rebuilt browser result for `light_studio_material`:

- GPU errors: 18 before to 0 after;
- sentinel: `OK BLENDER_WORKBENCH`;
- mean error: 0.000785399;
- over threshold 0.016: 40 pixels (0.244%);
- verdict: PASS.

Two adjacent limitations are deliberately not claimed fixed. `GPU_TEXTURE_1D_ARRAY` has a
pre-existing inconsistent mapping between its height-emulated 2D allocation/interface and
`to_wgpu_view_dimension()` returning e2DArray. Also, aliased source resolution remains one hop,
so nested texture views are not covered. Neither path is exercised by the pinned mipmap compute.

Patch 0132 reverse-checks and round-trips exact inside `upstream/`.

## Target 2: NONE-gap color attachment compaction

Workbench TransparentDepthPass can bind `object_id` (R16Uint) at color slot 2 with slots 0 and 1
empty. The old backend compacted attachments, placing R16Uint at pipeline target 0 against the
fragment shader's float location 0 output. Dawn rejected pipeline creation.

The native Dawn/Metal probe in `sandbox/gpu-r52/probe/probe_sparse_targets.cc` directly tested
the compatibility matrix:

- fragment outputs at locations 0 float, 1 float, 2 uint with targets null, null, R16Uint: OK;
- fragment output only at location 2 uint with the same targets: OK;
- compacted R16Uint at target 0: FAIL with the production base-type mismatch;
- a real render pass with null, null, R16Uint attachments plus a draw: OK.

Therefore sparse null targets are supported and no fragment variant is required. Patch 0130
preserves attachment slots in both framebuffer format discovery and render-pass descriptors,
and emits `Undefined` pipeline gaps with no blend and a zero write mask.

Targeted rebuilt browser result, `x-ray.blend`, 128x128 F12 bridge:

- sentinel: `OK BLENDER_WORKBENCH`;
- GPU errors: 0;
- mean error: 0.000298314;
- max error: 0.0078431368;
- over threshold 0.016: 0 pixels;
- verdict: PASS.

Patch discipline: patch 0130 reverse-checks inside `upstream/`; reverse then forward application
restores exact SHA-256 hashes for both owned source files.

## Target 4: splash TRI_FAN wedge

The fresh post-0124 splash recapture still showed the black diagonal wedge. The remaining cause
was topology lowering: WebGPU has no triangle-fan primitive, but the backend silently lowered
`GPU_PRIM_TRI_FAN` to `TriangleStrip`. For four vertices, the requested fan triangles are
`(0,1,2)` and `(0,2,3)`, while a strip produces `(0,1,2)` and `(2,1,3)`.

Patch 0134 preserves vertex identity and implements the retained fan paths explicitly:

- immediate-mode fans use a transient UInt32 index list and a TriangleList draw;
- direct non-indexed batches use the same exact fan order with absolute vertex indices;
- direct indexed batches run a cached single-invocation compute expander over the existing
  Index|Storage IBO, including packed U16/U32 indices, subranges, restart-separated fans, shared
  or already-uploaded buffers, and GPU-built buffers;
- indexed expansion emits isolated UInt32 TriangleStrip groups `(a,b,c,restart)`, with an exact
  restart-only tail. This avoids extra vertex invocations while retaining instance parameters;
- multi-viewport direct draws use the same expanded buffers;
- indirect triangle fans remain explicitly rejected, matching Metal. The pin has no production
  literal indirect-fan caller, so this is documented without claiming universal fan support.

The pipeline key now includes the strip index format. Fan-emulation strips select UInt32, while
ordinary strips retain Undefined. Range, source-byte, UInt32, and allocation overflow checks keep
draw ranges inside the logical index buffer and safe on wasm32. The old silent fan-to-strip
fallback is now an assertion-only unreachable guard.

Native Dawn/Metal probes cover both implementations:

- `probe_triangle_fan_expand.cc`: exact CPU order, original 20-byte vertex stride, valid
  TriangleList pipeline/draw, and 144 expected red pixels;
- `probe_indexed_fan_compute.cc`: production-shaped compute expansion plus a real
  TriangleStrip pipeline with `stripIndexFormat=Uint32` and full-capacity DrawIndexed. Packed U16
  and U32 restart/subrange cases each produce exactly three visible triangles with no validation
  errors.

The final headed-browser splash capture is wedge-free. Against the native golden it passes with
max error 0.6588236094 and 1,882 pixels (0.204%) over 0.016. The final workspace capture passes
with max error 0.8823530078 and 3,373 pixels (0.366%) over 0.016. The white cursor spike cluster in
that workspace capture is also present in the pre-0134 historical capture
`sandbox/i18n-r45/captures/r47-workspace_1280x720.png`; it is a separate pre-existing D-9 overlay
defect, not an 0134 regression or a claimed fix.

Patch 0134 reverse-checks inside `upstream/`. A reverse then forward application restores exact
SHA-256 hashes for all four owned source files.

## Full 20-scene rescore

The post-0132 final workbench binary produced the following raw matrix. Patch 0134 changes UI
immediate/batch fan drawing, not these F12 workbench scene pipelines.

| Test | Verdict | GPU errors | Mean error | Pixels over 0.016 |
|---|---:|---:|---:|---:|
| aa-disabled | FAIL | 0 | 0.00868518 | 1,228 (7.5%) |
| aa-single-pass | FAIL | 0 | 0.0104327 | 1,558 (9.51%) |
| dof | FAIL | 96 | 0.0208645 | 5,183 (31.6%) |
| in_front | FAIL | 0 | 0.00579467 | 1,410 (8.61%) |
| in_front_dof | FAIL | 96 | 0.0237566 | 6,167 (37.6%) |
| light_flat_attribute | PASS | 0 | 0.000227625 | 0 |
| light_flat_custom | FAIL | 0 | 0.0089839 | 1,392 (8.5%) |
| light_flat_random | FAIL | 0 | 0.00419108 | 750 (4.58%) |
| light_matcap | RENDER-CRASH | 0 | - | boot timeout |
| light_matcap_no_specular | RENDER-CRASH | 0 | - | boot timeout |
| light_studio_material | PASS | 0 | 0.000785399 | 40 (0.244%) |
| light_studio_object | FAIL | 0 | 0.00359716 | 721 (4.4%) |
| light_studio_object_no_specular | RENDER-CRASH | 0 | - | boot timeout |
| x-ray | PASS | 0 | 0.000298155 | 0 |
| x-ray_0 | PASS | 0 | 0.000127895 | 0 |
| x-ray_1 | FAIL | 0 | 0.00309739 | 655 (4%) |
| x-ray_back_cull | RENDER-CRASH | 0 | - | boot timeout |
| x-ray_in_front | PASS | 0 | 0.000281001 | 0 |
| acescg_blackbody | FAIL | 0 | 0.0192027 | 8,033 (49%) |
| rec2020_lights | FAIL | 0 | 0.107421 | 16,384 (100%) |

Raw count: 5 PASS, 11 FAIL, and 4 boot-timeout RENDER-CRASH. Each timeout was retried exactly
once without source or rig changes. `light_matcap` and `light_matcap_no_specular` then passed with
zero GPU errors. `light_studio_object_no_specular` and `x-ray_back_cull` timed out again and were
not retried further. Effective count: 7 PASS, 11 FAIL, and 2 unresolved load flakes.

The two 96-error DoF families predate patches 0130 through 0134. The identical mipLevelCount(3),
same-pass writable plus TextureBinding, and both Depth32FloatStencil8 expected-Float signatures
are recorded in
`sandbox/gpu-r46/caps/workbench_workbench_in_front_dof/gpuerrors.uniq.txt`. They remain queued for
the later M6 round rather than expanding this lane.

## Final build and census

- locked wasm rebuild: PASS;
- headed splash and workspace captures: PASS, with the comparator values above;
- locked native rebuild: PASS;
- M3 census: 149 PASS, 7 FAIL, 2 CRASH out of 158;
- static shader census: 956 PASS out of 973;
- the only M3 RED is the known I10 un-defer candidate.

Residual scope is therefore eleven pixel-delta scenes, the two pre-existing DoF validation
families, two twice-timed-out browser loads, the pre-existing cursor overlay defect, and the
documented 1D-array/nested-view and indirect-fan limitations. No foreign dirty files, ledger
results, dashboard, patch series, progress log, harness, or golden files are part of this lane's
commits.
