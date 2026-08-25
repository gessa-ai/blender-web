<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 interactive annotation depth-cache continuation — 2026-08-25

## Outcome

Patch 0266 converts the interactive `GPENCIL_OT_annotate` draw, polyline-update, and
depth-aware eraser paths from synchronous full-viewport depth reads to the owned
`ViewportDepthCacheSession`. It keeps Blender's recorded-stroke `exec` callback synchronous and
names that residual in `ledger/deferred.json`; this unit does not claim the entire depth-cache
family is closed.

Interactive operation forces the stock depth pass, starts one exact cache request, and either
continues immediately or retains the producing manager, window, screen, area, region, View3D,
RegionView3D, scene, dimensions, and matrices behind one 10 ms timer. A maximum 256 events with no
custom payload are copied into an owned FIFO, and polling is capped at 240 ticks. Settlement
transfers the cache exactly once. An initiating event that has already crossed the idle-to-stroke
transition resumes at `annotation_draw_apply_event`; subsequent events replay through the stock
modal dispatcher. A polyline update may invalidate that generation and transfer the remaining FIFO
to a successor request without reordering or duplicate application.

Context or matrix drift, unsafe event payload, queue overflow, timeout, backend failure, and
external cancellation all retire the timer, request, cache, FIFO, and uncommitted stroke before
returning cancellation. Native and noninteractive recorded execution retain their existing three
synchronous `ED_view3d_depth_override` call sites.

## Behavior and source evidence

- The pinned Blender oracle exposes `GPENCIL_OT_annotate` in draw mode with its stroke collection
  and `wait_for_input=true`. The exact predecessor rejects the focused source contract before
  evidence allocation because it lacks the new ownership/provenance contract
  (`20260825T012640-675032`).
- Focused receipt `20260825T014913-693360` passes eight contracts and 18 cases byte-for-byte under
  clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 366-byte output is
  `sha256:3a1beeb6c587386a1ba45a9c6ab36c4b180615c2d88461d844a87b0f38f6429e`; the production
  postimage is `sha256:8793ab7408a6d17424512d23565f2c582d90c69dcea49d353518e78a7fc32517`.
  The matrix covers native-immediate settlement, pending terminal replay, exact initiating-event
  apply, eraser FIFO, chained polyline refresh, producing-context drift, backend failure, timeout,
  unsafe payload and queue bounds, and external cancellation.
- The focused source checker rejects 12 ownership, prepare, queue, matrix, timeout, transfer,
  initial-resume, context, point-read, invoke, and cancellation mutations. Exact native and wasm
  product-graph commands compile `annotate_paint.cc` (`20260825T013031-678466` and
  `20260825T013034-678465`). Numbered patch 0266 reverses and reapplies the exact postimage at
  `sha256:69222e2ce6b6760b20e2adabd3fe1c2d1e2398054962a836ce671f9ae4ba500f`
  (`20260825T014856-693224`).
- Aggregate receipt `20260825T013752-683591` passes the 46-source owned-readback census with 39
  fail-closed mutations and byte-identical 627-byte native/Wasm output at
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`.

## Integration evidence

- The clean-pin freeze `20260825T013436-680954` reproduces all 20,258 manifest entries
  byte-for-byte without changing `upstream/`. `PREVIEW_SNAPSHOT.patch` is 2,142,658 bytes at
  `sha256:f33636abc9541ad2ec113d3029cf6ce7a1d40fd1f9737dc4e834e30cfb12574b`; both manifests
  are `sha256:0ad12d8dcd6362fda7a502b94c0ae98e319b8da37467201452f8acc2d7652269`.
  Clean-pin canonical replay binds 288 paths, while the isolated 0266 reverse/forward proof binds
  its one numbered identity.
- The immutable-upstream windowed graph compiles this one translation unit from the frozen source
  overlay, relinks `blender_browser`, and ends locked no-work (`20260825T014159-687164` and
  `20260825T014250-687601`). Strict OFF preflight `20260825T014250-687598` binds 657,928-byte
  JavaScript, 118,975,387-byte Wasm, and 167,143,248-byte data artifacts.
- Repository-wide REUSE 6.2.0 is GREEN for 2,438/2,438 files
  (`20260825T015258-695895`).
- Required M5 remains honestly RED only at the absent `blender_browser.deferred.wasm` product
  boundary (`20260825T014348-688910`). Container-backed regression
  `20260825T014358-689055` keeps M0 6/6 GREEN while M1–M8 retain their existing strict receipt,
  browser, split-product, hardware, run-label, and release boundaries.

Live C1/M5 acceptance remains separately deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). No adapter, browser profile,
split product, live receipt, result promotion, dependency decision, tolerance, golden, blacklist,
or milestone promise changed. dzn and Windows were not attempted, and WSL was not restarted.
