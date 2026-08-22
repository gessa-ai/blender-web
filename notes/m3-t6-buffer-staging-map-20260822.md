# M3.T6 WebGPU large-buffer staging map — 2026-08-22

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0198 makes the shared large `Buffer::update_sub()` path reject a missing
mapped-at-creation range before `memcpy`, unmap, command encoding, or queue submission. A Dawn
error buffer or other failed mapping now returns `false` to the caller instead of dereferencing a
null pointer.

## Diagnosis and implementation

The common initial-buffer creation path already treated `GetMappedRange()` as fallible, but its
large-update sibling checked only the `CreateBuffer()` handle and copied directly through the
returned pointer. WebGPU handle presence is not proof that a mapped range is available. The update
now stores the pointer, checks it, and performs the existing exact-byte copy only after success.
Small `Queue::WriteBuffer` updates and successful staging-copy ordering are unchanged. This is the
fallible mapped-range pattern recorded as Class 31 in `notes/porting-patterns.md`.

## Evidence

- The fail-first exact-source guard rejected the unchanged direct `GetMappedRange()` dereference
  before evidence allocation (`20260822T201836-1856956`).
- Final root and descendant-directory native/wasm32 runs pass 15 byte-identical contracts. The
  nine exact extracted update
  cases cover invalid destination/source/alignment/range inputs, the 65,536-byte direct boundary,
  staging allocation failure, staging map failure with zero later work, and a successful
  65,540-byte staged copy. Output is 1,216 bytes at SHA-256
  `8b139f3e0dc02f9d2a72e625c45ab8852d50e46409d5abfbf98d8efdcb3d80cf`; shipping inputs are
  SHA-256 `9f2af0938f7ee0431d14487160580c38315fcc89438936f054fe275cc1c937c0`
  (`20260822T201955-1858607`, `20260822T202504-1864087`).
- The canonical freezer retains 257 paths and 20,258 entries. Its 1,647,410-byte patch is SHA-256
  `9174c6902f50357492ef851d46ff7d3e1894a6997c59ebc35ef28df8166df6b7`; live and replay
  manifests are byte-identical at SHA-256
  `5c090771c62030b921b2b30ce87ebe4a8dfeb04b5d45e95fd4ab9dadce73a72e`.
  Canonical replay and numbered-patch reverse application are green
  (`20260822T202246-1862434`, `20260822T202252-1862514`).
- The optimized windowed product recompiles `wgpu_buffer.cc`, relinks, and finishes at exact
  locked-Ninja no-work (`20260822T202026-1859539`, `20260822T202125-1860893`). OFF-mode product
  preflight is green (`20260822T202128-1860923`), and REUSE 6.2.0 reports 2,119/2,119 compliant
  files (`20260822T202519-1864640`).
- Required M3 remains red for the absent fresh strict candidate at `2026-08-22T20:22:27Z`.
  Container-backed regression restores M0 to 6/6 green while M1-M8 retain their named strict
  receipt, product, browser, run-label, and hardware boundaries at that timestamp.

## Boundary

This task creates no accepted WebGPU adapter, device, buffer, command encoder, queue submission,
browser receipt, result promotion, dependency decision, deferral, tolerance, golden, blacklist,
or milestone promise. The s7 software-adapter stop condition remains live.
