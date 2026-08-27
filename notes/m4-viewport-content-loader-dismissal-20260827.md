<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# VIEW_3D-qualified loader dismissal — 2026-08-27

## Outcome

The source candidate no longer treats an arbitrary WebGPU surface present as permission to hide
the loader. Cold boot starts one bounded complete-frame episode. A frame qualifies for loader
readiness only when successful draw encoding records the visible VIEW_3D background, the stock
`overlay_grid_next` pass, and the later direct-window `OCIO_Display` composite in order. The
matching queue-validated surface submission publishes the one-shot
`bw_viewport_content_present_count` export; the shell polls only that export and fails closed with
the loader still visible at its existing 120-second ceiling.

This is deliberately stricter than resize recovery. After loader readiness has published, later
resize barriers retain their hardware-proven background/display predicate, so a user who disables
the grid cannot make resize presentation permanently impossible.

## Evidence

- Fail-first: the new shell and six-source contracts rejected the generic-present implementation
  for a missing VIEW_3D marker and missing grid trace.
- `M4_VIEWPORT_CONTENT_LOADER_PASS` rejects 13 source mutations covering grid ordering,
  presentation validation, cold-boot tracing, queue-tail selection, shell fallback, and numbered
  patch identity.
- The native and wasm32 recovery model is byte-identical across 65 cases, including background-only
  rejection, late-readiness trace rearm, background/grid/display acceptance, one-shot readiness,
  and permanent trace retirement after publication
  (`ledger/buildlogs/20260827T191031-2360794.log`).
- A controlled Chromium run keeps the loader visible with `_bw_present_count() == 1`, then hides it
  only after `_bw_viewport_content_present_count()` advances; the minimal Downloading/Launching
  design and local font remain intact (`M4_LOADER_BROWSER_PASS dismiss=view3d-content-only`).
- The three changed C++ units compile under the real windowed Emscripten flags without linking
  (`ledger/buildlogs/20260827T191116-2363280.log`). Canonical freeze/replay is exact at
  `PREVIEW_SNAPSHOT.patch` SHA-256 `1a9ce58a2438...`; public assembly, minification, hardening,
  staged provenance, technical compliance, and REUSE 6.2.0 are green.

## Boundary

No product was relinked. The immutable `v0.1.1-rc.1` CAPTURE handoff remains byte-identical:
JS `52a9a0257830`, Wasm `69b2f10ebac7`, `.wasm.orig` `505702dbf41c`, data `095d0ba748c3`, and
split manifest `10b181385e60`. That exact generation remains available for the driver's fresh
success and terminal profile capture.

The source candidate is pending a separate relink and Apple M4 Pro cold-boot check. Closure
requires the loader to remain visible through every chrome-only/clear VIEW_3D frame and disappear
only when grid, gizmo, and scene pixels are visibly present. This device-free work binds no pixel,
performance, profile, APPLY, public-bundle, tag, or release receipt.
