<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 window-colour owned-snapshot contract

This device-free contract binds the non-viewport colour sampler shared by the
regular colour, color-ramp, and Grease Pencil eyedroppers. One owned window
snapshot may complete immediately on native backends or remain pending across
browser event-loop turns. Once ready, the same exact RGBA8 snapshot supplies
arbitrary points without another synchronous GPU read.

The source verifier requires all three modal owners, bounded polling, exact
byte-to-float decoding, retry on window/failure changes, and cancellation before
operator destruction. It also rejects restoring the synchronous offscreen
fallback. The native/wasm32 contract covers immediate and delayed completion,
snapshot reuse, all three consumer roles, exact-size failure and retry,
replacement/cancellation, and timeout.

Run through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/m5-window-color-readback/run.sh
harness/buildwrap.sh bash sandbox/m5-window-color-readback/selfcheck.sh
```

This is source/device-free evidence only. It creates no adapter, browser, pixel
receipt, split product, or M5 promotion.
