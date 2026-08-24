<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 windowed VSE editing registration cut — 2026-08-24

## Outcome

The windowed browser profile no longer registers the Video Sequence Editor space type or its
operator macros. Patch 0251 guards only those two editor registration roots. Strip DNA/RNA,
generic `.blend` loading, the core sequencer library, and shared render/data paths remain compiled;
native and headless Wasm builds retain Blender's stock registration path through
`WITH_BLENDER_WEB_VSE=ON`.

This removes 330,595 raw Wasm bytes and exactly 74,433 Brotli-q11 bytes from the current windowed
module. The resulting Wasm is 23,588,861 q11 bytes. M8 therefore remains honestly RED: the Wasm
alone is still 8,588,861 bytes over LAUNCH.md's complete 15 MB interactive-payload budget before
stage-0 data.

## Fail-first and implementation boundary

The focused verifier rejected the unchanged tree before evidence allocation because patch 0251
and its guarded boundary were absent
(`ledger/buildlogs/20260824T054124-3781625.log`).

The accepted patch leaves `bf_editor_space_sequencer` and `bf_sequencer` in the build. It guards
only `vse::ED_spacetype_sequencer()` and `vse::ED_operatormacros_sequencer()` in the central
`space_api` registration translation unit, allowing the shipped linker's function-level
dead-code elimination to collect the now-unreachable editor closure. The numbered patch touches
only `source/blender/editors/space_api/CMakeLists.txt` and
`source/blender/editors/space_api/spacetypes.cc`; it cannot remove sequencer DNA, RNA, blenloader,
or core strip/data sources.

The option defaults ON. Only `WITH_BLENDER_WEB_WINDOWED` forces it OFF, while the `space_api`
CMake fallback preserves stock registration for generic native and headless configurations.

## Size evidence

Both rows use the same pinned emsdk Node 22.16.0 `zlib.brotliCompressSync` call with
`BROTLI_PARAM_QUALITY=11`; q5 is retained only as a faster independent diagnostic.

| module | SHA-256 | raw bytes | q5 bytes | q11 bytes |
|---|---|---:|---:|---:|
| patch-0250 baseline | `baaa23d1c016cb007ae785113b8776a205443848dd03c30dd22946b9461e188e` | 112,436,020 | 27,981,336 | 23,663,294 |
| patch-0251 candidate | `0c76b0f3702a691e33a72de541364a4c0ab3d65af98bea68c9f5f512a12af0d4` | 112,105,425 | 27,880,523 | 23,588,861 |
| reduction | — | **330,595** | **100,813** | **74,433** |

The baseline and candidate receipts are
`ledger/buildlogs/20260824T054238-3782746.log` and
`ledger/buildlogs/20260824T054608-3785076.log`.

The reduction is smaller than the earlier whole-VSE symbol attribution because this cut
deliberately preserves core sequencer paths still reachable from Blender's data and render graph.
The measured 74,433-byte marginal wire reduction is nevertheless material and comes from the
smallest truthful editor-only boundary.

## Verification

- The real locked `blender_browser` relink and exact no-work check are GREEN
  (`ledger/buildlogs/20260824T054522-3784677.log`,
  `ledger/buildlogs/20260824T054855-3786756.log`).
- Headless Wasm and native `bf_editor_space_api` both build GREEN. Their generated compile rules
  contain `WITH_BLENDER_WEB_VSE`; the windowed rule does not
  (`ledger/buildlogs/20260824T054903-3786842.log`,
  `ledger/buildlogs/20260824T054911-3786924.log`,
  `ledger/buildlogs/20260824T054925-3787051.log`,
  `ledger/buildlogs/20260824T054928-3787081.log`,
  `ledger/buildlogs/20260824T054932-3787131.log`).
- Root and descendant focused runs bind both distinct registration calls, default-ON and
  forced-OFF configuration, the exact two-file boundary, six rejecting mutations, and an
  isolated exact reverse/forward patch round-trip. Patch 0251 is SHA-256
  `88be1320af2f61334c8ea4b5ee6c678dd73be097789f6c85a62b9bc69f68cbfd`
  (`ledger/buildlogs/20260824T054223-3782117.log`,
  `ledger/buildlogs/20260824T055331-3791516.log`).
- The canonical freezer independently replays 20,258 entries across 261 paths. The frozen patch
  is SHA-256 `688e6c7279550ae2e6deec22c6f46af1415e4058b5daa7c8d7460175edabef68`,
  its manifest is SHA-256
  `aca270e59a4ee36fdaa6c0b7434b33b655261f7aead72ef8d96baf3a1151ec19`, and root/descendant
  canonical replay is GREEN (`ledger/buildlogs/20260824T055014-3788217.log`,
  `ledger/buildlogs/20260824T055111-3788874.log`,
  `ledger/buildlogs/20260824T055336-3791623.log`).
- OFF product preflight binds 647,913 JavaScript bytes, 112,105,425 Wasm bytes, and 167,143,248
  data bytes (`ledger/buildlogs/20260824T055123-3789031.log`). Final pinned REUSE 6.2.0 is GREEN
  for 2,268/2,268 files (`ledger/buildlogs/20260824T055552-3793280.log`).
- Required M8 remains RED at its unchanged 25 technical release boundaries
  (`ledger/buildlogs/20260824T055256-3790525.log`). Container-backed regression restores M0 to
  6/6 GREEN while M1-M8 retain their existing strict-receipt, product, browser, run-label,
  hardware, and release boundaries (`ledger/buildlogs/20260824T055307-3790650.log`).

## Product boundary

`ledger/deferred.json` records the user-visible omission as
`feature-off-vse-editing-windowed`. The browser retains strip data and generic `.blend` loading,
but does not expose the Video Sequence Editor space or register its editing operators/macros.
Use desktop Blender to author or edit sequences and bake required video results before browser
workflows.

Re-enable the feature and rerun all size/runtime receipts if a truthful accepted-hardware profile
split later clears the 15 MB bar without this cut. No browser, adapter, profile, split product, or
accepted receipt was created. Mesa dzn and the Windows path were not attempted, and WSL was not
restarted.
