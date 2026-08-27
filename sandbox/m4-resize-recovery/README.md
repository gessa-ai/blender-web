<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 window resize recovery contract

`verify_source.py` binds persistent backbuffer adoption to an explicit refresh of both default
framebuffer extent caches. It also requires browser WebGPU to join Metal's established per-frame
drawable reset: a single-window redraw must reactivate its GPU context so `sync_backbuffer()`
adopts a coherently committed replacement texture before any region encodes into the default
framebuffer. The integrated first-pixel contract also requires every applied browser extent to
request a redraw after surface reconfiguration and the WM size event, then requires the
asynchronously validated replacement surface/backbuffer commit to start a fresh bounded episode.
`verify_resize_trace.py` binds that episode to a diagnostic which records the exact resolved target,
viewport, and scissor for every successfully encoded draw, retains dedicated `overlay_background`
and `OCIO_Display` snapshots, and prints one line per successful present under hard per-episode and
process ceilings. Comparing its cumulative sequences across presents distinguishes fresh content
encoding from repeated presentation of a retained backbuffer without inferring liveness from logs.
`live_resize_repro.mjs` boots the real windowed product, waits past the initial 180-tick recovery
episode, shrinks its canvas from 1280x720 to 1100x640, restores it, and requires both coherent
commit generations, both new bounded redraw episodes, shell resize, WM event processing, uncapped
tick/presentation progress, and zero WebGPU encoding or submission rejection. It parses every
captured draw plan rather than accepting the log prefix alone: all/window draw sequences must
advance within each episode, the latest-plan sequence must equal the all-draw count,
`overlay_background` and `OCIO_Display` must each be freshly encoded more than once, every direct
window target must use the committed extent, and every enabled scissor must fit its target.

The Apple trace's `overlay_background=900x547` is not a stale 1100x640 window extent. Live Blender
layout introspection proves that 900x547 is the current `VIEW_3D` window region after shrink (and
that it returns to 1048x621 on restore); this pass intentionally targets an offscreen region while
`OCIO_Display` targets the full window. The remaining stale-pixel mechanism is queue order:
browser validation leaves Blender draw submissions pending in `OrderedQueueScheduler`, while the
old GHOST swap path submitted its backbuffer-to-surface blit immediately. The backend now registers
that blit as a queued operation at `swapBufferRelease()`, after every draw/write already recorded for
the frame. Its acquire, encode, and submit still execute synchronously within the eventual browser
callback turn so the swapchain texture cannot expire. The standalone GHOST harness retains its
immediate path because it has no Blender backend scheduler.

With a product server on port 8137:

```sh
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/m4-resize-recovery/verify_source.py
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/m4-resize-recovery/verify_resize_trace.py --selfcheck
harness/buildwrap.sh env BW_NODE_MODULES="$PWD/.m4-node/node_modules" \
  xvfb-run -a /home/pc/tools-node/node-v22.16.0-linux-x64/bin/node \
  sandbox/m4-resize-recovery/live_resize_repro.mjs 8137
```

The fallback adapter can bind this rejection/recovery contract but cannot bind an M4 pixel
receipt. Final resize pixel recovery remains a conformant-hardware check.

`hardware_resize_acceptance.mjs` is that hardware-only check. It preserves the driver's calibrated
fixed VIEW_3D sample box and `dominant_fraction < 0.95` decision, but removes the saved script's
machine-local module paths and adds the project's current hardware-adapter contract, exact pinned
Node/Playwright/PNGJS/Chromium identities, an expected `.wasm.orig` hash, confined immutable
evidence, and fail-closed page/WebGPU-error accounting. It uses ten fresh browser contexts. Each
attempt establishes a visible baseline, dismisses the splash, shrinks 1280x720 to 1100x640, then
sends no further input while polling for at most 24 seconds. Every boot, baseline, and shrink image
is retained so the semantic decision can be visually audited for the grid, Cube, and gizmo.

The browser-free self-check runs on either host:

```sh
harness/buildwrap.sh env BW_NODE_MODULES="$PWD/.m4-node/node_modules" \
  node \
  sandbox/m4-resize-recovery/hardware_resize_acceptance.mjs --selfcheck
```

The driver-operated conformant host runs the live bar against an already-served exact product:

```sh
node sandbox/m4-resize-recovery/hardware_resize_acceptance.mjs \
  --port 8165 \
  --run apple-ordered-present-r1 \
  --expected-wasm-orig-sha256 <exact-64-hex-generation>
```

Only `BW_P0E_HARDWARE_RESIZE_PASS attempts=10/10` plus the immutable `receipt.json` and ten shrink
images can close P0-E. A self-check, software adapter, or fewer than ten clean attempts cannot.
