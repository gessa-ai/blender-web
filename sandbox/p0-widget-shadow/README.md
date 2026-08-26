<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# P0-G widget-shadow diagnostic and source contract

`capture_diagnostic.mjs` attaches before the window-manager worker creates its WebGPU objects. It
records the final WGSL, render-pipeline blend descriptor, render-target clear/load history,
group-0 resources, and push-buffer initialization/updates for `gpu_shader_2D_widget_shadow`.
The forced SwiftShader adapter is diagnostic-only and binds no receipt.

Run the source and patch-identity contract through the repository build wrapper:

```sh
harness/buildwrap.sh .host-tools/bin/python3.13 sandbox/p0-widget-shadow/verify_source.py
```

Run the live fallback diagnostic while `scripts/serve-web.sh` serves the windowed product:

```sh
DISPLAY=:0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
  harness/buildwrap.sh node sandbox/p0-widget-shadow/capture_diagnostic.mjs 8123
```

Only the driver-operated conformant Apple host can close the pixel defect. Acceptance requires
transient UI shadows to be black/translucent with no white rounded bars or rings.
