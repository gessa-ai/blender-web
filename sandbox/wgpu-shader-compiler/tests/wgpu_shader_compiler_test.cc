/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.T7.pre compiler/interface contract plus end-to-end harness. The
 * device-free mode proves the complete translation and binding semantics on
 * every host; live mode additionally drives the generated modules/layouts
 * through an accepted native Dawn Metal or Vulkan device:
 *
 *   for each realistic create-info-shaped shader:
 *     GLSL --module--> WGSL + BGL entries  (shaderc 1.3 -> Tint -> spec map)
 *     build the ONE group-0 bind-group layout from the returned entries
 *     create a real render/compute pipeline -> the layouts must compose
 *
 * Positive cases (bindmap, types, compute) MUST create their pipeline; the
 * negative control (default-Tint / empty sampler_mappings) MUST be rejected by
 * the correct layout. The sampler-array case is a CHARACTERIZATION probe
 * (open-question-1) and is reported, not gated. Exit 0 iff every gated case
 * meets its expectation. */

#include <cstdint>
#include <initializer_list>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include "webgpu/webgpu_cpp.h"
#include <shaderc/shaderc.h>  // shaderc_{vertex,fragment}_shader kinds for the low-level calls

#include "wgpu_shader_compiler.hh"
#include "wgpu_shader_interface_map.hh"
#include "probe_platform.hh"
#include "tests/test_shaders.hh"

namespace bw = blender::gpu::webgpu;
namespace sh = blender::gpu::webgpu::test_shaders;

namespace {

std::string ToStr(wgpu::StringView s) {
  if (s.data == nullptr) return {};
  if (s.length == WGPU_STRLEN) return std::string(s.data);
  return std::string(s.data, s.length);
}

/* ---- Live Dawn device (headless host backend, mirrors dawn-probe) ---------- */

struct Dawn {
  wgpu::Instance instance;
  wgpu::Adapter adapter;
  wgpu::Device device;

  int init() {
    wgpu::InstanceDescriptor idesc = {};
    static constexpr auto kTimedWaitAny = wgpu::InstanceFeatureName::TimedWaitAny;
    idesc.requiredFeatureCount = 1;
    idesc.requiredFeatures = &kTimedWaitAny;
    instance = wgpu::CreateInstance(&idesc);
    if (instance == nullptr) {
      std::cerr << "CreateInstance failed\n";
      return 4;
    }

    wgpu::RequestAdapterOptions aopts = {};
    aopts.backendType = blender_web::dawn_probe::kBackendType;
    aopts.featureLevel = wgpu::FeatureLevel::Core;
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
    if (adapter == nullptr) {
      std::cerr << "no adapter\n";
      return 5;
    }

    wgpu::AdapterInfo info;
    adapter.GetInfo(&info);
    std::cout << "Dawn adapter: \"" << ToStr(info.device) << "\" backend="
              << blender_web::dawn_probe::kBackendName
              << " adapter_type=" << static_cast<int>(info.adapterType) << "\n\n";
    if (!blender_web::dawn_probe::is_hardware_adapter(info)) {
      std::cerr << "PROBE_BLOCKED: refusing non-hardware "
                << blender_web::dawn_probe::kBackendName << " adapter \""
                << ToStr(info.device) << "\"\n";
      return 5;
    }

    wgpu::DeviceDescriptor ddesc = {};
    ddesc.SetUncapturedErrorCallback(
        [](const wgpu::Device&, wgpu::ErrorType t, wgpu::StringView m) {
          std::cerr << "UNCAPTURED (" << static_cast<int>(t) << "): " << ToStr(m) << "\n";
        });
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
    if (device == nullptr) {
      std::cerr << "no device\n";
      return 6;
    }
    return 0;
  }

  /* Pop the current validation error scope; returns whether it was clean. */
  bool pop_ok(const char* what, bool verbose = true) {
    bool had_error = false;
    std::string msg;
    wgpu::Future f = device.PopErrorScope(
        wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView m) {
          if (type != wgpu::ErrorType::NoError) { had_error = true; msg = ToStr(m); }
        });
    instance.WaitAny(f, UINT64_MAX);
    if (had_error) {
      if (verbose) std::cerr << "    [" << what << "] VALIDATION ERROR: " << msg << "\n";
      return false;
    }
    return true;
  }

  wgpu::ShaderModule make_module(const std::string& wgsl, const char* label) {
    wgpu::ShaderSourceWGSL src;
    src.code = wgsl.c_str();
    wgpu::ShaderModuleDescriptor desc;
    desc.nextInChain = &src;
    desc.label = label;
    return device.CreateShaderModule(&desc);
  }

  wgpu::BindGroupLayout make_bgl(const std::vector<wgpu::BindGroupLayoutEntry>& entries,
                                 bool& ok) {
    wgpu::BindGroupLayoutDescriptor bgld = {};
    bgld.entryCount = entries.size();
    bgld.entries = entries.data();
    device.PushErrorScope(wgpu::ErrorFilter::Validation);
    wgpu::BindGroupLayout bgl = device.CreateBindGroupLayout(&bgld);
    ok = pop_ok("bind group layout");
    return bgl;
  }
};

/* Print just the resource-declaration lines from a WGSL string. */
void print_bindings(const std::string& label, const std::string& wgsl) {
  std::cout << "    --- " << label << " ---\n";
  size_t pos = 0;
  while (pos < wgsl.size()) {
    size_t eol = wgsl.find('\n', pos);
    if (eol == std::string::npos) eol = wgsl.size();
    std::string line = wgsl.substr(pos, eol - pos);
    if (line.find("@group(") != std::string::npos) std::cout << "        " << line << "\n";
    pos = eol + 1;
  }
}

/* ---- Resource lists (create-info shaped) ---------------------------------- */

std::vector<bw::ResourceDesc> bindmap_resources() {
  using namespace bw;
  return {
      {ResourceKind::UniformBuffer, 0, STAGE_VERTEX | STAGE_FRAGMENT, {}, {}, {}, {}, {}, {}, {},
       "Globals"},
      {ResourceKind::Sampler, 1, STAGE_FRAGMENT, TexelClass::Float, TexDim::e2D, true, 1, {}, {},
       {}, "color_tex"},
      {ResourceKind::Sampler, 2, STAGE_FRAGMENT, TexelClass::Float, TexDim::e2D, true, 1, {}, {},
       {}, "normal_tex"},
      {ResourceKind::UniformBuffer, 3, STAGE_FRAGMENT, {}, {}, {}, {}, {}, {}, {}, "Material"},
      {ResourceKind::StorageBuffer, 4, STAGE_FRAGMENT, {}, {}, {}, 1, true, {}, {}, "LightData"},
      {ResourceKind::UniformBuffer, 5, STAGE_VERTEX | STAGE_FRAGMENT, {}, {}, {}, {}, {}, {}, {},
       "Constants"},
  };
}

std::vector<bw::ResourceDesc> types_resources() {
  using namespace bw;
  return {
      {ResourceKind::UniformBuffer, 0, STAGE_FRAGMENT, {}, {}, {}, {}, {}, {}, {}, "Globals"},
      {ResourceKind::Sampler, 1, STAGE_FRAGMENT, TexelClass::Float, TexDim::e2D, true, 1, {}, {},
       {}, "color_tex"},
      {ResourceKind::Sampler, 2, STAGE_FRAGMENT, TexelClass::Shadow, TexDim::e2D, false, 1, {}, {},
       {}, "shadow_tex"},
      {ResourceKind::Sampler, 3, STAGE_FRAGMENT, TexelClass::Uint, TexDim::e2D, false, 1, {}, {},
       {}, "id_tex"},
  };
}

std::vector<bw::ResourceDesc> compute_resources() {
  using namespace bw;
  return {
      {ResourceKind::UniformBuffer, 0, STAGE_COMPUTE, {}, {}, {}, {}, {}, {}, {}, "Params"},
      {ResourceKind::StorageBuffer, 1, STAGE_COMPUTE, {}, {}, {}, 1, false, {}, {}, "Histogram"},
      {ResourceKind::StorageBuffer, 2, STAGE_COMPUTE, {}, {}, {}, 1, true, {}, {}, "InputVals"},
  };
}

/* ---- Vertex buffer layouts ------------------------------------------------ */

struct Vbl {
  std::vector<wgpu::VertexAttribute> attrs;
  uint64_t stride;
};

Vbl bindmap_vbl() {  // pos(vec3)+uv(vec2)+nor(vec3)
  return {{{.format = wgpu::VertexFormat::Float32x3, .offset = 0, .shaderLocation = 0},
           {.format = wgpu::VertexFormat::Float32x2, .offset = 12, .shaderLocation = 1},
           {.format = wgpu::VertexFormat::Float32x3, .offset = 20, .shaderLocation = 2}},
          32};
}
Vbl simple_vbl() {  // pos(vec3)+uv(vec2)
  return {{{.format = wgpu::VertexFormat::Float32x3, .offset = 0, .shaderLocation = 0},
           {.format = wgpu::VertexFormat::Float32x2, .offset = 12, .shaderLocation = 1}},
          20};
}

/* ---- Pipeline creation ----------------------------------------------------- */

bool try_render_pipeline(Dawn& d, const wgpu::ShaderModule& vmod, const wgpu::ShaderModule& fmod,
                         const wgpu::PipelineLayout& layout, const Vbl& vbl, const char* label,
                         bool verbose = true) {
  wgpu::VertexBufferLayout vb = {};
  vb.arrayStride = vbl.stride;
  vb.stepMode = wgpu::VertexStepMode::Vertex;
  vb.attributeCount = vbl.attrs.size();
  vb.attributes = vbl.attrs.data();

  wgpu::ColorTargetState color = {};
  color.format = wgpu::TextureFormat::RGBA8Unorm;
  color.writeMask = wgpu::ColorWriteMask::All;

  wgpu::FragmentState fs = {};
  fs.module = fmod;
  fs.entryPoint = "main";
  fs.targetCount = 1;
  fs.targets = &color;

  wgpu::RenderPipelineDescriptor rp = {};
  rp.layout = layout;
  rp.vertex.module = vmod;
  rp.vertex.entryPoint = "main";
  rp.vertex.bufferCount = 1;
  rp.vertex.buffers = &vb;
  rp.fragment = &fs;
  rp.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
  rp.multisample.count = 1;

  d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::RenderPipeline pipeline = d.device.CreateRenderPipeline(&rp);
  return d.pop_ok(label, verbose) && pipeline != nullptr;
}

bool try_compute_pipeline(Dawn& d, const wgpu::ShaderModule& cmod,
                          const wgpu::PipelineLayout& layout, const char* label) {
  wgpu::ComputePipelineDescriptor cpd = {};
  cpd.layout = layout;
  cpd.compute.module = cmod;
  cpd.compute.entryPoint = "main";
  d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::ComputePipeline cp = d.device.CreateComputePipeline(&cpd);
  return d.pop_ok(label, true) && cp != nullptr;
}

wgpu::PipelineLayout make_layout(Dawn& d, const wgpu::BindGroupLayout& bgl, bool& ok) {
  wgpu::PipelineLayoutDescriptor pld = {};
  pld.bindGroupLayoutCount = 1;
  pld.bindGroupLayouts = &bgl;
  d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::PipelineLayout pl = d.device.CreatePipelineLayout(&pld);
  ok = d.pop_ok("pipeline layout");
  return pl;
}

/* Summarise the interface map (binding numbers) for the report. */
void print_map(const bw::InterfaceMap& m) {
  std::cout << "    interface: SAMPLER_BASE=" << m.sampler_base << ", " << m.entries.size()
            << " BGL entries, " << m.sampler_mappings.size() << " sampler_mappings";
  if (!m.sampler_mappings.empty()) {
    std::cout << " {";
    for (size_t i = 0; i < m.sampler_mappings.size(); i++) {
      const auto& r = m.sampler_mappings[i];
      std::cout << (i ? ", " : "") << "(" << r.from.group << "," << r.from.binding << ")->("
                << r.to.group << "," << r.to.binding << ")";
    }
    std::cout << "}";
  }
  std::cout << "\n";
}

/* ---- Device-free compiler/interface contract ----------------------------- */

bool has_all(const std::string& text, std::initializer_list<const char*> needles) {
  for (const char* needle : needles) {
    if (text.find(needle) == std::string::npos) return false;
  }
  return true;
}

bool has_bindings(const bw::InterfaceMap& map, std::initializer_list<uint32_t> bindings) {
  if (map.entries.size() != bindings.size()) return false;
  size_t index = 0;
  for (uint32_t binding : bindings) {
    if (map.entries[index++].binding != binding) return false;
  }
  return true;
}

bool has_remaps(const bw::InterfaceMap& map,
                std::initializer_list<std::pair<uint32_t, uint32_t>> remaps) {
  if (map.sampler_mappings.size() != remaps.size()) return false;
  size_t index = 0;
  for (const auto& [from, to] : remaps) {
    const bw::SamplerRemap& actual = map.sampler_mappings[index++];
    if (actual.from.group != 0 || actual.to.group != 0 || actual.from.binding != from ||
        actual.to.binding != to) {
      return false;
    }
  }
  return true;
}

bool run_compile_only_contracts() {
  int passed = 0;
  int total = 0;
  auto gate = [&](const char* name, bool ok) {
    total++;
    if (ok) {
      passed++;
      std::cout << "COMPILE_ONLY " << name << " PASS\n";
    }
    else {
      std::cerr << "COMPILE_ONLY " << name << " FAIL\n";
    }
  };

  bw::ShaderStageSources bind_sources;
  bind_sources.vertex = sh::kBindmapVert;
  bind_sources.fragment = sh::kBindmapFrag;
  bind_sources.name = "bindmap";
  const bw::CompileResult bind = bw::compile_shader(bind_sources, bindmap_resources());
  gate("bindmap",
       bind.ok && bind.interface.sampler_base == bw::kSamplerBindingBaseFixed &&
           has_bindings(bind.interface, {0, 1, 257, 2, 258, 3, 4, 5}) &&
           has_remaps(bind.interface, {{1, 257}, {2, 258}}) &&
           has_all(bind.vertex_wgsl, {"@binding(0u)", "@binding(5u)"}) &&
           has_all(bind.fragment_wgsl,
                   {"@binding(0u)", "@binding(1u)", "@binding(257u)",
                    "@binding(2u)", "@binding(258u)", "@binding(3u)",
                    "@binding(4u)", "@binding(5u)"}));

  bw::ShaderStageSources type_sources;
  type_sources.vertex = sh::kSimpleVert;
  type_sources.fragment = sh::kTypesFrag;
  type_sources.name = "types";
  const bw::CompileResult types = bw::compile_shader(type_sources, types_resources());
  gate("types",
       types.ok && has_bindings(types.interface, {0, 1, 257, 2, 258, 3, 259}) &&
           has_remaps(types.interface, {{1, 257}, {2, 258}, {3, 259}}) &&
           has_all(types.fragment_wgsl,
                   {"texture_2d<f32>", "texture_depth_2d", "sampler_comparison",
                    "texture_2d<u32>", "@binding(257u)", "@binding(258u)",
                    "@binding(259u)"}));

  bw::ShaderStageSources compute_sources;
  compute_sources.compute = sh::kComputeAtomic;
  compute_sources.name = "compute_ssbo_atomic";
  const bw::CompileResult compute = bw::compile_shader(compute_sources, compute_resources());
  gate("compute_ssbo_atomic",
       compute.ok && has_bindings(compute.interface, {0, 1, 2}) &&
           compute.interface.sampler_mappings.empty() &&
           has_all(compute.compute_wgsl,
                   {"atomic<u32>", "var<storage, read_write>", "var<storage, read>"}));

  std::string error;
  const std::vector<uint32_t> default_spirv = bw::compile_glsl_to_spirv(
      sh::kBindmapFrag, shaderc_fragment_shader, "default_tint", false, error);
  std::string default_wgsl;
  const bool default_translated = !default_spirv.empty() &&
                                  bw::translate_spirv_to_wgsl(default_spirv, {}, default_wgsl, error);
  gate("default_tint_negative",
       default_translated && default_wgsl != bind.fragment_wgsl &&
           has_all(default_wgsl, {"@binding(6u)", "@binding(7u)"}) &&
           default_wgsl.find("@binding(257u)") == std::string::npos);

  const std::vector<uint32_t> array_spirv = bw::compile_glsl_to_spirv(
      sh::kSamplerArrayFrag, shaderc_fragment_shader, "sampler_array", false, error);
  const bw::InterfaceMap array_map = bw::build_interface_map(
      {{bw::ResourceKind::Sampler, 0, bw::STAGE_FRAGMENT, bw::TexelClass::Float,
        bw::TexDim::e2D, true, 4, {}, {}, {}, "tex"}});
  auto array_rejects = [&](const std::vector<bw::SamplerRemap>& remaps) {
    std::string wgsl;
    std::string array_error;
    return !bw::translate_spirv_to_wgsl(array_spirv, remaps, wgsl, array_error) &&
           array_error.find("arrays of handle types are not supported") != std::string::npos;
  };
  gate("sampler_array_rejection",
       !array_spirv.empty() && has_bindings(array_map, {0, 256, 1, 257, 2, 258, 3, 259}) &&
           has_remaps(array_map, {{0, 256}, {1, 257}, {2, 258}, {3, 259}}) &&
           array_rejects(array_map.sampler_mappings) &&
           array_rejects({{{0, 0}, {0, 256}}}) && array_rejects({}));

  const bw::InterfaceMap colliding_base = bw::build_interface_map(bindmap_resources(), 5);
  const bw::InterfaceMap limit_overflow = bw::build_interface_map(
      {{bw::ResourceKind::Sampler, 100, bw::STAGE_FRAGMENT, bw::TexelClass::Float,
        bw::TexDim::e2D, true, 1, {}, {}, {}, "limit"}},
      900);
  gate("interface_boundaries",
       !colliding_base.ok && !limit_overflow.ok &&
           bw::infer_sample_type(bw::TexelClass::Shadow, false) ==
               wgpu::TextureSampleType::Depth &&
           bw::infer_sampler_type(bw::TexelClass::Shadow, false) ==
               wgpu::SamplerBindingType::Comparison &&
           bw::infer_sampler_type(bw::TexelClass::Uint, true) ==
               wgpu::SamplerBindingType::NonFiltering &&
           bw::infer_view_dimension(bw::TexDim::CubeArray) ==
               wgpu::TextureViewDimension::CubeArray);

  if (passed == total && total == 6) {
    std::cout << "T7.PRE COMPILE_ONLY PASS: 6/6 contracts\n";
    return true;
  }
  std::cerr << "T7.PRE COMPILE_ONLY FAIL: " << passed << "/" << total << " contracts\n";
  return false;
}

/* ---- Cases ---------------------------------------------------------------- */

bool run_graphics_case(Dawn& d, const char* name, const char* vert, const char* frag,
                       const std::vector<bw::ResourceDesc>& resources, const Vbl& vbl) {
  std::cout << "==== CASE " << name << " (render) ====\n";
  bw::ShaderStageSources src;
  src.vertex = vert;
  src.fragment = frag;
  src.name = name;
  bw::CompileResult r = bw::compile_shader(src, resources);
  if (!r.ok) { std::cerr << "    compile FAIL: " << r.error << "\n"; return false; }
  print_map(r.interface);
  print_bindings("vertex WGSL", r.vertex_wgsl);
  print_bindings("fragment WGSL", r.fragment_wgsl);

  bool ok = true;
  wgpu::BindGroupLayout bgl = d.make_bgl(r.interface.entries, ok);
  if (!ok) return false;
  wgpu::PipelineLayout layout = make_layout(d, bgl, ok);
  if (!ok) return false;

  wgpu::ShaderModule vmod = d.make_module(r.vertex_wgsl, "vert");
  wgpu::ShaderModule fmod = d.make_module(r.fragment_wgsl, "frag");
  bool pipe = try_render_pipeline(d, vmod, fmod, layout, vbl, "render pipeline");
  std::cout << (pipe ? "    -> PASS: pipeline created\n\n" : "    -> FAIL\n\n");
  return pipe;
}

bool run_compute_case(Dawn& d) {
  std::cout << "==== CASE compute_ssbo_atomic (compute) ====\n";
  bw::ShaderStageSources src;
  src.compute = sh::kComputeAtomic;
  src.name = "compute_ssbo_atomic";
  bw::CompileResult r = bw::compile_shader(src, compute_resources());
  if (!r.ok) { std::cerr << "    compile FAIL: " << r.error << "\n"; return false; }
  print_map(r.interface);
  print_bindings("compute WGSL", r.compute_wgsl);
  /* Confirm the atomics survived the round-trip. */
  const bool has_atomic = r.compute_wgsl.find("atomic") != std::string::npos;
  std::cout << "    WGSL contains atomic<...>: " << (has_atomic ? "yes" : "NO") << "\n";

  bool ok = true;
  wgpu::BindGroupLayout bgl = d.make_bgl(r.interface.entries, ok);
  if (!ok) return false;
  wgpu::PipelineLayout layout = make_layout(d, bgl, ok);
  if (!ok) return false;
  wgpu::ShaderModule cmod = d.make_module(r.compute_wgsl, "comp");
  bool pipe = try_compute_pipeline(d, cmod, layout, "compute pipeline");
  std::cout << (pipe && has_atomic ? "    -> PASS: compute pipeline created, atomics present\n\n"
                                   : "    -> FAIL\n\n");
  return pipe && has_atomic;
}

/* Negative control: default Tint (empty sampler_mappings) fed to the CORRECT
 * (spec) layout must be REJECTED (mirrors dawn-probe C1). Rejection == PASS. */
bool run_negative_control(Dawn& d) {
  std::cout << "==== CASE negative_control (default-Tint, EXPECT REJECT) ====\n";
  std::string err;
  std::vector<uint32_t> vspv =
      bw::compile_glsl_to_spirv(sh::kBindmapVert, shaderc_vertex_shader, "neg", false, err);
  std::vector<uint32_t> fspv =
      bw::compile_glsl_to_spirv(sh::kBindmapFrag, shaderc_fragment_shader, "neg", false, err);
  if (vspv.empty() || fspv.empty()) { std::cerr << "    shaderc FAIL: " << err << "\n"; return false; }

  std::string a_vert, a_frag;
  if (!bw::translate_spirv_to_wgsl(vspv, {}, a_vert, err) ||
      !bw::translate_spirv_to_wgsl(fspv, {}, a_frag, err)) {
    std::cerr << "    tint FAIL: " << err << "\n";
    return false;
  }
  print_bindings("default-Tint fragment WGSL (renumbered)", a_frag);

  /* Build the CORRECT spec layout and try the default-Tint modules against it. */
  bw::InterfaceMap map = bw::build_interface_map(bindmap_resources());
  bool ok = true;
  wgpu::BindGroupLayout bgl = d.make_bgl(map.entries, ok);
  if (!ok) return false;
  wgpu::PipelineLayout layout = make_layout(d, bgl, ok);
  if (!ok) return false;

  wgpu::ShaderModule vmod = d.make_module(a_vert, "neg_vert");
  wgpu::ShaderModule fmod = d.make_module(a_frag, "neg_frag");
  const bool accepted =
      try_render_pipeline(d, vmod, fmod, layout, bindmap_vbl(), "default-Tint pipeline", false);
  std::cout << (accepted
                    ? "    -> FAIL: UNEXPECTEDLY accepted (silent mis-bind!)\n\n"
                    : "    -> PASS: correctly REJECTED by the spec layout\n\n");
  return !accepted;
}

/* Sampler-array probe (open-question-1). CHARACTERIZATION, not gated. Runs the
 * split three ways and reports what Tint emits + whether it validates. */
void run_sampler_array_probe(Dawn& d) {
  std::cout << "==== PROBE sampler_array: sampler2D tex[4] (open-question-1) ====\n";
  std::string err;
  std::vector<uint32_t> fspv =
      bw::compile_glsl_to_spirv(sh::kSamplerArrayFrag, shaderc_fragment_shader, "arr", false, err);
  if (fspv.empty()) { std::cerr << "    shaderc FAIL: " << err << "\n"; return; }

  auto try_variant = [&](const char* label, const std::vector<bw::SamplerRemap>& maps) {
    std::cout << "  -- variant: " << label << " --\n";
    std::string wgsl;
    if (!bw::translate_spirv_to_wgsl(fspv, maps, wgsl, err)) {
      std::cout << "    tint translate FAILED: " << err << "\n";
      return;
    }
    print_bindings("array-frag WGSL", wgsl);
    const bool binding_array = wgsl.find("binding_array") != std::string::npos;
    std::cout << "    emits binding_array<>: " << (binding_array ? "yes" : "no") << "\n";
    d.device.PushErrorScope(wgpu::ErrorFilter::Validation);
    wgpu::ShaderModule mod = d.make_module(wgsl, "arr_frag");
    const bool mod_ok = d.pop_ok("array module", true);
    std::cout << "    module validates on Dawn: " << (mod_ok ? "yes" : "no") << "\n";
  };

  /* Variant 1: per-element keys (what our interface map currently generates). */
  bw::InterfaceMap per_elem = bw::build_interface_map(
      {{bw::ResourceKind::Sampler, 0, bw::STAGE_FRAGMENT, bw::TexelClass::Float, bw::TexDim::e2D,
        true, 4, {}, {}, {}, "tex"}});
  print_map(per_elem);
  try_variant("per-element keys {0,0..3}->{0,256..259}", per_elem.sampler_mappings);

  /* Variant 2: single base key only. */
  try_variant("single base key {0,0}->{0,256}",
              {{bw::BindPoint{0, 0}, bw::BindPoint{0, 256}}});

  /* Variant 3: default Tint (empty), for reference. */
  try_variant("empty (default Tint)", {});
  std::cout << "  (verdict recorded in notes/gpu-t7pre-findings.md)\n\n";
}

}  // namespace

int main(int argc, char** argv) {
  if (argc == 2 && std::string(argv[1]) == "--compile-only") {
    return run_compile_only_contracts() ? 0 : 1;
  }
  if (argc > 2 || (argc == 2 && std::string(argv[1]) != "--live")) {
    std::cerr << "usage: " << argv[0] << " [--compile-only|--live]\n";
    return 64;
  }

  Dawn d;
  const int init_result = d.init();
  if (init_result != 0) return init_result;

  int passed = 0, total = 0;
  auto gate = [&](bool ok) { total++; if (ok) passed++; };

  gate(run_graphics_case(d, "bindmap", sh::kBindmapVert, sh::kBindmapFrag, bindmap_resources(),
                         bindmap_vbl()));
  gate(run_graphics_case(d, "types", sh::kSimpleVert, sh::kTypesFrag, types_resources(),
                         simple_vbl()));
  gate(run_compute_case(d));
  gate(run_negative_control(d));

  /* Non-gated characterization. */
  run_sampler_array_probe(d);

  std::cout << "================ SUMMARY ================\n";
  std::cout << "gated cases passed: " << passed << "/" << total << "\n";
  if (passed == total) {
    std::cout << "T7.PRE HARNESS PASS: the standalone shader-compiler module compiles "
                 "realistic Blender-shaped shaders end-to-end and creates live Dawn pipelines "
                 "from its generated bind-group layouts; default Tint is correctly rejected.\n";
    return 0;
  }
  std::cerr << "T7.PRE HARNESS FAIL\n";
  return 1;
}
