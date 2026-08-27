<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 window resize recovery contract

`verify_source.py` binds persistent backbuffer adoption to an explicit refresh of both default
framebuffer extent caches. The integrated first-pixel contract also requires every applied browser
extent to request a redraw after surface reconfiguration and the WM size event, then requires the
asynchronously validated replacement surface/backbuffer commit to start a fresh bounded episode.
`live_resize_repro.mjs` boots the real windowed product, waits past the initial 180-tick recovery
episode, shrinks its canvas from 1280x720 to 1100x640, restores it, and requires both coherent
commit generations, both new bounded redraw episodes, shell resize, WM event processing, uncapped
tick/presentation progress, and zero WebGPU encoding or submission rejection.

With a product server on port 8137:

```sh
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/m4-resize-recovery/verify_source.py
harness/buildwrap.sh env BW_NODE_MODULES="$PWD/.m4-node/node_modules" \
  xvfb-run -a /home/pc/tools-node/node-v22.16.0-linux-x64/bin/node \
  sandbox/m4-resize-recovery/live_resize_repro.mjs 8137
```

The fallback adapter can bind this rejection/recovery contract but cannot bind an M4 pixel
receipt. Final resize pixel recovery remains a conformant-hardware check.
