<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 windowed Clip editor registration cut — 2026-08-24

## Outcome

The windowed browser profile no longer registers the Clip/Motion Tracking editor space or its
operator macros. Patch 0253 guards only `ED_spacetype_clip()` and
`ED_operatormacros_clip()`. MovieClip data, DNA/RNA, generic `.blend` loading, shared
image/movie paths, and the editor library remain compiled; native and headless Wasm builds retain
Blender's stock registration path through `WITH_BLENDER_WEB_CLIP=ON`. The web configuration already
has `WITH_LIBMV=OFF`.

This removes 128,010 raw Wasm bytes and exactly 33,048 Brotli-q11 bytes from the current windowed
module. The resulting Wasm is 23,515,894 q11 bytes. M8 therefore remains honestly RED: the Wasm
alone is still 8,515,894 bytes over LAUNCH.md's complete 15 MB interactive-payload budget before
stage-0 data.

## Fail-first and implementation boundary

The focused verifier rejected the unchanged tree before evidence allocation because patch 0253
and its guarded boundary were absent
(`ledger/buildlogs/20260824T063215-3824440.log`).

The accepted patch leaves `bf_editor_space_clip`, MovieClip DNA/RNA, blenkernel data, loader
versioning, and all `space_clip` implementation sources intact. It guards only the two central
`space_api` registration calls, allowing the shipped linker's function-level dead-code elimination
to collect their otherwise unreachable editor closure. The numbered patch touches only
`source/blender/editors/space_api/CMakeLists.txt` and
`source/blender/editors/space_api/spacetypes.cc`; its focused gate rejects edits crossing the
retained data, loader, kernel, or editor implementation boundaries.

The option defaults ON. Only `WITH_BLENDER_WEB_WINDOWED` forces it OFF, while the `space_api`
CMake fallback preserves stock registration for generic native and headless configurations.

## Size evidence

Both rows use the same pinned emsdk Node 22.16.0 `zlib.brotliCompressSync` call with
`BROTLI_PARAM_QUALITY=11`; q5 is retained only as a faster independent diagnostic.

| module | SHA-256 | raw bytes | q5 bytes | q11 bytes |
|---|---|---:|---:|---:|
| patch-0252 baseline | `a4e0aeb47466113c943abecef5eb3a79362518fd0730966725ff844b0d55c97d` | 111,825,753 | 27,814,086 | 23,548,942 |
| patch-0253 candidate | `8ded9da0eb18d2652d2183bb6dc85fa5511366386c880ad682d09cbbcb477d12` | 111,697,743 | 27,771,586 | 23,515,894 |
| reduction | — | **128,010** | **42,500** | **33,048** |

The baseline and candidate receipts are
`ledger/buildlogs/20260824T060947-3805488.log` and
`ledger/buildlogs/20260824T063519-3826533.log`.

## Verification

- The real locked `blender_browser` relink and exact no-work check are GREEN
  (`ledger/buildlogs/20260824T063410-3825957.log`,
  `ledger/buildlogs/20260824T065104-3839430.log`).
- Headless Wasm and native `bf_editor_space_api` both build GREEN. Their generated compile rules
  contain `WITH_BLENDER_WEB_CLIP`; the windowed rule does not
  (`ledger/buildlogs/20260824T063816-3828682.log`,
  `ledger/buildlogs/20260824T063824-3829165.log`,
  `ledger/buildlogs/20260824T065104-3839425.log`).
- The focused verifier binds both distinct registration calls, default-ON and forced-OFF
  configuration, the retained editor library, seven rejecting mutations, the exact two-file
  boundary, and an isolated exact reverse/forward patch round trip. Patch 0253 is SHA-256
  `e922fa72919c3bc4f4ae6e559db086056ccf7466409b4aa37515a5da5e40827c`
  (`ledger/buildlogs/20260824T065104-3839425.log`).
- The canonical freezer independently replays 20,258 entries across 261 paths. The frozen patch is
  SHA-256 `96f45b07e7cc5620a2ab47ba6812f96ed0aebf5e0df61d441de496e408c6bf14`,
  and its manifest is SHA-256
  `c0c402c70dce6d16f25d7af27b4e4ee2146528e52206e95ff7de781bc8341031`
  (`ledger/buildlogs/20260824T064016-3829995.log`,
  `ledger/buildlogs/20260824T065104-3839426.log`).
- OFF product preflight binds 647,701 JavaScript bytes, 111,697,743 Wasm bytes, and 167,143,248
  data bytes (`ledger/buildlogs/20260824T064124-3831560.log`).
- Pinned REUSE 6.2.0 is GREEN for 2,274/2,274 files
  (`ledger/buildlogs/20260824T065104-3839437.log`).
- The deferral registry remains valid with unique IDs and binds the Clip omission as an M8
  deferral (`ledger/buildlogs/20260824T064429-3833545.log`).
- Required M8 remains RED at its unchanged technical-release boundaries
  (`ledger/buildlogs/20260824T065119-3839642.log`). Container-backed regression restores M0 to
  6/6 GREEN while M1-M8 retain their strict-receipt, split-product, browser, run-label, hardware,
  and release boundaries (`ledger/buildlogs/20260824T065123-3839695.log`).

## Product boundary

`ledger/deferred.json` records the user-visible omission as
`feature-off-clip-editor-windowed`. The browser retains MovieClip data/RNA and generic `.blend`
loading, but it does not expose the Clip editor or register its operator macros. Track footage and
author Clip/Motion Tracking state in desktop Blender before continuing launch-tier modeling,
geometry-node, animation, viewport, and small Cycles-CPU work in the browser.

Re-enable the feature and rerun all size/runtime receipts if a truthful accepted-hardware profile
split later clears the 15 MB bar without this cut. No browser, adapter, profile, split product, or
accepted receipt was created. Mesa dzn and the Windows path were not attempted, and WSL was not
restarted.
