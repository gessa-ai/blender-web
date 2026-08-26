<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4 browser focus-transition ordering

The browser main thread can complete `canvas -> page control -> canvas` before
Emscripten delivers the first focus callback to the proxied WM worker. The first
repair preserved that boundary for `processEvents()`, but later proxied key or
pointer callbacks could still enqueue input before the worker polled it. The focus
callback now consumes the capture-time loss before querying the later live DOM.
Because focus and input already share Emscripten's ordered worker callback queue,
the resulting sequence is exactly deactivate, activate, then the later input.

The live test performs both focus changes in one JavaScript task while Control and
left mouse are held, verifies an ordinary blur/refocus emits exactly one transition
pair, and then asserts immediate key and mouse down/up events cannot cross the focus
barrier. The capture bridge still acknowledges losses handled by an ordinary worker
callback and suppresses Blender-owned IME handoffs.

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
