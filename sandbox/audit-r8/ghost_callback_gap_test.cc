/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include "GHOST_WGPUTransaction.hh"

#include <atomic>
#include <chrono>
#include <cstdio>
#include <memory>
#include <string_view>
#include <thread>

namespace gw = ghost_web;

namespace {

struct RaceControl {
  std::atomic<bool> callback_has_owner{false};
  std::atomic<bool> destructor_started{false};
  std::atomic<bool> allow_owner_access{false};
  std::atomic<bool> destructor_returned{false};
};

std::atomic<int> callback_sink{0};

class OwnerProbe {
 public:
  using Lifetime = gw::OwnerCallbackLifetime<OwnerProbe>;

  explicit OwnerProbe(std::shared_ptr<RaceControl> control = {})
      : control_(std::move(control)), lifetime_(std::make_shared<Lifetime>(*this))
  {
  }

  ~OwnerProbe()
  {
    if (control_) {
      control_->destructor_started.store(true, std::memory_order_release);
    }
    lifetime_->invalidate();
  }

  std::shared_ptr<Lifetime> lifetime() const
  {
    return lifetime_;
  }

#if defined(__GNUC__) || defined(__clang__)
  __attribute__((noinline))
#endif
  void touch_after_gate()
  {
    callback_sink.store(marker_.load(std::memory_order_acquire), std::memory_order_release);
  }

 private:
  std::shared_ptr<RaceControl> control_;
  std::atomic<int> marker_{0x5a17};
  std::shared_ptr<Lifetime> lifetime_;
};

/** The pre-fix check-then-use gate, retained only as an ASan-negative control. */
template<typename OwnerT> class UnsafeOwnerLifetime {
 public:
  explicit UnsafeOwnerLifetime(OwnerT &owner) : owner_(&owner) {}

  void invalidate()
  {
    owner_.store(nullptr, std::memory_order_release);
  }

  template<typename Callback> bool deliver(Callback &&callback) const
  {
    OwnerT *owner = owner_.load(std::memory_order_acquire);
    if (owner == nullptr) {
      return false;
    }
    std::forward<Callback>(callback)(*owner);
    return true;
  }

 private:
  std::atomic<OwnerT *> owner_;
};

class UnsafeOwnerProbe {
 public:
  using Lifetime = UnsafeOwnerLifetime<UnsafeOwnerProbe>;

  UnsafeOwnerProbe() : lifetime_(std::make_shared<Lifetime>(*this)) {}

  ~UnsafeOwnerProbe()
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
  void touch_after_gate()
  {
    callback_sink.store(marker_.load(std::memory_order_acquire), std::memory_order_release);
  }

 private:
  std::atomic<int> marker_{0x7319};
  std::shared_ptr<Lifetime> lifetime_;
};

bool wait_for(const std::atomic<bool> &value)
{
  for (int attempt = 0; attempt < 1000000; attempt++) {
    if (value.load(std::memory_order_acquire)) {
      return true;
    }
    std::this_thread::yield();
  }
  return false;
}

int run_unsafe_owner_race()
{
  auto *owner = new UnsafeOwnerProbe();
  const std::shared_ptr<UnsafeOwnerProbe::Lifetime> lifetime = owner->lifetime();
  std::atomic<bool> callback_has_owner{false};
  std::atomic<bool> allow_owner_access{false};

  std::thread completion([&]() {
    lifetime->deliver([&](UnsafeOwnerProbe &loaded_owner) {
      callback_has_owner.store(true, std::memory_order_release);
      while (!allow_owner_access.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
      loaded_owner.touch_after_gate();
    });
  });

  if (!wait_for(callback_has_owner)) {
    return 2;
  }
  delete owner;
  allow_owner_access.store(true, std::memory_order_release);
  completion.join();
  return 0;
}

bool run_concurrent_owner_contract()
{
  callback_sink.store(0, std::memory_order_release);
  const auto control = std::make_shared<RaceControl>();
  auto *owner = new OwnerProbe(control);
  const std::shared_ptr<OwnerProbe::Lifetime> lifetime = owner->lifetime();
  std::atomic<bool> delivered{false};

  std::thread completion([&]() {
    delivered.store(
        lifetime->deliver([&](OwnerProbe &loaded_owner) {
          control->callback_has_owner.store(true, std::memory_order_release);
          while (!control->allow_owner_access.load(std::memory_order_acquire)) {
            std::this_thread::yield();
          }
          loaded_owner.touch_after_gate();
        }),
        std::memory_order_release);
  });
  if (!wait_for(control->callback_has_owner)) {
    completion.join();
    return false;
  }

  std::thread destroyer([&]() {
    delete owner;
    control->destructor_returned.store(true, std::memory_order_release);
  });
  if (!wait_for(control->destructor_started)) {
    control->allow_owner_access.store(true, std::memory_order_release);
    completion.join();
    destroyer.join();
    return false;
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(20));
  const bool waited_for_delivery =
      !control->destructor_returned.load(std::memory_order_acquire);
  control->allow_owner_access.store(true, std::memory_order_release);
  completion.join();
  destroyer.join();

  return waited_for_delivery && delivered.load(std::memory_order_acquire) &&
         control->destructor_returned.load(std::memory_order_acquire) &&
         callback_sink.load(std::memory_order_acquire) == 0x5a17;
}

bool run_self_destruction_contract()
{
  auto *owner = new OwnerProbe();
  const std::shared_ptr<OwnerProbe::Lifetime> lifetime = owner->lifetime();
  bool callback_ran = false;
  const bool delivered = lifetime->deliver([&](OwnerProbe &loaded_owner) {
    callback_ran = true;
    delete &loaded_owner;
  });
  return delivered && callback_ran && !lifetime->deliver([](OwnerProbe &) {});
}

bool run_serialized_owner_contract()
{
  auto owner = std::make_unique<OwnerProbe>();
  const std::shared_ptr<OwnerProbe::Lifetime> lifetime = owner->lifetime();
  std::atomic<int> active{0};
  std::atomic<int> peak{0};
  std::atomic<bool> first_entered{false};
  std::atomic<bool> release_first{false};
  std::atomic<bool> second_entered{false};

  const auto enter = [&](std::atomic<bool> &entered, const bool wait) {
    return lifetime->deliver([&](OwnerProbe & /*loaded_owner*/) {
      const int current = active.fetch_add(1, std::memory_order_acq_rel) + 1;
      int observed_peak = peak.load(std::memory_order_acquire);
      while (observed_peak < current &&
             !peak.compare_exchange_weak(observed_peak, current, std::memory_order_acq_rel))
      {
      }
      entered.store(true, std::memory_order_release);
      while (wait && !release_first.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
      active.fetch_sub(1, std::memory_order_acq_rel);
    });
  };

  std::thread first([&]() { enter(first_entered, true); });
  if (!wait_for(first_entered)) {
    release_first.store(true, std::memory_order_release);
    first.join();
    return false;
  }
  std::thread second([&]() { enter(second_entered, false); });
  std::this_thread::sleep_for(std::chrono::milliseconds(20));
  const bool second_waited = !second_entered.load(std::memory_order_acquire);
  release_first.store(true, std::memory_order_release);
  first.join();
  second.join();

  bool nested_ran = false;
  const bool outer_delivered = lifetime->deliver([&](OwnerProbe & /*loaded_owner*/) {
    nested_ran = lifetime->deliver([](OwnerProbe & /*nested_owner*/) {});
  });
  return second_waited && second_entered.load(std::memory_order_acquire) &&
         peak.load(std::memory_order_acquire) == 1 && outer_delivered && nested_ran;
}

bool run_imported_loss_contract()
{
  constexpr uint32_t generation = 7;
  gw::ImportedDeviceLossObservation observation{
      generation, gw::ImportedDeviceLossStatus::Pending};
  auto state = std::make_shared<gw::DeviceCallbackState>(
      generation, [&observation]() { return observation; });
  if (!gw::device_state_allows_callback_work(state)) {
    return false;
  }

  observation.status = gw::ImportedDeviceLossStatus::Unknown;
  if (gw::device_state_allows_callback_work(state) ||
      state->load(std::memory_order_acquire) != gw::DeviceState::Lost)
  {
    return false;
  }

  /* Loss is sticky even if a stale JavaScript record later looks pending again. */
  observation.status = gw::ImportedDeviceLossStatus::Pending;
  if (gw::device_state_allows_callback_work(state)) {
    return false;
  }

  observation = {generation + 1, gw::ImportedDeviceLossStatus::Pending};
  auto replaced = std::make_shared<gw::DeviceCallbackState>(
      generation, [&observation]() { return observation; });
  return !gw::device_state_allows_callback_work(replaced) &&
         replaced->load(std::memory_order_acquire) == gw::DeviceState::Lost;
}

}  // namespace

int main(int argc, char **argv)
{
  if (argc == 2 && std::string_view(argv[1]) == "--unsafe-owner-race") {
    return run_unsafe_owner_race();
  }
  if (!run_concurrent_owner_contract()) {
    std::fprintf(stderr, "FAIL: synchronized owner delivery contract\n");
    return 1;
  }
  if (!run_self_destruction_contract()) {
    std::fprintf(stderr, "FAIL: reentrant owner destruction contract\n");
    return 1;
  }
  if (!run_serialized_owner_contract()) {
    std::fprintf(stderr, "FAIL: serialized owner delivery contract\n");
    return 1;
  }
  if (!run_imported_loss_contract()) {
    std::fprintf(stderr, "FAIL: imported-device loss callback contract\n");
    return 1;
  }
  std::puts("CONTRACT ghost_owner_lifetime PASS concurrent=1 reentrant=1 delayed=blocked");
  std::puts("CONTRACT ghost_owner_serialization PASS concurrent=serialized nested=1");
  std::puts("CONTRACT ghost_imported_loss_callback PASS pending=allow settled=block sticky=1 replaced=block");
  return 0;
}
