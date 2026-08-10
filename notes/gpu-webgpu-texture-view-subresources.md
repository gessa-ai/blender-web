# WebGPU texture-view subresources (0143)

## Outcome

Patch 0143 makes WebGPU texture views carry an owned, flattened subresource range instead of
depending on a live source wrapper and root-relative mip/layer coordinates. It also replaces the
old row-packed 1D-array emulation with a physical WebGPU 2D-array texture, and updates the shader
ABI accordingly. The final patch contains 13 source/test paths, 3241 insertions, and 522 deletions.

This is the required texture-view dependency for the frozen EEVEE Phase A-prime patch 0144. It
does not apply 0144 and does not claim that EEVEE renders final pixels yet.

## Production behavior

- A canonical `SubresourceRange` pins the backing `wgpu::Texture`, stores backing and view
  formats/aspect, flattens nested base mip/layer offsets, and narrows exact mip/layer counts.
- View wrapper geometry is rebased to its selected mip. A failed backend view initialization now
  deletes the wrapper and returns null through the generic GPU API.
- Framebuffer attachments, clears, load/store passes, raw copies, typed render blits, 3D depth
  slices, sampled views, storage views, and readback resolve the exact selected subresource.
- Plain and array depth paths preserve the untouched depth/stencil sibling. Full selected depth
  copies use a depth-render route where WebGPU forbids depth buffer-to-texture copies. Selected
  stencil copies use the legal GPU buffer bridge.
- Cross-format color blits have typed float, signed, and unsigned variants and preserve cropped
  texel coordinates. Texture destinations use top-left source mapping. The persistent window
  backbuffer keeps the existing direct source Y plus bottom-origin destination conversion, so the
  region-offscreen compositor remains upright.
- A logical 1D array is stored as WebGPU `e2D`, extent `width x 1 x layers`. Upload, readback,
  clear, mip generation, sampling, integer fetch, size queries, storage image coordinates, and
  nested views all preserve the layer axis at every mip.
- Linear/sRGB compatible view formats are declared at allocation. Direct texture clear follows
  backing-format conversion; framebuffer clear follows selected-view conversion. Direct clear
  affects only relative mip zero, matching the public API.
- `RG11B10UfloatRenderable` and `Depth32FloatStencil8` are requested only when the adapter
  advertises them. RG11 read/sample/upload remains legal without renderability; an explicitly
  requested unsupported RG11 attachment fails allocation cleanly.

## Verification

### Patch and builds

- Final patch SHA-256:
  `01a03d36cdd7ea412cc48b2ee5b45ce69b0b7ed25454facc923f62ac80f2e17b`.
- Strict reverse check, isolated forward/reverse byte round trip, whitespace check, 13-path fence,
  and added-line U+2014 scan pass.
- Locked native production build passes.
- Locked `build-wasm-windowed-opt` shipping build passes. Shipping hashes are:
  JS `e849c706c7dde4ed85427c8f68f59e58e515a04243d19a9cdb09f6525fa35519`,
  wasm `b7a3e261e76939f0a9fa05c2518556756bc580ca00ac4d064fc436d99982edb1`,
  data `5aa7c461a5a05aa5f0354754bbd7de7124819334ee336c3bc0f40a1efb7741b1`.

### Backend behavior

- Fifteen new WebGPU tests pass. They cover physical 1D arrays, float/int/uint sampling and
  storage, nested source-free lifetime, geometry, rejected aliases, sRGB clear, RG11 optional
  capability, exact mip/layer clear, depth/stencil clear/load/store/blits, 3D attachment slices,
  typed integer render blit, and cropped extent.
- A standalone actual-Dawn Metal probe deliberately creates a device without RG11 renderability.
  Raw RG11 succeeds and RG11 plus RenderAttachment produces exactly one expected scoped
  validation. Eight D16/D24/D24S8/D32/D32S8 depth routes at mip 1, layer 1 pass; the three
  combined destinations preserve stencil; unexpected validation count is zero.
- The temporary Metal GTest oracle translation unit compiled, but the existing `GPUMetalTest`
  fixture exits 139 during fixture setup before any test body. An unrelated baseline Metal test
  follows the same failure seam. The temporary hunk was reversed exactly; the retained log is a
  harness-block receipt, not a behavioral pass.
- Final census is 164 PASS, 7 FAIL, 2 CRASH of 173 WebGPU tests, with static shaders 956/973 and
  the I10 control passing. Relative to the pre-0143 149/7/2 of 158 baseline, all 15 added tests
  pass and the non-pass set is unchanged.

### Browser behavior

- The exact shipping directory was served from `build-wasm-windowed-opt/bin`; the stale
  `build-wasm/bin` captures were discarded as rig negatives.
- Workbench `light_flat_attribute` returns `OK BLENDER_WORKBENCH`, two completed device captures,
  zero GPU errors, and a pixel pass: mean error 0.000227625, max error 0.003921628, zero pixels over
  0.016.
- Packed UDIM runs with the official Workbench test setup (`STUDIO`, `TEXTURE`). It returns one
  completed RGBA16F device capture and zero GPU errors. The repository scene uses Filmic, so the
  generic raw-byte scorer is not its PNG oracle. A native Metal 4.5.3 control first matches the
  repository Filmic golden within threshold (mean 0.00197993, max 0.01176471, zero pixels over
  0.016). With both sides evaluated under neutral Standard/sRGB, WebGPU device bytes match native
  Metal at mean 0.00116190, max 0.00784314, and zero pixels over 0.016. The retained 1280x720
  screenshot is upright and the packed UDIM image/tile mapping is visible.
- The production `write_still` PNG is still constant black. That is the already documented
  synchronous caller-facing readback continuation boundary, not a texture-view pixel failure;
  the device-byte capture above is complete and nonblack.
- EEVEE `principled_bsdf_default` returns `OK BLENDER_EEVEE`, zero GPU validation errors, and no
  texture-view/attachment error family. It stops before Film readback at the known Phase B
  `eevee_shadow_tag_update` vertex read-write storage declaration and the known
  `MADefault_Surface_shadow_mesh` `OpImageTexelPointer` failure. No EEVEE pixel pass is claimed.

## Binding follow-ups

- 0144 remains the frozen EEVEE RG11 storage promotion and one-output mip-dispatch patch. Rebase
  its disjoint `wgpu_shader.cc` hunks after 0143, then run its recorded EEVEE gates.
- 0145 remains mandatory for incompatible same-byte texture aliases and shared-backing readback
  cache coherence. 0143 intentionally rejects those logical aliases rather than pretending that
  Dawn supports them.
- 0147 remains mandatory for plain-1D sRGB clear, plain-1D/3D mip generation, partial/offset and
  combined-aspect cross-format depth/stencil fallbacks, RG11 render-target emulation when the
  optional feature is absent, exact 1D-array `textureQueryLod` lowering with sampler LOD state,
  and native guarded `Float32Filterable` feature parity. Negative internal blit offsets remain a
  safe no-op because the pin has no common Metal/Vulkan contract and no public caller uses them.
