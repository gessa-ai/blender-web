// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M3.T3 verify — drive the real GHOST_ContextWGPU (compiled against Blender's
// own GHOST headers) through the offscreen bring-up path a headless
// GHOST_SystemHeadless::createOffscreenContext would use, and confirm a live
// hardware WGPUDevice + adapter name. This is the sandbox standalone-main form
// of the T3 gate (the full gpu-test-binary form is wired by the product patches).

#include "GHOST_ContextWGPU.hh"
#include "probe_platform.hh"

#include <cstdio>
#include <string>
#include <utility>

namespace {

std::string string_view(wgpu::StringView value)
{
  if (value.data == nullptr) {
    return {};
  }
  if (value.length == WGPU_STRLEN) {
    return std::string(value.data);
  }
  return std::string(value.data, value.length);
}

bool require_hardware_adapter(const wgpu::Adapter &adapter, const char *phase)
{
  if (adapter == nullptr) {
    fprintf(stderr, "T3 %s adapter is null\n", phase);
    return false;
  }

  wgpu::AdapterInfo info = {};
  adapter.GetInfo(&info);
  const std::string device = string_view(info.device);
  if (!blender_web::dawn_probe::is_hardware_adapter(info)) {
    fprintf(stderr,
            "PROBE_BLOCKED: refusing non-hardware %s adapter phase=%s type=%u device=%s\n",
            blender_web::dawn_probe::kBackendName,
            phase,
            unsigned(info.adapterType),
            device.c_str());
    return false;
  }
  return true;
}

bool require_hardware_preflight()
{
  wgpu::InstanceDescriptor instance_desc = {};
  static constexpr auto kTimedWaitAny = wgpu::InstanceFeatureName::TimedWaitAny;
  instance_desc.requiredFeatureCount = 1;
  instance_desc.requiredFeatures = &kTimedWaitAny;
  wgpu::Instance instance = wgpu::CreateInstance(&instance_desc);
  if (instance == nullptr) {
    fprintf(stderr, "T3 preflight CreateInstance failed\n");
    return false;
  }

  wgpu::RequestAdapterOptions options = {};
  options.backendType = blender_web::dawn_probe::kBackendType;
  options.featureLevel = wgpu::FeatureLevel::Core;
  wgpu::Adapter adapter;
  std::string failure;
  instance.WaitAny(
      instance.RequestAdapter(
          &options,
          wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestAdapterStatus status, wgpu::Adapter candidate, wgpu::StringView msg) {
            if (status == wgpu::RequestAdapterStatus::Success) {
              adapter = std::move(candidate);
            }
            else {
              failure = string_view(msg);
            }
          }),
      UINT64_MAX);
  if (adapter == nullptr) {
    fprintf(stderr, "T3 preflight RequestAdapter failed: %s\n", failure.c_str());
    return false;
  }

  return require_hardware_adapter(adapter, "preflight");
}

}  // namespace

int main()
{
  if (!require_hardware_preflight()) {
    return 77;
  }

  GHOST_ContextParams params = {};  // offscreen defaults; no window/surface.
  GHOST_ContextWGPU ctx(params);

  if (ctx.initializeDrawingContext() != GHOST_kSuccess) {
    fprintf(stderr, "GHOST_ContextWGPU::initializeDrawingContext FAILED\n");
    return 1;
  }
  /* The preflight and context make independent RequestAdapter calls. A host
   * can expose more than one adapter, so eligibility of the first does not
   * prove that the device under test came from hardware. */
  if (!require_hardware_adapter(ctx.getAdapter(), "context")) {
    return 78;
  }
  printf("GHOST_ContextWGPU adapter: %s\n", ctx.getAdapterName());

  if (ctx.getDevice() == nullptr || ctx.getQueue() == nullptr) {
    fprintf(stderr, "device/queue is null after init\n");
    return 2;
  }

  if (ctx.activateDrawingContext() != GHOST_kSuccess ||
      ctx.releaseDrawingContext() != GHOST_kSuccess) {
    fprintf(stderr, "activate/release failed\n");
    return 3;
  }

  printf(
      "T3 VERIFY PASS: live WGPUDevice obtained through GHOST_ContextWGPU "
      "(offscreen, headless, %s).\n",
      blender_web::dawn_probe::kBackendName);
  return 0;
}
