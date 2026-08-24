<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 windowed compositor registration cut — 2026-08-24

> **Historical rejected experiment.** `AUDIT-R9-M8-FIDELITY-RESTORE` reverted this cut and
> retired its size-only deferral. The measurements below remain audit evidence; they do not
> describe the shipping windowed profile. See `notes/m8-registration-fidelity-restore-20260824.md`.

## Outcome

The windowed browser profile no longer calls the one generated registration root for concrete
compositor nodes. Patch 0250 leaves `register_node_tree_type_cmp()` live and does not touch
compositor DNA, RNA, the blend loader, or render/file data structures. Native and headless Wasm
builds retain Blender's stock registration path through `WITH_BLENDER_WEB_COMPOSITOR=ON`.

This removes 1,544,869 raw Wasm bytes and exactly 236,893 Brotli-q11 bytes from the current
windowed module. The resulting Wasm is 23,663,294 q11 bytes. M8 therefore remains honestly RED:
the Wasm alone is still 8,663,294 bytes over LAUNCH.md's complete 15 MB interactive-payload
budget before stage-0 data.

## Fail-first and implementation boundary

The focused verifier rejected the unchanged tree before evidence allocation because patch 0250
and its guarded boundary were absent
(`ledger/buildlogs/20260824T052112-3763860.log`).

The accepted patch leaves all compositor sources and libraries in the build. It guards only the
generated `register_compositor_nodes()` call in `register_nodes()`, allowing the shipped linker's
function-level dead-code elimination to collect the now-unreachable concrete-node closure. The
separate compositor tree-type registration remains unconditional. The numbered patch touches only
`source/blender/nodes/CMakeLists.txt` and
`source/blender/nodes/intern/node_register.cc`; it cannot remove DNA, RNA, blenloader, compositor
tree data, or any generic `.blend` load path.

The option defaults ON. Only `WITH_BLENDER_WEB_WINDOWED` forces it OFF, while the `bf_nodes`
CMake fallback preserves stock registration for generic native and headless configurations.

## Size evidence

Both rows use the same pinned emsdk Node 22.16.0 `zlib.brotliCompressSync` call with
`BROTLI_PARAM_QUALITY=11`; q5 is retained only as a faster independent diagnostic.

| module | SHA-256 | raw bytes | q5 bytes | q11 bytes |
|---|---|---:|---:|---:|
| patch-0249 baseline | `e6cfb7adebecdb3b9616bdb8a1dbf639711b8229fee88cd8c10bb983bc5094dd` | 113,980,889 | 28,227,396 | 23,900,187 |
| patch-0250 candidate | `baaa23d1c016cb007ae785113b8776a205443848dd03c30dd22946b9461e188e` | 112,436,020 | 27,981,336 | 23,663,294 |
| reduction | — | **1,544,869** | **246,060** | **236,893** |

The baseline and candidate receipts are
`ledger/buildlogs/20260824T051654-3760833.log` and
`ledger/buildlogs/20260824T052228-3765224.log`.

## Verification

- The real locked `blender_browser` relink and two exact no-work checks are GREEN
  (`ledger/buildlogs/20260824T052141-3764808.log`,
  `ledger/buildlogs/20260824T052652-3768686.log`,
  `ledger/buildlogs/20260824T052656-3768716.log`).
- Headless Wasm and native `bf_nodes` both build GREEN. Their generated compile rules contain
  `WITH_BLENDER_WEB_COMPOSITOR`; the windowed rule does not
  (`ledger/buildlogs/20260824T052613-3768132.log`,
  `ledger/buildlogs/20260824T052628-3768368.log`).
- OFF product preflight binds 649,162 JavaScript bytes, 112,436,020 Wasm bytes, and 167,143,248
  data bytes (`ledger/buildlogs/20260824T053231-3773919.log`).
- The focused verifier binds the two distinct registration calls, default-ON and forced-OFF
  configuration, the two-file patch boundary, six rejecting mutations, and an isolated exact
  reverse/forward patch round-trip. Patch 0250 is SHA-256
  `f7be2c5058a084305cebc2c868059a0a7c6291f50dcaa3373fa6ac9c8a2d569b`
  (`ledger/buildlogs/20260824T052600-3767240.log`,
  `ledger/buildlogs/20260824T052941-3770860.log`).
- The canonical freezer independently replays 20,258 entries across 261 paths. The frozen patch
  is SHA-256 `0d40edd945545d894c456adaa406737ae99abc3cd6b70358254db7f814e563a7`,
  and canonical replay is GREEN (`ledger/buildlogs/20260824T052716-3768876.log`,
  `ledger/buildlogs/20260824T052805-3769516.log`).
- Pinned REUSE 6.2.0 is GREEN for 2,265/2,265 files
  (`ledger/buildlogs/20260824T053247-3774062.log`). Required M8 remains RED with its existing 25
  technical failures. Final container-backed regression at 2026-08-24T05:30:45Z restores M0 to
  6/6 GREEN while M1-M8 retain their existing strict-receipt, product, browser, run-label,
  hardware, and release boundaries.

## Product boundary

`ledger/deferred.json` records the user-visible omission as
`feature-off-compositor-execution-windowed`. The browser retains compositor tree data and generic
`.blend` loading, but concrete compositor nodes are not registered and compositor execution is
not available. Use desktop Blender to bake compositing into source images or final render results,
and disable scene compositing for browser workflows.

Re-enable the feature and rerun all size/runtime receipts if a truthful accepted-hardware profile
split later clears the 15 MB bar without this cut. No browser, adapter, profile, split product, or
accepted receipt was created. Mesa dzn and the Windows path were not attempted, and WSL was not
restarted.
