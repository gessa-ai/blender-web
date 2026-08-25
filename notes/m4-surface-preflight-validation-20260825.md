<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4 deterministic surface preflight validation — 2026-08-25

## Outcome

Commit `7bc9916` closes `AUDIT-R10-M4-SURFACE-PREFLIGHT-VALIDATION`. The WM-worker no
longer treats the absence of an optional `uncapturederror` event after one event-loop turn as proof
that a presentation surface works. For every non-fallback or unknown-status adapter, publication
now requires a first surface texture/view, an opaque clear submitted inside validation,
out-of-memory, and internal error scopes, completed queue work, and a still-active device.

An exact browser-reported fallback adapter uses the same configure/acquire/clear/submit operation
without creating a post-configure WebGPU promise. That branch is labeled `fallback-diagnostic`,
cannot bind a receipt, and cannot claim strict validation. The current
`GPUAdapterInfo.isFallbackAdapter` boolean takes precedence; the retired adapter property remains
only as a legacy fallback. A missing status takes the strict path and therefore fails closed.

## Why the split is explicit

WebGPU's uncaptured-error event is optional and may be delayed or omitted, so event silence cannot
validate configuration. Error scopes and submitted-work completion provide the deterministic
strict boundary. This box can exercise only Chromium's fallback adapter: after canvas
configuration, its external Dawn Instance is invalidated when a WebGPU promise is created.
Readback-buffer `mapAsync()` reproduced `A valid external Instance reference no longer exists`;
bitmap and direct 2D-canvas readback alternatives returned transparent black. Those experiments
rule out a truthful strict software receipt rather than justify weakening the hardware path.

## Evidence

- Fail-first predecessor with synchronous telemetry rejects before acceptance because it never
  submits presentation work: `20260825T092624-1090397`.
- Rejected software readback alternatives: buffer mapping
  `20260825T093054-1095399`, bitmap transfer `20260825T093552-1099691`, and direct canvas readback
  `20260825T093742-1101674`.
- Final 14-case worker model passes strict completion, exact current-spec fallback selection,
  synchronous/delayed/omitted telemetry, cleanup, partial publication, and device-loss controls:
  `20260825T094255-1105264`. The exact staged implementation independently passes the same model:
  `20260825T095128-1114277`.
- Canonical native/Wasm integrated parity remains 4,813 identical bytes at SHA-256
  `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`:
  `20260825T094436-1107229`.
- Locked windowed relink and exact no-work rebuild: `20260825T094259-1105300` and
  `20260825T094609-1109251`; OFF product preflight: `20260825T094641-1110402`.
- Headed COOP/COEP fallback diagnostic reaches `state=running`, publishes one diagnostic
  presentation, and reports no stage-1/import failure: `20260825T094552-1108757`. Its later C++
  path reports `device_lost=1` after one tick, so the separate sustained-WM-liveness audit item
  remains open; this run is not a boot-liveness, pixel, adapter, or hardware receipt.
- Canonical-only replay stays green at pin `fbe6228777e7`, 252 patches, and snapshot SHA-256
  `4e65ce97d395`: `20260825T094818-1112105`.
- Required M4 remains honestly RED at the unchanged unsupported historical binding schema.
  Authoritative container-backed regression at `2026-08-25T09:48:01Z` keeps M0 6/6 GREEN while
  M1-M8 retain their strict existing receipt, product, browser, hardware, and release boundaries.

No adapter, profile, split product, receipt, result promotion, dependency, deferral, tolerance,
golden, blacklist, or promise changed. The s7 blocker remains `no conformant hardware Vulkan ICD
in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`; dzn and Windows were not attempted, and
WSL was not restarted.
