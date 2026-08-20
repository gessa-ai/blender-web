<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 Workbench producer portability - 2026-08-20

## Outcome

The current-tree Workbench evidence producer and scorer now run their hermetic
self-checks from the ornith-lab checkout and from a descendant working directory.
They no longer execute against `/Users/paws/blender-web` or the former shared
Playwright installation.

This is producer readiness only. No browser matrix was run and no M6, M4, split,
adapter, or GPU receipt was created. Section 7 of the migration runbook still
forbids capture while Chromium and Vulkan expose only a software adapter.

## Reproduced defects

- The scorer self-check failed while importing
  `/Users/paws/blender-web/sandbox/gpu-r35/score.py`:
  `ledger/buildlogs/20260820T181600-2353276.log`.
- The driver self-check failed before source transformation while opening
  `/Users/paws/blender-web/build-wasm-windowed-opt/bin/blender_browser.js`:
  `ledger/buildlogs/20260820T181608-2353314.log`.
- The driver attested five served shell files while the current aggregate M6
  verifier requires the six-file set that includes `diagnostics-bootstrap.js`.

## Repair

- `drive_workbench_case.mjs` derives the repository root from `import.meta.url`,
  derives source, shell, binary, and run roots from it, and restricts output to
  one safe immediate child of the immutable Workbench `runs/` directory.
- The retained r35 bridge remains byte-immutable. Its output-root and Playwright
  seams are transformed exactly once. Playwright resolution follows
  `BW_NODE_MODULES`, `NODE_PATH`, `.m4-node/node_modules`, then local
  `node_modules`; the old macOS module root is not executable state.
- Self-check mode uses non-evidence artifact placeholders so producer validation
  is possible before s7. A real run still reads and hash-binds the exact JS,
  primary Wasm, deferred Wasm, and data files before browser launch, so the
  current OFF-mode product fails closed rather than becoming evidence.
- `score_workbench.py` derives its legacy scorer, decoder, and pinned OCIO paths
  from its own file location.
- Served-shell attestation now includes `diagnostics-bootstrap.js`, matching the
  current aggregate verifier exactly.

## Evidence

- Driver self-check from the repository root:
  `ledger/buildlogs/20260820T182518-2360689.log`.
- Driver self-check from `sandbox/`, proving current-directory independence:
  `ledger/buildlogs/20260820T181838-2354880.log`.
- Scorer self-check under the native CPython 3.13 host tool:
  `ledger/buildlogs/20260820T182103-2356570.log`.
- Aggregate M6 verifier self-check, including the exact six-file shell contract:
  `ledger/buildlogs/20260820T182103-2356573.log`.
- Matrix-runner shell syntax:
  `ledger/buildlogs/20260820T182103-2356579.log`.
- REUSE compliance:
  `ledger/buildlogs/20260820T182518-2360690.log`.
- The required container-backed regression at 2026-08-20T18:24Z keeps M0
  6/6 GREEN and M1-M6 honestly RED. M6 now reaches the intended named boundary,
  `missing Workbench result matrix`; M5 remains blocked by the absent deferred
  APPLY shard, and M1-M4 retain their existing strict-manifest/adapter bindings.

The next Workbench action is unchanged: after s7 proves a hardware WebGPU
adapter and the CAPTURE-to-APPLY sequence completes, install pinned Playwright
1.61.1, allocate a fresh immutable matrix label, and run all 20 rows. A
llvmpipe/software run binds nothing.
