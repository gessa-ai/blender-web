<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T6 WebGPU buffer range-overflow hardening — 2026-08-22

## Outcome

Patch 0174 makes the shared WebGPU buffer wrapper fail closed when 4-byte size alignment is
unrepresentable or a byte subrange exceeds its allocation. Buffer creation and readback use
checked alignment, while updates use subtraction-form range containment instead of the wrapping
`offset + size` comparison.

## Diagnosis and implementation

The former `align_up` expression in
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:58` wraps values near `SIZE_MAX` to a small
allocation, and `Buffer::update_sub` formerly accepted a range whenever the wrapped sum compared
below `size_`. That could forward an invalid offset and size to Dawn rather than rejecting the
request at the backend boundary.

`checked_align_up` now validates a nonzero power-of-two alignment and proves the addition is
representable before publishing its output. `range_fits` expresses half-open containment as
`offset <= capacity && size <= capacity - offset`. The shipping creation, update, and read paths
are source-bound to those helpers at
`upstream/source/blender/gpu/webgpu/wgpu_buffer.cc:106`, `:150`, and `:190`.

## Evidence

- The unchanged production source fails to compile against the checked arithmetic contract at
  the absent `checked_align_up` and `range_fits` APIs (`20260822T090050-1242368`).
- The final native and wasm32 executions cover seven alignment cases and four range cases through
  `SIZE_MAX` byte-identically at 794 bytes, SHA-256
  `dc964e0b367ab54c06954240e808faaa19c15a3d4ab4243442c11f4add554994`; all ten integrated
  buffer contracts pass with source SHA-256
  `dbfe6fd43e707a641844fcaf058e46aca8795bb246e9f5dfb311ef1a4a65723d`
  (`20260822T090437-1246439`).
- Canonical freeze and independent replay retain 257 paths and 20,258 entries. The canonical
  patch is 1,565,421 bytes at SHA-256
  `e4d6d1714e3f270c56ae43f01a2e15b1cc72b09b84d1a88b1a5d6e806883ac6c`; live/replay
  manifests are byte-identical at SHA-256
  `3a6823e5567cee3f7ac813006ff1da79f08835892bf64242cafe832de094b8f4`
  (`20260822T090318-1244890`, `20260822T091419-1254762`).
- The optimized windowed wasm product recompiles `wgpu_buffer.cc`, links, and then reports exact
  locked-Ninja no-work (`20260822T090535-1247538`, `20260822T090617-1247925`).
- REUSE 6.2.0 reports copyright and license information for all 2,057 files
  (`20260822T091352-1253768`).
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260822T090634-1248502`). Container-backed regression restores M0 6/6 green and retains
  M1-M8 red on their existing strict-receipt, product, browser, run-label, and hardware
  boundaries (`20260822T090641-1248933`).

## Boundary

The contract creates no WebGPU instance, adapter, device, buffer, command, browser receipt, or
result promotion. Live buffer behavior remains owned by `M3-LINUX-REPLAY`, still blocked by the
named s7 software-adapter condition.
