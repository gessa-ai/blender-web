<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T10 integrated state-table Linux reconciliation — 2026-08-21

## Outcome

The canonical in-tree WebGPU fixed-function state table now has a checkout-relative,
device-free native/Wasm parity contract. The native leg reuses pinned Dawn's target graph; the
Wasm leg uses emdawnwebgpu's matching C/C++ value types. Both compile the shipping
`wgpu_state_table.cc` directly against Blender's real `GPU_state.hh` enums instead of substituting
the earlier standalone T10.pre enum mirror. Before allocating evidence, the driver requires a
clean Dawn `36cf1fae` checkout, canonical clean-pin replay, host CMake 4.0.3, emcc 6.0.5, and Node
22.16.0.

Four contracts cover the complete pure mapping surface:

- all 16 blend rows, including exact names, enabled state, color/alpha operations and factors,
  the one dual-source row, lookup identity, and invalid-value fallback;
- all seven depth modes plus the disabled/always invalid-value fallback;
- every one of the 16 stencil test/operation combinations, including independent front/back
  increment/decrement-wrap semantics for both shadow-volume counting modes;
- all three cull modes, both winding choices, both provoking-vertex choices, and all 64 write-mask
  bit patterns, proving that depth/stencil bits do not leak into the color mask.

Final root and descendant runs are green at `20260821T204349-566138` and
`20260821T204443-568565`. Native and Node emit identical 372-byte evidence
(`sha256:d3ce05b6a3bf`); the five canonical state/enum inputs have combined identity
`sha256:d16559be8c23`. Both targets finish at locked-Ninja no-work. Wrong-Dawn and wrong-Node
controls reject before evidence allocation (`20260821T204514-569086/569088`). Canonical replay
remains 257 paths at `sha256:e03f140fe3f3`; the existing windowed product is exact no-work
(`20260821T204244-565684`), and final REUSE 6.2.0 is 1,970/1,970 green
(`20260821T204553-569437`).

## Boundary

The contract creates no WebGPU instance, adapter, device, render pipeline, draw, pixel evidence,
or M3 receipt. It does not replace the historical live Dawn/Metal T10 proof, and a fresh Linux
live replay remains owned by `M3-LINUX-REPLAY` after s7 exposes an accepted hardware adapter.
Required M3 remains red for the absent strict candidate. Group-scoped container regression at
`2026-08-21T20:44:28Z` keeps M0 6/6 green and M1–M8 honestly red on their existing strict-
manifest, APPLY/artifact, browser, run-label, and hardware boundaries. No product,
upstream/GPU implementation, receipt, result flag, dependency record, deferral, tolerance,
golden, blacklist, or promise changed.
