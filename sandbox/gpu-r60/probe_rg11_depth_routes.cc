// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r60 / patch 0143 pre-build Dawn probe.
//
// This deliberately creates a device WITHOUT RG11B10UfloatRenderable, even when
// the adapter exposes it. It proves that RG11B10Ufloat remains legal for raw
// copy/sampling usage and that adding RenderAttachment is rejected.
//
// It also exercises the exact descriptor shape used by WGPUContext's public
// selected-depth render bridge: 2D-array backing textures, relative mip 1,
// layer 1, a single-aspect sampled source view, and an all-aspect destination
// attachment. The source texture handle is released after its sampled view and
// bind group are created but before queue submission. Combined destinations are
// initialized with a stencil sentinel and copied back after the depth draw to
// prove the stencil Load/Store + Keep controls preserve it.

#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include "webgpu/webgpu_cpp.h"

namespace {

constexpr uint32_t kBaseSize = 8;
constexpr uint32_t kMip = 1;
constexpr uint32_t kLayer = 1;
constexpr uint32_t kMipSize = kBaseSize >> kMip;
constexpr float kSourceDepth = 0.25f;
constexpr float kDestinationDepth = 0.75f;
constexpr uint32_t kSourceStencil = 11;
constexpr uint32_t kDestinationStencil = 37;

std::string to_string(wgpu::StringView value)
{
  if (value.data == nullptr) {
    return {};
  }
  return value.length == WGPU_STRLEN ? std::string(value.data) :
                                      std::string(value.data, value.length);
}

const char *format_name(wgpu::TextureFormat format)
{
  switch (format) {
    case wgpu::TextureFormat::Depth16Unorm:
      return "Depth16Unorm";
    case wgpu::TextureFormat::Depth24Plus:
      return "Depth24Plus";
    case wgpu::TextureFormat::Depth24PlusStencil8:
      return "Depth24PlusStencil8";
    case wgpu::TextureFormat::Depth32Float:
      return "Depth32Float";
    case wgpu::TextureFormat::Depth32FloatStencil8:
      return "Depth32FloatStencil8";
    case wgpu::TextureFormat::RG11B10Ufloat:
      return "RG11B10Ufloat";
    default:
      return "unknown";
  }
}

bool is_combined(wgpu::TextureFormat format)
{
  return format == wgpu::TextureFormat::Depth24PlusStencil8 ||
         format == wgpu::TextureFormat::Depth32FloatStencil8;
}

wgpu::ShaderModule shader_module(const wgpu::Device &device, const char *source)
{
  wgpu::ShaderSourceWGSL wgsl = {};
  wgsl.code = source;
  wgpu::ShaderModuleDescriptor descriptor = {};
  descriptor.nextInChain = &wgsl;
  return device.CreateShaderModule(&descriptor);
}

bool pop_validation(const wgpu::Instance &instance,
                    const wgpu::Device &device,
                    const char *label,
                    std::string &error)
{
  bool valid = true;
  instance.WaitAny(
      device.PopErrorScope(
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView message) {
            if (type != wgpu::ErrorType::NoError) {
              valid = false;
              error = to_string(message);
            }
          }),
      UINT64_MAX);
  if (!valid) {
    std::cerr << "  validation[" << label << "]: " << error << "\n";
  }
  return valid;
}

wgpu::Adapter request_adapter(const wgpu::Instance &instance)
{
  wgpu::RequestAdapterOptions options = {};
  options.backendType = wgpu::BackendType::Metal;
  options.featureLevel = wgpu::FeatureLevel::Core;
  wgpu::Adapter adapter;
  instance.WaitAny(
      instance.RequestAdapter(
          &options,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestAdapterStatus status,
              wgpu::Adapter result,
              wgpu::StringView message) {
            if (status == wgpu::RequestAdapterStatus::Success) {
              adapter = std::move(result);
            }
            else {
              std::cerr << "RequestAdapter failed: " << to_string(message) << "\n";
            }
          }),
      UINT64_MAX);
  return adapter;
}

wgpu::Device make_feature_omission_device(const wgpu::Instance &instance,
                                          const wgpu::Adapter &adapter)
{
  std::vector<wgpu::FeatureName> requested;
  if (adapter.HasFeature(wgpu::FeatureName::Depth32FloatStencil8)) {
    requested.push_back(wgpu::FeatureName::Depth32FloatStencil8);
  }
  /* Binding probe invariant: never request RG11B10UfloatRenderable. */
  wgpu::DeviceDescriptor descriptor = {};
  descriptor.requiredFeatureCount = requested.size();
  descriptor.requiredFeatures = requested.empty() ? nullptr : requested.data();
  descriptor.SetUncapturedErrorCallback(
      [](const wgpu::Device &, wgpu::ErrorType type, wgpu::StringView message) {
        std::cerr << "uncaptured[" << int(type) << "]: " << to_string(message) << "\n";
      });
  wgpu::Device device;
  instance.WaitAny(
      adapter.RequestDevice(
          &descriptor,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestDeviceStatus status,
              wgpu::Device result,
              wgpu::StringView message) {
            if (status == wgpu::RequestDeviceStatus::Success) {
              device = std::move(result);
            }
            else {
              std::cerr << "RequestDevice failed: " << to_string(message) << "\n";
            }
          }),
      UINT64_MAX);
  return device;
}

bool try_rg11_texture(const wgpu::Instance &instance,
                      const wgpu::Device &device,
                      wgpu::TextureUsage usage,
                      std::string &error)
{
  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  wgpu::TextureDescriptor descriptor = {};
  descriptor.label = "r60-rg11-no-feature";
  descriptor.size = {4, 4, 1};
  descriptor.mipLevelCount = 1;
  descriptor.sampleCount = 1;
  descriptor.dimension = wgpu::TextureDimension::e2D;
  descriptor.format = wgpu::TextureFormat::RG11B10Ufloat;
  descriptor.usage = usage;
  wgpu::Texture texture = device.CreateTexture(&descriptor);
  const bool valid = pop_validation(instance, device, "RG11B10Ufloat", error);
  return valid && texture != nullptr;
}

wgpu::Texture make_depth_texture(const wgpu::Device &device,
                                 const char *label,
                                 wgpu::TextureFormat format,
                                 bool stencil_readback)
{
  wgpu::TextureDescriptor descriptor = {};
  descriptor.label = label;
  descriptor.size = {kBaseSize, kBaseSize, 3};
  descriptor.mipLevelCount = 3;
  descriptor.sampleCount = 1;
  descriptor.dimension = wgpu::TextureDimension::e2D;
  descriptor.format = format;
  descriptor.usage = wgpu::TextureUsage::TextureBinding |
                     wgpu::TextureUsage::RenderAttachment;
  if (stencil_readback) {
    descriptor.usage |= wgpu::TextureUsage::CopySrc;
  }
  return device.CreateTexture(&descriptor);
}

wgpu::TextureView make_depth_view(const wgpu::Texture &texture,
                                  wgpu::TextureFormat format,
                                  wgpu::TextureAspect aspect)
{
  wgpu::TextureViewDescriptor descriptor = {};
  descriptor.format = format;
  if (aspect == wgpu::TextureAspect::DepthOnly) {
    if (format == wgpu::TextureFormat::Depth32FloatStencil8) {
      descriptor.format = wgpu::TextureFormat::Depth32Float;
    }
    else if (format == wgpu::TextureFormat::Depth24PlusStencil8) {
      descriptor.format = wgpu::TextureFormat::Depth24Plus;
    }
  }
  descriptor.dimension = wgpu::TextureViewDimension::e2D;
  descriptor.baseMipLevel = kMip;
  descriptor.mipLevelCount = 1;
  descriptor.baseArrayLayer = kLayer;
  descriptor.arrayLayerCount = 1;
  descriptor.aspect = aspect;
  return texture.CreateView(&descriptor);
}

void encode_clear(const wgpu::CommandEncoder &encoder,
                  const wgpu::TextureView &view,
                  wgpu::TextureFormat format,
                  float depth,
                  uint32_t stencil)
{
  wgpu::RenderPassDepthStencilAttachment attachment = {};
  attachment.view = view;
  attachment.depthLoadOp = wgpu::LoadOp::Clear;
  attachment.depthStoreOp = wgpu::StoreOp::Store;
  attachment.depthClearValue = depth;
  if (is_combined(format)) {
    attachment.stencilLoadOp = wgpu::LoadOp::Clear;
    attachment.stencilStoreOp = wgpu::StoreOp::Store;
    attachment.stencilClearValue = stencil;
  }
  wgpu::RenderPassDescriptor descriptor = {};
  descriptor.depthStencilAttachment = &attachment;
  wgpu::RenderPassEncoder pass = encoder.BeginRenderPass(&descriptor);
  pass.End();
}

wgpu::RenderPipeline make_depth_blit_pipeline(const wgpu::Device &device,
                                              const wgpu::ShaderModule &module,
                                              wgpu::TextureFormat destination_format)
{
  wgpu::FragmentState fragment = {};
  fragment.module = module;
  fragment.entryPoint = "fs_main";
  wgpu::DepthStencilState depth_stencil = {};
  depth_stencil.format = destination_format;
  depth_stencil.depthWriteEnabled = wgpu::OptionalBool::True;
  depth_stencil.depthCompare = wgpu::CompareFunction::Always;
  if (is_combined(destination_format)) {
    depth_stencil.stencilFront.compare = wgpu::CompareFunction::Always;
    depth_stencil.stencilFront.failOp = wgpu::StencilOperation::Keep;
    depth_stencil.stencilFront.depthFailOp = wgpu::StencilOperation::Keep;
    depth_stencil.stencilFront.passOp = wgpu::StencilOperation::Keep;
    depth_stencil.stencilBack = depth_stencil.stencilFront;
    depth_stencil.stencilReadMask = 0;
    depth_stencil.stencilWriteMask = 0;
  }
  wgpu::RenderPipelineDescriptor descriptor = {};
  descriptor.layout = nullptr;
  descriptor.vertex.module = module;
  descriptor.vertex.entryPoint = "vs_main";
  descriptor.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
  descriptor.fragment = &fragment;
  descriptor.depthStencil = &depth_stencil;
  return device.CreateRenderPipeline(&descriptor);
}

bool map_float(const wgpu::Instance &instance, const wgpu::Buffer &buffer, float &value)
{
  bool mapped = false;
  instance.WaitAny(
      buffer.MapAsync(
          wgpu::MapMode::Read,
          0,
          sizeof(float),
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::MapAsyncStatus status, wgpu::StringView message) {
            mapped = status == wgpu::MapAsyncStatus::Success;
            if (!mapped) {
              std::cerr << "MapAsync(depth) failed: " << to_string(message) << "\n";
            }
          }),
      UINT64_MAX);
  if (!mapped) {
    return false;
  }
  std::memcpy(&value, buffer.GetConstMappedRange(0, sizeof(float)), sizeof(float));
  buffer.Unmap();
  return true;
}

bool map_stencil(const wgpu::Instance &instance,
                 const wgpu::Buffer &buffer,
                 uint8_t expected)
{
  constexpr uint64_t buffer_size = 256 * kMipSize;
  bool mapped = false;
  instance.WaitAny(
      buffer.MapAsync(
          wgpu::MapMode::Read,
          0,
          buffer_size,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::MapAsyncStatus status, wgpu::StringView message) {
            mapped = status == wgpu::MapAsyncStatus::Success;
            if (!mapped) {
              std::cerr << "MapAsync(stencil) failed: " << to_string(message) << "\n";
            }
          }),
      UINT64_MAX);
  if (!mapped) {
    return false;
  }
  const uint8_t *bytes = static_cast<const uint8_t *>(
      buffer.GetConstMappedRange(0, buffer_size));
  bool exact = true;
  for (uint32_t y = 0; y < kMipSize; y++) {
    for (uint32_t x = 0; x < kMipSize; x++) {
      exact &= bytes[y * 256 + x] == expected;
    }
  }
  buffer.Unmap();
  return exact;
}

struct DepthCase {
  wgpu::TextureFormat source;
  wgpu::TextureFormat destination;
};

bool run_depth_case(const wgpu::Instance &instance,
                    const wgpu::Device &device,
                    const DepthCase &test)
{
  const bool preserve_stencil = is_combined(test.destination);
  std::cout << "depth route " << format_name(test.source) << " -> "
            << format_name(test.destination) << " at mip=" << kMip
            << " layer=" << kLayer << "\n";
  device.PushErrorScope(wgpu::ErrorFilter::Validation);

  wgpu::Texture source = make_depth_texture(device, "r60-depth-source", test.source, false);
  wgpu::Texture destination = make_depth_texture(
      device, "r60-depth-destination", test.destination, preserve_stencil);
  wgpu::TextureView source_attachment = make_depth_view(
      source, test.source, wgpu::TextureAspect::All);
  wgpu::TextureView destination_attachment = make_depth_view(
      destination, test.destination, wgpu::TextureAspect::All);
  /* Exact production descriptor: a combined backing uses its pure-depth view
   * format together with DepthOnly aspect. */
  wgpu::TextureView source_depth = make_depth_view(
      source, test.source, wgpu::TextureAspect::DepthOnly);
  wgpu::TextureView destination_depth = make_depth_view(
      destination, test.destination, wgpu::TextureAspect::DepthOnly);

  static constexpr const char *blit_wgsl =
      "struct VOut { @builtin(position) pos : vec4f, };\n"
      "@vertex fn vs_main(@builtin(vertex_index) vid : u32) -> VOut {\n"
      "  var o : VOut;\n"
      "  let x = f32((vid << 1u) & 2u);\n"
      "  let y = f32(vid & 2u);\n"
      "  o.pos = vec4f(x * 2.0 - 1.0, y * 2.0 - 1.0, 0.0, 1.0);\n"
      "  return o;\n"
      "}\n"
      "@group(0) @binding(0) var src_tex : texture_depth_2d;\n"
      "@fragment fn fs_main(i : VOut) -> @builtin(frag_depth) f32 {\n"
      "  let hi = textureDimensions(src_tex) - vec2u(1u);\n"
      "  let xy = vec2i(min(vec2u(i.pos.xy), hi));\n"
      "  return textureLoad(src_tex, xy, 0);\n"
      "}\n";
  static constexpr const char *read_wgsl =
      "struct Out { value : f32, };\n"
      "@group(0) @binding(0) var depth_tex : texture_depth_2d;\n"
      "@group(0) @binding(1) var<storage, read_write> out : Out;\n"
      "@compute @workgroup_size(1) fn main() {\n"
      "  out.value = textureLoad(depth_tex, vec2i(0, 0), 0);\n"
      "}\n";
  wgpu::ShaderModule blit_module = shader_module(device, blit_wgsl);
  wgpu::ShaderModule read_module = shader_module(device, read_wgsl);
  wgpu::RenderPipeline blit_pipeline = make_depth_blit_pipeline(
      device, blit_module, test.destination);
  wgpu::ComputePipelineDescriptor read_pipeline_descriptor = {};
  read_pipeline_descriptor.layout = nullptr;
  read_pipeline_descriptor.compute.module = read_module;
  read_pipeline_descriptor.compute.entryPoint = "main";
  wgpu::ComputePipeline read_pipeline = device.CreateComputePipeline(&read_pipeline_descriptor);

  wgpu::BindGroupEntry blit_entry = {};
  blit_entry.binding = 0;
  blit_entry.textureView = source_depth;
  wgpu::BindGroupDescriptor blit_group_descriptor = {};
  blit_group_descriptor.layout = blit_pipeline.GetBindGroupLayout(0);
  blit_group_descriptor.entryCount = 1;
  blit_group_descriptor.entries = &blit_entry;
  wgpu::BindGroup blit_group = device.CreateBindGroup(&blit_group_descriptor);

  wgpu::BufferDescriptor output_descriptor = {};
  output_descriptor.size = sizeof(float);
  output_descriptor.usage = wgpu::BufferUsage::Storage | wgpu::BufferUsage::CopySrc;
  wgpu::Buffer output = device.CreateBuffer(&output_descriptor);
  wgpu::BufferDescriptor readback_descriptor = {};
  readback_descriptor.size = sizeof(float);
  readback_descriptor.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
  wgpu::Buffer readback = device.CreateBuffer(&readback_descriptor);

  wgpu::BindGroupEntry read_entries[2] = {};
  read_entries[0].binding = 0;
  read_entries[0].textureView = destination_depth;
  read_entries[1].binding = 1;
  read_entries[1].buffer = output;
  read_entries[1].size = sizeof(float);
  wgpu::BindGroupDescriptor read_group_descriptor = {};
  read_group_descriptor.layout = read_pipeline.GetBindGroupLayout(0);
  read_group_descriptor.entryCount = 2;
  read_group_descriptor.entries = read_entries;
  wgpu::BindGroup read_group = device.CreateBindGroup(&read_group_descriptor);

  wgpu::Buffer stencil_readback;
  if (preserve_stencil) {
    wgpu::BufferDescriptor stencil_descriptor = {};
    stencil_descriptor.size = 256 * kMipSize;
    stencil_descriptor.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
    stencil_readback = device.CreateBuffer(&stencil_descriptor);
  }

  const bool handles_ok = source != nullptr && destination != nullptr &&
                          source_attachment != nullptr && destination_attachment != nullptr &&
                          source_depth != nullptr && destination_depth != nullptr &&
                          blit_pipeline != nullptr && read_pipeline != nullptr &&
                          blit_group != nullptr && read_group != nullptr && output != nullptr &&
                          readback != nullptr && (!preserve_stencil || stencil_readback != nullptr);
  if (!handles_ok) {
    std::string error;
    pop_validation(instance, device, "depth route setup", error);
    return false;
  }

  wgpu::CommandEncoder encoder = device.CreateCommandEncoder();
  encode_clear(encoder, source_attachment, test.source, kSourceDepth, kSourceStencil);
  encode_clear(encoder,
               destination_attachment,
               test.destination,
               kDestinationDepth,
               kDestinationStencil);

  wgpu::RenderPassDepthStencilAttachment blit_attachment = {};
  blit_attachment.view = destination_attachment;
  blit_attachment.depthLoadOp = wgpu::LoadOp::Load;
  blit_attachment.depthStoreOp = wgpu::StoreOp::Store;
  blit_attachment.depthClearValue = 1.0f;
  if (preserve_stencil) {
    blit_attachment.stencilLoadOp = wgpu::LoadOp::Load;
    blit_attachment.stencilStoreOp = wgpu::StoreOp::Store;
    blit_attachment.stencilClearValue = 0;
  }
  wgpu::RenderPassDescriptor blit_pass_descriptor = {};
  blit_pass_descriptor.depthStencilAttachment = &blit_attachment;
  wgpu::RenderPassEncoder blit_pass = encoder.BeginRenderPass(&blit_pass_descriptor);
  blit_pass.SetPipeline(blit_pipeline);
  blit_pass.SetBindGroup(0, blit_group);
  blit_pass.SetViewport(0, 0, kMipSize, kMipSize, 0, 1);
  blit_pass.SetScissorRect(0, 0, kMipSize, kMipSize);
  blit_pass.Draw(3);
  blit_pass.End();

  wgpu::ComputePassEncoder read_pass = encoder.BeginComputePass();
  read_pass.SetPipeline(read_pipeline);
  read_pass.SetBindGroup(0, read_group);
  read_pass.DispatchWorkgroups(1);
  read_pass.End();
  encoder.CopyBufferToBuffer(output, 0, readback, 0, sizeof(float));

  if (preserve_stencil) {
    wgpu::TexelCopyTextureInfo stencil_source = {};
    stencil_source.texture = destination;
    stencil_source.mipLevel = kMip;
    stencil_source.origin = {0, 0, kLayer};
    stencil_source.aspect = wgpu::TextureAspect::StencilOnly;
    wgpu::TexelCopyBufferInfo stencil_destination = {};
    stencil_destination.buffer = stencil_readback;
    stencil_destination.layout.bytesPerRow = 256;
    stencil_destination.layout.rowsPerImage = kMipSize;
    wgpu::Extent3D stencil_extent = {kMipSize, kMipSize, 1};
    encoder.CopyTextureToBuffer(&stencil_source, &stencil_destination, &stencil_extent);
  }

  wgpu::CommandBuffer command = encoder.Finish();
  /* Lifetime control: only the sampled view/bind group retain the source now. */
  source_attachment = nullptr;
  source = nullptr;
  device.GetQueue().Submit(1, &command);
  std::string validation_error;
  const bool validation_ok = pop_validation(
      instance, device, "depth route descriptors", validation_error);

  float copied_depth = 0.0f;
  const bool depth_mapped = map_float(instance, readback, copied_depth);
  const bool depth_exact = depth_mapped && std::abs(copied_depth - kSourceDepth) < 0.01f;
  const bool stencil_exact = !preserve_stencil ||
                             map_stencil(instance,
                                         stencil_readback,
                                         uint8_t(kDestinationStencil));
  std::cout << "  depth=" << copied_depth << " expected=" << kSourceDepth
            << " stencil=" << (preserve_stencil ? (stencil_exact ? "preserved" : "CHANGED") :
                                                       "n/a")
            << " validation=" << (validation_ok ? "OK" : "FAIL") << "\n";
  return validation_ok && depth_exact && stencil_exact;
}

}  // namespace

int main()
{
  wgpu::InstanceDescriptor instance_descriptor = {};
  static constexpr auto timed_wait = wgpu::InstanceFeatureName::TimedWaitAny;
  instance_descriptor.requiredFeatureCount = 1;
  instance_descriptor.requiredFeatures = &timed_wait;
  wgpu::Instance instance = wgpu::CreateInstance(&instance_descriptor);
  if (instance == nullptr) {
    std::cerr << "CreateInstance failed\n";
    return 2;
  }
  wgpu::Adapter adapter = request_adapter(instance);
  if (adapter == nullptr) {
    return 3;
  }
  std::cout << "adapter RG11B10UfloatRenderable="
            << (adapter.HasFeature(wgpu::FeatureName::RG11B10UfloatRenderable) ? "YES" : "no")
            << " Depth32FloatStencil8="
            << (adapter.HasFeature(wgpu::FeatureName::Depth32FloatStencil8) ? "YES" : "no")
            << "\n";
  wgpu::Device device = make_feature_omission_device(instance, adapter);
  if (device == nullptr) {
    return 4;
  }
  const bool rg11_omitted = !device.HasFeature(wgpu::FeatureName::RG11B10UfloatRenderable);
  std::string raw_error;
  const bool rg11_raw = try_rg11_texture(instance,
                                         device,
                                         wgpu::TextureUsage::CopySrc |
                                             wgpu::TextureUsage::CopyDst |
                                             wgpu::TextureUsage::TextureBinding,
                                         raw_error);
  std::string attachment_error;
  const bool rg11_attachment = try_rg11_texture(
      instance,
      device,
      wgpu::TextureUsage::CopySrc | wgpu::TextureUsage::CopyDst |
          wgpu::TextureUsage::TextureBinding | wgpu::TextureUsage::RenderAttachment,
      attachment_error);
  std::cout << "RG11 no-feature raw usage: " << (rg11_raw ? "OK" : "FAIL") << "\n"
            << "RG11 no-feature +RenderAttachment: "
            << (rg11_attachment ? "UNEXPECTED OK" : "EXPECTED VALIDATION") << "\n";

  std::vector<DepthCase> cases = {
      {wgpu::TextureFormat::Depth16Unorm, wgpu::TextureFormat::Depth32Float},
      {wgpu::TextureFormat::Depth32Float, wgpu::TextureFormat::Depth16Unorm},
      {wgpu::TextureFormat::Depth24Plus, wgpu::TextureFormat::Depth32Float},
      {wgpu::TextureFormat::Depth32Float, wgpu::TextureFormat::Depth24PlusStencil8},
      {wgpu::TextureFormat::Depth24PlusStencil8, wgpu::TextureFormat::Depth24Plus},
  };
  if (device.HasFeature(wgpu::FeatureName::Depth32FloatStencil8)) {
    cases.push_back(
        {wgpu::TextureFormat::Depth32FloatStencil8, wgpu::TextureFormat::Depth32Float});
    cases.push_back(
        {wgpu::TextureFormat::Depth32Float, wgpu::TextureFormat::Depth32FloatStencil8});
    cases.push_back({wgpu::TextureFormat::Depth32FloatStencil8,
                     wgpu::TextureFormat::Depth32FloatStencil8});
  }

  bool depth_ok = true;
  for (const DepthCase &test : cases) {
    depth_ok &= run_depth_case(instance, device, test);
  }
  const bool pass = rg11_omitted && rg11_raw && !rg11_attachment && depth_ok;
  std::cout << "r60 probe verdict: " << (pass ? "PASS" : "FAIL") << "\n";
  return pass ? 0 : 8;
}
