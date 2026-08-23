<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU dummy-buffer error-object contract — 2026-08-23

## Outcome

Commit `d8cd71d` closes the shared dummy-vertex-buffer slice of the R6 GPU resource
error-object audit. The `{0,0,0,1}` default attribute is now initialized through
`mappedAtCreation` while the candidate remains local, and the fixed-key cache publishes it only
after validation, out-of-memory, and internal scopes complete cleanly. A pending or rejected
candidate remains unavailable to draw binding and the same key can retry on a later frame.

This does not close resource creation as a whole. Persistent and transient buffer allocations
outside the dummy path, texture/view, bind-group/layout, pipeline-layout, and pipeline creation
still need completed-scope status and remain the highest-priority
`AUDIT-R6-GPU-RESOURCE-ERROR-OBJECT-CONTRACT` residual.

## Evidence

- The unchanged shipping source fails the new helper/cache source contract before build or
  evidence allocation (`20260823T103144-2676073`).
- Root and descendant-CWD integrated runs compile the shipping source through locked native and
  wasm32 graphs and pass 27 byte-identical contracts. Evidence is 2,962 bytes at SHA-256
  `3151bad75866705605be636c5e43ca96925751d7280dbaed5776d8b8c5c41cd1`; the bound source hash is
  `1f742b74bf894c44d1ec800a6b78339f932d673145e2ddfaaf7695ae31264380`
  (`20260823T103522-2679789`, `20260823T103533-2680618`). The three new creation cases cover a
  null allocation, a missing mapped range, and exact initialized bytes.
- The exact shipping helper compiles in the pinned Dawn graph (`20260823T103355-2678051`). Its
  llvmpipe control rejects a real non-null invalid buffer, then publishes an initialized retry and
  reports `scoped_dummy_buffer_cases=2 dummy_buffer_error_object_rejected=1`
  (`20260823T103405-2678131`). The transcript explicitly says
  `SOFTWARE_CONTROL_NON_RECEIPT`; it binds no milestone or hardware claim.
- The canonical clean-pin freeze retains 257 paths and 20,258 entries. Its 1,703,445-byte patch is
  SHA-256 `ed94fc0509c0017a5fe18ce3975961bb642073d5bd5a107ff31a9c8149d9af60`, and the live/replay
  manifest hash is `3ccde2585d8b19af8ed0f7d3af0653a519d03607f6505b766b7bcd8708f3da8f`.
  Canonical replay passes (`20260823T103515-2679677`). Numbered patch 0232 is 4,953 bytes at
  SHA-256 `836d71ad3549328e1513e715c3992562a3879f4b182c4d44455de052e32bc04c` and passes an isolated
  reverse/forward byte round trip (`20260823T104117-2686620`).
- The real `blender_browser` relinks and ends exact locked no-work
  (`20260823T103552-2681540`, `20260823T103659-2682903`). OFF preflight binds the
  118,510,385-byte primary Wasm (`20260823T103719-2683056`). REUSE 6.2.0 reports all 2,199 files
  compliant (`20260823T104207-2687651`).
- Required M3 remains honestly red only for the absent fresh strict candidate
  (`20260823T103830-2683722`). Container-backed regression restores M0 6/6 green while M1-M8
  retain their existing strict-receipt, product, browser, run-label, hardware, and release
  boundaries (`20260823T103901-2684211`). No gate result was promoted.

## Boundary

The live hardware WebGPU receipt remains deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry
dzn, launch a hardware browser, weaken a receipt, modify a result verdict, or claim live pixels.
