<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 framebuffer layered-load commit - 2026-08-23

## Outcome

Patch 0229 (`1ba3e94`) preserves an explicit all-layer framebuffer load clear until every selected
layer's checked clear command reaches the queue. View, encoder, render-pass, or finished-command-
buffer failure now returns through the full-clear helper chain without changing the pending
`GPU_LOADACTION_CLEAR`; the next draw can retry instead of loading attachment contents that were
never cleared.

## Diagnosis and implementation

`materialize_layered_loadstore_clears()` previously called a `void` full-clear wrapper and then
unconditionally changed the attachment action to `GPU_LOADACTION_LOAD`. The nested clear code
already rejected invalid WebGPU command resources, but that result could not reach the state
transition, so any rejected attempt permanently consumed the one-shot clear.

The full and scissored clear helper chain now propagates success. The materializer wraps the full
clear in `framebuffer_load_action_commit_if_valid()`, which changes the pending action only after
the complete callback succeeds. A partially submitted attempt is safe to retry: earlier layers
may be cleared again, but the action remains pending until every selected layer succeeds.

## Evidence

- The pre-change integrated baseline is green (`20260823T071626-2511220`). After the new contract
  was written first, unchanged shipping source rejects before compilation or evidence allocation
  at the absent commit helper (`20260823T071845-2512750`).
- Native and wasm32 targets compile independently (`20260823T072140-2515556`,
  `20260823T072150-2515616`) and both direct executions pass 25 contracts, including two exact
  fail-first/retry load-action cases (`20260823T072202-2515926`,
  `20260823T072202-2515927`). The final orchestrated native/wasm32 outputs are byte-identical at
  2,666 bytes, SHA-256
  `3ff36625098a62b7d649ef6fc10a601190c48419f055117c1a23bdc2649d64ae`, with 25 shipping inputs
  at SHA-256 `60b7e800c8397dc5089d0745ad2115abb1a006d9731bcd36eabcc8387e935bf9`
  (`20260823T072615-2518779`). Ambient Node v22.22.1 is rejected before its requested evidence
  directory exists (`20260823T072636-2520437`).
- The canonical freezer retains 257 paths and 20,258 live/replay entries. The 1,666,054-byte
  canonical patch is SHA-256
  `81d3dbb8724a9e257a53877f9e5f55e6cc156b539314effa86e89e8ee4bafd23`, and both manifests are
  SHA-256 `9a97e0d2bef0fcb841235f1dcdaecd133d7cdaa2e224d55b9b8bfc59174cc14c`
  (`20260823T072514-2518039`). Canonical-only replay is green
  (`20260823T072602-2518590`). Numbered patch 0229 is 12,129 bytes at SHA-256
  `8682d39b786a9c28e6e3d503df0f7d8f69912e0f6cce754a53aea0621a511856`; isolated reverse and
  forward check/apply cycles are green (`20260823T072818-2521844`,
  `20260823T072822-2521914`, `20260823T072826-2521976`, `20260823T072830-2522037`).
- The real `blender_browser` recompiles the affected GPU backend and relinks, then reaches exact
  locked-Ninja no-work (`20260823T072655-2521074`, `20260823T072738-2521475`). OFF preflight
  binds the 118,079,844-byte primary Wasm (`20260823T072752-2521584`).
- Final REUSE 6.2.0 is green for all 2,190 files (`20260823T073404-2526746`).
- Required M3 remains red only for the absent fresh strict candidate
  (`20260823T072930-2523361`). Container-backed regression restores M0 6/6 green while M1-M8
  retain their existing strict-receipt, split-product, browser, run-label, hardware, and
  independent M8 performance boundaries (`20260823T073125-2524256`).

## Boundary

This is device-free command/state proof. It creates no WebGPU instance, accepted adapter, device,
view, encoder, pass, command buffer, submission, draw, pixel, browser receipt, profile, or split
product. Live proof remains blocked by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships
none; Mesa dzn rejected by Dawn)**. No result promotion, dependency decision, deferral, tolerance,
golden, blacklist, or milestone promise changed.
