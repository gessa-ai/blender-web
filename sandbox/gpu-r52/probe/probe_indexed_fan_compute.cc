// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

#include "webgpu/webgpu_cpp.h"

namespace {

std::string to_string(wgpu::StringView value)
{
  if (value.data == nullptr) {
    return {};
  }
  return value.length == WGPU_STRLEN ? std::string(value.data) :
                                      std::string(value.data, value.length);
}

wgpu::Device make_device(const wgpu::Instance &instance, const wgpu::Adapter &adapter)
{
  wgpu::Device result;
  wgpu::DeviceDescriptor descriptor = {};
  descriptor.SetUncapturedErrorCallback(
      [](const wgpu::Device &, wgpu::ErrorType, wgpu::StringView message) {
        std::cerr << "uncaptured: " << to_string(message) << "\n";
      });
  instance.WaitAny(
      adapter.RequestDevice(
          &descriptor,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestDeviceStatus status, wgpu::Device device, wgpu::StringView message) {
            if (status == wgpu::RequestDeviceStatus::Success) {
              result = std::move(device);
            }
            else {
              std::cerr << "RequestDevice failed: " << to_string(message) << "\n";
            }
          }),
      UINT64_MAX);
  return result;
}

const char *compute_source = R"(
struct Params { first : u32, count : u32, restart : u32, max_count : u32 }
@group(0) @binding(0) var<storage, read> source_indices : array<u32>;
@group(0) @binding(1) var<storage, read_write> output_indices : array<u32>;
@group(0) @binding(2) var<uniform> params : Params;
fn load_index(position : u32) -> u32 {
  if (params.restart == 0xffffu) {
    let packed = source_indices[position >> 1u];
    return select(packed & 0xffffu, packed >> 16u, (position & 1u) != 0u);
  }
  return source_indices[position];
}
@compute @workgroup_size(1)
fn main() {
  var output_count = 0u;
  var fan_count = 0u;
  var fan_first = 0u;
  var fan_previous = 0u;
  for (var i = 0u; i < params.count; i++) {
    let index = load_index(params.first + i);
    if (index == params.restart) { fan_count = 0u; }
    else if (fan_count == 0u) { fan_first = index; fan_count = 1u; }
    else if (fan_count == 1u) { fan_previous = index; fan_count = 2u; }
    else {
      output_indices[output_count] = fan_first;
      output_indices[output_count + 1u] = fan_previous;
      output_indices[output_count + 2u] = index;
      output_indices[output_count + 3u] = 0xffffffffu;
      output_count += 4u;
      fan_previous = index;
      fan_count += 1u;
    }
  }
  while (output_count < params.max_count) {
    output_indices[output_count] = 0xffffffffu;
    output_count += 1u;
  }
}
)";

bool run_case(const wgpu::Instance &instance,
              const wgpu::Device &device,
              const wgpu::ComputePipeline &pipeline,
              const wgpu::RenderPipeline &render_pipeline,
              const wgpu::Buffer &vertex_buffer,
              const std::vector<uint32_t> &source,
              const uint32_t restart,
              const std::vector<uint32_t> &expected)
{
  const uint32_t params[4] = {1, 8, restart, (8 - 2) * 4};
  const uint32_t max_output_count = params[3];
  wgpu::BufferDescriptor source_descriptor = {};
  source_descriptor.size = source.size() * sizeof(uint32_t);
  source_descriptor.usage = wgpu::BufferUsage::Storage | wgpu::BufferUsage::CopyDst;
  wgpu::Buffer source_buffer = device.CreateBuffer(&source_descriptor);
  device.GetQueue().WriteBuffer(source_buffer, 0, source.data(), source_descriptor.size);
  wgpu::BufferDescriptor output_descriptor = {};
  output_descriptor.size = max_output_count * sizeof(uint32_t);
  output_descriptor.usage = wgpu::BufferUsage::Storage | wgpu::BufferUsage::Index |
                            wgpu::BufferUsage::CopySrc;
  wgpu::Buffer output_buffer = device.CreateBuffer(&output_descriptor);
  wgpu::BufferDescriptor params_descriptor = {};
  params_descriptor.size = sizeof(params);
  params_descriptor.usage = wgpu::BufferUsage::Uniform | wgpu::BufferUsage::CopyDst;
  wgpu::Buffer params_buffer = device.CreateBuffer(&params_descriptor);
  device.GetQueue().WriteBuffer(params_buffer, 0, params, sizeof(params));
  wgpu::BufferDescriptor readback_descriptor = {};
  readback_descriptor.size = output_descriptor.size;
  readback_descriptor.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
  wgpu::Buffer readback = device.CreateBuffer(&readback_descriptor);
  wgpu::TextureDescriptor texture_descriptor = {};
  texture_descriptor.size = {16, 16, 1};
  texture_descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
  texture_descriptor.usage = wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::CopySrc;
  wgpu::Texture texture = device.CreateTexture(&texture_descriptor);
  wgpu::BufferDescriptor pixel_readback_descriptor = {};
  pixel_readback_descriptor.size = 256 * 16;
  pixel_readback_descriptor.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
  wgpu::Buffer pixel_readback = device.CreateBuffer(&pixel_readback_descriptor);

  wgpu::BindGroupEntry entries[3] = {};
  entries[0].binding = 0;
  entries[0].buffer = source_buffer;
  entries[0].size = source_descriptor.size;
  entries[1].binding = 1;
  entries[1].buffer = output_buffer;
  entries[1].size = output_descriptor.size;
  entries[2].binding = 2;
  entries[2].buffer = params_buffer;
  entries[2].size = sizeof(params);
  wgpu::BindGroupDescriptor group_descriptor = {};
  group_descriptor.layout = pipeline.GetBindGroupLayout(0);
  group_descriptor.entryCount = 3;
  group_descriptor.entries = entries;
  wgpu::BindGroup group = device.CreateBindGroup(&group_descriptor);

  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::CommandEncoder encoder = device.CreateCommandEncoder();
  wgpu::ComputePassEncoder pass = encoder.BeginComputePass();
  pass.SetPipeline(pipeline);
  pass.SetBindGroup(0, group);
  pass.DispatchWorkgroups(1);
  pass.End();

  wgpu::RenderPassColorAttachment attachment = {};
  attachment.view = texture.CreateView();
  attachment.loadOp = wgpu::LoadOp::Clear;
  attachment.storeOp = wgpu::StoreOp::Store;
  attachment.clearValue = {0.0, 0.0, 0.0, 0.0};
  wgpu::RenderPassDescriptor render_pass_descriptor = {};
  render_pass_descriptor.colorAttachmentCount = 1;
  render_pass_descriptor.colorAttachments = &attachment;
  wgpu::RenderPassEncoder render_pass = encoder.BeginRenderPass(&render_pass_descriptor);
  render_pass.SetPipeline(render_pipeline);
  render_pass.SetVertexBuffer(0, vertex_buffer);
  render_pass.SetIndexBuffer(output_buffer, wgpu::IndexFormat::Uint32);
  render_pass.DrawIndexed(max_output_count);
  render_pass.End();

  encoder.CopyBufferToBuffer(output_buffer, 0, readback, 0, output_descriptor.size);
  wgpu::TexelCopyTextureInfo pixel_source = {};
  pixel_source.texture = texture;
  wgpu::TexelCopyBufferInfo pixel_destination = {};
  pixel_destination.buffer = pixel_readback;
  pixel_destination.layout.bytesPerRow = 256;
  pixel_destination.layout.rowsPerImage = 16;
  wgpu::Extent3D pixel_size = {16, 16, 1};
  encoder.CopyTextureToBuffer(&pixel_source, &pixel_destination, &pixel_size);
  wgpu::CommandBuffer command_buffer = encoder.Finish();
  device.GetQueue().Submit(1, &command_buffer);
  bool validation_ok = true;
  instance.WaitAny(
      device.PopErrorScope(
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView message) {
            if (type != wgpu::ErrorType::NoError) {
              validation_ok = false;
              std::cerr << "validation: " << to_string(message) << "\n";
            }
          }),
      UINT64_MAX);
  bool mapped = false;
  instance.WaitAny(
      readback.MapAsync(
          wgpu::MapMode::Read,
          0,
          readback_descriptor.size,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::MapAsyncStatus status, wgpu::StringView) {
            mapped = status == wgpu::MapAsyncStatus::Success;
          }),
      UINT64_MAX);
  if (!validation_ok || !mapped) {
    return false;
  }
  const void *bytes = readback.GetConstMappedRange(0, readback_descriptor.size);
  const bool indices_exact = std::memcmp(bytes, expected.data(), readback_descriptor.size) == 0;
  readback.Unmap();
  bool pixels_mapped = false;
  instance.WaitAny(
      pixel_readback.MapAsync(
          wgpu::MapMode::Read,
          0,
          pixel_readback_descriptor.size,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::MapAsyncStatus status, wgpu::StringView) {
            pixels_mapped = status == wgpu::MapAsyncStatus::Success;
          }),
      UINT64_MAX);
  if (!pixels_mapped) {
    return false;
  }
  const uint8_t *pixels = static_cast<const uint8_t *>(
      pixel_readback.GetConstMappedRange(0, pixel_readback_descriptor.size));
  uint32_t red_pixels = 0;
  for (uint32_t y = 0; y < 16; y++) {
    for (uint32_t x = 0; x < 16; x++) {
      const uint8_t *pixel = pixels + y * 256 + x * 4;
      red_pixels += pixel[0] == 255 && pixel[1] == 0 && pixel[2] == 0 && pixel[3] == 255;
    }
  }
  pixel_readback.Unmap();
  return indices_exact && red_pixels >= 60;
}

}  // namespace

int main()
{
  wgpu::InstanceDescriptor instance_descriptor = {};
  static constexpr auto timed_wait = wgpu::InstanceFeatureName::TimedWaitAny;
  instance_descriptor.requiredFeatureCount = 1;
  instance_descriptor.requiredFeatures = &timed_wait;
  wgpu::Instance instance = wgpu::CreateInstance(&instance_descriptor);
  wgpu::RequestAdapterOptions options = {};
  options.backendType = wgpu::BackendType::Metal;
  options.featureLevel = wgpu::FeatureLevel::Core;
  wgpu::Adapter adapter;
  instance.WaitAny(
      instance.RequestAdapter(
          &options,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestAdapterStatus status, wgpu::Adapter result, wgpu::StringView message) {
            if (status == wgpu::RequestAdapterStatus::Success) {
              adapter = std::move(result);
            }
            else {
              std::cerr << "RequestAdapter failed: " << to_string(message) << "\n";
            }
          }),
      UINT64_MAX);
  wgpu::Device device = make_device(instance, adapter);
  wgpu::ShaderSourceWGSL wgsl = {};
  wgsl.code = compute_source;
  wgpu::ShaderModuleDescriptor module_descriptor = {};
  module_descriptor.nextInChain = &wgsl;
  wgpu::ShaderModule module = device.CreateShaderModule(&module_descriptor);
  wgpu::ComputePipelineDescriptor pipeline_descriptor = {};
  pipeline_descriptor.compute.module = module;
  pipeline_descriptor.compute.entryPoint = "main";
  wgpu::ComputePipeline pipeline = device.CreateComputePipeline(&pipeline_descriptor);

  static constexpr const char *render_source = R"(
struct VertexOut { @builtin(position) position : vec4f }
@vertex fn vs(@location(0) position : vec2f) -> VertexOut {
  var out : VertexOut;
  out.position = vec4f(position, 0.0, 1.0);
  return out;
}
@fragment fn fs() -> @location(0) vec4f { return vec4f(1.0, 0.0, 0.0, 1.0); }
)";
  wgpu::ShaderSourceWGSL render_wgsl = {};
  render_wgsl.code = render_source;
  wgpu::ShaderModuleDescriptor render_module_descriptor = {};
  render_module_descriptor.nextInChain = &render_wgsl;
  wgpu::ShaderModule render_module = device.CreateShaderModule(&render_module_descriptor);
  wgpu::VertexAttribute attribute = {};
  attribute.format = wgpu::VertexFormat::Float32x2;
  attribute.shaderLocation = 0;
  wgpu::VertexBufferLayout vertex_layout = {};
  vertex_layout.arrayStride = 2 * sizeof(float);
  vertex_layout.attributeCount = 1;
  vertex_layout.attributes = &attribute;
  wgpu::ColorTargetState color_target = {};
  color_target.format = wgpu::TextureFormat::RGBA8Unorm;
  color_target.writeMask = wgpu::ColorWriteMask::All;
  wgpu::FragmentState fragment = {};
  fragment.module = render_module;
  fragment.entryPoint = "fs";
  fragment.targetCount = 1;
  fragment.targets = &color_target;
  wgpu::RenderPipelineDescriptor render_pipeline_descriptor = {};
  render_pipeline_descriptor.vertex.module = render_module;
  render_pipeline_descriptor.vertex.entryPoint = "vs";
  render_pipeline_descriptor.vertex.bufferCount = 1;
  render_pipeline_descriptor.vertex.buffers = &vertex_layout;
  render_pipeline_descriptor.primitive.topology = wgpu::PrimitiveTopology::TriangleStrip;
  render_pipeline_descriptor.primitive.stripIndexFormat = wgpu::IndexFormat::Uint32;
  render_pipeline_descriptor.fragment = &fragment;
  wgpu::RenderPipeline render_pipeline = device.CreateRenderPipeline(&render_pipeline_descriptor);
  const float positions[14] = {-0.9f,
                               -0.8f,
                               -0.1f,
                               -0.8f,
                               -0.5f,
                               0.8f,
                               0.5f,
                               0.0f,
                               0.1f,
                               -0.8f,
                               0.9f,
                               -0.8f,
                               0.9f,
                               0.8f};
  wgpu::BufferDescriptor vertex_descriptor = {};
  vertex_descriptor.size = sizeof(positions);
  vertex_descriptor.usage = wgpu::BufferUsage::Vertex | wgpu::BufferUsage::CopyDst;
  wgpu::Buffer vertex_buffer = device.CreateBuffer(&vertex_descriptor);
  device.GetQueue().WriteBuffer(vertex_buffer, 0, positions, sizeof(positions));

  const std::vector<uint16_t> u16 = {900, 0, 1, 2, 0xffff, 3, 4, 5, 6, 901};
  std::vector<uint32_t> packed_u16((u16.size() + 1) / 2, 0);
  for (size_t i = 0; i < u16.size(); i++) {
    packed_u16[i / 2] |= uint32_t(u16[i]) << ((i & 1) * 16);
  }
  const std::vector<uint32_t> expected_u16 = {0,
                                               1,
                                               2,
                                               0xffffffffu,
                                               3,
                                               4,
                                               5,
                                               0xffffffffu,
                                               3,
                                               5,
                                               6,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu};
  const bool u16_ok = run_case(instance,
                               device,
                               pipeline,
                               render_pipeline,
                               vertex_buffer,
                               packed_u16,
                               0xffff,
                               expected_u16);

  const std::vector<uint32_t> u32 = {900, 0, 1, 2, 0xffffffffu, 3, 4, 5, 6, 901};
  const std::vector<uint32_t> expected_u32 = {0,
                                               1,
                                               2,
                                               0xffffffffu,
                                               3,
                                               4,
                                               5,
                                               0xffffffffu,
                                               3,
                                               5,
                                               6,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu,
                                               0xffffffffu};
  const bool u32_ok = run_case(instance,
                               device,
                               pipeline,
                               render_pipeline,
                               vertex_buffer,
                               u32,
                               0xffffffffu,
                               expected_u32);

  std::cout << "Dawn packed-U16 compute + indexed strip draw exact 3 triangles: "
            << (u16_ok ? "OK" : "FAIL") << "\n";
  std::cout << "Dawn U32 compute + indexed strip draw exact 3 triangles: "
            << (u32_ok ? "OK" : "FAIL") << "\n";
  return u16_ok && u32_ok ? 0 : 1;
}
