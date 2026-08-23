<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU persistent-buffer error-object contract — 2026-08-23

## Outcome

Commit `b3a0abb` closes the persistent-buffer slice of the R6 GPU resource error-object audit.
Index, vertex, uniform, storage, texel-expansion, and shader push-constant buffers now cache one
composite allocation containing the handle and its metadata. The allocation remains unpublished
until validation, out-of-memory, and internal scopes settle cleanly. Duplicate pending calls are
deduplicated, rejected non-null candidates retry, and initial index bytes remain caller-owned until
an accepted allocation is observable on a later frame.

This does not close resource creation as a whole. Short-lived batch/immediate staging and fan
buffers retain the explicitly documented null-only compatibility seam and are the next smallest
slice. Texture/view, bind-group/layout, pipeline-layout, and pipeline creation also remain open
under `AUDIT-R6-GPU-RESOURCE-ERROR-OBJECT-CONTRACT`.

## Evidence

- The unchanged shipping source fails the new persistent-creation source contract before build or
  evidence allocation (`20260823T110326-2702330`).
- The exact extracted creation and index-upload methods compile through locked native and wasm32
  graphs and pass 18 byte-identical contracts, including six persistent-creation cases and seven
  index ownership cases. Evidence is 1,515 bytes at SHA-256
  `8ab98c2bf88c50836cbcf075fc2266b5e7899e3ef5f45947bf8dd20211141d74`; the bound source hash is
  `635618d876c3e9054bd1a2d1ba7f21b04b8cea7825ed1e739b4a472e3776f619`
  (`20260823T111120-2711195`). An ambient Node 22.22.1 control rejects before creating its fresh
  evidence directory (`20260823T111754-2718194`).
- The exact shipping cache compiles in the pinned Dawn graph (`20260823T111150-2712378`). Its
  llvmpipe control rejects a real non-null invalid buffer, publishes a clean retry with its metadata,
  and reports `scoped_persistent_buffer_cases=2 persistent_buffer_error_object_rejected=1`
  (`20260823T111157-2712459`). The transcript explicitly says
  `SOFTWARE_CONTROL_NON_RECEIPT`; it binds no milestone or hardware claim.
- The canonical clean-pin freeze retains 257 paths and 20,258 entries. Its 1,706,207-byte patch is
  SHA-256 `f87639add8abc43df066d5d85056a36ed470fbdf05bf56a30bc24706c5a12ec6`, and the live/replay
  manifest is 3,477,333 bytes at SHA-256
  `3e81c417c378fa1c65908473dcef42eccbddfd93547f7c190c79640293dea142`. Canonical replay passes
  (`20260823T110819-2707263`). Numbered patch 0233 is 24,833 bytes at SHA-256
  `f9f35cfa65205e6b29195627cae5d0e25d7cbb8a359d57d7a002546f3d4f1402` and passes isolated
  applicability, application, and live byte-comparison checks (`20260823T110630-2706014`,
  `20260823T110635-2706069`, `20260823T110641-2706138`).
- The real `blender_browser` relinks and ends exact locked no-work
  (`20260823T111217-2712691`, `20260823T111300-2713094`). OFF preflight binds the
  118,526,586-byte primary Wasm (`20260823T111308-2713196`). The final REUSE 6.2.0 run reports all
  2,203 files compliant (`20260823T111939-2719873`).
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260823T111943-2719984`). Container-backed regression restores M0 6/6 green while M1-M8
  retain their existing strict-receipt, product,
  browser, run-label, hardware, and release boundaries (`20260823T111947-2720051`). No gate result
  was promoted.

## Boundary

The live hardware WebGPU receipt remains deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry
dzn, launch a hardware browser, weaken a receipt, modify a result verdict, or claim live pixels.
