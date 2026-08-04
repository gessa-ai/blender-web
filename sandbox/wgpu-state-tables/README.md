<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M3.T10.pre — WebGPU state tables (standalone-proven)

The complete mechanical mapping from Blender's fixed-function state model
(`GPU_state.hh`) to WebGPU pipeline descriptor structs. Drop-in for
`source/blender/gpu/webgpu/wgpu_state.cc` / `wgpu_pipeline.cc`.

- `wgpu_state_table.{hh,cc}` — X-macro blend table (16 `GPUBlend` arms → `wgpu::
  BlendState`, transcribed verbatim from `opengl/gl_state.cc:335-425`, verified
  identical in the Vulkan + Metal backends) + depth/stencil (incl. shadow-volume
  increment/decrement-wrap) + cull/winding + color write mask + provoking-vertex
  note.
- `tests/wgpu_state_table_test.cc` — live Dawn/Metal harness: creates a render
  pipeline for every blend/depth/stencil/cull config (pipeline creation validates
  the descriptor). Hand-written WGSL; CUSTOM uses the dual-source path.

Build:  `harness/buildwrap.sh bash sandbox/wgpu-state-tables/build.sh`
(Dawn-only; reuses build-dawn/dawn; build tree build-dawn/t10pre-build, gitignored.)

Findings (incl. the full blend table + the point-size/logic-op/provoking gaps):
`notes/gpu-t6-t10pre-findings.md`.
