<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 particle-edit depth-cache continuation — 2026-08-25

## Outcome

Commit `32c338a` and patch 0273 move particle click, linked-pick, box, lasso, circle, and
brush-start depth-cache work behind caller-owned continuations. `PE_set_view3d_data` now prepares
or consumes an opaque one-shot session before it builds stack-local `PEData`; no particle-edit
source path calls the synchronous full-cache override. XRAY remains an immediate bypass, and an
immediately ready cache continues on the original native stack.

Pending click extends the existing View3D select owner. Linked-pick has its own identified timer;
box/lasso attach the session to the generic gesture owner; persistent and direct circle execution
retain separate exact owners; brush invoke and recorded-stroke execution delay initialization until
settlement. Producing manager, window, screen, area, region, RegionView3D, View3D, main database,
dependency graph, scene, view layer, object, particle edit, and XRAY identity are checked before the
cache transfers. Circle and brush retain only safe custom-data-free input behind 512- and 256-event
bounds, and every identified poll stops after 240 ticks. Drift, backend/consume failure, unsafe
payload, overflow, timeout, Escape, and external cancellation retire timer, FIFO, and session.

## Source and contract evidence

- The pinned Linux oracle exposes exactly `VIEW3D_OT_select`, `PARTICLE_OT_select_linked_pick`,
  box/lasso/circle, and `PARTICLE_OT_brush_edit`, with their stock public properties and expected
  false headless polls (`20260825T055721-912116`). The patch-0272 predecessor rejects before
  evidence allocation because it has no particle depth-session API
  (`20260825T063223-936417`).
- The post-commit focused receipt `20260825T064636-947776` passes eight native/wasm32 contracts
  and 44 cases byte-for-byte under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 559-byte output is
  `sha256:1e25d3750843dcfb7f09f7f42ebbd770dae6ff5d2e76852c67b05f009e29487d`; the three-source
  postimage is `sha256:d60a54a4b61dcd76b92d2060e759a52f159c1af26affc458f234573a8bb27938`.
  Twenty ownership, ordering, input, bound, and cleanup mutations fail closed. The same receipt
  reverses/reapplies patch 0273 at
  `sha256:abafc6272d7b62a9865513f31cedcc0093f53dfbac71f6d8231aea857d7110e7` and compiles exact
  native and windowed-Wasm product-graph `particle_edit.cc` and `view3d_select.cc` translation
  units.
- Aggregate async-readback receipt `20260825T064916-950503` binds 48 sources and rejects 44
  mutations. Its native/Wasm output remains byte-identical at 627 bytes /
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`, with source
  `sha256:3d0909c8c7da8678a1feef1dbfdfc3c62169880045c2085dd9febb5b5daabbd7`. It retains the
  native synchronous-depth control while reporting exactly `window_capture` as the sole open
  synchronous caller family.

## Integration evidence

- Clean-pin freeze `20260825T063746-940573` reproduces 20,258 source entries with byte-identical
  live/replay manifests at
  `sha256:39bb17825a467d9c1ebac78f96221ee28ea0393a08204a94a85d2767d8ee9e6c`.
  `PREVIEW_SNAPSHOT.patch` is 2,309,812 bytes at
  `sha256:ba8191cbfea3049951593025e5fb368e3379cf14e624b196143d4c5535e6b2b6`.
  Authoritative replay binds 301 canonical paths and 250 active patch identities
  (`20260825T063824-941073`); diagnostic numbered-history remains stopped at the documented old
  entry-0016 boundary and was not used as acceptance evidence.
- The real `blender_browser` rebuild and locked no-work check are green
  (`20260825T063545-938771` / `20260825T063644-940104`). Strict OFF preflight
  `20260825T063704-940264` binds 657,938-byte JavaScript, 118,997,954-byte Wasm, and
  167,143,248-byte data artifacts.
- Repository-wide REUSE 6.2.0 is green for 2,493/2,493 files
  (`20260825T065005-950917`). The six-tier
  hardware-deferral contract retains the exact named blocker after the partial-ledger update
  (`20260825T064844-948727`).
- Required M5 remains honestly red only at the absent
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary
  (`20260825T064844-948752`). Container-backed regression keeps M0 6/6 green while M1–M8 retain
  their existing strict receipt, browser, product, run-label, hardware, and release boundaries
  (`20260825T064854-948857`).

The full-viewport depth-cache caller family is complete at the source/device-free boundary. WM
window capture remains the sole synchronous family, and live C1/M5 acceptance remains separately
deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa
dzn rejected by Dawn). This work creates no adapter, device, browser profile, split product, or
live receipt, and changes no result promotion, dependency decision, tolerance, golden, blacklist,
or milestone promise. dzn and Windows were not attempted, and WSL was not restarted.
