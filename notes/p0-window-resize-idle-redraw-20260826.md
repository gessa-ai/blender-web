<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E window resize idle-redraw recovery — 2026-08-26

## Outcome

Browser extent application now re-arms the existing bounded WebGPU redraw-recovery episode after
the surface is reconfigured and `GHOST_kEventWindowSize` is queued. A resize therefore produces
ordinary full-screen `GHOST_kEventWindowUpdate` events at idle instead of leaving the new-extent
frame blank until unrelated user input.

This is implemented and device-free verified, not hardware-closed. The local adapter is
SwiftShader and cannot bind semantic M4 pixels. The driver-operated Apple M4 Pro must still show
nonblank Blender pixels after shrink and restore with zero intervening input.

## Fix and boundedness

`GHOST_SystemWeb::processEvents()` is the single consumer that applies a shell-posted backing
generation to the worker-owned `OffscreenCanvas`. Immediately after `reconfigureSurface()` and the
WM size event, it now calls `ghost_web::request_redraw_retry()`.

This reuses P0-D's existing recovery contract. A completed episode is re-armed, the next tick
requests an immediate update, later updates occur every 12 ticks, and the episode remains capped at
180 ticks. A resize during an already-active episode requests an immediate update without resetting
that episode's ceiling.

The live regression waits beyond the boot episode before resizing. It then requires at least eight
uncapped presentations in each resize epoch, continued WM resize/tick progress, and zero scissor,
encode, submit, transaction, or device-loss failures. Presentation counts here prove that the baked
product consumed the bounded update requests; they are not used as semantic-pixel evidence.

## Evidence

- Predecessor source rejection: `20260826T083813-580578` fails because the applied-resize block has
  no redraw-retry publication.
- Final native/Wasm integration: `20260826T083045-572489` passes the 15-case bounded behavior
  matrix and the six-source/30-mutation contract with `resize=rearmed`.
- Locked CAPTURE relink and exact no-work replay: `20260826T083105-573801` and
  `20260826T083231-575256`.
- Exact-product fallback run: `20260826T083654-579809` reports
  `ticks=246/495/744`, `presents=14/29/48`, `redrawPresents=15/19`, three applied backing
  generations, two processed WM resizes, and zero rejection/loss counters.
- CAPTURE inventory, producer self-check (`positive=21`, `negative=23`, zero browser launches),
  and two-phase source contract: `20260826T083416-577116`, `20260826T083416-577117`, and
  `20260826T083416-577121`.
- Pinned REUSE 6.2.0: `20260826T083915-581734`.
- Required M4 remains honestly RED at the hardware receipt boundary
  (`20260826T083437-577250`). Container-backed regression restores M0 to 6/6 GREEN while M1–M8
  retain their strict receipt/APPLY/browser/release boundaries (`20260826T083500-577738`).

Implementation commit: `8744f4f`.

## CAPTURE identity and hardware closure

The relinked CAPTURE generation is non-shipping and has no deferred shard:

- `blender_browser.wasm`: 120,496,023 bytes,
  SHA-256 `bfda545b97817573385958576c0ee5d88e1eb06e6a230a61c60dc81d3fcef80a`;
- `blender_browser.wasm.orig`: 119,142,918 bytes,
  SHA-256 `c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`;
- `blender_browser.js`: 707,146 bytes,
  SHA-256 `901fa6ac74f0caa8f133b054ca0e0ba5edc894c80710867030d70ab79b999fa9`;
- `blender_browser.data`: 167,143,248 bytes,
  SHA-256 `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`.

This relink intentionally invalidates every earlier provisional profile. Against this exact
generation, the Apple rig must boot at 1280x720, shrink to 1100x640, and restore to 1280x720 with
no input after either resize; each idle screenshot must retain semantic Blender UI/viewport pixels.
It must also rerun both sanctioned CAPTURE scenarios for P0-F and return strict PASS receipts before
the profiles can authorize APPLY.
