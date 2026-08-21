<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T1 shader-chain Linux reconciliation — 2026-08-21

## Outcome

The device-free half of M3.T1 is reproducible on ornith-lab. Identical C++ runs
natively and under Wasm through shaderc v2025.4, SPIR-V 1.3, and Dawn/Tint
`36cf1fae`; both emit 498 byte-identical WGSL bytes with
`sha256:2516371cb53290355753ca6dfb71fb0be972d55b64b3f614c3006f20a87a4329`.
The device-validation half remains blocked by the named s7 hardware condition.

## Finding and repair

The retained smoke driver failed immediately on its absolute macOS checkout
(`20260821T181740-431295`). After making the paths portable, the first Linux run
found a genuine native/Wasm difference: the native output lowered the vertex
position's final constant to `0.0f`, while Wasm retained source value `1.0f`
(`20260821T182403-434902`). The Linux precompiled `glslc` identifies its shaderc
as v2023.8; Blender 5.2 and the shipped Wasm closure pin v2025.4. That package is
therefore not a same-toolchain oracle.

The driver now checksum-binds the cached v2025.4 archive, builds its shared
native library through `scripts/ninja-locked.sh`, reuses Dawn's generated Tint
target graph for the native executable, and builds the Wasm executable from the
checked 4-entry shaderc plus 63-entry Tint archive manifests through the same
global lock. It requires emcc 6.0.5 and bundled Node 22.16.0, derives every path
from its own location, rejects a mismatched Dawn checkout before allocating
outputs, treats either stderr stream as failure, and requires exact WGSL bytes.

## Evidence and boundary

- Root run: `20260821T183417-445570`, exact 498-byte parity.
- Descendant-CWD replay: `20260821T183427-445816`, exact parity with all three
  Ninja targets reporting no work.
- Wrong-Dawn negative: `20260821T182916-441028`, rejected with zero allocations.
- Live Dawn control: `20260821T182931-441107`, llvmpipe rejected with
  `PROBE_BLOCKED` before validation.
- Exact REUSE 6.2.0: `20260821T183459-446208`, 1,946/1,946 files licensed.
- Required M3 scope: `20260821T183503-446275`, honestly RED only for the absent
  fresh strict candidate; group-scoped regression `20260821T183507-446340`
  restores M0 6/6 and leaves M1-M8 on their existing receipt/APPLY/hardware gates.

This work changes no product source, shader policy, archive, adapter acceptance,
harness expectation, receipt, result flag, deferral, tolerance, golden, or
milestone promise. A fresh M3 receipt still requires the exact checked GPU suite
on an accepted hardware Vulkan adapter.
