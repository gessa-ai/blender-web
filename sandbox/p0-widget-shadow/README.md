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

The driver-operated conformant Apple host closed the pixel defect on 2026-08-27. A toolbar
tooltip, the Shift+A Add-menu flyout, and the F9 Adjust Last Operation panel all rendered soft
dark shadows without white fill. A future audit may broaden coverage to a text tooltip and a
cascading submenu, but that spot-check is not a release blocker.
