<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU texture/view error-object contract — 2026-08-23

## Outcome

Commit `8443017` closes the texture/view slice of the R6 GPU resource error-object audit. Root
texture creation now reserves an ordered frame-epoch gate before `CreateTexture`; a shared
accepted/rejected status travels with every copied subresource range, so a browser rejection
invalidates the root and all Blender texture views without a callback retaining their wrappers.
Standalone `CreateView` calls reserve the same ordered gate. Views created while
`command_encode_submit_scoped` is active stay inside that enclosing validation/OOM/internal scope,
which rejects the complete command before submission. The backend-private empty-framebuffer
texture and view publish as one scoped cache value, preserving an accepted old pair while a resize
is pending and clearing only pending state after rejection.

This does not close resource creation as a whole. Bind-group/layout, pipeline-layout, and pipeline
creation/cache publication remain open under `AUDIT-R6-GPU-RESOURCE-ERROR-OBJECT-CONTRACT`.

## Evidence

- The unchanged canonical source fails the new exact texture/view scope guard before evidence
  allocation (`20260823T121056-2768566`).
- Native and wasm32 pass 25 byte-identical integrated texture contracts, including seven new
  root/view gate and atomic-pair cases, at 2,650 bytes SHA-256 `0631052df84e` with source SHA-256
  `1dc524f2f128` (`20260823T122603-2780980`). Ambient Node 25.1.0 rejects before creating its
  fresh evidence directory (`20260823T122637-2782498`).
- The pinned-Dawn llvmpipe control builds and proves the exact shipping gates block real non-null
  invalid texture and texture-view objects, then proves the composite cache rejects a non-null
  invalid pair and publishes a clean retry (`20260823T121743-2772653`,
  `20260823T121756-2772773`). Its transcript says `SOFTWARE_CONTROL_NON_RECEIPT`; it binds no
  milestone or hardware claim.
- Numbered patch 0235 is 17,910 bytes at SHA-256 `9010364d1e27` and passes isolated application,
  reverse application, and live-byte round trips. The clean-pin canonical freeze has 257 paths and
  20,258 entries; its 1,719,151-byte patch is SHA-256 `a0090ef9981d`, and its live/replay manifests
  are byte-identical at SHA-256 `723219fa9fd0` (`20260823T122325-2778271`,
  `20260823T122904-2784664`). The optional full numbered-history diagnostic still encounters the
  pre-existing patch-0016 drift at series entry 15; it is diagnostic-only and does not weaken the
  authoritative canonical replay or the isolated 0235 round trip (`20260823T122825-2784229`).
- The real `blender_browser` relinks and ends exact locked no-work
  (`20260823T122654-2783293`, `20260823T122744-2783781`). OFF preflight binds the
  118,565,049-byte primary Wasm (`20260823T122751-2783874`), and final REUSE 6.2.0 is green for
  2,207/2,207 files.
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260823T123103-2786316`). Container-backed regression at `2026-08-23T12:31:37Z` keeps M0
  6/6 green while M1-M8 retain their existing strict-receipt, product, browser, run-label,
  hardware, and release boundaries. No gate result was promoted.

## Boundary

The live hardware WebGPU receipt remains deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry
dzn, launch the post-reboot Windows path, modify a result verdict, or claim live pixels.
