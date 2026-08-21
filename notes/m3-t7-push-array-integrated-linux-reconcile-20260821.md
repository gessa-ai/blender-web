<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T7 push-array integrated Linux reconciliation — 2026-08-21

## Outcome

The real `WGPUShader::push_constant_set` implementation now has a device-free native/wasm32
contract for its std140 array-stride path. The driver extracts the canonical method body
byte-for-byte, changes only its class qualifier, and compiles it against the exact state the method
uses. This avoids both a copied test implementation and fake symbols for the live-device shader
vtable.

Five arrays cover float, vec2, vec3, vec4, and int payloads: 19 elements in a 304-byte block,
with every one of 148 payload bytes and 156 padding bytes asserted. Native and Node 22.16.0 emit
the same 669 bytes at SHA-256 `4a341f4bfdcc`; the extracted method is SHA-256
`cb6ec1291c1f`. The build also binds the canonical clean-pin replay, Dawn/Tint `36cf1fae`, emcc
6.0.5, byte-identical native/Wasm fmt input, and exact locked-Ninja no-work.

## Experiment and fail-closed boundary

The first experiment stack-constructed `WGPUShader`. That retained its full virtual table and
correctly exposed unrelated device/compiler link edges (`20260821T233223-728946`); no stubs were
added. The final extractor requires one exact method boundary and three structural invariants.
Its adversarial self-check removes the std140 stride expression and proves rejection before any
generated output is allocated.

Evidence:

- final parity build: `ledger/buildlogs/20260821T234223-739387.log`;
- extractor/identity self-check: `ledger/buildlogs/20260821T234049-736578.log`;
- canonical replay and exact windowed no-work:
  `ledger/buildlogs/20260821T233918-734657.log` and
  `ledger/buildlogs/20260821T233918-734662.log`;
- REUSE 6.2.0, 2,006/2,006:
  `ledger/buildlogs/20260821T233918-734658.log`;
- recurring vtable-retention pattern: `notes/porting-patterns.md`, Class 13.

## Newly exposed next item

This contract deliberately does not claim matrix packing. The canonical WebGPU method enters its
strided path only when `array_size > 1`; a normal `GPU_shader_uniform_mat3` call supplies
`comp_len=9, array_size=1`, so it falls through to a tight 36-byte copy even though
`std140_align_size(Type::float3x3_t)` reserves 48 bytes. Correct std140 layout needs padding after
each three-float column, exactly as the pinned Vulkan implementation does at
`source/blender/gpu/vulkan/vk_push_constants.hh:242-251`.

Four pinned create-infos consume this path: simple-lighting `NormalMatrix`, the scene-linear color
transform, and two sequencer scope matrices. `M3.T7.mat3-packing` is therefore an unblocked product
fix, not a deferral or a covered pass.

No product/upstream source, canonical patch, adapter, device, GPU buffer, receipt, result flag,
deferral, tolerance, golden, blacklist, or promise changed.

Required M3 remains red for the absent fresh strict candidate. The final container-backed
regression at 2026-08-21T23:41Z restores M0 to 6/6 green and leaves M1–M8 red on the existing
strict-receipt, APPLY/artifact, browser/run-label, and s7 hardware boundaries.
