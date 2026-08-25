<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 mouse-release ownership contract

This device-free contract proves that a canvas-owned mouse press receives its terminal release
after the pointer leaves the canvas, without turning unrelated page mouse-up events into GHOST
input. Window-targeted release coordinates are translated back into canvas space, and listener
removal remains paired with the registration target.

Build and serve the real WasmFS + `PROXY_TO_PTHREAD` GHOST harness, then run the focused checks:

```sh
harness/buildwrap.sh platform_web/ghost/harness/build.sh
BLENDER_WEB_SHELL="$PWD/platform_web/ghost/harness" \
  BLENDER_WEB_BIN="$PWD/platform_web/ghost/harness/build" \
  bash scripts/serve-web.sh 8192

.host-tools/bin/python3.13 sandbox/m4-mouse-release-ownership/source_contract.py \
  platform_web/ghost/GHOST_SystemWeb.cc \
  sandbox/m4-mouse-release-ownership/mouse_release_test.mjs \
  sandbox/wgpu-pipeline-integrated-smoke/window_lifecycle_contract.py --selfcheck
BW_HEADLESS=1 tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m4-mouse-release-ownership/mouse_release_test.mjs 8192
```

The browser case is platform behavior evidence only. It binds no WebGPU adapter, profile, pixel,
split product, or milestone receipt.
