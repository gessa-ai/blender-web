<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Canonical WebGPU vertex-buffer CPU parity smoke

This device-free M3.T6 reconciliation includes Blender's canonical in-tree
`wgpu_vertex_buffer.cc` postimage directly in one shared native/wasm32 test. It
covers all 1,024 signed 10-bit component encodings, signed-I10 detection across
all 16 vertex-attribute slots, 1,024 interleaved vertices, two deinterleaved
signed-normal blocks, truncated-input safety, signed-I10 subrange updates, and
all four usage modes with and without the buffer-texture flag. The subrange
contract compares 21 converted fields with the full-upload result, rejects four
partial/overflowing ranges atomically, and proves a one-field update remains
bounded even when the declared vertex census is `UINT32_MAX`.

Run only through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/wgpu-vertex-integrated-smoke/build.sh
harness/buildwrap.sh bash sandbox/wgpu-vertex-integrated-smoke/selfcheck.sh
```

The test deliberately reaches private CPU helpers through the canonical
translation unit instead of copying them. Function/data sections and linker
collection remove the uncalled context and device paths. Native and Wasm stdout
must be byte-identical and stderr must remain empty.

The driver checksum-binds Dawn `36cf1fae`, emcc 6.0.5, Node 22.16.0, matching
native/Wasm fmt headers, Blender's canonical clean-pin replay, and the 13 direct
vertex/enum/assert inputs before evidence allocation. Both targets build only
through `scripts/ninja-locked.sh` and finish with exact no-work checks.
The self-check requires both a wrong Dawn checkout and a wrong Node identity to
fail before their requested evidence directories are allocated.

No WebGPU instance, adapter, device, buffer, upload, or receipt is created. Live
vertex-buffer allocation and draw validation remain owned by
`M3-LINUX-REPLAY` and require an accepted hardware adapter.
