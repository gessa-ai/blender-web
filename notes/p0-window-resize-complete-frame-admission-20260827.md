<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E complete resize-frame admission candidate — 2026-08-27

## Outcome

Commit `a8f6c43` makes a resized surface present only a complete frame for the adopted backbuffer
episode. Patches 0291–0293 carry one full-area redraw through screen relayout, admit only a
same-frame VIEW_3D background/display composite at the queue tail, and establish the actual
`WGPUContext::begin_frame()` as the sole semantic trace reset boundary. GHOST withholds ordinary
surface copies while a bounded resize episode is waiting for such a frame, so a chrome-only,
window-only, empty, or partially rebuilt persistent backbuffer cannot become the visible result.

This supersedes the candidate's initial reset placement. `WGPUContext::activate()` may run several
times while Blender encodes one WM window frame. Resetting from its backbuffer snapshot erased the
early `overlay_background` draw on every activation and left only the final 23–25 commands at the
tail. The bounded fallback diagnostic showed cumulative sequence numbers advancing by about 331
per retry while every snapshot still reported `background=0`; the barrier correctly rejected all
of those corrupted snapshots and therefore exposed the boundary error. Activation still adopts
the texture, extent, format, and episode atomically. Only `begin_frame()` clears the frame-local
semantic facts, and later activations cannot discard already encoded region evidence.

## Evidence

- The first fail-first source run rejects the absent complete-frame schedule and present
  suppression (`20260827T173223-2279071`); the paired trace test also rejects the old surface
  (`20260827T173223-2279072`). The intermediate contracts then pass the 61-mutation redraw model
  and 80-check/47-mutation source boundary (`20260827T173318-2279485`,
  `20260827T173353-2280375`).
- The exact fallback diagnostic against that intermediate build emits repeated
  `frame_draws=23–25` and `background=0` snapshots even as sequences advance by hundreds, then
  fails with zero accepted barriers (`20260827T174027-2284927`). This directly identifies a reset
  inside the frame rather than absent drawing or absent retry.
- The frame-boundary fail-first rejects both activation-time reset and an absent real
  `begin_frame()` reset (`20260827T174214-2286331`). The final source verifier passes six sources,
  80 checks, and 47 mutations (`20260827T174307-2287370`).
- The locked CAPTURE relink completes at `20260827T174403-2288075`. The exact fallback product then
  shrinks and restores with ticks `246/525/618`, presents `16/17/18`, episodes `0/1/2`, two
  accepted barriers, zero incomplete admissions, and two complete/current/contained/VIEW_3D-bound
  traces, with no scissor, encode, submission, transaction, or device-loss failure
  (`20260827T174508-2288582`). This is software-adapter diagnostic evidence only.
- The native/wasm32 integrated GPU suite is byte-identical, canonical-only replay passes 270
  patches at canonical SHA-256 `bab25dbebfe29d6d46aa784efb8debffc664cc51a939769481e13ec7d2818d27`,
  and final REUSE 6.2.0 covers 2,745/2,745 files (`20260827T174615-2289884`,
  `20260827T174615-2289894`, `20260827T175408-2296902`). CAPTURE preflight, locked no-work,
  hardware producer 42/17, independent consumer 2/13, and capture-profile 21/23 self-checks are
  green (`20260827T174731-2291738` through `20260827T174731-2291762`).
- Required M4 remains red for the absent exact-generation accepted hardware binding
  (`20260827T175006-2293663`). Pinned-oracle regression restores M0 6/6 and leaves M1–M8 red only
  at their existing strict receipt, APPLY/product, hardware, and run-label boundaries
  (`20260827T175010-2293716`).

## Relinked CAPTURE generation

- `blender_browser.js`: 707,565 bytes,
  `52a9a025783071e959daf55d0c07772d9a737220d13b524df9d07abc8ac5f2f0`
- `blender_browser.wasm`: 120,511,178 bytes,
  `69b2f10ebac7fe9ae86ad0e230ea8e4ea414e76e0c662a76600128d2b4c53a11`
- `blender_browser.wasm.orig`: 119,157,853 bytes,
  `505702dbf41ce0a9552f47e6a78ff9f10562c068c9471a35031835b33e9c062c`
- `blender_browser.data`: 168,637,598 bytes,
  `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c`
- `blender_browser.split-build.json`: 13,251 bytes,
  `10b181385e609313a07c59f936e34be892cc5cdb9d9a2fb526cd7c1bd2097788`

## Hardware closure and release boundary

The driver subsequently bound this exact generation (`blender_browser.wasm.orig`
`505702dbf41ce0a9552f47e6a78ff9f10562c068c9471a35031835b33e9c062c`) to the Apple M4 Pro
pixel run. The standing zero-input shrink bar passes 10/10 fresh contexts in about 10.8–11.1
seconds per repaint; every result contains the full grid, shaded Cube, camera, light, panels, and
navigation gizmo, with zero page errors or WebGPU rejections. A separate six-cycle shrink/grow
stress run paints 1100x640, 1280x720, 900x550, 1280x720, 700x500, and 1280x720 without input, then
continues to produce a semantic pixel delta on orbit. P0-E is closed on hardware.

Commit `7ea0093` removes the later unverified runtime experiment and restores this accepted source
tree. The locked relink at `20260827T183234-2327996` reproduces all five artifact sizes and hashes
listed above byte-for-byte; CAPTURE preflight and locked no-work pass. CAPTURE remains diagnostic
and nonshipping. No current success/terminal profile pair is bound to this exact original, so the
hash-bound APPLY relink, public bundle, final `v0.1.1` tag, hardware staged receipt, and launch
claim remain unavailable until the driver returns those profiles.
