/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm parity contract for the canonical in-tree WebGPU
 * fixed-function state table. No instance, adapter, device, or pipeline is
 * created; live descriptor validation remains part of the hardware-gated M3
 * replay. */

#include <array>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <type_traits>

#include "wgpu_state_table.hh"

namespace bw = blender::gpu::webgpu;

namespace {

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    return false;
  }
  return true;
}

uint64_t fnv_byte(uint64_t hash, const uint8_t value)
{
  return (hash ^ value) * UINT64_C(1099511628211);
}

template<typename Enum> uint64_t enum_value(const Enum value)
{
  return uint64_t(static_cast<std::underlying_type_t<Enum>>(value));
}

uint64_t fnv_u64(uint64_t hash, const uint64_t value)
{
  for (uint32_t shift = 0; shift < 64; shift += 8) {
    hash = fnv_byte(hash, uint8_t(value >> shift));
  }
  return hash;
}

uint64_t fnv_string(uint64_t hash, const char *value)
{
  for (const unsigned char *p = reinterpret_cast<const unsigned char *>(value); *p != 0; p++) {
    hash = fnv_byte(hash, *p);
  }
  return fnv_byte(hash, 0);
}

bool component_equal(const wgpu::BlendComponent &actual,
                     const wgpu::BlendOperation operation,
                     const wgpu::BlendFactor source,
                     const wgpu::BlendFactor destination)
{
  return actual.operation == operation && actual.srcFactor == source &&
         actual.dstFactor == destination;
}

uint64_t hash_component(uint64_t hash, const wgpu::BlendComponent &component)
{
  hash = fnv_u64(hash, enum_value(component.operation));
  hash = fnv_u64(hash, enum_value(component.srcFactor));
  return fnv_u64(hash, enum_value(component.dstFactor));
}

bool blend_contract()
{
  using BF = wgpu::BlendFactor;
  using BO = wgpu::BlendOperation;
  struct Expected {
    blender::GPUBlend blend;
    const char *name;
    bool enabled;
    bool dual_source;
    BO operation;
    BF color_source;
    BF color_destination;
    BF alpha_source;
    BF alpha_destination;
  };
  constexpr std::array<Expected, 16> expected = {{
      {blender::GPU_BLEND_NONE, "GPU_BLEND_NONE", false, false, BO::Add, BF::One, BF::Zero, BF::One, BF::Zero},
      {blender::GPU_BLEND_ALPHA,
       "GPU_BLEND_ALPHA",
       true,
       false,
       BO::Add,
       BF::SrcAlpha,
       BF::OneMinusSrcAlpha,
       BF::One,
       BF::OneMinusSrcAlpha},
      {blender::GPU_BLEND_ALPHA_PREMULT,
       "GPU_BLEND_ALPHA_PREMULT",
       true,
       false,
       BO::Add,
       BF::One,
       BF::OneMinusSrcAlpha,
       BF::One,
       BF::OneMinusSrcAlpha},
      {blender::GPU_BLEND_ADDITIVE,
       "GPU_BLEND_ADDITIVE",
       true,
       false,
       BO::Add,
       BF::SrcAlpha,
       BF::One,
       BF::Zero,
       BF::One},
      {blender::GPU_BLEND_ADDITIVE_PREMULT,
       "GPU_BLEND_ADDITIVE_PREMULT",
       true,
       false,
       BO::Add,
       BF::One,
       BF::One,
       BF::One,
       BF::One},
      {blender::GPU_BLEND_MULTIPLY,
       "GPU_BLEND_MULTIPLY",
       true,
       false,
       BO::Add,
       BF::Dst,
       BF::Zero,
       BF::DstAlpha,
       BF::Zero},
      {blender::GPU_BLEND_SUBTRACT,
       "GPU_BLEND_SUBTRACT",
       true,
       false,
       BO::ReverseSubtract,
       BF::One,
       BF::One,
       BF::One,
       BF::One},
      {blender::GPU_BLEND_INVERT,
       "GPU_BLEND_INVERT",
       true,
       false,
       BO::Add,
       BF::OneMinusDst,
       BF::Zero,
       BF::Zero,
       BF::One},
      {blender::GPU_BLEND_MIN, "GPU_BLEND_MIN", true, false, BO::Min, BF::One, BF::One, BF::One, BF::One},
      {blender::GPU_BLEND_MAX, "GPU_BLEND_MAX", true, false, BO::Max, BF::One, BF::One, BF::One, BF::One},
      {blender::GPU_BLEND_OIT, "GPU_BLEND_OIT", true, false, BO::Add, BF::One, BF::One, BF::Zero, BF::OneMinusSrcAlpha},
      {blender::GPU_BLEND_BACKGROUND,
       "GPU_BLEND_BACKGROUND",
       true,
       false,
       BO::Add,
       BF::OneMinusDstAlpha,
       BF::SrcAlpha,
       BF::Zero,
       BF::SrcAlpha},
      {blender::GPU_BLEND_CUSTOM, "GPU_BLEND_CUSTOM", true, true, BO::Add, BF::One, BF::Src1, BF::One, BF::Src1Alpha},
      {blender::GPU_BLEND_ALPHA_UNDER_PREMUL,
       "GPU_BLEND_ALPHA_UNDER_PREMUL",
       true,
       false,
       BO::Add,
       BF::OneMinusDstAlpha,
       BF::One,
       BF::OneMinusDstAlpha,
       BF::One},
      {blender::GPU_BLEND_OVERLAY_MASK_FROM_ALPHA,
       "GPU_BLEND_OVERLAY_MASK_FROM_ALPHA",
       true,
       false,
       BO::Add,
       BF::Zero,
       BF::OneMinusSrcAlpha,
       BF::Zero,
       BF::OneMinusSrcAlpha},
      {blender::GPU_BLEND_TRANSPARENCY,
       "GPU_BLEND_TRANSPARENCY",
       true,
       false,
       BO::Add,
       BF::One,
       BF::SrcAlpha,
       BF::Zero,
       BF::SrcAlpha},
  }};

  size_t count = 0;
  const bw::BlendMapping *table = bw::blend_table(count);
  uint64_t hash = UINT64_C(14695981039346656037);
  size_t enabled = 0;
  size_t dual_source = 0;
  if (!require(table != nullptr, "blend table is null") ||
      !require(count == expected.size(), "blend table census"))
  {
    return false;
  }

  for (size_t i = 0; i < expected.size(); i++) {
    const Expected &want = expected[i];
    const bw::BlendMapping &actual = table[i];
    const bw::BlendMapping lookup = bw::to_blend(want.blend);
    if (!require(actual.blend == want.blend, "blend enum order") ||
        !require(std::strcmp(actual.name, want.name) == 0, "blend name") ||
        !require(actual.enabled == want.enabled, "blend enabled") ||
        !require(actual.dual_source == want.dual_source, "blend dual-source") ||
        !require(component_equal(actual.color,
                                 want.operation,
                                 want.color_source,
                                 want.color_destination),
                 "blend color component") ||
        !require(component_equal(actual.alpha,
                                 want.operation,
                                 want.alpha_source,
                                 want.alpha_destination),
                 "blend alpha component") ||
        !require(lookup.blend == actual.blend && lookup.color.operation == actual.color.operation &&
                     lookup.color.srcFactor == actual.color.srcFactor &&
                     lookup.color.dstFactor == actual.color.dstFactor &&
                     lookup.alpha.operation == actual.alpha.operation &&
                     lookup.alpha.srcFactor == actual.alpha.srcFactor &&
                     lookup.alpha.dstFactor == actual.alpha.dstFactor,
                 "blend lookup identity") ||
        !require(std::strcmp(bw::to_string(want.blend), want.name) == 0,
                 "blend string lookup"))
    {
      return false;
    }
    enabled += actual.enabled;
    dual_source += actual.dual_source;
    hash = fnv_string(hash, actual.name);
    hash = fnv_byte(hash, actual.enabled);
    hash = fnv_byte(hash, actual.dual_source);
    hash = hash_component(hash, actual.color);
    hash = hash_component(hash, actual.alpha);
  }

  const bw::BlendMapping fallback = bw::to_blend(static_cast<blender::GPUBlend>(255));
  if (!require(fallback.blend == blender::GPU_BLEND_NONE, "invalid blend fallback") ||
      !require(enabled == 15, "enabled blend census") ||
      !require(dual_source == 1, "dual-source blend census"))
  {
    return false;
  }

  std::printf("CONTRACT blend PASS rows=%zu enabled=%zu dual=%zu digest=%016" PRIx64 "\n",
              count,
              enabled,
              dual_source,
              hash);
  return true;
}

bool depth_contract()
{
  using CF = wgpu::CompareFunction;
  struct Expected {
    blender::GPUDepthTest test;
    bool enabled;
    CF compare;
  };
  constexpr std::array<Expected, 7> expected = {{
      {blender::GPU_DEPTH_NONE, false, CF::Always},
      {blender::GPU_DEPTH_ALWAYS, true, CF::Always},
      {blender::GPU_DEPTH_LESS, true, CF::Less},
      {blender::GPU_DEPTH_LESS_EQUAL, true, CF::LessEqual},
      {blender::GPU_DEPTH_EQUAL, true, CF::Equal},
      {blender::GPU_DEPTH_GREATER, true, CF::Greater},
      {blender::GPU_DEPTH_GREATER_EQUAL, true, CF::GreaterEqual},
  }};
  uint64_t hash = UINT64_C(14695981039346656037);
  for (const Expected &want : expected) {
    const bw::DepthMapping actual = bw::to_depth(want.test);
    if (!require(actual.test_enabled == want.enabled, "depth enabled") ||
        !require(actual.compare == want.compare, "depth compare"))
    {
      return false;
    }
    hash = fnv_byte(hash, actual.test_enabled);
    hash = fnv_u64(hash, enum_value(actual.compare));
  }
  const bw::DepthMapping fallback = bw::to_depth(static_cast<blender::GPUDepthTest>(255));
  if (!require(!fallback.test_enabled && fallback.compare == CF::Always,
               "invalid depth fallback"))
  {
    return false;
  }
  std::printf("CONTRACT depth PASS rows=%zu enabled=6 digest=%016" PRIx64 "\n",
              expected.size(),
              hash);
  return true;
}

bool stencil_face_equal(const wgpu::StencilFaceState &actual,
                        const wgpu::CompareFunction compare,
                        const wgpu::StencilOperation fail,
                        const wgpu::StencilOperation depth_fail,
                        const wgpu::StencilOperation pass)
{
  return actual.compare == compare && actual.failOp == fail &&
         actual.depthFailOp == depth_fail && actual.passOp == pass;
}

uint64_t hash_stencil_face(uint64_t hash, const wgpu::StencilFaceState &face)
{
  hash = fnv_u64(hash, enum_value(face.compare));
  hash = fnv_u64(hash, enum_value(face.failOp));
  hash = fnv_u64(hash, enum_value(face.depthFailOp));
  return fnv_u64(hash, enum_value(face.passOp));
}

bool stencil_contract()
{
  using CF = wgpu::CompareFunction;
  using SO = wgpu::StencilOperation;
  struct TestExpected {
    blender::GPUStencilTest test;
    bool enabled;
    CF compare;
  };
  struct OpExpected {
    blender::GPUStencilOp op;
    SO front_fail;
    SO front_depth_fail;
    SO front_pass;
    SO back_fail;
    SO back_depth_fail;
    SO back_pass;
  };
  constexpr std::array<TestExpected, 4> tests = {{
      {blender::GPU_STENCIL_NONE, false, CF::Always},
      {blender::GPU_STENCIL_ALWAYS, true, CF::Always},
      {blender::GPU_STENCIL_EQUAL, true, CF::Equal},
      {blender::GPU_STENCIL_NEQUAL, true, CF::NotEqual},
  }};
  constexpr std::array<OpExpected, 4> ops = {{
      {blender::GPU_STENCIL_OP_NONE, SO::Keep, SO::Keep, SO::Keep, SO::Keep, SO::Keep, SO::Keep},
      {blender::GPU_STENCIL_OP_REPLACE, SO::Keep, SO::Keep, SO::Replace, SO::Keep, SO::Keep, SO::Replace},
      {blender::GPU_STENCIL_OP_COUNT_DEPTH_PASS,
       SO::Keep,
       SO::Keep,
       SO::DecrementWrap,
       SO::Keep,
       SO::Keep,
       SO::IncrementWrap},
      {blender::GPU_STENCIL_OP_COUNT_DEPTH_FAIL,
       SO::Keep,
       SO::IncrementWrap,
       SO::Keep,
       SO::Keep,
       SO::DecrementWrap,
       SO::Keep},
  }};

  size_t cases = 0;
  uint64_t hash = UINT64_C(14695981039346656037);
  for (const TestExpected &test : tests) {
    for (const OpExpected &op : ops) {
      const bw::StencilMapping actual = bw::to_stencil(test.test, op.op);
      if (!require(actual.enabled == test.enabled, "stencil enabled") ||
          !require(stencil_face_equal(actual.front,
                                      test.compare,
                                      op.front_fail,
                                      op.front_depth_fail,
                                      op.front_pass),
                   "stencil front face") ||
          !require(stencil_face_equal(actual.back,
                                      test.compare,
                                      op.back_fail,
                                      op.back_depth_fail,
                                      op.back_pass),
                   "stencil back face"))
      {
        return false;
      }
      hash = fnv_byte(hash, actual.enabled);
      hash = hash_stencil_face(hash, actual.front);
      hash = hash_stencil_face(hash, actual.back);
      cases++;
    }
  }
  std::printf("CONTRACT stencil PASS cases=%zu tests=%zu ops=%zu digest=%016" PRIx64 "\n",
              cases,
              tests.size(),
              ops.size(),
              hash);
  return cases == 16;
}

bool raster_contract()
{
  using CM = wgpu::ColorWriteMask;
  constexpr std::array<blender::GPUFaceCullTest, 3> culls = {
      blender::GPU_CULL_NONE, blender::GPU_CULL_FRONT, blender::GPU_CULL_BACK};
  constexpr std::array<wgpu::CullMode, 3> expected_culls = {
      wgpu::CullMode::None, wgpu::CullMode::Front, wgpu::CullMode::Back};
  uint64_t hash = UINT64_C(14695981039346656037);
  for (size_t i = 0; i < culls.size(); i++) {
    const wgpu::CullMode actual = bw::to_cull_mode(culls[i]);
    if (!require(actual == expected_culls[i], "cull mapping")) {
      return false;
    }
    hash = fnv_u64(hash, enum_value(actual));
  }
  if (!require(bw::to_cull_mode(static_cast<blender::GPUFaceCullTest>(255)) ==
                   wgpu::CullMode::None,
               "invalid cull fallback") ||
      !require(bw::to_front_face(false) == wgpu::FrontFace::CCW,
               "default front face") ||
      !require(bw::to_front_face(true) == wgpu::FrontFace::CW,
               "inverted front face") ||
      !require(!bw::provoking_vertex_is_native(blender::GPU_VERTEX_LAST),
               "last provoking vertex is not native") ||
      !require(bw::provoking_vertex_is_native(blender::GPU_VERTEX_FIRST),
               "first provoking vertex is native"))
  {
    return false;
  }
  hash = fnv_u64(hash, enum_value(bw::to_front_face(false)));
  hash = fnv_u64(hash, enum_value(bw::to_front_face(true)));

  for (uint32_t mask = 0; mask < 64; mask++) {
    CM expected = CM::None;
    if ((mask & uint32_t(blender::GPU_WRITE_RED)) != 0) {
      expected |= CM::Red;
    }
    if ((mask & uint32_t(blender::GPU_WRITE_GREEN)) != 0) {
      expected |= CM::Green;
    }
    if ((mask & uint32_t(blender::GPU_WRITE_BLUE)) != 0) {
      expected |= CM::Blue;
    }
    if ((mask & uint32_t(blender::GPU_WRITE_ALPHA)) != 0) {
      expected |= CM::Alpha;
    }
    const CM actual = bw::to_color_write_mask(static_cast<blender::GPUWriteMask>(mask));
    if (!require(actual == expected, "color write-mask mapping")) {
      return false;
    }
    hash = fnv_u64(hash, enum_value(actual));
  }

  std::printf("CONTRACT raster PASS culls=%zu front_faces=2 write_masks=64 provoking=2 "
              "digest=%016" PRIx64 "\n",
              culls.size(),
              hash);
  return true;
}

}  // namespace

int main()
{
  if (!blend_contract() || !depth_contract() || !stencil_contract() || !raster_contract()) {
    return 1;
  }
  std::printf(
      "INTEGRATED_STATE_PASS contracts=4 blends=16 depth=7 stencil=16 write_masks=64\n");
  return 0;
}
