<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# EEVEE transmission display-alias correction

Date: 2026-08-09

This is an append-only correction to the M6 attribution for
`eevee_principled_bsdf_principled_bsdf_transmission`. It does not change the
existing matrix, comparator, oracle, threshold, or result files.

## Controlled browser result

Both runs used the same startup blend, `BLENDER_EEVEE`, 128 by 128 render,
shipping windowed wasm artifact, headed bundled Chromium, and isolated port
8147. The B run changed only the active `IMAGE_EDITOR` area to `VIEW_3D` in
memory before rendering.

| run | UI area | sentinel | GPU errors | hook kicks/dones | captures |
|---|---|---:|---:|---:|---:|
| A | saved `IMAGE_EDITOR`, `Render Result` | `OK BLENDER_EEVEE` | 2 | 0/0 | 0 |
| B | in-memory `VIEW_3D` | `OK BLENDER_EEVEE` | 0 | 0/0 | 0 |

Run A reports the RGBA16Float writable-storage alias between bindings 2 and 3,
both selecting mip 7 of the same 128 by 128 texture. The chronology control
records `M6_BRIDGE_DONE` at `21:20:12.484`, followed by the two validation
errors at `21:20:12.633` and `21:20:12.634`.

Therefore this validation error is post-render Image Editor display work. It
does not block the EEVEE render operator and it does not explain the missing
Film readback hook: both A and B return the render sentinel with zero hook
kicks, zero hook completions, and zero captures.

## Source attribution

The Image Editor display path asks for a viewer texture in
`source/blender/draw/engines/image/image_instance.hh:102-106`.
`source/blender/blenkernel/intern/image_gpu.cc:481-500` creates the single image
texture and updates its mip chain.

The generic mip generator creates one view per mip at
`source/blender/gpu/intern/gpu_texture_mipmap.cc:77-85`. For an eight-mip
texture, its final iteration starts at mip 6 and
`source/blender/gpu/intern/gpu_texture_mipmap.cc:89-96` binds mip 7 to both
output slots because the second output index is clamped to the last view while
`num_levels` is one. The shader suppresses the second write only after binding:
`source/blender/gpu/shaders/gpu_shader_2D_update_mipmaps.bsl.hh:163-173` declares
both writable outputs, while lines 599-617 branch on `num_levels` inside the
dispatch. WebGPU validates the two writable bindings before shader control flow
can suppress the second write.

The WebGPU view backend preserves the requested source and mip offset at
`source/blender/gpu/webgpu/wgpu_texture.cc:725-742`, creates an exact single-mip
storage view at lines 984-1025, and emits that view into the bind group at
`source/blender/gpu/webgpu/wgpu_context.cc:666-691`. The duplicate mip-7 request
is therefore a generic frontend mip-dispatch bug, not backend view identity or
EEVEE pass sequencing.

## Evidence

- As-is A: `sandbox/gpu-r35/caps/phaseaprime_alias_a_image_editor.log` and
  `sandbox/gpu-r35/caps/phaseaprime_alias_a_image_editor/`
- In-memory B: `sandbox/gpu-r35/caps/phaseaprime_alias_b_view3d.log` and
  `sandbox/gpu-r35/caps/phaseaprime_alias_b_view3d/`
- Timestamp control: `sandbox/gpu-r35/caps/phaseaprime_alias_a_chronology.log`
  and `sandbox/gpu-r35/caps/phaseaprime_alias_a_chronology/`
- Hash receipt: `sandbox/gpu-r35/caps/phaseaprime-alias-correction-hashes.md`

All three screenshots were opened and inspected. Each PNG has a CC0 license
sidecar.
