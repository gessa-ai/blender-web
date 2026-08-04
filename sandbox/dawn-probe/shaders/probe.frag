// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
#version 450
// M3.T1 probe — textured, tinted fragment stage.
//
// Deliberately exercises the single nastiest translation hazard the architect
// flagged as R1 (notes/gpu-webgpu-architecture.md §3c.2): a GLSL *combined*
// image sampler (sampler2D). In SPIR-V this is one OpTypeSampledImage at
// (set=0, binding=1); WGSL/WebGPU has no combined samplers, so Tint's SPIR-V
// reader must SPLIT it into a separate texture_2d<f32> + sampler at distinct
// @group/@binding. The WGSL this produces is the binding-map evidence seed for
// T2. A second UBO (material tint) sits at (set=0, binding=2) so we can see how
// Tint numbers the split sampler relative to a plain uniform buffer.

layout(location = 0) in vec2 v_uv;
layout(location = 0) out vec4 out_color;

layout(binding = 1) uniform sampler2D image;

layout(std140, binding = 2) uniform Material {
    vec4 tint;
} material;

void main()
{
    out_color = texture(image, v_uv) * material.tint;
}
