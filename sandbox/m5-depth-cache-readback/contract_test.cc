/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <algorithm>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>
#include <utility>
#include <vector>

#include "GPU_readback.hh"
#include "MEM_guardedalloc.h"
#include "gpu_readback_private.hh"

namespace {

void *aligned_allocate(const size_t size, size_t alignment)
{
  alignment = std::max(alignment, sizeof(void *));
  void *pointer = nullptr;
  if (posix_memalign(&pointer, alignment, std::max(size, size_t(1))) != 0) {
    std::abort();
  }
  return pointer;
}

void guarded_free(void *pointer, mem_guarded::internal::DestructorType)
{
  std::free(pointer);
}

void *guarded_allocate(const size_t size,
                       const size_t alignment,
                       const char *,
                       mem_guarded::internal::DestructorType)
{
  return aligned_allocate(size, alignment);
}

void *guarded_array_allocate(const size_t length,
                             const size_t element_size,
                             const size_t alignment,
                             const char *)
{
  if (element_size != 0 && length > std::numeric_limits<size_t>::max() / element_size) {
    return nullptr;
  }
  return aligned_allocate(length * element_size, alignment);
}

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "M5_DEPTH_CACHE_READBACK_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
}

std::vector<unsigned char> depth_bytes(const std::vector<float> &depths)
{
  std::vector<unsigned char> bytes(depths.size() * sizeof(float));
  std::memcpy(bytes.data(), depths.data(), bytes.size());
  return bytes;
}

class ControlledReadback final : public blender::GPUReadback {
 private:
  blender::eGPUReadbackStatus status_ = blender::GPU_READBACK_PENDING;
  blender::eGPUReadbackError error_ = blender::GPU_READBACK_ERROR_NONE;
  std::vector<unsigned char> bytes_;
  std::string *lifetime_;
  bool consume_ok_;

 public:
  ControlledReadback(std::vector<unsigned char> bytes,
                     std::string *lifetime,
                     const bool consume_ok = true)
      : bytes_(std::move(bytes)), lifetime_(lifetime), consume_ok_(consume_ok)
  {
  }

  ~ControlledReadback() override
  {
    lifetime_->push_back('R');
  }

  void ready()
  {
    status_ = blender::GPU_READBACK_READY;
    error_ = blender::GPU_READBACK_ERROR_NONE;
  }

  void fail()
  {
    status_ = blender::GPU_READBACK_FAILED;
    error_ = blender::GPU_READBACK_ERROR_MAP_FAILED;
  }

  blender::eGPUReadbackStatus status() override
  {
    return status_;
  }

  blender::eGPUReadbackError error() override
  {
    return error_;
  }

  size_t size() override
  {
    return bytes_.size();
  }

  bool consume(void *dst, const size_t dst_len) override
  {
    if (!consume_ok_ || status_ != blender::GPU_READBACK_READY || dst == nullptr ||
        dst_len < bytes_.size())
    {
      return false;
    }
    std::memcpy(dst, bytes_.data(), bytes_.size());
    return true;
  }
};

struct ContextKey {
  int region = 0;
  int region_view = 0;
  int region_width = 0;
  int region_height = 0;
  int texture_width = 0;
  int texture_height = 0;
  int view_transform = 0;

  bool operator==(const ContextKey &) const = default;
};

enum class CacheState {
  Pending,
  Ready,
  Failed,
};

struct DepthCache {
  unsigned short width = 0;
  unsigned short height = 0;
  short x = 0;
  short y = 0;
  std::vector<float> depths;
  double depth_range[2] = {0.0, 1.0};
};

class DepthCacheSession {
 private:
  blender::GPUReadback *readback_ = nullptr;
  ContextKey context_;
  size_t expected_size_ = 0;
  CacheState state_ = CacheState::Failed;

 public:
  ~DepthCacheSession()
  {
    cancel();
  }

  bool begin(const ContextKey context, blender::GPUReadback *readback)
  {
    cancel();
    state_ = CacheState::Failed;
    expected_size_ = 0;
    if (readback == nullptr || context.region == 0 || context.region_view == 0 ||
        context.region_width <= 0 || context.region_height <= 0 || context.texture_width <= 0 ||
        context.texture_height <= 0 ||
        context.texture_width > int(std::numeric_limits<unsigned short>::max()) ||
        context.texture_height > int(std::numeric_limits<unsigned short>::max()))
    {
      blender::GPU_readback_cancel(readback);
      return false;
    }

    const size_t width = size_t(context.texture_width);
    const size_t height = size_t(context.texture_height);
    if (width > size_t(std::numeric_limits<int>::max()) / height ||
        width > std::numeric_limits<size_t>::max() / height ||
        width * height > std::numeric_limits<size_t>::max() / sizeof(float))
    {
      blender::GPU_readback_cancel(readback);
      return false;
    }

    context_ = context;
    expected_size_ = width * height * sizeof(float);
    readback_ = readback;
    state_ = CacheState::Pending;
    return state() != CacheState::Failed;
  }

  CacheState state()
  {
    if (state_ != CacheState::Pending) {
      return state_;
    }
    const blender::eGPUReadbackStatus status = blender::GPU_readback_status(readback_);
    if (status == blender::GPU_READBACK_PENDING) {
      return state_;
    }
    if (status != blender::GPU_READBACK_READY ||
        blender::GPU_readback_size(readback_) != expected_size_)
    {
      blender::GPU_readback_cancel(readback_);
      state_ = CacheState::Failed;
      return state_;
    }
    state_ = CacheState::Ready;
    return state_;
  }

  DepthCache *take(const ContextKey context)
  {
    if (state() != CacheState::Ready || context != context_) {
      blender::GPU_readback_cancel(readback_);
      state_ = CacheState::Failed;
      return nullptr;
    }

    DepthCache *cache = new DepthCache;
    cache->width = static_cast<unsigned short>(context_.texture_width);
    cache->height = static_cast<unsigned short>(context_.texture_height);
    cache->depths.resize(expected_size_ / sizeof(float));
    if (!blender::GPU_readback_consume(
            readback_, cache->depths.data(), cache->depths.size() * sizeof(float)))
    {
      delete cache;
      blender::GPU_readback_cancel(readback_);
      state_ = CacheState::Failed;
      return nullptr;
    }
    state_ = CacheState::Failed;
    return cache;
  }

  void cancel()
  {
    blender::GPU_readback_cancel(readback_);
    state_ = CacheState::Failed;
  }
};

ContextKey context(const int texture_width = 3, const int texture_height = 2)
{
  return {1, 2, 640, 480, texture_width, texture_height, 7};
}

bool test_owned_pending_exact_cache()
{
  std::string lifetime;
  const std::vector<float> depths = {0.25f, 0.5f, 1.0f, 0.75f, 0.125f, 0.875f};
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(depths), &lifetime);
  DepthCacheSession session;
  if (!require(session.begin(context(), readback), "pending begin") ||
      !require(session.state() == CacheState::Pending, "pending state"))
  {
    return false;
  }
  readback->ready();
  DepthCache *cache = session.take(context());
  const bool ok = require(cache != nullptr, "ready cache") &&
                  require(cache->width == 3 && cache->height == 2, "exact dimensions") &&
                  require(cache->x == 0 && cache->y == 0, "full texture origin") &&
                  require(cache->depth_range[0] == 0.0 && cache->depth_range[1] == 1.0,
                          "depth range") &&
                  require(cache->depths == depths, "exact depth bytes") &&
                  require(lifetime == "R", "result released on transfer") &&
                  require(session.take(context()) == nullptr, "one shot transfer");
  delete cache;
  if (ok) {
    std::printf("CONTRACT owned_pending_exact PASS size=3x2 samples=6 lifetime=R\n");
  }
  return ok;
}

bool test_native_immediate()
{
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes({0.1f, 0.2f, 0.3f, 0.4f}), &lifetime);
  readback->ready();
  DepthCacheSession session;
  if (!require(session.begin(context(2, 2), readback), "immediate begin") ||
      !require(session.state() == CacheState::Ready, "immediate ready"))
  {
    return false;
  }
  DepthCache *cache = session.take(context(2, 2));
  const bool ok = require(cache != nullptr && cache->depths[3] == 0.4f, "immediate transfer") &&
                  require(lifetime == "R", "immediate release");
  delete cache;
  if (ok) {
    std::printf("CONTRACT native_immediate PASS size=2x2 lifetime=R\n");
  }
  return ok;
}

bool test_terminal_failures()
{
  std::string lifetime;
  auto *short_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes({0.1f, 0.2f, 0.3f}), &lifetime);
  short_readback->ready();
  DepthCacheSession short_session;
  if (!require(!short_session.begin(context(2, 2), short_readback), "size mismatch rejected") ||
      !require(lifetime == "R", "size mismatch released"))
  {
    return false;
  }

  auto *failed_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes({0.1f, 0.2f, 0.3f, 0.4f}), &lifetime);
  DepthCacheSession failed_session;
  if (!require(failed_session.begin(context(2, 2), failed_readback), "failure pending begin")) {
    return false;
  }
  failed_readback->fail();
  if (!require(failed_session.state() == CacheState::Failed, "backend failure") ||
      !require(lifetime == "RR", "backend failure released"))
  {
    return false;
  }

  auto *consume_failed = MEM_new<ControlledReadback>(
      __func__, depth_bytes({0.1f, 0.2f, 0.3f, 0.4f}), &lifetime, false);
  consume_failed->ready();
  DepthCacheSession consume_session;
  const bool ok = require(consume_session.begin(context(2, 2), consume_failed),
                          "consume failure ready") &&
                  require(consume_session.take(context(2, 2)) == nullptr,
                          "consume failure rejected") &&
                  require(lifetime == "RRR", "consume failure released");
  if (ok) {
    std::printf("CONTRACT terminal_failures PASS cases=3 lifetime=RRR\n");
  }
  return ok;
}

bool test_producing_context_guard()
{
  std::string lifetime;
  const auto run_drift = [&](const ContextKey changed) {
    auto *readback = MEM_new<ControlledReadback>(
        __func__, depth_bytes({0.1f, 0.2f, 0.3f, 0.4f}), &lifetime);
    readback->ready();
    DepthCacheSession session;
    return session.begin(context(2, 2), readback) && session.take(changed) == nullptr;
  };

  ContextKey region_drift = context(2, 2);
  region_drift.region = 9;
  ContextKey size_drift = context(2, 2);
  size_drift.region_width++;
  ContextKey transform_drift = context(2, 2);
  transform_drift.view_transform++;
  const bool ok = require(run_drift(region_drift), "region drift") &&
                  require(run_drift(size_drift), "region size drift") &&
                  require(run_drift(transform_drift), "view transform drift") &&
                  require(lifetime == "RRR", "drift releases");
  if (ok) {
    std::printf("CONTRACT producing_context_guard PASS cases=3 lifetime=RRR\n");
  }
  return ok;
}

bool test_reset_and_cancel()
{
  std::string lifetime;
  auto *first = MEM_new<ControlledReadback>(
      __func__, depth_bytes({0.1f, 0.2f, 0.3f, 0.4f}), &lifetime);
  auto *second = MEM_new<ControlledReadback>(
      __func__, depth_bytes({0.5f, 0.6f, 0.7f, 0.8f}), &lifetime);
  {
    DepthCacheSession session;
    if (!require(session.begin(context(2, 2), first), "first pending") ||
        !require(session.begin(context(2, 2), second), "replacement pending") ||
        !require(lifetime == "R", "replacement cancels first"))
    {
      return false;
    }
  }
  const bool ok = require(lifetime == "RR", "destructor cancels replacement");
  if (ok) {
    std::printf("CONTRACT reset_cancel PASS cases=2 lifetime=RR\n");
  }
  return ok;
}

bool test_invalid_geometry()
{
  std::string lifetime;
  const auto run_invalid = [&](const ContextKey invalid) {
    auto *readback = MEM_new<ControlledReadback>(__func__, std::vector<unsigned char>{}, &lifetime);
    DepthCacheSession session;
    return !session.begin(invalid, readback);
  };

  ContextKey zero = context();
  zero.texture_width = 0;
  ContextKey too_wide = context();
  too_wide.texture_width = int(std::numeric_limits<unsigned short>::max()) + 1;
  ContextKey no_view = context();
  no_view.region_view = 0;
  ContextKey too_many_pixels = context(
      std::numeric_limits<unsigned short>::max(), std::numeric_limits<unsigned short>::max());
  const bool ok = require(run_invalid(zero), "zero texture") &&
                  require(run_invalid(too_wide), "ushort overflow") &&
                  require(run_invalid(no_view), "missing view") &&
                  require(run_invalid(too_many_pixels), "signed index overflow") &&
                  require(lifetime == "RRRR", "invalid requests released");
  if (ok) {
    std::printf("CONTRACT invalid_geometry PASS cases=4 lifetime=RRRR\n");
  }
  return ok;
}

}  // namespace

namespace mem_guarded::internal {
void *(*mem_mallocN_aligned_ex)(size_t, size_t, const char *, DestructorType) = guarded_allocate;
void (*mem_freeN_ex)(void *, DestructorType) = guarded_free;
void *(*mem_malloc_arrayN_aligned)(size_t, size_t, size_t, const char *) = guarded_array_allocate;
}  // namespace mem_guarded::internal

int main()
{
  if (!test_owned_pending_exact_cache() || !test_native_immediate() ||
      !test_terminal_failures() || !test_producing_context_guard() || !test_reset_and_cancel() ||
      !test_invalid_geometry())
  {
    return 1;
  }
  std::printf("M5_DEPTH_CACHE_READBACK_CONTRACT_PASS contracts=6 cases=14\n");
  return 0;
}
