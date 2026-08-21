<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Canonical WebGPU state-manager bind-space parity smoke

This device-free M3.T10 reconciliation compiles Blender's canonical in-tree
`wgpu_state_manager.cc` and the real `StateManager` constructor from
`gpu_state.cc` in one native/wasm32 contract. It covers default GPU state, last-
bind-wins texture and image maps, independent texture/image namespaces,
resource-wide and all-bind cleanup, implicit WebGPU state/barrier preservation,
and the reusable signal/wait state of the queue-ordered fence.

Run only through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/wgpu-bindspace-integrated-smoke/build.sh
harness/buildwrap.sh bash sandbox/wgpu-bindspace-integrated-smoke/selfcheck.sh
```

Function/data sections and linker collection retain the real base constructor
while removing unrelated frontend/device paths from `gpu_state.cc`. Native and
Wasm stdout must be byte-identical and stderr must remain empty.

The driver binds Dawn `36cf1fae`, emcc 6.0.5, Node 22.16.0, byte-identical
native/Wasm fmt headers, Blender's canonical clean-pin replay, and all seven
direct source/header inputs before evidence allocation. Both targets build only
through `scripts/ninja-locked.sh` and finish with exact no-work checks. The
self-check requires wrong Dawn, wrong Node, and drifted fmt identities to fail
before their requested evidence directories are allocated.

No WebGPU instance, adapter, device, bind group, command, or receipt is created.
Live resource assembly and fence ordering remain owned by `M3-LINUX-REPLAY` and
require an accepted hardware adapter.
