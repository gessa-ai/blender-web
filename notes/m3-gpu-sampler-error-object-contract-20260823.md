<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU sampler error-object contract — 2026-08-23

## Outcome

Commit `3d67aa6` closes the sampler-cache slice of the R6 GPU resource error-object audit. A sampler
candidate now remains pending and unpublished until validation, out-of-memory, and internal error
scopes all complete cleanly. A non-null Dawn sampler error object is rejected, its key remains
retryable, and an already accepted cached sampler is preserved.

This does not close resource creation as a whole. Buffer, texture/view, bind-group/layout,
pipeline-layout, and pipeline creation/cache publication still need completed-scope status and
remain the highest-priority `AUDIT-R6-GPU-RESOURCE-ERROR-OBJECT-CONTRACT` residual.

## Implementation

`ScopedHandleCache` owns a reference-counted state containing accepted handles, pending keys, and a
mutex. The first cache miss marks its key pending before creation; repeated misses deduplicate while
the browser callback is outstanding. The candidate is retained in callback-owned storage and is
published atomically only when the handle is non-null and the completed scope result is clean.
Failure erases only the pending marker, so a later call can retry. The callback captures shared
state rather than the owning `WGPUContext`, allowing it to settle safely after context destruction.

`WGPUContext::get_sampler()` returns an accepted cached sampler first, refuses creation without a
live instance/device, and otherwise routes `CreateSampler` through the scoped cache. A browser miss
returns null until scope completion; existing checked command paths therefore reject dependent work
for that frame instead of consuming a provisional object.

Patch 0231 contains the shipping-source change. Integrated source guards require the scoped cache
and reject the previous direct map lookup and null-only publication helper.

## Evidence

- The unchanged shipping source fails the new cache source contract before build or evidence
  allocation (`20260823T095003-2638437`).
- Final root and descendant-CWD integrated runs compile the shipping source through locked native
  and wasm32 graphs and pass 26 byte-identical contracts. Evidence is 2,836 bytes at SHA-256
  `953210ed733966000fede8ec208da2ad3a1dacfceffa83da47b33e438d443937`; the bound source hash is
  `0f4d05072fbec3d7f55f668eb2a0ec8df76864e95438e35e085486f5f8b6b04f`
  (`20260823T101229-2659482`, `20260823T101241-2660319`). The new five-case model covers pending
  non-publication, duplicate suppression, non-null rejection, clean retry, and cache-hit
  preservation. A wrong Node version rejects before evidence allocation
  (`20260823T101429-2662646`).
- The exact shipping cache compiles in the pinned Dawn graph (`20260823T095353-2641939`). Its live
  llvmpipe control creates a non-null invalid sampler, rejects it, then publishes a valid retry and
  reports `scoped_sampler_cases=2 sampler_error_object_rejected=1`
  (`20260823T095421-2642893`). The transcript explicitly says `SOFTWARE_CONTROL_NON_RECEIPT`; it
  binds no milestone or hardware claim.
- The canonical clean-pin freeze retains 257 paths and 20,258 entries
  (`20260823T101016-2657386`). Its 1,702,789-byte patch has SHA-256
  `946ac5baae5bab0fad0ac24ae4faf87f6c3fc0c0d1b497f2ef217ab13dbefccc`, and the live/replay
  manifest hash is `c83b464235944154b65ca71a42041bac0ad10c2dcdab086e39692d929a93c046`.
  Numbered patch 0231 is 6,580 bytes at SHA-256
  `176b3285aff318d1fc02b20994e80ed2b62c80fbeac4339d1463a0cfc1e84d7c` and passes independent
  forward/reverse application checks.
- The real `blender_browser` rebuild and exact locked no-work pass
  (`20260823T101332-2661354`, `20260823T101414-2661781`). OFF preflight binds the
  118,511,492-byte primary Wasm (`20260823T101419-2662292`).
- Final REUSE 6.2.0 reports all 2,197 files compliant (`20260823T102221-2668961`).
- Required M3 remains honestly red only for the absent fresh strict candidate
  (`20260823T101606-2663818`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict-receipt, product, browser, run-label, hardware, and release boundaries
  (`20260823T101610-2663865`). No gate result was promoted.

## Boundary

The live hardware WebGPU receipt remains deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry
dzn, launch a hardware browser, weaken a receipt, modify a result verdict, or claim live pixels.
