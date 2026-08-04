// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
#version 450
// M3.T2 binding-audit — Blender-SHAPED vertex stage.
//
// Mirrors Blender's Vulkan backend binding scheme (verified in
// notes/gpu-binding-map-spec.md): a single descriptor set (set 0), dense 0-based
// sequential bindings assigned in resource-declaration order, with the
// push-constant-emulation UBO taking the LAST binding. Bindings 0 and 5 are
// SHARED with the fragment stage (same binding, same type) so the cross-stage
// bind-group-layout composition can be exercised.
//
// Binding map (shared set 0):
//   0  Globals   UBO            (vertex + fragment)   <- a "pass" UBO
//   1  color_tex combined sampler2D (fragment only)
//   2  normal_tex combined sampler2D (fragment only)
//   3  Material  UBO            (fragment only)
//   4  LightData SSBO readonly  (fragment only)
//   5  Constants UBO            (vertex + fragment)   <- push-constant fallback, LAST

layout(location = 0) in vec3 in_pos;
layout(location = 1) in vec2 in_uv;
layout(location = 2) in vec3 in_nor;

layout(std140, binding = 0) uniform Globals {
    mat4 view;
    mat4 proj;
} globals;

// Push-constant emulation UBO (VKPushConstants::StorageType::BUFFER). In Blender
// this is emitted `layout(binding = <last>, std140) uniform constants { ... }`.
layout(std140, binding = 5) uniform Constants {
    mat4 model;
    vec4 world_offset;
} constants;

layout(location = 0) out vec2 v_uv;
layout(location = 1) out vec3 v_nor;

void main()
{
    v_uv = in_uv;
    v_nor = mat3(constants.model) * in_nor;
    vec4 world = constants.model * vec4(in_pos, 1.0) + constants.world_offset;
    gl_Position = globals.proj * globals.view * world;
}
