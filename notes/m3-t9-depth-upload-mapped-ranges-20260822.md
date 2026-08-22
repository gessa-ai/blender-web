# M3.T9 depth-upload mapped ranges — 2026-08-22

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0199 makes both mapped-at-creation buffer writes in
`WGPUContext::upload_depth_render()` fail closed. A WebGPU error buffer that exposes no mapped
range now returns `false` before host memory is touched, before an invalid unmap, and before bind
group, render-pass, draw, or submission work.

## Diagnosis and implementation

The depth upload checked the values and parameter buffer handles but passed each unverified
`GetMappedRange()` result directly to `memcpy`. WebGPU handle presence is not proof that a mapped
range exists. The new dependency-light `mapped_buffer_write()` helper checks null/empty caller
inputs, checks the mapped pointer, copies the exact payload only on success, and unmaps exactly
once. Both shipping call sites guard its result. This is the Class-31 fallible mapped-range
pattern already recorded in `notes/porting-patterns.md`.

## Evidence

- The fail-first exact-source guard rejected the unchanged source before evidence allocation
  (`20260822T203524-1872434`).
- Final root and descendant-directory native/wasm32 runs pass 16 byte-identical buffer contracts,
  including four mapped-write cases for null input, empty input, missing mapped range with zero
  copy/unmap work, and successful exact-byte copy with one unmap. Output is 1,286 bytes at
  SHA-256 `b3bac669ae9c`; shipping inputs are SHA-256 `53455f7a0be2`
  (`20260822T203807-1874910`, `20260822T203907-1876716`). Wrong Node 22.22.1 rejects before the
  isolated evidence directory is allocated (`20260822T204128-1879868`).
- The canonical freezer retains 257 paths and 20,258 entries. Its 1,648,030-byte patch is
  SHA-256 `c79951909266`; live and replay manifests are byte-identical at SHA-256
  `d0ee4f840e90` (`20260822T203721-1874403`). Canonical replay and patch-0199 reverse-check are
  green.
- The optimized windowed product rebuilds the affected WebGPU translation units, relinks, and
  ends at exact locked-Ninja no-work (`20260822T203925-1877290`,
  `20260822T204017-1877779`). OFF-mode product preflight is green, and final REUSE 6.2.0 reports
  2,121/2,121 compliant files (`20260822T204212-1880402`).
- Required M3 remains red for the absent fresh strict candidate at `2026-08-22T20:40:41Z`.
  Container-backed regression keeps M0 6/6 green while M1-M8 retain their named strict receipt,
  product, browser, run-label, and hardware boundaries at that timestamp.

## Boundary

This task creates no accepted WebGPU adapter, device, buffer, bind group, render pass, draw,
submission, pixel or browser receipt, result promotion, dependency decision, deferral, tolerance,
golden, blacklist, or milestone promise. The s7 software-adapter stop condition remains live.
