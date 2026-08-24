<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 cursor depth-pick continuation contract

This device-free contract covers the first concrete consumer of the remaining View3D depth-pick
family. `ViewportDepthPickSession` owns one exact framebuffer-depth request, preserves Blender's
0/2/4-pixel progressive auto-distance precedence, and rejects region or view-transform drift
before unprojection. `VIEW3D_OT_cursor3d` retains its exact event coordinate and orientation while
browser WebGPU maps that request across WM-loop ticks. Native completion remains immediate; no-hit
results retain Blender's view-plane fallback; failure, timeout, cancel, or viewport drift cannot
mutate the cursor late.

The contract deliberately does not claim the whole depth-pick family is closed. Navigation,
center-pick, depth-eyedropper, painting, zoom-border/NDOF, the full depth cache, and WM window
capture remain visible in the source receipt and in `ledger/deferred.json`.

Run against a canonical replay source tree through the build wrapper:

```sh
BW_SOURCE_ROOT=/path/to/replayed/source \
  harness/buildwrap.sh bash sandbox/m5-cursor-depth-pick/run.sh
```

Both native and Wasm compilations use `scripts/ninja-locked.sh`. The receipt requires Linux x86_64,
clang++ 17, emcc 6.0.5, pinned Node 22.16.0, byte-identical contract output, a seven-file source
digest, and thirteen fail-closed source mutations. It creates no adapter, browser profile, split product,
live M5 receipt, golden, tolerance, or result promotion.
