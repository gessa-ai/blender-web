<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 Grease Pencil primitive depth-cache continuation — 2026-08-25

## Outcome

Commit `72e1939` and patch 0269 convert the shared invoke path for all six
`GREASE_PENCIL_OT_primitive_*` operators without changing their public RNA surface. Surface and
stroke placement starts one owned asynchronous full-viewport cache before the first control point
is projected. Non-depth and immediately ready requests stay on the original invoke stack, and an
initial read failure preserves the stock projection fallback instead of manufacturing a new cancel.

The pending path snapshots the invoke-time primitive type, subdivision, and start coordinates. It
retains the producing manager, window, screen, area, region, RegionView3D, View3D, dependency graph,
scene, view layer, object, Grease Pencil data, active layer/drawing, paint, brush, and frame. Up to
256 custom-data-free `wmEvent` copies remain FIFO behind one 100 Hz timer for at most 240 ticks. The
modal cursor and handler are owned while pending, but navigation, control points, editable curves,
preview callback, and status state do not exist before settlement.

One ready-only helper creates those stock resources and mutations exactly once, then the pending
poller replays retained input through the unchanged modal dispatcher. Confirm and navigation events
therefore preserve their original semantics and order. The pre-initialized exit branch retires the
exact timer, placement request, event FIFO, and cursor without touching absent draw handles or
geometry. Producing-context drift, a later backend failure, timeout, unsafe payload, overflow,
Escape, and external cancellation all use that branch.

## Source and contract evidence

- The pinned Blender oracle reports all six registered operators as pollable with the same exact
  `subdivision` integer and `type` enum properties (`20260825T032424-781955`). The patch-0268
  predecessor rejects before evidence allocation because the primitive owner lacks continuation
  state (`20260825T032954-785700`).
- The post-commit focused receipt (`20260825T034959-802925`) passes eight contracts and 28 cases
  byte-for-byte under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 571-byte output is
  `sha256:8a597a117df314b7cc29527445ca5eb8641348b1badb1059e45138b3610183e8`; the one-file
  shipping postimage is
  `sha256:ae90c461b3c6a7080fe75fcb01652fb8358ed97c6bde60d3920dea373fee82a7`.
  Sixteen immediate/fallback, pre-projection, context, FIFO, payload, bound, settlement, and teardown
  mutations fail closed. The same receipt reverses/reapplies numbered patch 0269 at
  `sha256:2238460382169c809304deee1c2329d11552c3db6972731389d7d04ac8cdca1a` and compiles the
  exact native and wasm product-graph translation unit.
- Aggregate async-readback receipt `20260825T034535-798854` remains green and byte-identical at
  627 bytes / `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`.
  It truthfully retains exactly the `depth_cache` and `window_capture` synchronous families.

## Integration evidence

- Clean-pin freeze `20260825T034341-796839` reproduces 20,258 source entries with zero ignored
  paths. `PREVIEW_SNAPSHOT.patch` is 2,190,506 bytes at
  `sha256:30133a7b7631a240bd5e110999fc2b33afdb8ab91d3f269442d468a841ce551c`; both manifests
  are `sha256:7288fc64eb70b97607ff8fa02e1f8a0b4b1c7cc46a50b985fda5f47836abf742`.
  Canonical-only replay binds 294 paths and 246 active numbered identities
  (`20260825T034229-796123`).
- The real `blender_browser` product rebuild and locked no-work check are green
  (`20260825T034417-797414` / `20260825T034512-798601`). Strict OFF preflight
  `20260825T034525-798769` binds 657,928-byte JavaScript, 118,982,671-byte Wasm, and
  167,143,248-byte data artifacts.
- Repository-wide REUSE 6.2.0 is green for 2,457/2,457 files
  (`20260825T035353-806022`).
- The six-tier hardware-deferral contract retains the exact named blocker
  (`20260825T035315-805855`). Required M5 remains honestly red only at the absent
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary
  (`20260825T035255-804946`). Pinned-container regression `20260825T035304-805062` restores M0
  6/6 green and leaves M1–M8 at their existing strict-receipt, browser, product, run-label,
  hardware, and release boundaries.

Grease Pencil fill and pen-helper placement remain explicit depth-cache residuals alongside object
axis-target placement, particle edit, and WM window capture. Live C1/M5 acceptance remains
separately deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships
none; Mesa dzn rejected by Dawn). This work creates no adapter, device, browser profile, split
product, or live receipt, and changes no result promotion, dependency decision, tolerance, golden,
blacklist, or milestone promise. dzn and Windows were not attempted, and WSL was not restarted.
