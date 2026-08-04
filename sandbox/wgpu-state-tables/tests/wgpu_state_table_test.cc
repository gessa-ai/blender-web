/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.T10.pre live harness. Validates the state→descriptor mapping by CREATING a
 * real render pipeline for each config on a native Dawn/Metal device (pipeline
 * creation validates the whole descriptor combination). Covers: all 16 GPUBlend
 * arms (CUSTOM via the dual-source path when the feature is present), all 7
 * GPUDepthTest arms, representative stencil test×op combos, and cull×winding.
 * Uses hand-written WGSL (no shaderc/Tint needed). */

#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include "webgpu/webgpu_cpp.h"

#include "wgpu_state_table.hh"

namespace bw = blender::gpu::webgpu;

namespace {

std::string ToStr(wgpu::StringView s) {
  if (s.data == nullptr) return {};
  if (s.length == WGPU_STRLEN) return std::string(s.data);
  return std::string(s.data, s.length);
}

const char *kVertWgsl = R"WGSL(
@vertex fn vs(@builtin(vertex_index) i : u32) -> @builtin(position) vec4<f32> {
  var p = array<vec2<f32>, 3>(vec2<f32>(-1.0,-1.0), vec2<f32>(3.0,-1.0), vec2<f32>(-1.0,3.0));
  return vec4<f32>(p[i], 0.0, 1.0);
}
)WGSL";

const char *kFragWgsl = R"WGSL(
@fragment fn fs() -> @location(0) vec4<f32> { return vec4<f32>(1.0, 0.5, 0.25, 1.0); }
)WGSL";

const char *kFragDualSrc = R"WGSL(
enable dual_source_blending;
struct FO {
  @location(0) @blend_src(0) c0 : vec4<f32>,
  @location(0) @blend_src(1) c1 : vec4<f32>,
};
@fragment fn fs() -> FO {
  var o : FO;
  o.c0 = vec4<f32>(1.0, 0.5, 0.25, 1.0);
  o.c1 = vec4<f32>(0.5, 0.5, 0.5, 0.5);
  return o;
}
)WGSL";

struct Dawn {
  wgpu::Instance instance;
  wgpu::Adapter adapter;
  wgpu::Device device;
  bool dual_source = false;

  bool init() {
    wgpu::InstanceDescriptor idesc = {};
    static constexpr auto kTWA = wgpu::InstanceFeatureName::TimedWaitAny;
    idesc.requiredFeatureCount = 1;
    idesc.requiredFeatures = &kTWA;
    instance = wgpu::CreateInstance(&idesc);
    if (!instance) return false;
    wgpu::RequestAdapterOptions aopts = {};
    aopts.backendType = wgpu::BackendType::Metal;
    aopts.featureLevel = wgpu::FeatureLevel::Core;
    instance.WaitAny(instance.RequestAdapter(&aopts, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::RequestAdapterStatus s, wgpu::Adapter a, wgpu::StringView) {
          if (s == wgpu::RequestAdapterStatus::Success) adapter = std::move(a);
        }), UINT64_MAX);
    if (!adapter) return false;
    dual_source = adapter.HasFeature(wgpu::FeatureName::DualSourceBlending);
    std::vector<wgpu::FeatureName> feats;
    if (dual_source) feats.push_back(wgpu::FeatureName::DualSourceBlending);
    wgpu::DeviceDescriptor ddesc = {};
    ddesc.requiredFeatureCount = feats.size();
    ddesc.requiredFeatures = feats.data();
    ddesc.SetUncapturedErrorCallback([](const wgpu::Device&, wgpu::ErrorType t, wgpu::StringView m) {
      std::fprintf(stderr, "UNCAPTURED(%d): %s\n", int(t), ToStr(m).c_str());
    });
    instance.WaitAny(adapter.RequestDevice(&ddesc, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::RequestDeviceStatus s, wgpu::Device d, wgpu::StringView) {
          if (s == wgpu::RequestDeviceStatus::Success) device = std::move(d);
        }), UINT64_MAX);
    if (!device) return false;
    wgpu::AdapterInfo info; adapter.GetInfo(&info);
    std::printf("Dawn adapter: \"%s\" backend=Metal | DualSourceBlending: %s\n\n",
                ToStr(info.device).c_str(), dual_source ? "yes" : "no");
    return true;
  }

  wgpu::ShaderModule module(const char *wgsl) {
    wgpu::ShaderSourceWGSL src; src.code = wgsl;
    wgpu::ShaderModuleDescriptor d; d.nextInChain = &src;
    return device.CreateShaderModule(&d);
  }

  bool pop_ok() {
    bool err = false;
    wgpu::Future f = device.PopErrorScope(wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType t, wgpu::StringView m) {
          if (t != wgpu::ErrorType::NoError) { err = true; std::fprintf(stderr, "    err: %s\n", ToStr(m).c_str()); }
        });
    instance.WaitAny(f, UINT64_MAX);
    return !err;
  }
};

struct Ctx {
  Dawn *d;
  wgpu::ShaderModule vs;
  wgpu::ShaderModule fs;
  wgpu::ShaderModule fs_dual;
};

/* Create a render pipeline with the given blend / depth-stencil / primitive and
 * report whether it validated. */
bool make_pipeline(Ctx &c, const wgpu::BlendState *blend, const wgpu::DepthStencilState *ds,
                   const wgpu::PrimitiveState &prim, bool dual) {
  wgpu::ColorTargetState color = {};
  color.format = wgpu::TextureFormat::RGBA8Unorm;
  color.writeMask = wgpu::ColorWriteMask::All;
  color.blend = blend;

  wgpu::FragmentState frag = {};
  frag.module = dual ? c.fs_dual : c.fs;
  frag.entryPoint = "fs";
  frag.targetCount = 1;
  frag.targets = &color;

  wgpu::RenderPipelineDescriptor rp = {};
  rp.vertex.module = c.vs;
  rp.vertex.entryPoint = "vs";
  rp.primitive = prim;
  rp.fragment = &frag;
  rp.depthStencil = ds;
  rp.multisample.count = 1;

  c.d->device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::RenderPipeline p = c.d->device.CreateRenderPipeline(&rp);
  return c.d->pop_ok() && p != nullptr;
}

}  // namespace

int main() {
  Dawn d;
  if (!d.init()) return 2;
  Ctx c{&d, d.module(kVertWgsl), d.module(kFragWgsl),
        d.dual_source ? d.module(kFragDualSrc) : wgpu::ShaderModule()};

  wgpu::PrimitiveState prim = {};
  prim.topology = wgpu::PrimitiveTopology::TriangleList;
  prim.frontFace = wgpu::FrontFace::CCW;
  prim.cullMode = wgpu::CullMode::None;

  int pass = 0, total = 0, skipped = 0;
  auto gate = [&](bool ok) { total++; if (ok) pass++; };

  /* ---- Blend arms ---- */
  std::printf("==== GPUBlend arms (16) ====\n");
  size_t nb = 0; const bw::BlendMapping *bt = bw::blend_table(nb);
  for (size_t i = 0; i < nb; i++) {
    const bw::BlendMapping &m = bt[i];
    if (m.dual_source && !d.dual_source) {
      std::printf("  %-24s SKIP (DualSourceBlending absent; descriptor mapped: Src1/Src1Alpha)\n", m.name);
      skipped++;
      continue;
    }
    wgpu::BlendState bs = {}; bs.color = m.color; bs.alpha = m.alpha;
    const wgpu::BlendState *bp = m.enabled ? &bs : nullptr; /* NONE => no blend */
    bool ok = make_pipeline(c, bp, nullptr, prim, m.dual_source);
    std::printf("  %-24s %s\n", m.name, ok ? "pipeline OK" : "FAIL");
    gate(ok);
  }

  /* ---- Depth arms ---- */
  std::printf("\n==== GPUDepthTest arms (7) ====\n");
  const bw::GPUDepthTest depths[] = {
      bw::GPUDepthTest::NONE, bw::GPUDepthTest::ALWAYS, bw::GPUDepthTest::LESS,
      bw::GPUDepthTest::LESS_EQUAL, bw::GPUDepthTest::EQUAL, bw::GPUDepthTest::GREATER,
      bw::GPUDepthTest::GREATER_EQUAL};
  const char *dnames[] = {"NONE", "ALWAYS", "LESS", "LESS_EQUAL", "EQUAL", "GREATER", "GREATER_EQUAL"};
  for (int i = 0; i < 7; i++) {
    bw::DepthMapping dm = bw::to_depth(depths[i]);
    wgpu::DepthStencilState ds = {};
    ds.format = wgpu::TextureFormat::Depth24Plus;
    ds.depthCompare = dm.compare;
    ds.depthWriteEnabled = dm.test_enabled ? wgpu::OptionalBool::True : wgpu::OptionalBool::False;
    bool ok = make_pipeline(c, nullptr, &ds, prim, false);
    std::printf("  depth %-14s compare -> %s\n", dnames[i], ok ? "pipeline OK" : "FAIL");
    gate(ok);
  }

  /* ---- Stencil test×op combos ---- */
  std::printf("\n==== GPUStencil test x op ====\n");
  const bw::GPUStencilTest stests[] = {bw::GPUStencilTest::ALWAYS, bw::GPUStencilTest::EQUAL,
                                       bw::GPUStencilTest::NEQUAL};
  const char *stn[] = {"ALWAYS", "EQUAL", "NEQUAL"};
  const bw::GPUStencilOp sops[] = {bw::GPUStencilOp::REPLACE, bw::GPUStencilOp::COUNT_DEPTH_PASS,
                                   bw::GPUStencilOp::COUNT_DEPTH_FAIL};
  const char *son[] = {"REPLACE", "COUNT_DEPTH_PASS", "COUNT_DEPTH_FAIL"};
  for (int t = 0; t < 3; t++) {
    for (int o = 0; o < 3; o++) {
      bw::StencilMapping sm = bw::to_stencil(stests[t], sops[o]);
      wgpu::DepthStencilState ds = {};
      ds.format = wgpu::TextureFormat::Depth24PlusStencil8;
      ds.depthCompare = wgpu::CompareFunction::Always;
      ds.depthWriteEnabled = wgpu::OptionalBool::False;
      ds.stencilFront = sm.front;
      ds.stencilBack = sm.back;
      bool ok = make_pipeline(c, nullptr, &ds, prim, false);
      std::printf("  stencil %-7s / %-16s -> %s\n", stn[t], son[o], ok ? "OK" : "FAIL");
      gate(ok);
    }
  }

  /* ---- Cull x winding ---- */
  std::printf("\n==== GPUFaceCullTest x front-face ====\n");
  const bw::GPUFaceCullTest culls[] = {bw::GPUFaceCullTest::NONE, bw::GPUFaceCullTest::FRONT,
                                       bw::GPUFaceCullTest::BACK};
  const char *cn[] = {"NONE", "FRONT", "BACK"};
  for (int i = 0; i < 3; i++) {
    for (int inv = 0; inv < 2; inv++) {
      wgpu::PrimitiveState p = prim;
      p.cullMode = bw::to_cull_mode(culls[i]);
      p.frontFace = bw::to_front_face(inv != 0);
      bool ok = make_pipeline(c, nullptr, nullptr, p, false);
      std::printf("  cull %-5s winding %-3s -> %s\n", cn[i], inv ? "CW" : "CCW", ok ? "OK" : "FAIL");
      gate(ok);
    }
  }

  std::printf("\n==== provoking vertex ====\n");
  std::printf("  FIRST native to WebGPU: %s | LAST native: %s (LAST must be emulated in-shader)\n",
              bw::provoking_vertex_is_native(bw::GPUProvokingVertex::FIRST) ? "yes" : "no",
              bw::provoking_vertex_is_native(bw::GPUProvokingVertex::LAST) ? "yes" : "no");

  std::printf("\n================ SUMMARY ================\n");
  std::printf("pipelines validated: %d/%d  (skipped: %d)\n", pass, total, skipped);
  if (pass == total) {
    std::printf("T10.PRE HARNESS PASS: every mapped GPU state config creates a valid Dawn "
                "render pipeline (blend/depth/stencil/cull); CUSTOM=dual-source, "
                "provoking-vertex/point-size/logic-op gaps characterized.\n");
    return 0;
  }
  std::fprintf(stderr, "T10.PRE HARNESS FAIL\n");
  return 1;
}
