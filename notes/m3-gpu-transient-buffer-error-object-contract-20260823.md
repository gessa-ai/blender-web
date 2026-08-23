<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU transient-buffer error-object contract — 2026-08-23

## Outcome

Commit `d7b7db1` closes the short-lived batch/immediate buffer slice of the R6 GPU resource
error-object audit. The five transient index, parameter, and vertex allocation sites now reserve
an ordered frame-epoch gate before `CreateBuffer`. A provisional handle may be used only for
CPU-side command encoding queued behind that gate. Completed validation, out-of-memory, and
internal scopes release accepted work; a literal null or non-null error object cancels the
dependent same-epoch queue work, while a later frame can recreate and retry. Callback state owns
the candidate and never captures the stack `Buffer` wrapper.

This does not close resource creation as a whole. Texture/view, bind-group/layout,
pipeline-layout, and pipeline creation/cache remain open under
`AUDIT-R6-GPU-RESOURCE-ERROR-OBJECT-CONTRACT`.

## Evidence

- The unchanged source fails the new exact transient-gate guard before evidence allocation
  (`20260823T113309-2729983`).
- Root and descendant native/wasm32 runs pass 28 byte-identical integrated contracts, including
  three transient gate cases and both callback completion orders, at 3,110 bytes SHA-256
  `eab4f0f40f0e` with source SHA-256 `c4adf6539172`
  (`20260823T114643-2745005`, `20260823T114716-2746255`). The complete buffer contract remains
  byte-identical at 1,515 bytes SHA-256 `8ab98c2bf88c` (`20260823T114045-2738347`). Ambient Node
  22.22.1 rejects before creating its fresh evidence directory (`20260823T114423-2742778`).
- The pinned-Dawn llvmpipe control builds and proves the exact shipping gate blocks dependent work
  after a real non-null invalid buffer, then releases a clean next-epoch retry
  (`20260823T114339-2741514`, `20260823T114352-2741629`). Its transcript says
  `SOFTWARE_CONTROL_NON_RECEIPT`; it binds no milestone or hardware claim.
- Numbered patch 0234 is 17,937 bytes at SHA-256 `e77d93f7bd0f` and passes isolated application,
  reverse application, whitespace, and live-byte round trips. The clean-pin canonical freeze has
  257 paths and 20,258 entries; its 1,713,762-byte patch is SHA-256 `685b55cb283f`, and its
  live/replay manifests are byte-identical at SHA-256 `b7f08ecf1c43`
  (`20260823T113914-2735550`, `20260823T114242-2741010`).
- The real `blender_browser` relinks and ends exact locked no-work
  (`20260823T114106-2739228`, `20260823T114150-2739672`). OFF preflight binds the
  118,538,224-byte primary Wasm (`20260823T114209-2739846`), and final post-record REUSE 6.2.0
  is green for 2,205/2,205 files (`20260823T115334-2753462`).
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260823T114750-2748195`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict-receipt, product, browser, run-label, hardware, and release boundaries
  (`20260823T114807-2748349`). No gate result was promoted.

## Boundary

The live hardware WebGPU receipt remains deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry
dzn, launch the post-reboot Windows path, modify a result verdict, or claim live pixels.
