// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M3.T1 — Dawn+Tint native toolchain probe (blender-web).
//
// Proves the full WebGPU shader chain runs natively on this Mac, in-process:
//
//   .spv (Vulkan-1.1 / SPIR-V 1.3, produced offline by glslangValidator;
//         Tint's IR reader hardcodes SPV_ENV_VULKAN_1_1 — see notes)
//     -> tint::spirv::reader::ReadIR      -> tint::core::ir::Module
//     -> tint::wgsl::writer::ProgramFromIR -> tint::Program
//     -> tint::wgsl::writer::Generate      -> WGSL text
//     -> wgpuDeviceCreateShaderModule(WGSL) on a real Dawn/Metal device
//     -> validate via a Validation error scope + uncaptured-error callback.
//
// Exit 0 iff BOTH stages translate cleanly AND both shader modules validate
// with zero validation errors. Any failure returns a distinct non-zero code.
//
// This is the T1 de-risk for R2 (Dawn/Tint native build + SPV reader) and it
// dumps the fragment WGSL, which is the binding-map evidence seed for T2 (R1,
// combined-sampler split). See notes/gpu-webgpu-architecture.md §3, §6.
//
// API note: the chain here is the IR-based Tint API (ReadIR -> ProgramFromIR ->
// Generate), NOT the AST-based `spirv::reader::Read -> Program` that the
// architecture doc assumed. That older entry point no longer exists at this
// Dawn pin. Details in notes/gpu-dawn-probe.md.

#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

// WebGPU C++ bindings. We link the monolithic dawn::webgpu_dawn static library
// (Dawn's documented external-consumption target, docs/quickstart-cmake.md),
// which provides the real wgpu* implementation directly — so no dawn_proc table
// wiring and no DawnNative.h are needed; the native Metal backend is registered
// by wgpuCreateInstance itself.
#include "webgpu/webgpu_cpp.h"

// Tint (lives inside Dawn's tree; headers are rooted at the Dawn source dir).
#include "src/tint/lang/core/ir/module.h"
#include "src/tint/lang/spirv/reader/reader.h"
#include "src/tint/lang/wgsl/program/program.h"
#include "src/tint/lang/wgsl/writer/writer.h"

namespace {

// Convert a WGPUStringView-style value to std::string (handles the
// WGPU_STRLEN "null-terminated" sentinel).
std::string ToStr(wgpu::StringView s) {
  if (s.data == nullptr) {
    return {};
  }
  if (s.length == WGPU_STRLEN) {
    return std::string(s.data);
  }
  return std::string(s.data, s.length);
}

std::vector<uint32_t> LoadSpirv(const char* path) {
  std::ifstream f(path, std::ios::binary | std::ios::ate);
  if (!f) {
    std::cerr << "ERROR: cannot open SPIR-V file: " << path << "\n";
    return {};
  }
  const std::streamsize bytes = f.tellg();
  if (bytes <= 0 || (bytes % 4) != 0) {
    std::cerr << "ERROR: not a SPIR-V word stream: " << path << "\n";
    return {};
  }
  f.seekg(0);
  std::vector<uint32_t> words(static_cast<size_t>(bytes) / 4);
  f.read(reinterpret_cast<char*>(words.data()), bytes);
  return words;
}

// SPIR-V words -> WGSL, in-process, via Tint. Mirrors src/tint/cmd/common/
// helper.cc::ReadSpirv (the canonical path in Dawn's own tooling).
bool SpirvToWgsl(const std::vector<uint32_t>& spirv, std::string& out_wgsl) {
  // Empty sampler_mappings => Tint auto-resolves binding conflicts caused by
  // splitting combined image samplers, by incrementing binding numbers until
  // unique (see src/tint/lang/spirv/reader/common/options.h). This is exactly
  // the behaviour T2 must characterise.
  tint::spirv::reader::Options reader_opts;

  auto ir = tint::spirv::reader::ReadIR(spirv, reader_opts);
  if (ir != tint::Success) {
    std::cerr << "Tint SPIR-V reader (ReadIR) failed:\n" << ir.Failure() << "\n";
    return false;
  }

  tint::wgsl::writer::Options writer_opts;
  auto prog = tint::wgsl::writer::ProgramFromIR(ir.Get(), writer_opts);
  if (prog != tint::Success) {
    std::cerr << "Tint IR->Program (ProgramFromIR) failed:\n"
              << prog.Failure() << "\n";
    return false;
  }
  tint::Program program = prog.Move();

  auto gen = tint::wgsl::writer::Generate(program, writer_opts);
  if (gen != tint::Success) {
    std::cerr << "Tint WGSL writer (Generate) failed:\n" << gen.Failure() << "\n";
    return false;
  }
  out_wgsl = gen.Get().wgsl;
  return true;
}

// Create a shader module from WGSL on a live Dawn device and report whether it
// validates clean. Uses a Validation error scope for a deterministic verdict,
// plus GetCompilationInfo for detailed per-message diagnostics.
bool CreateAndValidate(const wgpu::Instance& instance, const wgpu::Device& device,
                       const std::string& wgsl, const char* label) {
  device.PushErrorScope(wgpu::ErrorFilter::Validation);

  wgpu::ShaderSourceWGSL wgsl_desc;
  wgsl_desc.code = wgsl.c_str();
  wgpu::ShaderModuleDescriptor desc;
  desc.nextInChain = &wgsl_desc;
  desc.label = label;
  wgpu::ShaderModule module = device.CreateShaderModule(&desc);

  bool had_error = false;
  std::string err_msg;
  wgpu::Future pop = device.PopErrorScope(
      wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::PopErrorScopeStatus, wgpu::ErrorType type, wgpu::StringView msg) {
        if (type != wgpu::ErrorType::NoError) {
          had_error = true;
          err_msg = ToStr(msg);
        }
      });
  instance.WaitAny(pop, UINT64_MAX);

  // Detailed WGSL compilation diagnostics (informational).
  if (module != nullptr) {
    wgpu::Future ci = module.GetCompilationInfo(
        wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::CompilationInfoRequestStatus, wgpu::CompilationInfo const* info) {
          if (info == nullptr) {
            return;
          }
          for (size_t i = 0; i < info->messageCount; ++i) {
            const wgpu::CompilationMessage& m = info->messages[i];
            const char* sev = m.type == wgpu::CompilationMessageType::Error ? "error"
                              : m.type == wgpu::CompilationMessageType::Warning
                                  ? "warning"
                                  : "info";
            std::cout << "   [" << label << "] compilation " << sev << " (line "
                      << m.lineNum << "): " << ToStr(m.message) << "\n";
          }
        });
    instance.WaitAny(ci, UINT64_MAX);
  }

  if (had_error) {
    std::cerr << "[" << label << "] MODULE VALIDATION FAILED: " << err_msg << "\n";
    return false;
  }
  if (module == nullptr) {
    std::cerr << "[" << label << "] CreateShaderModule returned null\n";
    return false;
  }
  std::cout << "[" << label << "] shader module validated CLEAN\n";
  return true;
}

}  // namespace

int main(int argc, char** argv) {
  const char* vert_path = argc > 1 ? argv[1] : "probe.vert.spv";
  const char* frag_path = argc > 2 ? argv[2] : "probe.frag.spv";

  // ---- Stage 1: load SPIR-V -------------------------------------------------
  std::vector<uint32_t> vert_spv = LoadSpirv(vert_path);
  std::vector<uint32_t> frag_spv = LoadSpirv(frag_path);
  if (vert_spv.empty() || frag_spv.empty()) {
    return 2;
  }
  std::cout << "Loaded SPIR-V: vertex " << vert_spv.size() * 4 << " bytes, fragment "
            << frag_spv.size() * 4 << " bytes\n";

  // ---- Stage 2: Tint SPIR-V -> WGSL ----------------------------------------
  std::string vert_wgsl;
  std::string frag_wgsl;
  const bool v_ok = SpirvToWgsl(vert_spv, vert_wgsl);
  const bool f_ok = SpirvToWgsl(frag_spv, frag_wgsl);
  if (!v_ok || !f_ok) {
    std::cerr << "TINT TRANSLATE: FAIL\n";
    return 3;
  }
  std::cout << "\n===== VERTEX WGSL =====\n" << vert_wgsl;
  std::cout << "\n===== FRAGMENT WGSL =====\n" << frag_wgsl << "\n";

  // ---- Stage 3: real Dawn/Metal device (headless, no surface) --------------
  wgpu::InstanceDescriptor instance_desc = {};
  static constexpr auto kTimedWaitAny = wgpu::InstanceFeatureName::TimedWaitAny;
  instance_desc.requiredFeatureCount = 1;
  instance_desc.requiredFeatures = &kTimedWaitAny;
  wgpu::Instance instance = wgpu::CreateInstance(&instance_desc);
  if (instance == nullptr) {
    std::cerr << "CreateInstance failed\n";
    return 4;
  }

  wgpu::RequestAdapterOptions adapter_opts = {};
  adapter_opts.backendType = wgpu::BackendType::Metal;
  adapter_opts.featureLevel = wgpu::FeatureLevel::Core;
  wgpu::Adapter adapter;
  instance.WaitAny(
      instance.RequestAdapter(
          &adapter_opts, wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestAdapterStatus status, wgpu::Adapter a, wgpu::StringView msg) {
            if (status != wgpu::RequestAdapterStatus::Success) {
              std::cerr << "RequestAdapter failed: " << ToStr(msg) << "\n";
              return;
            }
            adapter = std::move(a);
          }),
      UINT64_MAX);
  if (adapter == nullptr) {
    std::cerr << "no Metal adapter\n";
    return 5;
  }
  wgpu::AdapterInfo info;
  adapter.GetInfo(&info);
  std::cout << "Dawn adapter: \"" << ToStr(info.device) << "\" vendor=\""
            << ToStr(info.vendor) << "\" backend=Metal\n";

  wgpu::DeviceDescriptor device_desc = {};
  device_desc.SetUncapturedErrorCallback(
      [](const wgpu::Device&, wgpu::ErrorType type, wgpu::StringView msg) {
        std::cerr << "UNCAPTURED error (type " << static_cast<int>(type)
                  << "): " << ToStr(msg) << "\n";
      });
  wgpu::Device device;
  instance.WaitAny(
      adapter.RequestDevice(
          &device_desc, wgpu::CallbackMode::WaitAnyOnly,
          [&](wgpu::RequestDeviceStatus status, wgpu::Device d, wgpu::StringView msg) {
            if (status != wgpu::RequestDeviceStatus::Success) {
              std::cerr << "RequestDevice failed: " << ToStr(msg) << "\n";
              return;
            }
            device = std::move(d);
          }),
      UINT64_MAX);
  if (device == nullptr) {
    std::cerr << "no Dawn device\n";
    return 6;
  }

  // ---- Stage 4: validate both modules --------------------------------------
  std::cout << "\n";
  const bool vmod_ok = CreateAndValidate(instance, device, vert_wgsl, "vertex");
  const bool fmod_ok = CreateAndValidate(instance, device, frag_wgsl, "fragment");

  if (vmod_ok && fmod_ok) {
    std::cout << "\nPROBE PASS: dawn-build + spirv-gen + tint-translate + "
                 "module-validate all green.\n";
    return 0;
  }
  std::cerr << "\nPROBE FAIL: module validation did not pass.\n";
  return 7;
}
