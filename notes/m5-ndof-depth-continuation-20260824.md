<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 NDOF depth continuation — 2026-08-24

## Outcome

NDOF orbit-center selection no longer performs a synchronous framebuffer-depth read on the
browser WM worker. Patch 0263 preserves Blender's bounds-first choice and yields only when that
choice falls through to the stock region-relative rectangle. The continuation owns the exact
clamped rectangle, applies the stock row-major strict-nearest reduction, and retains the producing
window, screen, area, region, View3D, RegionView3D, matrices, camera state, clipping, grid, locks,
NDOF mode, and NDOF flags until settlement.

The starting `wmNDOFMotionData` and every later NDOF motion are copied into owned storage instead
of retaining window-manager custom-data pointers. Up to 256 motions replay FIFO after the request
settles; a later starting motion may transfer the remaining FIFO into its own request. Native-ready
execution remains immediate. Invalid payloads, queue overflow, producing-view drift, Escape,
backend failure, the 240-tick timeout, and external cancellation remove the exact timer and cancel
the GPU ticket before freeing state.

This closes the depth-pick caller family at the source/device-free boundary. Depth cache and WM
window capture are the two remaining synchronous readback families. No live adapter, browser,
profile, split product, result promotion, tolerance, golden, blacklist, or milestone promise
changed.

## Behavior and source evidence

- The pinned native oracle reports that the NDOF operators do not poll in background mode and
  exposes no operator properties beyond `rna_type` (`20260824T225603-552473`). Behavior is bound
  through the pinned stock source and the device-free continuation model rather than a fabricated
  headless device event.
- Focused Linux receipt `20260824T231821-569100` passes eight contracts and 20 cases byte-for-byte
  under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 392-byte output is
  `sha256:653fe8a6652da3618ae95a9e2d3abd51e06493a92cfa0fcfa3479a5db77ffcdf`; the six-source
  postimage is `sha256:3b4878bcf9bddf1d4de45043872fde46e510d746ee025cbf88f702aa67cc6535`.
- The source checker rejects eight ownership, request, FIFO, lifecycle, and callback mutations.
  Numbered patch 0263 reverses and forwards the three exact postimages at
  `sha256:74026ddc853fce55277d4bcae3b1f2bb2002342f17de24ae22fda755eddb04a7`.
- Aggregate receipt `20260824T231848-569669` passes the 43-source owned-readback census on native
  and wasm32 at 627 bytes, `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`.
  Its source receipt reports NDOF converted and exactly `depth_cache` plus `window_capture`
  remaining, while `live_hardware_receipt` remains false.

## Integration evidence

- The clean-pin freezer receipt `20260824T231711-568324` composes 285 paths and reproduces 20,258
  manifest entries byte-for-byte. `PREVIEW_SNAPSHOT.patch` is 2,078,099 bytes at
  `sha256:8c6b3abc0d97013ad56352279cdd4a5625544bf09fe44d5bd53bd4334c839424`; both manifests are
  `sha256:5ffdc4bd9a0d89764d701222ea5df83bd62d7fd3aa3c195a07b2d25db8bfc02b`.
- The reconstructed NDOF and generic navigation translation units compile with the exact native
  and windowed-Wasm graph commands and an explicit `WITH_INPUT_NDOF` definition in the focused
  receipt. The immutable-upstream `blender_browser` graph and its dry run remain locked no-work
  (`20260824T232123-572169`/`20260824T232128-572378`). OFF preflight
  `20260824T232138-572471` binds the existing 657,928-byte JavaScript, 118,955,345-byte Wasm, and
  167,143,248-byte data artifacts.
- Repository-wide REUSE 6.2.0 is GREEN for 2,411/2,411 files
  (`20260824T232200-572662`). Required M5 remains honestly RED only at the absent
  `blender_browser.deferred.wasm` boundary (`20260824T232217-572885`). Container-backed regression
  `20260824T232226-572997` restores M0 6/6 GREEN while M1–M8 retain their existing strict-receipt,
  browser, split-product, hardware, run-label, and release boundaries.

Live C1/M5 acceptance remains separately deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). dzn and Windows were not
attempted, and WSL was not restarted.
