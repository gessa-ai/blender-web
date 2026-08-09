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
offsets, and restricts a plain e2D storage view to one array layer. Fresh rebuilt browser result
for `light_studio_material`:

- GPU errors: 18 before to 0 after;
- sentinel: `OK BLENDER_WORKBENCH`;
- mean error: 0.000785399;
- over threshold 0.016: 40 pixels (0.244%);
- verdict: PASS.

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

## Remaining verification

The final rebuilt tree will be used for the full 20-scene rescore, splash recapture, and native
census.
