<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 owned depth-cache readback primitive

This device-free contract covers the full-viewport depth-cache request needed by browser paint,
annotation, placement, and particle-edit continuations. `ViewportDepthCacheSession` must own the
exact texture result, preserve the producing region size and view matrices, validate the byte
count before allocation, and transfer one `ViewDepths` result only after settlement. Native
backends may complete immediately; browser WebGPU may return pending without blocking the WM
event loop.

This is an enabler, not a caller conversion or a live WebGPU receipt. The synchronous depth-cache
family remains visible until every consumer owns a bounded kick/poll continuation. WM window
capture remains a separate family, and live M5 acceptance remains hardware-blocked.

Run through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/m5-depth-cache-readback/run.sh
```
