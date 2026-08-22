<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Pinned offscreen viewport/scissor oracle

`probe.py` draws a full-screen quad into a 6x5 native offscreen and proves that
Blender's ordinary viewport and optional scissor use lower-left framebuffer
coordinates. It records one viewport-only footprint and one independent
viewport/scissor intersection for the device-free WebGPU plan contract.

Run it through the digest-pinned native oracle container:

```sh
harness/buildwrap.sh sudo -n -g docker scripts/oracle-container.sh blender \
  --python /home/pc/gessa/blender-web/sandbox/wgpu-offscreen-viewport-oracle/probe.py
```
