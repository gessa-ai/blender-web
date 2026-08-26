<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 modifier-side state contract

GHOST modifier state discriminates left and right keys. Browser keyboard events already expose
that physical side through `KeyboardEvent.code`; mouse and wheel events expose only aggregate
modifier flags. This contract requires exact Shift, Control, Alt, and OS key transitions to win,
preserves either or both known sides across aggregate input, and uses left only as the fallback
when no exact key history exists.

The unchanged implementation failed trusted CDP input at its first case: `ShiftRight` generated
the exact right-side key event but `getModifierKeys()` returned mask `1` (left) instead of mask
`2` (right). Run the final source and browser checks with:

```sh
.host-tools/bin/python3.13 sandbox/m4-modifier-side-state/source_contract.py \
  platform_web/ghost/GHOST_SystemWeb.hh platform_web/ghost/GHOST_SystemWeb.cc \
  platform_web/ghost/GHOST_EventBridgeWeb.cc \
  platform_web/ghost/harness/test_ghost_web.cc \
  sandbox/m4-modifier-side-state/modifier_side_test.mjs --selfcheck
harness/buildwrap.sh platform_web/ghost/harness/build.sh
BLENDER_WEB_SHELL="$PWD/platform_web/ghost/harness" \
  BLENDER_WEB_BIN="$PWD/platform_web/ghost/harness/build" \
  bash scripts/serve-web.sh 8191
BW_HEADLESS=1 tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m4-modifier-side-state/modifier_side_test.mjs 8191
```

The live check is browser input evidence only. It binds no WebGPU adapter, pixels, or receipt.
