<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# P0-I modal-extrude frame-coherence diagnostic

`capture_diagnostic.mjs` reproduces the launch-path `Tab -> E -> mouse move -> click` sequence
against the real windowed Wasm product. It attests the topology change (8 to 16 Cube vertices), then
exercises and cancels constrained move, rotate, and scale operations. It intercepts only the canvas
worker's WebGPU objects and records bounded traces for the polyline, dashed-line, widget,
region-composite, and surface-present shader families. The forced SwiftShader adapter is
diagnostic-only and binds no hardware or pixel receipt.

Serve the already-linked product, then run the capture and analyzer through the repository wrapper:

```sh
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" bash scripts/serve-web.sh 8123
DISPLAY=:0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
  harness/buildwrap.sh node sandbox/p0-modal-extrude/capture_diagnostic.mjs 8123
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-modal-extrude/analyze_trace.py
```

The analyzer validates that the modal constraint-line submissions use the live `VIEW_3D` target,
viewport, and a narrow line width, that each line has a distinct immediate resource, and that no
bind-group completeness warning or page error occurred. It then reports how many logical modal
redraw clusters reached the queue and how many surface copies occurred during that phase. A PASS
means the diagnostic is internally coherent; it does not mean the Apple-only pixel defect is fixed.

The 2026-08-27 trace characterizes the filed artifacts as first-use ordinary-frame coherence loss,
not a repeat of P0-G's undefined widget-shadow RGB: five extrusion redraw clusters reached the same
persistent viewport attachment with no extrusion-phase surface copy, while the post-confirm HUD
produced many later widget/region composites. Constrained move, rotate, and scale subsequently
reach the surface normally after that backlog drains. See
`notes/p0-modal-extrude-frame-coherence-20260827.md` for the guarded fix boundary and the required
hardware acceptance pass.
