<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU bind-group/layout error-object contract — 2026-08-23

## Outcome

Commit `424c9f2` closes the bind-group/layout slice of the R6 GPU resource error-object audit.
Every transient bind group created before a command transaction now reserves an ordered
frame-epoch gate; a completed validation/OOM/internal error cancels the dependent same-epoch
command, while a clean later epoch can retry. Bind groups created inside an existing scoped
command remain covered by that complete command transaction.

Shader layout coverage and layout readiness are now separate states. A covered shader remains
explicit-layout-required while its bind-group-layout/pipeline-layout pair is pending or after a
rejection, so pipeline lookup cannot silently choose Dawn auto layout. The pair publishes
atomically through the shared scoped cache, pending requests deduplicate, and rejection preserves
the CPU layout entries for a clean retry. No asynchronous callback retains the shader wrapper.

This does not close resource creation as a whole. Shader-module and render/compute-pipeline
creation/cache publication remain open under `AUDIT-R6-GPU-RESOURCE-ERROR-OBJECT-CONTRACT`.

## Evidence

- The pre-change pinned-Dawn control remained green for its earlier eight-case audit but contained
  no transient-bind-group or layout-pair cases (`20260823T124626-2800157`,
  `20260823T124626-2800186`). Its llvmpipe adapter is explicitly
  `SOFTWARE_CONTROL_NON_RECEIPT`.
- Root and descendant-CWD native/wasm32 shader-frontend runs pass 653 cases byte-identically at
  965 bytes SHA-256 `8d0bca94a5c1` (`20260823T130000-2811351`,
  `20260823T131047-2822425`). The paired pipeline runs pass at 3,110 bytes SHA-256
  `eab4f0f40f0e`, including exact coverage for the three context helpers, indexed fan, both
  scissored-clear paths, explicit-layout readiness, and every enclosing command scope
  (`20260823T130049-2812778`, `20260823T131058-2822839`). Initial concurrent descendant replays
  exhausted the already-full `/tmp` tmpfs; the recorded disk-backed reruns above supersede those
  environmental failures without changing source or expectations.
- The post-change pinned-Dawn probe builds and proves a real non-null invalid transient bind group
  cancels dependent work, and a non-null invalid bind-group-layout/pipeline-layout pair remains
  unpublished before a clean retry (`20260823T130225-2815144`,
  `20260823T130239-2815243`). The transcript remains `SOFTWARE_CONTROL_NON_RECEIPT` and binds no
  milestone or hardware claim.
- Numbered patch 0236 is 22,107 bytes at SHA-256 `7e5112ad150b` and passes isolated
  reverse/forward/live-byte round trip (`20260823T131604-2828202`). The clean-pin canonical freeze
  has 257 paths and 20,258 entries; its 1,722,977-byte patch is SHA-256 `654271c672d4`, and its
  3,477,334-byte live/replay manifests are byte-identical at SHA-256 `cc7b5ee7c818`
  (`20260823T130635-2818199`, `20260823T130738-2818875`).
- The real `blender_browser` rebuild completes (`20260823T125307-2805300`) and both locked product
  checks end exact no-work (`20260823T131111-2823736`, `20260823T131115-2823818`). OFF preflight
  binds the 118,617,645-byte primary Wasm (`20260823T131119-2823888`), and exact REUSE 6.2.0 is
  green for all tracked files.
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260823T131152-2824204`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict-manifest, split-product, browser, run-label, hardware, and release
  boundaries (`20260823T131215-2824389`). No gate result was promoted.

## Boundary

The live hardware WebGPU receipt remains deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry
dzn, launch the post-reboot Windows path, modify a result verdict, or claim live pixels.
