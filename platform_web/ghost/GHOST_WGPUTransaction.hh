/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#pragma once

#include <cstdint>
#include <type_traits>
#include <utility>

namespace ghost_web {

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
