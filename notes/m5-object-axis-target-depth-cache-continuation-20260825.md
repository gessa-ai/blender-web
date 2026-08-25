<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 object axis-target depth-cache continuation — 2026-08-25

## Outcome

Commit `d2a2456` and patch 0272 move `OBJECT_OT_transform_axis_target`'s synchronous
full-viewport depth read behind an operation-owned continuation. The temporary overlay suppression
now spans only the draw-only depth preparation and is restored before readback initialization can
fail or suspend. Selected compatible objects and their transform backups are not captured until a
valid cache has been consumed.

The native-immediate path consumes the cache and enters the stock initialization tail on the
original stack. A genuinely pending request retains the exact custom-data-free initiating event
plus up to 256 safe modal events behind one 100 Hz timer for at most 240 ticks. It guards the
producing manager, window, screen, area, region, RegionView3D, View3D, dependency graph, scene,
view layer, and active target object. Ready settlement transfers one `ViewDepths`, initializes the
stock selected-object/backup state exactly once, and replays the FIFO through the unchanged modal
dispatcher. Initiating-button release, confirm/cancel, translation toggles, and mouse movement
therefore keep their stock order and terminal behavior.

The existing incompatible-target pass-through and no-depth warning/cancellation remain unchanged.
Context drift, later backend or consume failure, timer-allocation failure, timeout, unsafe event
payload, queue overflow, Escape, right-click, external cancellation, and destruction retire the
timer, request, initiating event, and FIFO. An explicit initialized-state guard prevents pending
cancellation from restoring transform backups that do not exist yet.

## Source and contract evidence

- The pinned Linux oracle retains public `OBJECT_OT_transform_axis_target`, no RNA properties, and
  the expected false headless poll (`20260825T053950-896100`). The pinned predecessor fails before
  evidence allocation because it owns no continuation state (`20260825T053940-896014`).
- The final focused receipt (`20260825T054216-898447`) passes eight contracts and 36 cases
  byte-for-byte under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 479-byte output is
  `sha256:0b6ffd7acf4353ebc1b77914b81284628e062286e6353f00b6da53044b9fcbe3`; the one-file shipping
  postimage is `sha256:4726fb6898e566dd00375fc8adecfb97eead1f3d0bbdbc07782b98929f8de8f3`.
  Seventeen ownership, ordering, override-restoration, timer, context, FIFO, and cleanup mutations
  fail closed. The same receipt reverses/reapplies patch 0272 at
  `sha256:295b92b3478381c73af9a314b127b941c9fe280947dfdac8d4583df25c2cf1cc` and compiles the exact
  native and windowed-Wasm product-graph `object_transform.cc` translation unit.
- Aggregate async-readback receipt `20260825T054234-898674` remains byte-identical at 627 bytes /
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720` and truthfully retains
  exactly the `depth_cache` and `window_capture` synchronous families.

## Integration evidence

- Clean-pin freeze `20260825T054135-897876` reproduces 20,258 source entries with byte-identical
  live/replay manifests at
  `sha256:12997bb060478c720cef8a49c31681c34d47d0ab58f7f1f2be5ea4a246170ebf`.
  `PREVIEW_SNAPSHOT.patch` is 2,247,391 bytes at
  `sha256:4e20dcd1fb68df2471c6146fe12cc034254ff5846a0fa1b6b8a7d435f69a8e3f`.
  Authoritative replay binds 299 paths and 249 active numbered identities
  (`20260825T054234-898675`).
- The real `blender_browser` relink and locked no-work check are green
  (`20260825T054249-898983` / `20260825T054337-899413`). Strict OFF preflight
  `20260825T054342-899464` binds 657,938-byte JavaScript, 118,987,552-byte Wasm, and
  167,143,248-byte data artifacts.
- Repository-wide REUSE 6.2.0 is green for 2,484/2,484 files
  (`20260825T054919-904728`). The six-tier hardware-deferral contract retains the exact named
  blocker after the partial-ledger update (`20260825T054511-901623`).
- Required M5 remains honestly red only at the absent
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary
  (`20260825T054354-899549`). Container-backed regression restores M0 6/6 green while M1–M8 retain
  their existing strict-receipt, browser, product, run-label, hardware, and release boundaries
  (`20260825T054358-899597`).

Particle edit is now the sole remaining depth-cache caller family, and WM window capture remains
the other synchronous family. Live C1/M5 acceptance remains separately deferred by the named
blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
This work creates no adapter, device, browser profile, split product, or live receipt, and changes
no result promotion, dependency decision, tolerance, golden, blacklist, or milestone promise. dzn
and Windows were not attempted, and WSL was not restarted.
