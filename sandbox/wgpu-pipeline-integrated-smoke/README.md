<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Canonical WebGPU render-pipeline mapping parity smoke

This device-free M3.T10 reconciliation compiles Blender's canonical in-tree
`wgpu_pipeline` postimage directly for native and wasm32 against Blender's real
primitive, index-format, component, and fetch enums. The shared test covers all
11 primitive rows, all 33 primitive/index-format combinations, and all 96
combinations of eight vertex component types, four valid component lengths, and
three fetch modes. The strip contract requires `Uint16`/`Uint32` only for indexed
line-strip, line-loop, and triangle-strip pipelines and keeps every non-strip
topology at `Undefined`, matching pinned Dawn validation. This also includes the
resolved normalized signed-I10 mapping to `Snorm8x4`.

Run only through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/wgpu-pipeline-integrated-smoke/build.sh
```

The triangle-fan row deliberately exercises the backend's fail-visible fallback:
both executions must emit the exact canonical `BLI_assert_unreachable` diagnostic
before returning `TriangleList`. Native and Wasm stdout and stderr must be
byte-identical.

The driver checksum-binds Dawn `36cf1fae`, emcc 6.0.5, Node 22.16.0, matching
native/Wasm fmt headers, Blender's canonical clean-pin replay, and the 13 direct
pipeline/batch/enum/assert inputs before evidence allocation. It also requires
both shipping direct and indirect batch paths to call the tested strip-format
mapping. Both targets build only through `scripts/ninja-locked.sh` and finish
with exact no-work checks.

No WebGPU instance, adapter, device, render pipeline, or pixel evidence is
created. Live descriptor and pixel validation remain owned by
`M3-LINUX-REPLAY` and require an accepted hardware adapter.
