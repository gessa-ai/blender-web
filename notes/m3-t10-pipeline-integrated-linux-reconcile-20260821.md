<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T10 integrated render-pipeline mapping Linux reconciliation — 2026-08-21

## Outcome

Blender's canonical in-tree `wgpu_pipeline.cc` postimage now has a checkout-relative,
device-free native/Wasm parity contract for its pure primitive-topology and vertex-format
mappings. The test compiles the shipping translation unit directly and section-collects its
unreached live-device/cache half rather than copying product logic or supplying fake symbols.
The canonical `BLI_assert.cc` is linked in both graphs so the deliberately unsupported
triangle-fan call remains fail-visible in Release builds.

Four contracts cover all 11 `GPUPrimType` rows and all 96 combinations of eight
`GPUVertCompType` values, four valid component lengths, and three `GPUVertFetchMode` values.
This includes the signed packed-normal resolution: all four normalized I10 cases map to
`Snorm8x4`, while the eight non-normalized cases retain `Unorm10_10_10_2`. The triangle-fan row
emits the exact canonical two-line unreachable diagnostic before returning its documented
`TriangleList` fallback.

Root and descendant runs are green at `20260821T211523-597109` and
`20260821T211542-597723`. Native and Node emit byte-identical 232-byte stdout
(`sha256:79b3dccccc1c`) plus byte-identical 193-byte stderr (`sha256:4855ed8f3218`). The 12
direct canonical pipeline/enum/assert inputs have combined identity `sha256:65e002d247cb` and
the byte-identical native/Wasm fmt sentinel is `sha256:ccaf61c9b593`. Both targets finish at
locked-Ninja no-work. Wrong-Dawn and wrong-Node controls reject with zero build/evidence
allocations (`20260821T211612-598256` / `20260821T211619-598341`).

Canonical clean-pin replay remains 257 paths at `sha256:e03f140fe3f3`, the existing windowed
product is exact no-work, and REUSE 6.2.0 is 1,975/1,975 green
(`20260821T211728-598962` / `598953` / `598952`).

## Boundary

The contract creates no WebGPU instance, adapter, device, render pipeline, command encoder,
pixel evidence, or M3 receipt. It does not replace the historical live Dawn/Metal descriptor
and pixel proof; fresh Linux live replay remains owned by `M3-LINUX-REPLAY` after s7 exposes an
accepted hardware adapter. Required M3 remains red for the absent strict candidate, and the
container-backed regression at `2026-08-21T21:18:03Z` keeps M0 6/6 green while M1–M8 remain
honestly red on their existing strict-manifest, APPLY/artifact, browser, run-label, and hardware
boundaries. No product/upstream/GPU implementation, receipt, result flag, dependency record,
deferral, tolerance, golden, blacklist, or promise changed.
