<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Canonical WebGPU fixed-function state parity smoke

This device-free M3.T10 reconciliation compiles Blender's canonical in-tree
`wgpu_state_table` postimage directly for native and wasm32 against the real
`GPU_state.hh` enums. The shared test exhaustively verifies all 16 blend rows,
seven depth modes, all 16 stencil test/operation combinations, three cull modes,
both front-face and provoking-vertex choices, and all 64 write-mask bit patterns.
Native and Wasm stdout must be byte-identical.

Run only through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/wgpu-state-integrated-smoke/build.sh
```

The driver checksum-binds Dawn `36cf1fae`, emcc 6.0.5, Node 22.16.0, Blender's
canonical clean-pin replay, and the five exact state/enum inputs before evidence
allocation. Both targets build only through `scripts/ninja-locked.sh` and finish
with an exact no-work check.

No WebGPU instance, adapter, device, or render pipeline is created. Live
descriptor and pixel validation remain owned by `M3-LINUX-REPLAY` and require an
accepted hardware adapter.
