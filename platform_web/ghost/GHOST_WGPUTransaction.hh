/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#pragma once

#include <cstdint>
#include <utility>

namespace ghost_web {

/** Replace a size-bound texture only after its complete WebGPU handle exists. */
template<typename TextureT, typename CreateTextureFn>
bool texture_replace_if_valid(CreateTextureFn &&create_texture,
                              TextureT &r_texture,
                              const uint32_t width,
                              const uint32_t height,
                              uint32_t &r_width,
                              uint32_t &r_height)
{
  TextureT texture = std::forward<CreateTextureFn>(create_texture)();
  if (texture == nullptr) {
    return false;
  }
  r_texture = std::move(texture);
  r_width = width;
  r_height = height;
  return true;
}

/**
 * Create the present shader/layout/pipeline dependency chain as one publication
 * transaction. Transient module and pipeline-layout handles stay local; the
 * reusable bind-group layout and pipeline are published only as a valid pair.
 */
template<typename BindGroupLayoutT,
         typename PipelineT,
         typename CreateShaderModuleFn,
         typename CreateBindGroupLayoutFn,
         typename CreatePipelineLayoutFn,
         typename CreatePipelineFn>
bool present_pipeline_create_if_valid(
    CreateShaderModuleFn &&create_shader_module,
    CreateBindGroupLayoutFn &&create_bind_group_layout,
    CreatePipelineLayoutFn &&create_pipeline_layout,
    CreatePipelineFn &&create_pipeline,
    BindGroupLayoutT &r_bind_group_layout,
    PipelineT &r_pipeline)
{
  auto shader_module = std::forward<CreateShaderModuleFn>(create_shader_module)();
  if (shader_module == nullptr) {
    return false;
  }
  BindGroupLayoutT bind_group_layout =
      std::forward<CreateBindGroupLayoutFn>(create_bind_group_layout)();
  if (bind_group_layout == nullptr) {
    return false;
  }
  auto pipeline_layout =
      std::forward<CreatePipelineLayoutFn>(create_pipeline_layout)(bind_group_layout);
  if (pipeline_layout == nullptr) {
    return false;
  }
  PipelineT pipeline =
      std::forward<CreatePipelineFn>(create_pipeline)(shader_module, pipeline_layout);
  if (pipeline == nullptr) {
    return false;
  }
  r_bind_group_layout = std::move(bind_group_layout);
  r_pipeline = std::move(pipeline);
  return true;
}

/**
 * Encode and submit one present pass only after every transient resource and
 * command handle is valid. A failure discards the local encoder and any work it
 * already contains; only the complete command buffer reaches the queue.
 */
template<typename CreateSourceViewFn,
         typename CreateTargetViewFn,
         typename CreateBindGroupFn,
         typename CreateCommandEncoderFn,
         typename BeginRenderPassFn,
         typename EncodePassFn,
         typename SubmitFn>
bool present_frame_encode_submit_if_valid(
    CreateSourceViewFn &&create_source_view,
    CreateTargetViewFn &&create_target_view,
    CreateBindGroupFn &&create_bind_group,
    CreateCommandEncoderFn &&create_command_encoder,
    BeginRenderPassFn &&begin_render_pass,
    EncodePassFn &&encode_pass,
    SubmitFn &&submit)
{
  auto source_view = std::forward<CreateSourceViewFn>(create_source_view)();
  if (source_view == nullptr) {
    return false;
  }
  auto target_view = std::forward<CreateTargetViewFn>(create_target_view)();
  if (target_view == nullptr) {
    return false;
  }
  auto bind_group = std::forward<CreateBindGroupFn>(create_bind_group)(source_view);
  if (bind_group == nullptr) {
    return false;
  }
  auto encoder = std::forward<CreateCommandEncoderFn>(create_command_encoder)();
  if (encoder == nullptr) {
    return false;
  }
  auto pass = std::forward<BeginRenderPassFn>(begin_render_pass)(encoder, target_view);
  if (pass == nullptr) {
    return false;
  }
  std::forward<EncodePassFn>(encode_pass)(pass, bind_group);
  pass.End();
  auto command_buffer = encoder.Finish();
  if (command_buffer == nullptr) {
    return false;
  }
  std::forward<SubmitFn>(submit)(command_buffer);
  return true;
}

}  // namespace ghost_web
