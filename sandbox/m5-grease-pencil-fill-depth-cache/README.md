<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: GPL-2.0-or-later -->

# Grease Pencil fill depth-cache continuation contract

This focused contract binds the stock `GREASE_PENCIL_OT_fill` owner to one bounded
full-viewport depth-cache phase. Pixel rendering and Delaunay triangulation consume a
caller-owned `DrawingPlacement` only after its cache is ready; neither helper performs a
synchronous read. Non-depth and immediately ready native execution remain on the original stack,
and an initial read failure preserves Blender's existing projection fallback.

The source verifier covers both public helper declarations and implementations plus the operator
owner. Its mutation controls require exact input retention, the producing-context guard, identified
100 Hz polling, the 240-tick bound, ready-only helper dispatch, and complete cancellation. The C++
model exercises the same lifecycle byte-for-byte under native clang and wasm32/Node. The runner
also reverses and reapplies patch 0270 and compiles the exact `draw_ops.cc` and `fill.cc` product
translation units in native and windowed-Wasm graphs.

Run only through the project wrapper:

```sh
harness/buildwrap.sh sandbox/m5-grease-pencil-fill-depth-cache/run.sh
```

This is device-free source evidence. It cannot produce a live browser or hardware receipt.
