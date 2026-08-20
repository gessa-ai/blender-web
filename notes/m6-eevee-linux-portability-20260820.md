<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 EEVEE producer portability - 2026-08-20

## Outcome

The current 30-row EEVEE browser-matrix producer now runs its hermetic,
no-browser self-check from the ornith-lab checkout and from a descendant working
directory. It no longer executes the retained one-row driver's macOS checkout,
Playwright, Metal-ANGLE, Homebrew `oiiotool`, or five-file shell assumptions.

This is producer readiness only. No browser or native fixture batch was run, no
matrix directory was allocated, and no M6, M4, split, adapter, or GPU receipt was
created. The s7 stop-condition remains binding: llvmpipe is software and binds
nothing, while the shipping APPLY split product cannot exist before accepted
hardware profile capture.

## Reproduced defect

Before the repair, the required self-check failed before generating its first
row driver while opening the absolute macOS manifest path:
`ledger/buildlogs/20260820T182909-2364653.log`.

## Repair

- `run_eevee_matrix.mjs` derives the checkout and canonical run directory from
  its own `import.meta.url`, independent of the caller's current directory.
- The retained 2,175-line one-row F12 driver remains unchanged. The current
  producer replaces each load-bearing root, comparator, shell, Playwright, and
  browser-argument seam with an exact-count guard before hashing the temporary
  row driver.
- Playwright resolution follows `BW_NODE_MODULES`, `NODE_PATH`,
  `.m4-node/node_modules`, then local `node_modules`. The selected root and
  platform-specific browser arguments are bound into each row receipt and
  independently rechecked by the matrix consumer.
- Linux drops the macOS-only `--use-angle=metal` argument; macOS retains it.
  Both paths retain headed Chromium and `--enable-unsafe-webgpu`. This is launch
  portability, not adapter acceptance; the s7 hardware proof remains external
  and mandatory.
- Real rows still read and SHA-256-bind the exact JS, primary Wasm, deferred
  Wasm, data, blend, golden, canonical driver, and generated driver before a
  verdict. Output is confined to one validated immediate child of `runs/`.
- Served-shell attestation now covers the current six-file set, including
  `diagnostics-bootstrap.js`. The Linux comparator default is the `oiiotool`
  found on `PATH`, with the existing explicit `OIIOTOOL` override preserved.

## Evidence

- Root self-check: `ledger/buildlogs/20260820T183537-2369388.log`.
- Descendant-cwd self-check:
  `ledger/buildlogs/20260820T183537-2369387.log`.
- Both runs validate 30/30 generated-driver syntax checks and 30/30 generated
  driver self-checks, exact setup coverage 29 canonical bakes plus one pinned
  scene skip, the 27/1/2 sample distribution, six shell files, and Linux browser
  arguments. Both report `browser_launches=0`.
- Aggregate M6 verifier self-check:
  `ledger/buildlogs/20260820T183608-2370708.log`.
- Final matrix-runner syntax:
  `ledger/buildlogs/20260820T183608-2370707.log`.
- REUSE 3.3 compliance, 1,917/1,917 files:
  `ledger/buildlogs/20260820T183653-2371119.log`.
- Required M6 and container-backed regression at 2026-08-20T18:38Z remain
  honestly RED at the existing missing-current-Workbench boundary; M0 is 6/6
  GREEN, while M1-M5 retain their strict-manifest, hardware, binding, and APPLY
  blockers.

The next EEVEE action is unchanged: after s7 proves a hardware WebGPU adapter
and CAPTURE-to-APPLY completes, install pinned Playwright 1.61.1, allocate a
fresh immutable label, and run the full 30-row canonical-probe matrix. The
optional native-prebake route remains a separate macOS-era path and was not
claimed as Linux-ready here.
