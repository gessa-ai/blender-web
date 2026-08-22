<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T6 WebGPU buffer-read offset alignment — 2026-08-22

## Outcome

Patch 0195 rejects a misaligned source offset before `Buffer::read()` reaches either native
Dawn's `CopyBufferToBuffer` encoder or the browser asynchronous readback registry. The read path
now reuses the existing checked copy-span validator, so source-offset alignment, aligned transfer
size, and allocation containment are decided together.

## Diagnosis

`Buffer::read()` already rounded the requested size to four bytes and checked the resulting range,
but it did not check `offset % 4`. The pinned Dawn contract fixes buffer-copy offset alignment at
four bytes (`build-dawn/dawn/src/dawn/common/Constants.h:86`) and rejects either source or
destination offset when it is not a multiple of four
(`build-dawn/dawn/src/dawn/native/CommandEncoder.cpp:374-378`). Native reads could therefore
create a validation-invalid command, while the wasm path reached `kick_buffer()` only to be
rejected there later.

The production seam now calls `buffer_copy_range_valid(offset, 0, copy, size_, copy)` after the
checked size alignment. The helper was already used by storage-buffer copies and already had a
native/wasm32 contract for misaligned source and destination offsets; the expanded source guard
binds that exact decision to `Buffer::read()`.

## Evidence

- The fail-first source contract stopped before evidence allocation on the absent read-path call
  (`20260822T191718-1799581`).
- Root and descendant-working-directory runs compile the canonical buffer implementation for
  native and wasm32 and pass 13 byte-identical contracts, including the nine-case copy-range
  matrix. Output is 988 bytes at SHA-256
  `56bf5c1a0285988bb5a4dbac446692054d592587a76f65fb7a7e77adf7c1840a`; shipping inputs are
  SHA-256 `f75699fcc53b6035a134d624c18af3df382ee332ffbf14021d28f0e7fc38f851`
  (`20260822T191953-1802069`, `20260822T192118-1803471`). Wrong Dawn and Node identities allocate
  no requested evidence (`20260822T192142-1803966`, `20260822T192150-1804128`).
- The canonical freezer retains 257 paths and 20,258 entries. Its 1,646,581-byte patch is SHA-256
  `9a9d91ad82ff65dc76a78f699b2f1bae4cbf64b4d91e33a6646092b852ccd6a6`; live and replay
  manifests are byte-identical at SHA-256
  `7ff9c29b238917e89dbf74bfaa7e8d6235e363598cb249469239d5fb2d9f2d8b`
  (`20260822T191858-1800611`, `20260822T191941-1801927`). Numbered patch reverse application is
  green (`20260822T192204-1805274`).
- The optimized `blender_browser` rebuild and exact locked-Ninja no-work check are green
  (`20260822T192018-1802854`, `20260822T192056-1803231`); OFF-mode product preflight is green
  (`20260822T192115-1803445`). Final REUSE 6.2.0 reports 2,110/2,110 files compliant
  (`20260822T192553-1808436`).
- Required M3 remains red for the absent fresh strict candidate at `2026-08-22T19:23:10Z`.
  Container-backed regression keeps M0 6/6 green while M1-M8 retain their named strict-receipt,
  product, browser, run-label, and hardware boundaries at `2026-08-22T19:23:11Z`.

## Boundary

This task creates no accepted WebGPU adapter, device, buffer, command, browser receipt, result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone promise.
The s7 software-adapter stop condition remains live.
