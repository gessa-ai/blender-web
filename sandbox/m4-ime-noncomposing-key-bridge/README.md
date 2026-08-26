<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 IME non-composing key bridge

This contract covers ordinary keyboard events while Blender's hidden IME textarea owns DOM focus.
The shipping `WITH_INPUT_IME` profile registers key-down/up on both Blender-owned focus elements;
an earlier textarea listener suppresses browser composition process keys before Emscripten proxies
them, so a composition cannot also enter Blender as raw keys. The non-IME profile retains its
14-listener canvas contract, while the shipping profile transactionally owns and retires all 16.

Build and serve the real `PROXY_TO_PTHREAD` worker harness, then run the focused trusted-input case:

```sh
harness/buildwrap.sh platform_web/ghost/harness/build.sh
BLENDER_WEB_SHELL="$PWD/platform_web/ghost/harness" \
  BLENDER_WEB_BIN="$PWD/platform_web/ghost/harness/build" \
  bash scripts/serve-web.sh 8198
harness/buildwrap.sh env BW_HEADLESS=1 \
  tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m4-ime-noncomposing-key-bridge/ime_keyboard_test.mjs 8198
```

The source self-check binds the listener targets, composition suppression, trusted browser case,
and product text-state driver. After a locked product relink, the headed product diagnostic uses
Blender's stock object-name editor and reads the committed name back through its Python Console and
GHOST clipboard path:

```sh
.host-tools/bin/python3.13 \
  sandbox/m4-ime-noncomposing-key-bridge/source_contract.py \
  platform_web/ghost/GHOST_SystemWeb.cc \
  sandbox/m4-ime-noncomposing-key-bridge/ime_keyboard_test.mjs \
  sandbox/m4-ime-noncomposing-key-bridge/product_text_state_test.mjs --selfcheck
xvfb-run -a env BW_HEADED=1 tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m4-ime-noncomposing-key-bridge/product_text_state_test.mjs 8199
```

The product run uses a forced software adapter and is diagnostic-nonreceipt evidence. It binds no
hardware adapter, profile, pixel receipt, result promotion, or milestone promise.
