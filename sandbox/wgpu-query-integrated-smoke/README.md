<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Canonical WebGPU conservative-query parity smoke

This device-free M3.T10 reconciliation compiles Blender's canonical in-tree
`wgpu_query` postimage directly for native and wasm32. The shared contract checks
initial state, five valid begin/end transitions, defensive duplicate transitions,
and the exact conservative zero-hit result used while synchronous browser
occlusion queries remain unavailable. Native and Wasm stdout must be
byte-identical.

Run only through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/wgpu-query-integrated-smoke/build.sh
```

The driver checksum-binds Dawn `36cf1fae`, emcc 6.0.5, Node 22.16.0, Blender's
canonical clean-pin replay, and the five exact query/span inputs before evidence
allocation. Both targets build only through `scripts/ninja-locked.sh` and finish
with an exact no-work check.

No WebGPU instance, adapter, device, or query set is created. This contract proves
the fallback honestly; it does not turn that fallback into feature parity. Live
query support remains a named deferral until Blender's synchronous legacy
selection API gains an asynchronous browser-compatible continuation.
