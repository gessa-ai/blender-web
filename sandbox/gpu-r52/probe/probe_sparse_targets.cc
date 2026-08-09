// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r52 - sparse color-target + fragment-output-masking acceptance probe.
//
// The workbench TransparentDepthPass builds framebuffers with GPU_ATTACHMENT_NONE
// gaps, e.g. ensure(depth, NONE, NONE, object_id): object_id (R16Uint) sits at
// COLOR SLOT 2, slots 0/1 empty. WGPUFrameBuffer::target_formats COMPACTS the color
// attachments (colors[color_count++] skips NONE), so R16Uint lands at pipeline
// targets[0] and is validated against the WGSL fragment @location(0) FLOAT output
// (the prepass frag writes material@0 / normal@1 / object_id@2) -> Dawn:
//   "Color format (R16Uint) base type (Uint) doesn't match the fragment module
//    output type (Float). While validating targets[0]."
//
// The candidate faithful fix preserves the SLOTS: targets = [null, null, R16Uint].
// This probe determines, on a real Dawn/Metal device (same generation as the
// emdawnwebgpu M4 browser path), EXACTLY what Dawn accepts, which decides the fix
// shape:
//   Q1  frag writes @loc 0(f32) 1(f32) 2(u32); targets [null,null,R16Uint]
//       -> does Dawn allow fragment outputs whose target slot is null (Vulkan
//          VK_ATTACHMENT_UNUSED semantics), or does it require every output to
//          have a non-null target?  (If allowed: slot-preservation alone is the
//          whole fix. If rejected: need shader variants / output masking.)
//   Q2  frag writes ONLY @loc 2(u32); targets [null,null,R16Uint]
//       -> does Dawn allow a NON-null target with no matching fragment output?
//          (the reverse direction; informs whether a per-variant frag that only
//          writes object_id would validate.)
//   Q3  frag writes @loc 0 1 2; targets [R16Uint] (TODAY's compaction) -> expected
//          FAIL (base-type mismatch) - the control reproducing the live bug.
//   Q4  frag writes @loc 0 1 2; targets [null,null,R16Uint] but with writeMask
//          probing is N/A (null target has no writeMask) - covered by Q1.
//
// Pure Dawn validation via a Validation error scope around CreateRenderPipeline.
// Boilerplate mirrors sandbox/eevee-storage-design/probe_storage_bgl.cc.

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

wgpu::ShaderModule MakeWGSL(const wgpu::Device& device, const char* src) {
  wgpu::ShaderSourceWGSL wgsl = {};
  wgsl.code = src;
  wgpu::ShaderModuleDescriptor d = {};
  d.nextInChain = &wgsl;
  return device.CreateShaderModule(&d);
}

// Build a render pipeline with the given fragment module and a color-target array
// (Undefined format == a null/empty slot). Returns true iff Dawn validates it.
bool TryPipeline(const wgpu::Instance& instance,
                 const wgpu::Device& device,
                 const wgpu::ShaderModule& vs,
                 const wgpu::ShaderModule& fs,
                 const std::vector<wgpu::TextureFormat>& target_formats,
                 std::string& err) {
  device.PushErrorScope(wgpu::ErrorFilter::Validation);

  std::vector<wgpu::ColorTargetState> targets(target_formats.size());
  for (size_t i = 0; i < target_formats.size(); i++) {
    targets[i].format = target_formats[i];      // Undefined == empty slot
    targets[i].blend = nullptr;
    // For an empty (Undefined) slot, writeMask must stay 0 per Dawn; for a real
    // target use All.
    targets[i].writeMask = (target_formats[i] == wgpu::TextureFormat::Undefined)
                               ? wgpu::ColorWriteMask::None
                               : wgpu::ColorWriteMask::All;
  }

  wgpu::FragmentState fragment = {};
  fragment.module = fs;
  fragment.entryPoint = "fs";
  fragment.targetCount = targets.size();
  fragment.targets = targets.data();

  wgpu::RenderPipelineDescriptor desc = {};
  desc.layout = nullptr;  // auto layout; we only care about fragment/target validation
  desc.vertex.module = vs;
  desc.vertex.entryPoint = "vs";
  desc.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
  desc.fragment = &fragment;

  wgpu::RenderPipeline pipe = device.CreateRenderPipeline(&desc);

  bool had_error = false;
  wgpu::Future pop = device.PopErrorScope(
      wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView msg) {
        if (type != wgpu::ErrorType::NoError) { had_error = true; err = ToStr(msg); }
      });
  instance.WaitAny(pop, UINT64_MAX);
  return !had_error && pipe != nullptr;
}

const char* kVS = R"(
@vertex fn vs(@builtin(vertex_index) i : u32) -> @builtin(position) vec4f {
  return vec4f(0.0, 0.0, 0.0, 1.0);
}
)";

// Fragment that writes THREE outputs: 0/1 float (material/normal), 2 uint (object_id).
const char* kFS_012 = R"(
struct FO {
  @location(0) material : vec4f,
  @location(1) normal   : vec4f,
  @location(2) object_id: vec4u,
}
@fragment fn fs() -> FO {
  var o : FO;
  o.material  = vec4f(1.0);
  o.normal    = vec4f(1.0);
  o.object_id = vec4u(1u);
  return o;
}
)";

// Fragment that writes ONLY @location(2) uint.
const char* kFS_2 = R"(
struct FO { @location(2) object_id : vec4u }
@fragment fn fs() -> FO {
  var o : FO;
  o.object_id = vec4u(1u);
  return o;
}
)";

wgpu::Device MakeDevice(const wgpu::Instance& instance, const wgpu::Adapter& adapter) {
  wgpu::DeviceDescriptor desc = {};
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

  wgpu::Device device = MakeDevice(instance, adapter);
  if (device == nullptr) { std::cerr << "no device\n"; return 6; }

  wgpu::ShaderModule vs  = MakeWGSL(device, kVS);
  wgpu::ShaderModule f012 = MakeWGSL(device, kFS_012);
  wgpu::ShaderModule f2   = MakeWGSL(device, kFS_2);

  const auto U = wgpu::TextureFormat::Undefined;
  const auto R16U = wgpu::TextureFormat::R16Uint;
  std::string err;

  std::cout << "\n==== SPARSE COLOR-TARGET / FRAGMENT-OUTPUT-MASKING MATRIX ====\n";

  err.clear();
  bool q1 = TryPipeline(instance, device, vs, f012, {U, U, R16U}, err);
  std::cout << "Q1 frag[0f,1f,2u] targets[null,null,R16Uint]  : " << (q1 ? "OK" : "FAIL")
            << (q1 ? "" : ("  <- " + err)) << "\n";

  err.clear();
  bool q2 = TryPipeline(instance, device, vs, f2, {U, U, R16U}, err);
  std::cout << "Q2 frag[2u only] targets[null,null,R16Uint]   : " << (q2 ? "OK" : "FAIL")
            << (q2 ? "" : ("  <- " + err)) << "\n";

  err.clear();
  bool q3 = TryPipeline(instance, device, vs, f012, {R16U}, err);
  std::cout << "Q3 frag[0f,1f,2u] targets[R16Uint] (compaction): " << (q3 ? "OK" : "FAIL")
            << (q3 ? "" : ("  <- " + err)) << "\n";

  // Q5: a 3-wide all-float MRT with a hole in the MIDDLE, both outputs present at
  // the non-null slots (sanity: gaps are allowed when outputs match the non-null).
  err.clear();
  const auto RGBA = wgpu::TextureFormat::RGBA8Unorm;
  const char* kFS_02f = R"(
struct FO { @location(0) a: vec4f, @location(2) c: vec4f }
@fragment fn fs() -> FO { var o:FO; o.a=vec4f(1.0); o.c=vec4f(1.0); return o; }
)";
  wgpu::ShaderModule f02 = MakeWGSL(device, kFS_02f);
  bool q5 = TryPipeline(instance, device, vs, f02, {RGBA, U, RGBA}, err);
  std::cout << "Q5 frag[0f,2f]   targets[RGBA,null,RGBA]       : " << (q5 ? "OK" : "FAIL")
            << (q5 ? "" : ("  <- " + err)) << "\n";

  // Q6: the RENDER-PASS side (begin_load_pass): encode a real pass with color
  // attachments [null, null, R16Uint], bind the slot-preserving pipeline, draw.
  // This is what WGPUFrameBuffer::begin_load_pass must produce; verify Dawn accepts
  // a null-view color attachment and that the pipeline is compatible with it.
  {
    device.PushErrorScope(wgpu::ErrorFilter::Validation);
    wgpu::RenderPipeline pipe;
    {
      std::vector<wgpu::ColorTargetState> targets(3);
      targets[0].format = U;    targets[0].writeMask = wgpu::ColorWriteMask::None;
      targets[1].format = U;    targets[1].writeMask = wgpu::ColorWriteMask::None;
      targets[2].format = R16U; targets[2].writeMask = wgpu::ColorWriteMask::All;
      wgpu::FragmentState fragment = {};
      fragment.module = f012; fragment.entryPoint = "fs";
      fragment.targetCount = 3; fragment.targets = targets.data();
      wgpu::RenderPipelineDescriptor desc = {};
      desc.vertex.module = vs; desc.vertex.entryPoint = "vs";
      desc.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
      desc.fragment = &fragment;
      pipe = device.CreateRenderPipeline(&desc);
    }
    wgpu::TextureDescriptor td = {};
    td.size = {4, 4, 1};
    td.format = R16U;
    td.usage = wgpu::TextureUsage::RenderAttachment;
    wgpu::Texture oid = device.CreateTexture(&td);

    std::vector<wgpu::RenderPassColorAttachment> cas(3);
    // slots 0,1 = null (view left null, ops Undefined)
    cas[2].view = oid.CreateView();
    cas[2].loadOp = wgpu::LoadOp::Clear;
    cas[2].storeOp = wgpu::StoreOp::Store;
    cas[2].clearValue = {0, 0, 0, 0};
    wgpu::RenderPassDescriptor rp = {};
    rp.colorAttachmentCount = 3;
    rp.colorAttachments = cas.data();

    wgpu::CommandEncoder enc = device.CreateCommandEncoder();
    wgpu::RenderPassEncoder pass = enc.BeginRenderPass(&rp);
    pass.SetPipeline(pipe);
    pass.Draw(3, 1, 0, 0);
    pass.End();
    wgpu::CommandBuffer cb = enc.Finish();
    device.GetQueue().Submit(1, &cb);

    bool had_error = false; std::string e6;
    wgpu::Future pop = device.PopErrorScope(
        wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView msg) {
          if (type != wgpu::ErrorType::NoError) { had_error = true; e6 = ToStr(msg); }
        });
    instance.WaitAny(pop, UINT64_MAX);
    std::cout << "Q6 renderpass ca[null,null,R16Uint]+draw     : " << (had_error ? "FAIL" : "OK")
              << (had_error ? ("  <- " + e6) : "") << "\n";
  }

  std::cout << "\nINTERPRETATION:\n"
            << "  Q1 OK  => slot preservation ALONE fixes the x-ray cluster (Dawn permits\n"
            << "            fragment outputs at null-target slots; matches Vulkan UNUSED).\n"
            << "  Q1 FAIL, Q2 OK => need per-framebuffer fragment variant emitting only the\n"
            << "            present outputs (shader-level, out of the framebuffer/pipeline fence).\n"
            << "  Q3 FAIL is the live bug reproduced (compaction base-type mismatch).\n";
  return 0;
}
