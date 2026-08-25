<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 Grease Pencil pen depth-cache continuation

This focused contract binds `GREASE_PENCIL_OT_pen` surface/stroke placement to one operation-owned
full-viewport request. It requires the wait to finish before keyframe duplication, editable-drawing
capture, or layer-transform capture, while preserving Blender's immediate path and initial read
failure fallback.

The source verifier checks the shared post-initialize seam, exact initiating event, bounded safe
event FIFO, producing-context identity, identified 240-tick poll, cleanup, external cancellation,
and removal of both branch-identical synchronous cache reads. Fourteen mutations must fail closed.
The native/wasm32 model exercises 9 contracts and 33 cases byte-for-byte. The receipt also reverses
and reapplies patch 0271 and compiles the exact `curves_pen.cc` and `grease_pencil_pen.cc` product
translation units in the native and wasm graphs.

Run from the repository root:

```sh
harness/buildwrap.sh sandbox/m5-grease-pencil-pen-depth-cache/run.sh
```

This is device-free evidence only. It creates no hardware WebGPU receipt and does not alter the M5
live acceptance blocker.
