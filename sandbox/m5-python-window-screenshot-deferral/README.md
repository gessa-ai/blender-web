<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 Python window-screenshot browser deferral

`Window.screenshot()` has a stock synchronous `memoryview` return contract. That contract cannot
suspend the window-manager worker while WebGPU maps its capture without JSPI or Asyncify: blocking
the worker also blocks delivery of the map completion. The browser build therefore preserves the
method and argument parsing but raises an actionable `RuntimeError`; native builds retain the exact
synchronous capture, crop, alpha, and owned-memoryview implementation. Browser scripts can use the
already-owned `bpy.ops.screen.screenshot()` continuation for file capture.

The focused receipt replays the canonical postimage from the pinned Blender commit, reverses and
reapplies patch 0275, rejects source mutations, and compiles the real `bpy_rna_wm.cc` translation
unit from both the native and windowed-wasm product graphs. Symbol and string inspection proves the
native object retains `WM_window_pixels_read`, while the wasm object excludes that call and embeds
the browser-specific error.

Run through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/m5-python-window-screenshot-deferral/run.sh
harness/buildwrap.sh bash sandbox/m5-python-window-screenshot-deferral/selfcheck.sh
```

This is a disclosed API deferral, not a converted asynchronous memoryview API and not a browser or
hardware receipt.
