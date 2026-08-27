# P0-E hardware resize acceptance producer — 2026-08-27

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Commit `4b6710a` makes the driver's calibrated ten-attempt P0-E pixel check a portable,
repository-owned hardware acceptance producer. It does not close P0-E: the exact ordered-present
CAPTURE generation still needs 10/10 Apple hardware shrinks with the complete idle scene visible.

The saved driver script was useful evidence but was not runnable from this checkout because its
Playwright and PNGJS imports named two driver-local absolute trees. The new producer derives the
checkout and product paths, resolves the already-pinned browser dependencies, and writes confined
immutable evidence without retaining host-local paths in its receipt.

## Contract

- exact Node 22.16.0, Playwright 1.61.1, PNGJS 7.0.0, and Chromium 149.0.7827.55;
- `hardware-webgpu-adapter-v1`, reading `GPUAdapterInfo.isFallbackAdapter` before the legacy field
  and rejecting missing status, fallback, masked, CPU, SwiftShader, llvmpipe, lavapipe, softpipe,
  WARP, and other software identities before evidence allocation;
- an explicit expected `.wasm.orig` SHA-256, checked against the direct local file, the local
  CAPTURE manifest, and the manifest served by the tested loopback origin;
- exactly ten fresh browser contexts at DPR 1; each establishes a 1280x720 semantic VIEW_3D
  baseline, dismisses the splash, shrinks to 1100x640, then emits no keyboard or pointer input;
- the driver's calibrated fixed-region decision (`dominantFraction < 0.95`) with a 24-second hard
  bound, retaining every boot, baseline, and shrink PNG for grid/Cube/gizmo visual audit;
- zero unhandled page errors and zero scissor, encode, submit, present-transaction, or device-loss
  diagnostics in every passing attempt.

Only `BW_P0E_HARDWARE_RESIZE_PASS attempts=10/10` and its receipt/images can close the candidate.
The self-check and any software-adapter run are explicitly nonreceipts.

## Evidence

- Saved-script portability failure: `ledger/buildlogs/20260827T080531-1791395.log`.
- Final browser-free self-check: 26 positive / 17 negative cases, ten attempts, 24,000 ms bound at
  `ledger/buildlogs/20260827T081654-1800093.log`.
- Live Linux probe rejects `adapter-absent` before allocation; the output-absence check is green:
  `ledger/buildlogs/20260827T081017-1794277.log` and
  `ledger/buildlogs/20260827T081122-1795554.log`.
- A wrong generation rejects before browser launch at
  `ledger/buildlogs/20260827T081222-1796023.log`.
- Existing ordered-present source and resize-trace contracts remain green at
  `ledger/buildlogs/20260827T081416-1798347.log` and
  `ledger/buildlogs/20260827T081416-1798346.log`.
- REUSE 6.2.0 is green at `ledger/buildlogs/20260827T081654-1800094.log`.
- The ordered-present `.wasm.orig` remains byte-identical at SHA-256
  `e3d284c7da0e11f09beada6c9a4b788044b0c8f9715dcee42bc80839d70c8238`:
  `ledger/buildlogs/20260827T081731-1800403.log`.
- Direct M4 remains RED at its absent exact-generation hardware binding:
  `ledger/buildlogs/20260827T081236-1796119.log`.
- Authoritative pinned-container regression restores M0 to 6/6 and leaves M1-M8 at their existing
  strict receipt/APPLY/browser/tier boundaries: `ledger/buildlogs/20260827T081310-1797248.log`.

## Boundary

This unit changes no runtime source and performs no relink. It creates no hardware adapter, pixel
receipt, profile, APPLY/public bundle, result promotion, tolerance, golden, blacklist, deferral,
tag, or launch claim. P0-E stays open against exact CAPTURE generation
`e3d284c7da0e11f09beada6c9a4b788044b0c8f9715dcee42bc80839d70c8238` until the driver-operated
Apple rig records 10/10.
