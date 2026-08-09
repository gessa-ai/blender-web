// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r48 (design lane) - EEVEE storage-texture BindGroupLayout acceptance probe.
//
// Proves, on a real Dawn/Metal device (the same generation as the pinned
// emdawnwebgpu M4 browser path), the three-part hypothesis for unblocking the
// 30 EEVEE M6 render scenes whose pipelines fail at CreateBindGroupLayout:
//
//   (1) VISIBILITY: a writable (WriteOnly / ReadWrite) storage-texture BGL entry
//       is rejected iff its visibility set contains Vertex; narrowing to
//       Fragment-only makes it valid. (Mirrors the RW-storage-buffer strip
//       already in wgpu_shader_interface_map.cc.)
//   (2) FORMAT: the EEVEE g-buffer / film formats that are NOT storage-writable
//       in core WebGPU (RGB10A2Unorm, RG16Unorm, R16Float, RGBA16Float RW, ...)
//       become storage-writable once TextureFormatsTier1 / Tier2 are requested
//       at device creation - IF this adapter exposes them (this probe reports
//       whether it does).
//   (3) LIMITS: >4 storage textures in a single stage needs requiredLimits
//       (maxStorageTexturesPerShaderStage) raised at device creation.
//
// Method: a control device (mirrors today's GHOST_ContextWGPU feature set) and a
// proposed device (control + Tier1 + Tier2 + raised limits). Each runs a matrix
// of CreateBindGroupLayout calls under a Validation error scope; OK/FAIL per cell
// is the evidence. No Blender, no Tint, no shaders - pure Dawn validation.
//
// Exit 0 iff the proposed device accepts every Fragment-only EEVEE-format entry
// AND still rejects the Vertex-visible writable entries (i.e. the fix is real and
// does not over-reach). Boilerplate mirrors sandbox/dawn-probe/probe.cc.

#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#include "webgpu/webgpu_cpp.h"

namespace {

std::string ToStr(wgpu::StringView s) {
  if (s.data == nullptr) return {};
  if (s.length == WGPU_STRLEN) return std::string(s.data);
  return std::string(s.data, s.length);
}

const char* AccessName(wgpu::StorageTextureAccess a) {
  switch (a) {
    case wgpu::StorageTextureAccess::WriteOnly: return "WriteOnly";
    case wgpu::StorageTextureAccess::ReadOnly:  return "ReadOnly";
    case wgpu::StorageTextureAccess::ReadWrite: return "ReadWrite";
    default: return "?";
  }
}

const char* VisName(wgpu::ShaderStage v) {
  if (v == (wgpu::ShaderStage::Vertex | wgpu::ShaderStage::Fragment)) return "Vertex|Fragment";
  if (v == wgpu::ShaderStage::Fragment) return "Fragment";
  if (v == wgpu::ShaderStage::Compute)  return "Compute";
  return "?";
}

struct FmtRow {
  wgpu::TextureFormat fmt;
  const char* blender_fmt;   // Blender BSL format token
  const char* eevee_use;     // where EEVEE uses it
};

// Try CreateBindGroupLayout for one storage-texture entry; return true iff valid.
bool TryStorageTexBGL(const wgpu::Instance& instance,
                      const wgpu::Device& device,
                      wgpu::TextureFormat fmt,
                      wgpu::StorageTextureAccess access,
                      wgpu::ShaderStage vis,
                      std::string& err) {
  device.PushErrorScope(wgpu::ErrorFilter::Validation);

  wgpu::BindGroupLayoutEntry e = {};
  e.binding = 0;
  e.visibility = vis;
  e.storageTexture.access = access;
  e.storageTexture.format = fmt;
  e.storageTexture.viewDimension = wgpu::TextureViewDimension::e2DArray;

  wgpu::BindGroupLayoutDescriptor d = {};
  d.entryCount = 1;
  d.entries = &e;
  wgpu::BindGroupLayout bgl = device.CreateBindGroupLayout(&d);

  bool had_error = false;
  wgpu::Future pop = device.PopErrorScope(
      wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView msg) {
        if (type != wgpu::ErrorType::NoError) { had_error = true; err = ToStr(msg); }
      });
  instance.WaitAny(pop, UINT64_MAX);
  return !had_error && bgl != nullptr;
}

// Try a BGL with `count` WriteOnly R32Uint storage textures in one stage.
bool TryStorageTexCount(const wgpu::Instance& instance,
                        const wgpu::Device& device,
                        uint32_t count,
                        wgpu::ShaderStage vis,
                        std::string& err) {
  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  std::vector<wgpu::BindGroupLayoutEntry> entries(count);
  for (uint32_t i = 0; i < count; i++) {
    entries[i].binding = i;
    entries[i].visibility = vis;
    entries[i].storageTexture.access = wgpu::StorageTextureAccess::WriteOnly;
    entries[i].storageTexture.format = wgpu::TextureFormat::R32Uint;
    entries[i].storageTexture.viewDimension = wgpu::TextureViewDimension::e2D;
  }
  wgpu::BindGroupLayoutDescriptor d = {};
  d.entryCount = entries.size();
  d.entries = entries.data();
  wgpu::BindGroupLayout bgl = device.CreateBindGroupLayout(&d);
  bool had_error = false;
  wgpu::Future pop = device.PopErrorScope(
      wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView msg) {
        if (type != wgpu::ErrorType::NoError) { had_error = true; err = ToStr(msg); }
      });
  instance.WaitAny(pop, UINT64_MAX);
  return !had_error && bgl != nullptr;
}

// A Dawn adapter is single-use ("consumed" after one CreateDevice), so request a
// fresh adapter for each device we build.
wgpu::Adapter RequestAdapter(const wgpu::Instance& instance) {
  wgpu::RequestAdapterOptions opts = {};
  opts.backendType = wgpu::BackendType::Metal;
  opts.featureLevel = wgpu::FeatureLevel::Core;
  wgpu::Adapter adapter;
  instance.WaitAny(
      instance.RequestAdapter(
          &opts, wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestAdapterStatus status, wgpu::Adapter a, wgpu::StringView msg) {
            if (status == wgpu::RequestAdapterStatus::Success) adapter = std::move(a);
            else std::cerr << "RequestAdapter failed: " << ToStr(msg) << "\n";
          }),
      UINT64_MAX);
  return adapter;
}

wgpu::Device MakeDevice(const wgpu::Instance& instance,
                        const wgpu::Adapter& adapter,
                        const std::vector<wgpu::FeatureName>& features,
                        bool raise_limits) {
  wgpu::DeviceDescriptor desc = {};
  desc.requiredFeatureCount = features.size();
  desc.requiredFeatures = features.empty() ? nullptr : features.data();

  wgpu::Limits limits = {};
  if (raise_limits) {
    // Pull the adapter's supported ceiling and ask for it (mirrors what the
    // backend should do at RequestDevice). Default core is 4 storage textures /
    // 8 storage buffers per stage; EEVEE compute passes bind more.
    wgpu::Limits supported = {};
    adapter.GetLimits(&supported);
    limits.maxStorageTexturesPerShaderStage = supported.maxStorageTexturesPerShaderStage;
    limits.maxStorageBuffersPerShaderStage = supported.maxStorageBuffersPerShaderStage;
    desc.requiredLimits = &limits;
  }

  desc.SetUncapturedErrorCallback(
      [](const wgpu::Device&, wgpu::ErrorType type, wgpu::StringView msg) {
        std::cerr << "  [uncaptured type " << static_cast<int>(type) << "] "
                  << ToStr(msg) << "\n";
      });
  wgpu::Device device;
  instance.WaitAny(
      adapter.RequestDevice(
          &desc, wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestDeviceStatus status, wgpu::Device d, wgpu::StringView msg) {
            if (status != wgpu::RequestDeviceStatus::Success) {
              std::cerr << "  RequestDevice failed: " << ToStr(msg) << "\n";
              return;
            }
            device = std::move(d);
          }),
      UINT64_MAX);
  return device;
}

// The EEVEE writable storage-texture formats seen failing in the real render
// captures (sandbox/gpu-r44/resolve_default.dump.txt, gpu-r44-r3/shadow_info.log).
const std::vector<FmtRow> kWriteFmts = {
    {wgpu::TextureFormat::RGB10A2Unorm, "UNORM_10_10_10_2", "gbuf_closure_img (surf_deferred)"},
    {wgpu::TextureFormat::RG16Unorm,    "UNORM_16_16",      "gbuf_normal_img (surf_deferred)"},
    {wgpu::TextureFormat::R32Uint,      "UINT_32",          "gbuf_header_img (surf_deferred)"},
    {wgpu::TextureFormat::R16Float,     "SFLOAT_16",        "value passes / DoF"},
    {wgpu::TextureFormat::RG16Float,    "SFLOAT_16_16",     "ray_time / misc"},
    {wgpu::TextureFormat::RG11B10Ufloat,"UFLOAT_11_11_10",  "volume props"},
};
const std::vector<FmtRow> kRWFmts = {
    {wgpu::TextureFormat::R32Float,     "SFLOAT_32",         "film depth_img (RW)"},
    {wgpu::TextureFormat::RGBA16Float,  "SFLOAT_16_16_16_16","film out_combined_img (RW)"},
    {wgpu::TextureFormat::RG16Unorm,    "UNORM_16_16",       "deferred_thickness_amend gbuf_normal (RW)"},
};

int RunMatrix(const wgpu::Instance& instance, const wgpu::Device& device, const char* label) {
  std::cout << "\n================ DEVICE: " << label << " ================\n";
  if (device == nullptr) { std::cout << "  (device creation FAILED)\n"; return -1; }

  std::string err;
  int frag_ok = 0, frag_total = 0;
  int vert_rejected = 0, vert_total = 0;

  std::cout << "-- WriteOnly storage textures --\n";
  for (const FmtRow& r : kWriteFmts) {
    bool f = TryStorageTexBGL(instance, device, r.fmt, wgpu::StorageTextureAccess::WriteOnly,
                              wgpu::ShaderStage::Fragment, err);
    bool vf = TryStorageTexBGL(instance, device, r.fmt, wgpu::StorageTextureAccess::WriteOnly,
                               wgpu::ShaderStage::Vertex | wgpu::ShaderStage::Fragment, err);
    frag_total++; vert_total++;
    if (f) frag_ok++;
    if (!vf) vert_rejected++;
    std::cout << "  " << r.blender_fmt << " (" << r.eevee_use << ")\n"
              << "      Fragment-only   : " << (f ? "OK" : "FAIL") << "\n"
              << "      Vertex|Fragment : " << (vf ? "OK" : "FAIL (expected)") << "\n";
  }

  std::cout << "-- ReadWrite storage textures --\n";
  for (const FmtRow& r : kRWFmts) {
    bool f = TryStorageTexBGL(instance, device, r.fmt, wgpu::StorageTextureAccess::ReadWrite,
                              wgpu::ShaderStage::Fragment, err);
    frag_total++;
    if (f) frag_ok++;
    std::cout << "  " << r.blender_fmt << " (" << r.eevee_use << ")\n"
              << "      Fragment-only   : " << (f ? "OK" : "FAIL") << "\n";
  }

  std::cout << "-- storage-texture COUNT in one stage (Compute) --\n";
  for (uint32_t n : {4u, 5u, 8u}) {
    bool ok = TryStorageTexCount(instance, device, n, wgpu::ShaderStage::Compute, err);
    std::cout << "  " << n << " storage textures : " << (ok ? "OK" : "FAIL")
              << (ok ? "" : ("  <- " + err)) << "\n";
  }

  std::cout << "SUMMARY[" << label << "]: Fragment-only accepted "
            << frag_ok << "/" << frag_total << "; Vertex-visible writable rejected "
            << vert_rejected << "/" << vert_total << "\n";
  return (frag_ok == frag_total && vert_rejected == vert_total) ? 0 : 1;
}

}  // namespace

int main() {
  wgpu::InstanceDescriptor instance_desc = {};
  static constexpr auto kTimedWaitAny = wgpu::InstanceFeatureName::TimedWaitAny;
  instance_desc.requiredFeatureCount = 1;
  instance_desc.requiredFeatures = &kTimedWaitAny;
  wgpu::Instance instance = wgpu::CreateInstance(&instance_desc);
  if (instance == nullptr) { std::cerr << "CreateInstance failed\n"; return 4; }

  wgpu::RequestAdapterOptions adapter_opts = {};
  adapter_opts.backendType = wgpu::BackendType::Metal;
  adapter_opts.featureLevel = wgpu::FeatureLevel::Core;
  wgpu::Adapter adapter;
  instance.WaitAny(
      instance.RequestAdapter(
          &adapter_opts, wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestAdapterStatus status, wgpu::Adapter a, wgpu::StringView msg) {
            if (status == wgpu::RequestAdapterStatus::Success) adapter = std::move(a);
            else std::cerr << "RequestAdapter failed: " << ToStr(msg) << "\n";
          }),
      UINT64_MAX);
  if (adapter == nullptr) { std::cerr << "no Metal adapter\n"; return 5; }

  wgpu::AdapterInfo info;
  adapter.GetInfo(&info);
  std::cout << "Dawn adapter: \"" << ToStr(info.device) << "\" backend=Metal\n";

  // Report the storage-relevant feature availability on this adapter.
  auto has = [&](wgpu::FeatureName f) { return adapter.HasFeature(f); };
  std::cout << "Adapter features:\n"
            << "  TextureFormatsTier1     : " << (has(wgpu::FeatureName::TextureFormatsTier1) ? "YES" : "no") << "\n"
            << "  TextureFormatsTier2     : " << (has(wgpu::FeatureName::TextureFormatsTier2) ? "YES" : "no") << "\n"
            << "  Unorm16TextureFormats   : " << (has(wgpu::FeatureName::Unorm16TextureFormats) ? "YES" : "no") << "\n"
            << "  RG11B10UfloatRenderable : " << (has(wgpu::FeatureName::RG11B10UfloatRenderable) ? "YES" : "no") << "\n"
            << "  BGRA8UnormStorage       : " << (has(wgpu::FeatureName::BGRA8UnormStorage) ? "YES" : "no") << "\n";
  wgpu::Limits alim = {};
  adapter.GetLimits(&alim);
  std::cout << "Adapter limits: maxStorageTexturesPerShaderStage=" << alim.maxStorageTexturesPerShaderStage
            << " maxStorageBuffersPerShaderStage=" << alim.maxStorageBuffersPerShaderStage << "\n";

  // Control device: today's GHOST feature set (Unorm16 + RG11B10Renderable), default limits.
  std::vector<wgpu::FeatureName> control_feats;
  if (has(wgpu::FeatureName::Unorm16TextureFormats))
    control_feats.push_back(wgpu::FeatureName::Unorm16TextureFormats);
  if (has(wgpu::FeatureName::RG11B10UfloatRenderable))
    control_feats.push_back(wgpu::FeatureName::RG11B10UfloatRenderable);
  wgpu::Device control = MakeDevice(instance, adapter, control_feats, /*raise_limits=*/false);

  // Proposed device: control + storage-texture format tiers + raised limits.
  // A consumed adapter cannot make a second device, so request a fresh one.
  wgpu::Adapter adapter2 = RequestAdapter(instance);
  std::vector<wgpu::FeatureName> prop_feats = control_feats;
  if (has(wgpu::FeatureName::TextureFormatsTier1))
    prop_feats.push_back(wgpu::FeatureName::TextureFormatsTier1);
  if (has(wgpu::FeatureName::TextureFormatsTier2))
    prop_feats.push_back(wgpu::FeatureName::TextureFormatsTier2);
  wgpu::Device proposed = MakeDevice(instance, adapter2, prop_feats, /*raise_limits=*/true);

  RunMatrix(instance, control, "CONTROL (today's features, default limits)");
  int prop_rc = RunMatrix(instance, proposed, "PROPOSED (+Tier1+Tier2+raised limits)");

  std::cout << "\nProbe verdict: "
            << (prop_rc == 0 ? "PASS (proposed device accepts all EEVEE Fragment-only "
                               "storage entries and still rejects Vertex-visible writable)"
                             : "PARTIAL (see matrix; residual formats need per-case handling)")
            << "\n";
  return prop_rc == 0 ? 0 : 8;
}
