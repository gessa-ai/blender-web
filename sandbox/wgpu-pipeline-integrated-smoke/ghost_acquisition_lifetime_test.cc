/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <cstddef>
#include <cstdio>
#include <functional>
#include <memory>
#include <string_view>

#ifndef BW_GHOST_PRESENT_TRANSACTION_HEADER
#  error "BW_GHOST_PRESENT_TRANSACTION_HEADER must name the shipping transaction header"
#endif
#include BW_GHOST_PRESENT_TRANSACTION_HEADER

namespace gw = ghost_web;

struct AcquisitionCounters {
  size_t owner_accesses = 0;
  size_t follow_on_requests = 0;
  size_t completions = 0;
};

class GhostAcquisitionContextProbe {
 public:
  using Lifetime = gw::OwnerCallbackLifetime<GhostAcquisitionContextProbe>;

  explicit GhostAcquisitionContextProbe(std::shared_ptr<AcquisitionCounters> counters)
      : counters_(std::move(counters)), lifetime_(std::make_shared<Lifetime>(*this))
  {
  }

  ~GhostAcquisitionContextProbe()
  {
    lifetime_->invalidate();
  }

  std::shared_ptr<Lifetime> lifetime() const
  {
    return lifetime_;
  }

#if defined(__GNUC__) || defined(__clang__)
  __attribute__((noinline))
#endif
  void adapter_completed()
  {
    counters_->owner_accesses++;
    counters_->follow_on_requests++;
  }

#if defined(__GNUC__) || defined(__clang__)
  __attribute__((noinline))
#endif
  void device_completed()
  {
    counters_->owner_accesses++;
    counters_->completions++;
  }

 private:
  std::shared_ptr<AcquisitionCounters> counters_;
  std::shared_ptr<Lifetime> lifetime_;
};

static bool require(const bool condition, const std::string_view message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL: %.*s\n", int(message.size()), message.data());
  }
  return condition;
}

static int run_unsafe_control()
{
  const auto counters = std::make_shared<AcquisitionCounters>();
  auto *owner = new GhostAcquisitionContextProbe(counters);
  std::function<void()> delayed = [owner]() { owner->adapter_completed(); };
  delete owner;
  delayed();
  return 0;
}

int main(int argc, char **argv)
{
  if (argc == 2 && std::string_view(argv[1]) == "--unsafe-control") {
    return run_unsafe_control();
  }

  const auto invalidated = std::make_shared<AcquisitionCounters>();
  std::weak_ptr<GhostAcquisitionContextProbe::Lifetime> weak_lifetime;
  std::function<bool()> delayed_adapter;
  std::function<bool()> delayed_device;
  {
    auto owner = std::make_unique<GhostAcquisitionContextProbe>(invalidated);
    const auto lifetime = owner->lifetime();
    weak_lifetime = lifetime;
    delayed_adapter = [lifetime]() {
      return lifetime->deliver(
          [](GhostAcquisitionContextProbe &context) { context.adapter_completed(); });
    };
    delayed_device = [lifetime]() {
      return lifetime->deliver(
          [](GhostAcquisitionContextProbe &context) { context.device_completed(); });
    };
  }

  if (!require(!delayed_adapter(), "adapter callback is inert after context destruction") ||
      !require(!delayed_device(), "device callback is inert after context destruction") ||
      !require(invalidated->owner_accesses == 0, "no owner access after invalidation") ||
      !require(invalidated->follow_on_requests == 0, "no device request after invalidation") ||
      !require(invalidated->completions == 0, "no initialization completion after invalidation"))
  {
    return 1;
  }

  const auto live = std::make_shared<AcquisitionCounters>();
  {
    auto owner = std::make_unique<GhostAcquisitionContextProbe>(live);
    const auto lifetime = owner->lifetime();
    if (!require(lifetime->deliver([](GhostAcquisitionContextProbe &context) {
                   context.adapter_completed();
                 }),
                 "live adapter callback is delivered") ||
        !require(lifetime->deliver([](GhostAcquisitionContextProbe &context) {
                   context.device_completed();
                 }),
                 "live device callback is delivered"))
    {
      return 1;
    }
  }
  if (!require(live->owner_accesses == 2 && live->follow_on_requests == 1 &&
                   live->completions == 1,
               "live acquisition callback census"))
  {
    return 1;
  }

  delayed_adapter = nullptr;
  delayed_device = nullptr;
  if (!require(weak_lifetime.expired(), "delayed callbacks release the invalidated lifetime")) {
    return 1;
  }

  std::puts("CONTRACT ghost_acquisition_lifetime PASS cases=4 delayed=2 live=2 "
            "owner_access_after_invalidate=0 completion_after_invalidate=0 "
            "follow_on_after_invalidate=0");
  return 0;
}
