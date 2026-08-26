<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 IME focus-ownership contract

This device-free contract treats the canvas and Blender's enabled hidden IME textarea as one
logical GHOST focus domain. Internal begin/end handoffs publish no window activation changes,
while focus moving to an ordinary page control or away from the browser still publishes exactly
one deactivate/reactivate pair.

Build and serve the real WasmFS + `PROXY_TO_PTHREAD` harness, then run the focused checks:

```sh
harness/buildwrap.sh platform_web/ghost/harness/build.sh
BLENDER_WEB_SHELL="$PWD/platform_web/ghost/harness" \
  BLENDER_WEB_BIN="$PWD/platform_web/ghost/harness/build" \
  bash scripts/serve-web.sh 8193

.host-tools/bin/python3.13 sandbox/m4-ime-focus-ownership/source_contract.py \
  platform_web/ghost/GHOST_SystemWeb.hh \
  platform_web/ghost/GHOST_SystemWeb.cc \
  platform_web/ghost/harness/ime_composition_test.mjs --selfcheck
BW_HEADLESS=1 tools/emsdk/node/22.16.0_64bit/bin/node \
  platform_web/ghost/harness/ime_composition_test.mjs 8193
```

The browser run is platform behavior evidence only. It binds no WebGPU adapter, profile, pixel,
split product, or milestone receipt.
