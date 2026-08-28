<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# P0-I cumulative-interaction diagnostic

`capture_diagnostic.mjs` reproduces the filed 10-orbit, 10-pan, 10-zoom sequence against the real
windowed Wasm product. It couples screenshots to Blender-native workspace, region, scene, and Cube
projection state so an off-screen object is not mistaken for a dropped geometry draw. It also
censuses every hard bind-group completeness warning rather than naming one expected shader. The
post-stress header pass requires nine state-changing workspace clicks while proving that DOM click
and GHOST press coordinates are identical. Moving back into the canvas between transitions
prevents a tooltip from turning the automation's settle delay into a false input failure; the
fallback diagnostic also allows the real workspace layout time instead of queuing later clicks.

The Linux run deliberately exercises the Apple-verified pointer-lock rejection fallback and forces
SwiftShader. It is diagnostic-only and binds no hardware or pixel receipt.

Serve an already-linked product and run the capture plus both contracts:

```sh
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" bash scripts/serve-web.sh 8123
DISPLAY=:0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
  harness/buildwrap.sh node sandbox/p0-interaction-stress/capture_diagnostic.mjs 8123
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/analyze_diagnostic.py
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_source.py --self-check
```

The analyzer requires a running product, semantic pixels through the final orbit, Blender-native
Cube presence, stable three-to-six-second settle pixels, zero page/lifecycle errors, and zero hard
completeness warnings. It also requires all nine post-stress workspace transitions and the full
DOM-to-GHOST button-coordinate canary. An already-active tab is deliberately excluded because it
is not a workspace transition.

The source contract verifies that vertex and index buffers preserve SSBO binding intent while
first-use allocation is pending, and that numbered patch 0297 carries both changes. The original
diagnostic emitted six `gpu_shader_3D_polyline_flat_color` failures with surviving bindings
`[0,1,2,3]`, assembled bindings `[3]`, and missing bindings `[0,1,2]`. A device-free PASS proves the
specific retry contract and does not close P0-I's required Apple-hardware pixel verification.
