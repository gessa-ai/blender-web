/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.pointsize.pre live harness — the program's first RENDERED-CONTENT check.
 * Compiles the gl_PointSize→instanced-quad rewrite through the T7.pre chain
 * (shaderc→Tint→WGSL), builds a real pipeline, RENDERS a 3-point grid offscreen
 * at point sizes 1 / 5 / 9 px into a 64×64 target, reads the pixels back and
 * asserts coverage: each point center is lit, the gaps between points are dark,
 * and — per size — a pixel inside the radius is lit while one outside is dark. */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "webgpu/webgpu_cpp.h"

#include "wgpu_pointsize_expand.hh"
#include "wgpu_shader_compiler.hh"  // T7.pre chain

namespace bw = blender::gpu::webgpu;

namespace {

std::string ToStr(wgpu::StringView s) {
  if (s.data == nullptr) return {};
  if (s.length == WGPU_STRLEN) return std::string(s.data);
  return std::string(s.data, s.length);
}
uint32_t align256(uint32_t x) { return (x + 255u) & ~255u; }

constexpr uint32_t W = 64, H = 64;

struct Dawn {
  wgpu::Instance instance;
  wgpu::Adapter adapter;
  wgpu::Device device;
  wgpu::Queue queue;
  bool init() {
    wgpu::InstanceDescriptor idesc = {};
    static constexpr auto kTWA = wgpu::InstanceFeatureName::TimedWaitAny;
    idesc.requiredFeatureCount = 1; idesc.requiredFeatures = &kTWA;
    instance = wgpu::CreateInstance(&idesc);
    if (!instance) return false;
    wgpu::RequestAdapterOptions ao = {}; ao.backendType = wgpu::BackendType::Metal;
    ao.featureLevel = wgpu::FeatureLevel::Core;
    instance.WaitAny(instance.RequestAdapter(&ao, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::RequestAdapterStatus s, wgpu::Adapter a, wgpu::StringView) {
          if (s == wgpu::RequestAdapterStatus::Success) adapter = std::move(a); }), UINT64_MAX);
    if (!adapter) return false;
    wgpu::DeviceDescriptor dd = {};
    dd.SetUncapturedErrorCallback([](const wgpu::Device&, wgpu::ErrorType t, wgpu::StringView m) {
      std::fprintf(stderr, "UNCAPTURED(%d): %s\n", int(t), ToStr(m).c_str()); });
    instance.WaitAny(adapter.RequestDevice(&dd, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::RequestDeviceStatus s, wgpu::Device d, wgpu::StringView) {
          if (s == wgpu::RequestDeviceStatus::Success) device = std::move(d); }), UINT64_MAX);
    if (!device) return false;
    queue = device.GetQueue();
    wgpu::AdapterInfo info; adapter.GetInfo(&info);
    std::printf("Dawn adapter: \"%s\" backend=Metal\n\n", ToStr(info.device).c_str());
    return true;
  }
  std::vector<uint8_t> read(const wgpu::Buffer &b, uint32_t n) {
    bool ok = false;
    wgpu::Future f = b.MapAsync(wgpu::MapMode::Read, 0, n, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::MapAsyncStatus s, wgpu::StringView) { ok = (s == wgpu::MapAsyncStatus::Success); });
    instance.WaitAny(f, UINT64_MAX);
    std::vector<uint8_t> out;
    if (ok) { const uint8_t *p = static_cast<const uint8_t*>(b.GetConstMappedRange(0, n));
      if (p) out.assign(p, p + n); b.Unmap(); }
    return out;
  }
};

/* pixel (px,py) center -> NDC (identity MVP; framebuffer y is down). */
void ndc_of(int px, int py, float &x, float &y) {
  x = (float(px) + 0.5f) / W * 2.0f - 1.0f;
  y = 1.0f - (float(py) + 0.5f) / H * 2.0f;
}

}  // namespace

int main() {
  Dawn d;
  if (!d.init()) return 2;

  /* ---- Compile the rewrite through the T7.pre chain ---- */
  bw::ShaderStageSources src;
  src.vertex = bw::rewritten_point_vert();
  src.fragment = bw::rewritten_point_frag();
  src.name = "point_uniform_size_aa_expanded";
  bw::CompileResult cr = bw::compile_shader(src, bw::point_resources());
  if (!cr.ok) { std::fprintf(stderr, "T7 compile FAIL: %s\n", cr.error.c_str()); return 3; }
  std::printf("compiled rewrite via shaderc->Tint->WGSL (%zu BGL entries)\n\n",
              cr.interface.entries.size());

  wgpu::ShaderSourceWGSL vsrc; vsrc.code = cr.vertex_wgsl.c_str();
  wgpu::ShaderModuleDescriptor vmd; vmd.nextInChain = &vsrc;
  wgpu::ShaderModule vmod = d.device.CreateShaderModule(&vmd);
  wgpu::ShaderSourceWGSL fsrc; fsrc.code = cr.fragment_wgsl.c_str();
  wgpu::ShaderModuleDescriptor fmd; fmd.nextInChain = &fsrc;
  wgpu::ShaderModule fmod = d.device.CreateShaderModule(&fmd);

  /* ---- BGL + pipeline ---- */
  wgpu::BindGroupLayoutDescriptor bgld = {};
  bgld.entryCount = cr.interface.entries.size();
  bgld.entries = cr.interface.entries.data();
  wgpu::BindGroupLayout bgl = d.device.CreateBindGroupLayout(&bgld);
  wgpu::PipelineLayoutDescriptor pld = {}; pld.bindGroupLayoutCount = 1; pld.bindGroupLayouts = &bgl;
  wgpu::PipelineLayout playout = d.device.CreatePipelineLayout(&pld);

  wgpu::VertexAttribute attr = {.format = wgpu::VertexFormat::Float32x3, .offset = 0, .shaderLocation = 0};
  wgpu::VertexBufferLayout vbl = {};
  vbl.arrayStride = 12; vbl.stepMode = wgpu::VertexStepMode::Instance;  /* pos is per-point */
  vbl.attributeCount = 1; vbl.attributes = &attr;

  wgpu::ColorTargetState color = {}; color.format = wgpu::TextureFormat::RGBA8Unorm;
  color.writeMask = wgpu::ColorWriteMask::All;
  wgpu::FragmentState fs = {}; fs.module = fmod; fs.entryPoint = "main"; fs.targetCount = 1; fs.targets = &color;
  wgpu::RenderPipelineDescriptor rp = {};
  rp.layout = playout;
  rp.vertex.module = vmod; rp.vertex.entryPoint = "main"; rp.vertex.bufferCount = 1; rp.vertex.buffers = &vbl;
  rp.fragment = &fs;
  rp.primitive.topology = wgpu::PrimitiveTopology::TriangleStrip;
  rp.primitive.cullMode = wgpu::CullMode::None;
  rp.multisample.count = 1;
  d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::RenderPipeline pipeline = d.device.CreateRenderPipeline(&rp);
  { bool err = false; wgpu::Future f = d.device.PopErrorScope(wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType t, wgpu::StringView m){ if (t!=wgpu::ErrorType::NoError){err=true; std::fprintf(stderr,"pipeline: %s\n",ToStr(m).c_str());} });
    d.instance.WaitAny(f, UINT64_MAX); if (err || !pipeline) { std::fprintf(stderr,"pipeline FAIL\n"); return 4; } }

  /* ---- UBO + vertex buffer (3-point grid) + bind group ---- */
  const int cx[3] = {16, 32, 48}, cy = 32;
  float verts[9];
  for (int i = 0; i < 3; i++) { ndc_of(cx[i], cy, verts[i*3+0], verts[i*3+1]); verts[i*3+2] = 0.0f; }
  wgpu::BufferDescriptor vbd = {}; vbd.size = sizeof(verts);
  vbd.usage = wgpu::BufferUsage::Vertex | wgpu::BufferUsage::CopyDst;
  wgpu::Buffer vbuf = d.device.CreateBuffer(&vbd);
  d.queue.WriteBuffer(vbuf, 0, verts, sizeof(verts));

  wgpu::BufferDescriptor ubd = {}; ubd.size = sizeof(bw::PointGlobals);
  ubd.usage = wgpu::BufferUsage::Uniform | wgpu::BufferUsage::CopyDst;
  wgpu::Buffer ubo = d.device.CreateBuffer(&ubd);

  wgpu::BindGroupEntry be = {}; be.binding = 0; be.buffer = ubo; be.size = sizeof(bw::PointGlobals);
  wgpu::BindGroupDescriptor bgd = {}; bgd.layout = bgl; bgd.entryCount = 1; bgd.entries = &be;
  wgpu::BindGroup bg = d.device.CreateBindGroup(&bgd);

  /* ---- Render + readback per size ---- */
  const uint32_t abpr = align256(W * 4);
  struct SizeCheck { float size; int inner_off; int outer_off; };
  const SizeCheck checks[] = {{1.0f, 0, 3}, {5.0f, 1, 5}, {9.0f, 3, 6}};
  int fails = 0;

  for (const SizeCheck &sc : checks) {
    bw::PointGlobals g = {};
    const float I[16] = {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1};
    std::memcpy(g.mvp, I, sizeof(I));
    g.color[0] = g.color[1] = g.color[2] = g.color[3] = 1.0f;  /* opaque white */
    g.viewport[0] = float(W); g.viewport[1] = float(H); g.size = sc.size;
    d.queue.WriteBuffer(ubo, 0, &g, sizeof(g));

    wgpu::TextureDescriptor td = {};
    td.usage = wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::CopySrc;
    td.dimension = wgpu::TextureDimension::e2D; td.size = {W, H, 1};
    td.format = wgpu::TextureFormat::RGBA8Unorm;
    wgpu::Texture rt = d.device.CreateTexture(&td);
    wgpu::TextureView rtv = rt.CreateView();

    wgpu::RenderPassColorAttachment ca = {};
    ca.view = rtv; ca.loadOp = wgpu::LoadOp::Clear; ca.storeOp = wgpu::StoreOp::Store;
    ca.clearValue = {0, 0, 0, 1};
    wgpu::RenderPassDescriptor rpd = {}; rpd.colorAttachmentCount = 1; rpd.colorAttachments = &ca;
    wgpu::CommandEncoder enc = d.device.CreateCommandEncoder();
    wgpu::RenderPassEncoder pass = enc.BeginRenderPass(&rpd);
    pass.SetPipeline(pipeline);
    pass.SetBindGroup(0, bg);
    pass.SetVertexBuffer(0, vbuf);
    pass.Draw(4, 3);   /* 4-vertex quad × 3 point instances */
    pass.End();

    wgpu::BufferDescriptor rbd = {}; rbd.size = size_t(abpr) * H;
    rbd.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
    wgpu::Buffer rb = d.device.CreateBuffer(&rbd);
    wgpu::TexelCopyTextureInfo srct = {}; srct.texture = rt;
    wgpu::TexelCopyBufferInfo dstb = {}; dstb.buffer = rb; dstb.layout.bytesPerRow = abpr; dstb.layout.rowsPerImage = H;
    wgpu::Extent3D ext = {W, H, 1};
    enc.CopyTextureToBuffer(&srct, &dstb, &ext);
    wgpu::CommandBuffer cb = enc.Finish();
    d.queue.Submit(1, &cb);
    std::vector<uint8_t> img = d.read(rb, uint32_t(rbd.size));
    if (img.empty()) { std::fprintf(stderr, "readback FAIL\n"); return 5; }

    auto R = [&](int x, int y) -> int { return img[size_t(y) * abpr + size_t(x) * 4]; };
    auto covered = [&](int x, int y) { return R(x, y) > 128; };

    /* ASCII strip of row 32 (cols 8..56) as rendered-content evidence. */
    std::printf("  size=%2.0fpx row%2d: ", sc.size, cy);
    for (int x = 8; x <= 56; x++) std::putchar(covered(x, cy) ? '#' : '.');
    std::putchar('\n');

    bool ok = true;
    for (int i = 0; i < 3; i++) ok = ok && covered(cx[i], cy);      /* centers lit */
    ok = ok && !covered(24, cy) && !covered(40, cy);                /* gaps dark */
    if (sc.inner_off > 0) ok = ok && covered(32 + sc.inner_off, cy);/* inside radius lit */
    ok = ok && !covered(32 + sc.outer_off, cy);                     /* outside radius dark */
    std::printf("    checks: 3 centers lit, 2 gaps dark, inner(+%d)=%s, outer(+%d)=%s -> %s\n",
                sc.inner_off, sc.inner_off ? (covered(32+sc.inner_off,cy)?"lit":"DARK") : "n/a",
                sc.outer_off, covered(32+sc.outer_off,cy)?"LIT":"dark", ok ? "PASS" : "FAIL");
    if (!ok) fails++;
  }

  std::printf("\n================ SUMMARY ================\n");
  if (fails == 0) {
    std::printf("POINTSIZE PROTOTYPE PASS: the gl_PointSize->instanced-quad rewrite compiles "
                "through the T7 chain and RENDERS correct point coverage at 1/5/9 px on Dawn.\n");
    return 0;
  }
  std::fprintf(stderr, "POINTSIZE PROTOTYPE FAIL (%d size(s))\n", fails);
  return 1;
}
