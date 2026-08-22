<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Pinned framebuffer scissored-clear oracle

`probe.py` uses Blender's native GPU API to pin framebuffer-clear behavior on a
6x5 offscreen. An enabled lower-left scissor restricts color and depth clears,
including a color texture attached across every array layer. With scissor disabled,
the viewport alone does not restrict a clear and the complete attachment is updated.

Run it through the digest-pinned native oracle container:

```sh
harness/buildwrap.sh sudo -n -g docker scripts/oracle-container.sh blender \
  --python /home/pc/gessa/blender-web/sandbox/wgpu-framebuffer-scissored-clear-oracle/probe.py
```
