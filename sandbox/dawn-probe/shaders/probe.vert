// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
#version 450
// M3.T1 probe — trivial transform vertex stage.
// A UBO at (set=0, binding=0) plus two vertex inputs: the minimal realistic
// shape Blender's create-info codegen emits. Nothing fancy — this stage exists
// to prove the GLSL->SPIR-V->Tint->WGSL->CreateShaderModule chain end to end.

layout(location = 0) in vec3 in_pos;
layout(location = 1) in vec2 in_uv;

layout(std140, binding = 0) uniform Camera {
    mat4 mvp;
} camera;

layout(location = 0) out vec2 v_uv;

void main()
{
    v_uv = in_uv;
    gl_Position = camera.mvp * vec4(in_pos, 1.0);
}
