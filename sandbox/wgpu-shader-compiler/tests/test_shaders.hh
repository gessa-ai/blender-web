/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * GLSL 450 test corpus for the M3.T7.pre shader-compiler harness. Blender-SHAPED
 * (dense set-0 bindings, push-constant fallback UBO last). The bindmap pair is
 * ported from sandbox/dawn-probe/shaders/bindmap.{vert,frag} (T2); the rest are
 * new: a shared vertex, a sampler-qualifier matrix (float / shadow / uint), a
 * compute shader with an SSBO + atomics (T8), and the sampler-array probe. */

#pragma once

namespace blender::gpu::webgpu::test_shaders {

/* ---- Case "bindmap": full T2 pair (2 combined float sampler2Ds) ------------ */

inline const char *kBindmapVert = R"GLSL(
#version 450
layout(location = 0) in vec3 in_pos;
layout(location = 1) in vec2 in_uv;
layout(location = 2) in vec3 in_nor;
layout(std140, binding = 0) uniform Globals { mat4 view; mat4 proj; } globals;
layout(std140, binding = 5) uniform Constants { mat4 model; vec4 world_offset; } constants;
layout(location = 0) out vec2 v_uv;
layout(location = 1) out vec3 v_nor;
void main() {
  v_uv = in_uv;
  v_nor = mat3(constants.model) * in_nor;
  vec4 world = constants.model * vec4(in_pos, 1.0) + constants.world_offset;
  gl_Position = globals.proj * globals.view * world;
}
)GLSL";

inline const char *kBindmapFrag = R"GLSL(
#version 450
layout(location = 0) in vec2 v_uv;
layout(location = 1) in vec3 v_nor;
layout(location = 0) out vec4 out_color;
layout(std140, binding = 0) uniform Globals { mat4 view; mat4 proj; } globals;
layout(binding = 1) uniform sampler2D color_tex;
layout(binding = 2) uniform sampler2D normal_tex;
layout(std140, binding = 3) uniform Material { vec4 base_color; vec4 params; } material;
struct Light { vec4 pos; vec4 color; };
layout(std430, binding = 4) readonly buffer LightData { Light lights[]; } light_data;
layout(std140, binding = 5) uniform Constants { mat4 model; vec4 world_offset; } constants;
void main() {
  vec3 base = texture(color_tex, v_uv).rgb * material.base_color.rgb;
  vec3 n = normalize(v_nor + (texture(normal_tex, v_uv).xyz * 2.0 - 1.0));
  vec3 lit = vec3(0.0);
  int count = int(material.params.x);
  for (int i = 0; i < count; i++) {
    vec3 l = normalize(light_data.lights[i].pos.xyz);
    lit += max(dot(n, l), 0.0) * light_data.lights[i].color.rgb;
  }
  vec3 view_dir = normalize(globals.view[2].xyz);
  float bias = constants.world_offset.w;
  out_color = vec4(base * lit + base * 0.1 + view_dir * 0.0 + vec3(bias) * 0.0,
                   material.base_color.a);
}
)GLSL";

/* ---- Shared minimal vertex for the resource-free-vertex cases -------------- */

inline const char *kSimpleVert = R"GLSL(
#version 450
layout(location = 0) in vec3 in_pos;
layout(location = 1) in vec2 in_uv;
layout(location = 0) out vec2 v_uv;
void main() { v_uv = in_uv; gl_Position = vec4(in_pos, 1.0); }
)GLSL";

/* ---- Case "types": sampler-qualifier matrix (open-question-3) --------------
 * binding 1 sampler2D        -> texture_2d<f32>  + Filtering sampler (textureSample)
 * binding 2 sampler2DShadow  -> texture_depth_2d + Comparison sampler (textureSampleCompare)
 * binding 3 usampler2D       -> texture_2d<u32>  (texelFetch; sampler half unused) */

inline const char *kTypesFrag = R"GLSL(
#version 450
layout(location = 0) in vec2 v_uv;
layout(location = 0) out vec4 out_color;
layout(std140, binding = 0) uniform Globals { mat4 mvp; } g;
layout(binding = 1) uniform sampler2D color_tex;
layout(binding = 2) uniform sampler2DShadow shadow_tex;
layout(binding = 3) uniform usampler2D id_tex;
void main() {
  vec3 base = texture(color_tex, v_uv).rgb;
  float vis = texture(shadow_tex, vec3(v_uv, 0.5));
  uint id = texelFetch(id_tex, ivec2(v_uv * 4.0), 0).r;
  out_color = vec4(base * vis + vec3(float(id)) * 0.0 + g.mvp[0].xyz * 0.0, 1.0);
}
)GLSL";

/* ---- Case "compute": SSBO (read-write) + atomics (T8) ---------------------- */

inline const char *kComputeAtomic = R"GLSL(
#version 450
layout(local_size_x = 64) in;
layout(std140, binding = 0) uniform Params { uint count; } params;
layout(std430, binding = 1) buffer Histogram { uint bins[]; } hist;         // read-write
layout(std430, binding = 2) readonly buffer InputVals { uint values[]; } inp;
void main() {
  uint i = gl_GlobalInvocationID.x;
  if (i >= params.count) { return; }
  uint v = inp.values[i] & 255u;
  atomicAdd(hist.bins[v], 1u);
}
)GLSL";

/* ---- Probe: array of combined samplers (open-question-1) ------------------- */

inline const char *kSamplerArrayFrag = R"GLSL(
#version 450
layout(location = 0) in vec2 v_uv;
layout(location = 0) out vec4 out_color;
layout(binding = 0) uniform sampler2D tex[4];
void main() {
  vec4 c = vec4(0.0);
  c += texture(tex[0], v_uv);
  c += texture(tex[1], v_uv);
  c += texture(tex[2], v_uv);
  c += texture(tex[3], v_uv);
  out_color = c;
}
)GLSL";

}  // namespace blender::gpu::webgpu::test_shaders
