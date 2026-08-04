/* SPDX-FileCopyrightText: 2022-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from intern/ghost/intern/GHOST_ContextVK.cc @ fbe6228777e7 */

/** \file
 * \ingroup GHOST
 */

#include "GHOST_ContextWGPU.hh"

#include <cstdint>

GHOST_ContextWGPU::GHOST_ContextWGPU(const GHOST_ContextParams &context_params)
    : GHOST_Context(context_params)
{
}

GHOST_ContextWGPU::~GHOST_ContextWGPU() {}

GHOST_TSuccess GHOST_ContextWGPU::initializeDrawingContext()
{
  /* Headless (no surface) native Dawn bring-up on Metal — identical shape to the
   * T1 probe (sandbox/dawn-probe/probe.cc), driven synchronously via WaitAny. */
  wgpu::InstanceDescriptor instance_desc = {};
  static constexpr auto kTimedWaitAny = wgpu::InstanceFeatureName::TimedWaitAny;
  instance_desc.requiredFeatureCount = 1;
  instance_desc.requiredFeatures = &kTimedWaitAny;
  instance_ = wgpu::CreateInstance(&instance_desc);
  if (instance_ == nullptr) {
    return GHOST_kFailure;
  }

  wgpu::RequestAdapterOptions adapter_opts = {};
  adapter_opts.backendType = wgpu::BackendType::Metal;
  adapter_opts.featureLevel = wgpu::FeatureLevel::Core;
  instance_.WaitAny(
      instance_.RequestAdapter(
          &adapter_opts,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestAdapterStatus status, wgpu::Adapter a, wgpu::StringView /*msg*/) {
            if (status == wgpu::RequestAdapterStatus::Success) {
              adapter_ = std::move(a);
            }
          }),
      UINT64_MAX);
  if (adapter_ == nullptr) {
    return GHOST_kFailure;
  }

  wgpu::AdapterInfo info;
  adapter_.GetInfo(&info);
  if (info.device.data != nullptr) {
    const size_t len = (info.device.length == WGPU_STRLEN) ?
                           std::char_traits<char>::length(info.device.data) :
                           info.device.length;
    adapter_name_.assign(info.device.data, len);
  }

  wgpu::DeviceDescriptor device_desc = {};
  device_desc.SetUncapturedErrorCallback(
      [](const wgpu::Device &, wgpu::ErrorType, wgpu::StringView /*msg*/) {});
  instance_.WaitAny(
      adapter_.RequestDevice(
          &device_desc,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestDeviceStatus status, wgpu::Device d, wgpu::StringView /*msg*/) {
            if (status == wgpu::RequestDeviceStatus::Success) {
              device_ = std::move(d);
            }
          }),
      UINT64_MAX);
  if (device_ == nullptr) {
    return GHOST_kFailure;
  }
  queue_ = device_.GetQueue();
  return GHOST_kSuccess;
}

/* Offscreen headless context: no swap-chain, so acquire/release are success
 * no-ops; the WebGPU backend submits directly to the queue. */
GHOST_TSuccess GHOST_ContextWGPU::swapBufferAcquire()
{
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPU::swapBufferRelease()
{
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPU::activateDrawingContext()
{
  active_context_ = this;
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPU::releaseDrawingContext()
{
  if (active_context_ == this) {
    active_context_ = nullptr;
  }
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPU::releaseNativeHandles()
{
  return GHOST_kSuccess;
}
