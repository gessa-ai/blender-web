/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm contract for the exact shipping mipmap resource
 * transaction. WebGPU handles are deterministic fakes; no instance, adapter,
 * device, texture, pass, or command buffer is created. */

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>

#ifndef BW_WGPU_MIPMAP_SOURCE
#  error "BW_WGPU_MIPMAP_SOURCE must name the extracted shipping method"
#endif

namespace mipmap_contract {

enum GPUTextureType : uint8_t {
  GPU_TEXTURE_1D,
  GPU_TEXTURE_1D_ARRAY,
  GPU_TEXTURE_2D,
  GPU_TEXTURE_2D_ARRAY,
  GPU_TEXTURE_3D,
  GPU_TEXTURE_CUBE,
  GPU_TEXTURE_CUBE_ARRAY,
};

constexpr uint32_t GPU_FORMAT_INTEGER = 1u << 0;
constexpr uint32_t GPU_FORMAT_SIGNED = 1u << 1;

template<typename T, typename... Candidates>
bool elem(const T &value, const Candidates &...candidates)
{
  return ((value == candidates) || ...);
}

enum class Repr : uint8_t {
  F32,
  Snorm16,
  Compressed,
  Depth32F,
  Depth32FS8,
  Unsupported,
};

inline Repr repr_of(int /*format*/)
{
  return Repr::F32;
}

inline const char *mipmap_float_shader_source()
{
  return "@vertex fn vs_main() {} @fragment fn fs_main() {}";
}

enum class Failure : uint8_t {
  None,
  Module,
  Pipeline,
  Encoder,
  SourceView,
  DestinationView,
  BindGroup,
  Pass,
  Finish,
};

struct Trace {
  Failure failure = Failure::None;
  uint32_t fail_call = 0;
  uint32_t module_calls = 0;
  uint32_t pipeline_calls = 0;
  uint32_t encoder_calls = 0;
  uint32_t source_view_calls = 0;
  uint32_t destination_view_calls = 0;
  uint32_t bind_group_calls = 0;
  uint32_t pass_calls = 0;
  uint32_t pipeline_sets = 0;
  uint32_t bind_group_sets = 0;
  uint32_t draws = 0;
  uint32_t pass_ends = 0;
  uint32_t finish_calls = 0;
  uint32_t submit_calls = 0;
  uint32_t invalid_uses = 0;
};

namespace wgpu {

enum class TextureUsage : uint32_t {
  TextureBinding = 1u << 0,
  RenderAttachment = 1u << 1,
};

inline uint32_t operator&(const uint32_t usage, const TextureUsage flag)
{
  return usage & uint32_t(flag);
}

enum class TextureFormat : uint8_t { Undefined, RGBA8Unorm };
enum class ColorWriteMask : uint8_t { All };
enum class PrimitiveTopology : uint8_t { TriangleList };
enum class LoadOp : uint8_t { Clear };
enum class StoreOp : uint8_t { Store };

template<typename Tag> class Handle {
 public:
  Handle() = default;
  Handle(std::nullptr_t) {}
  Handle(Trace *trace, const bool valid) : trace_(trace), valid_(valid) {}

  Handle &operator=(std::nullptr_t)
  {
    trace_ = nullptr;
    valid_ = false;
    return *this;
  }

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  bool valid() const
  {
    return valid_;
  }

  Trace *trace() const
  {
    return trace_;
  }

 protected:
  Trace *trace_ = nullptr;
  bool valid_ = false;
};

struct ShaderModuleTag;
struct TextureViewTag;
struct BindGroupTag;
struct BindGroupLayoutTag;
struct CommandBufferTag;

using ShaderModule = Handle<ShaderModuleTag>;
using TextureView = Handle<TextureViewTag>;
using BindGroup = Handle<BindGroupTag>;
using BindGroupLayout = Handle<BindGroupLayoutTag>;
using CommandBuffer = Handle<CommandBufferTag>;

struct ShaderSourceWGSL {
  const char *code = nullptr;
};

struct ShaderModuleDescriptor {
  const ShaderSourceWGSL *nextInChain = nullptr;
};

struct ColorTargetState {
  TextureFormat format = TextureFormat::Undefined;
  ColorWriteMask writeMask = ColorWriteMask::All;
};

struct FragmentState {
  ShaderModule module;
  const char *entryPoint = nullptr;
  size_t targetCount = 0;
  const ColorTargetState *targets = nullptr;
};

struct RenderPipelineDescriptor {
  BindGroupLayout layout;
  struct {
    ShaderModule module;
    const char *entryPoint = nullptr;
  } vertex;
  struct {
    PrimitiveTopology topology = PrimitiveTopology::TriangleList;
  } primitive;
  const FragmentState *fragment = nullptr;
};

class RenderPipeline : public Handle<struct RenderPipelineTag> {
 public:
  using Handle::Handle;

  BindGroupLayout GetBindGroupLayout(uint32_t /*index*/) const
  {
    if (!valid_) {
      trace_->invalid_uses++;
      return {};
    }
    return BindGroupLayout(trace_, true);
  }
};

struct BindGroupEntry {
  uint32_t binding = 0;
  TextureView textureView;
};

struct BindGroupDescriptor {
  BindGroupLayout layout;
  size_t entryCount = 0;
  const BindGroupEntry *entries = nullptr;
};

struct RenderPassColorAttachment {
  TextureView view;
  LoadOp loadOp = LoadOp::Clear;
  StoreOp storeOp = StoreOp::Store;
};

struct RenderPassDescriptor {
  size_t colorAttachmentCount = 0;
  const RenderPassColorAttachment *colorAttachments = nullptr;
};

class RenderPassEncoder : public Handle<struct RenderPassEncoderTag> {
 public:
  using Handle::Handle;

  void SetPipeline(const RenderPipeline &pipeline)
  {
    trace_->pipeline_sets++;
    if (!valid_ || pipeline == nullptr) {
      trace_->invalid_uses++;
    }
  }

  void SetBindGroup(uint32_t /*index*/, const BindGroup &group)
  {
    trace_->bind_group_sets++;
    if (!valid_ || group == nullptr) {
      trace_->invalid_uses++;
    }
  }

  void Draw(uint32_t /*vertices*/,
            uint32_t /*instances*/,
            uint32_t /*first_vertex*/,
            uint32_t /*first_instance*/)
  {
    trace_->draws++;
    if (!valid_) {
      trace_->invalid_uses++;
    }
  }

  void End()
  {
    trace_->pass_ends++;
    if (!valid_) {
      trace_->invalid_uses++;
    }
  }
};

class CommandEncoder : public Handle<struct CommandEncoderTag> {
 public:
  using Handle::Handle;

  RenderPassEncoder BeginRenderPass(const RenderPassDescriptor *descriptor)
  {
    trace_->pass_calls++;
    const bool inputs_valid = descriptor != nullptr && descriptor->colorAttachmentCount == 1 &&
                              descriptor->colorAttachments != nullptr &&
                              descriptor->colorAttachments[0].view != nullptr;
    if (!valid_ || !inputs_valid) {
      trace_->invalid_uses++;
      return RenderPassEncoder(trace_, false);
    }
    const bool valid = !(trace_->failure == Failure::Pass &&
                         trace_->pass_calls - 1 == trace_->fail_call);
    return RenderPassEncoder(trace_, valid);
  }

  CommandBuffer Finish()
  {
    trace_->finish_calls++;
    if (!valid_) {
      trace_->invalid_uses++;
      return CommandBuffer(trace_, false);
    }
    return CommandBuffer(trace_, trace_->failure != Failure::Finish);
  }
};

class Device {
 public:
  explicit Device(Trace *trace = nullptr) : trace_(trace) {}

  ShaderModule CreateShaderModule(const ShaderModuleDescriptor *descriptor) const
  {
    trace_->module_calls++;
    const bool inputs_valid = descriptor != nullptr && descriptor->nextInChain != nullptr &&
                              descriptor->nextInChain->code != nullptr;
    return ShaderModule(trace_, inputs_valid && trace_->failure != Failure::Module);
  }

  RenderPipeline CreateRenderPipeline(const RenderPipelineDescriptor *descriptor) const
  {
    trace_->pipeline_calls++;
    const bool inputs_valid = descriptor != nullptr && descriptor->vertex.module != nullptr &&
                              descriptor->fragment != nullptr &&
                              descriptor->fragment->module != nullptr;
    if (!inputs_valid) {
      trace_->invalid_uses++;
    }
    return RenderPipeline(
        trace_, inputs_valid && trace_->failure != Failure::Pipeline);
  }

  CommandEncoder CreateCommandEncoder() const
  {
    trace_->encoder_calls++;
    return CommandEncoder(trace_, trace_->failure != Failure::Encoder);
  }

  BindGroup CreateBindGroup(const BindGroupDescriptor *descriptor) const
  {
    trace_->bind_group_calls++;
    const bool inputs_valid = descriptor != nullptr && descriptor->layout != nullptr &&
                              descriptor->entryCount == 1 && descriptor->entries != nullptr &&
                              descriptor->entries[0].textureView != nullptr;
    if (!inputs_valid) {
      trace_->invalid_uses++;
    }
    const bool failed = trace_->failure == Failure::BindGroup &&
                        trace_->bind_group_calls - 1 == trace_->fail_call;
    return BindGroup(trace_, inputs_valid && !failed);
  }

 private:
  Trace *trace_ = nullptr;
};

class Queue {
 public:
  explicit Queue(Trace *trace = nullptr) : trace_(trace) {}

  void Submit(size_t /*count*/, const CommandBuffer *commands)
  {
    trace_->submit_calls++;
    if (commands == nullptr || *commands == nullptr) {
      trace_->invalid_uses++;
    }
  }

 private:
  Trace *trace_ = nullptr;
};

class Texture {
 public:
  uint32_t GetUsage() const
  {
    return uint32_t(TextureUsage::TextureBinding) | uint32_t(TextureUsage::RenderAttachment);
  }
};

}  // namespace wgpu

class WGPUContext {
 public:
  explicit WGPUContext(Trace &trace) : device_(&trace), queue_(&trace) {}

  wgpu::Device device_get()
  {
    return device_;
  }

  wgpu::Queue &queue_get()
  {
    return queue_;
  }

 private:
  wgpu::Device device_;
  wgpu::Queue queue_;
};

static WGPUContext *active_context_value = nullptr;

static WGPUContext *active_context()
{
  return active_context_value;
}

class MipmapHarness {
 public:
  explicit MipmapHarness(Trace &trace) : trace_(trace) {}

  void generate_mipmap();

 private:
  bool is_texture_view() const
  {
    return false;
  }

  wgpu::TextureView sampled_attachment_view(int /*mip*/, int /*layer*/)
  {
    const uint32_t call = trace_.source_view_calls++;
    const bool failed = trace_.failure == Failure::SourceView && call == trace_.fail_call;
    return wgpu::TextureView(&trace_, !failed);
  }

  wgpu::TextureView attachment_view(int /*mip*/, int /*layer*/)
  {
    const uint32_t call = trace_.destination_view_calls++;
    const bool failed = trace_.failure == Failure::DestinationView && call == trace_.fail_call;
    return wgpu::TextureView(&trace_, !failed);
  }

  struct Subresources {
    bool valid() const
    {
      return true;
    }

    uint32_t mip_count = 3;
    uint32_t layer_count = 2;
    wgpu::Texture texture;
    wgpu::TextureFormat view_format = wgpu::TextureFormat::RGBA8Unorm;
  } subresources_;

  Trace &trace_;
  GPUTextureType type_ = GPU_TEXTURE_2D_ARRAY;
  bool snorm16_emulated_ = false;
  int format_ = 0;
  uint32_t format_flag_ = 0;
};

}  // namespace mipmap_contract

#define BLI_assert_msg(condition, message) \
  do {                                      \
    if (!(condition)) {                     \
      std::abort();                         \
    }                                       \
  } while (false)
#define ELEM(value, ...) ::mipmap_contract::elem(value, __VA_ARGS__)
#include BW_WGPU_MIPMAP_SOURCE
#undef ELEM
#undef BLI_assert_msg

namespace {

bool require_mipmap(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL mipmap-resource %s\n", message);
    return false;
  }
  return true;
}

mipmap_contract::Trace run_mipmap_case(const mipmap_contract::Failure failure,
                                       const uint32_t fail_call = 0)
{
  mipmap_contract::Trace trace;
  trace.failure = failure;
  trace.fail_call = fail_call;
  mipmap_contract::WGPUContext context(trace);
  mipmap_contract::active_context_value = &context;
  mipmap_contract::MipmapHarness texture(trace);
  texture.generate_mipmap();
  mipmap_contract::active_context_value = nullptr;
  return trace;
}

}  // namespace

bool run_integrated_mipmap_resource_contracts()
{
  using mipmap_contract::Failure;
  using mipmap_contract::Trace;

  const Trace module = run_mipmap_case(Failure::Module);
  if (!require_mipmap(module.module_calls == 1 && module.pipeline_calls == 0 &&
                          module.invalid_uses == 0 && module.submit_calls == 0,
                      "module failure stops before pipeline creation"))
  {
    return false;
  }

  const Trace pipeline = run_mipmap_case(Failure::Pipeline);
  if (!require_mipmap(pipeline.pipeline_calls == 1 && pipeline.encoder_calls == 0 &&
                          pipeline.invalid_uses == 0 && pipeline.submit_calls == 0,
                      "pipeline failure stops before encoder creation"))
  {
    return false;
  }

  const Trace encoder = run_mipmap_case(Failure::Encoder);
  if (!require_mipmap(encoder.encoder_calls == 1 && encoder.source_view_calls == 0 &&
                          encoder.invalid_uses == 0 && encoder.submit_calls == 0,
                      "encoder failure stops before subresource work"))
  {
    return false;
  }

  const Trace source_view = run_mipmap_case(Failure::SourceView, 1);
  if (!require_mipmap(source_view.pass_ends == 1 && source_view.finish_calls == 0 &&
                          source_view.invalid_uses == 0 && source_view.submit_calls == 0,
                      "source-view failure discards earlier encoded passes"))
  {
    return false;
  }

  const Trace destination_view = run_mipmap_case(Failure::DestinationView, 1);
  if (!require_mipmap(destination_view.pass_ends == 1 && destination_view.finish_calls == 0 &&
                          destination_view.invalid_uses == 0 && destination_view.submit_calls == 0,
                      "destination-view failure discards earlier encoded passes"))
  {
    return false;
  }

  const Trace bind_group = run_mipmap_case(Failure::BindGroup, 1);
  if (!require_mipmap(bind_group.bind_group_calls == 2 && bind_group.pass_calls == 1 &&
                          bind_group.finish_calls == 0 && bind_group.invalid_uses == 0 &&
                          bind_group.submit_calls == 0,
                      "bind-group failure stops before its render pass"))
  {
    return false;
  }

  const Trace pass = run_mipmap_case(Failure::Pass, 1);
  if (!require_mipmap(pass.pass_calls == 2 && pass.pass_ends == 1 && pass.finish_calls == 0 &&
                          pass.invalid_uses == 0 && pass.submit_calls == 0,
                      "render-pass failure discards the encoder"))
  {
    return false;
  }

  const Trace finish = run_mipmap_case(Failure::Finish);
  if (!require_mipmap(finish.pass_ends == 4 && finish.finish_calls == 1 &&
                          finish.invalid_uses == 0 && finish.submit_calls == 0,
                      "command-buffer failure stops before submission"))
  {
    return false;
  }

  const Trace success = run_mipmap_case(Failure::None);
  if (!require_mipmap(success.module_calls == 1 && success.pipeline_calls == 1 &&
                          success.encoder_calls == 1 && success.source_view_calls == 4 &&
                          success.destination_view_calls == 4 && success.bind_group_calls == 4 &&
                          success.pass_calls == 4 && success.pipeline_sets == 4 &&
                          success.bind_group_sets == 4 && success.draws == 4 &&
                          success.pass_ends == 4 && success.finish_calls == 1 &&
                          success.submit_calls == 1 && success.invalid_uses == 0,
                      "successful two-layer three-mip chain submits exactly once"))
  {
    return false;
  }

  std::printf(
      "CONTRACT mipmap-resource-transaction PASS cases=9 passes=4 fail-before-submit=8\n");
  return true;
}
