<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Grease Pencil freehand depth-cache continuation

This focused source/device-free receipt covers the launch-critical freehand
`GREASE_PENCIL_OT_brush_stroke` placement path. It proves that surface and stroke placement start
one owned viewport-depth cache, retain the exact first and generated extension samples, and replay a
sanitized terminal event through the stock `PaintStroke` dispatcher after bounded settlement.

The native/wasm model covers immediate completion, FIFO copy ownership, release/line-end replay,
producing-context drift, backend failure, the 240-tick timeout, the 256-sample bound, cancellation,
and exact-once settlement. The source verifier binds those decisions across the placement helper,
operation interface, modal owner, and freehand paint operation and rejects 12 structural mutations.

Run through the repository build wrapper:

```sh
harness/buildwrap.sh sandbox/m5-grease-pencil-depth-cache/run.sh
```

This receipt does not cover Grease Pencil primitive, fill, or pen-helper placement callers and does
not bind an adapter, browser, split product, or live M5 receipt.
