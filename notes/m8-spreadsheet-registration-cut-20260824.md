<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 windowed Spreadsheet editor registration cut — 2026-08-24

> **Historical rejected experiment.** `AUDIT-R9-M8-FIDELITY-RESTORE` reverted this cut and
> retired its size-only deferral. The measurements below remain audit evidence; they do not
> describe the shipping windowed profile. See `notes/m8-registration-fidelity-restore-20260824.md`.

## Outcome

The windowed browser profile no longer registers the Spreadsheet editor space. Patch 0252 guards
only `spreadsheet::register_spacetype()`. Spreadsheet DNA/RNA, generic `.blend` loading,
geometry-node data paths, and the editor library remain compiled; native and headless Wasm builds
retain Blender's stock registration path through `WITH_BLENDER_WEB_SPREADSHEET=ON`.

This removes 279,672 raw Wasm bytes and exactly 39,919 Brotli-q11 bytes from the current windowed
module. The resulting Wasm is 23,548,942 q11 bytes. M8 therefore remains honestly RED: the Wasm
alone is still 8,548,942 bytes over LAUNCH.md's complete 15 MB interactive-payload budget before
stage-0 data.

## Fail-first and implementation boundary

The focused verifier rejected the unchanged tree before evidence allocation because patch 0252
and its guarded boundary were absent
(`ledger/buildlogs/20260824T060502-3802020.log`).

The accepted patch leaves `bf_editor_space_spreadsheet`, `bf::nodes`, Spreadsheet DNA/RNA, and
all loader sources in the build. It guards only the central `space_api` registration call, allowing
the shipped linker's function-level dead-code elimination to collect the now-unreachable editor
closure. The numbered patch touches only
`source/blender/editors/space_api/CMakeLists.txt` and
`source/blender/editors/space_api/spacetypes.cc`; its focused gate rejects changes crossing the
retained makesdna, makesrna, blenloader, nodes, or geometry boundaries.

The option defaults ON. Only `WITH_BLENDER_WEB_WINDOWED` forces it OFF, while the `space_api`
CMake fallback preserves stock registration for generic native and headless configurations.

## Size evidence

Both rows use the same pinned emsdk Node 22.16.0 `zlib.brotliCompressSync` call with
`BROTLI_PARAM_QUALITY=11`; q5 is retained only as a faster independent diagnostic.

| module | SHA-256 | raw bytes | q5 bytes | q11 bytes |
|---|---|---:|---:|---:|
| patch-0251 baseline | `0c76b0f3702a691e33a72de541364a4c0ab3d65af98bea68c9f5f512a12af0d4` | 112,105,425 | 27,880,523 | 23,588,861 |
| patch-0252 candidate | `a4e0aeb47466113c943abecef5eb3a79362518fd0730966725ff844b0d55c97d` | 111,825,753 | 27,814,086 | 23,548,942 |
| reduction | — | **279,672** | **66,437** | **39,919** |

The baseline and candidate receipts are
`ledger/buildlogs/20260824T060520-3802331.log` and
`ledger/buildlogs/20260824T060947-3805488.log`.

## Verification

- The real locked `blender_browser` relink and exact no-work check are GREEN
  (`ledger/buildlogs/20260824T060900-3805101.log`,
  `ledger/buildlogs/20260824T062324-3816075.log`).
- Headless Wasm and native `bf_editor_space_api` both build GREEN. Their generated compile rules
  contain `WITH_BLENDER_WEB_SPREADSHEET`; the windowed rule does not
  (`ledger/buildlogs/20260824T062336-3816254.log`,
  `ledger/buildlogs/20260824T062336-3816258.log`).
- Root and descendant focused runs bind the single registration call, default-ON and forced-OFF
  configuration, retained editor/nodes libraries, the exact two-file boundary, seven rejecting
  mutations, and an isolated exact reverse/forward patch round-trip. Patch 0252 is SHA-256
  `bcf7907e52f4ed5a4b378e16c0c98fba0f0f37d53a499c581ccd4ba5e74a8ad5`
  (`ledger/buildlogs/20260824T062324-3816061.log`,
  `ledger/buildlogs/20260824T062324-3816060.log`).
- The canonical freezer independently replays 20,258 entries across 261 paths. The frozen patch
  is SHA-256 `5d721e623db2bc5726541970008021783b825f7ecbb5b602781c22a705f62475`,
  and its manifest is SHA-256
  `c407b19941bb8068cfdec161b3cb8906c0229c0d11faf904a341b20f8bb818b0`
  (`ledger/buildlogs/20260824T061411-3808813.log`,
  `ledger/buildlogs/20260824T062324-3816066.log`,
  `ledger/buildlogs/20260824T062336-3816252.log`).
- OFF product preflight binds 647,701 JavaScript bytes, 111,825,753 Wasm bytes, and 167,143,248
  data bytes (`ledger/buildlogs/20260824T061544-3809860.log`).
- Pinned REUSE 6.2.0 is GREEN for 2,271/2,271 files
  (`ledger/buildlogs/20260824T062345-3816445.log`).
- Required M8 remains RED at its unchanged 25 technical release boundaries
  (`ledger/buildlogs/20260824T062356-3817339.log`). Container-backed regression restores M0 to
  6/6 GREEN while M1-M8 retain their existing strict-receipt, product, browser, run-label,
  hardware, and release boundaries (`ledger/buildlogs/20260824T062402-3817416.log`).

## Product boundary

`ledger/deferred.json` records the user-visible omission as
`feature-off-spreadsheet-editor-windowed`. The browser retains Spreadsheet data/RNA and generic
`.blend` loading, but does not expose the Spreadsheet editor. Use desktop Blender to inspect
geometry-node attributes in a Spreadsheet before continuing launch-tier geometry-node and mesh
workflows in the browser.

Re-enable the feature and rerun all size/runtime receipts if a truthful accepted-hardware profile
split later clears the 15 MB bar without this cut. No browser, adapter, profile, split product, or
accepted receipt was created. Mesa dzn and the Windows path were not attempted, and WSL was not
restarted.
