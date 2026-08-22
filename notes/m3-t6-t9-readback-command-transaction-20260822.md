<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T6/T9 WebGPU readback command transaction — 2026-08-22

## Outcome

Patch 0208 makes both asynchronous readback kick paths fail closed when WebGPU returns a null
command encoder or finished command buffer. A failed texture or buffer kick now releases its
pinned backend handles and publishes the reserved ticket as terminal
`CommandEncodingFailed` before mapping or submission.

## Diagnosis and implementation

Both paths already guarded staging-buffer allocation, but immediately dereferenced the command
encoder and submitted the result of `Finish()` without validating either handle. A transient
creation failure could therefore reach a null-handle call or schedule `MapAsync` for work that
was never submitted, leaving the readback registry pending indefinitely.

The shared `command_encode_submit_if_valid()` transaction validates the encoder before the copy,
validates the finished command buffer before submission, and submits exactly once only on success.
The two callers use the existing `fail_reserved_pending()` accounting path, release staging and
source pins, and return the preserved ticket without installing a callback.

## Verification

- The unchanged backend is rejected at the absent helper before evidence allocation
  (`20260822T234102-2072481`).
- Final root and descendant-CWD native/wasm32 runs pass 17 byte-identical integrated buffer
  contracts at 1,344 bytes, SHA-256
  `f70d802d9d0c9ef7b00a44abcace5fcb233dbf64d444228049bc8d3f3e23afd7`; the shipping input set
  binds at SHA-256 `267ed3572b169a728a6c231d20fd4295a6bbce5fb21bf474837b4f6a762d64e7`
  (`20260822T234557-2076954`, `20260822T235104-2083506`). The new three-case transaction proves
  encoder failure performs no copy/finish/submit, finished-buffer failure performs no submit,
  and success copies, finishes, and submits exactly once.
- Wrong Node 22.22.1 is rejected before evidence allocation (`20260822T234924-2081692`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,654,403-byte
  canonical patch is SHA-256
  `87f54b05a7d15062d0078da76d3cb6f6ea4b450b4266f9926bbd1d006cba7706`; both manifests are
  SHA-256 `3c3638f2c15c7f18b38aa67d9d05b35e94c8245d067e61ee54c3537b740d2033`
  (`20260822T234417-2075467`, `20260822T234546-2076855`). Final patch 0208 is 102 lines at
  SHA-256 `dd56e71213dab2be16d7e99f2fd5e886a4fda83e97b81fca6c65b9d5e4536535` and reverse-applies
  cleanly to the live source.
- The real `blender_browser` rebuild and exact locked no-work check are green
  (`20260822T234632-2078362`, `20260822T234717-2078811`). OFF preflight binds the resulting
  118,072,756-byte primary Wasm (`20260822T234751-2079138`).
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260822T234837-2080067`). The final container-backed regression restores M0 to 6/6 GREEN
  while M1-M8 retain their existing strict-receipt/product/browser/run-label/hardware boundaries
  (`20260822T234907-2080872`).
- Final REUSE 6.2.0 reports all 2,140 files compliant (`20260822T235225-2084383`).

## Boundary

No WebGPU instance, adapter, device, buffer, encoder, command buffer, submission, mapping, pixel,
or browser receipt is claimed. Live proof remains blocked by **no conformant hardware Vulkan ICD
in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result promotion, dependency decision,
deferral, tolerance, golden, blacklist, or milestone promise changed.
