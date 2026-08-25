<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 Grease Pencil freehand depth-cache continuation — 2026-08-25

## Outcome

Commit `148d1bc` and patch 0268 convert the launch-critical freehand
`GREASE_PENCIL_OT_brush_stroke` surface/stroke placement path without changing stock native-ready
or non-depth behavior. `DrawingPlacement` owns one asynchronous full-viewport cache session and
reuses the exact synchronous depth mode, selected-only policy, forced 3D stroke order, and cache
transfer semantics. Copying a pending placement is forbidden; move, reset, failure, and destruction
all transfer or retire the exact owned session.

The paint operation snapshots the exact producing manager, window, screen, area, region, View3D,
RegionView3D, dependency graph, scene, object, evaluated object, Grease Pencil data, layer, and
frame. Its first already-processed `InputSample` and up to 256 generated extension samples remain
owned in FIFO order while one 60 Hz modal timer polls for at most 240 ticks. A ready request starts
on the original callback stack. Context drift, backend failure, timeout, overflow, Escape, and
external cancellation retire the complete request, placement, sample queue, timer, and retained
terminal event before any deferred mutation.

Release and confirm handling remain stock. The modal stroke owner copies the terminal `wmEvent`,
clears borrowed/custom payload fields, and replays that event through `PaintStroke::modal` only
after the sample FIFO settles. This is required for line and anchored brushes because the shared
dispatcher performs their `line_end` work before invoking the operation's done callback; jumping
directly to done would have silently lost that stock finalization.

## Source and contract evidence

- The pinned Blender oracle reports the public brush-stroke operator fields and exact per-sample
  RNA surface (`20260825T023950-737349`). The 0267 predecessor rejects before evidence allocation
  because no placement continuation API exists (`20260825T024411-740083`).
- Final root and descendant focused receipts (`20260825T030716-764796` and
  `20260825T030957-767775`) pass eight contracts and 18 cases byte-for-byte under clang++ 17 and
  em++ 6.0.5/Node 22.16.0. Their 543-byte output is
  `sha256:e69dfa75cceaf8dc0df86d4efcf0f881111e16a8673b26305d0e132b7b99a56c`; the
  five-file production postimage is
  `sha256:53aaf9bbae531f0c5ee5b695c19ac1e30412693586cf41b1ec87d558864af715`.
  Twelve ownership, immediate/pending, context, FIFO, terminal-replay, bound, failure, and
  cancellation mutations fail closed.
- Exact native and wasm product-graph compiles cover all three changed translation units
  (`20260825T025020-751504`, `20260825T025025-751625`, and
  `20260825T025140-752895`). Numbered patch 0268 reverses and reapplies its five exact postimages
  at `sha256:e532f14296fb4bbf0ed5124327a7bedd59c2cbafb2e4d8e44c303ebb09aa3590`
  (`20260825T025807-756912`).
- Aggregate source receipt `20260825T030658-764357` remains green with 40 fail-closed mutations
  and byte-identical 627-byte native/Wasm output at
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`.
  It truthfully retains exactly the `depth_cache` and `window_capture` synchronous families.

## Integration evidence

- The corrected clean-pin freeze (`20260825T030521-763325`) composes patches 0266–0268 and
  reproduces 20,258 source entries with zero ignored paths. `PREVIEW_SNAPSHOT.patch` is 2,173,710
  bytes at `sha256:bcf670e96390cad3f76a1d2b03f482d6b2968bd7933c964f4c1d63785c40243f`;
  both manifests are
  `sha256:691a1b812dd323dd9d6890ae5cd4d7f8ef598a26833c50a572f93975bcd346be`.
  Canonical-only replay binds 293 paths and 245 active identities
  (`20260825T030651-764214`). An earlier incomplete snapshot that omitted the already-landed 0266
  and 0267 postimages was rejected during aggregate verification and is not used as evidence.
- The real `blender_browser` product linked successfully (`20260825T030206-759706`) and ends exact
  locked no-work (`20260825T031042-768435`). Strict OFF preflight
  `20260825T031042-768434` binds 657,928-byte JavaScript, 118,981,534-byte Wasm, and 167,143,248-byte
  data artifacts.
- Repository-wide REUSE 6.2.0 is green for 2,448/2,448 files
  (`20260825T031649-773616`). The six-tier WSL2 hardware-deferral contract retains the exact named
  blocker (`20260825T031649-773615`).
- Required M5 remains honestly red only at the absent
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary
  (`20260825T030806-766094`). Pinned-container regression `20260825T031116-768985` restores M0
  6/6 green and leaves M1–M8 at their existing strict-receipt, browser, product, run-label,
  hardware, and release boundaries.

Grease Pencil primitive, fill, and pen-helper placement callers remain explicit depth-cache
residuals alongside object axis-target placement, particle edit, and WM window capture. Live C1/M5
acceptance remains separately deferred by the named blocker: no conformant hardware Vulkan ICD in
WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This work creates no adapter, device, browser
profile, split product, or live receipt, and changes no result promotion, dependency decision,
tolerance, golden, blacklist, or milestone promise. dzn and Windows were not attempted, and WSL was
not restarted.
