<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4 browser focus-transition ordering

The browser main thread can complete `canvas -> page control -> canvas` before
Emscripten delivers the first focus callback to the proxied WM worker. The
predecessor queried the later `document.activeElement`, suppressed the blur, and
left held Blender keys/buttons stuck. The live test performs both focus changes
in one JavaScript task while Control and left mouse are held, then verifies that
an ordinary blur/refocus still emits exactly one transition pair. The fix publishes
a monotonic loss generation from capturing DOM blur, acknowledges losses already
handled by the ordinary worker callback, and suppresses Blender-owned IME handoffs.

Build and run the real worker-topology harness:

```sh
harness/buildwrap.sh platform_web/ghost/harness/build.sh
BLENDER_WEB_SHELL="$PWD/platform_web/ghost/harness" \
  BLENDER_WEB_BIN="$PWD/platform_web/ghost/harness/build" \
  bash scripts/serve-web.sh 18424
BW_HEADLESS=1 tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m4-focus-transition-order/focus_transition_order_test.mjs 18424
```

Run the fail-closed source contract:

```sh
.host-tools/bin/python3.13 sandbox/m4-focus-transition-order/source_contract.py \
  platform_web/ghost/GHOST_SystemWeb.hh \
  platform_web/ghost/GHOST_SystemWeb.cc \
  sandbox/m4-focus-transition-order/focus_transition_order_test.mjs --selfcheck
```
