// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M3.T2 — combined-sampler binding audit (blender-web).
//
// Builds on the T1 probe (probe.cc, still the `dawn_probe` target). Takes a
// Blender-SHAPED shader pair (shaders/bindmap.{vert,frag} — dense set-0
// bindings, push-constant-emulation UBO last, two combined sampler2Ds, bindings
// shared across stages) and runs the SPIR-V->WGSL chain THREE ways to produce
// the normative binding-map spec for wgpu_shader_interface (T7):
//
//   Mode A: default Tint (empty sampler_mappings). SplitCombinedImageSamplerPass
//           copies the combined binding to BOTH the texture and sampler halves,
//           then ResolveBindingConflictsPass renumbers to make them unique —
//           which BUMPS unrelated resources. We dump the result to document the
//           collisions exactly.
//   Mode B: steer each split-out sampler to a reserved binding via
//           spirv::reader::Options::sampler_mappings ({0,N} -> {0, 256+N}).
//           With mappings non-empty, ResolveBindingConflictsPass is skipped, so
//           every non-sampler resource keeps Blender's binding. Deterministic.
//   Mode C: create a real wgpuRenderPipeline from the Mode-B vertex+fragment
//           modules with ONE explicit bind-group layout (group 0) matching the
//           spec. Pipeline creation success == the layouts truly compose across
//           stages (the strongest cheap validation).
//
// Exit 0 iff all modules validate clean AND the render pipeline is created with
// no validation error.

#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>

#include "webgpu/webgpu_cpp.h"

#include "probe_platform.hh"

#include "src/tint/api/common/binding_point.h"
#include "src/tint/lang/core/ir/module.h"
#include "src/tint/lang/spirv/reader/reader.h"
#include "src/tint/lang/wgsl/program/program.h"
#include "src/tint/lang/wgsl/writer/writer.h"

namespace {

// Reserved binding base for split-out samplers (Mode B). Chosen so it sits well
// above any realistic Blender set-0 resource binding count (per-stage device
// limits cap total set-0 bindings well under 128) yet stays below WebGPU's
// maxBindingsPerBindGroup = 1000 (Dawn Limits.cpp; same in emdawnwebgpu). So a
// combined sampler at Blender binding N -> texture stays at N, sampler goes to
// kSamplerBindingBase + N, collision-free against the dense [0,128) resources.
constexpr uint32_t kSamplerBindingBase = 256u;

std::string ToStr(wgpu::StringView s) {
  if (s.data == nullptr) return {};
  if (s.length == WGPU_STRLEN) return std::string(s.data);
  return std::string(s.data, s.length);
}

std::vector<uint32_t> LoadSpirv(const char* path) {
  std::ifstream f(path, std::ios::binary | std::ios::ate);
  if (!f) {
    std::cerr << "ERROR: cannot open " << path << "\n";
    return {};
  }
  const std::streamsize bytes = f.tellg();
  if (bytes <= 0 || (bytes % 4) != 0) {
    std::cerr << "ERROR: not a SPIR-V word stream: " << path << "\n";
    return {};
  }
  f.seekg(0);
  std::vector<uint32_t> words(static_cast<size_t>(bytes) / 4);
  f.read(reinterpret_cast<char*>(words.data()), bytes);
  return words;
}

using SamplerMap = std::unordered_map<tint::BindingPoint, tint::BindingPoint>;

// SPIR-V -> WGSL with an optional sampler-remap table.
bool Translate(const std::vector<uint32_t>& spirv, const SamplerMap& mappings,
               std::string& out_wgsl) {
  tint::spirv::reader::Options reader_opts;
  reader_opts.sampler_mappings = mappings;
  auto ir = tint::spirv::reader::ReadIR(spirv, reader_opts);
  if (ir != tint::Success) {
    std::cerr << "ReadIR failed:\n" << ir.Failure() << "\n";
    return false;
  }
  tint::wgsl::writer::Options writer_opts;
  auto prog = tint::wgsl::writer::ProgramFromIR(ir.Get(), writer_opts);
  if (prog != tint::Success) {
    std::cerr << "ProgramFromIR failed:\n" << prog.Failure() << "\n";
    return false;
  }
  tint::Program program = prog.Move();
  auto gen = tint::wgsl::writer::Generate(program, writer_opts);
  if (gen != tint::Success) {
    std::cerr << "Generate failed:\n" << gen.Failure() << "\n";
    return false;
  }
  out_wgsl = gen.Get().wgsl;
  return true;
}

// Print just the resource-declaration lines (those carrying @group/@binding).
void PrintBindings(const std::string& label, const std::string& wgsl) {
  std::cout << "--- " << label << " resource bindings ---\n";
  size_t pos = 0;
  while (pos < wgsl.size()) {
    size_t eol = wgsl.find('\n', pos);
    if (eol == std::string::npos) eol = wgsl.size();
    std::string line = wgsl.substr(pos, eol - pos);
    if (line.find("@group(") != std::string::npos) {
      std::cout << "    " << line << "\n";
    }
    pos = eol + 1;
  }
}

wgpu::ShaderModule MakeModule(const wgpu::Device& device, const std::string& wgsl,
                              const char* label) {
  wgpu::ShaderSourceWGSL src;
  src.code = wgsl.c_str();
  wgpu::ShaderModuleDescriptor desc;
  desc.nextInChain = &src;
  desc.label = label;
  return device.CreateShaderModule(&desc);
}

// Pop the current validation error scope; true == clean.
bool PopOk(const wgpu::Instance& inst, const wgpu::Device& dev, const char* what) {
  bool had_error = false;
  std::string msg;
  wgpu::Future f = dev.PopErrorScope(
      wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView m) {
        if (type != wgpu::ErrorType::NoError) {
          had_error = true;
          msg = ToStr(m);
        }
      });
  inst.WaitAny(f, UINT64_MAX);
  if (had_error) {
    std::cerr << "[" << what << "] VALIDATION ERROR: " << msg << "\n";
    return false;
  }
  std::cout << "[" << what << "] OK\n";
  return true;
}

}  // namespace

int main(int argc, char** argv) {
  const char* vert_path = argc > 1 ? argv[1] : "bindmap.vert.spv";
  const char* frag_path = argc > 2 ? argv[2] : "bindmap.frag.spv";

  std::vector<uint32_t> vert_spv = LoadSpirv(vert_path);
  std::vector<uint32_t> frag_spv = LoadSpirv(frag_path);
  if (vert_spv.empty() || frag_spv.empty()) return 2;

  // ---- Mode A: default Tint (empty sampler_mappings) -----------------------
  std::cout << "================ MODE A: default Tint (empty sampler_mappings)"
               " ================\n";
  std::string a_vert, a_frag;
  if (!Translate(vert_spv, {}, a_vert) || !Translate(frag_spv, {}, a_frag)) {
    std::cerr << "Mode A translate FAIL\n";
    return 3;
  }
  PrintBindings("A/vertex", a_vert);
  PrintBindings("A/fragment", a_frag);

  // ---- Mode B: reserved-range sampler_mappings -----------------------------
  // color_tex is the combined sampler at Blender binding 1, normal_tex at 2.
  SamplerMap mappings;
  mappings[tint::BindingPoint{0u, 1u}] = tint::BindingPoint{0u, kSamplerBindingBase + 1u};
  mappings[tint::BindingPoint{0u, 2u}] = tint::BindingPoint{0u, kSamplerBindingBase + 2u};

  std::cout << "\n================ MODE B: sampler_mappings {0,1}->{0," << (kSamplerBindingBase + 1)
            << "}, {0,2}->{0," << (kSamplerBindingBase + 2) << "} ================\n";
  std::string b_vert, b_frag;
  if (!Translate(vert_spv, mappings, b_vert) || !Translate(frag_spv, mappings, b_frag)) {
    std::cerr << "Mode B translate FAIL\n";
    return 3;
  }
  PrintBindings("B/vertex", b_vert);
  PrintBindings("B/fragment", b_frag);

  // ---- Dawn device (headless host backend) ---------------------------------
  wgpu::InstanceDescriptor idesc = {};
  static constexpr auto kTimedWaitAny = wgpu::InstanceFeatureName::TimedWaitAny;
  idesc.requiredFeatureCount = 1;
  idesc.requiredFeatures = &kTimedWaitAny;
  wgpu::Instance instance = wgpu::CreateInstance(&idesc);
  if (instance == nullptr) { std::cerr << "CreateInstance failed\n"; return 4; }

  wgpu::RequestAdapterOptions aopts = {};
  aopts.backendType = blender_web::dawn_probe::kBackendType;
  aopts.featureLevel = wgpu::FeatureLevel::Core;
  wgpu::Adapter adapter;
  instance.WaitAny(instance.RequestAdapter(
                       &aopts, wgpu::CallbackMode::WaitAnyOnly,
                       [&](wgpu::RequestAdapterStatus s, wgpu::Adapter a, wgpu::StringView m) {
                         if (s != wgpu::RequestAdapterStatus::Success) {
                           std::cerr << "adapter: " << ToStr(m) << "\n";
                           return;
                         }
                         adapter = std::move(a);
                       }),
                   UINT64_MAX);
  if (adapter == nullptr) { std::cerr << "no adapter\n"; return 5; }

  wgpu::AdapterInfo info;
  adapter.GetInfo(&info);
  std::cout << "\nDawn adapter: \"" << ToStr(info.device) << "\" backend="
            << blender_web::dawn_probe::kBackendName
            << " adapter_type=" << static_cast<int>(info.adapterType) << "\n";
  if (!blender_web::dawn_probe::is_hardware_adapter(info)) {
    std::cerr << "PROBE_BLOCKED: refusing non-hardware "
              << blender_web::dawn_probe::kBackendName << " adapter \"" << ToStr(info.device)
              << "\"\n";
    return 5;
  }

  wgpu::DeviceDescriptor ddesc = {};
  ddesc.SetUncapturedErrorCallback(
      [](const wgpu::Device&, wgpu::ErrorType t, wgpu::StringView m) {
        std::cerr << "UNCAPTURED (" << static_cast<int>(t) << "): " << ToStr(m) << "\n";
      });
  wgpu::Device device;
  instance.WaitAny(adapter.RequestDevice(
                       &ddesc, wgpu::CallbackMode::WaitAnyOnly,
                       [&](wgpu::RequestDeviceStatus s, wgpu::Device d, wgpu::StringView m) {
                         if (s != wgpu::RequestDeviceStatus::Success) {
                           std::cerr << "device: " << ToStr(m) << "\n";
                           return;
                         }
                         device = std::move(d);
                       }),
                   UINT64_MAX);
  if (device == nullptr) { std::cerr << "no device\n"; return 6; }

  // ---- Validate the four modules -------------------------------------------
  std::cout << "\n================ module validation ================\n";
  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::ShaderModule a_vmod = MakeModule(device, a_vert, "A_vert");
  bool ok = PopOk(instance, device, "A/vertex module");
  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::ShaderModule a_fmod = MakeModule(device, a_frag, "A_frag");
  ok = PopOk(instance, device, "A/fragment module") && ok;
  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::ShaderModule b_vmod = MakeModule(device, b_vert, "B_vert");
  ok = PopOk(instance, device, "B/vertex module") && ok;
  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::ShaderModule b_fmod = MakeModule(device, b_frag, "B_frag");
  ok = PopOk(instance, device, "B/fragment module") && ok;
  if (!ok) { std::cerr << "\nmodule validation FAILED\n"; return 7; }

  // ---- Mode C: real render pipeline from the Mode-B modules -----------------
  // ONE bind-group layout (group 0) mirroring Blender's single descriptor set,
  // with the split samplers at the reserved bindings. Visibilities encode which
  // stage(s) use each binding (0 and 5 are shared).
  std::cout << "\n================ MODE C: render pipeline (explicit BGL) ================\n";
  auto uniform = [](uint32_t binding, wgpu::ShaderStage vis) {
    wgpu::BindGroupLayoutEntry e = {};
    e.binding = binding;
    e.visibility = vis;
    e.buffer.type = wgpu::BufferBindingType::Uniform;
    return e;
  };
  auto ssbo_ro = [](uint32_t binding, wgpu::ShaderStage vis) {
    wgpu::BindGroupLayoutEntry e = {};
    e.binding = binding;
    e.visibility = vis;
    e.buffer.type = wgpu::BufferBindingType::ReadOnlyStorage;
    return e;
  };
  auto tex2d = [](uint32_t binding, wgpu::ShaderStage vis) {
    wgpu::BindGroupLayoutEntry e = {};
    e.binding = binding;
    e.visibility = vis;
    e.texture.sampleType = wgpu::TextureSampleType::Float;
    e.texture.viewDimension = wgpu::TextureViewDimension::e2D;
    return e;
  };
  auto samp = [](uint32_t binding, wgpu::ShaderStage vis) {
    wgpu::BindGroupLayoutEntry e = {};
    e.binding = binding;
    e.visibility = vis;
    e.sampler.type = wgpu::SamplerBindingType::Filtering;
    return e;
  };
  const auto VF = wgpu::ShaderStage::Vertex | wgpu::ShaderStage::Fragment;
  const auto F = wgpu::ShaderStage::Fragment;
  std::vector<wgpu::BindGroupLayoutEntry> entries = {
      uniform(0, VF),                       // Globals (shared)
      tex2d(1, F),                          // color_tex (texture half)
      tex2d(2, F),                          // normal_tex (texture half)
      uniform(3, F),                        // Material
      ssbo_ro(4, F),                        // LightData
      uniform(5, VF),                       // Constants / push-const UBO (shared)
      samp(kSamplerBindingBase + 1, F),     // color_tex (sampler half)
      samp(kSamplerBindingBase + 2, F),     // normal_tex (sampler half)
  };
  wgpu::BindGroupLayoutDescriptor bgld = {};
  bgld.entryCount = entries.size();
  bgld.entries = entries.data();
  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::BindGroupLayout bgl = device.CreateBindGroupLayout(&bgld);
  bool cok = PopOk(instance, device, "bind group layout");

  wgpu::PipelineLayoutDescriptor pld = {};
  pld.bindGroupLayoutCount = 1;
  pld.bindGroupLayouts = &bgl;
  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::PipelineLayout playout = device.CreatePipelineLayout(&pld);
  cok = PopOk(instance, device, "pipeline layout") && cok;

  // Vertex buffer: interleaved pos(vec3)+uv(vec2)+nor(vec3), stride 32.
  std::vector<wgpu::VertexAttribute> attrs = {
      {.format = wgpu::VertexFormat::Float32x3, .offset = 0, .shaderLocation = 0},
      {.format = wgpu::VertexFormat::Float32x2, .offset = 12, .shaderLocation = 1},
      {.format = wgpu::VertexFormat::Float32x3, .offset = 20, .shaderLocation = 2},
  };
  wgpu::VertexBufferLayout vbl = {};
  vbl.arrayStride = 32;
  vbl.stepMode = wgpu::VertexStepMode::Vertex;
  vbl.attributeCount = attrs.size();
  vbl.attributes = attrs.data();

  wgpu::ColorTargetState color = {};
  color.format = wgpu::TextureFormat::RGBA8Unorm;
  color.writeMask = wgpu::ColorWriteMask::All;

  // Build one render pipeline against the Blender-shaped bind-group layout above.
  // Returns true iff CreateRenderPipeline validates clean.
  auto try_pipeline = [&](const wgpu::ShaderModule& vmod, const wgpu::ShaderModule& fmod,
                          const char* label) -> bool {
    wgpu::FragmentState fs = {};
    fs.module = fmod;
    fs.entryPoint = "main";
    fs.targetCount = 1;
    fs.targets = &color;
    wgpu::RenderPipelineDescriptor rp = {};
    rp.layout = playout;
    rp.vertex.module = vmod;
    rp.vertex.entryPoint = "main";
    rp.vertex.bufferCount = 1;
    rp.vertex.buffers = &vbl;
    rp.fragment = &fs;
    rp.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
    rp.multisample.count = 1;
    device.PushErrorScope(wgpu::ErrorFilter::Validation);
    wgpu::RenderPipeline pipeline = device.CreateRenderPipeline(&rp);
    return PopOk(instance, device, label) && pipeline != nullptr;
  };

  // C1 (negative control): the DEFAULT-Tint modules against Blender's intended
  // layout MUST be rejected — Mode A renumbered fragment resources to bindings
  // (6, 7) that don't exist in this layout, and moved the shared `constants`
  // binding out of sync with the vertex stage. Rejection here is the PASS.
  const bool a_rejected = !try_pipeline(a_vmod, a_fmod, "C1 default-Tint pipeline (expect REJECT)");
  std::cout << (a_rejected ? "    -> correctly REJECTED (default Tint incompatible with the layout)\n"
                           : "    -> UNEXPECTEDLY accepted (would be a silent mis-bind!)\n");

  // C2: the sampler_mapping'd modules MUST compose with the same layout.
  const bool b_ok = try_pipeline(b_vmod, b_fmod, "C2 mapped pipeline (expect PASS)");

  if (cok && a_rejected && b_ok) {
    std::cout << "\nBINDMAP PROBE PASS: default Tint diverges across stages and is "
                 "rejected by Blender's single-set layout; the sampler_mappings "
                 "spec composes into a valid render pipeline.\n";
    return 0;
  }
  std::cerr << "\nBINDMAP PROBE FAIL (bgl/layout=" << cok << " a_rejected=" << a_rejected
            << " b_ok=" << b_ok << ")\n";
  return 8;
}
