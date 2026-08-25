<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 Grease Pencil pen depth-cache continuation — 2026-08-25

## Outcome

Commit `71f82ec` and patch 0271 move both branch-identical synchronous surface/stroke reads out of
`GREASE_PENCIL_OT_pen` initialization. The operation now starts one owned full-viewport placement
request before it duplicates keyframes, retrieves editable drawings, or captures layer transforms.
The shared curves pen base exposes one narrow post-initialize seam containing its unchanged
first-event work; both the native-immediate path and the deferred Grease Pencil path use that same
seam exactly once.

A genuinely pending request retains the exact custom-data-free initiating event plus up to 256 safe
modal events behind one 100 Hz timer for at most 240 ticks. It guards the producing manager, window,
screen, area, region, RegionView3D, View3D, dependency graph, scene, view layer, object, evaluated
object, Grease Pencil data, active layer, frame, and point-selection mode. Ready settlement runs the
stock keyframe/drawing/transform tail, consumes the initiating event, then replays the FIFO through
the unchanged base modal dispatcher. A queued mouse release therefore preserves stock terminal
semantics. Non-depth and immediately ready requests remain on the original stack, and an initial
read failure retains Blender's existing no-cache projection fallback.

Context drift, later backend failure, timer-allocation failure, timeout, unsafe payload, queue
overflow, Escape, external cancellation, and destruction retire the timer, request, initiating
event, and FIFO before mutable initialization. Pending exit does not touch initialized drawing
state.

## Source and contract evidence

- The pinned Linux oracle retains public `GREASE_PENCIL_OT_pen`, a true poll, and the exact 14
  writable common pen properties (`20260825T044737-852322`). The patch-0270 predecessor fails
  closed before evidence allocation because it owns no continuation state
  (`20260825T045109-854619`).
- The focused receipt (`20260825T050322-863354`) passes nine contracts and 33 cases byte-for-byte
  under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 514-byte output is
  `sha256:98d9831ac3ac02003d39151192763ddac5a49c9cfbecf72ef24e6e9807394f88`; the three-file shipping
  postimage is `sha256:ac8421fc850e57ac90bac9aa8818df130be01aee3e4255e0b407294e79ecbc94`.
  Fourteen ownership, ordering, shared-seam, timer, context, FIFO, and cleanup mutations fail
  closed. The same receipt reverses/reapplies patch 0271 at
  `sha256:4d762b97769ef342b2e4c81a8ae206c5afe77d81993ad420c602e819a6244be6` and compiles the exact
  native and wasm product-graph `curves_pen.cc` and `grease_pencil_pen.cc` translation units.
- Aggregate async-readback receipt `20260825T050406-864531` remains byte-identical at 627 bytes /
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720` and truthfully retains
  exactly the `depth_cache` and `window_capture` synchronous families.

## Integration evidence

- Clean-pin freeze `20260825T045850-859787` reproduces 20,258 source entries with byte-identical
  live/replay manifests at
  `sha256:23981834d59f6d1c75bd9bed9a9305a721bdb1408098aa318ffd5c411d08407f`.
  `PREVIEW_SNAPSHOT.patch` is 2,233,405 bytes at
  `sha256:92b181cf6966a0e8a40a8d333d0c71a22abb4a37b9e2a7afe3cef1a97ecb9b2f`.
  Authoritative canonical replay binds 298 paths and 248 active numbered identities
  (`20260825T050013-861454`). The diagnostic numbered-history mode still stops at pre-existing
  entry 0016, exactly as documented since 2026-08-20; it never reaches patch 0271 and binds no
  evidence for this task.
- The real `blender_browser` relink and locked no-work check are green
  (`20260825T050423-865049` / `20260825T050524-865774`). Strict OFF preflight
  `20260825T050533-865848` binds 657,938-byte JavaScript, 118,985,267-byte Wasm, and
  167,143,248-byte data artifacts.
- Repository-wide REUSE 6.2.0 is green for 2,475/2,475 files
  (`20260825T051201-872000`). The six-tier hardware deferral retains the exact named blocker after
  the partial-ledger update (`20260825T051201-871999`).
- Required M5 remains honestly red only at the absent
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary
  (`20260825T050753-868071`). Container-backed regression restores M0 6/6 green while M1–M8 retain
  their existing strict receipt, browser, product, run-label, hardware, and release boundaries
  (`20260825T050803-868351`).

Object axis-target placement, particle edit, and WM window capture remain explicit synchronous
residuals. Live C1/M5 acceptance remains separately deferred by the named blocker: no conformant
hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This work creates no
adapter, device, browser profile, split product, or live receipt, and changes no result promotion,
dependency decision, tolerance, golden, blacklist, or milestone promise. dzn and Windows were not
attempted, and WSL was not restarted.
