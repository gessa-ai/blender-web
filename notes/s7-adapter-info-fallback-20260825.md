<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# s7 GPUAdapterInfo fallback-status repair — 2026-08-25

## Outcome

Commit `30fa865` repairs the strict CAPTURE producer's live hardware-adapter probe. Current
Chromium exposes `isFallbackAdapter` on `GPUAdapterInfo`; the producer had read only the retired
`GPUAdapter` location and therefore flattened every current adapter to an absent fallback status.
The downstream classifier correctly requires literal `false`, so that extraction defect rejected
all hardware before immutable CAPTURE evidence allocation.

The probe now prefers a boolean `adapter.info.isFallbackAdapter` and falls back to the legacy
`adapter.isFallbackAdapter` location only when the current field is absent. The receipt schema and
both independent profile-union/APPLY consumers remain unchanged: accepted hardware still records
literal `false`, while true, absent, malformed, masked, or software identities remain rejected.

## Verification

- The exact predecessor expression returns `null` for an Apple/Metal-shaped
  `GPUAdapterInfo.isFallbackAdapter=false` fixture and fails closed
  (`20260825T074013-1001796`).
- The executable producer self-check now drives the real page-evaluation callback with
  current-spec, legacy, and conflicting-precedence adapter shapes. It passes 14 positive and 23
  negative checks; a current-spec true-fallback fixture is explicitly rejected
  (`20260825T073716-998966`).
- Both immutable receipt consumers pass four positive controls and reject all 29 mutations, and
  the complete two-phase source contract reports PASS in the same focused run
  (`20260825T073716-998966`).
- Final pinned REUSE 6.2.0 covers 2,496/2,496 files (`20260825T074143-1003166`).
- The required M8 scope remains honestly RED at its existing 25 technical-release boundaries
  (`20260825T073921-1000718`). Container-backed regression restores M0 to 6/6 GREEN while M1-M8
  retain their existing strict receipt, artifact, product, browser, hardware, and release
  boundaries (`20260825T073926-1000810`).

## Boundary

This repair creates no adapter, CAPTURE profile, union, APPLY shard, live receipt, result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone promise. A
software/fallback adapter still binds nothing. Live proof remains externally blocked by
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`; dzn
and Windows Edge were not attempted, and WSL was not restarted.
