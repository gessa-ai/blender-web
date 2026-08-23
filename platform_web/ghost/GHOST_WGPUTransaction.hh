/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#pragma once

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
#include <type_traits>
#include <unordered_map>
#include <utility>

namespace ghost_web {

enum class DrawingContextMode {
  PresentableWindow,
  DeviceOnly,
};

/**
 * Shared validity gate for browser callbacks whose C++ owner is not reference-counted.
 *
 * Emdawnwebgpu resolves fallback adapter/device requests from the same browser event loop that
 * destroys the GHOST context. Each browser callback retains this gate instead of the raw owner;
 * context destruction invalidates it before releasing any other callback state. Delayed
 * completions can therefore discard their handles without touching the dead context.
 */
template<typename OwnerT> class OwnerCallbackLifetime {
 public:
  explicit OwnerCallbackLifetime(OwnerT &owner) : owner_(&owner) {}

  /** Stop future deliveries without waiting for an already-running owner callback. */
  void cancel()
  {
    std::lock_guard lock(mutex_);
    accepting_ = false;
  }

  void invalidate()
  {
    std::unique_lock lock(mutex_);
    accepting_ = false;
    owner_ = nullptr;
    const std::thread::id caller = std::this_thread::get_id();
    idle_.wait(lock, [this, caller]() {
      const auto caller_it = deliveries_by_thread_.find(caller);
      const size_t caller_deliveries = caller_it == deliveries_by_thread_.end() ?
                                           0 :
                                           caller_it->second;
      return active_deliveries_ == caller_deliveries;
    });
  }

  template<typename Callback> bool deliver(Callback &&callback) const
  {
    OwnerT *owner;
    std::thread::id delivery_thread;
    {
      std::lock_guard lock(mutex_);
      owner = owner_;
      if (!accepting_ || owner == nullptr) {
        return false;
      }
      delivery_thread = std::this_thread::get_id();
      active_deliveries_++;
      deliveries_by_thread_[delivery_thread]++;
    }

    ActiveDelivery delivery(*this, delivery_thread);
    std::forward<Callback>(callback)(*owner);
    return true;
  }

 private:
  class ActiveDelivery {
   public:
    ActiveDelivery(const OwnerCallbackLifetime &lifetime, const std::thread::id thread)
        : lifetime_(lifetime), thread_(thread)
    {
    }
    ~ActiveDelivery()
    {
      lifetime_.finish_delivery(thread_);
    }

   private:
    const OwnerCallbackLifetime &lifetime_;
    const std::thread::id thread_;
  };

  void finish_delivery(const std::thread::id thread) const
  {
    std::lock_guard lock(mutex_);
    active_deliveries_--;
    const auto thread_it = deliveries_by_thread_.find(thread);
    if (thread_it != deliveries_by_thread_.end()) {
      if (thread_it->second <= 1) {
        deliveries_by_thread_.erase(thread_it);
      }
      else {
        thread_it->second--;
      }
    }
    idle_.notify_all();
  }

  mutable std::mutex mutex_;
  mutable std::condition_variable idle_;
  mutable size_t active_deliveries_ = 0;
  mutable std::unordered_map<std::thread::id, size_t> deliveries_by_thread_;
  bool accepting_ = true;
  OwnerT *owner_;
};

/** Terminal state shared by callbacks without retaining a GHOST context pointer. */
enum class DeviceState : uint8_t {
  Active,
  Lost,
};

/** Browser-native `GPUDevice.lost` state exported by the pre-main worker. */
enum class ImportedDeviceLossStatus : uint8_t {
  Pending = 0,
  Unknown = 1,
  Destroyed = 2,
};

/** A context may use only the exact still-pending signal bound to its imported device. */
inline DeviceState device_state_after_loss_signal(const DeviceState current,
                                                  const uint32_t bound_generation,
                                                  const uint32_t observed_generation,
                                                  const ImportedDeviceLossStatus status)
{
  if (current == DeviceState::Lost) {
    return DeviceState::Lost;
  }
  if (bound_generation == 0 || observed_generation != bound_generation ||
      status != ImportedDeviceLossStatus::Pending)
  {
    return DeviceState::Lost;
  }
  return DeviceState::Active;
}

/** Callback-safe terminal transition; loss is monotonic and cannot be retried in-place. */
inline void device_state_mark_lost(std::atomic<DeviceState> &state)
{
  state.store(DeviceState::Lost, std::memory_order_release);
}

inline bool device_state_allows_work(const DeviceState state)
{
  return state == DeviceState::Active;
}

struct ImportedDeviceLossObservation {
  uint32_t generation = 0;
  ImportedDeviceLossStatus status = ImportedDeviceLossStatus::Unknown;
};

/**
 * Callback-owned terminal state for either a fallback Dawn device or an imported browser device.
 *
 * An imported device's `GPUDevice.lost` promise lives in JavaScript, so every callback samples
 * that immutable generation binding directly instead of waiting for a later owner-side poll to
 * update the C++ atomic. The first missing, replaced, or settled signal makes loss sticky.
 */
class DeviceCallbackState {
 public:
  using ImportedLossObserver = std::function<ImportedDeviceLossObservation()>;

  DeviceCallbackState() = default;
  DeviceCallbackState(const uint32_t imported_generation, ImportedLossObserver observer)
      : imported_generation_(imported_generation), imported_loss_observer_(std::move(observer))
  {
  }

  DeviceState load(const std::memory_order order) const
  {
    return state_.load(order);
  }

  void mark_lost()
  {
    state_.store(DeviceState::Lost, std::memory_order_release);
  }

  bool allows_work()
  {
    DeviceState current = state_.load(std::memory_order_acquire);
    if (current == DeviceState::Active && imported_loss_observer_) {
      const ImportedDeviceLossObservation observation = imported_loss_observer_();
      current = device_state_after_loss_signal(
          current, imported_generation_, observation.generation, observation.status);
      if (current == DeviceState::Lost) {
        mark_lost();
      }
    }
    return device_state_allows_work(current);
  }

 private:
  std::atomic<DeviceState> state_{DeviceState::Active};
  const uint32_t imported_generation_ = 0;
  const ImportedLossObserver imported_loss_observer_;
};

inline void device_state_mark_lost(DeviceCallbackState &state)
{
  state.mark_lost();
}

/** Browser completions must observe loss directly, before later owner-side cleanup runs. */
inline bool device_state_allows_callback_work(
    const std::shared_ptr<std::atomic<DeviceState>> &state)
{
  return state != nullptr &&
         device_state_allows_work(state->load(std::memory_order_acquire));
}

inline bool device_state_allows_callback_work(
    const std::shared_ptr<DeviceCallbackState> &state)
{
  return state != nullptr && state->allows_work();
}

/** Exact pre-main browser presentation stage observed by synchronous GHOST setup. */
enum class PreinitializedPresentationStatus : uint8_t {
  NotAttempted = 0,
  CanvasUnresolved = 1,
  SurfaceCreationFailed = 2,
  ConfigurationFailed = 3,
  BackbufferFailed = 4,
  Ready = 5,
};

/** WebGPU's exact per-frame surface acquisition result, kept API-neutral for native/wasm tests. */
enum class SurfaceAcquireStatus : uint8_t {
  SuccessOptimal,
  SuccessSuboptimal,
  Timeout,
  Outdated,
  Lost,
  Error,
};

/** Recovery required before a surface texture may reach present command encoding. */
enum class SurfaceAcquireAction : uint8_t {
  Present,
  PresentAndReconfigure,
  Retry,
  Reconfigure,
  Recreate,
};

inline SurfaceAcquireAction surface_acquire_action(const SurfaceAcquireStatus status,
                                                   const bool texture_valid)
{
  if (status == SurfaceAcquireStatus::Timeout) {
    return SurfaceAcquireAction::Retry;
  }
  if (status == SurfaceAcquireStatus::Lost) {
    return SurfaceAcquireAction::Recreate;
  }
  if (!texture_valid) {
    return SurfaceAcquireAction::Reconfigure;
  }
  if (status == SurfaceAcquireStatus::SuccessOptimal) {
    return SurfaceAcquireAction::Present;
  }
  if (status == SurfaceAcquireStatus::SuccessSuboptimal) {
    return SurfaceAcquireAction::PresentAndReconfigure;
  }
  return SurfaceAcquireAction::Reconfigure;
}

inline bool surface_acquire_can_present(const SurfaceAcquireAction action)
{
  return action == SurfaceAcquireAction::Present ||
         action == SurfaceAcquireAction::PresentAndReconfigure;
}

/**
 * A device-only context is valid once its device exists. A presentable window
 * additionally requires the complete pre-main surface transaction and non-zero
 * dimensions; no partial browser setup may satisfy the synchronous GHOST status.
 */
inline bool drawing_context_status_is_ready(
    const DrawingContextMode mode,
    const bool device_ready,
    const PreinitializedPresentationStatus presentation_status,
    const bool surface_valid,
    const bool backbuffer_valid,
    const uint32_t width,
    const uint32_t height)
{
  if (!device_ready) {
    return false;
  }
  if (mode == DrawingContextMode::DeviceOnly) {
    return true;
  }
  return presentation_status == PreinitializedPresentationStatus::Ready && surface_valid &&
         backbuffer_valid && width != 0 && height != 0;
}

enum class SurfaceResizeResult {
  Rejected,
  Superseded,
  Committed,
};

/** Whether the latest requested extent still needs a backbuffer candidate. */
inline bool surface_resize_candidate_needed(const bool configured,
                                            const uint32_t authoritative_width,
                                            const uint32_t authoritative_height,
                                            const uint32_t requested_width,
                                            const uint32_t requested_height,
                                            const bool candidate_pending,
                                            const bool backbuffer_valid,
                                            const uint32_t backbuffer_width,
                                            const uint32_t backbuffer_height)
{
  if (candidate_pending || requested_width == 0 || requested_height == 0) {
    return false;
  }
  return !configured || !backbuffer_valid || authoritative_width != requested_width ||
         authoritative_height != requested_height || backbuffer_width != requested_width ||
         backbuffer_height != requested_height;
}

/**
 * Configure and publish one size-bound surface/backbuffer state only when the
 * validated candidate still matches the latest browser resize request.
 */
template<typename TextureT, typename ConfigureFn>
SurfaceResizeResult surface_resize_commit_if_current(const bool candidate_valid,
                                                      TextureT candidate,
                                                      const uint32_t candidate_width,
                                                      const uint32_t candidate_height,
                                                      const uint32_t requested_width,
                                                      const uint32_t requested_height,
                                                      ConfigureFn &&configure,
                                                      TextureT &r_backbuffer,
                                                      uint32_t &r_backbuffer_width,
                                                      uint32_t &r_backbuffer_height,
                                                      uint32_t &r_authoritative_width,
                                                      uint32_t &r_authoritative_height,
                                                      bool &r_configured)
{
  if (!candidate_valid || candidate == nullptr) {
    return SurfaceResizeResult::Rejected;
  }
  if (candidate_width != requested_width || candidate_height != requested_height) {
    return SurfaceResizeResult::Superseded;
  }

  /* The previous complete state remains published while Configure executes. The
   * caller runs on the WebGPU-owning worker, so the following field publication
   * cannot be observed halfway through this synchronous commit. */
  std::forward<ConfigureFn>(configure)(candidate_width, candidate_height);
  r_backbuffer = std::move(candidate);
  r_backbuffer_width = candidate_width;
  r_backbuffer_height = candidate_height;
  r_authoritative_width = candidate_width;
  r_authoritative_height = candidate_height;
  r_configured = true;
  return SurfaceResizeResult::Committed;
}

/** Require one exact authoritative/surface/backbuffer extent before textureLoad. */
inline bool surface_resize_present_coherent(const bool configured,
                                            const uint32_t authoritative_width,
                                            const uint32_t authoritative_height,
                                            const bool backbuffer_valid,
                                            const uint32_t backbuffer_width,
                                            const uint32_t backbuffer_height,
                                            const uint32_t surface_width,
                                            const uint32_t surface_height)
{
  return configured && authoritative_width != 0 && authoritative_height != 0 &&
         backbuffer_valid && backbuffer_width == authoritative_width &&
         backbuffer_height == authoritative_height && surface_width == authoritative_width &&
         surface_height == authoritative_height;
}

/** Publish drawing-context validity only from the context setter's exact status. */
template<typename StatusT, typename InitializeFn>
bool drawing_context_initialize_if_valid(const StatusT success, InitializeFn &&initialize)
{
  return std::forward<InitializeFn>(initialize)() == success;
}

/**
 * Publish a newly-created window only after its drawing context made the window
 * valid. Invalid windows are destroyed before any manager, callback, or event
 * observes their pointer.
 */
template<typename WindowT, typename DestroyWindowFn, typename PublishWindowFn>
WindowT *window_publish_if_valid(WindowT *window,
                                 DestroyWindowFn &&destroy_window,
                                 PublishWindowFn &&publish_window)
{
  if (window == nullptr) {
    return nullptr;
  }
  if (!window->getValid()) {
    std::forward<DestroyWindowFn>(destroy_window)(window);
    return nullptr;
  }
  std::forward<PublishWindowFn>(publish_window)(window);
  return window;
}

/**
 * Create one handle inside an implementation error scope. A WebGPU implementation may return a
 * non-null error object, so publication is deferred until the scope completes without an error.
 */
template<typename BeginScopeFn, typename CreateFn, typename EndScopeFn, typename CompleteFn>
void scoped_handle_create(BeginScopeFn &&begin_scope,
                          CreateFn &&create,
                          EndScopeFn &&end_scope,
                          CompleteFn &&complete)
{
  std::forward<BeginScopeFn>(begin_scope)();
  auto candidate = std::forward<CreateFn>(create)();
  const bool handle_valid = candidate != nullptr;
  std::forward<EndScopeFn>(end_scope)(
      [candidate = std::move(candidate),
       handle_valid,
       complete = std::forward<CompleteFn>(complete)](const bool scope_valid) mutable {
        complete(handle_valid && scope_valid, std::move(candidate));
      });
}

/**
 * Create the present shader/layout/pipeline dependency chain as one publication
 * transaction. Transient module and pipeline-layout handles stay local; the
 * reusable bind-group layout and pipeline are published only as a valid pair.
 */
template<typename BeginScopeFn,
         typename CreateShaderModuleFn,
         typename CreateBindGroupLayoutFn,
         typename CreatePipelineLayoutFn,
         typename CreatePipelineFn,
         typename EndScopeFn,
         typename CompleteFn>
void present_pipeline_create_scoped(
    BeginScopeFn &&begin_scope,
    CreateShaderModuleFn &&create_shader_module,
    CreateBindGroupLayoutFn &&create_bind_group_layout,
    CreatePipelineLayoutFn &&create_pipeline_layout,
    CreatePipelineFn &&create_pipeline,
    EndScopeFn &&end_scope,
    CompleteFn &&complete)
{
  using ShaderModuleT = std::decay_t<decltype(create_shader_module())>;
  using BindGroupLayoutT = std::decay_t<decltype(create_bind_group_layout())>;
  using PipelineLayoutT = std::decay_t<decltype(
      create_pipeline_layout(std::declval<const BindGroupLayoutT &>()))>;
  using PipelineT = std::decay_t<decltype(create_pipeline(
      std::declval<const ShaderModuleT &>(), std::declval<const PipelineLayoutT &>()))>;

  std::forward<BeginScopeFn>(begin_scope)();
  ShaderModuleT shader_module = std::forward<CreateShaderModuleFn>(create_shader_module)();
  BindGroupLayoutT bind_group_layout;
  PipelineLayoutT pipeline_layout;
  PipelineT pipeline;
  bool handles_valid = shader_module != nullptr;
  if (handles_valid) {
    bind_group_layout = std::forward<CreateBindGroupLayoutFn>(create_bind_group_layout)();
    handles_valid = bind_group_layout != nullptr;
  }
  if (handles_valid) {
    pipeline_layout =
        std::forward<CreatePipelineLayoutFn>(create_pipeline_layout)(bind_group_layout);
    handles_valid = pipeline_layout != nullptr;
  }
  if (handles_valid) {
    pipeline = std::forward<CreatePipelineFn>(create_pipeline)(shader_module, pipeline_layout);
    handles_valid = pipeline != nullptr;
  }

  std::forward<EndScopeFn>(end_scope)(
      [shader_module = std::move(shader_module),
       bind_group_layout = std::move(bind_group_layout),
       pipeline_layout = std::move(pipeline_layout),
       pipeline = std::move(pipeline),
       handles_valid,
       complete = std::forward<CompleteFn>(complete)](const bool scope_valid) mutable {
        /* Retain the complete dependency chain until the scope reports its result. */
        (void)shader_module;
        (void)pipeline_layout;
        complete(scope_valid && handles_valid,
                 std::move(bind_group_layout),
                 std::move(pipeline));
      });
}

/**
 * Encode and submit one present pass only after every transient resource and
 * command handle is valid. A failure discards the local encoder and any work it
 * already contains; only the complete command buffer reaches the queue.
 */
template<typename BeginEncodeScopeFn,
         typename CreateSourceViewFn,
         typename CreateTargetViewFn,
         typename CreateBindGroupFn,
         typename CreateCommandEncoderFn,
         typename BeginRenderPassFn,
         typename EncodePassFn,
         typename EndEncodeScopeFn,
         typename BeginSubmitScopeFn,
         typename SubmitFn,
         typename EndSubmitScopeFn,
         typename CompleteFn>
void present_frame_encode_submit_scoped(
    BeginEncodeScopeFn &&begin_encode_scope,
    CreateSourceViewFn &&create_source_view,
    CreateTargetViewFn &&create_target_view,
    CreateBindGroupFn &&create_bind_group,
    CreateCommandEncoderFn &&create_command_encoder,
    BeginRenderPassFn &&begin_render_pass,
    EncodePassFn &&encode_pass,
    EndEncodeScopeFn &&end_encode_scope,
    BeginSubmitScopeFn &&begin_submit_scope,
    SubmitFn &&submit,
    EndSubmitScopeFn &&end_submit_scope,
    CompleteFn &&complete)
{
  using CommandEncoderT = std::decay_t<decltype(create_command_encoder())>;
  using CommandBufferT = std::decay_t<decltype(std::declval<CommandEncoderT &>().Finish())>;

  std::forward<BeginEncodeScopeFn>(begin_encode_scope)();
  auto source_view = std::forward<CreateSourceViewFn>(create_source_view)();
  using SourceViewT = std::decay_t<decltype(source_view)>;
  using TargetViewT = std::decay_t<decltype(create_target_view())>;
  using BindGroupT = std::decay_t<decltype(create_bind_group(
      std::declval<const SourceViewT &>()))>;
  using RenderPassT = std::decay_t<decltype(begin_render_pass(
      std::declval<CommandEncoderT &>(), std::declval<const TargetViewT &>()))>;

  TargetViewT target_view;
  BindGroupT bind_group;
  CommandEncoderT encoder;
  RenderPassT pass;
  CommandBufferT command_buffer;
  bool handles_valid = source_view != nullptr;
  if (handles_valid) {
    target_view = std::forward<CreateTargetViewFn>(create_target_view)();
    handles_valid = target_view != nullptr;
  }
  if (handles_valid) {
    bind_group = std::forward<CreateBindGroupFn>(create_bind_group)(source_view);
    handles_valid = bind_group != nullptr;
  }
  if (handles_valid) {
    encoder = std::forward<CreateCommandEncoderFn>(create_command_encoder)();
    handles_valid = encoder != nullptr;
  }
  if (handles_valid) {
    pass = std::forward<BeginRenderPassFn>(begin_render_pass)(encoder, target_view);
    handles_valid = pass != nullptr;
  }
  if (handles_valid) {
    std::forward<EncodePassFn>(encode_pass)(pass, bind_group);
    pass.End();
    command_buffer = encoder.Finish();
    handles_valid = command_buffer != nullptr;
  }

  std::forward<EndEncodeScopeFn>(end_encode_scope)(
      [source_view = std::move(source_view),
       target_view = std::move(target_view),
       bind_group = std::move(bind_group),
       encoder = std::move(encoder),
       pass = std::move(pass),
       command_buffer = std::move(command_buffer),
       handles_valid,
       begin_submit_scope = std::forward<BeginSubmitScopeFn>(begin_submit_scope),
       submit = std::forward<SubmitFn>(submit),
       end_submit_scope = std::forward<EndSubmitScopeFn>(end_submit_scope),
       complete = std::forward<CompleteFn>(complete)](const bool encode_scope_valid) mutable {
        /* Retain all encoded dependencies until the first scope has completed. */
        (void)source_view;
        (void)target_view;
        (void)bind_group;
        (void)encoder;
        (void)pass;
        if (!handles_valid || !encode_scope_valid) {
          complete(false);
          return;
        }

        begin_submit_scope();
        submit(command_buffer);
        end_submit_scope(
            [command_buffer = std::move(command_buffer),
             complete = std::move(complete)](const bool submit_scope_valid) mutable {
              /* Queue submission can itself report validation asynchronously. */
              (void)command_buffer;
              complete(submit_scope_valid);
            });
      });
}

}  // namespace ghost_web
