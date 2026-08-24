<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 zoom-border depth continuation — 2026-08-24

## Outcome

Zoom to Border no longer performs a synchronous framebuffer-depth read on the browser WM worker.
Patch 0262 owns the exact rectangle request, preserves Blender's in-place viewport clamp and strict
nearest-depth reduction, and transfers a pending request from the generic box gesture into a bounded
operator continuation. Native-ready execution remains immediate. Browser settlement replays the
captured zoom direction and smooth duration only if the producing window, area, region, view
matrices, camera state, clip/grid/lens settings, smooth state, and view locks still match.

Perspective no-hit still reports `Depth too large` and cancels; orthographic no-hit still takes the
stock screen-delta fallback. New same-window/region requests supersede older ones. Supersession,
view drift, Escape, gesture cancellation, timeout, backend failure, and external cancellation all
unlink the owner, remove its timer, and cancel the GPU ticket before freeing state.

Only NDOF remains synchronous inside the depth-pick family. The aggregate partial deferral remains
three families because depth cache and WM window capture are separate unresolved families. No live
adapter, browser, profile, split product, result promotion, tolerance, golden, blacklist, or
milestone promise changed.

## Behavior and source evidence

- The pinned native oracle reports `VIEW3D_OT_zoom_border.poll() == false` in background mode and
  exposes the exact border/zoom properties; the UI behavior is therefore bound through the pinned
  stock source plus the device-free continuation model rather than a fabricated headless action.
- Focused Linux receipt `20260824T223725-538489` passes eight contracts and 20 cases byte-for-byte
  under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 369-byte output is
  `sha256:188bb536b90b7f189af0cf076b7bc80a0d19767b9f1f60b31a0964b2a8aff96d`; the four-source
  postimage is `sha256:ff9475ba15b5325140c114eb813a76bd88af33fe288d309718eef52b9402ba86`.
- The source checker rejects 15 clamp, request, nearest-depth, captured-state, gesture-handoff,
  timer, timeout, passthrough, cleanup, and callback-wiring mutations before allocating evidence.
  Numbered patch 0262 reverses and forwards one exact postimage at
  `sha256:0c4c5394cbb3342154f14f2e622bf033d91dea98b875d79baa639640f410845b`.
- Aggregate receipt `20260824T223702-537136` passes the 42-source owned-readback census on native
  and wasm32 at 627 bytes, `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`.
  It reports exactly `depth_pick`, `depth_cache`, and `window_capture`, with Zoom to Border converted
  and NDOF still visible as the depth-pick residual.

## Integration evidence

- The clean-pin canonical freezer composes 284 paths and reproduces 20,258 manifest entries
  byte-for-byte. `PREVIEW_SNAPSHOT.patch` is 2,051,539 bytes at
  `sha256:521f7a610164cfb6420abb6ef268dc138c49bf14dc042d455a3e9ada45f5427a`; both manifests are
  `sha256:11411c750dcdd9ad25a3750db160396eba2ab019c7efa87b8fe19eb44f469af1`.
- The reconstructed production translation unit compiles with the exact native and windowed-Wasm
  graph commands in the focused receipt. The immutable-upstream `blender_browser` graph rebuilds
  successfully (`20260824T223742-538960`) and then ends locked no-work
  (`20260824T223844-539467`). OFF preflight `20260824T224313-543065` binds the existing 657,928-byte
  JavaScript, 118,955,345-byte Wasm, and 167,143,248-byte data artifacts.
- Required M5 remains honestly RED at the absent `blender_browser.deferred.wasm` boundary. Final
  container-backed regression at `2026-08-24T22:40:34Z` restores M0 6/6 GREEN while M1–M8 retain
  their existing strict-receipt, browser, split-product, hardware, run-label, and release boundaries.

Live C1/M5 acceptance remains separately deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). dzn and Windows were not
attempted, and WSL was not restarted.
