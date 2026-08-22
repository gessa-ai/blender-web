/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm contract for the canonical in-tree WebGPU shader
 * compiler postimage. This intentionally tests the evolved module rather than
 * the standalone T7.pre prototype: WGSL caching, Tint reflection, sampler
 * compaction, and current binding policies all participate.
 */

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include "wgpu_shader_cache.hh"
#include "wgpu_shader_compiler.hh"
#include "wgpu_shader_interface_map.hh"

#include "tests/test_shaders.hh"

namespace bw = blender::gpu::webgpu;
namespace shaders = blender::gpu::webgpu::test_shaders;

namespace {

using BindingPair = std::pair<uint32_t, uint32_t>;

bool exact_bindings(const bw::InterfaceMap &map, const std::vector<uint32_t> &expected)
{
  if (map.entries.size() != expected.size()) {
    return false;
  }
  for (size_t index = 0; index < expected.size(); index++) {
    if (map.entries[index].binding != expected[index]) {
      return false;
    }
  }
  return true;
}

bool exact_remaps(const bw::InterfaceMap &map, const std::vector<BindingPair> &expected)
{
  if (map.sampler_mappings.size() != expected.size()) {
    return false;
  }
  for (size_t index = 0; index < expected.size(); index++) {
    const bw::SamplerRemap &actual = map.sampler_mappings[index];
    if (actual.from.group != 0 || actual.to.group != 0 ||
        actual.from.binding != expected[index].first || actual.to.binding != expected[index].second)
    {
      return false;
    }
  }
  return true;
}

bool contains_all(const std::string &text, const std::vector<std::string> &needles)
{
  return std::all_of(needles.begin(), needles.end(), [&](const std::string &needle) {
    return text.find(needle) != std::string::npos;
  });
}

size_t line_count_with(const std::string &text, const std::string &needle)
{
  size_t count = 0;
  size_t begin = 0;
  while (begin < text.size()) {
    const size_t end = text.find('\n', begin);
    const size_t length = end == std::string::npos ? text.size() - begin : end - begin;
    if (text.substr(begin, length).find(needle) != std::string::npos) {
      count++;
    }
    if (end == std::string::npos) {
      break;
    }
    begin = end + 1;
  }
  return count;
}

std::string cache_file_path(const char *cache_dir, const bw::ShaderCacheKey &key)
{
  char filename[48];
  std::snprintf(filename,
                sizeof(filename),
                "%016llx%016llx.wgslc",
                static_cast<unsigned long long>(key.hi),
                static_cast<unsigned long long>(key.lo));
  return std::string(cache_dir) + "/" + filename;
}

bool copy_file(const std::string &source_path, const std::string &target_path)
{
  FILE *source = std::fopen(source_path.c_str(), "rb");
  if (source == nullptr) {
    return false;
  }
  FILE *target = std::fopen(target_path.c_str(), "wb");
  if (target == nullptr) {
    std::fclose(source);
    return false;
  }

  bool ok = true;
  char buffer[4096];
  while (ok) {
    const size_t bytes_read = std::fread(buffer, 1, sizeof(buffer), source);
    if (bytes_read != 0 && std::fwrite(buffer, 1, bytes_read, target) != bytes_read) {
      ok = false;
    }
    if (bytes_read != sizeof(buffer)) {
      ok = ok && std::feof(source) != 0 && std::ferror(source) == 0;
      break;
    }
  }
  ok = std::fclose(source) == 0 && ok;
  ok = std::fclose(target) == 0 && ok;
  return ok;
}

std::string binding_list(const std::vector<uint32_t> &bindings)
{
  std::ostringstream output;
  for (size_t index = 0; index < bindings.size(); index++) {
    if (index != 0) {
      output << ',';
    }
    output << bindings[index];
  }
  return output.str();
}

std::string interface_binding_list(const bw::InterfaceMap &map)
{
  std::vector<uint32_t> bindings;
  bindings.reserve(map.entries.size());
  for (const wgpu::BindGroupLayoutEntry &entry : map.entries) {
    bindings.push_back(entry.binding);
  }
  return binding_list(bindings);
}

std::vector<bw::ResourceDesc> bindmap_resources()
{
  using namespace bw;
  return {
      {ResourceKind::UniformBuffer,
       0,
       STAGE_VERTEX | STAGE_FRAGMENT,
       {},
       {},
       {},
       {},
       {},
       {},
       {},
       "Globals"},
      {ResourceKind::Sampler,
       1,
       STAGE_FRAGMENT,
       TexelClass::Float,
       TexDim::e2D,
       true,
       1,
       {},
       {},
       {},
       "color_tex"},
      {ResourceKind::Sampler,
       2,
       STAGE_FRAGMENT,
       TexelClass::Float,
       TexDim::e2D,
       true,
       1,
       {},
       {},
       {},
       "normal_tex"},
      {ResourceKind::UniformBuffer,
       3,
       STAGE_FRAGMENT,
       {},
       {},
       {},
       {},
       {},
       {},
       {},
       "Material"},
      {ResourceKind::StorageBuffer,
       4,
       STAGE_FRAGMENT,
       {},
       {},
       {},
       1,
       true,
       {},
       {},
       "LightData"},
      {ResourceKind::UniformBuffer,
       5,
       STAGE_VERTEX | STAGE_FRAGMENT,
       {},
       {},
       {},
       {},
       {},
       {},
       {},
       "Constants"},
  };
}

std::vector<bw::ResourceDesc> type_resources()
{
  using namespace bw;
  return {
      {ResourceKind::UniformBuffer,
       0,
       STAGE_FRAGMENT,
       {},
       {},
       {},
       {},
       {},
       {},
       {},
       "Globals"},
      {ResourceKind::Sampler,
       1,
       STAGE_FRAGMENT,
       TexelClass::Float,
       TexDim::e2D,
       true,
       1,
       {},
       {},
       {},
       "color_tex"},
      {ResourceKind::Sampler,
       2,
       STAGE_FRAGMENT,
       TexelClass::Shadow,
       TexDim::e2D,
       false,
       1,
       {},
       {},
       {},
       "shadow_tex"},
      {ResourceKind::Sampler,
       3,
       STAGE_FRAGMENT,
       TexelClass::Uint,
       TexDim::e2D,
       false,
       1,
       {},
       {},
       {},
       "id_tex"},
  };
}

std::vector<bw::ResourceDesc> compute_resources()
{
  using namespace bw;
  return {
      {ResourceKind::UniformBuffer,
       0,
       STAGE_COMPUTE,
       {},
       {},
       {},
       {},
       {},
       {},
       {},
       "Params"},
      {ResourceKind::StorageBuffer,
       1,
       STAGE_COMPUTE,
       {},
       {},
       {},
       1,
       false,
       {},
       {},
       "Histogram"},
      {ResourceKind::StorageBuffer,
       2,
       STAGE_COMPUTE,
       {},
       {},
       {},
       1,
       true,
       {},
       {},
       "InputVals"},
  };
}

bool bindmap_cache_reflection_contract()
{
  bw::ShaderStageSources sources;
  sources.vertex = shaders::kBindmapVert;
  sources.fragment = shaders::kBindmapFrag;
  sources.name = "bindmap_integrated";

  const bw::CompileResult cold = bw::compile_shader(sources, bindmap_resources());
  const bw::CompileResult warm = bw::compile_shader(sources, bindmap_resources());
  return cold.ok && warm.ok && cold.vertex_wgsl == warm.vertex_wgsl &&
         cold.fragment_wgsl == warm.fragment_wgsl &&
         exact_bindings(cold.interface, {0, 1, 257, 2, 258, 3, 4, 5}) &&
         exact_remaps(cold.interface, {{1, 257}, {2, 258}}) &&
         cold.vertex_resource_bindings == std::vector<uint32_t>({0, 5}) &&
         cold.fragment_resource_bindings ==
             std::vector<uint32_t>({0, 1, 2, 3, 4, 5, 257, 258}) &&
         cold.sampled_texture_bindings == std::vector<uint32_t>({1, 2}) &&
         cold.vertex_resource_bindings == warm.vertex_resource_bindings &&
         cold.fragment_resource_bindings == warm.fragment_resource_bindings &&
         cold.sampled_texture_bindings == warm.sampled_texture_bindings;
}

bool cache_envelope_contract()
{
  const char *cache_dir = std::getenv("BW_SHADER_CACHE_DIR");
  if (cache_dir == nullptr || cache_dir[0] == '\0') {
    return false;
  }

  const bw::ShaderCacheKey key{0x454e56454c4f5045ull, 0x545241494c494e47ull};
  const std::string path = cache_file_path(cache_dir, key);
  const std::string expected_vertex = "vertex-envelope";
  const std::string expected_fragment = "fragment-envelope";
  const std::string expected_compute = "compute-envelope";
  bw::cache_store(key, expected_vertex, expected_fragment, expected_compute);

  std::string vertex;
  std::string fragment;
  std::string compute;
  const bool clean_hit = bw::cache_lookup(key, vertex, fragment, compute) &&
                         vertex == expected_vertex && fragment == expected_fragment &&
                         compute == expected_compute;

  FILE *file = std::fopen(path.c_str(), "ab");
  const bool appended = file != nullptr && std::fputc('!', file) != EOF;
  const bool closed = file != nullptr && std::fclose(file) == 0;

  vertex = "vertex-sentinel";
  fragment = "fragment-sentinel";
  compute = "compute-sentinel";
  const bool trailing_rejected = !bw::cache_lookup(key, vertex, fragment, compute) &&
                                 vertex == "vertex-sentinel" &&
                                 fragment == "fragment-sentinel" &&
                                 compute == "compute-sentinel";
  const bool removed = std::remove(path.c_str()) == 0;
  return clean_hit && appended && closed && trailing_rejected && removed;
}

bool cache_key_binding_contract()
{
  const char *cache_dir = std::getenv("BW_SHADER_CACHE_DIR");
  if (cache_dir == nullptr || cache_dir[0] == '\0') {
    return false;
  }

  const bw::ShaderCacheKey source_key{0x4b455942494e4441ull, 0x534f555243452d31ull};
  const bw::ShaderCacheKey target_key{0x4b455942494e4442ull, 0x5441524745542d32ull};
  const std::string source_path = cache_file_path(cache_dir, source_key);
  const std::string target_path = cache_file_path(cache_dir, target_key);
  bw::cache_store(source_key, "source-vertex", "source-fragment", "source-compute");
  bw::cache_store(target_key, "target-vertex", "target-fragment", "target-compute");

  const bool substituted = copy_file(source_path, target_path);
  std::string vertex = "vertex-sentinel";
  std::string fragment = "fragment-sentinel";
  std::string compute = "compute-sentinel";
  const bool substitution_rejected = !bw::cache_lookup(target_key, vertex, fragment, compute) &&
                                     vertex == "vertex-sentinel" &&
                                     fragment == "fragment-sentinel" &&
                                     compute == "compute-sentinel";
  const bool source_removed = std::remove(source_path.c_str()) == 0;
  const bool target_removed = std::remove(target_path.c_str()) == 0;
  return substituted && substitution_rejected && source_removed && target_removed;
}

bool type_reflection_contract()
{
  bw::ShaderStageSources sources;
  sources.vertex = shaders::kSimpleVert;
  sources.fragment = shaders::kTypesFrag;
  sources.name = "types_integrated";
  const bw::CompileResult result = bw::compile_shader(sources, type_resources());

  const bool ok = result.ok &&
                  exact_bindings(result.interface, {0, 1, 257, 2, 258, 3, 259}) &&
                  exact_remaps(result.interface, {{1, 257}, {2, 258}, {3, 259}}) &&
                  result.vertex_resource_bindings.empty() &&
                  result.fragment_resource_bindings ==
                      std::vector<uint32_t>({0, 1, 2, 3, 257, 258, 259}) &&
                  result.sampled_texture_bindings == std::vector<uint32_t>({1, 2}) &&
                  contains_all(result.fragment_wgsl,
                               {"texture_2d<f32>",
                                "texture_depth_2d",
                                "sampler_comparison",
                                "texture_2d<u32>"});
  if (!ok) {
    std::cerr << "type reflection detail: ok=" << result.ok
              << " interface=" << interface_binding_list(result.interface)
              << " vertex=" << binding_list(result.vertex_resource_bindings)
              << " fragment=" << binding_list(result.fragment_resource_bindings)
              << " sampled=" << binding_list(result.sampled_texture_bindings)
              << " wgsl_float=" << (result.fragment_wgsl.find("texture_2d<f32>") !=
                                      std::string::npos)
              << " wgsl_depth=" << (result.fragment_wgsl.find("texture_depth_2d") !=
                                      std::string::npos)
              << " wgsl_compare=" << (result.fragment_wgsl.find("sampler_comparison") !=
                                        std::string::npos)
              << " wgsl_uint=" << (result.fragment_wgsl.find("texture_2d<u32>") !=
                                     std::string::npos)
              << '\n';
  }
  return ok;
}

bool compute_reflection_contract()
{
  bw::ShaderStageSources sources;
  sources.compute = shaders::kComputeAtomic;
  sources.name = "compute_integrated";
  const bw::CompileResult result = bw::compile_shader(sources, compute_resources());

  return result.ok && exact_bindings(result.interface, {0, 1, 2}) &&
         result.interface.sampler_mappings.empty() &&
         result.compute_resource_bindings == std::vector<uint32_t>({0, 1, 2}) &&
         result.sampled_texture_bindings.empty() &&
         contains_all(result.compute_wgsl,
                      {"atomic<u32>", "var<storage, read_write>", "var<storage, read>"});
}

bool binding_policy_contract()
{
  using namespace bw;
  const InterfaceMap visibility = build_interface_map({
      {ResourceKind::StorageBuffer,
       0,
       STAGE_VERTEX | STAGE_FRAGMENT,
       {},
       {},
       {},
       1,
       false,
       {},
       {},
       "rw_buffer"},
      {ResourceKind::StorageImage,
       1,
       STAGE_VERTEX | STAGE_FRAGMENT,
       TexelClass::Float,
       TexDim::e2D,
       false,
       1,
       true,
       wgpu::StorageTextureAccess::ReadWrite,
       wgpu::TextureFormat::RGBA8Unorm,
       "rw_image"},
      {ResourceKind::StorageBuffer,
       2,
       STAGE_VERTEX | STAGE_FRAGMENT,
       {},
       {},
       {},
       1,
       true,
       {},
       {},
       "readonly_buffer"},
  });
  const InterfaceMap colliding = build_interface_map(bindmap_resources(), 5);
  const InterfaceMap overflowing = build_interface_map(
      {{ResourceKind::Sampler,
        100,
        STAGE_FRAGMENT,
        TexelClass::Float,
        TexDim::e2D,
        true,
        1,
        {},
        {},
        {},
        "overflow"}},
      900);

  return visibility.ok && visibility.entries.size() == 3 &&
         visibility.entries[0].visibility == wgpu::ShaderStage::Fragment &&
         visibility.entries[1].visibility == wgpu::ShaderStage::Fragment &&
         visibility.entries[2].visibility ==
             (wgpu::ShaderStage::Vertex | wgpu::ShaderStage::Fragment) &&
         infer_sample_type(TexelClass::Depth, false) ==
             wgpu::TextureSampleType::UnfilterableFloat &&
         infer_sample_type(TexelClass::Shadow, false) == wgpu::TextureSampleType::Depth &&
         infer_sampler_type(TexelClass::Shadow, false) ==
             wgpu::SamplerBindingType::Comparison &&
         !colliding.ok && !overflowing.ok;
}

bool sampler_compaction_contract()
{
  constexpr uint32_t sampler_count = 17;
  std::ostringstream glsl;
  glsl << "#version 450\nlayout(location = 0) out vec4 out_color;\n";
  std::vector<bw::ResourceDesc> resources;
  std::vector<uint32_t> expected_resources;
  for (uint32_t index = 0; index < sampler_count; index++) {
    glsl << "layout(binding = " << index << ") uniform sampler2D tex" << index << ";\n";
    resources.push_back({bw::ResourceKind::Sampler,
                         index,
                         bw::STAGE_FRAGMENT,
                         bw::TexelClass::Float,
                         bw::TexDim::e2D,
                         true,
                         1,
                         {},
                         {},
                         {},
                         "compact"});
    expected_resources.push_back(index);
  }
  glsl << "void main() { vec2 uv = vec2(0.25); vec4 value = vec4(0.0);\n";
  for (uint32_t index = 0; index < sampler_count; index++) {
    glsl << "value += texture(tex" << index << ", uv);\n";
  }
  glsl << "out_color = value; }\n";

  bw::ShaderStageSources sources;
  sources.fragment = glsl.str();
  sources.name = "sampler_compact_integrated";
  const bw::CompileResult result = bw::compile_shader(sources, resources);

  if (!result.ok || result.interface.entries.size() != sampler_count + 1 ||
      result.interface.sampler_mappings.size() != sampler_count ||
      line_count_with(result.fragment_wgsl, " : sampler") != 1)
  {
    return false;
  }
  expected_resources.push_back(bw::kSamplerBindingBaseFixed);
  std::sort(expected_resources.begin(), expected_resources.end());
  if (result.fragment_resource_bindings != expected_resources ||
      result.sampled_texture_bindings != std::vector<uint32_t>({0,
                                                                1,
                                                                2,
                                                                3,
                                                                4,
                                                                5,
                                                                6,
                                                                7,
                                                                8,
                                                                9,
                                                                10,
                                                                11,
                                                                12,
                                                                13,
                                                                14,
                                                                15,
                                                                16}))
  {
    return false;
  }
  return std::all_of(result.interface.sampler_mappings.begin(),
                     result.interface.sampler_mappings.end(),
                     [&](const bw::SamplerRemap &mapping) {
                       return mapping.from.group == 0 && mapping.to.group == 0 &&
                              mapping.to.binding == bw::kSamplerBindingBaseFixed;
                     });
}

}  // namespace

int main()
{
  const char *cache_dir = std::getenv("BW_SHADER_CACHE_DIR");
  if (cache_dir == nullptr || cache_dir[0] == '\0' ||
      std::getenv("BW_SHADER_CACHE_CENSUS_DIR") != nullptr)
  {
    std::cerr << "the integrated contract requires an explicit cache directory and no census "
                 "filter\n";
    return 64;
  }

  int passed = 0;
  int total = 0;
  auto gate = [&](const char *name, bool ok) {
    total++;
    if (ok) {
      passed++;
      std::cout << "CONTRACT " << name << " PASS\n";
    }
    else {
      std::cerr << "CONTRACT " << name << " FAIL\n";
    }
  };

  gate("bindmap_cache_reflection", bindmap_cache_reflection_contract());
  gate("cache_envelope", cache_envelope_contract());
  gate("cache_key_binding", cache_key_binding_contract());
  gate("type_reflection", type_reflection_contract());
  gate("compute_reflection", compute_reflection_contract());
  gate("binding_policy", binding_policy_contract());
  gate("sampler_compaction", sampler_compaction_contract());

  if (passed == 7 && total == 7) {
    std::cout << "INTEGRATED_SHADER_COMPILER_PASS contracts=7 cache_entries=4\n";
    return 0;
  }
  std::cerr << "INTEGRATED_SHADER_COMPILER_FAIL contracts=" << passed << "/" << total << "\n";
  return 1;
}
