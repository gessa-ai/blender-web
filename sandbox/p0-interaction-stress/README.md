<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# P0-I/J cumulative-interaction diagnostic and Apple acceptance producer

`capture_diagnostic.mjs` reproduces the filed 10-orbit, 10-pan, 10-zoom sequence against the real
windowed Wasm product. It couples screenshots to Blender-native workspace, region, scene, and Cube
projection state so an off-screen object is not mistaken for a dropped geometry draw. It also
censuses every hard bind-group completeness warning rather than naming one expected shader. The
post-stress header pass requires nine state-changing workspace clicks while proving that DOM click
and GHOST press coordinates are identical. Moving back into the canvas between transitions
prevents a tooltip from turning the automation's settle delay into a false input failure; the
fallback diagnostic also allows the real workspace layout time instead of queuing later clicks.

Before that broader battery, schema v2 replays the driver's tighter total-freeze isolation:
Numpad 1/3/7/0/4, Select All, Deselect All, MMB orbit, trusted Cube click, `G X 2` plus undo, and a
second MMB orbit. Each changing view is coupled to settled Blender-native perspective/rotation and
new pixels. Each orbit must advance the read-only `_bw_redraw_retry_count` generation and change
the canvas within the 12-second bounded recovery ceiling; the measured settle time is retained.
Hardware must select exactly Cube through the trusted viewport click. SwiftShader may cancel its
known asynchronous failed GPU pick, use Select All only as a liveness canary, then restore Cube-only
selection through a real, coordinate-checked Outliner click before visual comparison begins.

The default Linux run deliberately exercises the Apple-verified pointer-lock rejection fallback
and forces SwiftShader. It is diagnostic-only and binds no hardware or pixel receipt.

Serve an already-linked product and run the capture plus both contracts:

```sh
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" bash scripts/serve-web.sh 8123
DISPLAY=:0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
  harness/buildwrap.sh node sandbox/p0-interaction-stress/capture_diagnostic.mjs 8123
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/analyze_diagnostic.py
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_source.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_buffer_texture_pending.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_capture_contract.py --self-check
```

The analyzer requires a running product, semantic pixels through the final orbit, Blender-native
Cube presence, stable three-to-six-second settle pixels, zero page/lifecycle errors, and zero hard
completeness warnings. It also requires all nine post-stress workspace transitions and the full
DOM-to-GHOST button-coordinate canary. An already-active tab is deliberately excluded because it
is not a workspace transition.

The strengthened P0-J path establishes a same-run front-view/Frame-Selected reference, restores
that exact Blender-native pose after the cumulative battery and again after the final orbit, then
compares actual pixels. The full VIEW_3D must stay within a 1% changed-pixel ceiling; narrower
viewport-header, toolbar-icon, Outliner-text, and workspace-label regions use a 0.2% ceiling. This
detects the filed missing Cube/grid, clipped leading text, missing icons, and retained grey bars
without relying on PNG byte size. A real `G X 2 Enter` followed by `Control+Z` must also change and
restore Blender's native Cube location after the stress sequence.

On the driver-operated Apple host, run the same producer in hardware mode against an already-served
CAPTURE generation:

```sh
node sandbox/p0-interaction-stress/capture_diagnostic.mjs \
  --hardware --port 8123 \
  --run mac-m4pro-p0ij-<label> \
  --bin-dir build-wasm-windowed-opt/bin \
  --expected-wasm-orig-sha256 <64-lowercase-hex>
.host-tools/bin/python3.13 sandbox/p0-interaction-stress/analyze_diagnostic.py \
  sandbox/p0-interaction-stress/hardware-evidence/mac-m4pro-p0ij-<label>/diagnostic.json
```

Hardware mode is Apple-only and pins Node 22.16.0, Playwright 1.61.1, PNGJS 7.0.0, and Chromium
149.0.7827.55. It prefers `adapter.info.isFallbackAdapter`, rejects absent/fallback/software
adapters, verifies local and served split manifests against the requested `wasm.orig`, and creates
the immutable evidence directory only after those checks pass. Pointer lock may succeed or take the
single bounded rejection fallback; either path must leave zero page errors.

Hardware input receipts retain the five-second delivery bar. Only the explicitly non-receipt
SwiftShader lane permits a 15-second workspace-event window for synchronous Shading workspace
construction.

The source contract verifies that vertex and index buffers preserve SSBO binding intent while
first-use allocation is pending, and that numbered patch 0297 carries both changes. The original
diagnostic emitted six `gpu_shader_3D_polyline_flat_color` failures with surviving bindings
`[0,1,2,3]`, assembled bindings `[3]`, and missing bindings `[0,1,2]`. A device-free PASS proves the
specific retry contract and does not close P0-I's required Apple-hardware pixel verification.
The adjacent buffer-texture contract verifies that patch 0298 preserves the eventual correctly
shaped backing plus its separate pending allocation dependency. In particular, float1-3 sampler
buffers must wait for their expanded float4 backing rather than binding the smaller primary buffer.
Its device-free PASS likewise binds only that state transition, not pixels.
The adjacent input-recovery contract also requires the production retry-generation export, so
hardware evidence proves the callback path fired rather than accepting a source-only hook.
