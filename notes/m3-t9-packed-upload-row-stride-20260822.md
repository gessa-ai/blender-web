<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T9 packed strided-upload row parity — 2026-08-22

## Outcome

Patch 0168 makes WebGPU's strided texture-upload path use Blender's whole-host-texel size
helper. The prior component-count formula treated the already compact
`GPU_DATA_2_10_10_10_REV` and `GPU_DATA_10_11_11_REV` representations as four or three
independent 32-bit components, advancing each source row by 4x or 3x its real byte stride.
The corrected expression matches the pinned Vulkan path in
`source/blender/gpu/vulkan/vk_texture.cc` and leaves ordinary scalar-component rows unchanged.

## Experiment and device-free contract

The unchanged postimage failed the direct source precondition at
`source/blender/gpu/webgpu/wgpu_texture.cc:1398`, where a packed texel was sized as logical
components times data-format bytes. The texture integrated smoke now binds that exact shipping
call site to `to_bytesize(format_, format)` and compiles Blender's real inline helper. Six cases
cover RGB10A2 UNORM/UINT and R11G11B10 compact rows plus float R11G11B10, RGBA8, and RG32F
controls. A seven-texel row totals 252 bytes across the matrix, and each of the three compact
cases is exactly 28 bytes.

The helper's canonical private-header closure links Blender's real `BLI_assert.cc`; native and
wasm32 consume byte-identical pinned fmt headers. Both legs emit the same 734-byte nine-contract
record (`sha256:51e68c56e43f`), bind the fourteen-source digest
`182beb94f162`, and finish locked-Ninja no-work
(`ledger/buildlogs/20260822T060735-1089497.log`).

## Canonical integration and product build

The independent freezer retained 257 source paths and 20,258 manifest entries. Its live and
replay manifests are byte-identical at SHA-256
`a690ef64439b3e8df49b2cf9034e728931481bbb0832825bec4089be797cfe4a`; the 1,548,277-byte
canonical patch is bound by SHA-256
`f7240244a1971f87399010bbf2afe64e145837172cafa67ae9ead6cfa028a5d9`
(`ledger/buildlogs/20260822T060634-1088772.log`). Clean-pin canonical replay independently
passes with 145 active numbered patches (`ledger/buildlogs/20260822T060725-1089392.log`).

The real `blender_browser` target rebuilt the corrected texture translation unit, GPU archive,
and windowed product, then reported exact locked-Ninja no-work
(`ledger/buildlogs/20260822T060754-1089964.log`,
`ledger/buildlogs/20260822T060835-1091095.log`). This device-free correction creates no
adapter, device, texture, browser receipt, result promotion, dependency decision, deferral,
tolerance, golden, or blacklist. The strict M3 replay remains owned by the named s7 hardware
adapter gate.

Shell syntax, patch reverse-application, snapshot checksum, scoped whitespace checks, and exact
REUSE 6.2.0 are green for 2,046/2,046 files
(`ledger/buildlogs/20260822T061104-1092015.log`). The live control still identifies only
llvmpipe adapter type 3, rejects it before device evidence, and emits the exact software-adapter
PASS (`ledger/buildlogs/20260822T061248-1095354.log`). The required M3 scope therefore remains
red only for the absent fresh strict candidate (`ledger/buildlogs/20260822T061201-1094132.log`).
Container-backed regression keeps M0 at 6/6 green and leaves M1–M8 red at their existing strict
receipt, browser artifact, run-label, and hardware boundaries
(`ledger/buildlogs/20260822T061206-1094198.log`).
