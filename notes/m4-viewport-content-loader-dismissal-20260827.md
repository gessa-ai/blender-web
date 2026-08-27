<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# VIEW_3D-qualified loader dismissal — 2026-08-27

## Outcome

The source candidate no longer treats an arbitrary WebGPU surface present as permission to hide
the loader. Cold boot starts one bounded complete-frame episode. A frame qualifies for loader
readiness only when successful draw encoding records the visible VIEW_3D background, the stock
`overlay_grid_next` pass, and a later direct-window `OCIO_Display` composite. The two offscreen
passes may occur in either order, but the final display composite must follow both. The
matching queue-validated surface submission publishes the one-shot
`bw_viewport_content_present_count` export; the shell polls only that export and fails closed with
the loader still visible at its existing 120-second ceiling.

This is deliberately stricter than resize recovery. After loader readiness has published, later
resize barriers retain their hardware-proven background/display predicate, so a user who disables
the grid cannot make resize presentation permanently impossible.

## Evidence

- Fail-first: the new shell and six-source contracts rejected the generic-present implementation
  for a missing VIEW_3D marker and missing grid trace. The first exact CAPTURE relink then exposed
  a second fail-first boundary: `WM_main` advanced 325 ticks but produced zero presents because the
  live trace was consistently grid -> background -> display while the source-only predicate
  required background -> grid -> display. The final sampled sequences were grid `3817`, background
  `3819`, and display `3856`.
- `e369b6e` removes that invented offscreen ordering constraint while still requiring both passes
  before the display composite. `M4_VIEWPORT_CONTENT_LOADER_PASS` now binds the exact-product
  diagnostic and rejects 17 mutations across seven sources
  (`ledger/buildlogs/20260827T193111-2380460.log`).
- The native and wasm32 recovery model is byte-identical across 66 cases, including the measured
  grid-before-background order, alternate background-before-grid order, background-only rejection,
  late-readiness trace rearm, one-shot readiness, and permanent trace retirement after publication
  (`ledger/buildlogs/20260827T192819-2376213.log`).
- A controlled Chromium run keeps the loader visible with `_bw_present_count() == 1`, then hides it
  only after `_bw_viewport_content_present_count()` advances; the minimal Downloading/Launching
  design and local font remain intact (`ledger/buildlogs/20260827T193115-2380495.log`).
- The exact relinked fallback product reaches generic present and validated VIEW_3D present together
  at 11,928 ms, dismisses the loader at 11,955 ms with both counters at one, advances 435 WM ticks,
  and reports zero page errors (`ledger/buildlogs/20260827T193119-2380665.log`). This is a
  software-adapter diagnostic, not a pixel or performance receipt.
- The three changed C++ units compile under the real windowed Emscripten flags without linking
  (`ledger/buildlogs/20260827T191116-2363280.log`). Canonical freeze/replay is exact at
  `PREVIEW_SNAPSHOT.patch` SHA-256 `1a9ce58a2438...`; public assembly, minification, hardening,
  staged provenance, technical compliance, and REUSE 6.2.0 are green.

## Boundary

The corrected source is relinked as a new CAPTURE generation: JS `8d05e8c8f0c4` (707,729 bytes),
Wasm `9b0cbb993e16` (120,513,470 bytes), `.wasm.orig` `f3251f948449` (119,160,136 bytes), data
`095d0ba748c3` (168,637,598 bytes), and split manifest `eefd2418dbf9` (13,294 bytes). CAPTURE
preflight passes, and committed `e369b6e` is locked no-work
(`ledger/buildlogs/20260827T193212-2381269.log`). This supersedes the immutable
`v0.1.1-rc.1` bytes for the loader candidate but does not rewrite that tag.

The candidate is pending an Apple M4 Pro cold-boot check. Closure
requires the loader to remain visible through every chrome-only/clear VIEW_3D frame and disappear
only when grid, gizmo, and scene pixels are visibly present, without regressing P0-E resize recovery.
The new `.wasm.orig` hash also requires fresh success and terminal profiles before APPLY. This
device-free work binds no hardware pixel, performance, profile, APPLY, public-bundle, final tag, or
release receipt.
