<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T6 WebGPU initial index-upload commit — 2026-08-22

## Outcome

Patch 0197 makes buffer creation publish its handle and metadata only after mapped-at-creation
initialization succeeds, and makes `WGPUIndexBuffer::upload_data()` transfer CPU index-data
ownership only after that complete transaction. Allocation or mapping failure now preserves an
invalid destination, the host payload, and uncommitted upload state so a later draw can retry.

## Diagnosis and implementation

The common buffer wrapper already returned `false` for invalid limits, allocation failure, or a
missing mapped range. The index caller discarded that result, unconditionally deleted `data_`, and
set `data_uploaded_`. Blender's pinned Vulkan path instead checks allocation before entering its
upload/ownership-transfer path (`source/blender/gpu/vulkan/vk_index_buffer.cc:25-31`).

The common wrapper now constructs and initializes a local WebGPU handle, publishing it and its
metadata only on success. The index caller returns immediately when that creation fails. Its
existing successful path and odd-u16 exact-byte upload remain unchanged. This is the fallible
creation/ownership pattern recorded as Class 30 in `notes/porting-patterns.md`.

## Evidence

- The fail-first extracted shipping-method contract stopped on the failed-create retention check:
  unchanged code consumed the six-byte payload and committed upload state
  (`20260822T195613-1835077`).
- Final root and descendant-directory runs compile the exact extracted method for native and
  wasm32 and pass 14 byte-identical contracts. The six upload cases cover subrange delegation,
  an existing device buffer, absent context, device-built allocation, failed creation plus
  successful retry, and first-attempt success. Output is 1,097 bytes at SHA-256
  `57d41cb33db7b17f7e35a31ca2e04965182d4756d7198dadfd936fe9d052689a`; shipping inputs are
  SHA-256 `0f1e3a8698e8ea6773a4c7c82a8a766f1aa7cbae0cd57e127c733248b9774058`
  (`20260822T200626-1846450`, `20260822T200641-1847187`).
- The canonical freezer retains 257 paths and 20,258 entries. Its 1,647,332-byte patch is SHA-256
  `8d4a58b3c140ea1fda6a22e25bc0910324ce67a57e6912b99a01127de8a660d2`; live and replay manifests
  are byte-identical at SHA-256
  `52e477b754325d409d4d2942dd4f4e6c11bfa57720c0210304b2c0869f70f861`
  (`20260822T200522-1844928`). The numbered patch reverse-check is green.
- The optimized `blender_browser` recompiles `wgpu_buffer.cc` plus `wgpu_index_buffer.cc`, relinks,
  and finishes at exact
  locked-Ninja no-work (`20260822T200657-1847726`, `20260822T200740-1848173`). OFF-mode product
  preflight is green (`20260822T200740-1848174`). REUSE 6.2.0 reports 2,115/2,115 files compliant
  (`20260822T200850-1849443`).
- Required M3 remains red for the absent fresh strict candidate at `2026-08-22T20:07:55Z`.
  Container-backed regression keeps M0 at 6/6 green while M1-M8 retain their named strict-receipt,
  product, browser, run-label, and hardware boundaries at the same timestamp.

## Boundary

This task creates no accepted WebGPU adapter, device, buffer, command, browser receipt, result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone promise.
The s7 software-adapter stop condition remains live.
