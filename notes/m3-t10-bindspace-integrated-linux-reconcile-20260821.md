<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T10 state-manager bind-space Linux reconciliation

Outcome: Blender's canonical WebGPU state-manager bind spaces and reusable
queue-ordered fence now have a device-free native/wasm32 parity contract. The
contract compiles the shipping `wgpu_state_manager.cc` and retains the real base
`StateManager` constructor from `gpu_state.cc`; it copies no product logic and
creates no WebGPU instance, adapter, device, bind group, or command.

## Contract

Four independently checked families cover:

- every default immutable/mutable GPU state field used by the backend plus all
  eight invalid default image formats;
- last-bind-wins texture/sampler state, independent slots, resource-wide alias
  removal, all-bind cleanup, and independence from the image namespace;
- the equivalent image bind/replace/unbind/all-clear lifecycle; and
- preservation across WebGPU's implicit state/barrier calls plus fence
  wait-before-signal, repeated signal, consuming wait, and repeated wait.

Native and Node 22.16.0 stdout are byte-identical: 300 bytes,
SHA-256 `2112ce5e5dcc6a17997531f9e9259e949a2affe7aa2f665ee54054fbe180654d`.
The seven direct shipping inputs hash to
`bb7dc946fca9a22653f391dcd7f2b5a0aeda9371c875e86f0082ad569e572587`;
native and Wasm fmt headers are byte-identical at
`ccaf61c9b5937e0fa97737fb047121c5fca9db34de516b8edfc1d913583e3c8e`.

## Evidence and fail-closed controls

- Root parity run: `ledger/buildlogs/20260821T230719-706424.log` — native and
  wasm32 builds green, exact output parity, both locked-Ninja targets end no-work.
- Identity self-check: `ledger/buildlogs/20260821T230729-706422.log` — wrong Dawn,
  wrong Node, and drifted fmt each reject before its requested evidence path is
  allocated.
- Canonical source replay is required before evidence allocation. The driver
  additionally binds Dawn `36cf1fae`, emcc 6.0.5, Node 22.16.0, CMake 4.0.3, the
  host CPython XML modules, and the exact native/Wasm fmt header.

The initial compile reproduced the documented private-GPU-header fmt dependency;
the final target follows `notes/porting-patterns.md` Class 10 and binds the real
headers rather than stubbing the dependency. Section collection retains the base
constructor while discarding unrelated frontend/device functions from
`gpu_state.cc`, following Class 11.

This is CPU state and binding-lifecycle evidence only. Live bind-group resource
assembly, queue ordering, the strict M3 receipt, and every adapter/device claim
remain owned by `M3-LINUX-REPLAY`, which is still blocked by s7's software-only
llvmpipe adapter.
