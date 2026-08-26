<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 callback-registration metadata soak

GHOST-web must distinguish callbacks queued by retired HTML5 listener sets without retaining
heap metadata forever. The production path uses a fixed 4,096-byte pool of never-recycled opaque
tokens. Every successful or failed registration attempt consumes one token; exhaustion fails
closed instead of reusing an address that a delayed callback could still carry.

The source contract rejects dynamic registration-record retention, token reuse, early owner
publication, late retirement, and weakened soak assertions. The real WasmFS +
`PROXY_TO_PTHREAD` browser case in `platform_web/ghost/harness/window_lifecycle_test.mjs` holds a
callback across 128 deliberately failed registrations and 256 dispose/replacement cycles, checks
the fixed metadata budget and exact attempt delta, requires DOM listener balance, rejects the
stale callback, and proves fresh input still works.

```sh
.host-tools/bin/python3.13 sandbox/m8-callback-registration-soak/source_contract.py \
  platform_web/ghost/GHOST_SystemWeb.cc \
  platform_web/ghost/harness/window_lifecycle_test.mjs --selfcheck
harness/buildwrap.sh platform_web/ghost/harness/build.sh
BLENDER_WEB_SHELL="$PWD/platform_web/ghost/harness" \
  BLENDER_WEB_BIN="$PWD/platform_web/ghost/harness/build" \
  bash scripts/serve-web.sh 8201
harness/buildwrap.sh env BW_HEADLESS=1 \
  tools/emsdk/node/22.16.0_64bit/bin/node \
  platform_web/ghost/harness/window_lifecycle_test.mjs 8201
```

This is device-free lifecycle/leak evidence. It binds no WebGPU adapter or pixel receipt.
