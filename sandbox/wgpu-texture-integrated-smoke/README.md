<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Canonical WebGPU texture parity smoke

This device-free M3.T9 reconciliation compiles Blender's canonical in-tree
`wgpu_texture_format` and `wgpu_data_conversion` postimages directly for native
and wasm32. The shared test verifies the complete 63-format census, capability
classification, the five legal linear/sRGB view pairs, all 13 RGB-to-RGBA
promotion plans and byte transforms, three Dawn RGB9E5 decode vectors, seven
canonical/edge RGB9E5 encodes, 25 RG11B10 vectors against the pinned Vulkan
F32/F11/F10 policy, the 16-case feature-aware render-attachment matrix (including
Grease Pencil's `UNORM_16` render mask), 26 exact texture dimension/array/mip limit
decisions, 14 checked uncompressed-upload layouts, 13 physical copy-region boundaries,
six non-renderable clear layouts covering exact byte geometry and overflow rejection,
18 framebuffer-clear policy decisions covering whole-attachment load operations, clipped draws,
empty no-ops, bottom-to-top coordinate conversion, color/depth/stencil aspects, integer edges,
and three-layer exhaustion. The driver also requires both scissored-clear pipeline caches to
validate a newly created handle before publishing it, so a transient failure remains retryable.
It checksum-binds the WebGPU GPU-test regression that combines an explicit green load clear,
a normal red draw through a zero viewport, and framebuffer readback of the unchanged green result.
Four real format-flag cases distinguish normalized RGB10A2 and RGBA8
from unsigned RGB10A2 and signed RGBA8 before pinned-Tint parsing of the exact float, uint, sint,
and depth fullscreen-clear WGSL variants,
eleven native-parity 1/2/3-tap mipmap axis plans (including the odd 5-to-2 edge kernel),
plus a pinned-Tint parse of the exact float/normalized WGSL consumed by `WGPUTexture` and an
exact-method nine-case resource transaction that rejects every fallible mipmap handle before
dependent work or queue submission,
15 checked readback layouts covering padded staging, host-size, and device-limit boundaries,
six strided-upload host-texel cases that
separate packed 32-bit rows from scalar-component rows, seven BC1/2/3 physical-block and
source-stride layouts, all nine compressed texture-type enumerators, all ten documented
`rgba`/`xyzw`/`01` component-swizzle symbols, and invalid/boundary behavior. Native and Wasm
stdout must be byte-identical.

Run only through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/wgpu-texture-integrated-smoke/build.sh
```

The driver checksum-binds Dawn `36cf1fae`, emcc 6.0.5, Node 22.16.0, Blender's
canonical clean-pin replay, and the 25 exact table/conversion/texture/enum/assert/oracle
inputs before evidence allocation. It also requires the exact RGB9E5 format classification;
the exact RGB9E5, RG11B10, and Blender DDS compressed-upload call-site censuses; the sampled-view
swizzle descriptor and native adapter-guarded feature request; three launch-tier Blender swizzle
consumer families; and the browser's all-supported-features device request before allocating
evidence. Both targets
build only through `scripts/ninja-locked.sh` and finish with an exact no-work check.

No WebGPU instance, adapter, device, texture, render pass, draw, sampled pixel, or milestone
receipt is created. Live component-swizzle sampling, compressed sampling/readback, and
framebuffer coverage remain owned by `M3-LINUX-REPLAY` and require an accepted hardware adapter.
