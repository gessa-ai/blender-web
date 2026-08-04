/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.T6.pre live harness. On a real native Dawn/Metal device: for each buffer
 * kind (vertex/index/uniform/storage) create with initial data, read back
 * byte-exact, apply a sub-range update and re-read it; plus one >16 MiB storage
 * buffer that exercises the staging (CopyBufferToBuffer) update path. */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "webgpu/webgpu_cpp.h"

#include "wgpu_buffer.hh"

namespace bw = blender::gpu::webgpu;

namespace {

std::string ToStr(wgpu::StringView s) {
  if (s.data == nullptr) return {};
  if (s.length == WGPU_STRLEN) return std::string(s.data);
  return std::string(s.data, s.length);
}

std::vector<uint8_t> pattern(size_t n, uint8_t seed) {
  std::vector<uint8_t> v(n);
  for (size_t i = 0; i < n; i++) v[i] = uint8_t((i * 131u + seed) & 0xFFu);
  return v;
}

struct Dawn {
  wgpu::Instance instance;
  wgpu::Adapter adapter;
  wgpu::Device device;
  wgpu::Queue queue;

  bool init() {
    wgpu::InstanceDescriptor idesc = {};
    static constexpr auto kTWA = wgpu::InstanceFeatureName::TimedWaitAny;
    idesc.requiredFeatureCount = 1;
    idesc.requiredFeatures = &kTWA;
    instance = wgpu::CreateInstance(&idesc);
    if (!instance) return false;
    wgpu::RequestAdapterOptions aopts = {};
    aopts.backendType = wgpu::BackendType::Metal;
    aopts.featureLevel = wgpu::FeatureLevel::Core;
    instance.WaitAny(instance.RequestAdapter(&aopts, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::RequestAdapterStatus s, wgpu::Adapter a, wgpu::StringView m) {
          if (s == wgpu::RequestAdapterStatus::Success) adapter = std::move(a);
          else std::fprintf(stderr, "adapter: %s\n", ToStr(m).c_str());
        }), UINT64_MAX);
    if (!adapter) return false;
    wgpu::DeviceDescriptor ddesc = {};
    ddesc.SetUncapturedErrorCallback([](const wgpu::Device&, wgpu::ErrorType t, wgpu::StringView m) {
      std::fprintf(stderr, "UNCAPTURED(%d): %s\n", int(t), ToStr(m).c_str());
    });
    instance.WaitAny(adapter.RequestDevice(&ddesc, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::RequestDeviceStatus s, wgpu::Device d, wgpu::StringView m) {
          if (s == wgpu::RequestDeviceStatus::Success) device = std::move(d);
          else std::fprintf(stderr, "device: %s\n", ToStr(m).c_str());
        }), UINT64_MAX);
    if (!device) return false;
    queue = device.GetQueue();
    wgpu::AdapterInfo info; adapter.GetInfo(&info);
    std::printf("Dawn adapter: \"%s\" backend=Metal\n\n", ToStr(info.device).c_str());
    return true;
  }
};

const char *kind_name(bw::BufferKind k) {
  switch (k) {
    case bw::BufferKind::Vertex: return "Vertex";
    case bw::BufferKind::Index: return "Index";
    case bw::BufferKind::Uniform: return "Uniform";
    case bw::BufferKind::Storage: return "Storage";
  }
  return "?";
}

/* Create + full readback + sub-update + partial readback. */
bool test_kind(Dawn &d, bw::BufferKind kind, size_t size) {
  bw::Buffer buf;
  std::vector<uint8_t> init = pattern(size, 7);
  if (!buf.create(d.device, kind, bw::UsageType::Dynamic, size, init.data(), /*readable=*/true)) {
    std::printf("  %-8s create FAIL\n", kind_name(kind));
    return false;
  }
  std::vector<uint8_t> back = buf.read(d.instance, d.device, d.queue, 0, size);
  bool full_ok = (back == init);

  /* Sub-range update (4-aligned) with a different pattern. */
  const size_t off = 64, len = 128;
  std::vector<uint8_t> upd = pattern(len, 200);
  bool up_ok = buf.update_sub(d.device, d.queue, off, upd.data(), len);
  std::vector<uint8_t> sub = buf.read(d.instance, d.device, d.queue, off, len);
  bool sub_ok = up_ok && (sub == upd);

  std::printf("  %-8s size=%-8zu create+init:%s  full-readback:%s  sub-update:%s\n",
              kind_name(kind), size, buf.valid() ? "OK" : "FAIL",
              full_ok ? "OK" : "FAIL", sub_ok ? "OK" : "FAIL");
  return buf.valid() && full_ok && sub_ok;
}

/* >16 MiB buffer exercising the staging (CopyBufferToBuffer) update path. */
bool test_large(Dawn &d) {
  const size_t size = 20u * 1024u * 1024u; /* 20 MiB > kWriteBufferStagingThreshold */
  bw::Buffer buf;
  if (!buf.create(d.device, bw::BufferKind::Storage, bw::UsageType::Dynamic, size, nullptr, true)) {
    std::printf("  large   create FAIL\n");
    return false;
  }
  std::vector<uint8_t> data = pattern(size, 99);
  /* One big update_sub -> routes through the staging buffer path. */
  bool up = buf.update_sub(d.device, d.queue, 0, data.data(), size);
  /* Verify a slice near the end. */
  const size_t off = size - 4096, len = 4096;
  std::vector<uint8_t> tail = buf.read(d.instance, d.device, d.queue, off, len);
  bool ok = up && tail.size() == len &&
            std::memcmp(tail.data(), &data[off], len) == 0;
  std::printf("  large    size=%zu (20 MiB) staging update + tail readback: %s\n", size,
              ok ? "OK" : "FAIL");
  return ok;
}

}  // namespace

int main() {
  Dawn d;
  if (!d.init()) return 2;

  std::printf("==== buffer kinds: create / readback / sub-update ====\n");
  int pass = 0, total = 0;
  auto gate = [&](bool ok) { total++; if (ok) pass++; };
  gate(test_kind(d, bw::BufferKind::Vertex, 4096));
  gate(test_kind(d, bw::BufferKind::Index, 4096));
  gate(test_kind(d, bw::BufferKind::Uniform, 256));
  gate(test_kind(d, bw::BufferKind::Storage, 8192));

  std::printf("\n==== large buffer (staging path) ====\n");
  gate(test_large(d));

  std::printf("\n================ SUMMARY ================\n");
  std::printf("buffer cases passed: %d/%d\n", pass, total);
  if (pass == total) {
    std::printf("T6.PRE HARNESS PASS: all buffer kinds create + upload + readback byte-exact; "
                "sub-range updates and the >16 MiB staging path verified.\n");
    return 0;
  }
  std::fprintf(stderr, "T6.PRE HARNESS FAIL\n");
  return 1;
}
