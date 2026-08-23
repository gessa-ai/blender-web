// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

/**
 * Audit-only Dawn error-handle control.
 *
 * This deliberately runs on the available software Vulkan adapter. It proves
 * API return-value semantics only and MUST NOT bind a receipt, profile, or
 * milestone result.
 */

#include <array>
#include <atomic>
#include <cstdint>
#include <functional>
#include <iostream>
#include <memory>
#include <string>
#include <utility>

#include "webgpu/webgpu_cpp.h"

#include "GHOST_WGPUTransaction.hh"
#include "probe_platform.hh"
#include "wgpu_common.hh"

namespace {

std::string to_string(wgpu::StringView value)
{
  if (value.data == nullptr) {
    return {};
  }
  if (value.length == WGPU_STRLEN) {
    return std::string(value.data);
  }
  return std::string(value.data, value.length);
}

template<typename Fn>
bool captures_validation(const wgpu::Instance &instance,
                         const wgpu::Device &device,
                         Fn &&operation,
                         std::string &r_message)
{
  bool callback_called = false;
  wgpu::ErrorType error_type = wgpu::ErrorType::NoError;
  device.PushErrorScope(wgpu::ErrorFilter::Validation);
  std::forward<Fn>(operation)();
  const wgpu::Future future = device.PopErrorScope(
      wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::PopErrorScopeStatus status, wgpu::ErrorType type, wgpu::StringView message) {
        callback_called = status == wgpu::PopErrorScopeStatus::Success;
        error_type = type;
        r_message = to_string(message);
      });
  instance.WaitAny(future, UINT64_MAX);
  return callback_called && error_type == wgpu::ErrorType::Validation;
}

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::cerr << "AUDIT_FAIL " << message << '\n';
  }
  return condition;
}

struct CountingQueue {
  wgpu::Queue queue;
  int *submit_attempts = nullptr;

  bool operator==(std::nullptr_t) const
  {
    return queue == nullptr;
  }

  void Submit(const size_t count, const wgpu::CommandBuffer *commands) const
  {
    (*submit_attempts)++;
    queue.Submit(count, commands);
  }
};

struct PersistentBufferAllocation {
  wgpu::Buffer handle;
  uint64_t size = 0;
  bool readable = false;

  bool operator==(std::nullptr_t) const
  {
    return handle == nullptr;
  }
  bool operator!=(std::nullptr_t) const
  {
    return handle != nullptr;
  }
};

struct TextureViewAllocation {
  wgpu::Texture texture;
  wgpu::TextureView view;

  bool operator==(std::nullptr_t) const
  {
    return texture == nullptr || view == nullptr;
  }
  bool operator!=(std::nullptr_t) const
  {
    return !(*this == nullptr);
  }
};

struct LayoutAllocation {
  wgpu::BindGroupLayout bind_group_layout;
  wgpu::PipelineLayout pipeline_layout;

  bool operator==(std::nullptr_t) const
  {
    return bind_group_layout == nullptr || pipeline_layout == nullptr;
  }
  bool operator!=(std::nullptr_t) const
  {
    return !(*this == nullptr);
  }
};

struct ShaderModuleAllocation {
  wgpu::ShaderModule vertex;
  wgpu::ShaderModule fragment;
  wgpu::ShaderModule compute;

  bool operator==(std::nullptr_t) const
  {
    return vertex == nullptr && fragment == nullptr && compute == nullptr;
  }
  bool operator!=(std::nullptr_t) const
  {
    return !(*this == nullptr);
  }
};

}  // namespace

int main()
{
  wgpu::InstanceDescriptor instance_descriptor = {};
  static constexpr auto timed_wait = wgpu::InstanceFeatureName::TimedWaitAny;
  instance_descriptor.requiredFeatureCount = 1;
  instance_descriptor.requiredFeatures = &timed_wait;
  wgpu::Instance instance = wgpu::CreateInstance(&instance_descriptor);
  if (!require(instance != nullptr, "CreateInstance returned null")) {
    return 2;
  }

  wgpu::RequestAdapterOptions adapter_options = {};
  adapter_options.backendType = blender_web::dawn_probe::kBackendType;
  adapter_options.featureLevel = wgpu::FeatureLevel::Core;
  wgpu::Adapter adapter;
  instance.WaitAny(
      instance.RequestAdapter(
          &adapter_options,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestAdapterStatus status, wgpu::Adapter candidate, wgpu::StringView) {
            if (status == wgpu::RequestAdapterStatus::Success) {
              adapter = std::move(candidate);
            }
          }),
      UINT64_MAX);
  if (!require(adapter != nullptr, "software-control adapter unavailable")) {
    return 3;
  }

  wgpu::AdapterInfo adapter_info = {};
  adapter.GetInfo(&adapter_info);
  std::cout << "AUDIT_CONTROL adapter=\"" << to_string(adapter_info.device)
            << "\" type=" << static_cast<int>(adapter_info.adapterType)
            << " SOFTWARE_CONTROL_NON_RECEIPT\n";

  auto loss_state =
      std::make_shared<std::atomic<ghost_web::DeviceState>>(ghost_web::DeviceState::Active);
  wgpu::DeviceDescriptor device_descriptor = {};
  device_descriptor.SetDeviceLostCallback(
      wgpu::CallbackMode::WaitAnyOnly,
      [loss_state](const wgpu::Device &,
                   wgpu::DeviceLostReason,
                   wgpu::StringView) { ghost_web::device_state_mark_lost(*loss_state); });
  wgpu::Device device;
  instance.WaitAny(
      adapter.RequestDevice(
          &device_descriptor,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestDeviceStatus status, wgpu::Device candidate, wgpu::StringView) {
            if (status == wgpu::RequestDeviceStatus::Success) {
              device = std::move(candidate);
            }
          }),
      UINT64_MAX);
  if (!require(device != nullptr, "software-control device unavailable")) {
    return 4;
  }

  int passed = 0;
  std::string error;

  wgpu::Buffer invalid_buffer;
  error.clear();
  const bool buffer_error = captures_validation(instance, device, [&]() {
    wgpu::BufferDescriptor descriptor = {};
    descriptor.size = 4;
    descriptor.usage = wgpu::BufferUsage::None;
    invalid_buffer = device.CreateBuffer(&descriptor);
  }, error);
  if (!require(invalid_buffer != nullptr && buffer_error,
               "invalid buffer did not return a non-null error object"))
  {
    return 5;
  }
  passed++;

  wgpu::BindGroupLayout invalid_layout;
  error.clear();
  const bool layout_error = captures_validation(instance, device, [&]() {
    wgpu::BindGroupLayoutEntry entries[2] = {};
    for (wgpu::BindGroupLayoutEntry &entry : entries) {
      entry.binding = 0;
      entry.visibility = wgpu::ShaderStage::Vertex;
      entry.buffer.type = wgpu::BufferBindingType::Uniform;
    }
    wgpu::BindGroupLayoutDescriptor descriptor = {};
    descriptor.entryCount = 2;
    descriptor.entries = entries;
    invalid_layout = device.CreateBindGroupLayout(&descriptor);
  }, error);
  if (!require(invalid_layout != nullptr && layout_error,
               "invalid bind-group layout did not return a non-null error object"))
  {
    return 6;
  }
  passed++;

  wgpu::PipelineLayout invalid_pipeline_layout;
  error.clear();
  const bool pipeline_layout_error = captures_validation(instance, device, [&]() {
    const std::array<wgpu::BindGroupLayout, 1> layouts = {invalid_layout};
    wgpu::PipelineLayoutDescriptor descriptor = {};
    descriptor.bindGroupLayoutCount = layouts.size();
    descriptor.bindGroupLayouts = layouts.data();
    invalid_pipeline_layout = device.CreatePipelineLayout(&descriptor);
  }, error);
  if (!require(invalid_pipeline_layout != nullptr && pipeline_layout_error,
               "invalid pipeline layout did not return a non-null error object"))
  {
    return 7;
  }
  passed++;

  wgpu::BindGroupLayoutEntry required_entry = {};
  required_entry.binding = 0;
  required_entry.visibility = wgpu::ShaderStage::Vertex;
  required_entry.buffer.type = wgpu::BufferBindingType::Uniform;
  wgpu::BindGroupLayoutDescriptor required_layout_descriptor = {};
  required_layout_descriptor.entryCount = 1;
  required_layout_descriptor.entries = &required_entry;
  const wgpu::BindGroupLayout required_layout =
      device.CreateBindGroupLayout(&required_layout_descriptor);
  if (!require(required_layout != nullptr, "valid bind-group layout setup failed")) {
    return 8;
  }

  wgpu::BindGroup invalid_bind_group;
  error.clear();
  const bool bind_group_error = captures_validation(instance, device, [&]() {
    wgpu::BindGroupDescriptor descriptor = {};
    descriptor.layout = required_layout;
    invalid_bind_group = device.CreateBindGroup(&descriptor);
  }, error);
  if (!require(invalid_bind_group != nullptr && bind_group_error,
               "invalid bind group did not return a non-null error object"))
  {
    return 9;
  }
  passed++;

  wgpu::ShaderModule invalid_shader;
  error.clear();
  const bool shader_error = captures_validation(instance, device, [&]() {
    wgpu::ShaderSourceWGSL source = {};
    source.code = "this is not WGSL";
    wgpu::ShaderModuleDescriptor descriptor = {};
    descriptor.nextInChain = &source;
    invalid_shader = device.CreateShaderModule(&descriptor);
  }, error);
  if (!require(invalid_shader != nullptr && shader_error,
               "invalid shader did not return a non-null error object"))
  {
    return 10;
  }
  passed++;

  wgpu::Texture invalid_texture;
  error.clear();
  const bool texture_error = captures_validation(instance, device, [&]() {
    wgpu::TextureDescriptor descriptor = {};
    descriptor.size = {1, 1, 1};
    descriptor.dimension = wgpu::TextureDimension::e2D;
    descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
    descriptor.mipLevelCount = 1;
    descriptor.sampleCount = 1;
    descriptor.usage = wgpu::TextureUsage::None;
    invalid_texture = device.CreateTexture(&descriptor);
  }, error);
  if (!require(invalid_texture != nullptr && texture_error,
               "invalid texture did not return a non-null error object"))
  {
    return 11;
  }
  passed++;

  wgpu::TextureDescriptor texture_descriptor = {};
  texture_descriptor.size = {1, 1, 1};
  texture_descriptor.dimension = wgpu::TextureDimension::e2D;
  texture_descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
  texture_descriptor.mipLevelCount = 1;
  texture_descriptor.sampleCount = 1;
  texture_descriptor.usage = wgpu::TextureUsage::RenderAttachment;
  const wgpu::Texture texture = device.CreateTexture(&texture_descriptor);
  const wgpu::TextureView texture_view = texture.CreateView();
  if (!require(texture != nullptr && texture_view != nullptr,
               "valid render attachment setup failed"))
  {
    return 12;
  }

  wgpu::TextureView invalid_view;
  error.clear();
  const bool view_error = captures_validation(instance, device, [&]() {
    wgpu::TextureViewDescriptor descriptor = {};
    descriptor.dimension = wgpu::TextureViewDimension::e3D;
    invalid_view = texture.CreateView(&descriptor);
  }, error);
  if (!require(invalid_view != nullptr && view_error,
               "invalid texture view did not return a non-null error object"))
  {
    return 13;
  }
  passed++;

  wgpu::CommandEncoder encoder;
  wgpu::RenderPassEncoder pass;
  wgpu::CommandBuffer command_buffer;
  error.clear();
  const bool command_error = captures_validation(instance, device, [&]() {
    encoder = device.CreateCommandEncoder();
    wgpu::RenderPassColorAttachment color = {};
    color.view = texture_view;
    color.depthSlice = 0;
    color.loadOp = wgpu::LoadOp::Clear;
    color.storeOp = wgpu::StoreOp::Store;
    wgpu::RenderPassDescriptor descriptor = {};
    descriptor.colorAttachmentCount = 1;
    descriptor.colorAttachments = &color;
    pass = encoder.BeginRenderPass(&descriptor);
    pass.End();
    command_buffer = encoder.Finish();
    device.GetQueue().Submit(1, &command_buffer);
  }, error);
  if (!require(encoder != nullptr && pass != nullptr && command_buffer != nullptr && command_error,
               "invalid pass/command path did not retain non-null error objects"))
  {
    return 14;
  }
  passed++;

  int scoped_cases = 0;
  for (const bool valid_case : {false, true}) {
    wgpu::Future scope_future = {};
    bool candidate_nonnull = false;
    bool completed = false;
    bool accepted = false;
    wgpu::Buffer published;
    ghost_web::scoped_handle_create(
        [&]() { device.PushErrorScope(wgpu::ErrorFilter::Validation); },
        [&]() {
          wgpu::BufferDescriptor descriptor = {};
          descriptor.size = 4;
          descriptor.usage = valid_case ? wgpu::BufferUsage::CopyDst : wgpu::BufferUsage::None;
          wgpu::Buffer candidate = device.CreateBuffer(&descriptor);
          candidate_nonnull = candidate != nullptr;
          return candidate;
        },
        [&](auto completion) {
          auto shared_completion = std::make_shared<std::function<void(bool)>>(
              std::move(completion));
          scope_future = device.PopErrorScope(
              wgpu::CallbackMode::WaitAnyOnly,
              [shared_completion](wgpu::PopErrorScopeStatus status,
                                  wgpu::ErrorType type,
                                  wgpu::StringView) {
                (*shared_completion)(status == wgpu::PopErrorScopeStatus::Success &&
                                     type == wgpu::ErrorType::NoError);
              });
        },
        [&](const bool valid, wgpu::Buffer candidate) {
          completed = true;
          accepted = valid;
          if (valid) {
            published = std::move(candidate);
          }
        });
    if (!require(candidate_nonnull && !completed && published == nullptr,
                 "scoped handle remained unpublished before scope completion") ||
        !require(instance.WaitAny(scope_future, UINT64_MAX) == wgpu::WaitStatus::Success,
                 "scoped handle validation future did not settle") ||
        !require(completed && accepted == valid_case,
                 "scoped handle acceptance did not follow validation status") ||
        !require(valid_case ? published != nullptr : published == nullptr,
                 "scoped handle publication mismatch"))
    {
      return 15;
    }
    scoped_cases++;
  }

  int resize_cases = 0;
  wgpu::Texture resize_backbuffer = texture;
  uint32_t resize_authoritative_width = 1;
  uint32_t resize_authoritative_height = 1;
  uint32_t resize_backbuffer_width = 1;
  uint32_t resize_backbuffer_height = 1;
  constexpr uint32_t resize_requested_width = 2;
  constexpr uint32_t resize_requested_height = 2;
  bool resize_configured = true;
  int resize_configure_calls = 0;
  bool resize_configure_saw_old_state = true;
  for (const bool valid_case : {false, true}) {
    wgpu::Future scope_future = {};
    bool candidate_nonnull = false;
    bool completed = false;
    ghost_web::SurfaceResizeResult resize_result = ghost_web::SurfaceResizeResult::Rejected;
    if (!require(ghost_web::surface_resize_candidate_needed(resize_configured,
                                                            resize_authoritative_width,
                                                            resize_authoritative_height,
                                                            resize_requested_width,
                                                            resize_requested_height,
                                                            false,
                                                            resize_backbuffer != nullptr,
                                                            resize_backbuffer_width,
                                                            resize_backbuffer_height),
                 "shipping resize state did not retain its pending request"))
    {
      return 41;
    }
    ghost_web::scoped_handle_create(
        [&]() { device.PushErrorScope(wgpu::ErrorFilter::Validation); },
        [&]() {
          wgpu::TextureDescriptor descriptor = {};
          descriptor.size = {resize_requested_width, resize_requested_height, 1};
          descriptor.dimension = wgpu::TextureDimension::e2D;
          descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
          descriptor.mipLevelCount = 1;
          descriptor.sampleCount = 1;
          descriptor.usage = valid_case ? wgpu::TextureUsage::RenderAttachment :
                                          wgpu::TextureUsage::None;
          wgpu::Texture candidate = device.CreateTexture(&descriptor);
          candidate_nonnull = candidate != nullptr;
          return candidate;
        },
        [&](auto completion) {
          auto shared_completion = std::make_shared<std::function<void(bool)>>(
              std::move(completion));
          scope_future = device.PopErrorScope(
              wgpu::CallbackMode::WaitAnyOnly,
              [shared_completion](wgpu::PopErrorScopeStatus status,
                                  wgpu::ErrorType type,
                                  wgpu::StringView) {
                (*shared_completion)(status == wgpu::PopErrorScopeStatus::Success &&
                                     type == wgpu::ErrorType::NoError);
              });
        },
        [&](const bool valid, wgpu::Texture candidate) {
          completed = true;
          resize_result = ghost_web::surface_resize_commit_if_current(
              valid,
              std::move(candidate),
              resize_requested_width,
              resize_requested_height,
              resize_requested_width,
              resize_requested_height,
              [&](const uint32_t width, const uint32_t height) {
                resize_configure_calls++;
                resize_configure_saw_old_state &= width == resize_requested_width &&
                                                  height == resize_requested_height &&
                                                  resize_authoritative_width == 1 &&
                                                  resize_authoritative_height == 1 &&
                                                  resize_backbuffer_width == 1 &&
                                                  resize_backbuffer_height == 1;
              },
              resize_backbuffer,
              resize_backbuffer_width,
              resize_backbuffer_height,
              resize_authoritative_width,
              resize_authoritative_height,
              resize_configured);
        });
    if (!require(candidate_nonnull && !completed && resize_backbuffer.GetWidth() == 1 &&
                     resize_authoritative_width == 1 && resize_authoritative_height == 1,
                 "shipping resize published before its texture scope completed") ||
        !require(instance.WaitAny(scope_future, UINT64_MAX) == wgpu::WaitStatus::Success,
                 "shipping resize validation future did not settle"))
    {
      return 41;
    }
    const ghost_web::SurfaceResizeResult expected =
        valid_case ? ghost_web::SurfaceResizeResult::Committed :
                     ghost_web::SurfaceResizeResult::Rejected;
    if (!require(completed && resize_result == expected,
                 "shipping resize acceptance did not follow validation status") ||
        !require(valid_case ?
                     resize_backbuffer.GetWidth() == resize_requested_width &&
                         resize_backbuffer.GetHeight() == resize_requested_height &&
                         resize_authoritative_width == resize_requested_width &&
                         resize_authoritative_height == resize_requested_height &&
                         resize_backbuffer_width == resize_requested_width &&
                         resize_backbuffer_height == resize_requested_height &&
                         resize_configure_calls == 1 && resize_configure_saw_old_state :
                     resize_backbuffer.GetWidth() == 1 && resize_backbuffer.GetHeight() == 1 &&
                         resize_authoritative_width == 1 && resize_authoritative_height == 1 &&
                         resize_backbuffer_width == 1 && resize_backbuffer_height == 1 &&
                         resize_configure_calls == 0,
                 "shipping resize did not preserve or atomically replace its complete state"))
    {
      return 41;
    }
    resize_cases++;
  }
  if (!require(!ghost_web::surface_resize_candidate_needed(resize_configured,
                                                            resize_authoritative_width,
                                                            resize_authoritative_height,
                                                            resize_requested_width,
                                                            resize_requested_height,
                                                            false,
                                                            resize_backbuffer != nullptr,
                                                            resize_backbuffer_width,
                                                            resize_backbuffer_height) &&
                   ghost_web::surface_resize_present_coherent(resize_configured,
                                                               resize_authoritative_width,
                                                               resize_authoritative_height,
                                                               resize_backbuffer != nullptr,
                                                               resize_backbuffer_width,
                                                               resize_backbuffer_height,
                                                               resize_requested_width,
                                                               resize_requested_height),
               "shipping resize retry did not settle into a presentable extent"))
  {
    return 41;
  }

  for (const bool valid_case : {false, true}) {
    wgpu::Future encode_future = {};
    wgpu::Future submit_future = {};
    bool submit_scope_started = false;
    int submit_attempts = 0;
    bool completed = false;
    bool accepted = false;
    ghost_web::present_frame_encode_submit_scoped(
        [&]() { device.PushErrorScope(wgpu::ErrorFilter::Validation); },
        [&]() { return texture.CreateView(); },
        [&]() { return texture.CreateView(); },
        [&](const wgpu::TextureView &source_view) { return source_view; },
        [&]() { return device.CreateCommandEncoder(); },
        [&](wgpu::CommandEncoder &candidate_encoder, const wgpu::TextureView &target_view) {
          wgpu::RenderPassColorAttachment color = {};
          color.view = target_view;
          color.depthSlice = valid_case ? wgpu::kDepthSliceUndefined : 0;
          color.loadOp = wgpu::LoadOp::Clear;
          color.storeOp = wgpu::StoreOp::Store;
          wgpu::RenderPassDescriptor descriptor = {};
          descriptor.colorAttachmentCount = 1;
          descriptor.colorAttachments = &color;
          return candidate_encoder.BeginRenderPass(&descriptor);
        },
        [](wgpu::RenderPassEncoder &, const wgpu::TextureView &) {},
        [&](auto completion) {
          auto shared_completion = std::make_shared<std::function<void(bool)>>(
              std::move(completion));
          encode_future = device.PopErrorScope(
              wgpu::CallbackMode::WaitAnyOnly,
              [shared_completion](wgpu::PopErrorScopeStatus status,
                                  wgpu::ErrorType type,
                                  wgpu::StringView) {
                (*shared_completion)(status == wgpu::PopErrorScopeStatus::Success &&
                                     type == wgpu::ErrorType::NoError);
              });
        },
        [&]() {
          submit_scope_started = true;
          device.PushErrorScope(wgpu::ErrorFilter::Validation);
        },
        [&](const wgpu::CommandBuffer &candidate) {
          submit_attempts++;
          device.GetQueue().Submit(1, &candidate);
        },
        [&](auto completion) {
          auto shared_completion = std::make_shared<std::function<void(bool)>>(
              std::move(completion));
          submit_future = device.PopErrorScope(
              wgpu::CallbackMode::WaitAnyOnly,
              [shared_completion](wgpu::PopErrorScopeStatus status,
                                  wgpu::ErrorType type,
                                  wgpu::StringView) {
                (*shared_completion)(status == wgpu::PopErrorScopeStatus::Success &&
                                     type == wgpu::ErrorType::NoError);
              });
        },
        [&](const bool valid) {
          completed = true;
          accepted = valid;
        });
    if (!require(!completed && !submit_scope_started && submit_attempts == 0,
                 "frame transaction acted before encoding scope completion") ||
        !require(instance.WaitAny(encode_future, UINT64_MAX) == wgpu::WaitStatus::Success,
                 "frame encoding validation future did not settle"))
    {
      return 16;
    }
    if (!valid_case) {
      if (!require(completed && !accepted && !submit_scope_started && submit_attempts == 0,
                   "non-null error command buffer reached queue submission"))
      {
        return 17;
      }
    }
    else {
      if (!require(!completed && submit_scope_started && submit_attempts == 1,
                   "validated command buffer did not enter submit scope") ||
          !require(instance.WaitAny(submit_future, UINT64_MAX) == wgpu::WaitStatus::Success,
                   "frame submission validation future did not settle") ||
          !require(completed && accepted && submit_attempts == 1,
                   "clean submission did not complete exactly once"))
      {
        return 18;
      }
    }
    scoped_cases++;
  }

  namespace bw = blender::gpu::webgpu;
  bw::OrderedQueueScheduler gpu_scheduler;
  int gpu_scoped_cases = 0;
  for (const bool valid_case : {false, true}) {
    if (valid_case) {
      /* The rejected command poisons only its frame epoch; a new Blender frame must be able to
       * retry cleanly without allowing any later work from the failed epoch through. */
      gpu_scheduler.begin_epoch();
    }
    int submit_attempts = 0;
    bool completed = false;
    bool accepted = false;
    const CountingQueue queue{device.GetQueue(), &submit_attempts};
    bw::command_encode_submit_scoped(
        instance,
        device,
        queue,
        gpu_scheduler,
        valid_case ? "audit valid GPU command" : "audit invalid GPU command",
        [&](auto &candidate_encoder) {
          wgpu::RenderPassColorAttachment color = {};
          color.view = texture_view;
          color.depthSlice = valid_case ? wgpu::kDepthSliceUndefined : 0;
          color.loadOp = wgpu::LoadOp::Clear;
          color.storeOp = wgpu::StoreOp::Store;
          wgpu::RenderPassDescriptor descriptor = {};
          descriptor.colorAttachmentCount = 1;
          descriptor.colorAttachments = &color;
          wgpu::RenderPassEncoder candidate_pass =
              candidate_encoder.BeginRenderPass(&descriptor);
          if (candidate_pass == nullptr) {
            return false;
          }
          candidate_pass.End();
          return true;
        },
        [&](const bool valid) {
          completed = true;
          accepted = valid;
        });
    if (!require(completed, "shipping GPU command scope did not complete synchronously") ||
        !require(accepted == valid_case,
                 "shipping GPU command acceptance did not follow completed scopes") ||
        !require(submit_attempts == (valid_case ? 1 : 0),
                 "shipping GPU helper submitted a rejected error object") ||
        !require(gpu_scheduler.pending_count() == 0,
                 "shipping GPU command left ordered queue work pending"))
    {
      return 19;
    }
    gpu_scoped_cases++;
  }

  bw::ScopedHandleCache<uint32_t, wgpu::Sampler> scoped_sampler_cache;
  int sampler_creates = 0;
  wgpu::Sampler invalid_sampler = scoped_sampler_cache.get_or_create(
      instance, device, 7u, "audit invalid sampler", [&]() {
        sampler_creates++;
        wgpu::SamplerDescriptor descriptor = {};
        descriptor.lodMinClamp = 2.0f;
        descriptor.lodMaxClamp = 1.0f;
        return device.CreateSampler(&descriptor);
      });
  if (!require(invalid_sampler == nullptr && scoped_sampler_cache.size() == 0 &&
                   !scoped_sampler_cache.pending(7u) && sampler_creates == 1,
               "shipping scoped cache published a non-null sampler error object"))
  {
    return 20;
  }

  wgpu::Sampler valid_sampler = scoped_sampler_cache.get_or_create(
      instance, device, 7u, "audit valid sampler", [&]() {
        sampler_creates++;
        wgpu::SamplerDescriptor descriptor = {};
        return device.CreateSampler(&descriptor);
      });
  if (!require(valid_sampler != nullptr && scoped_sampler_cache.size() == 1 &&
                   !scoped_sampler_cache.pending(7u) && sampler_creates == 2,
               "shipping scoped cache did not publish a clean sampler retry"))
  {
    return 21;
  }

  bw::ScopedHandleCache<uint8_t, wgpu::Buffer> scoped_dummy_buffer_cache;
  int dummy_buffer_creates = 0;
  wgpu::Buffer invalid_dummy_buffer = scoped_dummy_buffer_cache.get_or_create(
      instance, device, uint8_t(0), "audit invalid dummy vertex buffer", [&]() {
        dummy_buffer_creates++;
        wgpu::BufferDescriptor descriptor = {};
        descriptor.size = 16;
        descriptor.usage = wgpu::BufferUsage::None;
        return device.CreateBuffer(&descriptor);
      });
  if (!require(invalid_dummy_buffer == nullptr && scoped_dummy_buffer_cache.size() == 0 &&
                   !scoped_dummy_buffer_cache.pending(uint8_t(0)) &&
                   dummy_buffer_creates == 1,
               "shipping scoped cache published a non-null dummy-buffer error object"))
  {
    return 22;
  }

  wgpu::Buffer valid_dummy_buffer = scoped_dummy_buffer_cache.get_or_create(
      instance, device, uint8_t(0), "audit valid dummy vertex buffer", [&]() {
        dummy_buffer_creates++;
        return bw::dummy_vertex_buffer_create(device);
      });
  if (!require(valid_dummy_buffer != nullptr && scoped_dummy_buffer_cache.size() == 1 &&
                   !scoped_dummy_buffer_cache.pending(uint8_t(0)) &&
                   dummy_buffer_creates == 2,
               "shipping scoped cache did not publish an initialized dummy-buffer retry"))
  {
    return 23;
  }

  bw::ScopedHandleCache<uint8_t, PersistentBufferAllocation> persistent_buffer_cache;
  int persistent_buffer_creates = 0;
  const PersistentBufferAllocation invalid_persistent = persistent_buffer_cache.get_or_create(
      instance, device, uint8_t(0), "audit invalid persistent buffer", [&]() {
        persistent_buffer_creates++;
        wgpu::BufferDescriptor descriptor = {};
        descriptor.size = 4;
        descriptor.usage = wgpu::BufferUsage::None;
        PersistentBufferAllocation candidate;
        candidate.handle = device.CreateBuffer(&descriptor);
        candidate.size = descriptor.size;
        candidate.readable = true;
        return candidate;
      });
  if (!require(invalid_persistent == nullptr && persistent_buffer_cache.size() == 0 &&
                   !persistent_buffer_cache.pending(uint8_t(0)) &&
                   persistent_buffer_creates == 1,
               "shipping scoped cache published a non-null persistent-buffer error object"))
  {
    return 24;
  }

  const PersistentBufferAllocation valid_persistent = persistent_buffer_cache.get_or_create(
      instance, device, uint8_t(0), "audit valid persistent buffer", [&]() {
        persistent_buffer_creates++;
        wgpu::BufferDescriptor descriptor = {};
        descriptor.size = 8;
        descriptor.usage = wgpu::BufferUsage::CopyDst;
        PersistentBufferAllocation candidate;
        candidate.handle = device.CreateBuffer(&descriptor);
        candidate.size = descriptor.size;
        candidate.readable = false;
        return candidate;
      });
  if (!require(valid_persistent != nullptr && valid_persistent.size == 8 &&
                   !valid_persistent.readable && persistent_buffer_cache.size() == 1 &&
                   !persistent_buffer_cache.pending(uint8_t(0)) &&
                   persistent_buffer_creates == 2,
               "shipping scoped cache did not atomically publish a clean persistent retry"))
  {
    return 25;
  }

  bw::OrderedQueueScheduler transient_buffer_scheduler;
  int transient_buffer_cases = 0;
  for (const bool valid_case : {false, true}) {
    if (valid_case) {
      transient_buffer_scheduler.begin_epoch();
    }
    bool completed = false;
    bool accepted = false;
    int dependent_work = 0;
    int canceled_work = 0;
    const wgpu::Buffer candidate = bw::transient_resource_create_scoped(
        instance,
        device,
        transient_buffer_scheduler,
        valid_case ? "audit valid transient buffer" : "audit invalid transient buffer",
        [&]() {
          wgpu::BufferDescriptor descriptor = {};
          descriptor.size = 4;
          descriptor.usage = valid_case ? wgpu::BufferUsage::CopyDst :
                                          wgpu::BufferUsage::None;
          return device.CreateBuffer(&descriptor);
        },
        [&](const bool valid) {
          completed = true;
          accepted = valid;
        });
    transient_buffer_scheduler.enqueue(
        [&](auto done) {
          dependent_work++;
          done(true);
        },
        [&]() { canceled_work++; });
    if (!require(candidate != nullptr,
                 "Dawn transient-buffer control did not return a non-null candidate") ||
        !require(completed && accepted == valid_case,
                 "shipping transient-buffer gate ignored completed scope status") ||
        !require(dependent_work == (valid_case ? 1 : 0) &&
                     canceled_work == (valid_case ? 0 : 1),
                 "shipping transient-buffer gate released rejected dependent work") ||
        !require(transient_buffer_scheduler.pending_count() == 0,
                 "shipping transient-buffer gate left ordered work pending"))
    {
      return 26;
    }
    transient_buffer_cases++;
  }

  wgpu::BindGroupLayoutDescriptor empty_layout_descriptor = {};
  const wgpu::BindGroupLayout empty_layout =
      device.CreateBindGroupLayout(&empty_layout_descriptor);
  if (!require(empty_layout != nullptr, "valid empty bind-group layout setup failed")) {
    return 31;
  }
  bw::OrderedQueueScheduler transient_bind_group_scheduler;
  int transient_bind_group_cases = 0;
  for (const bool valid_case : {false, true}) {
    if (valid_case) {
      transient_bind_group_scheduler.begin_epoch();
    }
    bool completed = false;
    bool accepted = false;
    int dependent_work = 0;
    int canceled_work = 0;
    const wgpu::BindGroup candidate = bw::transient_resource_create_scoped(
        instance,
        device,
        transient_bind_group_scheduler,
        valid_case ? "audit valid transient bind group" :
                     "audit invalid transient bind group",
        [&]() {
          wgpu::BindGroupDescriptor descriptor = {};
          descriptor.layout = valid_case ? empty_layout : required_layout;
          return device.CreateBindGroup(&descriptor);
        },
        [&](const bool valid) {
          completed = true;
          accepted = valid;
        });
    transient_bind_group_scheduler.enqueue(
        [&](auto done) {
          dependent_work++;
          done(true);
        },
        [&]() { canceled_work++; });
    if (!require(candidate != nullptr,
                 "Dawn transient-bind-group control did not return a non-null candidate") ||
        !require(completed && accepted == valid_case,
                 "shipping transient-bind-group gate ignored completed scope status") ||
        !require(dependent_work == (valid_case ? 1 : 0) &&
                     canceled_work == (valid_case ? 0 : 1),
                 "shipping transient-bind-group gate released rejected dependent work") ||
        !require(transient_bind_group_scheduler.pending_count() == 0,
                 "shipping transient-bind-group gate left ordered work pending"))
    {
      return 32;
    }
    transient_bind_group_cases++;
  }

  bw::OrderedQueueScheduler transient_texture_scheduler;
  int transient_texture_cases = 0;
  for (const bool valid_case : {false, true}) {
    if (valid_case) {
      transient_texture_scheduler.begin_epoch();
    }
    bool completed = false;
    bool accepted = false;
    int dependent_work = 0;
    int canceled_work = 0;
    const wgpu::Texture candidate = bw::transient_resource_create_scoped(
        instance,
        device,
        transient_texture_scheduler,
        valid_case ? "audit valid transient texture" : "audit invalid transient texture",
        [&]() {
          wgpu::TextureDescriptor descriptor = {};
          descriptor.size = {1, 1, 1};
          descriptor.dimension = wgpu::TextureDimension::e2D;
          descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
          descriptor.mipLevelCount = 1;
          descriptor.sampleCount = 1;
          descriptor.usage = valid_case ? wgpu::TextureUsage::RenderAttachment :
                                          wgpu::TextureUsage::None;
          return device.CreateTexture(&descriptor);
        },
        [&](const bool valid) {
          completed = true;
          accepted = valid;
        });
    transient_texture_scheduler.enqueue(
        [&](auto done) {
          dependent_work++;
          done(true);
        },
        [&]() { canceled_work++; });
    if (!require(candidate != nullptr,
                 "Dawn transient-texture control did not return a non-null candidate") ||
        !require(completed && accepted == valid_case,
                 "shipping transient-texture gate ignored completed scope status") ||
        !require(dependent_work == (valid_case ? 1 : 0) &&
                     canceled_work == (valid_case ? 0 : 1),
                 "shipping transient-texture gate released rejected dependent work") ||
        !require(transient_texture_scheduler.pending_count() == 0,
                 "shipping transient-texture gate left ordered work pending"))
    {
      return 27;
    }
    transient_texture_cases++;
  }

  bw::OrderedQueueScheduler transient_view_scheduler;
  int transient_view_cases = 0;
  for (const bool valid_case : {false, true}) {
    if (valid_case) {
      transient_view_scheduler.begin_epoch();
    }
    bool completed = false;
    bool accepted = false;
    int dependent_work = 0;
    int canceled_work = 0;
    const wgpu::TextureView candidate = bw::transient_resource_create_scoped(
        instance,
        device,
        transient_view_scheduler,
        valid_case ? "audit valid transient texture view" :
                     "audit invalid transient texture view",
        [&]() {
          if (valid_case) {
            return texture.CreateView();
          }
          wgpu::TextureViewDescriptor descriptor = {};
          descriptor.dimension = wgpu::TextureViewDimension::e3D;
          return texture.CreateView(&descriptor);
        },
        [&](const bool valid) {
          completed = true;
          accepted = valid;
        });
    transient_view_scheduler.enqueue(
        [&](auto done) {
          dependent_work++;
          done(true);
        },
        [&]() { canceled_work++; });
    if (!require(candidate != nullptr,
                 "Dawn transient-view control did not return a non-null candidate") ||
        !require(completed && accepted == valid_case,
                 "shipping transient-view gate ignored completed scope status") ||
        !require(dependent_work == (valid_case ? 1 : 0) &&
                     canceled_work == (valid_case ? 0 : 1),
                 "shipping transient-view gate released rejected dependent work") ||
        !require(transient_view_scheduler.pending_count() == 0,
                 "shipping transient-view gate left ordered work pending"))
    {
      return 28;
    }
    transient_view_cases++;
  }

  bw::ScopedHandleCache<uint8_t, TextureViewAllocation> texture_view_pair_cache;
  int texture_view_pair_cases = 0;
  bool invalid_pair_handles_nonnull = false;
  const TextureViewAllocation invalid_pair = texture_view_pair_cache.get_or_create(
      instance, device, uint8_t(0), "audit invalid texture/view pair", [&]() {
        TextureViewAllocation candidate;
        wgpu::TextureDescriptor descriptor = {};
        descriptor.size = {1, 1, 1};
        descriptor.dimension = wgpu::TextureDimension::e2D;
        descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
        descriptor.mipLevelCount = 1;
        descriptor.sampleCount = 1;
        descriptor.usage = wgpu::TextureUsage::None;
        candidate.texture = device.CreateTexture(&descriptor);
        candidate.view = candidate.texture.CreateView();
        invalid_pair_handles_nonnull = candidate.texture != nullptr && candidate.view != nullptr;
        return candidate;
      });
  texture_view_pair_cases++;
  if (!require(invalid_pair == nullptr && invalid_pair_handles_nonnull &&
                   texture_view_pair_cache.size() == 0 &&
                   !texture_view_pair_cache.pending(uint8_t(0)),
               "shipping scoped cache published a non-null texture/view error pair"))
  {
    return 29;
  }

  const TextureViewAllocation valid_pair = texture_view_pair_cache.get_or_create(
      instance, device, uint8_t(0), "audit valid texture/view pair", [&]() {
        TextureViewAllocation candidate;
        wgpu::TextureDescriptor descriptor = {};
        descriptor.size = {1, 1, 1};
        descriptor.dimension = wgpu::TextureDimension::e2D;
        descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
        descriptor.mipLevelCount = 1;
        descriptor.sampleCount = 1;
        descriptor.usage = wgpu::TextureUsage::RenderAttachment;
        candidate.texture = device.CreateTexture(&descriptor);
        candidate.view = candidate.texture.CreateView();
        return candidate;
      });
  texture_view_pair_cases++;
  if (!require(valid_pair != nullptr && texture_view_pair_cache.size() == 1 &&
                   !texture_view_pair_cache.pending(uint8_t(0)),
               "shipping scoped cache did not atomically publish a clean texture/view retry"))
  {
    return 30;
  }

  bw::ScopedHandleCache<uint8_t, LayoutAllocation> layout_pair_cache;
  int layout_pair_cases = 0;
  bool invalid_layout_pair_nonnull = false;
  const LayoutAllocation rejected_layout_pair = layout_pair_cache.get_or_create(
      instance, device, uint8_t(0), "audit invalid layout pair", [&]() {
        wgpu::BindGroupLayoutEntry duplicate_entries[2] = {};
        for (wgpu::BindGroupLayoutEntry &entry : duplicate_entries) {
          entry.binding = 0;
          entry.visibility = wgpu::ShaderStage::Vertex;
          entry.buffer.type = wgpu::BufferBindingType::Uniform;
        }
        wgpu::BindGroupLayoutDescriptor bind_group_descriptor = {};
        bind_group_descriptor.entryCount = 2;
        bind_group_descriptor.entries = duplicate_entries;
        LayoutAllocation candidate;
        candidate.bind_group_layout = device.CreateBindGroupLayout(&bind_group_descriptor);
        wgpu::PipelineLayoutDescriptor pipeline_descriptor = {};
        pipeline_descriptor.bindGroupLayoutCount = 1;
        pipeline_descriptor.bindGroupLayouts = &candidate.bind_group_layout;
        candidate.pipeline_layout = device.CreatePipelineLayout(&pipeline_descriptor);
        invalid_layout_pair_nonnull = candidate.bind_group_layout != nullptr &&
                                      candidate.pipeline_layout != nullptr;
        return candidate;
      });
  layout_pair_cases++;
  if (!require(rejected_layout_pair == nullptr && invalid_layout_pair_nonnull &&
                   layout_pair_cache.size() == 0 &&
                   !layout_pair_cache.pending(uint8_t(0)),
               "shipping scoped cache published a non-null layout error pair"))
  {
    return 33;
  }

  const LayoutAllocation accepted_layout_pair = layout_pair_cache.get_or_create(
      instance, device, uint8_t(0), "audit valid layout pair", [&]() {
        LayoutAllocation candidate;
        wgpu::BindGroupLayoutDescriptor bind_group_descriptor = {};
        candidate.bind_group_layout = device.CreateBindGroupLayout(&bind_group_descriptor);
        wgpu::PipelineLayoutDescriptor pipeline_descriptor = {};
        pipeline_descriptor.bindGroupLayoutCount = 1;
        pipeline_descriptor.bindGroupLayouts = &candidate.bind_group_layout;
        candidate.pipeline_layout = device.CreatePipelineLayout(&pipeline_descriptor);
        return candidate;
      });
  layout_pair_cases++;
  if (!require(accepted_layout_pair != nullptr && layout_pair_cache.size() == 1 &&
                   !layout_pair_cache.pending(uint8_t(0)),
               "shipping scoped cache did not atomically publish a clean layout retry"))
  {
    return 34;
  }

  bw::ScopedHandleCache<uint8_t, ShaderModuleAllocation> shader_module_cache;
  int shader_module_cases = 0;
  bool invalid_shader_set_nonnull = false;
  const ShaderModuleAllocation rejected_shader_set = shader_module_cache.get_or_create(
      instance, device, uint8_t(0), "audit invalid shader module set", [&]() {
        wgpu::ShaderSourceWGSL source = {};
        source.code = "this is still not WGSL";
        wgpu::ShaderModuleDescriptor descriptor = {};
        descriptor.nextInChain = &source;
        ShaderModuleAllocation candidate;
        candidate.vertex = device.CreateShaderModule(&descriptor);
        invalid_shader_set_nonnull = candidate.vertex != nullptr;
        return candidate;
      });
  shader_module_cases++;
  if (!require(rejected_shader_set == nullptr && invalid_shader_set_nonnull &&
                   shader_module_cache.size() == 0 &&
                   !shader_module_cache.pending(uint8_t(0)),
               "shipping scoped cache published a non-null shader-module error set"))
  {
    return 35;
  }

  const ShaderModuleAllocation accepted_shader_set = shader_module_cache.get_or_create(
      instance, device, uint8_t(0), "audit valid shader module set", [&]() {
        ShaderModuleAllocation candidate;
        wgpu::ShaderSourceWGSL vertex_source = {};
        vertex_source.code =
            "@vertex fn vs_main() -> @builtin(position) vec4f { return vec4f(0.0); }";
        wgpu::ShaderModuleDescriptor vertex_descriptor = {};
        vertex_descriptor.nextInChain = &vertex_source;
        candidate.vertex = device.CreateShaderModule(&vertex_descriptor);

        wgpu::ShaderSourceWGSL fragment_source = {};
        fragment_source.code =
            "@fragment fn fs_main() -> @location(0) vec4f { return vec4f(1.0); }";
        wgpu::ShaderModuleDescriptor fragment_descriptor = {};
        fragment_descriptor.nextInChain = &fragment_source;
        candidate.fragment = device.CreateShaderModule(&fragment_descriptor);

        wgpu::ShaderSourceWGSL compute_source = {};
        compute_source.code = "@compute @workgroup_size(1) fn main() {}";
        wgpu::ShaderModuleDescriptor compute_descriptor = {};
        compute_descriptor.nextInChain = &compute_source;
        candidate.compute = device.CreateShaderModule(&compute_descriptor);
        return candidate;
      });
  shader_module_cases++;
  if (!require(accepted_shader_set.vertex != nullptr &&
                   accepted_shader_set.fragment != nullptr &&
                   accepted_shader_set.compute != nullptr && shader_module_cache.size() == 1 &&
                   !shader_module_cache.pending(uint8_t(0)),
               "shipping scoped cache did not atomically publish a clean shader-module retry"))
  {
    return 36;
  }

  bw::ScopedHandleCache<uint8_t, wgpu::RenderPipeline> render_pipeline_cache;
  int render_pipeline_cases = 0;
  bool invalid_render_pipeline_nonnull = false;
  const wgpu::RenderPipeline rejected_render_pipeline = render_pipeline_cache.get_or_create(
      instance, device, uint8_t(0), "audit invalid render pipeline", [&]() {
        wgpu::RenderPipelineDescriptor descriptor = {};
        descriptor.vertex.module = accepted_shader_set.vertex;
        descriptor.vertex.entryPoint = "missing";
        wgpu::RenderPipeline candidate = device.CreateRenderPipeline(&descriptor);
        invalid_render_pipeline_nonnull = candidate != nullptr;
        return candidate;
      });
  render_pipeline_cases++;
  if (!require(rejected_render_pipeline == nullptr && invalid_render_pipeline_nonnull &&
                   render_pipeline_cache.size() == 0 &&
                   !render_pipeline_cache.pending(uint8_t(0)),
               "shipping scoped cache published a non-null render-pipeline error object"))
  {
    return 37;
  }

  const wgpu::RenderPipeline accepted_render_pipeline = render_pipeline_cache.get_or_create(
      instance, device, uint8_t(0), "audit valid render pipeline", [&]() {
        wgpu::ColorTargetState target = {};
        target.format = wgpu::TextureFormat::RGBA8Unorm;
        wgpu::FragmentState fragment = {};
        fragment.module = accepted_shader_set.fragment;
        fragment.entryPoint = "fs_main";
        fragment.targetCount = 1;
        fragment.targets = &target;
        wgpu::RenderPipelineDescriptor descriptor = {};
        descriptor.vertex.module = accepted_shader_set.vertex;
        descriptor.vertex.entryPoint = "vs_main";
        descriptor.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
        descriptor.fragment = &fragment;
        return device.CreateRenderPipeline(&descriptor);
      });
  render_pipeline_cases++;
  if (!require(accepted_render_pipeline != nullptr && render_pipeline_cache.size() == 1 &&
                   !render_pipeline_cache.pending(uint8_t(0)),
               "shipping scoped cache did not publish a clean render-pipeline retry"))
  {
    return 38;
  }

  bw::ScopedHandleCache<std::string, wgpu::ComputePipeline> compute_pipeline_cache;
  int compute_pipeline_cases = 0;
  bool invalid_compute_pipeline_nonnull = false;
  const wgpu::ComputePipeline rejected_compute_pipeline = compute_pipeline_cache.get_or_create(
      instance, device, std::string("default"), "audit invalid compute pipeline", [&]() {
        wgpu::ComputePipelineDescriptor descriptor = {};
        descriptor.compute.module = accepted_shader_set.compute;
        descriptor.compute.entryPoint = "missing";
        wgpu::ComputePipeline candidate = device.CreateComputePipeline(&descriptor);
        invalid_compute_pipeline_nonnull = candidate != nullptr;
        return candidate;
      });
  compute_pipeline_cases++;
  if (!require(rejected_compute_pipeline == nullptr && invalid_compute_pipeline_nonnull &&
                   compute_pipeline_cache.size() == 0 &&
                   !compute_pipeline_cache.pending(std::string("default")),
               "shipping scoped cache published a non-null compute-pipeline error object"))
  {
    return 39;
  }

  const wgpu::ComputePipeline accepted_compute_pipeline = compute_pipeline_cache.get_or_create(
      instance, device, std::string("default"), "audit valid compute pipeline", [&]() {
        wgpu::ComputePipelineDescriptor descriptor = {};
        descriptor.compute.module = accepted_shader_set.compute;
        descriptor.compute.entryPoint = "main";
        return device.CreateComputePipeline(&descriptor);
      });
  compute_pipeline_cases++;
  if (!require(accepted_compute_pipeline != nullptr && compute_pipeline_cache.size() == 1 &&
                   !compute_pipeline_cache.pending(std::string("default")),
               "shipping scoped cache did not publish a clean compute-pipeline retry"))
  {
    return 40;
  }

  /* Dawn keeps returning non-null error objects after ForceLoss; the callback-owned
   * terminal state must therefore override an apparently presentable texture/status pair. */
  const wgpu::Future loss_future = device.GetLostFuture();
  device.ForceLoss(wgpu::DeviceLostReason::Unknown, "blender-web device-loss control");
  if (!require(instance.WaitAny(loss_future, UINT64_MAX) == wgpu::WaitStatus::Success &&
                   loss_state->load(std::memory_order_acquire) == ghost_web::DeviceState::Lost,
               "owned device-loss callback did not publish terminal state"))
  {
    return 42;
  }

  wgpu::TextureDescriptor lost_texture_descriptor = {};
  lost_texture_descriptor.size = {1, 1, 1};
  lost_texture_descriptor.dimension = wgpu::TextureDimension::e2D;
  lost_texture_descriptor.format = wgpu::TextureFormat::RGBA8Unorm;
  lost_texture_descriptor.mipLevelCount = 1;
  lost_texture_descriptor.sampleCount = 1;
  lost_texture_descriptor.usage = wgpu::TextureUsage::RenderAttachment;
  const wgpu::Texture lost_texture = device.CreateTexture(&lost_texture_descriptor);
  const ghost_web::SurfaceAcquireAction apparent_surface_action =
      ghost_web::surface_acquire_action(ghost_web::SurfaceAcquireStatus::SuccessOptimal,
                                        lost_texture != nullptr);
  if (!require(lost_texture != nullptr &&
                   ghost_web::surface_acquire_can_present(apparent_surface_action) &&
                   !ghost_web::device_state_allows_work(
                       loss_state->load(std::memory_order_acquire)),
               "terminal device state did not override a non-null error texture"))
  {
    return 42;
  }

  std::cout << "DAWN_ERROR_HANDLE_AUDIT_PASS cases=" << passed
            << " null_guards_miss_validation=8 scoped_contract=" << scoped_cases
            << " scoped_resize_cases=" << resize_cases
            << " resize_error_object_rejected=1 resize_retry_committed=1"
            << " error_object_submit_rejected=1 gpu_scoped_contract=" << gpu_scoped_cases
            << " gpu_error_object_submit_rejected=1 scoped_sampler_cases=2"
            << " sampler_error_object_rejected=1 scoped_dummy_buffer_cases=2"
            << " dummy_buffer_error_object_rejected=1 scoped_persistent_buffer_cases=2"
            << " persistent_buffer_error_object_rejected=1 scoped_transient_buffer_cases="
            << transient_buffer_cases
            << " transient_buffer_error_object_blocked=1 scoped_transient_bind_group_cases="
            << transient_bind_group_cases
            << " transient_bind_group_error_object_blocked=1 scoped_transient_texture_cases="
            << transient_texture_cases
            << " transient_texture_error_object_blocked=1 scoped_transient_view_cases="
            << transient_view_cases
            << " transient_view_error_object_blocked=1 scoped_texture_view_pair_cases="
            << texture_view_pair_cases
            << " texture_view_pair_error_object_rejected=1 scoped_layout_pair_cases="
            << layout_pair_cases
            << " layout_pair_error_object_rejected=1 scoped_shader_module_cases="
            << shader_module_cases
            << " shader_module_error_object_rejected=1 scoped_render_pipeline_cases="
            << render_pipeline_cases
            << " render_pipeline_error_object_rejected=1 scoped_compute_pipeline_cases="
            << compute_pipeline_cases
            << " compute_pipeline_error_object_rejected=1 device_loss_callback_cases=2"
            << " device_loss_error_texture_blocked=1 SOFTWARE_CONTROL_NON_RECEIPT\n";
  return 0;
}
