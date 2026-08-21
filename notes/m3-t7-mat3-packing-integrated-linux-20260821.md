<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T7 float3x3 push-constant packing — 2026-08-21

## Outcome

Patch 0152 fixes the canonical `WGPUShader::push_constant_set` path for float3x3 values. Blender
supplies nine tightly packed floats, while std140 stores the matrix as three float3 columns at a
16-byte stride. The WebGPU writer now copies each 12-byte column separately and leaves the four
padding bytes after every column, matching the pinned Vulkan layout.

The extracted device-free contract covers all four pinned float3x3 declarations:
`NormalMatrix`, `gpu_scene_linear_to_rec709`, `scope_gamut_to_rec709`, and `scope_yuv_matrix`.
The pre-fix experiment failed at the first `NormalMatrix` padding word
(`20260821T234909-744871`). After the fix, native and wasm32/Node executions cover four matrices,
12 columns, all 144 payload bytes, and all 48 padding bytes with byte-identical 772-byte output,
SHA-256 `cb74c418a316`; the extracted method is SHA-256 `59c62511e950`
(`20260821T235452-749678`).

## Source and fail-closed evidence

The extractor now binds both the existing array-stride path and the new matrix-column path. Its
adversarial self-check rejects each independently before allocating generated evidence, and the
driver also freezes the exact four-declaration create-info census (`20260821T235439-749422`).

The canonical freezer retained 257 paths and 20,258 manifest entries. The 1,532,106-byte patch is
SHA-256 `3045050329c5`, and its byte-identical live/replay manifest is SHA-256 `dec961c47e21`
(`20260821T235232-748435`, integrity check `20260821T235436-749361`). The windowed Wasm target
rebuilt the affected edge and then ended at exact locked-Ninja no-work
(`20260821T235519-751188`, `20260821T235602-751524`).

## Boundary

This is a deterministic CPU-side packing correction. The contract creates no WebGPU instance,
adapter, device, shader module, pipeline, profile, or receipt. Required M3 remains red for the
absent fresh strict candidate (`20260821T235630-751781`); container-backed regression keeps M0
6/6 green and M1–M8 red on their existing strict-receipt, APPLY/artifact, browser/run-label, and
s7 hardware boundaries (`20260821T235638-751865`).
