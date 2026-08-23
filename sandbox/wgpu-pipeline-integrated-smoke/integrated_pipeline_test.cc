/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm parity contract for the canonical in-tree WebGPU
 * render-pipeline enum mappings. No instance, adapter, device, or pipeline is
 * created; live descriptor validation remains part of the hardware-gated M3
 * replay. */

#include <array>
#include <cstdio>
#include <limits>
#include <unordered_set>

#ifndef BW_WGPU_PIPELINE_SOURCE
#  error "BW_WGPU_PIPELINE_SOURCE must name the canonical wgpu_pipeline.cc"
#endif

/* The dummy-binding helper intentionally has internal linkage. Including the
 * canonical translation unit keeps this contract on the shipping vertex plan. */
#include BW_WGPU_PIPELINE_SOURCE

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

class BufferHandleProbe {
 public:
  BufferHandleProbe() = default;
  explicit BufferHandleProbe(const int identity) : identity_(identity) {}

  bool operator==(std::nullptr_t) const
  {
    return identity_ == 0;
  }

  int identity() const
  {
    return identity_;
  }

 private:
  int identity_ = 0;
};

class BufferDeviceProbe {
 public:
  explicit BufferDeviceProbe(const bool create_success) : create_success_(create_success) {}

  BufferHandleProbe CreateBuffer(const wgpu::BufferDescriptor *descriptor)
  {
    create_calls_++;
    descriptor_present_ = descriptor != nullptr;
    if (descriptor != nullptr) {
      size_ = descriptor->size;
      usage_ = descriptor->usage;
      mapped_at_creation_ = descriptor->mappedAtCreation;
    }
    return create_success_ ? BufferHandleProbe(29) : BufferHandleProbe();
  }

  size_t create_calls() const
  {
    return create_calls_;
  }

  bool descriptor_present() const
  {
    return descriptor_present_;
  }

  uint64_t size() const
  {
    return size_;
  }

  wgpu::BufferUsage usage() const
  {
    return usage_;
  }

  bool mapped_at_creation() const
  {
    return mapped_at_creation_;
  }

 private:
  bool create_success_ = false;
  bool descriptor_present_ = false;
  size_t create_calls_ = 0;
  uint64_t size_ = 0;
  wgpu::BufferUsage usage_ = wgpu::BufferUsage::None;
  bool mapped_at_creation_ = false;
};

bool multiview_uniform_allocation_contract()
{
  constexpr wgpu::BufferUsage expected_usage =
      wgpu::BufferUsage::Uniform | wgpu::BufferUsage::CopyDst;

  BufferDeviceProbe failing_device(false);
  BufferHandleProbe failed_output(7);
  if (!require(!bw::multi_viewport_uniform_buffer_create(failing_device, failed_output),
               "failed multi-viewport allocation is rejected") ||
      !require(failed_output.identity() == 7,
               "failed multi-viewport allocation preserves output") ||
      !require(failing_device.create_calls() == 1 && failing_device.descriptor_present() &&
                   failing_device.size() == 16 && failing_device.usage() == expected_usage &&
                   !failing_device.mapped_at_creation(),
               "failed multi-viewport allocation uses the exact descriptor"))
  {
    return false;
  }

  BufferDeviceProbe successful_device(true);
  BufferHandleProbe successful_output(11);
  if (!require(bw::multi_viewport_uniform_buffer_create(successful_device, successful_output),
               "successful multi-viewport allocation is accepted") ||
      !require(successful_output.identity() == 29,
               "successful multi-viewport allocation publishes the candidate") ||
      !require(successful_device.create_calls() == 1 && successful_device.descriptor_present() &&
                   successful_device.size() == 16 &&
                   successful_device.usage() == expected_usage &&
                   !successful_device.mapped_at_creation(),
               "successful multi-viewport allocation uses the exact descriptor"))
  {
    return false;
  }

  std::puts(
      "CONTRACT multiview_uniform_allocation PASS cases=2 creates=2 failure=atomic bytes=16");
  return true;
}

class CacheHandleProbe {
 public:
  CacheHandleProbe() = default;
  explicit CacheHandleProbe(const int identity) : identity_(identity) {}

  bool operator==(std::nullptr_t) const
  {
    return identity_ == 0;
  }

  int identity() const
  {
    return identity_;
  }

 private:
  int identity_ = 0;
};

bool transient_handle_publication_contract()
{
  CacheHandleProbe output(31);
  if (!require(!bw::transient_handle_publish_if_valid(CacheHandleProbe(), output),
               "null transient handle is rejected") ||
      !require(output.identity() == 31, "failed transient publication preserves output"))
  {
    return false;
  }

  if (!require(bw::transient_handle_publish_if_valid(CacheHandleProbe(73), output),
               "valid transient handle is accepted") ||
      !require(output.identity() == 73, "valid transient handle is published"))
  {
    return false;
  }

  std::puts(
      "CONTRACT transient_handle_publication PASS attempts=2 failure=atomic success=published");
  return true;
}

bool vertex_buffer_handle_resolution_contract()
{
  const std::array<int, 3> bindings = {11, 22, 33};

  std::vector<CacheHandleProbe> failed_output = {CacheHandleProbe(97)};
  int failed_resolves = 0;
  if (!require(
          !bw::vertex_buffer_handles_resolve_if_valid(
              bindings,
              [&](const int binding) {
                failed_resolves++;
                return binding == 22 ? CacheHandleProbe() : CacheHandleProbe(binding);
              },
              failed_output),
          "missing planned vertex buffer is rejected") ||
      !require(failed_resolves == 2, "planned vertex resolution fails fast") ||
      !require(failed_output.size() == 1 && failed_output[0].identity() == 97,
               "failed planned vertex resolution preserves output"))
  {
    return false;
  }

  std::vector<CacheHandleProbe> successful_output = {CacheHandleProbe(101)};
  int successful_resolves = 0;
  if (!require(
          bw::vertex_buffer_handles_resolve_if_valid(
              bindings,
              [&](const int binding) {
                successful_resolves++;
                return CacheHandleProbe(binding);
              },
              successful_output),
          "complete planned vertex buffers are accepted") ||
      !require(successful_resolves == 3 && successful_output.size() == 3,
               "complete planned vertex resolution census") ||
      !require(successful_output[0].identity() == 11 &&
                   successful_output[1].identity() == 22 &&
                   successful_output[2].identity() == 33,
               "complete planned vertex buffers publish in slot order"))
  {
    return false;
  }

  const std::array<int, 0> empty_bindings = {};
  std::vector<CacheHandleProbe> empty_output = {CacheHandleProbe(103)};
  if (!require(
          bw::vertex_buffer_handles_resolve_if_valid(
              empty_bindings,
              [](const int binding) { return CacheHandleProbe(binding); },
              empty_output),
          "procedural draw with no vertex buffers is accepted") ||
      !require(empty_output.empty(), "empty planned vertex resolution publishes empty output"))
  {
    return false;
  }

  std::puts(
      "CONTRACT vertex_buffer_handle_resolution PASS cases=3 resolved=5 failure=atomic order=stable");
  return true;
}

bool cache_handle_publication_contract()
{
  std::unordered_map<uint32_t, CacheHandleProbe> cache;
  cache.emplace(3u, CacheHandleProbe(31));

  const CacheHandleProbe failed_candidate;
  if (!require(!bw::cache_handle_if_valid(cache, 7u, failed_candidate),
               "null cache candidate is rejected") ||
      !require(cache.size() == 1 && cache.find(7u) == cache.end(),
               "null cache candidate is not published") ||
      !require(cache.at(3u).identity() == 31, "failed publication preserves cache"))
  {
    return false;
  }

  const CacheHandleProbe retry_candidate(73);
  if (!require(bw::cache_handle_if_valid(cache, 7u, retry_candidate),
               "valid retry candidate is accepted") ||
      !require(cache.size() == 2 && cache.at(7u).identity() == 73,
               "valid retry candidate is published") ||
      !require(retry_candidate.identity() == 73, "publication preserves caller handle"))
  {
    return false;
  }

  std::puts(
      "CONTRACT cache_handle_publication PASS attempts=2 failure=unpublished retry=published entries=2");
  return true;
}

struct ComputePipelineVariantProbe {
  std::vector<uint32_t> key;
  CacheHandleProbe pipeline;
};

bool compute_pipeline_cache_publication_contract()
{
  std::vector<ComputePipelineVariantProbe> cache;
  cache.push_back({{3u}, CacheHandleProbe(31)});

  const std::vector<uint32_t> retry_key = {7u, 11u};
  const CacheHandleProbe failed_candidate;
  if (!require(!bw::cache_variant_if_valid(cache, retry_key, failed_candidate),
               "null compute-pipeline candidate is rejected") ||
      !require(cache.size() == 1 && cache.front().key == std::vector<uint32_t>{3u},
               "null compute-pipeline candidate is not published") ||
      !require(cache.front().pipeline.identity() == 31,
               "failed compute-pipeline publication preserves cache"))
  {
    return false;
  }

  const CacheHandleProbe retry_candidate(73);
  if (!require(bw::cache_variant_if_valid(cache, retry_key, retry_candidate),
               "valid compute-pipeline retry is accepted") ||
      !require(cache.size() == 2 && cache.back().key == retry_key &&
                   cache.back().pipeline.identity() == 73,
               "valid compute-pipeline retry is published") ||
      !require(retry_candidate.identity() == 73,
               "compute-pipeline publication preserves caller handle"))
  {
    return false;
  }

  std::puts(
      "CONTRACT compute_pipeline_cache_publication PASS attempts=2 failure=unpublished retry=published entries=2");
  return true;
}

bool primitive_topology_contract()
{
  using PT = wgpu::PrimitiveTopology;
  struct Expected {
    blender::GPUPrimType primitive;
    PT topology;
  };
  constexpr std::array<Expected, 11> expected = {{
      {blender::GPU_PRIM_POINTS, PT::PointList},
      {blender::GPU_PRIM_LINES, PT::LineList},
      {blender::GPU_PRIM_TRIS, PT::TriangleList},
      {blender::GPU_PRIM_LINE_STRIP, PT::LineStrip},
      {blender::GPU_PRIM_LINE_LOOP, PT::LineStrip},
      {blender::GPU_PRIM_TRI_STRIP, PT::TriangleStrip},
      {blender::GPU_PRIM_TRI_FAN, PT::TriangleList},
      {blender::GPU_PRIM_LINES_ADJ, PT::TriangleList},
      {blender::GPU_PRIM_TRIS_ADJ, PT::TriangleList},
      {blender::GPU_PRIM_LINE_STRIP_ADJ, PT::TriangleList},
      {blender::GPU_PRIM_NONE, PT::TriangleList},
  }};

  for (const Expected &row : expected) {
    if (!require(bw::to_wgpu_topology(row.primitive) == row.topology,
                 "primitive topology mapping"))
    {
      return false;
    }
  }
  std::puts("CONTRACT primitive_topology PASS cases=11");
  return true;
}

bool strip_index_format_contract()
{
  using IF = wgpu::IndexFormat;
  constexpr std::array primitives = {
      blender::GPU_PRIM_POINTS,
      blender::GPU_PRIM_LINES,
      blender::GPU_PRIM_TRIS,
      blender::GPU_PRIM_LINE_STRIP,
      blender::GPU_PRIM_LINE_LOOP,
      blender::GPU_PRIM_TRI_STRIP,
      blender::GPU_PRIM_TRI_FAN,
      blender::GPU_PRIM_LINES_ADJ,
      blender::GPU_PRIM_TRIS_ADJ,
      blender::GPU_PRIM_LINE_STRIP_ADJ,
      blender::GPU_PRIM_NONE,
  };
  constexpr std::array index_formats = {IF::Undefined, IF::Uint16, IF::Uint32};

  size_t cases = 0;
  size_t selected = 0;
  for (const blender::GPUPrimType primitive : primitives) {
    const bool is_strip = primitive == blender::GPU_PRIM_LINE_STRIP ||
                          primitive == blender::GPU_PRIM_LINE_LOOP ||
                          primitive == blender::GPU_PRIM_TRI_STRIP;
    for (const IF index_format : index_formats) {
      const IF expected = is_strip ? index_format : IF::Undefined;
      if (!require(bw::to_wgpu_strip_index_format(primitive, index_format) == expected,
                   "strip index-format mapping"))
      {
        return false;
      }
      cases++;
      selected += expected != IF::Undefined ? 1 : 0;
    }
  }
  if (!require(cases == 33, "strip index-format census") ||
      !require(selected == 6, "selected strip index-format census"))
  {
    return false;
  }
  std::puts("CONTRACT strip_index_format PASS cases=33 selected=6");
  return true;
}

bool indirect_draw_span_contract()
{
  struct Case {
    int count;
    intptr_t offset;
    intptr_t stride;
    bool indexed;
    uint64_t buffer_size;
    bool accepted;
    uint64_t first_offset;
    uint64_t command_stride;
    uint64_t command_size;
    uint64_t end_offset;
  };
  constexpr intptr_t aligned_intptr_max =
      std::numeric_limits<intptr_t>::max() & ~intptr_t(3);
  constexpr std::array<Case, 19> cases = {{
      {1, 0, 0, false, 16, true, 0, 16, 16, 16},
      {1, 4, 0, true, 24, true, 4, 20, 20, 24},
      {3, 8, 0, false, 56, true, 8, 16, 16, 56},
      {3, 4, 32, true, 88, true, 4, 32, 20, 88},
      {2, 4, 4, false, 24, true, 4, 4, 16, 24},
      {2, 0, 24, true, 44, true, 0, 24, 20, 44},
      {4, 16, 32, false, 128, true, 16, 32, 16, 128},
      {0, 0, 0, false, 16, false, 0, 0, 0, 0},
      {-1, 0, 0, false, 16, false, 0, 0, 0, 0},
      {1, -4, 0, false, 16, false, 0, 0, 0, 0},
      {2, 0, -4, false, 32, false, 0, 0, 0, 0},
      {1, 2, 0, false, 32, false, 0, 0, 0, 0},
      {2, 0, 2, false, 32, false, 0, 0, 0, 0},
      {1, 0, 0, false, 15, false, 0, 0, 0, 0},
      {1, 0, 0, true, 19, false, 0, 0, 0, 0},
      {1, 4, 0, false, 16, false, 0, 0, 0, 0},
      {2, 0, 0, false, 31, false, 0, 0, 0, 0},
      {2, 0, 24, true, 43, false, 0, 0, 0, 0},
      {std::numeric_limits<int>::max(),
       aligned_intptr_max,
       aligned_intptr_max,
       false,
       1024,
       false,
       0,
       0,
       0,
       0},
  }};

  size_t accepted = 0;
  size_t rejected = 0;
  uint64_t first_sum = 0;
  uint64_t stride_sum = 0;
  uint64_t end_sum = 0;
  for (const Case &test : cases) {
    bw::IndirectDrawSpan actual = {11, 12, 13, 14};
    const bw::IndirectDrawSpan sentinel = actual;
    const bool result = bw::indirect_draw_span(
        test.count, test.offset, test.stride, test.indexed, test.buffer_size, actual);
    if (!require(result == test.accepted, "indirect draw span decision")) {
      return false;
    }
    if (!result) {
      if (!require(actual.first_offset == sentinel.first_offset &&
                       actual.command_stride == sentinel.command_stride &&
                       actual.command_size == sentinel.command_size &&
                       actual.end_offset == sentinel.end_offset,
                   "rejected indirect draw span preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.first_offset == test.first_offset &&
                     actual.command_stride == test.command_stride &&
                     actual.command_size == test.command_size &&
                     actual.end_offset == test.end_offset,
                 "accepted indirect draw span geometry"))
    {
      return false;
    }
    accepted++;
    first_sum += actual.first_offset;
    stride_sum += actual.command_stride;
    end_sum += actual.end_offset;
  }

  if (!require(accepted == 7 && rejected == 12, "indirect draw span census") ||
      !require(first_sum == 36 && stride_sum == 144 && end_sum == 380,
               "indirect draw span aggregate"))
  {
    return false;
  }
  std::puts("CONTRACT indirect_draw_span PASS cases=19 accepted=7 rejected=12 "
            "first_sum=36 stride_sum=144 end_sum=380");
  return true;
}

bool direct_draw_plan_contract()
{
  struct Case {
    int vertex_first;
    int vertex_count;
    int instance_first;
    int instance_count;
    bool accepted;
  };
  constexpr int int_max = std::numeric_limits<int>::max();
  constexpr int int_min = std::numeric_limits<int>::min();
  constexpr std::array<Case, 16> cases = {{
      {0, 1, 0, 1, true},
      {3, 7, 11, 13, true},
      {int_max, 1, int_max, 1, true},
      {0, int_max, 0, int_max, true},
      {int_max, int_max, int_max, int_max, true},
      {-1, 1, 0, 1, false},
      {0, -1, 0, 1, false},
      {0, 1, -1, 1, false},
      {0, 1, 0, -1, false},
      {0, 0, 0, 1, false},
      {0, 1, 0, 0, false},
      {int_min, 1, 0, 1, false},
      {0, int_min, 0, 1, false},
      {0, 1, int_min, 1, false},
      {0, 1, 0, int_min, false},
      {-1, -1, -1, -1, false},
  }};

  size_t accepted = 0;
  size_t rejected = 0;
  uint64_t value_sum = 0;
  for (const Case &test : cases) {
    bw::DirectDrawPlan actual = {101, 102, 103, 104};
    const bw::DirectDrawPlan sentinel = actual;
    const bool result = bw::direct_draw_plan(test.vertex_first,
                                             test.vertex_count,
                                             test.instance_first,
                                             test.instance_count,
                                             actual);
    if (!require(result == test.accepted, "direct draw decision")) {
      return false;
    }
    if (!result) {
      if (!require(actual.vertex_first == sentinel.vertex_first &&
                       actual.vertex_count == sentinel.vertex_count &&
                       actual.instance_first == sentinel.instance_first &&
                       actual.instance_count == sentinel.instance_count,
                   "rejected direct draw preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.vertex_first == uint32_t(test.vertex_first) &&
                     actual.vertex_count == uint32_t(test.vertex_count) &&
                     actual.instance_first == uint32_t(test.instance_first) &&
                     actual.instance_count == uint32_t(test.instance_count),
                 "accepted direct draw geometry"))
    {
      return false;
    }
    accepted++;
    value_sum += uint64_t(actual.vertex_first) + actual.vertex_count + actual.instance_first +
                 actual.instance_count;
  }

  if (!require(accepted == 5 && rejected == 11, "direct draw census") ||
      !require(value_sum == 17179869214ull, "direct draw aggregate"))
  {
    return false;
  }
  std::puts(
      "CONTRACT direct_draw_plan PASS cases=16 accepted=5 rejected=11 value_sum=17179869214");
  return true;
}

bool viewport_scissor_plan_contract()
{
  struct Case {
    int x;
    int y;
    int width;
    int height;
    uint32_t target_width;
    uint32_t target_height;
    uint32_t max_viewport_dimension;
    bool accepted;
    uint32_t scissor_x;
    uint32_t scissor_y;
    uint32_t scissor_width;
    uint32_t scissor_height;
  };
  constexpr int int_max = std::numeric_limits<int>::max();
  constexpr int int_min = std::numeric_limits<int>::min();
  constexpr std::array<Case, 28> cases = {{
      {0, 0, 640, 480, 640, 480, 8192, true, 0, 0, 640, 480},
      {10, 20, 30, 40, 640, 480, 8192, true, 10, 20, 30, 40},
      {-10, 5, 20, 10, 640, 480, 8192, true, 0, 5, 10, 10},
      {5, -10, 10, 20, 640, 480, 8192, true, 5, 0, 10, 10},
      {630, 20, 20, 30, 640, 480, 8192, true, 630, 20, 10, 30},
      {20, 470, 30, 20, 640, 480, 8192, true, 20, 470, 30, 10},
      {-10, -20, 660, 520, 640, 480, 8192, true, 0, 0, 640, 480},
      {-10, -10, 20, 20, 640, 480, 8192, true, 0, 0, 10, 10},
      {639, 479, 1, 1, 640, 480, 8192, true, 639, 479, 1, 1},
      {-63, -63, 64, 64, 64, 64, 64, true, 0, 0, 1, 1},
      {63, 63, 64, 64, 64, 64, 64, true, 63, 63, 1, 1},
      {0, 0, 0, 1, 640, 480, 8192, true, 0, 0, 0, 0},
      {0, 0, 1, 0, 640, 480, 8192, true, 0, 0, 0, 0},
      {0, 0, -1, 1, 640, 480, 8192, false, 0, 0, 0, 0},
      {0, 0, 1, -1, 640, 480, 8192, false, 0, 0, 0, 0},
      {0, 0, 1, 1, 0, 480, 8192, false, 0, 0, 0, 0},
      {0, 0, 1, 1, 640, 0, 8192, false, 0, 0, 0, 0},
      {0, 0, 1, 1, 640, 480, 0, false, 0, 0, 0, 0},
      {0, 0, 1, 1, 65, 64, 64, false, 0, 0, 0, 0},
      {0, 0, 1, 1, 64, 65, 64, false, 0, 0, 0, 0},
      {0, 0, 65, 1, 64, 64, 64, false, 0, 0, 0, 0},
      {0, 0, 1, 65, 64, 64, 64, false, 0, 0, 0, 0},
      {-10, 0, 10, 1, 640, 480, 8192, true, 0, 0, 0, 0},
      {640, 0, 1, 1, 640, 480, 8192, true, 0, 0, 0, 0},
      {0, -10, 1, 10, 640, 480, 8192, true, 0, 0, 0, 0},
      {0, 480, 1, 1, 640, 480, 8192, true, 0, 0, 0, 0},
      {int_min, 0, 1, 1, 640, 480, 8192, false, 0, 0, 0, 0},
      {int_max, 0, int_max, 1, 640, 480, 8192, false, 0, 0, 0, 0},
  }};

  size_t accepted = 0;
  size_t rejected = 0;
  uint64_t scissor_area = 0;
  for (const Case &test : cases) {
    bw::ViewportScissorPlan actual = {101, 102, 103, 104, 105, 106, 107, 108};
    const bw::ViewportScissorPlan sentinel = actual;
    const bool result = bw::viewport_scissor_plan(test.x,
                                                  test.y,
                                                  test.width,
                                                  test.height,
                                                  test.target_width,
                                                  test.target_height,
                                                  test.max_viewport_dimension,
                                                  actual);
    if (!require(result == test.accepted, "viewport/scissor decision")) {
      return false;
    }
    if (!result) {
      if (!require(actual.viewport_x == sentinel.viewport_x &&
                       actual.viewport_y == sentinel.viewport_y &&
                       actual.viewport_width == sentinel.viewport_width &&
                       actual.viewport_height == sentinel.viewport_height &&
                       actual.scissor_x == sentinel.scissor_x &&
                       actual.scissor_y == sentinel.scissor_y &&
                       actual.scissor_width == sentinel.scissor_width &&
                       actual.scissor_height == sentinel.scissor_height,
                   "rejected viewport/scissor preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.viewport_x == test.x && actual.viewport_y == test.y &&
                     actual.viewport_width == uint32_t(test.width) &&
                     actual.viewport_height == uint32_t(test.height),
                 "accepted viewport preserves raster transform") ||
        !require(actual.scissor_x == test.scissor_x &&
                     actual.scissor_y == test.scissor_y &&
                     actual.scissor_width == test.scissor_width &&
                     actual.scissor_height == test.scissor_height,
                 "accepted scissor intersection"))
    {
      return false;
    }
    accepted++;
    scissor_area += uint64_t(actual.scissor_width) * actual.scissor_height;
  }

  if (!require(accepted == 17 && rejected == 11, "viewport/scissor census") ||
      !require(scissor_area == 616503, "viewport/scissor aggregate"))
  {
    return false;
  }
  std::puts(
      "CONTRACT viewport_scissor_plan PASS cases=28 accepted=17 rejected=11 area=616503");
  return true;
}

bool window_viewport_scissor_plan_contract()
{
  struct Case {
    int viewport_x;
    int viewport_y;
    int viewport_width;
    int viewport_height;
    bool scissor_enabled;
    int scissor_x;
    int scissor_y;
    int scissor_width;
    int scissor_height;
    int target_width;
    int target_height;
    uint32_t max_viewport_dimension;
    bool accepted;
    int expected_viewport_x;
    int expected_viewport_y;
    uint32_t expected_viewport_width;
    uint32_t expected_viewport_height;
    bool expected_scissor_enabled;
    uint32_t expected_scissor_x;
    uint32_t expected_scissor_y;
    uint32_t expected_scissor_width;
    uint32_t expected_scissor_height;
  };
  constexpr int int_max = std::numeric_limits<int>::max();
  constexpr int int_min = std::numeric_limits<int>::min();
  constexpr std::array<Case, 31> cases = {{
      {0, 0, 640, 480, false, 0, 0, 0, 0, 640, 480, 8192, true,
       0, 0, 640, 480, false, 0, 0, 0, 0},
      {10, 20, 30, 40, false, 0, 0, 0, 0, 640, 480, 8192, true,
       10, 420, 30, 40, false, 0, 0, 0, 0},
      {-10, 5, 20, 10, false, 0, 0, 0, 0, 640, 480, 8192, true,
       -10, 465, 20, 10, false, 0, 0, 0, 0},
      {5, -10, 10, 20, false, 0, 0, 0, 0, 640, 480, 8192, true,
       5, 470, 10, 20, false, 0, 0, 0, 0},
      {630, 20, 20, 30, false, 0, 0, 0, 0, 640, 480, 8192, true,
       630, 430, 20, 30, false, 0, 0, 0, 0},
      {20, 470, 30, 20, false, 0, 0, 0, 0, 640, 480, 8192, true,
       20, -10, 30, 20, false, 0, 0, 0, 0},
      {-10, -20, 660, 520, false, 0, 0, 0, 0, 640, 480, 8192, true,
       -10, -20, 660, 520, false, 0, 0, 0, 0},
      {0, 0, 640, 480, true, 10, 20, 30, 40, 640, 480, 8192, true,
       0, 0, 640, 480, true, 10, 420, 30, 40},
      {0, 0, 640, 480, true, -10, 5, 20, 10, 640, 480, 8192, true,
       0, 0, 640, 480, true, 0, 465, 10, 10},
      {0, 0, 640, 480, true, 5, -10, 10, 20, 640, 480, 8192, true,
       0, 0, 640, 480, true, 5, 470, 10, 10},
      {0, 0, 64, 64, true, -10, 0, int_max, 1, 64, 64, 64, true,
       0, 0, 64, 64, true, 0, 63, 64, 1},
      {-63, 0, 64, 64, false, 0, 0, 0, 0, 64, 64, 64, true,
       -63, 0, 64, 64, false, 0, 0, 0, 0},
      {63, 0, 64, 64, false, 0, 0, 0, 0, 64, 64, 64, true,
       63, 0, 64, 64, false, 0, 0, 0, 0},
      {0, 0, 640, 480, true, 20, 470, 30, 20, 640, 480, 8192, true,
       0, 0, 640, 480, true, 20, 0, 30, 10},
      {0, 0, 0, 1, false, 0, 0, 0, 0, 640, 480, 8192, true,
       0, 479, 0, 1, false, 0, 0, 0, 0},
      {0, 0, 1, 0, false, 0, 0, 0, 0, 640, 480, 8192, true,
       0, 480, 1, 0, false, 0, 0, 0, 0},
      {-10, 0, 10, 1, false, 0, 0, 0, 0, 640, 480, 8192, true,
       -10, 479, 10, 1, true, 0, 0, 0, 0},
      {640, 0, 1, 1, false, 0, 0, 0, 0, 640, 480, 8192, true,
       640, 479, 1, 1, true, 0, 0, 0, 0},
      {0, -10, 1, 10, false, 0, 0, 0, 0, 640, 480, 8192, true,
       0, 480, 1, 10, true, 0, 0, 0, 0},
      {0, 480, 1, 1, false, 0, 0, 0, 0, 640, 480, 8192, true,
       0, -1, 1, 1, true, 0, 0, 0, 0},
      {0, 0, 1, 1, false, 0, 0, 0, 0, 0, 480, 8192, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, 0, 1, 1, false, 0, 0, 0, 0, 640, 0, 8192, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, 0, 1, 1, false, 0, 0, 0, 0, 640, 480, 0, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, 0, 1, 1, false, 0, 0, 0, 0, 65, 64, 64, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, 0, 65, 1, false, 0, 0, 0, 0, 64, 64, 64, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, int_min, 1, 1, false, 0, 0, 0, 0, 640, 480, 8192, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, int_max, 1, 1, false, 0, 0, 0, 0, 640, 480, 8192, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {int_max, 0, int_max, 1, false, 0, 0, 0, 0, 640, 480, 8192, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, 0, 640, 480, true, 0, 0, 0, 1, 640, 480, 8192, true,
       0, 0, 640, 480, true, 0, 0, 0, 0},
      {0, 0, 640, 480, true, -10, 0, 10, 1, 640, 480, 8192, true,
       0, 0, 640, 480, true, 0, 0, 0, 0},
      {0, 0, 640, 480, true, 0, int_min, 1, 1, 640, 480, 8192, true,
       0, 0, 640, 480, true, 0, 0, 0, 0},
  }};

  size_t accepted = 0;
  size_t rejected = 0;
  int64_t viewport_sum = 0;
  uint64_t scissor_area = 0;
  const auto plans_equal = [](const bw::WindowViewportPlan &a,
                              const bw::WindowViewportPlan &b) {
    return a.viewport.viewport_x == b.viewport.viewport_x &&
           a.viewport.viewport_y == b.viewport.viewport_y &&
           a.viewport.viewport_width == b.viewport.viewport_width &&
           a.viewport.viewport_height == b.viewport.viewport_height &&
           a.viewport.scissor_x == b.viewport.scissor_x &&
           a.viewport.scissor_y == b.viewport.scissor_y &&
           a.viewport.scissor_width == b.viewport.scissor_width &&
           a.viewport.scissor_height == b.viewport.scissor_height &&
           a.scissor_enabled == b.scissor_enabled && a.scissor_x == b.scissor_x &&
           a.scissor_y == b.scissor_y && a.scissor_width == b.scissor_width &&
           a.scissor_height == b.scissor_height;
  };
  for (const Case &test : cases) {
    const int viewport[4] = {
        test.viewport_x, test.viewport_y, test.viewport_width, test.viewport_height};
    const int scissor[4] = {
        test.scissor_x, test.scissor_y, test.scissor_width, test.scissor_height};
    bw::WindowViewportPlan actual = {
        {101, 102, 103, 104, 105, 106, 107, 108}, true, 109, 110, 111, 112};
    const bw::WindowViewportPlan sentinel = actual;
    const bool result = bw::window_viewport_scissor_plan(viewport,
                                                         test.scissor_enabled ? scissor : nullptr,
                                                         test.target_width,
                                                         test.target_height,
                                                         test.max_viewport_dimension,
                                                         actual);
    if (!require(result == test.accepted, "window viewport/scissor decision")) {
      return false;
    }
    if (!result) {
      if (!require(plans_equal(actual, sentinel),
                   "rejected window viewport/scissor preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.viewport.viewport_x == test.expected_viewport_x &&
                     actual.viewport.viewport_y == test.expected_viewport_y &&
                     actual.viewport.viewport_width == test.expected_viewport_width &&
                     actual.viewport.viewport_height == test.expected_viewport_height,
                 "accepted window viewport preserves bottom-origin transform") ||
        !require(actual.scissor_enabled == test.expected_scissor_enabled &&
                     actual.scissor_x == test.expected_scissor_x &&
                     actual.scissor_y == test.expected_scissor_y &&
                     actual.scissor_width == test.expected_scissor_width &&
                     actual.scissor_height == test.expected_scissor_height,
                 "accepted window scissor intersection"))
    {
      return false;
    }
    accepted++;
    viewport_sum += int64_t(actual.viewport.viewport_x) + actual.viewport.viewport_y +
                    actual.viewport.viewport_width + actual.viewport.viewport_height;
    if (actual.scissor_enabled) {
      scissor_area += uint64_t(actual.scissor_width) * actual.scissor_height;
    }
  }

  bw::WindowViewportPlan null_actual = {
      {101, 102, 103, 104, 105, 106, 107, 108}, true, 109, 110, 111, 112};
  const bw::WindowViewportPlan null_sentinel = null_actual;
  if (!require(!bw::window_viewport_scissor_plan(nullptr, nullptr, 640, 480, 8192, null_actual),
               "null window viewport rejected") ||
      !require(plans_equal(null_actual, null_sentinel), "null window viewport preserves output") ||
      !require(accepted == 23 && rejected == 8, "window viewport/scissor census") ||
      !require(viewport_sum == 16208, "window viewport aggregate") ||
      !require(scissor_area == 1764, "window scissor aggregate"))
  {
    return false;
  }
  std::puts("CONTRACT window_viewport_scissor_plan PASS cases=32 accepted=23 rejected=9 "
            "viewport_sum=16208 scissor_area=1764");
  return true;
}

bool offscreen_viewport_scissor_plan_contract()
{
  struct Case {
    int viewport[4];
    bool scissor_enabled;
    int scissor[4];
    int target_width;
    int target_height;
    uint32_t max_viewport_dimension;
    bool accepted;
    int expected_viewport_x;
    int expected_viewport_y;
    uint32_t expected_viewport_width;
    uint32_t expected_viewport_height;
    bool expected_scissor_enabled;
    uint32_t expected_scissor_x;
    uint32_t expected_scissor_y;
    uint32_t expected_scissor_width;
    uint32_t expected_scissor_height;
  };
  constexpr int int_max = std::numeric_limits<int>::max();
  constexpr std::array<Case, 20> cases = {{
      {{0, 0, 6, 5}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       0, 0, 6, 5, false, 0, 0, 0, 0},
      {{1, 1, 3, 2}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       1, 2, 3, 2, false, 0, 0, 0, 0},
      {{-2, 1, 4, 3}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       -2, 1, 4, 3, false, 0, 0, 0, 0},
      {{4, 3, 4, 3}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       4, -1, 4, 3, false, 0, 0, 0, 0},
      {{1, 0, 4, 4}, true, {3, 2, 3, 3}, 6, 5, 8, true,
       1, 1, 4, 4, true, 3, 0, 3, 3},
      {{0, 0, 6, 5}, true, {-2, 1, 4, 3}, 6, 5, 8, true,
       0, 0, 6, 5, true, 0, 1, 2, 3},
      {{0, 0, 6, 5}, true, {4, 3, 4, 3}, 6, 5, 8, true,
       0, 0, 6, 5, true, 4, 0, 2, 2},
      {{-2, -2, 10, 9}, true, {0, 0, 6, 5}, 6, 5, 16, true,
       -2, -2, 10, 9, true, 0, 0, 6, 5},
      {{-63, -63, 64, 64}, false, {0, 0, 0, 0}, 64, 64, 64, true,
       -63, 63, 64, 64, false, 0, 0, 0, 0},
      {{63, 63, 64, 64}, false, {0, 0, 0, 0}, 64, 64, 64, true,
       63, -63, 64, 64, false, 0, 0, 0, 0},
      {{0, 0, 64, 64}, true, {-10, 0, int_max, 1}, 64, 64, 64, true,
       0, 0, 64, 64, true, 0, 63, 64, 1},
      {{0, 0, 6, 5}, false, {0, 0, 0, -1}, 6, 5, 8, true,
       0, 0, 6, 5, false, 0, 0, 0, 0},
      {{0, 0, 0, 1}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       0, 4, 0, 1, false, 0, 0, 0, 0},
      {{0, 0, 1, 0}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       0, 5, 1, 0, false, 0, 0, 0, 0},
      {{-10, 0, 10, 1}, false, {0, 0, 0, 0}, 6, 5, 8, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {{0, 5, 1, 1}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       0, -1, 1, 1, true, 0, 0, 0, 0},
      {{0, 0, 1, 1}, false, {0, 0, 0, 0}, 0, 5, 8, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {{0, 0, 1, 1}, false, {0, 0, 0, 0}, 9, 5, 8, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {{0, 0, 6, 5}, true, {0, 0, 0, 1}, 6, 5, 8, true,
       0, 0, 6, 5, true, 0, 0, 0, 0},
      {{0, 0, 6, 5}, true, {-10, 0, 10, 1}, 6, 5, 8, true,
       0, 0, 6, 5, true, 0, 0, 0, 0},
  }};

  const auto plans_equal = [](const bw::FramebufferViewportPlan &a,
                              const bw::FramebufferViewportPlan &b) {
    return a.viewport.viewport_x == b.viewport.viewport_x &&
           a.viewport.viewport_y == b.viewport.viewport_y &&
           a.viewport.viewport_width == b.viewport.viewport_width &&
           a.viewport.viewport_height == b.viewport.viewport_height &&
           a.viewport.scissor_x == b.viewport.scissor_x &&
           a.viewport.scissor_y == b.viewport.scissor_y &&
           a.viewport.scissor_width == b.viewport.scissor_width &&
           a.viewport.scissor_height == b.viewport.scissor_height &&
           a.scissor_enabled == b.scissor_enabled && a.scissor_x == b.scissor_x &&
           a.scissor_y == b.scissor_y && a.scissor_width == b.scissor_width &&
           a.scissor_height == b.scissor_height;
  };

  size_t accepted = 0;
  size_t rejected = 0;
  size_t enabled_scissors = 0;
  uint64_t scissor_area = 0;
  for (size_t case_index = 0; case_index < cases.size(); case_index++) {
    const Case &test = cases[case_index];
    bw::FramebufferViewportPlan actual = {
        {101, 102, 103, 104, 105, 106, 107, 108}, true, 109, 110, 111, 112};
    const bw::FramebufferViewportPlan sentinel = actual;
    const bool result = bw::offscreen_viewport_scissor_plan(
        test.viewport,
        test.scissor_enabled ? test.scissor : nullptr,
        test.target_width,
        test.target_height,
        test.max_viewport_dimension,
        actual);
    if (!require(result == test.accepted, "offscreen viewport/scissor decision")) {
      std::fprintf(stderr, "offscreen case=%zu accepted=%d actual=%d\n", case_index,
                   int(test.accepted), int(result));
      return false;
    }
    if (!result) {
      if (!require(plans_equal(actual, sentinel),
                   "rejected offscreen viewport/scissor preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.viewport.viewport_x == test.expected_viewport_x &&
                     actual.viewport.viewport_y == test.expected_viewport_y &&
                     actual.viewport.viewport_width == test.expected_viewport_width &&
                     actual.viewport.viewport_height == test.expected_viewport_height,
                 "accepted offscreen viewport converts to WebGPU top origin") ||
        !require(actual.scissor_enabled == test.expected_scissor_enabled &&
                     actual.scissor_x == test.expected_scissor_x &&
                     actual.scissor_y == test.expected_scissor_y &&
                     actual.scissor_width == test.expected_scissor_width &&
                     actual.scissor_height == test.expected_scissor_height,
                 "accepted offscreen scissor clips independently"))
    {
      return false;
    }
    accepted++;
    if (actual.scissor_enabled) {
      enabled_scissors++;
      scissor_area += uint64_t(actual.scissor_width) * actual.scissor_height;
    }
  }

  bw::FramebufferViewportPlan null_actual = {
      {101, 102, 103, 104, 105, 106, 107, 108}, true, 109, 110, 111, 112};
  const bw::FramebufferViewportPlan null_sentinel = null_actual;
  if (!require(!bw::offscreen_viewport_scissor_plan(
                   nullptr, nullptr, 6, 5, 8, null_actual),
               "null offscreen viewport rejected") ||
      !require(plans_equal(null_actual, null_sentinel),
               "null offscreen viewport preserves output") ||
      !require(accepted == 17 && rejected == 3, "offscreen viewport/scissor census") ||
      !require(enabled_scissors == 8, "offscreen enabled-scissor census") ||
      !require(scissor_area == 113, "offscreen scissor aggregate"))
  {
    return false;
  }
  std::puts("CONTRACT offscreen_viewport_scissor_plan PASS cases=21 accepted=17 rejected=4 "
            "scissors=8 scissor_area=113");
  return true;
}

bool compute_dispatch_range_contract()
{
  struct DirectCase {
    int groups_x;
    int groups_y;
    int groups_z;
    int max_x;
    int max_y;
    int max_z;
    bool accepted;
    uint32_t expected_x;
    uint32_t expected_y;
    uint32_t expected_z;
  };
  constexpr std::array<DirectCase, 15> direct_cases = {{
      {1, 1, 1, 65535, 65535, 65535, true, 1, 1, 1},
      {0, 1, 1, 65535, 65535, 65535, true, 0, 1, 1},
      {1, 0, 1, 65535, 65535, 65535, true, 1, 0, 1},
      {1, 1, 0, 65535, 65535, 65535, true, 1, 1, 0},
      {7, 11, 13, 7, 11, 13, true, 7, 11, 13},
      {0, 0, 0, 1, 1, 1, true, 0, 0, 0},
      {-1, 1, 1, 65535, 65535, 65535, false, 0, 0, 0},
      {1, -1, 1, 65535, 65535, 65535, false, 0, 0, 0},
      {1, 1, -1, 65535, 65535, 65535, false, 0, 0, 0},
      {8, 11, 13, 7, 11, 13, false, 0, 0, 0},
      {7, 12, 13, 7, 11, 13, false, 0, 0, 0},
      {7, 11, 14, 7, 11, 13, false, 0, 0, 0},
      {1, 1, 1, 0, 1, 1, false, 0, 0, 0},
      {1, 1, 1, 1, 0, 1, false, 0, 0, 0},
      {1, 1, 1, 1, 1, 0, false, 0, 0, 0},
  }};

  size_t direct_accepted = 0;
  size_t direct_rejected = 0;
  uint64_t accepted_group_sum = 0;
  for (const DirectCase &test : direct_cases) {
    bw::ComputeDispatchPlan actual = {101, 102, 103};
    const bw::ComputeDispatchPlan sentinel = actual;
    const bool result = bw::compute_dispatch_plan(test.groups_x,
                                                  test.groups_y,
                                                  test.groups_z,
                                                  test.max_x,
                                                  test.max_y,
                                                  test.max_z,
                                                  actual);
    if (!require(result == test.accepted, "compute dispatch decision")) {
      return false;
    }
    if (!result) {
      if (!require(actual.groups_x == sentinel.groups_x &&
                       actual.groups_y == sentinel.groups_y &&
                       actual.groups_z == sentinel.groups_z,
                   "rejected compute dispatch preserves output"))
      {
        return false;
      }
      direct_rejected++;
      continue;
    }
    if (!require(actual.groups_x == test.expected_x && actual.groups_y == test.expected_y &&
                     actual.groups_z == test.expected_z,
                 "accepted compute dispatch geometry"))
    {
      return false;
    }
    direct_accepted++;
    accepted_group_sum += actual.groups_x + actual.groups_y + actual.groups_z;
  }

  struct IndirectCase {
    uint64_t offset;
    uint64_t capacity;
    bool accepted;
  };
  constexpr std::array<IndirectCase, 13> indirect_cases = {{
      {0, 12, true},
      {4, 16, true},
      {8, 20, true},
      {12, 24, true},
      {std::numeric_limits<uint64_t>::max() - 15,
       std::numeric_limits<uint64_t>::max(),
       true},
      {0, 0, false},
      {0, 11, false},
      {4, 15, false},
      {1, 32, false},
      {2, 32, false},
      {3, 32, false},
      {std::numeric_limits<uint64_t>::max() - 11,
       std::numeric_limits<uint64_t>::max(),
       false},
      {std::numeric_limits<uint64_t>::max() - 3,
       std::numeric_limits<uint64_t>::max(),
       false},
  }};
  size_t indirect_accepted = 0;
  size_t indirect_rejected = 0;
  for (const IndirectCase &test : indirect_cases) {
    const bool result = bw::compute_indirect_dispatch_range(test.offset, test.capacity);
    if (!require(result == test.accepted, "compute indirect dispatch range")) {
      return false;
    }
    result ? indirect_accepted++ : indirect_rejected++;
  }

  if (!require(direct_accepted == 6 && direct_rejected == 9,
               "direct compute dispatch census") ||
      !require(indirect_accepted == 5 && indirect_rejected == 8,
               "indirect compute dispatch census") ||
      !require(accepted_group_sum == 40, "accepted compute dispatch aggregate"))
  {
    return false;
  }
  std::puts("CONTRACT compute_dispatch_range PASS direct_cases=15 accepted=6 rejected=9 "
            "indirect_cases=13 accepted=5 rejected=8 group_sum=40");
  return true;
}

struct ComputeCommandTrace {
  bool encoder_success = false;
  bool pass_success = false;
  bool command_success = false;
  int encoder_creates = 0;
  int pass_begins = 0;
  int pass_work = 0;
  int pass_ends = 0;
  int finishes = 0;
  int submits = 0;
};

class ComputeCommandBufferProbe {
 public:
  ComputeCommandBufferProbe() = default;
  explicit ComputeCommandBufferProbe(const bool valid) : valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

 private:
  bool valid_ = false;
};

class ComputePassProbe {
 public:
  ComputePassProbe() = default;
  ComputePassProbe(ComputeCommandTrace *trace, const bool valid) : trace_(trace), valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  void Work()
  {
    trace_->pass_work++;
  }

  void End()
  {
    trace_->pass_ends++;
  }

 private:
  ComputeCommandTrace *trace_ = nullptr;
  bool valid_ = false;
};

class ComputeCommandEncoderProbe {
 public:
  ComputeCommandEncoderProbe() = default;
  ComputeCommandEncoderProbe(ComputeCommandTrace *trace, const bool valid)
      : trace_(trace), valid_(valid)
  {
  }

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  ComputePassProbe BeginComputePass()
  {
    trace_->pass_begins++;
    return ComputePassProbe(trace_, trace_->pass_success);
  }

  ComputeCommandBufferProbe Finish()
  {
    trace_->finishes++;
    return ComputeCommandBufferProbe(trace_->command_success);
  }

 private:
  ComputeCommandTrace *trace_ = nullptr;
  bool valid_ = false;
};

class ComputeCommandDeviceProbe {
 public:
  explicit ComputeCommandDeviceProbe(ComputeCommandTrace &trace) : trace_(&trace) {}

  ComputeCommandEncoderProbe CreateCommandEncoder() const
  {
    trace_->encoder_creates++;
    return ComputeCommandEncoderProbe(trace_, trace_->encoder_success);
  }

 private:
  ComputeCommandTrace *trace_ = nullptr;
};

class ComputeCommandQueueProbe {
 public:
  explicit ComputeCommandQueueProbe(ComputeCommandTrace &trace) : trace_(&trace) {}

  void Submit(const size_t count, const ComputeCommandBufferProbe *command_buffer) const
  {
    if (count == 1 && command_buffer != nullptr && !(*command_buffer == nullptr)) {
      trace_->submits++;
    }
  }

 private:
  ComputeCommandTrace *trace_ = nullptr;
};

bool compute_command_transaction_contract()
{
  struct FailureCase {
    bool encoder_success;
    bool pass_success;
    bool command_success;
    int expected_begins;
    int expected_work;
    int expected_ends;
    int expected_finishes;
  };
  constexpr std::array<FailureCase, 4> cases = {{{false, true, true, 0, 0, 0, 0},
                                                 {true, false, true, 1, 0, 0, 0},
                                                 {true, true, false, 1, 1, 1, 1},
                                                 {true, true, true, 1, 1, 1, 1}}};

  int accepted = 0;
  for (const FailureCase &test : cases) {
    ComputeCommandTrace trace;
    trace.encoder_success = test.encoder_success;
    trace.pass_success = test.pass_success;
    trace.command_success = test.command_success;
    const ComputeCommandDeviceProbe device(trace);
    const ComputeCommandQueueProbe queue(trace);

    const bool result = bw::command_pass_encode_submit_if_valid(
        device,
        queue,
        [](auto &encoder) { return encoder.BeginComputePass(); },
        [](auto &pass) { pass.Work(); });
    const bool expect_success = test.encoder_success && test.pass_success && test.command_success;
    if (!require(result == expect_success, "compute command transaction result") ||
        !require(trace.encoder_creates == 1, "compute command encoder creation count") ||
        !require(trace.pass_begins == test.expected_begins, "compute pass begin count") ||
        !require(trace.pass_work == test.expected_work, "compute pass dependent work count") ||
        !require(trace.pass_ends == test.expected_ends, "compute pass end count") ||
        !require(trace.finishes == test.expected_finishes, "compute command finish count") ||
        !require(trace.submits == int(expect_success), "compute command submit count"))
    {
      return false;
    }
    accepted += int(expect_success);
  }

  if (!require(accepted == 1, "compute command transaction success census")) {
    return false;
  }
  std::puts("CONTRACT compute_command_transaction PASS cases=4 accepted=1 "
            "encoder_fail=closed pass_fail=closed command_fail=closed");
  return true;
}

struct BufferCommandTrace {
  bool encoder_success = true;
  bool encode_success = true;
  bool command_success = true;
  int encoder_creates = 0;
  int copies = 0;
  int finishes = 0;
  int submits = 0;
};

class BufferCommandBufferProbe {
 public:
  BufferCommandBufferProbe() = default;
  explicit BufferCommandBufferProbe(const bool valid) : valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

 private:
  bool valid_ = false;
};

class BufferCommandEncoderProbe {
 public:
  BufferCommandEncoderProbe() = default;
  BufferCommandEncoderProbe(BufferCommandTrace *trace, const bool valid)
      : trace_(trace), valid_(valid)
  {
  }

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  void CopyBufferToBuffer()
  {
    trace_->copies++;
  }

  BufferCommandBufferProbe Finish()
  {
    trace_->finishes++;
    return BufferCommandBufferProbe(trace_->command_success);
  }

 private:
  BufferCommandTrace *trace_ = nullptr;
  bool valid_ = false;
};

class BufferCommandDeviceProbe {
 public:
  explicit BufferCommandDeviceProbe(BufferCommandTrace &trace) : trace_(&trace) {}

  BufferCommandEncoderProbe CreateCommandEncoder() const
  {
    trace_->encoder_creates++;
    return BufferCommandEncoderProbe(trace_, trace_->encoder_success);
  }

 private:
  BufferCommandTrace *trace_ = nullptr;
};

class BufferCommandQueueProbe {
 public:
  explicit BufferCommandQueueProbe(BufferCommandTrace &trace) : trace_(&trace) {}

  void Submit(const size_t count, const BufferCommandBufferProbe *command_buffer) const
  {
    if (count == 1 && command_buffer != nullptr && !(*command_buffer == nullptr)) {
      trace_->submits++;
    }
  }

 private:
  BufferCommandTrace *trace_ = nullptr;
};

bool buffer_command_transaction_contract()
{
  struct FailureCase {
    bool encoder_success;
    bool encode_success;
    bool command_success;
    int expected_copies;
    int expected_finishes;
  };
  constexpr std::array<FailureCase, 4> cases = {{{false, true, true, 0, 0},
                                                 {true, false, true, 1, 0},
                                                 {true, true, false, 1, 1},
                                                 {true, true, true, 1, 1}}};

  int accepted = 0;
  for (const FailureCase &test : cases) {
    BufferCommandTrace trace;
    trace.encoder_success = test.encoder_success;
    trace.encode_success = test.encode_success;
    trace.command_success = test.command_success;
    const BufferCommandDeviceProbe device(trace);
    const BufferCommandQueueProbe queue(trace);

    const bool result = bw::command_encode_submit_if_valid(
        device, queue, [&](auto &encoder) {
          encoder.CopyBufferToBuffer();
          return trace.encode_success;
        });
    const bool expect_success =
        test.encoder_success && test.encode_success && test.command_success;
    if (!require(result == expect_success, "buffer command transaction result") ||
        !require(trace.encoder_creates == 1, "buffer command encoder creation count") ||
        !require(trace.copies == test.expected_copies, "buffer command copy count") ||
        !require(trace.finishes == test.expected_finishes, "buffer command finish count") ||
        !require(trace.submits == int(expect_success), "buffer command submit count"))
    {
      return false;
    }
    accepted += int(expect_success);
  }

  if (!require(accepted == 1, "buffer command transaction success census")) {
    return false;
  }
  std::puts("CONTRACT buffer_command_transaction PASS cases=4 accepted=1 "
            "encoder_fail=closed encode_fail=discarded command_fail=closed");
  return true;
}

wgpu::VertexFormat expected_32bit_format(const blender::GPUVertCompType component,
                                         const int component_len)
{
  using VF = wgpu::VertexFormat;
  if (component == blender::GPU_COMP_F32) {
    constexpr std::array<VF, 4> formats = {
        VF::Float32, VF::Float32x2, VF::Float32x3, VF::Float32x4};
    return formats[size_t(component_len - 1)];
  }
  if (component == blender::GPU_COMP_I32) {
    constexpr std::array<VF, 4> formats = {
        VF::Sint32, VF::Sint32x2, VF::Sint32x3, VF::Sint32x4};
    return formats[size_t(component_len - 1)];
  }
  constexpr std::array<VF, 4> formats = {
      VF::Uint32, VF::Uint32x2, VF::Uint32x3, VF::Uint32x4};
  return formats[size_t(component_len - 1)];
}

bool format_32bit_contract()
{
  constexpr std::array components = {
      blender::GPU_COMP_F32, blender::GPU_COMP_I32, blender::GPU_COMP_U32};
  constexpr std::array fetch_modes = {blender::GPU_FETCH_FLOAT,
                                      blender::GPU_FETCH_INT,
                                      blender::GPU_FETCH_INT_TO_FLOAT_UNIT};
  size_t cases = 0;
  for (const blender::GPUVertCompType component : components) {
    for (int component_len = 1; component_len <= 4; component_len++) {
      for (const blender::GPUVertFetchMode fetch : fetch_modes) {
        if (!require(bw::to_wgpu_vertex_format(component, component_len, fetch) ==
                         expected_32bit_format(component, component_len),
                     "32-bit vertex format mapping"))
        {
          return false;
        }
        cases++;
      }
    }
  }
  if (!require(cases == 36, "32-bit vertex format census")) {
    return false;
  }
  std::puts("CONTRACT format_32bit PASS cases=36");
  return true;
}

wgpu::VertexFormat expected_subword_format(const blender::GPUVertCompType component,
                                           const int component_len,
                                           const bool normalized)
{
  using VF = wgpu::VertexFormat;
  const bool pair = component_len <= 2;
  switch (component) {
    case blender::GPU_COMP_I8:
      return normalized ? (pair ? VF::Snorm8x2 : VF::Snorm8x4) :
                          (pair ? VF::Sint8x2 : VF::Sint8x4);
    case blender::GPU_COMP_U8:
      return normalized ? (pair ? VF::Unorm8x2 : VF::Unorm8x4) :
                          (pair ? VF::Uint8x2 : VF::Uint8x4);
    case blender::GPU_COMP_I16:
      return normalized ? (pair ? VF::Snorm16x2 : VF::Snorm16x4) :
                          (pair ? VF::Sint16x2 : VF::Sint16x4);
    case blender::GPU_COMP_U16:
      return normalized ? (pair ? VF::Unorm16x2 : VF::Unorm16x4) :
                          (pair ? VF::Uint16x2 : VF::Uint16x4);
    default:
      return VF::Float32x4;
  }
}

bool format_subword_contract()
{
  constexpr std::array components = {blender::GPU_COMP_I8,
                                     blender::GPU_COMP_U8,
                                     blender::GPU_COMP_I16,
                                     blender::GPU_COMP_U16};
  constexpr std::array fetch_modes = {blender::GPU_FETCH_FLOAT,
                                      blender::GPU_FETCH_INT,
                                      blender::GPU_FETCH_INT_TO_FLOAT_UNIT};
  size_t cases = 0;
  for (const blender::GPUVertCompType component : components) {
    for (int component_len = 1; component_len <= 4; component_len++) {
      for (const blender::GPUVertFetchMode fetch : fetch_modes) {
        const bool normalized = fetch == blender::GPU_FETCH_INT_TO_FLOAT_UNIT;
        if (!require(bw::to_wgpu_vertex_format(component, component_len, fetch) ==
                         expected_subword_format(component, component_len, normalized),
                     "subword vertex format mapping"))
        {
          return false;
        }
        cases++;
      }
    }
  }
  if (!require(cases == 48, "subword vertex format census")) {
    return false;
  }
  std::puts("CONTRACT format_subword PASS cases=48");
  return true;
}

bool format_i10_contract()
{
  constexpr std::array fetch_modes = {blender::GPU_FETCH_FLOAT,
                                      blender::GPU_FETCH_INT,
                                      blender::GPU_FETCH_INT_TO_FLOAT_UNIT};
  size_t cases = 0;
  size_t signed_cases = 0;
  for (int component_len = 1; component_len <= 4; component_len++) {
    for (const blender::GPUVertFetchMode fetch : fetch_modes) {
      const bool normalized = fetch == blender::GPU_FETCH_INT_TO_FLOAT_UNIT;
      const wgpu::VertexFormat expected = normalized ? wgpu::VertexFormat::Snorm8x4 :
                                                       wgpu::VertexFormat::Unorm10_10_10_2;
      if (!require(bw::to_wgpu_vertex_format(blender::GPU_COMP_I10, component_len, fetch) ==
                       expected,
                   "signed I10 vertex format mapping"))
      {
        return false;
      }
      cases++;
      signed_cases += normalized ? 1 : 0;
    }
  }
  if (!require(cases == 12, "I10 vertex format census") ||
      !require(signed_cases == 4, "normalized I10 census"))
  {
    return false;
  }
  std::puts("CONTRACT format_i10 PASS cases=12 normalized=4");
  return true;
}

bool dummy_vertex_contract()
{
  using T = blender::gpu::shader::Type;
  using VF = wgpu::VertexFormat;
  struct Expected {
    T type;
    VF format;
  };
  constexpr std::array<Expected, 32> expected = {{
      {T::float_t, VF::Float32},
      {T::float2_t, VF::Float32x2},
      {T::float3_t, VF::Float32x3},
      {T::float4_t, VF::Float32x4},
      {T::float3x3_t, VF::Float32x4},
      {T::float4x4_t, VF::Float32x4},
      {T::uint_t, VF::Uint32},
      {T::uint2_t, VF::Uint32x2},
      {T::uint3_t, VF::Uint32x3},
      {T::uint4_t, VF::Uint32x4},
      {T::int_t, VF::Sint32},
      {T::int2_t, VF::Sint32x2},
      {T::int3_t, VF::Sint32x3},
      {T::int4_t, VF::Sint32x4},
      {T::bool_t, VF::Uint32},
      {T::float3_10_10_10_2_t, VF::Float32x3},
      {T::uchar_t, VF::Uint32},
      {T::uchar2_t, VF::Uint32x2},
      {T::uchar3_t, VF::Uint32x3},
      {T::uchar4_t, VF::Uint32x4},
      {T::char_t, VF::Sint32},
      {T::char2_t, VF::Sint32x2},
      {T::char3_t, VF::Sint32x3},
      {T::char4_t, VF::Sint32x4},
      {T::ushort_t, VF::Uint32},
      {T::ushort2_t, VF::Uint32x2},
      {T::ushort3_t, VF::Uint32x3},
      {T::ushort4_t, VF::Uint32x4},
      {T::short_t, VF::Sint32},
      {T::short2_t, VF::Sint32x2},
      {T::short3_t, VF::Sint32x3},
      {T::short4_t, VF::Sint32x4},
  }};

  for (size_t index = 0; index < expected.size(); index++) {
    const uint32_t location = uint32_t(index % 16);
    const bw::VertexBinding binding =
        bw::dummy_vertex_binding(location, uint8_t(expected[index].type));
    if (!require(binding.vbo_index == -1 && binding.is_dummy,
                 "dummy source identity") ||
        !require(binding.buffer_offset == 0, "dummy buffer offset") ||
        !require(binding.array_stride == 0, "dummy zero stride") ||
        !require(binding.step_mode == wgpu::VertexStepMode::Vertex,
                 "dummy vertex step mode") ||
        !require(binding.attributes.size() == 1, "dummy attribute count") ||
        !require(binding.attributes[0].format == expected[index].format,
                 "dummy attribute format") ||
        !require(binding.attributes[0].offset == 0, "dummy attribute offset") ||
        !require(binding.attributes[0].shaderLocation == location,
                 "dummy shader location"))
    {
      return false;
    }
  }

  std::puts("CONTRACT dummy_vertex PASS cases=32 stride=0 step=vertex");
  return true;
}

bool shader_lifetime_cache_contract()
{
  /* Reproduce allocator address reuse without constructing a device-backed shader:
   * the render-pipeline hash must distinguish successive lifetimes at one address. */
  auto *reused_address =
      reinterpret_cast<blender::gpu::WGPUShader *>(uintptr_t{0x1000});
  constexpr uint64_t identity_count = 4096;
  const auto identity_hash = [](const bw::PipelineInfo &info) {
    uint64_t hash = 1469598103934665603ull;
    bw::hash_shader_identity(hash, info.shader, info.shader_cache_identity);
    return hash;
  };
  std::unordered_set<uint64_t> hashes;
  hashes.reserve(identity_count);
  for (uint64_t identity = 1; identity <= identity_count; identity++) {
    const bw::PipelineInfo info(reused_address, identity);
    hashes.insert(identity_hash(info));
  }

  const bw::PipelineInfo first(reused_address, 1);
  const bw::PipelineInfo same_lifetime(reused_address, 1);
  const bw::PipelineInfo replacement(reused_address, 2);
  if (!require(identity_hash(first) == identity_hash(same_lifetime),
               "same shader lifetime cache identity") ||
      !require(identity_hash(first) != identity_hash(replacement),
               "reused shader address cache separation") ||
      !require(hashes.size() == identity_count, "shader lifetime hash census"))
  {
    return false;
  }

  std::puts("CONTRACT shader_lifetime_cache PASS cases=4096 unique=4096");
  return true;
}

bool vertex_alias_cache_key_contract()
{
  /* Attribute aliases participate in shader-location matching. Distinct valid alias
   * sequences must therefore remain distinct in the render-pipeline cache key, even
   * when their bytes concatenate to the same undelimited string. */
  blender::GPUVertFormat split_after_first{};
  blender::GPU_vertformat_clear(&split_after_first);
  blender::GPU_vertformat_attr_add(
      &split_after_first, "a", blender::gpu::VertAttrType::SFLOAT_32);
  blender::GPU_vertformat_alias_add(&split_after_first, "bc");
  split_after_first.pack();

  blender::GPUVertFormat split_after_second{};
  blender::GPU_vertformat_clear(&split_after_second);
  blender::GPU_vertformat_attr_add(
      &split_after_second, "ab", blender::gpu::VertAttrType::SFLOAT_32);
  blender::GPU_vertformat_alias_add(&split_after_second, "c");
  split_after_second.pack();

  auto *shader = reinterpret_cast<blender::gpu::WGPUShader *>(uintptr_t{0x2000});
  bw::PipelineInfo first(shader, 1);
  first.vertex_formats[0] = &split_after_first;
  first.vertex_lens[0] = 1;
  first.vertex_formats_len = 1;
  bw::PipelineInfo second(shader, 1);
  second.vertex_formats[0] = &split_after_second;
  second.vertex_lens[0] = 1;
  second.vertex_formats_len = 1;

  const blender::GPUVertAttr &first_attr = split_after_first.attrs[0];
  const blender::GPUVertAttr &second_attr = split_after_second.attrs[0];
  const char *first_name = blender::GPU_vertformat_attr_name_get(
      &split_after_first, &first_attr, 0);
  const char *first_alias = blender::GPU_vertformat_attr_name_get(
      &split_after_first, &first_attr, 1);
  const char *second_name = blender::GPU_vertformat_attr_name_get(
      &split_after_second, &second_attr, 0);
  const char *second_alias = blender::GPU_vertformat_attr_name_get(
      &split_after_second, &second_attr, 1);
  if (!require(split_after_first.attrs[0].name_len == 2 &&
                   split_after_second.attrs[0].name_len == 2,
               "vertex alias-list census") ||
      !require(first_attr.type.format == second_attr.type.format &&
                   first_attr.offset == second_attr.offset &&
                   split_after_first.stride == split_after_second.stride,
               "vertex alias layouts otherwise match") ||
      !require(std::strcmp(first_name, "a") == 0 && std::strcmp(first_alias, "bc") == 0 &&
                   std::strcmp(second_name, "ab") == 0 && std::strcmp(second_alias, "c") == 0,
               "vertex alias collision inputs") ||
      !require(bw::pipeline_hash(first) != bw::pipeline_hash(second),
               "vertex alias-list cache separation"))
  {
    return false;
  }

  std::puts("CONTRACT vertex_alias_cache_key PASS cases=2 aliases=4 unique=2");
  return true;
}

}  // namespace

int main()
{
  if (!primitive_topology_contract() || !strip_index_format_contract() ||
      !multiview_uniform_allocation_contract() ||
      !transient_handle_publication_contract() ||
      !vertex_buffer_handle_resolution_contract() ||
      !cache_handle_publication_contract() ||
      !compute_pipeline_cache_publication_contract() ||
      !indirect_draw_span_contract() || !direct_draw_plan_contract() ||
      !viewport_scissor_plan_contract() || !window_viewport_scissor_plan_contract() ||
      !offscreen_viewport_scissor_plan_contract() ||
      !compute_dispatch_range_contract() ||
      !compute_command_transaction_contract() ||
      !buffer_command_transaction_contract() ||
      !format_32bit_contract() ||
      !format_subword_contract() || !format_i10_contract() || !dummy_vertex_contract() ||
      !shader_lifetime_cache_contract() || !vertex_alias_cache_key_contract())
  {
    return 1;
  }
  std::puts(
      "INTEGRATED_PIPELINE_PASS contracts=21 primitives=11 strip_cases=33 "
      "multiview_allocations=2 indirect_spans=19 direct_draws=16 viewport_scissors=28 "
      "window_rects=32 offscreen_rects=21 compute_direct=15 "
      "compute_indirect=13 compute_command_cases=4 buffer_command_cases=4 formats=96 i10=12 "
      "dummy=32 transient_publications=2 vertex_binding_resolutions=3 cache_publications=2 "
      "compute_cache_publications=2 "
      "shader_lifetimes=4096 alias_keys=2");
  return 0;
}
