<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 registration fidelity restoration — 2026-08-24

## Outcome

The default windowed profile again registers Blender's complete sculpt/paint, Grease Pencil,
compositor-node, VSE, Spreadsheet, Clip, NLA, and physics editor roots. The eight size-only
feature cuts from patches 0248-0255 were rejected and removed from the active patch stack as one
atomic correction. Their eight deferral rows and feature switches are retired, and their
non-composable focused verifiers are removed.

This restores the fidelity-first decision in `notes/decisions.md` D-10. A payload target is not a
hard platform blocker and cannot justify discarding native-visible behavior, especially when the
cuts did not close M8. The profile/split-product path remains the structural answer after an
accepted hardware profile exists.

## Rejected-history evidence

The original measurement notes remain tracked and are explicitly marked as historical rejected
experiments. Together the eight cuts saved 1,254,866 pinned Node 22.16.0 Brotli-q11 bytes but
left the Wasm alone 8,471,033 bytes above the complete 15 MB interactive budget before stage-0
data. The measurements remain useful evidence; none describes the current product.

| rejected cut | historical q11 reduction |
|---|---:|
| Sculpt/Paint | 489,232 bytes |
| Grease Pencil | 336,480 bytes |
| Compositor nodes | 236,893 bytes |
| VSE | 74,433 bytes |
| Spreadsheet | 39,919 bytes |
| Clip | 33,048 bytes |
| NLA | 31,745 bytes |
| Physics | 13,116 bytes |
| **Total** | **1,254,866 bytes** |

## Corrected boundary

- All 21 previously guarded registration calls are present exactly once and outside preprocessor
  conditions in the shipping postimage.
- `patches/blender_web.cmake` contains none of the eight cut switches or windowed forced-OFF
  defaults.
- The eight numbered patches no longer exist or appear in the active historical series, and the
  canonical squashed postimage no longer changes their four cut-only upstream paths.
- `ledger/deferred.json` contains none of the eight size-only deferrals. The remaining deferrals
  continue to require named technical or external blockers.
- One aggregate verifier replaces the eight serial single-patch round-trip checks and rejects
  missing/conditional registration, live flags, series entries, deferrals, patch/verifier residue,
  or unmarked history.

## Verification

- The isolated suffix experiment reversed patches 0255 through 0248 in their only safe order and
  recovered all 21 unconditional calls before the live postimage changed
  (`ledger/buildlogs/20260824T085705-3944511.log`). The live reverse then completed atomically
  (`20260824T085721-3944959`).
- The aggregate verifier first rejected the stale canonical snapshot, then passed 21 calls, eight
  retired patches, eight retired deferrals, and eight mutation controls after regeneration
  (`20260824T090227-3948075`, `20260824T090423-3950003`).
- The canonical freezer reproduced 20,258 live/replay entries across 257 changed paths. The
  1,757,756-byte squashed patch is SHA-256
  `b71513bc33c94987d3629a94d7f642d790a101e7624bf8a81f926fcff64cfa49`; both manifests are
  SHA-256 `161ddc65dd37103d6930c9c0f00333c374072e1486d593616ed324e5579c5f1f`
  (`20260824T090313-3948421`). Independent clean-pin replay passes all 257 paths with 224 active
  development-history patches (`20260824T090427-3950029`).
- The real locked `blender_browser` relink and exact no-work run are green
  (`20260824T090444-3950183`, `20260824T090609-3950853`). The restored Wasm is byte-identical to
  the saved pre-cut baseline: SHA-256
  `cace05581a682aa92ca4a94c7430cf4af30c3726de93bf4fe79b8fbc081a4380`, 118,772,391 raw bytes,
  and 24,725,899 pinned Node 22.16.0 Brotli-q11 bytes (`20260824T090624-3951772`). It is therefore
  honestly 9,725,899 bytes over the complete 15 MB budget before stage-0 data.
- Headless Wasm and native rebuilt both affected libraries and reached exact locked no-work
  (`20260824T090940-3953870`, `20260824T090959-3954165`,
  `20260824T091027-3954607`, `20260824T091030-3954637`). OFF preflight binds 657,928-byte
  JavaScript, 118,772,391-byte Wasm, and 167,143,248-byte data
  (`20260824T091035-3954686`).
- Pinned REUSE 6.2.0 is green for 2,270/2,270 files
  (`20260824T091116-3955520`). Required M8 remains red at its unchanged 25 technical boundaries
  (`20260824T091132-3955941`); container-backed regression restores M0 to 6/6 green while M1-M8
  retain their existing strict-receipt/product/browser/hardware/release boundaries
  (`20260824T091139-3956013`).

## Receipt boundary

This correction creates no browser, adapter, device, profile, split product, pixel, performance,
or milestone receipt. M8 remains red until its independent technical-release boundaries are
green or justified-and-deferred. Live hardware proof remains externally blocked by **no
conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. Mesa dzn
and the staged Windows path were not attempted, and WSL was not restarted.
