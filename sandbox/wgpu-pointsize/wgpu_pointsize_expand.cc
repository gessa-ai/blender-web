/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * The gl_PointSize → instanced-quad rewrite of gpu_shader_3D_point_uniform_size_aa.
 * See wgpu_pointsize_expand.hh. The GLSL below is the faithful transform of the
 * upstream vert/frag (read-only recon):
 *   VERT (upstream): gl_Position = MVP*vec4(pos,1); gl_PointSize = size;
 *                    radii[0]=0.5*size; radii[1]=radius-1; radii /= size;
 *   FRAG (upstream): dist = length(gl_PointCoord - vec2(0.5));
 *                    a = mix(color.a, 0, smoothstep(radii[1], radii[0], dist));
 *                    if (a==0) discard;
 * Only the point-expansion prologue and the gl_PointCoord→v_uv swap change; the
 * AA radii math and the fragment falloff are byte-for-byte the same. */

#include "wgpu_pointsize_expand.hh"

namespace blender::gpu::webgpu {

/* Per-INSTANCE `pos` (stepMode Instance) + gl_VertexIndex-selected quad corner.
 * Point size is in PIXELS: converted to a clip-space offset (×2 for the [-1,1]
 * NDC span, ÷viewport for pixels→fraction, ×center.w to survive perspective). */
static const char *kVert = R"GLSL(
#version 450
layout(std140, binding = 0) uniform Globals {
  mat4 mvp;
  vec4 color;
  vec2 viewport;
  float size;
  float pad_;
} g;
layout(location = 0) in vec3 pos;         /* per-instance point center */
layout(location = 0) out vec2 v_uv;       /* replaces gl_PointCoord */
layout(location = 1) out vec2 v_radii;    /* flat: radii[0], radii[1] */
void main() {
  vec2 corners[4] = vec2[4](vec2(-0.5, -0.5), vec2(0.5, -0.5),
                            vec2(-0.5,  0.5), vec2(0.5,  0.5));
  vec2 corner = corners[gl_VertexIndex];
  vec4 center = g.mvp * vec4(pos, 1.0);
  vec2 off_ndc = (corner * g.size / g.viewport) * 2.0;
  gl_Position = center + vec4(off_ndc * center.w, 0.0, 0.0);
  v_uv = corner + vec2(0.5);
  float radius = 0.5 * g.size;
  v_radii = vec2(radius, radius - 1.0) / g.size;
}
)GLSL";

static const char *kFrag = R"GLSL(
#version 450
layout(std140, binding = 0) uniform Globals {
  mat4 mvp;
  vec4 color;
  vec2 viewport;
  float size;
  float pad_;
} g;
layout(location = 0) in vec2 v_uv;
layout(location = 1) in vec2 v_radii;
layout(location = 0) out vec4 fragColor;
void main() {
  float dist = length(v_uv - vec2(0.5));
  fragColor = g.color;
  fragColor.a = mix(g.color.a, 0.0, smoothstep(v_radii[1], v_radii[0], dist));
  if (fragColor.a == 0.0) {
    discard;
  }
}
)GLSL";

const char *rewritten_point_vert() { return kVert; }
const char *rewritten_point_frag() { return kFrag; }

std::vector<ResourceDesc> point_resources()
{
  ResourceDesc ubo;
  ubo.kind = ResourceKind::UniformBuffer;
  ubo.binding = 0;
  ubo.stages = STAGE_VERTEX | STAGE_FRAGMENT;
  ubo.name = "Globals";
  return {ubo};
}

static const float kCorners[8] = {-0.5f, -0.5f, 0.5f, -0.5f, -0.5f, 0.5f, 0.5f, 0.5f};
const float *quad_corners(uint32_t &count)
{
  count = 4;
  return kCorners;
}

}  // namespace blender::gpu::webgpu
