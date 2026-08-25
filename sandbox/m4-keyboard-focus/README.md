<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 canvas keyboard-focus contract

This device-free contract proves that raw keyboard events reach GHOST only while the focusable
canvas owns DOM focus. It pairs an eight-mutation source check with the real WasmFS +
`PROXY_TO_PTHREAD` GHOST browser harness. The browser case first requires a focused key event,
moves focus to an ordinary DOM button, and then rejects any GHOST key-down/up delivery.

Build and serve the standalone harness, then run the checks:

```sh
harness/buildwrap.sh platform_web/ghost/harness/build.sh
BLENDER_WEB_SHELL="$PWD/platform_web/ghost/harness" \
  BLENDER_WEB_BIN="$PWD/platform_web/ghost/harness/build" \
  bash scripts/serve-web.sh 8191

.host-tools/bin/python3.13 sandbox/m4-keyboard-focus/source_contract.py \
  platform_web/ghost/GHOST_SystemWeb.cc \
  sandbox/m4-keyboard-focus/keyboard_focus_test.mjs \
  platform_web/ghost/harness/window_lifecycle_test.mjs --selfcheck
BW_HEADLESS=1 tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m4-keyboard-focus/keyboard_focus_test.mjs 8191
```

The check is browser/runtime evidence only. It binds no WebGPU adapter or M4 pixel receipt.
