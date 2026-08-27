<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 window resize recovery contract

`verify_source.py` binds persistent backbuffer adoption to an explicit refresh of both default
framebuffer extent caches. It also requires browser WebGPU to join Metal's established per-frame
drawable reset: a single-window redraw must reactivate its GPU context so `sync_backbuffer()`
adopts a coherently committed replacement texture before any region encodes into the default
framebuffer. The source contract binds that activation through `sync_backbuffer()` and requires
`wm_window_make_drawable()` to precede `GPU_context_begin_frame()`, so the frame-episode barrier
cannot be labeled before the replacement drawable and cached extents have actually been adopted.
Texture, format, extent, and committed redraw episode are read through one GHOST
`BackbufferFrameSnapshot` under one callback-lifetime execution token. Individually guarded
getters are insufficient: an `AllowSpontaneous` resize completion may commit between them and
pair the previous texture with the replacement episode, admitting an untouched backbuffer at the
completed-frame barrier.
The integrated first-pixel contract also requires every applied browser extent to
request a redraw after surface reconfiguration and the WM size event, then requires the
asynchronously validated replacement surface/backbuffer commit to start a fresh bounded episode.
The source verifier distinguishes Blender's per-window `GPU_context_end_frame()` hook from the
later backend-wide `GPU_render_end()`: it requires complete offscreen/onscreen encoding, then the
context queue-tail hook, then GHOST's synchronous `swapBufferRelease()`. This call order is what
makes the completed-frame barrier a real frame tail rather than an empty or post-present marker.
It also binds the synthetic `GHOST_kEventWindowUpdate` used by the ready barrier to Emscripten's
`NC_SCREEN | NA_EDITED` notifier before the ordinary window notifier. A present-only or
chrome-only update cannot therefore satisfy the source contract while leaving the replacement
backbuffer's `VIEW_3D` regions untouched.
`verify_resize_trace.py` binds that episode to a diagnostic which records the exact resolved target,
viewport, and scissor for every successfully encoded draw, retains dedicated `overlay_background`
and `OCIO_Display` snapshots, and prints one line per successful present under hard per-episode and
process ceilings. The browser backend captures that snapshot at the exact resized-frame tail and
stores it with the ordered-queue barrier. The later synthetic WindowUpdate may encode another
frame while the barrier is ready, but those mutable later plans cannot overwrite the diagnostic
for the completed backbuffer actually admitted to presentation. GHOST withholds interim surface
copies until every earlier scoped submission has settled, then performs exactly one synchronous
present while the barrier holds later queue work. The actual
surface acquire/encode/submit remains inside `swapBufferRelease()`; it is never deferred across a
WM frame or browser turn. The native/Wasm integration also drives both rejection boundaries: a
failed prior-frame submission must cancel the waiting barrier and drain the next epoch, while a
failed synchronous surface present must release later-epoch work and leave the same resize episode
retryable. Neither transient failure may strand GHOST in permanent present suppression.
It also covers the two resize-drag supersession windows: a replacement extent arriving before the
old barrier reaches the queue head, and one arriving after that barrier is ready but before GHOST
presents it. In both cases the obsolete completion fails exactly once, the replacement epoch
drains, and a stale GHOST completion cannot retire the replacement barrier.
`live_resize_repro.mjs` boots the real windowed product, waits past the initial 180-tick recovery
episode, shrinks its canvas from 1280x720 to 1100x640, restores it, and requires both coherent
commit generations, both new bounded redraw episodes, shell resize, WM event processing, uncapped
tick/presentation progress, exactly one successful barrier per resize, and zero WebGPU encoding or
submission rejection. It parses the captured completed-frame draw plan rather than accepting the
log prefix alone: the latest-plan sequence must equal the all-draw count, `overlay_background` and
`OCIO_Display` must both have encoded before the admitted present, every direct window target must
use the committed extent, and every enabled scissor must fit its target. A
focused Blender Python marker also publishes the live `VIEW_3D` area's `WINDOW` region after each
WM relayout. Every `overlay_background` plan must remain offscreen and match that region's exact
extent/viewport, while every `OCIO_Display` plan must remain a direct full-window draw.

The Apple trace's `overlay_background=900x547` is not a stale 1100x640 window extent. Live Blender
layout introspection proves that 900x547 is the current `VIEW_3D` window region after shrink (and
that it returns to 1048x621 on restore); this pass intentionally targets an offscreen region while
`OCIO_Display` targets the full window. A later experiment routed the surface blit through the
backend's asynchronous ordered queue, but that generation hard-aborted during boot on 10/10 Apple
hardware attempts. The current barrier orders the already-completed backend frame before a
still-synchronous GHOST surface copy, preserving the safe boundary without presenting an
intermediate persistent-backbuffer state.

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
evidence, and fail-closed page/WebGPU-error accounting. Every canonical product file and retained
boot/baseline/shrink image is recorded by exact byte count and SHA-256. It uses ten fresh browser
contexts. Each
attempt establishes a visible baseline, dismisses the splash, shrinks 1280x720 to 1100x640, then
sends no further input while polling for at most 24 seconds. A shrink passes only after three
consecutive non-flat samples, so one transient good frame followed by the stale overlay cannot
false-green the run. Every boot, baseline, and shrink image is retained so the semantic decision
can be visually audited for the grid, Cube, and gizmo.

Any failed attempt also writes an immutable `NN-diagnostics.json` sidecar. It snapshots the
uncapped WM tick, presentation, and resize-episode counters immediately before and after the
shrink, plus the already-bounded `WGPUWeb-resize`, `WGPUWeb-resize-trace`, and
`WGPUWeb-resize-present-barrier` console lines. The diagnostic window opens at the exact
zero-input resize boundary, excluding boot warmup, and also retains post-resize bind-group
completeness failures. The 128-line total remains hard-bounded, but resize/trace/barrier lines
displace completeness warnings if a warning storm fills the cap; warnings can never hide the
completed-frame mechanism evidence. Passing runs emit no sidecars, so the independent
accepted-receipt inventory stays unchanged. These failure-only records distinguish a missing
barrier present from a successful present of stale or empty backbuffer content, and show whether
that admitted frame had a known dropped draw, without another product relink.

`verify_hardware_resize_receipt.mjs` is the independent post-capture consumer. It re-hashes the
current CAPTURE product, producer source, and all 30 images; decodes every PNG and replays the
calibrated ROI decision; requires the exact accepted hardware adapter and pinned browser stack;
and rejects any missing/extra evidence file, nonzero post-resize input/error, unstable attempt, or
stale generation. Its self-check includes stale-product, altered-image, flat-frame, and unexpected-
inventory mutations.

The browser-free self-check runs on either host:

```sh
harness/buildwrap.sh env BW_NODE_MODULES="$PWD/.m4-node/node_modules" \
  node \
  sandbox/m4-resize-recovery/hardware_resize_acceptance.mjs --selfcheck
harness/buildwrap.sh env BW_NODE_MODULES="$PWD/.m4-node/node_modules" \
  node \
  sandbox/m4-resize-recovery/verify_hardware_resize_receipt.mjs --selfcheck
```

The driver-operated conformant host runs the live bar against an already-served exact product:

```sh
node sandbox/m4-resize-recovery/hardware_resize_acceptance.mjs \
  --port 8165 \
  --run apple-ordered-present-r1 \
  --expected-wasm-orig-sha256 <exact-64-hex-generation>

node sandbox/m4-resize-recovery/verify_hardware_resize_receipt.mjs \
  --evidence sandbox/m4-resize-recovery/hardware-evidence/apple-ordered-present-r1 \
  --expected-wasm-orig-sha256 <exact-64-hex-generation>
```

Only `BW_P0E_HARDWARE_RESIZE_PASS attempts=10/10` plus
`BW_P0E_HARDWARE_RESIZE_RECEIPT_PASS attempts=10/10`, the immutable `receipt.json`, and ten shrink
images can close P0-E. A self-check, software adapter, or fewer than ten clean attempts cannot.
