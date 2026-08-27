<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Two-phase release loader — 2026-08-27

## Outcome

Commit `f9dfb78` adds the owner-specified `Downloading` and `Launching` states to the existing
minimal loader without adding another spinner, bar, paragraph, or network asset. `Downloading`
retains Emscripten's byte-derived Stage-0 data percentage. `Launching` removes that determinate
value, displays an em dash, and gives the same two-pixel bar one honest indeterminate sweep until
the loader's dismissal signal fires.

This is shell-only. The relinked P0-E CAPTURE artifact remains byte-identical at
`blender_browser.wasm.orig` SHA-256
`390062afea7c7117c40640b3259ae7328507c840ada80b62551f33ad992507f2`, so the driver's pending
10/10 Apple resize acceptance run is not invalidated.

## Boundary

The current generated Emscripten glue emits byte progress as
`Downloading data... (loaded/total)` and emits `Running...` only after its run dependencies have
resolved. The shell uses that exact post-download/runtime boundary, with
`onRuntimeInitialized` as the format-drift fallback.

This task does **not** close the owner's viewport-content dismissal gap. The legacy
`noteFirstPixels` path still consumes a generic first successful presentation, which can be a
chrome-only frame. A separately filed successor must expose and consume a marker for successful
visible `SPACE_VIEW3D` content before hiding the loader. It is sequenced behind P0-E's exact
Apple 10/10 acceptance so this hardware candidate remains stable.

## Evidence

- Fail-first source contract rejects the missing phase DOM at
  `20260827T050230-1650882`; final source coverage passes at `20260827T050526-1654196`.
- Controlled Chromium observes byte-determinate `Downloading 25%`, then
  indeterminate `Launching —`, with one ring, one bar, the local font, a single-line footer,
  hidden diagnostics, and zero external requests at `20260827T050353-1652512`.
- JavaScript syntax and the unchanged bounded first-presentation fallback pass at
  `20260827T050424-1653092` and `20260827T052255-1659635`.
- Public disclaimer, deployment portability, monolithic/staged assembler self-checks, and the
  technical receipt contract pass at `20260827T050450-1653381`,
  `20260827T050450-1653382`, `20260827T050450-1653385`,
  `20260827T050450-1653397`, and `20260827T050450-1653408`.
- Exact Stage-0 provenance/minification replay passes at `20260827T050526-1654195`; the five
  public scripts now measure 28,031 raw Brotli bytes versus 14,250 minified bytes under pinned
  q11/lgwin-24. The independent minifier and codec self-checks pass at
  `20260827T052255-1659636` and `20260827T052255-1659643`.
- REUSE 6.2.0 passes at `20260827T052333-1659955`.
- Direct M4 remains honestly red at its pre-existing browser-pixel binding boundary
  (`20260827T052339-1660073`). Container-backed regression restores M0 6/6 while M1–M8 retain
  their named strict receipt/APPLY/browser boundaries (`20260827T053616-1666400`).

No Wasm relink, APPLY shard, public bundle, tag, profile, hardware receipt, result promotion,
tolerance, golden, blacklist, deferral status, promise, or launch claim changed.
