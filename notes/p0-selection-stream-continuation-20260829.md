<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J selection stream continuation — 2026-08-29

## Outcome

The deterministic post-`Alt+A` freeze now has a concrete failure source and a relinked candidate.
The first post-deselect click invokes `VIEW3D_OT_select`; its one-draw WebGPU selection output was
destroyed before asynchronous allocation validation could publish a readable buffer. Blender
reported `WebGPU selection readback failed (error 7)` and opened a modal error popup, which then
captured every later orbit/click/key event. This was an input freeze only in its downstream visual
effect: the worker, WM queue, and renderer had not stopped.

Patch `0305-gpu-webgpu-select-stream-continuation.patch` keeps that output in one ordered stream
epoch through clear, draw, and readback. Because the now-valid browser readback is genuinely
asynchronous, the selection modal also retains ordinary input in a bounded FIFO and restores it in
exact order once mapping completes. The current CAPTURE candidate is relinked and device-free
green, but P0-I/J remain open until the driver obtains the required Apple 10/10 visual result and
same-generation hardware gauntlet.

## Root-cause discriminator

The temporary WM/modal trace showed the first orbit itself retiring normally. The following click
started `VIEW3D_OT_select`, then the UI contained a `Report: Error` popup whose body was exactly
`WebGPU selection readback failed (error 7)`
(`ledger/buildlogs/20260829T055411-3851867.log`). Error 7 is
`GPU_READBACK_ERROR_SOURCE_UNAVAILABLE`, emitted when `WGPUStorageBuffer::read_async()` cannot
obtain a source allocation.

Selection without a persistent viewport owns a one-draw `SelectMap`. Its output buffer used the
default dynamic lifetime. On browser WebGPU, `ensure()` began asynchronously validated persistent
allocation, but the draw instance returned and destroyed the wrapper before that allocation could
be published. The read path consulted only the persistent cache, so the exact provisional handle
already owned by the current ordered-queue epoch was invisible. The error popup—not a dead event
loop—then consumed all subsequent ordinary input.

Temporary WM-break/modal/popup instrumentation was removed after establishing this chain. Patch
`0304-view3d-web-rotate-retirement-diagnostic.patch` retains only bounded read-only rotate
invoke/confirm/cancel/terminal/active counters, because those remain useful for the hardware
acceptance discriminator.

## Fix

- `StorageCommon` and `StorageArrayBuffer` now preserve an explicit `GPUUsageType` across initial
  creation, resize, and swap.
- The one-draw `select_output_buf` is `GPU_USAGE_STREAM`.
- `WGPUStorageBuffer::ensure()` maps all frontend usage values and creates stream storage through
  `Buffer::create_transient()` in the active ordered queue scheduler.
- buffer update, pending-update retry, and read use `allocation_get()`, which returns the
  same-epoch provisional allocation when one exists and otherwise retains the persistent behavior.
- while a Web selection continuation is pending, custom/timer events pass through to their owners;
  ordinary events are copied without custom-data ownership into a 512-entry FIFO. Success, escape,
  timeout, particle failure, readback failure, and queue-bound failure all restore retained events
  at the WM queue head in exact FIFO order before teardown.
- the focused producer rejects any selection-readback report and requires every queued/recovery
  orbit to invoke and retire a real `VIEW3D_OT_rotate`. `BW_P0_STATE_ONLY=1` exists only for the
  WSL software-adapter diagnostic and is rejected in Apple hardware mode.

## Evidence

- touched Wasm objects compiled cleanly:
  `ledger/buildlogs/20260829T060352-3858206.log`
- exact FIFO candidate relink:
  `ledger/buildlogs/20260829T061119-3864357.log`
- final identical-content CAPTURE relink and locked no-work check:
  `ledger/buildlogs/20260829T062720-3875396.log`,
  `ledger/buildlogs/20260829T062857-3877148.log`
- focused source/mutation contract: `P0J_SELECT_STREAM_CONTINUATION_SOURCE_PASS` and
  `P0J_SELECT_STREAM_CONTINUATION_SELFCHECK_PASS mutations=12`
  (`ledger/buildlogs/20260829T062538-3874298.log`,
  `ledger/buildlogs/20260829T062538-3874299.log`)
- exact five-file numbered-patch reverse/forward cycle:
  `P0J_PATCH_REVERSE_FORWARD_PASS files=5`
  (`ledger/buildlogs/20260829T062551-3874449.log`)
- canonical clean-pin reconstruction: 305 paths, 20,258 entries, patch SHA-256
  `b1f1edb75c2605756093e91f47db3722c80cda416f06dc2aa889df6cf1f7933c`
  (`ledger/buildlogs/20260829T062610-3874626.log`,
  `ledger/buildlogs/20260829T062657-3875171.log`)
- REUSE 3.3: 2,784/2,784 files compliant
  (`ledger/buildlogs/20260829T062830-3876880.log`)
- rapid and slow/sparse software-adapter state controls have no selection-readback report, page
  error, or lifecycle error. The rapid queue drains with two rotate retirements and the independent
  recovery orbit retires a third; the slow/sparse orbits retire individually
  (`ledger/buildlogs/20260829T061355-3866711.log`,
  `ledger/buildlogs/20260829T061436-3867234.log`). These are explicitly state/counter evidence, not
  pixel or hardware receipts.
- capture-profile and composed-gauntlet fail-closed self-checks are green
  (`ledger/buildlogs/20260829T063011-3879415.log`,
  `ledger/buildlogs/20260829T063004-3879268.log`).
- authoritative container-backed regression restores M0 to 6/6; M1-M8 retain their named strict,
  Apple-pixel, deferred-Wasm, APPLY, and release-product boundaries
  (`ledger/buildlogs/20260829T062924-3877600.log`).

## Candidate identity and closure bar

- `blender_browser.js`: `d3f1140b5d31`
- `blender_browser.wasm`: `7865d7c201ae`
- `blender_browser.wasm.orig`: `cccb4f50e28a` (118,995,705 bytes)
- `blender_browser.data`: `095d0ba748c3`
- `blender_browser.split-build.json`: `e7359d9b6ab4`

The driver must run the exact slow/sparse sequence—boot, view cycle, `A`, `Alt+A`, isolated orbit,
then isolated recovery input—10/10 on Apple hardware. It must also compose two clean interaction
runs with the same-generation P0-E resize receipt through `verify_hardware_gauntlet.py`. Until then,
this is a testable candidate, not hardware closure, and no receipt/profile/APPLY/public-release or
launch claim changes.
