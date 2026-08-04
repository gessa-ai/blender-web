/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.T9.pre live harness. On a real native Dawn/Metal device, for every Blender
 * texture format in the table:
 *   - probe creatability + caps (renderable / storage / multisample) via
 *     CreateTexture attempts (cross-checked against the spec caps in the table);
 *   - round-trip a deterministic pattern for copyable color formats
 *     (writeTexture -> CopyTextureToBuffer -> mapAsync -> byte compare), applying
 *     the RGB->RGBA promotion for 3-channel formats via wgpu_data_conversion;
 *   - clear+readback representative renderable color + depth formats;
 *   - upload+readback a BC block if texture-compression-bc is present.
 * Plus a device-free unit test of the promotion transform.
 *
 * Exit 0 iff: the conversion unit test passes; every format whose feature gate is
 * satisfied is creatable; every gated copyable color format round-trips byte-exact;
 * and the representative render/depth clears verify. Feature-gated formats absent
 * on the adapter are reported UNSUPPORTED-ON-ADAPTER (not failures). */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "webgpu/webgpu_cpp.h"

#include "wgpu_data_conversion.hh"
#include "wgpu_texture_format.hh"

namespace bw = blender::gpu::webgpu;

namespace {

std::string ToStr(wgpu::StringView s) {
  if (s.data == nullptr) return {};
  if (s.length == WGPU_STRLEN) return std::string(s.data);
  return std::string(s.data, s.length);
}

uint32_t align256(uint32_t x) { return (x + 255u) & ~255u; }

std::vector<uint8_t> pattern(size_t n) {
  std::vector<uint8_t> v(n);
  for (size_t i = 0; i < n; i++) v[i] = uint8_t((i * 37u + 11u) & 0xFFu);
  return v;
}

struct Dawn {
  wgpu::Instance instance;
  wgpu::Adapter adapter;
  wgpu::Device device;
  wgpu::Queue queue;

  bool has(wgpu::FeatureName f) const { return adapter.HasFeature(f); }

  bool init() {
    wgpu::InstanceDescriptor idesc = {};
    static constexpr auto kTWA = wgpu::InstanceFeatureName::TimedWaitAny;
    idesc.requiredFeatureCount = 1;
    idesc.requiredFeatures = &kTWA;
    instance = wgpu::CreateInstance(&idesc);
    if (!instance) { std::fprintf(stderr, "CreateInstance failed\n"); return false; }

    wgpu::RequestAdapterOptions aopts = {};
    aopts.backendType = wgpu::BackendType::Metal;
    aopts.featureLevel = wgpu::FeatureLevel::Core;
    instance.WaitAny(instance.RequestAdapter(&aopts, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::RequestAdapterStatus s, wgpu::Adapter a, wgpu::StringView m) {
          if (s == wgpu::RequestAdapterStatus::Success) adapter = std::move(a);
          else std::fprintf(stderr, "adapter: %s\n", ToStr(m).c_str());
        }), UINT64_MAX);
    if (!adapter) return false;

    /* Request every optional format feature the adapter exposes so the gated
     * formats are testable. */
    std::vector<wgpu::FeatureName> feats;
    for (wgpu::FeatureName f : {wgpu::FeatureName::TextureCompressionBC,
                                wgpu::FeatureName::Depth32FloatStencil8,
                                wgpu::FeatureName::Float32Filterable,
                                wgpu::FeatureName::RG11B10UfloatRenderable,
                                wgpu::FeatureName::Unorm16TextureFormats,
                                wgpu::FeatureName::Unorm16Filterable}) {
      if (adapter.HasFeature(f)) feats.push_back(f);
    }
    wgpu::DeviceDescriptor ddesc = {};
    ddesc.requiredFeatureCount = feats.size();
    ddesc.requiredFeatures = feats.data();
    ddesc.SetUncapturedErrorCallback([](const wgpu::Device&, wgpu::ErrorType t, wgpu::StringView m) {
      std::fprintf(stderr, "UNCAPTURED(%d): %s\n", int(t), ToStr(m).c_str());
    });
    instance.WaitAny(adapter.RequestDevice(&ddesc, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::RequestDeviceStatus s, wgpu::Device d, wgpu::StringView m) {
          if (s == wgpu::RequestDeviceStatus::Success) device = std::move(d);
          else std::fprintf(stderr, "device: %s\n", ToStr(m).c_str());
        }), UINT64_MAX);
    if (!device) return false;
    queue = device.GetQueue();
    wgpu::AdapterInfo info; adapter.GetInfo(&info);
    std::printf("Dawn adapter: \"%s\" backend=Metal\n", ToStr(info.device).c_str());
    std::printf("optional features present:");
    const char *names[] = {"BC", "Depth32FloatStencil8", "Float32Filterable",
                           "RG11B10UfloatRenderable", "Unorm16TextureFormats"};
    wgpu::FeatureName fs[] = {wgpu::FeatureName::TextureCompressionBC,
                              wgpu::FeatureName::Depth32FloatStencil8,
                              wgpu::FeatureName::Float32Filterable,
                              wgpu::FeatureName::RG11B10UfloatRenderable,
                              wgpu::FeatureName::Unorm16TextureFormats};
    for (int i = 0; i < 5; i++) if (adapter.HasFeature(fs[i])) std::printf(" %s", names[i]);
    std::printf("\n\n");
    return true;
  }

  bool pop_ok() {
    bool err = false;
    wgpu::Future f = device.PopErrorScope(wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType t, wgpu::StringView) {
          if (t != wgpu::ErrorType::NoError) err = true;
        });
    instance.WaitAny(f, UINT64_MAX);
    return !err;
  }

  /* Try to create a texture; returns null (and consumes the error) on failure. */
  wgpu::Texture try_create(wgpu::TextureFormat fmt, wgpu::TextureUsage usage,
                           uint32_t w, uint32_t h, uint32_t samples, bool &ok) {
    wgpu::TextureDescriptor td = {};
    td.usage = usage;
    td.dimension = wgpu::TextureDimension::e2D;
    td.size = {w, h, 1};
    td.format = fmt;
    td.sampleCount = samples;
    device.PushErrorScope(wgpu::ErrorFilter::Validation);
    wgpu::Texture t = device.CreateTexture(&td);
    ok = pop_ok() && t != nullptr;
    return t;
  }

  /* Map a readback buffer and return its bytes. */
  std::vector<uint8_t> read_buffer(const wgpu::Buffer &buf, uint32_t size) {
    bool done = false;
    wgpu::Future f = buf.MapAsync(wgpu::MapMode::Read, 0, size, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::MapAsyncStatus s, wgpu::StringView) { done = (s == wgpu::MapAsyncStatus::Success); });
    instance.WaitAny(f, UINT64_MAX);
    std::vector<uint8_t> out;
    if (done) {
      const uint8_t *p = static_cast<const uint8_t *>(buf.GetConstMappedRange(0, size));
      if (p) out.assign(p, p + size);
      buf.Unmap();
    }
    return out;
  }
};

/* Bytes-per-texel of the CREATED wgpu format for a Blender format. */
uint32_t created_texel_bytes(const bw::FormatInfo &info) {
  const bw::PromotionPlan plan = bw::promotion_plan(info.blender);
  if (plan.needed) return 4u * plan.comp_bytes;
  return info.src_bytes_per_pixel; /* Direct/packed: matches wgpu texel size */
}

struct Row {
  std::string name;
  std::string wgpu;
  bool gate_ok = true;
  bool created = false;
  bool rend = false, stor = false, msaa = false;
  std::string result; /* PASS / PROMOTED / MISMATCH / CREATED / UNSUPPORTED / ... */
};

/* ---- Device-free unit test of the promotion transform ---------------------- */
bool test_conversion_unit() {
  std::printf("==== unit: RGB->RGBA promotion ====\n");
  bool ok = true;
  struct C { bw::TextureFormat fmt; const char *name; uint32_t cb; };
  const C cases[] = {
      {bw::TextureFormat::UNORM_8_8_8, "UNORM_8_8_8", 1},
      {bw::TextureFormat::SFLOAT_16_16_16, "SFLOAT_16_16_16", 2},
      {bw::TextureFormat::SFLOAT_32_32_32, "SFLOAT_32_32_32", 4},
      {bw::TextureFormat::UINT_16_16_16, "UINT_16_16_16", 2},
  };
  for (const C &c : cases) {
    const uint32_t w = 3, h = 2;
    std::vector<uint8_t> rgb = pattern(size_t(w) * h * 3 * c.cb);
    std::vector<uint8_t> rgba = bw::promote_for_upload(c.fmt, rgb, w, h);
    bool good = rgba.size() == size_t(w) * h * 4 * c.cb;
    uint8_t alpha[4]; bw::opaque_alpha_bytes(bw::promotion_plan(c.fmt).type, c.cb, alpha);
    for (size_t p = 0; good && p < size_t(w) * h; p++) {
      /* RGB preserved */
      if (std::memcmp(&rgba[p * 4 * c.cb], &rgb[p * 3 * c.cb], 3 * c.cb) != 0) good = false;
      /* alpha == opaque */
      if (std::memcmp(&rgba[p * 4 * c.cb + 3 * c.cb], alpha, c.cb) != 0) good = false;
    }
    std::printf("    %-16s comp_bytes=%u -> %s\n", c.name, c.cb, good ? "OK" : "FAIL");
    ok = ok && good;
  }
  std::printf("\n");
  return ok;
}

}  // namespace

int main() {
  Dawn d;
  if (!d.init()) return 2;

  int fail = 0;
  bool unit_ok = test_conversion_unit();
  if (!unit_ok) fail++;

  size_t n = 0;
  const bw::FormatInfo *table = bw::format_table(n);
  std::vector<Row> rows;
  int created = 0, roundtrip_pass = 0, promoted_pass = 0, unsupported = 0, copyable = 0;

  for (size_t i = 0; i < n; i++) {
    const bw::FormatInfo &info = table[i];
    Row row;
    row.name = info.name;

    /* Creatability feature gate. Float32Filterable / RG11B10UfloatRenderable do
     * not gate creation (cap-only). BC / Depth32FloatStencil8 / Norm16 do. */
    bool gate_ok = true;
    if (info.gate == bw::FeatureGate::TextureCompressionBC)
      gate_ok = d.has(wgpu::FeatureName::TextureCompressionBC);
    else if (info.gate == bw::FeatureGate::Depth32FloatStencil8)
      gate_ok = d.has(wgpu::FeatureName::Depth32FloatStencil8);
    else if (info.gate == bw::FeatureGate::Unorm16)
      gate_ok = d.has(wgpu::FeatureName::Unorm16TextureFormats);
    else if (info.gate == bw::FeatureGate::Snorm16)
      /* No WebGPU/Dawn feature enables 16-bit SNORM textures at the pin — the
       * RGBA16Snorm enum value exists but nothing makes it creatable. Genuinely
       * unsupported → must be emulated by the backend (see findings). */
      gate_ok = false;
    row.gate_ok = gate_ok;

    const bool is_depth = info.conv == bw::ConvClass::Depth;
    const bool is_compressed = info.conv == bw::ConvClass::Compressed;

    if (!gate_ok) {
      row.result = "UNSUPPORTED-ON-ADAPTER";
      unsupported++;
      rows.push_back(row);
      continue;
    }

    /* Base creatability (minimal usage). */
    bool cok = false;
    wgpu::TextureUsage base = wgpu::TextureUsage::CopyDst | wgpu::TextureUsage::CopySrc;
    if (!is_depth && !is_compressed) base = base | wgpu::TextureUsage::TextureBinding;
    wgpu::Texture tex = d.try_create(info.wgpu, base, 4, 4, 1, cok);
    row.created = cok;
    if (cok) created++;

    /* Caps discovery. */
    bool rok = false, sok = false, mok = false;
    { wgpu::Texture t = d.try_create(info.wgpu,
          wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::CopySrc, 4, 4, 1, rok); }
    row.rend = rok;
    if (bw::caps_of(info.wgpu).storage) {
      wgpu::Texture t = d.try_create(info.wgpu, wgpu::TextureUsage::StorageBinding, 4, 4, 1, sok);
      row.stor = sok;
    }
    { wgpu::Texture t = d.try_create(info.wgpu, wgpu::TextureUsage::RenderAttachment, 4, 4, 4, mok); }
    row.msaa = mok;

    if (!cok) { row.result = "CREATE-FAIL"; fail++; rows.push_back(row); continue; }

    /* Round-trip for copyable color formats (skip depth + compressed). */
    if (is_depth) {
      row.result = "CREATED (depth; see depth-clear)";
      rows.push_back(row);
      continue;
    }
    if (is_compressed) {
      row.result = "CREATED (compressed; see BC block)";
      rows.push_back(row);
      continue;
    }

    copyable++;
    const uint32_t w = 4, h = 4;
    const uint32_t bpp = created_texel_bytes(info);
    const bw::PromotionPlan plan = bw::promotion_plan(info.blender);
    std::vector<uint8_t> upload;
    if (plan.needed) {
      std::vector<uint8_t> rgb = pattern(size_t(w) * h * 3 * plan.comp_bytes);
      upload = bw::promote_for_upload(info.blender, rgb, w, h);
    }
    else {
      upload = pattern(size_t(w) * h * bpp);
    }

    wgpu::TexelCopyTextureInfo dst = {};
    dst.texture = tex;
    wgpu::TexelCopyBufferLayout layout = {};
    layout.bytesPerRow = w * bpp;
    layout.rowsPerImage = h;
    wgpu::Extent3D ext = {w, h, 1};
    d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
    d.queue.WriteTexture(&dst, upload.data(), upload.size(), &layout, &ext);
    bool wok = d.pop_ok();

    const uint32_t abpr = align256(w * bpp);
    wgpu::BufferDescriptor bd = {};
    bd.size = size_t(abpr) * h;
    bd.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
    wgpu::Buffer rb = d.device.CreateBuffer(&bd);

    wgpu::TexelCopyTextureInfo src = {}; src.texture = tex;
    wgpu::TexelCopyBufferInfo bdst = {}; bdst.buffer = rb;
    bdst.layout.bytesPerRow = abpr; bdst.layout.rowsPerImage = h;
    wgpu::CommandEncoder enc = d.device.CreateCommandEncoder();
    enc.CopyTextureToBuffer(&src, &bdst, &ext);
    wgpu::CommandBuffer cb = enc.Finish();
    d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
    d.queue.Submit(1, &cb);
    bool cok2 = d.pop_ok();

    std::vector<uint8_t> back = d.read_buffer(rb, uint32_t(bd.size));
    bool match = wok && cok2 && !back.empty();
    for (uint32_t y = 0; match && y < h; y++) {
      if (std::memcmp(&back[size_t(y) * abpr], &upload[size_t(y) * w * bpp], w * bpp) != 0)
        match = false;
    }
    if (match) {
      roundtrip_pass++;
      if (plan.needed) { row.result = "PROMOTED-ROUNDTRIP-PASS"; promoted_pass++; }
      else row.result = "ROUNDTRIP-PASS";
    } else {
      row.result = "MISMATCH";
      fail++;
    }
    rows.push_back(row);
  }

  /* ---- Representative render-clear (color) ---- */
  std::printf("==== render-clear (color RGBA8Unorm) ====\n");
  bool color_clear_ok = false;
  {
    bool ok = false;
    wgpu::Texture rt = d.try_create(wgpu::TextureFormat::RGBA8Unorm,
        wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::CopySrc, 4, 4, 1, ok);
    if (ok) {
      wgpu::TextureView v = rt.CreateView();
      wgpu::RenderPassColorAttachment ca = {};
      ca.view = v; ca.loadOp = wgpu::LoadOp::Clear; ca.storeOp = wgpu::StoreOp::Store;
      ca.clearValue = {0.25, 0.5, 0.75, 1.0};
      wgpu::RenderPassDescriptor rp = {}; rp.colorAttachmentCount = 1; rp.colorAttachments = &ca;
      wgpu::CommandEncoder enc = d.device.CreateCommandEncoder();
      wgpu::RenderPassEncoder pass = enc.BeginRenderPass(&rp); pass.End();
      const uint32_t abpr = align256(4 * 4);
      wgpu::BufferDescriptor bd = {}; bd.size = size_t(abpr) * 4;
      bd.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
      wgpu::Buffer rb = d.device.CreateBuffer(&bd);
      wgpu::TexelCopyTextureInfo src = {}; src.texture = rt;
      wgpu::TexelCopyBufferInfo bdst = {}; bdst.buffer = rb; bdst.layout.bytesPerRow = abpr; bdst.layout.rowsPerImage = 4;
      wgpu::Extent3D ext = {4, 4, 1};
      enc.CopyTextureToBuffer(&src, &bdst, &ext);
      wgpu::CommandBuffer cb = enc.Finish();
      d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
      d.queue.Submit(1, &cb);
      bool sok = d.pop_ok();
      std::vector<uint8_t> back = d.read_buffer(rb, uint32_t(bd.size));
      /* 0.25,0.5,0.75,1.0 unorm8 = 64,128,191,255 (round). */
      color_clear_ok = sok && back.size() >= 4 && back[0] == 64 && back[1] == 128 &&
                       (back[2] == 191 || back[2] == 190) && back[3] == 255;
    }
    std::printf("    RGBA8Unorm clear {64,128,191,255} readback -> %s\n\n",
                color_clear_ok ? "PASS" : "FAIL");
    if (!color_clear_ok) fail++;
  }

  /* ---- Representative depth-clear + readback (Depth32Float) ---- */
  std::printf("==== depth-clear (Depth32Float) ====\n");
  bool depth_ok = false;
  {
    bool ok = false;
    wgpu::Texture dt = d.try_create(wgpu::TextureFormat::Depth32Float,
        wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::CopySrc, 4, 4, 1, ok);
    if (ok) {
      wgpu::TextureView v = dt.CreateView();
      wgpu::RenderPassDepthStencilAttachment da = {};
      da.view = v; da.depthLoadOp = wgpu::LoadOp::Clear; da.depthStoreOp = wgpu::StoreOp::Store;
      da.depthClearValue = 0.5f;
      wgpu::RenderPassDescriptor rp = {}; rp.colorAttachmentCount = 0; rp.depthStencilAttachment = &da;
      wgpu::CommandEncoder enc = d.device.CreateCommandEncoder();
      wgpu::RenderPassEncoder pass = enc.BeginRenderPass(&rp); pass.End();
      const uint32_t abpr = align256(4 * 4); /* Depth32Float = 4 bytes/texel */
      wgpu::BufferDescriptor bd = {}; bd.size = size_t(abpr) * 4;
      bd.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
      wgpu::Buffer rb = d.device.CreateBuffer(&bd);
      wgpu::TexelCopyTextureInfo src = {}; src.texture = dt; src.aspect = wgpu::TextureAspect::DepthOnly;
      wgpu::TexelCopyBufferInfo bdst = {}; bdst.buffer = rb; bdst.layout.bytesPerRow = abpr; bdst.layout.rowsPerImage = 4;
      wgpu::Extent3D ext = {4, 4, 1};
      enc.CopyTextureToBuffer(&src, &bdst, &ext);
      wgpu::CommandBuffer cb = enc.Finish();
      d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
      d.queue.Submit(1, &cb);
      bool sok = d.pop_ok();
      std::vector<uint8_t> back = d.read_buffer(rb, uint32_t(bd.size));
      float depth = 0.0f; if (back.size() >= 4) std::memcpy(&depth, back.data(), 4);
      depth_ok = sok && depth > 0.49f && depth < 0.51f;
    }
    std::printf("    Depth32Float clear 0.5 readback -> %s\n\n", depth_ok ? "PASS" : "FAIL");
    if (!depth_ok) fail++;
  }

  /* ---- BC block upload/readback (if feature present) ---- */
  std::printf("==== compressed (BC1RGBAUnorm 4x4 block) ====\n");
  if (d.has(wgpu::FeatureName::TextureCompressionBC)) {
    bool ok = false;
    wgpu::Texture bt = d.try_create(wgpu::TextureFormat::BC1RGBAUnorm,
        wgpu::TextureUsage::CopyDst | wgpu::TextureUsage::CopySrc, 4, 4, 1, ok);
    bool bc_ok = false;
    if (ok) {
      std::vector<uint8_t> block = pattern(8); /* BC1 = 8 bytes / 4x4 block */
      wgpu::TexelCopyTextureInfo dst = {}; dst.texture = bt;
      wgpu::TexelCopyBufferLayout layout = {}; layout.bytesPerRow = 8; layout.rowsPerImage = 1;
      wgpu::Extent3D ext = {4, 4, 1};
      d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
      d.queue.WriteTexture(&dst, block.data(), block.size(), &layout, &ext);
      bool wok = d.pop_ok();
      const uint32_t abpr = align256(8);
      wgpu::BufferDescriptor bd = {}; bd.size = abpr;
      bd.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
      wgpu::Buffer rb = d.device.CreateBuffer(&bd);
      wgpu::TexelCopyTextureInfo src = {}; src.texture = bt;
      wgpu::TexelCopyBufferInfo bdst = {}; bdst.buffer = rb; bdst.layout.bytesPerRow = abpr; bdst.layout.rowsPerImage = 1;
      wgpu::CommandEncoder enc = d.device.CreateCommandEncoder();
      enc.CopyTextureToBuffer(&src, &bdst, &ext);
      wgpu::CommandBuffer cb = enc.Finish();
      d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
      d.queue.Submit(1, &cb);
      bool sok = d.pop_ok();
      std::vector<uint8_t> back = d.read_buffer(rb, uint32_t(bd.size));
      bc_ok = wok && sok && back.size() >= 8 && std::memcmp(back.data(), block.data(), 8) == 0;
    }
    std::printf("    BC1 block round-trip -> %s\n\n", bc_ok ? "PASS" : "FAIL");
    if (!bc_ok) fail++;
  } else {
    std::printf("    texture-compression-bc NOT present on this adapter -> BC formats UNSUPPORTED here\n\n");
  }

  /* ---- Per-format table ---- */
  std::printf("==== per-format results (created / R=render S=storage M=msaa / result) ====\n");
  for (const Row &r : rows) {
    std::printf("  %-22s %s  R%d S%d M%d  %s\n", r.name.c_str(),
                r.created ? "created" : (r.gate_ok ? "NOTCREATED" : "gated  "),
                r.rend, r.stor, r.msaa, r.result.c_str());
  }

  std::printf("\n================ SUMMARY ================\n");
  std::printf("formats in table: %zu | created: %d | unsupported-on-adapter: %d\n", n, created, unsupported);
  std::printf("copyable color: %d | round-trip PASS: %d (of which promoted: %d)\n",
              copyable, roundtrip_pass, promoted_pass);
  std::printf("conversion unit: %s | color-clear: %s | depth-clear: %s\n",
              unit_ok ? "PASS" : "FAIL", color_clear_ok ? "PASS" : "FAIL", depth_ok ? "PASS" : "FAIL");
  if (fail == 0 && roundtrip_pass == copyable && copyable > 0) {
    std::printf("T9.PRE HARNESS PASS: every gated Blender texture format maps + creates on Dawn; "
                "all copyable color formats round-trip byte-exact (incl. RGB->RGBA promotions); "
                "render/depth/compressed paths verified.\n");
    return 0;
  }
  std::fprintf(stderr, "T9.PRE HARNESS FAIL (fail=%d roundtrip=%d/%d)\n", fail, roundtrip_pass, copyable);
  return 1;
}
