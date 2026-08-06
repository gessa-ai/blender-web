<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4.T14a — present-path Y-flip fixed: Blender's window composites UPRIGHT in a Chrome tab

Round 17 (gpu-backend). Companion to `m4-first-ui-pixels-quicksetup-splash.png` (r16), which
showed the same boot **vertically mirrored** ("window composite Y-flipped", r16 note).

## What changed

The ADR-005 clip-space Y-flip (`gl_Position.y = -gl_Position.y`, patch 0052) is correct and
load-bearing for OFFSCREEN targets (paired with the front-face swap 0044 + readback row-flip
0045) — it matches the GL-convention the gpu-suite oracles encode. But WebGPU's NDC is already
`+Y`-up (like GL), and the window surface is composited **directly** by the browser with no
readback, so applying the offscreen flip to window passes renders the whole window upside-down.

Fix (patches 0096, all in `upstream/source/blender/gpu/webgpu/**`): the clip-space Y sign is
now a **pipeline-overridable constant** (`gpu_clip_y_sign`, WGSL `override` @id 1000, default
bit-pattern of `-1.0f`). `PipelineInfo::flip_y` (part of the pipeline cache key) is `false` only
for the surface-backed window backbuffer (`WGPUContext::is_window_backbuffer`), where the
override is set to `+1.0f` and the front-face swap is dropped. Every offscreen pipeline leaves
the override unset → keeps the `-1.0f` default byte-for-byte.

## Verification (this image)

- Served `build-wasm-windowed/bin` on `:8123`, booted `:8123/windowed.html` in a real
  Chrome tab (Chrome 148, WebGPU + crossOriginIsolated + SharedArrayBuffer), `--factory-startup`,
  no `--background`. Boot reached `state: main loop (WM_main)`, `data: loaded`.
- Capture: `canvas.toDataURL` readback of the 1800×1169 window surface, downscaled to 620×403.
- **UPRIGHT confirmed:** the viewport header (`Object Mode | View | Select | Add | Object`,
  `Global`, gizmos) is at the TOP; the tool column is top-left; `Options` is top-right; the
  Quick Setup splash reads top-to-bottom correctly (title → Theme Blender Dark → Keymap Blender
  → Mouse Select Left/Right → Spacebar Action Play → Continue). All glyphs read normally (not
  mirrored). This is the exact vertical inverse of the r16 mirrored composite.

## Input hit-testing (not broken by the flip)

`GHOST_EventBridgeWeb.cc:50-53` forwards the browser's canvas-relative `targetX/targetY`
(top-left origin) straight into `GHOST_EventCursor` — the standard GHOST convention that
Blender's WM flips to bottom-left, i.e. the input path already **assumes an upright framebuffer**.
The render fix therefore ALIGNS picking with the display (r16's mirrored render was the
misaligned case); the input path is untouched. Keyboard input confirmed live in-tab (Escape
dismissed the GPU-backend fallback dialog). Native gpu suite unaffected: `flip_y` is always true
without a surface, so static_shaders stays 956/973 and the offscreen watched-set is unchanged.

Format note: saved as `.jpg` (JPEG, the compact `toDataURL` capture); the `*.png` in the task
naming convention is a naming hint only.
