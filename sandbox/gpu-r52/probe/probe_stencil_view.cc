// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

#include <cstdint>
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
  static constexpr auto depth32_stencil8 = wgpu::FeatureName::Depth32FloatStencil8;
  descriptor.requiredFeatureCount = 1;
  descriptor.requiredFeatures = &depth32_stencil8;
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

bool bind_view(const wgpu::Instance &instance,
               const wgpu::Device &device,
               const wgpu::TextureView &view,
               wgpu::TextureSampleType sample_type,
               std::string &error)
{
  wgpu::BindGroupLayoutEntry layout_entry = {};
  layout_entry.binding = 0;
  layout_entry.visibility = wgpu::ShaderStage::Fragment;
  layout_entry.texture.sampleType = sample_type;
  layout_entry.texture.viewDimension = wgpu::TextureViewDimension::e2D;

  wgpu::BindGroupLayoutDescriptor layout_descriptor = {};
  layout_descriptor.entryCount = 1;
  layout_descriptor.entries = &layout_entry;
  wgpu::BindGroupLayout layout = device.CreateBindGroupLayout(&layout_descriptor);

  wgpu::BindGroupEntry entry = {};
  entry.binding = 0;
  entry.textureView = view;
  wgpu::BindGroupDescriptor descriptor = {};
  descriptor.layout = layout;
  descriptor.entryCount = 1;
  descriptor.entries = &entry;

  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::BindGroup group = device.CreateBindGroup(&descriptor);
  bool had_error = false;
  wgpu::Future future = device.PopErrorScope(
      wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView message) {
        if (type != wgpu::ErrorType::NoError) {
          had_error = true;
          error = to_string(message);
        }
      });
  instance.WaitAny(future, UINT64_MAX);
  return !had_error && group != nullptr;
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
  texture_descriptor.size = {4, 4, 1};
  texture_descriptor.format = wgpu::TextureFormat::Depth32FloatStencil8;
  texture_descriptor.usage = wgpu::TextureUsage::TextureBinding |
                             wgpu::TextureUsage::RenderAttachment;
  wgpu::Texture texture = device.CreateTexture(&texture_descriptor);

  wgpu::TextureViewDescriptor stencil_descriptor = {};
  stencil_descriptor.format = wgpu::TextureFormat::Stencil8;
  stencil_descriptor.dimension = wgpu::TextureViewDimension::e2D;
  stencil_descriptor.aspect = wgpu::TextureAspect::StencilOnly;
  wgpu::TextureView stencil_view = texture.CreateView(&stencil_descriptor);

  wgpu::TextureViewDescriptor depth_descriptor = {};
  depth_descriptor.format = wgpu::TextureFormat::Depth32Float;
  depth_descriptor.dimension = wgpu::TextureViewDimension::e2D;
  depth_descriptor.aspect = wgpu::TextureAspect::DepthOnly;
  wgpu::TextureView depth_view = texture.CreateView(&depth_descriptor);

  std::string stencil_error;
  const bool stencil_uint = bind_view(
      instance, device, stencil_view, wgpu::TextureSampleType::Uint, stencil_error);
  std::string depth_uint_error;
  const bool depth_uint = bind_view(
      instance, device, depth_view, wgpu::TextureSampleType::Uint, depth_uint_error);
  std::string depth_float_error;
  const bool depth_float = bind_view(
      instance, device, depth_view, wgpu::TextureSampleType::Depth, depth_float_error);

  std::cout << "StencilOnly Stencil8 -> Uint binding: " << (stencil_uint ? "OK" : "FAIL")
            << (stencil_uint ? "" : " <- " + stencil_error) << "\n";
  std::cout << "DepthOnly Depth32Float -> Uint binding control: "
            << (depth_uint ? "UNEXPECTED OK" : "EXPECTED FAIL")
            << (depth_uint ? "" : " <- " + depth_uint_error) << "\n";
  std::cout << "DepthOnly Depth32Float -> Depth binding: " << (depth_float ? "OK" : "FAIL")
            << (depth_float ? "" : " <- " + depth_float_error) << "\n";

  return (stencil_uint && !depth_uint && depth_float) ? 0 : 1;
}
