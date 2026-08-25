<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 curve depth-cache continuation — 2026-08-25

## Outcome

Patch 0265 converts both freehand surface-projection operators, `CURVE_OT_draw` and
`CURVES_OT_draw`, from a synchronous full-viewport depth-cache read to the owned
`ViewportDepthCacheSession`. A new draw-only `ED_view3d_depth_override_prepare` entry point forces
the stock depth pass even when the View3D override flag is already set, without reading the texture
back synchronously. The existing `ED_view3d_depth_override` entry point and native synchronous
behavior remain unchanged.

When the owned request is immediately ready, both operators continue on the original call stack.
When it is pending, they retain the producing window, screen, area, region, View3D, RegionView3D,
scene, and edit object plus a maximum 256 custom-data-free events. One exact 10 ms timer polls for
at most 240 ticks. Settlement transfers the cache once, finalizes the stock projection state, and
replays the FIFO through the original modal dispatcher. View drift, failure, timeout, Escape,
right-click, unsafe event payload, queue overflow, and external cancellation all remove the timer
and destroy the FIFO and request before returning cancellation. Initial request failure preserves
the stock warning and view-plane fallback.

This closes only the two curve-draw consumers. The synchronous depth-cache family still contains
legacy annotation, Grease Pencil surface placement, object axis-target placement, and particle-edit
callers; WM window capture remains the other synchronous family. No software adapter, device-free
contract, or OFF product binds a live M5 receipt.

## Behavior and source evidence

- The pinned Blender oracle exposes both operators with `wait_for_input=true` and surface projection
  (`20260825T001932-623030`). The unmodified preimage fails the focused source gate before evidence
  allocation (`20260825T002353-625483`).
- Focused Linux receipt `20260825T004848-645324` passes eight contracts and 16 cases byte-for-byte
  under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 538-byte output is
  `sha256:67c46981c31b0561a35f60d909e09aae34c8def02d026c71cc4ceb7a827df830`; the four-source
  postimage is `sha256:d2c1858ea7d5567b72ef2b87226a32bef9e2bca93220da6270a09e7a77d2741c`.
  The matrix covers both operators' native-immediate path, pending non-wait and wait-for-input
  FIFOs, producing-context drift, backend failure and timeout, Escape and external cancellation,
  unsafe payload and queue bounds, and initial view-plane fallback.
- The focused source checker rejects 19 API, forced-redraw, FIFO, context, timeout, transfer,
  dispatcher, and cancellation mutations. The exact native and windowed-Wasm product commands
  compile `view3d_draw.cc`, `editcurve_paint.cc`, and `curves_draw.cc`; both focused build graphs
  end locked no-work.
- Numbered patch 0265 reverses and reapplies all four exact postimages at
  `sha256:415022cbedc64b447a4b49f1a14976da7ff89ae2d10b05d94b8de429c1a3e7e5`.
  Aggregate receipt `20260825T004914-645849` passes the 45-source owned-readback gate with 38
  fail-closed mutations and byte-identical 627-byte native/Wasm output at
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`.

## Integration evidence

- Clean-pin freeze `20260825T004628-643126` reproduces 20,258 manifest entries byte-for-byte.
  `PREVIEW_SNAPSHOT.patch` is 2,115,771 bytes at
  `sha256:b071f59fa4ebe3a504a927dd0cfcf6471a6805a56326901035a7e54dd597ac83`; both manifests are
  `sha256:958bc8e2ca4b94c63955fe337da98cb0194397a6225778e9e480a78a04465f7a`.
  Canonical replay `20260825T004821-644983` binds 287 paths and all 242 active-series identities.
  The optional historical replay remains diagnostic and still stops at the pre-existing patch-0016
  conflict (`20260825T004828-645082`); 0265's isolated reverse/forward proof is green.
- The complete materialized series rebuilds the real `blender_browser` and then ends locked no-work
  (`20260825T004931-647103`/`20260825T005035-647870`). OFF preflight
  `20260825T005047-647999` binds 657,928-byte JavaScript, 118,970,502-byte Wasm, and
  167,143,248-byte data artifacts. Final REUSE 6.2.0 covers 2,429/2,429 files
  (`20260825T005515-652189`).
- Required M5 remains honestly RED only at the absent `blender_browser.deferred.wasm` boundary
  (`20260825T005121-648380`). Container-backed regression `20260825T005134-648504` keeps M0
  6/6 GREEN while M1–M8 retain their existing strict receipt, browser, split-product, hardware,
  run-label, and release boundaries.

Live C1/M5 acceptance remains separately deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). No adapter, browser profile,
split product, live receipt, result promotion, dependency decision, tolerance, golden, blacklist,
or milestone promise changed. dzn and Windows were not attempted, and WSL was not restarted.
