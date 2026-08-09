// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>

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

  wgpu::TextureDescriptor texture_descriptor = {};
  texture_descriptor.size = {4, 4, 4};
  texture_descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
  texture_descriptor.usage = wgpu::TextureUsage::StorageBinding | wgpu::TextureUsage::CopySrc;
  wgpu::Texture texture = device.CreateTexture(&texture_descriptor);

  wgpu::TextureViewDescriptor view_descriptor = {};
  view_descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
  view_descriptor.dimension = wgpu::TextureViewDimension::e2DArray;
  view_descriptor.baseArrayLayer = 2;
  view_descriptor.arrayLayerCount = 1;
  wgpu::TextureView view = texture.CreateView(&view_descriptor);

  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  static constexpr const char *source = R"(
@group(0) @binding(0) var out_tex : texture_storage_2d_array<rgba8unorm, write>;
@compute @workgroup_size(1)
fn cs() {
  textureStore(out_tex, vec2i(0, 0), 0, vec4f(1.0, 0.0, 0.0, 1.0));
  textureStore(out_tex, vec2i(0, 0), 1, vec4f(0.0, 1.0, 0.0, 1.0));
}
)";
  wgpu::ShaderSourceWGSL wgsl = {};
  wgsl.code = source;
  wgpu::ShaderModuleDescriptor module_descriptor = {};
  module_descriptor.nextInChain = &wgsl;
  wgpu::ShaderModule module = device.CreateShaderModule(&module_descriptor);

  wgpu::ComputePipelineDescriptor pipeline_descriptor = {};
  pipeline_descriptor.compute.module = module;
  pipeline_descriptor.compute.entryPoint = "cs";
  wgpu::ComputePipeline pipeline = device.CreateComputePipeline(&pipeline_descriptor);

  wgpu::BindGroupEntry entry = {};
  entry.binding = 0;
  entry.textureView = view;
  wgpu::BindGroupDescriptor group_descriptor = {};
  group_descriptor.layout = pipeline.GetBindGroupLayout(0);
  group_descriptor.entryCount = 1;
  group_descriptor.entries = &entry;
  wgpu::BindGroup group = device.CreateBindGroup(&group_descriptor);

  wgpu::BufferDescriptor buffer_descriptor = {};
  buffer_descriptor.size = 512;
  buffer_descriptor.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
  wgpu::Buffer staging = device.CreateBuffer(&buffer_descriptor);

  wgpu::CommandEncoder encoder = device.CreateCommandEncoder();
  wgpu::ComputePassEncoder pass = encoder.BeginComputePass();
  pass.SetPipeline(pipeline);
  pass.SetBindGroup(0, group);
  pass.DispatchWorkgroups(1);
  pass.End();

  wgpu::Extent3D one_pixel = {1, 1, 1};
  for (uint32_t index = 0; index < 2; index++) {
    wgpu::TexelCopyTextureInfo source_copy = {};
    source_copy.texture = texture;
    source_copy.origin = {0, 0, 2 + index};
    wgpu::TexelCopyBufferInfo destination = {};
    destination.buffer = staging;
    destination.layout.offset = index * 256;
    destination.layout.bytesPerRow = 256;
    destination.layout.rowsPerImage = 1;
    encoder.CopyTextureToBuffer(&source_copy, &destination, &one_pixel);
  }
  wgpu::CommandBuffer command_buffer = encoder.Finish();
  device.GetQueue().Submit(1, &command_buffer);

  bool validation_ok = true;
  wgpu::Future validation_future = device.PopErrorScope(
      wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView message) {
        if (type != wgpu::ErrorType::NoError) {
          validation_ok = false;
          std::cerr << "validation: " << to_string(message) << "\n";
        }
      });
  instance.WaitAny(validation_future, UINT64_MAX);
  if (!validation_ok) {
    return 3;
  }

  bool mapped = false;
  wgpu::Future map_future = staging.MapAsync(
      wgpu::MapMode::Read,
      0,
      512,
      wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::MapAsyncStatus status, wgpu::StringView message) {
        mapped = status == wgpu::MapAsyncStatus::Success;
        if (!mapped) {
          std::cerr << "MapAsync failed: " << to_string(message) << "\n";
        }
      });
  instance.WaitAny(map_future, UINT64_MAX);
  if (!mapped) {
    return 2;
  }

  const uint8_t *bytes = static_cast<const uint8_t *>(staging.GetConstMappedRange(0, 512));
  const uint8_t expected_layer2[4] = {255, 0, 0, 255};
  const uint8_t expected_layer3[4] = {0, 0, 0, 0};
  const bool layer2_red = std::memcmp(bytes, expected_layer2, 4) == 0;
  const bool layer3_untouched = std::memcmp(bytes + 256, expected_layer3, 4) == 0;

  std::cout << "view baseArrayLayer=2 arrayLayerCount=1 BGL/dispatch: "
            << ((validation_ok && group != nullptr) ? "OK" : "FAIL") << "\n";
  std::cout << "source layer 2 receives view-layer 0 write: " << (layer2_red ? "OK" : "FAIL")
            << "\n";
  std::cout << "source layer 3 rejects out-of-view layer 1 write: "
            << (layer3_untouched ? "OK" : "FAIL") << "\n";

  staging.Unmap();
  return validation_ok && group != nullptr && layer2_red && layer3_untouched ? 0 : 1;
}
