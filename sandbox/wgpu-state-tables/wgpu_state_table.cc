/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Blender state → WebGPU descriptor mapping. See wgpu_state_table.hh.
 * The blend table is transcribed VERBATIM from opengl/gl_state.cc:335-425
 * (GL_* → wgpu::BlendFactor); the equation column from gl_state.cc:428-439. */

#include "wgpu_state_table.hh"

namespace blender::gpu::webgpu {

using BF = wgpu::BlendFactor;
using BO = wgpu::BlendOperation;
using CF = wgpu::CompareFunction;
using SO = wgpu::StencilOperation;

/* GPU_BLEND_x -> (color src,dst) (alpha src,dst) equation dual-source.
 *   X(name, enabled, colorSrc, colorDst, alphaSrc, alphaDst, op, dual) */
#define GPU_BLEND_TABLE(X) \
  X(NONE,                    false, One,             Zero,             One,             Zero,             Add,             false) \
  X(ALPHA,                   true,  SrcAlpha,        OneMinusSrcAlpha, One,             OneMinusSrcAlpha, Add,             false) \
  X(ALPHA_PREMULT,           true,  One,             OneMinusSrcAlpha, One,             OneMinusSrcAlpha, Add,             false) \
  X(ADDITIVE,                true,  SrcAlpha,        One,              Zero,            One,              Add,             false) \
  X(ADDITIVE_PREMULT,        true,  One,             One,              One,             One,              Add,             false) \
  X(MULTIPLY,                true,  Dst,             Zero,             DstAlpha,        Zero,             Add,             false) \
  X(SUBTRACT,                true,  One,             One,              One,             One,              ReverseSubtract, false) \
  X(INVERT,                  true,  OneMinusDst,     Zero,             Zero,            One,              Add,             false) \
  X(MIN,                     true,  One,             One,              One,             One,              Min,             false) \
  X(MAX,                     true,  One,             One,              One,             One,              Max,             false) \
  X(OIT,                     true,  One,             One,              Zero,            OneMinusSrcAlpha, Add,             false) \
  X(BACKGROUND,              true,  OneMinusDstAlpha,SrcAlpha,         Zero,            SrcAlpha,         Add,             false) \
  X(CUSTOM,                  true,  One,             Src1,             One,             Src1Alpha,        Add,             true)  \
  X(ALPHA_UNDER_PREMUL,      true,  OneMinusDstAlpha,One,              OneMinusDstAlpha,One,              Add,             false) \
  X(OVERLAY_MASK_FROM_ALPHA, true,  Zero,            OneMinusSrcAlpha, Zero,            OneMinusSrcAlpha, Add,             false) \
  X(TRANSPARENCY,            true,  One,             SrcAlpha,         Zero,            SrcAlpha,         Add,             false)

static const BlendMapping g_blend[] = {
#define X(name, en, cs, cd, as, ad, op, dual) \
  {GPUBlend::name, #name, en, dual, {BO::op, BF::cs, BF::cd}, {BO::op, BF::as, BF::ad}},
    GPU_BLEND_TABLE(X)
#undef X
};
static constexpr size_t g_blend_count = sizeof(g_blend) / sizeof(g_blend[0]);

const BlendMapping *blend_table(size_t &count) { count = g_blend_count; return g_blend; }

BlendMapping to_blend(GPUBlend blend)
{
  for (const BlendMapping &m : g_blend) {
    if (m.blend == blend) {
      return m;
    }
  }
  return g_blend[0];
}

const char *to_string(GPUBlend b) { return to_blend(b).name; }

DepthMapping to_depth(GPUDepthTest test)
{
  switch (test) {
    case GPUDepthTest::NONE:          return {false, CF::Always};
    case GPUDepthTest::ALWAYS:        return {true, CF::Always};
    case GPUDepthTest::LESS:          return {true, CF::Less};
    case GPUDepthTest::LESS_EQUAL:    return {true, CF::LessEqual};
    case GPUDepthTest::EQUAL:         return {true, CF::Equal};
    case GPUDepthTest::GREATER:       return {true, CF::Greater};
    case GPUDepthTest::GREATER_EQUAL: return {true, CF::GreaterEqual};
  }
  return {false, CF::Always};
}

StencilMapping to_stencil(GPUStencilTest test, GPUStencilOp op)
{
  CF cmp = CF::Always;
  bool enabled = true;
  switch (test) {
    case GPUStencilTest::NONE:   enabled = false; cmp = CF::Always; break;
    case GPUStencilTest::ALWAYS: cmp = CF::Always; break;
    case GPUStencilTest::EQUAL:  cmp = CF::Equal; break;
    case GPUStencilTest::NEQUAL: cmp = CF::NotEqual; break;
  }
  wgpu::StencilFaceState front = {}, back = {};
  front.compare = back.compare = cmp;
  /* {failOp, depthFailOp, passOp}; from gl_state.cc:218-234 glStencilOp order. */
  switch (op) {
    case GPUStencilOp::NONE:
      front.failOp = front.depthFailOp = front.passOp = SO::Keep;
      back = front;
      break;
    case GPUStencilOp::REPLACE:
      front.failOp = SO::Keep; front.depthFailOp = SO::Keep; front.passOp = SO::Replace;
      back = front;
      break;
    case GPUStencilOp::COUNT_DEPTH_PASS: /* depth-pass count: passOp wrap, per-face */
      back.failOp = SO::Keep;  back.depthFailOp = SO::Keep;  back.passOp = SO::IncrementWrap;
      front.failOp = SO::Keep; front.depthFailOp = SO::Keep; front.passOp = SO::DecrementWrap;
      break;
    case GPUStencilOp::COUNT_DEPTH_FAIL: /* depth-fail count: depthFailOp wrap, per-face */
      back.failOp = SO::Keep;  back.depthFailOp = SO::DecrementWrap; back.passOp = SO::Keep;
      front.failOp = SO::Keep; front.depthFailOp = SO::IncrementWrap; front.passOp = SO::Keep;
      break;
  }
  return {enabled, front, back};
}

wgpu::CullMode to_cull_mode(GPUFaceCullTest cull)
{
  switch (cull) {
    case GPUFaceCullTest::NONE:  return wgpu::CullMode::None;
    case GPUFaceCullTest::FRONT: return wgpu::CullMode::Front;
    case GPUFaceCullTest::BACK:  return wgpu::CullMode::Back;
  }
  return wgpu::CullMode::None;
}

wgpu::FrontFace to_front_face(bool invert)
{
  /* GL default is CCW (glFrontFace(GL_CCW)); invert flips to CW. gl_state.cc:290-293. */
  return invert ? wgpu::FrontFace::CW : wgpu::FrontFace::CCW;
}

wgpu::ColorWriteMask to_color_write_mask(uint32_t m)
{
  wgpu::ColorWriteMask out = wgpu::ColorWriteMask::None;
  if (m & GPU_WRITE_RED)   out |= wgpu::ColorWriteMask::Red;
  if (m & GPU_WRITE_GREEN) out |= wgpu::ColorWriteMask::Green;
  if (m & GPU_WRITE_BLUE)  out |= wgpu::ColorWriteMask::Blue;
  if (m & GPU_WRITE_ALPHA) out |= wgpu::ColorWriteMask::Alpha;
  return out;
}

bool provoking_vertex_is_native(GPUProvokingVertex vert)
{
  return vert == GPUProvokingVertex::FIRST;
}

}  // namespace blender::gpu::webgpu
