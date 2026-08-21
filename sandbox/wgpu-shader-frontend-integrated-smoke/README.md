<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T7 shader-frontend integrated parity

This device-free contract includes the canonical in-tree `wgpu_shader.cc`
translation unit directly and exercises its private GLSL image-type, storage-
format, qualifier, std140 layout, texel-buffer helper, integer-sampler, physical
1D-array, and finite-value builtin rewrite helpers. It also extracts the shipping
`WGPUShader::push_constant_set` method byte-for-byte and executes it in a minimal
device-free class, covering five std140 arrays (19 elements, 148 payload bytes, and
156 padding bytes). Native and Wasm executions must produce byte-identical evidence.
Live-device sections are discarded at link;
the driver creates no WebGPU instance, adapter, device, shader module, pipeline,
or M3 receipt.

The image-type census covers all 39 distinct `ImageType` values in the pinned
create-info API and specifically requires signed atomic 2D arrays to emit the
`iimage2DArray`/`isampler2DArray` spellings. The other contracts cover all 63
texture formats, all eight qualifier bit patterns, and 30 scalar/array std140
layouts.

The packing contract owns scalar, vec2, vec3, vec4, and integer array strides. It
does not claim `float3x3` packing: the 2026-08-21 audit found that separate matrix
column-padding defect and queued it as its own product-fix unit.

The source-rewrite census covers nested texel-buffer helper inlining, all six
integer sampling call families plus controls, every physical 1D-array sampled/image
operation used by the backend, all eight storage-image atomic names, and token-safe
`isnan`/`isinf` helper injection.

Run from any checkout-relative working directory:

```sh
harness/buildwrap.sh bash sandbox/wgpu-shader-frontend-integrated-smoke/build.sh
harness/buildwrap.sh bash sandbox/wgpu-shader-frontend-integrated-smoke/selfcheck.sh
```

Both native and Wasm targets are built only through `scripts/ninja-locked.sh`.
