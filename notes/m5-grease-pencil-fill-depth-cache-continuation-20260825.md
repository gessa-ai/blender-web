<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 Grease Pencil fill depth-cache continuation — 2026-08-25

## Outcome

Commit `340a412` and patch 0270 move both synchronous Grease Pencil fill-cache reads to the
`GREASE_PENCIL_OT_fill` owner. A surface/stroke click now constructs one placement and begins its
owned full-viewport request before autokey can create drawings and before either pixel rendering or
Delaunay triangulation can produce a result. The public `pixel_fill_strokes` and
`delaunay_fill_strokes` helpers take that ready placement explicitly and contain no synchronous
cache call.

Non-depth and immediately ready requests finish on the original modal stack. An initial read
failure keeps Blender's stock projection fallback; only a genuinely pending request installs the
100 Hz timer. The operation retains one custom-data-free copy of the terminal click for at most 240
ticks and swallows unrelated events, because stock execution would have completed on that click.
It guards the producing manager, window, screen, area, region, RegionView3D, View3D, dependency
graph, scene, view layer, object, Grease Pencil data, active layer, frame, paint, and brush. Ready
settlement applies the exact original window/region coordinates, fit mode, boundary selection,
invert state, and solver once. Drift, later backend failure, timeout, Escape, timer-allocation
failure, external cancellation, and destruction retire the timer, retained event, placement, and
request before any fill result work.

## Source and contract evidence

- The pinned Blender oracle retains the public `GREASE_PENCIL_OT_fill` identity and its exact
  writable `invert`/`precision` Boolean properties (`20260825T042152-829926`). The patch-0269
  predecessor fails closed before evidence allocation because the fill owner has no continuation
  state (`20260825T041037-819561`).
- The post-commit focused receipt (`20260825T042956-838065`) passes eight contracts and 28 cases
  byte-for-byte under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 452-byte output is
  `sha256:598292ce9359bf7f508272764089d397d8ba6d64dfd1872ce1efb8e44ba44ecc`; the three-file
  shipping postimage is
  `sha256:5f3ba17a571d1bccb31bc7b75826b50e46fab63096636e09849c2a17d6c10e39`.
  Twelve ownership, ordering, helper-interface, timer, context, and algorithm mutations fail
  closed. The same receipt reverses/reapplies patch 0270 at
  `sha256:02f5eb81a7253b5301e21381d6b8a30752332cf35828bfe09e9fc331f6bb86d2` and compiles the
  exact native and wasm product-graph `draw_ops.cc` and `fill.cc` translation units.
- Aggregate async-readback receipt `20260825T042859-837447` remains byte-identical at 627 bytes /
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720` and truthfully
  retains exactly the `depth_cache` and `window_capture` synchronous families.

## Integration evidence

- Clean-pin freeze `20260825T042634-835110` reproduces 20,258 source entries with byte-identical
  live/replay manifests at
  `sha256:c407f10b7fd4b8e8300109542953ba5cf7f82e03ffd7437fea51afd11168e034`.
  `PREVIEW_SNAPSHOT.patch` is 2,213,162 bytes at
  `sha256:31608af0fba94bd0f093f00f8dfa5798aba0756c3ffe076a59d17c211f276b3c`.
  Post-commit canonical replay binds 295 paths and 247 active numbered identities
  (`20260825T043020-839143`).
- The real `blender_browser` rebuild and post-commit locked no-work check are green
  (`20260825T042756-836597` / `20260825T043028-839248`). Strict OFF preflight
  `20260825T042851-837370` binds 657,938-byte JavaScript, 118,984,327-byte Wasm, and
  167,143,248-byte data artifacts.
- Repository-wide REUSE 6.2.0 is green for 2,466/2,466 files
  (`20260825T043319-841091`).
- The six-tier hardware-deferral contract retains the exact named blocker
  (`20260825T042416-832074`). Required M5 remains honestly red only at the absent
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary
  (`20260825T042424-832157`). Container-backed regression restores M0 6/6 green while M1–M8
  retain their existing strict receipt, browser, product, run-label, hardware, and release
  boundaries (`20260825T042443-832607`).

Grease Pencil pen-helper placement, object axis-target placement, particle edit, and WM window
capture remain explicit synchronous residuals. Live C1/M5 acceptance remains separately deferred
by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn
rejected by Dawn). This work creates no adapter, device, browser profile, split product, or live
receipt, and changes no result promotion, dependency decision, tolerance, golden, blacklist, or
milestone promise. dzn and Windows were not attempted, and WSL was not restarted.
