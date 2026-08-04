<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M3.pointsize.pre — gl_PointSize → instanced-quad expansion prototype

WebGPU points are always 1px and WGSL has no point-size builtin — the one raster
gap left open by T10.pre. This proves the mechanical rewrite that closes it:
`GPU_PRIM_POINTS` + `gl_PointSize` → an instanced quad per point, sized in the
vertex shader, with `gl_PointCoord` replaced by an interpolated UV.

- `wgpu_pointsize_expand.{hh,cc}` — the rewritten representative shader
  (`gpu_shader_3D_point_uniform_size_aa`, read at the pin) as drop-in GLSL + its
  resource layout + the quad geometry.
- `tests/wgpu_pointsize_test.cc` — compiles the rewrite through the **T7.pre chain**
  (shaderc→Tint→WGSL), builds a pipeline, RENDERS a 3-point grid offscreen at sizes
  1/5/9 px, reads pixels back, and asserts coverage (centers lit, gaps dark, inner
  radius lit, outer radius dark). The program's first rendered-content check.

Build:  `harness/buildwrap.sh bash sandbox/wgpu-pointsize/build.sh`
(reuses build-dawn/dawn + lib/macos_arm64/shaderc; build tree build-dawn/pointsize-build, gitignored.)

The mechanical rewrite recipe + placement recommendation: `notes/gpu-pointsize-prototype.md`.
