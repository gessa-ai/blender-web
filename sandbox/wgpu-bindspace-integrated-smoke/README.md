<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Canonical WebGPU bind-space, sampler, and dummy-attribute parity smoke

This device-free M3.T10 reconciliation compiles Blender's canonical in-tree
`wgpu_state_manager.cc` and the real `StateManager` constructor from
`gpu_state.cc` in one native/wasm32 contract. It covers default GPU state, last-
bind-wins texture and image maps, independent texture/image namespaces,
resource-wide and all-bind cleanup, implicit WebGPU state/barrier preservation,
and the reusable signal/wait state of the queue-ordered fence. It also extracts
the shipping sampler-descriptor policy byte-for-byte from `wgpu_context.cc` and
exhausts Blender's 2x/4x/8x/16x mip-gated anisotropy values, the Dawn-required
linear-filter invariant, custom samplers, and all four address modes.
The same contract extracts the shipping dummy-vertex initializer and emulates
its device/queue boundary to prove one 16-byte `(0,0,0,1)` write, one allocation,
and stable handle reuse. The expected bytes are bound to Blender's pinned Vulkan
dummy-buffer policy, including the fourth component required by missing orcos.

Run only through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/wgpu-bindspace-integrated-smoke/build.sh
harness/buildwrap.sh bash sandbox/wgpu-bindspace-integrated-smoke/selfcheck.sh
```

Function/data sections and linker collection retain the real base constructor
while removing unrelated frontend/device paths from `gpu_state.cc`. Native and
Wasm stdout must be byte-identical and stderr must remain empty.

The driver binds Dawn `36cf1fae`, emcc 6.0.5, Node 22.16.0, byte-identical
native/Wasm fmt headers, Blender's canonical clean-pin replay, the exact
extracted sampler and dummy-vertex policies, and all nine direct source/header inputs before
evidence allocation. Both targets build only
through `scripts/ninja-locked.sh` and finish with exact no-work checks. The
self-check requires malformed sampler and dummy-vertex source, wrong Dawn, wrong Node, and
drifted fmt identities to fail before their requested evidence directories are
allocated.

No real WebGPU instance, adapter, device, buffer, sampler, bind group, command, or receipt is
created. Live resource assembly and fence ordering remain owned by
`M3-LINUX-REPLAY` and require an accepted hardware adapter.
