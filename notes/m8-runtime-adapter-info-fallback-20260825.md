<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 runtime GPUAdapterInfo fallback-status repair — 2026-08-25

## Outcome

Commit `fe9ef91` repairs the shared M5–M8 launch-runtime hardware probe. The s7 CAPTURE producer
already read the current `GPUAdapterInfo.isFallbackAdapter` field, but the later runtime-evidence
producer still read only the retired `GPUAdapter.isFallbackAdapter` location. Current Chromium
hardware could therefore pass s7 and then be rejected as `fallback-status-absent` by every final
browser lane.

The runtime probe now prefers a boolean current-spec field and retains the legacy location only as
a compatibility fallback. The strict normalized receipt and consumer remain unchanged: hardware
must still report literal `false`, provide an unmasked identity, and match no software token.

## Verification

- Before the edit, the exact production callback rejected an Apple/Metal-shaped current-spec
  fixture with `reason=fallback-status-absent`.
- The exact committed producer self-check executes current-spec, legacy, conflicting-precedence,
  true-fallback, and SwiftShader raw adapter shapes through the page callback
  (`20260825T123659-1280263`).
- The independent M8 consumer contract and technical-receipt mutation suite remain green
  (`20260825T123659-1280264`, `20260825T123659-1280265`).
- REUSE 6.2.0 covers 2,528/2,528 files (`20260825T124020-1283435`).
- Container-backed regression restores M0 to 6/6 GREEN while the downstream scopes retain their
  existing strict receipt, split-product, browser, hardware, and release boundaries
  (`20260825T123736-1280927`).

## Boundary

This fix creates no adapter, profile, union, APPLY shard, browser receipt, result promotion,
dependency decision, deferral, tolerance, golden, blacklist, or promise. Software/fallback still
binds nothing. Live proof remains externally blocked by `no conformant hardware Vulkan ICD in
WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`; dzn and Windows Edge were not attempted, and
WSL was not restarted.
