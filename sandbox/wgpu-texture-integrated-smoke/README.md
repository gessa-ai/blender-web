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
canonical/edge RGB9E5 encodes, and invalid/boundary behavior. Native and Wasm
stdout must be byte-identical.

Run only through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/wgpu-texture-integrated-smoke/build.sh
```

The driver checksum-binds Dawn `36cf1fae`, emcc 6.0.5, Node 22.16.0, Blender's
canonical clean-pin replay, and the eight exact table/conversion/texture/enum inputs
before evidence allocation. It also requires the exact RGB9E5 format classification
and two pack/one unpack shipping call sites before allocating evidence. Both targets build only through
`scripts/ninja-locked.sh` and finish with an exact no-work check.

No WebGPU instance, adapter, device, texture, or milestone receipt is created.
Live creation, upload/readback, and framebuffer coverage remain owned by
`M3-LINUX-REPLAY` and require an accepted hardware adapter.
