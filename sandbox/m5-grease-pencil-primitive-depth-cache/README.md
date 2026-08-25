<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Grease Pencil primitive depth-cache continuation

This focused source/device-free receipt covers the shared invoke path used by all six
`GREASE_PENCIL_OT_primitive_*` operators. Surface and stroke placement owns one asynchronous
viewport-depth cache before the first control point is projected. The invoke-time coordinates,
primitive type, subdivision, cursor, producing context, and up to 256 custom-data-free modal events
remain owned behind one 240-tick timer. Settlement initializes the stock navigation, control points,
curve data, preview callback, and modal state exactly once, then replays retained input FIFO.

The native/wasm model covers all six primitive types, immediate and pending initialization,
pre-projection suspension, navigation/event replay, producing-context drift, backend failure, the
timer and event bounds, cancellation, exact-once settlement, and modal teardown. The source verifier
binds those decisions to the one shipping translation unit and rejects 16 structural mutations.

Run through the repository build wrapper:

```sh
harness/buildwrap.sh sandbox/m5-grease-pencil-primitive-depth-cache/run.sh
```

This receipt leaves Grease Pencil fill and pen-helper placement explicit, and does not bind an
adapter, browser, split product, or live M5 receipt.
