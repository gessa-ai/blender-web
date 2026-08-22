<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T9 RGB9E5 conversion — 2026-08-21

## Outcome

Patch 0153 closes the canonical texture path's silent `UFLOAT_9_9_9_EXP_5` gap. The format
table already selected WebGPU's native `RGB9E5Ufloat`, but `repr_of()` classified it as
unsupported, so CPU upload, readback, and clear returned without moving data. The new shared
conversion helpers implement the 9/9/9-bit mantissas plus 5-bit shared exponent and wire all
three operations to the native 32-bit layout.

The arithmetic follows the pinned Dawn definition and vectors at
`build-dawn/dawn/src/dawn/native/BlitTextureToBuffer.cpp:626` and
`build-dawn/dawn/src/dawn/tests/end2end/TextureFormatTests.cpp:985`: each channel decodes as
`mantissa * 2^(exponent - 24)`. Packing clamps negative/NaN inputs to zero and positive infinity
to 65,408, rounds each mantissa, and advances the shared exponent on a 512-mantissa rollover.

## Evidence

The pre-fix exact-source contract stopped at the absent production pack/unpack API
(`20260822T001018-763213`). The final device-free native and wasm32/Node executions cover three
Dawn decode vectors plus seven canonical/edge encodes, including the exponent rollover and
negative/NaN/infinity inputs. Their complete 506-byte stdout is byte-identical at
SHA-256 `f993d883b41d`; the contract also requires the exact format classification, two packing
call sites, one unpacking call site, and all eight table/conversion/texture/enum inputs before
evidence allocation (`20260822T002045-776809`).

The canonical freezer retained 257 paths and 20,258 manifest entries. Its 1,535,730-byte patch is
SHA-256 `a8a582c521d3`, and its live/replay manifests are byte-identical at
SHA-256 `3553bf3594cf` (`20260822T001608-771707`). Canonical replay is green
(`20260822T001657-773039`). The real windowed Wasm product rebuilt through locked Ninja and then
ended at exact no-work (`20260822T001728-773863`, `20260822T001810-774202`). REUSE 6.2.0 is
2,010/2,010 green (`20260822T002233-778582`).

## Boundary

This is deterministic CPU-side format conversion. The contract creates no WebGPU instance,
adapter, device, texture, profile, or receipt. Required M3 remains red for the absent fresh strict
candidate; container-backed regression keeps M0 6/6 green while M1-M8 retain their existing
strict-receipt, APPLY/artifact, browser/run-label, and s7 hardware boundaries. No result was
promoted and no deferral, tolerance, golden, blacklist, dependency decision, or promise changed.
