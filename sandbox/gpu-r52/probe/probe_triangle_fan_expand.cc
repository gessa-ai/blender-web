// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

#include <array>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#include "webgpu/webgpu_cpp.h"

namespace {

struct Vertex {
  float position[2];
  uint32_t serial;
  float uv[2];
};

std::string to_string(wgpu::StringView value)
{
  if (value.data == nullptr) {
    return {};
  }
  return value.length == WGPU_STRLEN ? std::string(value.data) :
                                      std::string(value.data, value.length);
}

std::vector<uint32_t> fan_indices(const uint32_t vertex_first, const uint32_t vertex_len)
{
  std::vector<uint32_t> result;
  result.reserve((vertex_len - 2) * 3);
  for (uint32_t i = 1; i + 1 < vertex_len; i++) {
    result.push_back(vertex_first);
    result.push_back(vertex_first + i);
    result.push_back(vertex_first + i + 1);
  }
  return result;
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

}  // namespace

int main()
{
  const std::array<Vertex, 6> fan = {{{{0.0f, 0.0f}, 0, {0.5f, 0.5f}},
                                      {{-0.8f, -0.8f}, 1, {0.0f, 0.0f}},
                                      {{0.8f, -0.8f}, 2, {1.0f, 0.0f}},
                                      {{0.8f, 0.8f}, 3, {1.0f, 1.0f}},
                                      {{-0.8f, 0.8f}, 4, {0.0f, 1.0f}},
                                      {{-0.8f, -0.8f}, 5, {0.0f, 0.0f}}}};
  const std::vector<uint32_t> indices = fan_indices(0, fan.size());
  const std::array<uint32_t, 12> expected = {0, 1, 2, 0, 2, 3, 0, 3, 4, 0, 4, 5};
  bool mapping_ok = indices.size() == expected.size();
  for (size_t i = 0; mapping_ok && i < expected.size(); i++) {
    mapping_ok = indices[i] == expected[i] && fan[indices[i]].serial == expected[i];
  }
  std::cout << "CPU UInt32 fan order (0,i,i+1), original stride=" << sizeof(Vertex)
            << ": " << (mapping_ok ? "OK" : "FAIL") << "\n";
  if (!mapping_ok) {
    return 1;
  }

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
  device.PushErrorScope(wgpu::ErrorFilter::Validation);

  static constexpr const char *shader_source = R"(
struct VertexOut { @builtin(position) position : vec4f }
@vertex fn vs(@location(0) position : vec2f) -> VertexOut {
  var out : VertexOut;
  out.position = vec4f(position, 0.0, 1.0);
  return out;
}
@fragment fn fs() -> @location(0) vec4f { return vec4f(1.0, 0.0, 0.0, 1.0); }
)";
  wgpu::ShaderSourceWGSL wgsl = {};
  wgsl.code = shader_source;
  wgpu::ShaderModuleDescriptor module_descriptor = {};
  module_descriptor.nextInChain = &wgsl;
  wgpu::ShaderModule module = device.CreateShaderModule(&module_descriptor);

  wgpu::VertexAttribute attribute = {};
  attribute.format = wgpu::VertexFormat::Float32x2;
  attribute.offset = 0;
  attribute.shaderLocation = 0;
  wgpu::VertexBufferLayout buffer_layout = {};
  buffer_layout.arrayStride = sizeof(Vertex);
  buffer_layout.stepMode = wgpu::VertexStepMode::Vertex;
  buffer_layout.attributeCount = 1;
  buffer_layout.attributes = &attribute;
  wgpu::ColorTargetState color_target = {};
  color_target.format = wgpu::TextureFormat::RGBA8Unorm;
  color_target.writeMask = wgpu::ColorWriteMask::All;
  wgpu::FragmentState fragment = {};
  fragment.module = module;
  fragment.entryPoint = "fs";
  fragment.targetCount = 1;
  fragment.targets = &color_target;
  wgpu::RenderPipelineDescriptor pipeline_descriptor = {};
  pipeline_descriptor.vertex.module = module;
  pipeline_descriptor.vertex.entryPoint = "vs";
  pipeline_descriptor.vertex.bufferCount = 1;
  pipeline_descriptor.vertex.buffers = &buffer_layout;
  pipeline_descriptor.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
  pipeline_descriptor.fragment = &fragment;
  wgpu::RenderPipeline pipeline = device.CreateRenderPipeline(&pipeline_descriptor);

  wgpu::BufferDescriptor vertex_descriptor = {};
  vertex_descriptor.size = sizeof(fan);
  vertex_descriptor.usage = wgpu::BufferUsage::Vertex | wgpu::BufferUsage::CopyDst;
  wgpu::Buffer vertex_buffer = device.CreateBuffer(&vertex_descriptor);
  device.GetQueue().WriteBuffer(vertex_buffer, 0, fan.data(), sizeof(fan));
  wgpu::BufferDescriptor index_descriptor = {};
  index_descriptor.size = indices.size() * sizeof(uint32_t);
  index_descriptor.usage = wgpu::BufferUsage::Index | wgpu::BufferUsage::CopyDst;
  wgpu::Buffer index_buffer = device.CreateBuffer(&index_descriptor);
  device.GetQueue().WriteBuffer(index_buffer, 0, indices.data(), index_descriptor.size);

  wgpu::TextureDescriptor texture_descriptor = {};
  texture_descriptor.size = {16, 16, 1};
  texture_descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
  texture_descriptor.usage = wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::CopySrc;
  wgpu::Texture texture = device.CreateTexture(&texture_descriptor);
  wgpu::BufferDescriptor readback_descriptor = {};
  readback_descriptor.size = 256 * 16;
  readback_descriptor.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
  wgpu::Buffer readback = device.CreateBuffer(&readback_descriptor);

  wgpu::RenderPassColorAttachment attachment = {};
  attachment.view = texture.CreateView();
  attachment.loadOp = wgpu::LoadOp::Clear;
  attachment.storeOp = wgpu::StoreOp::Store;
  attachment.clearValue = {0.0, 0.0, 0.0, 0.0};
  wgpu::RenderPassDescriptor pass_descriptor = {};
  pass_descriptor.colorAttachmentCount = 1;
  pass_descriptor.colorAttachments = &attachment;
  wgpu::CommandEncoder encoder = device.CreateCommandEncoder();
  wgpu::RenderPassEncoder pass = encoder.BeginRenderPass(&pass_descriptor);
  pass.SetPipeline(pipeline);
  pass.SetVertexBuffer(0, vertex_buffer);
  pass.SetIndexBuffer(index_buffer, wgpu::IndexFormat::Uint32);
  pass.DrawIndexed(expected.size());
  pass.End();

  wgpu::TexelCopyTextureInfo copy_source = {};
  copy_source.texture = texture;
  wgpu::TexelCopyBufferInfo copy_destination = {};
  copy_destination.buffer = readback;
  copy_destination.layout.bytesPerRow = 256;
  copy_destination.layout.rowsPerImage = 16;
  wgpu::Extent3D copy_size = {16, 16, 1};
  encoder.CopyTextureToBuffer(&copy_source, &copy_destination, &copy_size);
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
          [&](wgpu::MapAsyncStatus status, wgpu::StringView message) {
            mapped = status == wgpu::MapAsyncStatus::Success;
            if (!mapped) {
              std::cerr << "MapAsync failed: " << to_string(message) << "\n";
            }
          }),
      UINT64_MAX);
  if (!validation_ok || !mapped) {
    return 2;
  }
  const uint8_t *pixels = static_cast<const uint8_t *>(
      readback.GetConstMappedRange(0, readback_descriptor.size));
  uint32_t red_pixels = 0;
  for (uint32_t y = 0; y < 16; y++) {
    for (uint32_t x = 0; x < 16; x++) {
      const uint8_t *pixel = pixels + y * 256 + x * 4;
      red_pixels += pixel[0] == 255 && pixel[1] == 0 && pixel[2] == 0 && pixel[3] == 255;
    }
  }
  readback.Unmap();
  const bool render_ok = red_pixels >= 140;
  std::cout << "Dawn TriangleList validation/readback red_pixels=" << red_pixels << ": "
            << (render_ok ? "OK" : "FAIL") << "\n";
  return render_ok ? 0 : 3;
}
