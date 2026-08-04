<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M1 Wave-2 — P2 (kernel hub) result

Date: 2026-08-03. Owner: build-deps worker (P2).
Protocol: shared 5-worker tree, upstream NOT restored (driver restores at wave end),
edits scoped to P2 dirs only, ninja via `scripts/ninja-locked.sh`, patches 0120–0139.

## Result: 6/6 target archives GREEN (wasm32)

(blenkernel/depsgraph/animrig/blentranslation were already green from M1.13/14.)

| target | archive | bytes | members | fix |
|---|---|---|---|---|
| bf_blenloader_core | libbf_blenloader_core.a |     5,298 |  5 | none |
| bf_blenloader      | libbf_blenloader.a      | 2,380,872 | 29 | none (readfile — .blend critical path) |
| bf_functions       | libbf_functions.a       | 3,405,018 | 18 | none |
| bf_asset_system    | libbf_asset_system.a    |   660,464 | 19 | **patch 0120** |
| bf_simulation      | libbf_simulation.a      |   114,892 |  6 | none |
| bf_shader_fx       | libbf_shader_fx.a       |    50,618 | 13 | none |

5 of 6 built with zero fixes. blenloader (the high-value readfile lib) compiled
clean to wasm — no LP64/fenv/mmap surprises, matching the recon prediction.

## Error classes hit (1)

### Class-4 — WITH_PYTHON=OFF dead-path bug (1 TU) — FIXED (patch 0120)
`asset_system/intern/disk_file_hash_service.cc`: both `DiskFileHashService::get_hash`
and `::file_matches` have a `#if WITH_PYTHON ... #else ...` split. The `#else`
(no-Python) branch calls `UNUSED_VARS(C, hash_algorithm[, hexhash, size_in_bytes])`
but neither method takes a `C` (bContext) parameter — a stray copy-paste identifier
`error: use of undeclared identifier 'C'` (lines 103, 174). Never compiled when
WITH_PYTHON=ON, so the native oracle (Python ON) is byte-identical; the WITH_PYTHON
`#else` is the equivalent guard. Fix drops the bogus `C`. Not a wasm-specific issue
per se — it's a latent upstream bug that only M1's WITH_PYTHON=OFF surfaces; other
no-Python configs would hit it too.

## Notes
- No shared-header edits needed (no `editors/include` / cross-dir seam touched).
- No cmake reconfigure triggered by my work.
- `scripts/ninja-locked.sh` serialized cleanly against concurrent workers (waits
  observed, no `.ninja_log` corruption).
- Receipts: build 6-target (5 green, 1 fail) `ledger/buildlogs/20260804T015825.log`;
  asset_system green `ledger/buildlogs/20260804T020929.log`.
