<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 view-center depth continuation contract

This device-free contract covers `VIEW3D_OT_view_center_pick`, the second concrete consumer of
the remaining View3D depth-pick family. The operator owns its shared progressive depth request
across browser event-loop ticks, retains the exact event coordinate and smooth-view duration,
and applies either the stock depth hit or simple-pan fallback only while the producing viewport
state remains unchanged. Supersession, failure, timeout, Escape, cancellation, and context drift
retire the request without starting a stale smooth-view transition.

Run against a canonical replay source tree through the build wrapper:

```sh
BW_SOURCE_ROOT=/path/to/replayed/source \
  harness/buildwrap.sh bash sandbox/m5-center-depth-pick/run.sh
```

The receipt requires Linux x86_64, clang++ 17, emcc 6.0.5, pinned Node 22.16.0, byte-identical
native/wasm32 behavioral output, twelve fail-closed source mutations, and exact reverse/forward
replay of numbered patch 0257. It creates no adapter, browser profile, split product, live M5
receipt, golden, tolerance, or result promotion.
