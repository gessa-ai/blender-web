<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU shader/pipeline error-object contract — 2026-08-23

## Outcome

Commit `46a1eb0` closes the remaining shader-module and render/compute-pipeline slice of the R6
GPU resource error-object audit. Shader finalization now retains final WGSL as CPU retry state and
publishes the complete required module set only after validation, out-of-memory, and internal
scopes settle. Draw and dispatch paths stop while modules are pending, retry rejected sets, and
never pass provisional or error modules into pipeline creation.

General render pipelines, specialization-keyed compute pipelines, context blit/depth pipelines,
framebuffer clear pipelines, and the indexed-fan pipeline use scoped caches with explicit pending
state. Accepted keys remain stable while rejected non-null candidates stay unpublished and retry.
The one-shot mipmap shader/pipeline pair instead reserves an ordered transient resource gate, so a
failed scope cancels dependent same-epoch command work. This completes the R6 GPU resource
error-object prerequisite; bind-group completeness and ordinary framebuffer load-action commit
remain separate queued findings.

## Evidence

- Root native/wasm32 pipeline runs pass 28 byte-identical contracts at 3,126 bytes SHA-256
  `4cd5289b1f56`, including atomic shader-module-set publication and distinct accepted/rejected
  pipeline keys (`20260823T133646-2844283`). The shader-frontend companion remains byte-identical
  at 965 bytes SHA-256 `8d0bca94a5c1` across 653 cases (`20260823T133711-2845568`). Both bind Dawn
  `36cf1fae`, emcc 6.0.5, and Node 22.16.0.
- The pinned-Dawn control rebuilds and proves real non-null invalid shader-module, render-pipeline,
  and compute-pipeline objects remain unpublished before clean retries
  (`20260823T133901-2847559`, `20260823T133910-2847619`). Its adapter is llvmpipe and its transcript
  says `SOFTWARE_CONTROL_NON_RECEIPT`; it binds no hardware, profile, pixel, or milestone claim.
- Numbered patch 0237 is 51,975 bytes at SHA-256 `83d81c71fafa` and passes isolated reverse and
  clean-forward applicability (`20260823T134129-2849600`, `20260823T134141-2849685`). The canonical
  replayer accepts all 257 paths (`20260823T134151-2849770`). A fresh clean-pin freeze independently
  reproduces the 1,726,246-byte canonical patch at SHA-256 `4646e6798398`; its 20,258-entry live and
  replay manifests are byte-identical at SHA-256 `027d0496583d`
  (`20260823T134521-2853697`).
- The real optimized `blender_browser` rebuild completes after the 13-file source change
  (`20260823T133118-2839311`) and ends exact locked no-work
  (`20260823T134217-2849974`). OFF preflight binds the 118,697,864-byte primary Wasm at SHA-256
  `1862954de54b` (`20260823T134245-2850320`).
- Required M3 remains honestly red at `2026-08-23T13:44:13Z` only for the absent fresh strict
  candidate. Container-backed regression at the same timestamp restores M0 6/6 green while M1-M8
  retain their existing strict-manifest, split-product, browser, run-label, hardware, and release
  boundaries. No gate result was promoted.
- Final REUSE 6.2.0 is green for all 2,211 tracked files
  (`20260823T134939-2856550`).

## Boundary

The live hardware WebGPU receipt remains deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry
dzn, launch the post-reboot Windows path, modify a result verdict or deferral, weaken a receipt, or
claim live pixels.
