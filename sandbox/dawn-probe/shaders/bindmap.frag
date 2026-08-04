// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
#version 450
// M3.T2 binding-audit — Blender-SHAPED fragment stage.
// See bindmap.vert for the shared set-0 binding map. This stage exercises the
// two combined sampler2Ds (bindings 1, 2 — the R1 split hazard), a material UBO
// (3), a read-only SSBO (4), and the shared Globals(0) + Constants(5) UBOs.

layout(location = 0) in vec2 v_uv;
layout(location = 1) in vec3 v_nor;
layout(location = 0) out vec4 out_color;

layout(std140, binding = 0) uniform Globals {
    mat4 view;
    mat4 proj;
} globals;

layout(binding = 1) uniform sampler2D color_tex;
layout(binding = 2) uniform sampler2D normal_tex;

layout(std140, binding = 3) uniform Material {
    vec4 base_color;
    vec4 params;   // params.x = active light count
} material;

struct Light {
    vec4 pos;
    vec4 color;
};
layout(std430, binding = 4) readonly buffer LightData {
    Light lights[];
} light_data;

layout(std140, binding = 5) uniform Constants {
    mat4 model;
    vec4 world_offset;
} constants;

void main()
{
    vec3 base = texture(color_tex, v_uv).rgb * material.base_color.rgb;
    vec3 n = normalize(v_nor + (texture(normal_tex, v_uv).xyz * 2.0 - 1.0));

    vec3 lit = vec3(0.0);
    int count = int(material.params.x);
    for (int i = 0; i < count; i++) {
        vec3 l = normalize(light_data.lights[i].pos.xyz);
        lit += max(dot(n, l), 0.0) * light_data.lights[i].color.rgb;
    }

    // Reference the shared Globals + Constants so both bindings are live in this
    // stage too (keeps 0 and 5 in the fragment interface).
    vec3 view_dir = normalize(globals.view[2].xyz);
    float bias = constants.world_offset.w;
    out_color = vec4(base * lit + base * 0.1 + view_dir * 0.0 + vec3(bias) * 0.0,
                     material.base_color.a);
}
