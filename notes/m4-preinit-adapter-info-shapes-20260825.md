<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 WM-worker adapter-info shape contract

## Outcome

The shipping WM-worker preinit contract now executes the current
`GPUAdapterInfo.isFallbackAdapter` shape, the legacy `GPUAdapter.isFallbackAdapter` shape,
both conflicting-precedence shapes, and an unknown-status shape. The current field wins every
conflict, exact `true` alone enters the diagnostic fallback path, and unknown status stays on the
strict validation path.

The acceptance-critical `requestAdapter()` census is now covered at all three sites:

- `platform_web/shell/wgpu-preinit-worker.js` — shipping device/presentation preinit;
- `sandbox/m8-wasm-split/capture_blender_profile.mjs` — strict CAPTURE profile producer;
- `sandbox/m8-launch-gate/runtime_evidence.mjs` — shared M5-M8 runtime-evidence producer.

Other repository-local direct adapter requests are diagnostics and do not bind a profile or
milestone receipt. No acceptance rule or software-token rejection changed.

## Change and fail-closed controls

Commit `b41258d` expands the production-shaped worker model from 14 to 19 cases. Its integrated
self-check also rewrites the exact shipping source three ways and requires every mutation to fail:

1. read only the retired adapter property;
2. give the retired property precedence over `GPUAdapterInfo`;
3. treat an unknown fallback status as diagnostic fallback.

The mutations execute the same full pre-main presentation transaction as the positive cases, so
they cover the fallback adapter's post-configuration promise failure as well as classification.

## Evidence

- Exact Node 22.16.0 CAPTURE producer self-check: 14 positive / 23 negative
  (`20260825T125155-1296144`).
- Exact Node 22.16.0 shared runtime-evidence self-check: seven adapter-consuming producers and
  35 negative controls (`20260825T125155-1296145`).
- Integrated native/wasm32 presentation, callback, device-loss, source, and mutation matrix:
  GREEN (`20260825T125005-1292581`).
- Exact REUSE 6.2.0 covers 2,529/2,529 files (`20260825T125343-1296998`).
- Required M4 remains honestly RED only at the unsupported historical binding schema
  (`20260825T125051-1294103`). Container-backed regression keeps M0 6/6 GREEN and M1-M8 at their
  existing strict receipt/product/browser/hardware/release boundaries
  (`20260825T125100-1294217`).

No browser was launched and no adapter, profile, split product, pixel, receipt, result promotion,
deferral, tolerance, golden, blacklist, or milestone promise changed. Mesa dzn and Windows Edge
were not attempted, WSL was not restarted, and the live blocker remains **no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**.
