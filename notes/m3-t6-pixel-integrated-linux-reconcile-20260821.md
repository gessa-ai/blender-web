<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T6 integrated pixel-buffer Linux reconciliation — 2026-08-21

## Outcome

The existing device-free M3.T6 buffer contract now compiles Blender's canonical in-tree
`wgpu_pixel_buffer.cc` postimage directly in its native and wasm32 graphs. The class's virtual
deleting destructor exposes a real link dependency on `MEM_CXX_CLASS_ALLOC_FUNCS`, so both legs
also compile the canonical five-source guardedalloc closure rather than supplying a test shim.
The direct private-GPU-header dependency is bound to the pinned native and Wasm fmt include roots;
their consumed `fmt/ranges.h` files must be byte-identical before evidence allocation.

The added sixth contract checks seven allocation sizes from zero through 4,096 bytes, exact
`get_size()` results, empty native handles, duplicate-map rejection, mapped-upload rejection,
oversized-upload rejection, stable remapping, and byte preservation for all 4,869 written bytes.
It runs alongside the existing alignment, 32-case usage, invalid-buffer, move-lifetime, and
readback-registry contracts.

Final root and descendant runs are green at `20260821T210258-586223` and
`20260821T210312-586610`. Native and Node emit identical 441-byte evidence
(`sha256:7786a0ecf86b`); the 15 canonical WebGPU/base/allocator inputs have combined identity
`sha256:45d86d809161`, and the identical fmt header is `sha256:ccaf61c9b593`. Both targets finish
at locked-Ninja no-work. Wrong-Dawn and wrong-Node controls reject before evidence allocation at
`20260821T210003-582907/582929`.

Canonical clean-pin replay remains 257 paths at `sha256:e03f140fe3f3`, and the windowed product
remains exact no-work (`20260821T205939-582601/582602`). REUSE 6.2.0 is 1,971/1,971 green
(`20260821T210400-587728`).

## Boundary

The contract creates no WebGPU instance, adapter, device, GPU buffer, texture, queue upload,
pixel evidence, or M3 receipt. It does not replace the historical live buffer/upload proof; a
fresh Linux replay remains owned by `M3-LINUX-REPLAY` after s7 exposes an accepted hardware
adapter. Required M3 and the full regression remain honestly red at `2026-08-21T21:00:36Z` on
the existing strict-manifest, APPLY/artifact, browser, run-label, and hardware boundaries, while
M0 remains 6/6 green. No product, upstream/GPU implementation, receipt, result flag, dependency
record, deferral, tolerance, golden, blacklist, or promise changed.
