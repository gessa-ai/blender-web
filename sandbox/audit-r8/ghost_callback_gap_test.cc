/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include "GHOST_WGPUTransaction.hh"

#include <array>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <functional>
#include <memory>
#include <string_view>
#include <thread>

namespace gw = ghost_web;

namespace {

struct RaceControl {
  std::atomic<bool> callback_has_owner{false};
  std::atomic<bool> destructor_started{false};
  std::atomic<bool> admission_closed{false};
  std::atomic<bool> nested_delivery_finished{false};
  std::atomic<bool> nested_delivery_ran{false};
  std::atomic<bool> queued_delivery_attempted{false};
  std::atomic<bool> queued_delivery_ran{false};
  std::atomic<bool> allow_owner_access{false};
  std::atomic<bool> destructor_returned{false};
};

struct ExecutionControl {
  std::atomic<int> active{0};
  std::atomic<int> peak{0};
  std::atomic<bool> callback_entered{false};
  std::atomic<bool> owner_attempted{false};
  std::atomic<bool> owner_entered{false};
  std::atomic<bool> cleanup_attempted{false};
  std::atomic<bool> cleanup_entered{false};
  std::atomic<bool> release_callback{false};
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
    /* Destruction closes admission before waiting for an active callback. */
    lifetime_->cancel();
    if (control_) {
      control_->admission_closed.store(true, std::memory_order_release);
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

void enter_execution(ExecutionControl &control, std::atomic<bool> &entered)
{
  const int current = control.active.fetch_add(1, std::memory_order_acq_rel) + 1;
  int observed_peak = control.peak.load(std::memory_order_acquire);
  while (observed_peak < current &&
         !control.peak.compare_exchange_weak(observed_peak, current, std::memory_order_acq_rel))
  {
  }
  entered.store(true, std::memory_order_release);
}

class OwnerExecutionProbe {
 public:
  using Lifetime = gw::OwnerCallbackLifetime<OwnerExecutionProbe>;

  OwnerExecutionProbe() : lifetime_(std::make_shared<Lifetime>(*this)) {}

  ~OwnerExecutionProbe()
  {
    lifetime_->cancel();
    lifetime_->invalidate();
  }

  std::shared_ptr<Lifetime> lifetime() const
  {
    return lifetime_;
  }

  bool public_owner_step(ExecutionControl &control)
  {
    const std::shared_ptr<Lifetime> lifetime = lifetime_;
    auto owner_execution = lifetime->enter();
    if (!owner_execution) {
      return false;
    }
    enter_execution(control, control.owner_entered);
    control.active.fetch_sub(1, std::memory_order_acq_rel);
    return true;
  }

  bool terminal_cleanup(ExecutionControl &control)
  {
    const std::shared_ptr<Lifetime> lifetime = lifetime_;
    auto owner_execution = lifetime->enter();
    if (!owner_execution) {
      return false;
    }
    enter_execution(control, control.cleanup_entered);
    lifetime->cancel();
    control.active.fetch_sub(1, std::memory_order_acq_rel);
    return true;
  }

 private:
  std::shared_ptr<Lifetime> lifetime_;
};

enum class InitializationStage {
  BackbufferCreation,
  SurfaceConfiguration,
};

struct ReadyObservation {
  int calls = 0;
  bool success = true;
};

struct ReadyLifetimeObservation {
  int calls = 0;
  bool success = false;
  bool continued_after_delete = false;
};

template<typename OwnerT> struct SelfDestroyingReady {
  static constexpr uint64_t marker_value = UINT64_C(0x7767707572656164);

  OwnerT **owner_slot = nullptr;
  std::shared_ptr<ReadyLifetimeObservation> observation;
  volatile uint64_t marker = marker_value;

#if defined(__GNUC__) || defined(__clang__)
  __attribute__((noinline))
#endif
  void operator()(const bool success)
  {
    observation->calls++;
    observation->success = success;
    OwnerT *owner = *owner_slot;
    *owner_slot = nullptr;
    delete owner;

    /* The callable must remain alive after it destroys the owner that originally stored it. */
    const bool callable_survived = marker == marker_value;
    observation->continued_after_delete = callable_survived;
  }
};

class InitializationProbe {
 public:
  using Lifetime = gw::OwnerCallbackLifetime<InitializationProbe>;
  using ReadyCallback = std::function<void(bool)>;

  InitializationProbe(const InitializationStage stage,
                      const std::shared_ptr<ReadyObservation> &ready_observation)
      : InitializationProbe(stage, [ready_observation](const bool success) {
          ready_observation->calls++;
          ready_observation->success = success;
        })
  {
  }

  InitializationProbe(const InitializationStage stage, ReadyCallback on_ready)
      : backbuffer_pending_(true),
        configuration_pending_(stage == InitializationStage::SurfaceConfiguration),
        on_ready_(std::move(on_ready)),
        lifetime_(std::make_shared<Lifetime>(*this))
  {
  }

  ~InitializationProbe()
  {
    lifetime_->cancel();
    lifetime_->invalidate();
  }

  std::shared_ptr<Lifetime> lifetime() const
  {
    return lifetime_;
  }

  void complete_initialization(const bool success)
  {
    if (initialization_settled_) {
      return;
    }
    initialization_settled_ = true;
    ReadyCallback on_ready = std::move(on_ready_);
    on_ready_ = nullptr;
    if (on_ready) {
      on_ready(success);
    }
  }

  void propagate_device_loss()
  {
    if (device_loss_propagated_) {
      return;
    }
    device_loss_propagated_ = true;
    lifetime_->cancel();
    backbuffer_pending_ = false;
    configuration_pending_ = false;
    complete_initialization(false);
  }

  bool has_pending_initialization() const
  {
    return backbuffer_pending_ || configuration_pending_;
  }

 private:
  bool backbuffer_pending_ = false;
  bool configuration_pending_ = false;
  bool initialization_settled_ = false;
  bool device_loss_propagated_ = false;
  ReadyCallback on_ready_;
  std::shared_ptr<Lifetime> lifetime_;
};

enum class ShippingCallbackRole : size_t {
  AdapterAcquisition,
  DeviceAcquisition,
  BackbufferCreation,
  SurfaceConfiguration,
  PresentPipelineCreation,
  PresentSubmission,
  PresentCompletion,
  FallbackDeviceLoss,
  Count,
};

constexpr size_t shipping_callback_role_count = size_t(ShippingCallbackRole::Count);

struct ShippingCallbackObservation {
  std::array<int, shipping_callback_role_count> deliveries{};
  int ready_calls = 0;
  bool ready_success = true;
  bool pending_cleared = false;
  int destroyed = 0;
};

/**
 * Device-free mirror of the shipping context's eight asynchronous owner callbacks.
 *
 * Acquisition callbacks retain only the owner gate, five rendering completions retain both the
 * owner gate and callback-owned device state, and fallback loss publishes terminal state before
 * entering the owner.  Destruction closes the same gate retained by every returned completion.
 */
class ShippingContextProbe {
 public:
  using Lifetime = gw::OwnerCallbackLifetime<ShippingContextProbe>;
  using Completion = std::function<bool()>;

  explicit ShippingContextProbe(std::shared_ptr<ShippingCallbackObservation> observation)
      : observation_(std::move(observation)), lifetime_(std::make_shared<Lifetime>(*this))
  {
  }

  ~ShippingContextProbe()
  {
    lifetime_->cancel();
    lifetime_->invalidate();
    observation_->destroyed++;
  }

  Completion make_completion(const ShippingCallbackRole role)
  {
    const std::shared_ptr<Lifetime> lifetime = lifetime_;
    const std::shared_ptr<gw::DeviceCallbackState> device_state = device_state_;
    if (role == ShippingCallbackRole::FallbackDeviceLoss) {
      return [device_state, lifetime]() {
        return gw::fallback_device_loss_notify(
            device_state, lifetime, [](ShippingContextProbe &owner) {
              owner.record(ShippingCallbackRole::FallbackDeviceLoss);
              owner.propagate_device_loss();
            });
      };
    }
    if (role == ShippingCallbackRole::AdapterAcquisition ||
        role == ShippingCallbackRole::DeviceAcquisition)
    {
      return [lifetime, role]() {
        return lifetime->deliver(
            [role](ShippingContextProbe &owner) { owner.record(role); });
      };
    }
    return [lifetime, device_state, role]() {
      return lifetime->deliver([&](ShippingContextProbe &owner) {
        if (!gw::device_state_allows_callback_work(device_state)) {
          return;
        }
        owner.record(role);
      });
    };
  }

 private:
  void record(const ShippingCallbackRole role)
  {
    observation_->deliveries[size_t(role)]++;
  }

  void propagate_device_loss()
  {
    if (device_loss_propagated_) {
      return;
    }
    device_loss_propagated_ = true;
    gw::device_state_mark_lost(*device_state_);
    lifetime_->cancel();
    backbuffer_pending_ = false;
    configuration_pending_ = false;
    present_pipeline_pending_ = false;
    present_pending_ = false;
    observation_->pending_cleared = true;
    if (!initialization_settled_) {
      initialization_settled_ = true;
      observation_->ready_calls++;
      observation_->ready_success = false;
    }
  }

  std::shared_ptr<ShippingCallbackObservation> observation_;
  std::shared_ptr<gw::DeviceCallbackState> device_state_ =
      std::make_shared<gw::DeviceCallbackState>();
  std::shared_ptr<Lifetime> lifetime_;
  bool backbuffer_pending_ = true;
  bool configuration_pending_ = true;
  bool present_pipeline_pending_ = true;
  bool present_pending_ = true;
  bool initialization_settled_ = false;
  bool device_loss_propagated_ = false;
};

class UnsafeReadyProbe {
 public:
  using Lifetime = gw::OwnerCallbackLifetime<UnsafeReadyProbe>;
  using ReadyCallback = std::function<void(bool)>;

  explicit UnsafeReadyProbe(ReadyCallback on_ready)
      : on_ready_(std::move(on_ready)), lifetime_(std::make_shared<Lifetime>(*this))
  {
  }

  ~UnsafeReadyProbe()
  {
    lifetime_->cancel();
    lifetime_->invalidate();
  }

  std::shared_ptr<Lifetime> lifetime() const
  {
    return lifetime_;
  }

  void complete_initialization(const bool success)
  {
    if (on_ready_) {
      on_ready_(success);
    }
  }

 private:
  ReadyCallback on_ready_;
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

int run_unsafe_ready_self_destruction()
{
  const auto observation = std::make_shared<ReadyLifetimeObservation>();
  UnsafeReadyProbe *owner = nullptr;
  owner = new UnsafeReadyProbe(SelfDestroyingReady<UnsafeReadyProbe>{&owner, observation});
  const std::shared_ptr<UnsafeReadyProbe::Lifetime> lifetime = owner->lifetime();
  lifetime->deliver([](UnsafeReadyProbe &loaded_owner) {
    loaded_owner.complete_initialization(true);
  });
  return observation->continued_after_delete ? 0 : 2;
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

bool run_callback_owner_execution_contract()
{
  auto owner = std::make_unique<OwnerExecutionProbe>();
  const std::shared_ptr<OwnerExecutionProbe::Lifetime> lifetime = owner->lifetime();
  ExecutionControl control;
  bool callback_delivered = false;
  bool owner_executed = false;

  std::thread completion([&]() {
    callback_delivered = lifetime->deliver([&](OwnerExecutionProbe & /*loaded_owner*/) {
      enter_execution(control, control.callback_entered);
      while (!control.release_callback.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
      control.active.fetch_sub(1, std::memory_order_acq_rel);
    });
  });
  if (!wait_for(control.callback_entered)) {
    control.release_callback.store(true, std::memory_order_release);
    completion.join();
    return false;
  }

  std::thread owner_thread([&]() {
    control.owner_attempted.store(true, std::memory_order_release);
    owner_executed = owner->public_owner_step(control);
  });
  if (!wait_for(control.owner_attempted)) {
    control.release_callback.store(true, std::memory_order_release);
    completion.join();
    owner_thread.join();
    return false;
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(20));
  const bool owner_waited = !control.owner_entered.load(std::memory_order_acquire);
  control.release_callback.store(true, std::memory_order_release);
  completion.join();
  owner_thread.join();

  return owner_waited && callback_delivered && owner_executed &&
         control.owner_entered.load(std::memory_order_acquire) &&
         control.peak.load(std::memory_order_acquire) == 1;
}

bool run_cleanup_quiescence_contract()
{
  auto owner = std::make_unique<OwnerExecutionProbe>();
  const std::shared_ptr<OwnerExecutionProbe::Lifetime> lifetime = owner->lifetime();
  ExecutionControl control;
  bool cleanup_executed = false;

  std::thread completion([&]() {
    lifetime->deliver([&](OwnerExecutionProbe & /*loaded_owner*/) {
      enter_execution(control, control.callback_entered);
      while (!control.release_callback.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
      control.active.fetch_sub(1, std::memory_order_acq_rel);
    });
  });
  if (!wait_for(control.callback_entered)) {
    control.release_callback.store(true, std::memory_order_release);
    completion.join();
    return false;
  }

  std::thread cleanup([&]() {
    control.cleanup_attempted.store(true, std::memory_order_release);
    cleanup_executed = owner->terminal_cleanup(control);
  });
  if (!wait_for(control.cleanup_attempted)) {
    control.release_callback.store(true, std::memory_order_release);
    completion.join();
    cleanup.join();
    return false;
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(20));
  const bool cleanup_waited = !control.cleanup_entered.load(std::memory_order_acquire);
  control.release_callback.store(true, std::memory_order_release);
  completion.join();
  cleanup.join();

  return cleanup_waited && cleanup_executed &&
         control.cleanup_entered.load(std::memory_order_acquire) &&
         control.peak.load(std::memory_order_acquire) == 1 &&
         !lifetime->deliver([](OwnerExecutionProbe & /*loaded_owner*/) {});
}

bool run_destruction_admission_contract()
{
  const auto control = std::make_shared<RaceControl>();
  auto *owner = new OwnerProbe(control);
  const std::shared_ptr<OwnerProbe::Lifetime> lifetime = owner->lifetime();
  std::atomic<bool> release_active{false};
  bool active_delivered = false;
  bool queued_delivered = false;

  std::thread active([&]() {
    active_delivered = lifetime->deliver([&](OwnerProbe & /*loaded_owner*/) {
      control->callback_has_owner.store(true, std::memory_order_release);
      while (!control->admission_closed.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
      control->nested_delivery_ran.store(
          lifetime->deliver([](OwnerProbe & /*nested_owner*/) {}), std::memory_order_release);
      control->nested_delivery_finished.store(true, std::memory_order_release);
      while (!release_active.load(std::memory_order_acquire)) {
        std::this_thread::yield();
      }
    });
  });
  if (!wait_for(control->callback_has_owner)) {
    release_active.store(true, std::memory_order_release);
    active.join();
    return false;
  }

  std::thread queued([&]() {
    control->queued_delivery_attempted.store(true, std::memory_order_release);
    queued_delivered = lifetime->deliver([&](OwnerProbe & /*loaded_owner*/) {
      control->queued_delivery_ran.store(true, std::memory_order_release);
    });
  });
  if (!wait_for(control->queued_delivery_attempted)) {
    release_active.store(true, std::memory_order_release);
    active.join();
    queued.join();
    return false;
  }

  std::thread destroyer([&]() {
    delete owner;
    control->destructor_returned.store(true, std::memory_order_release);
  });
  if (!wait_for(control->admission_closed) || !wait_for(control->nested_delivery_finished)) {
    release_active.store(true, std::memory_order_release);
    active.join();
    queued.join();
    destroyer.join();
    return false;
  }
  const bool destruction_waited =
      !control->destructor_returned.load(std::memory_order_acquire);
  const bool late_delivery_blocked =
      !control->nested_delivery_ran.load(std::memory_order_acquire) &&
      !control->queued_delivery_ran.load(std::memory_order_acquire);
  release_active.store(true, std::memory_order_release);
  active.join();
  queued.join();
  destroyer.join();

  return active_delivered && !queued_delivered && destruction_waited && late_delivery_blocked &&
         control->destructor_returned.load(std::memory_order_acquire);
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

bool run_loss_initialization_stage(const InitializationStage stage)
{
  const auto ready_observation = std::make_shared<ReadyObservation>();
  auto owner = std::make_unique<InitializationProbe>(stage, ready_observation);
  const std::shared_ptr<InitializationProbe::Lifetime> lifetime = owner->lifetime();
  const auto device_state = std::make_shared<gw::DeviceCallbackState>();

  /* Production shape: the device-lost callback retains only shared state and the owner gate. */
  const auto device_lost = [device_state, lifetime]() {
    return gw::fallback_device_loss_notify(
        device_state, lifetime, [](InitializationProbe &owner) {
          owner.propagate_device_loss();
        });
  };

  const bool delivered = device_lost();
  const bool duplicate_delivered = device_lost();
  const bool pending_completion_delivered =
      lifetime->deliver([](InitializationProbe & /*owner*/) {});
  return delivered && !duplicate_delivered && !pending_completion_delivered &&
         device_state->load(std::memory_order_acquire) == gw::DeviceState::Lost &&
         ready_observation->calls == 1 && !ready_observation->success &&
         !owner->has_pending_initialization();
}

bool run_loss_initialization_contract()
{
  return run_loss_initialization_stage(InitializationStage::BackbufferCreation) &&
         run_loss_initialization_stage(InitializationStage::SurfaceConfiguration);
}

bool run_ready_callback_lifetime_contract()
{
  const auto observation = std::make_shared<ReadyLifetimeObservation>();
  InitializationProbe *owner = nullptr;
  owner = new InitializationProbe(
      InitializationStage::BackbufferCreation,
      SelfDestroyingReady<InitializationProbe>{&owner, observation});
  const std::shared_ptr<InitializationProbe::Lifetime> lifetime = owner->lifetime();
  const bool delivered = lifetime->deliver([](InitializationProbe &loaded_owner) {
    loaded_owner.complete_initialization(true);
  });

  return delivered && owner == nullptr && observation->calls == 1 && observation->success &&
         observation->continued_after_delete &&
         !lifetime->deliver([](InitializationProbe & /*loaded_owner*/) {});
}

bool run_shipping_callback_matrix_contract()
{
  using Role = ShippingCallbackRole;
  using Completion = ShippingContextProbe::Completion;
  const auto observation = std::make_shared<ShippingCallbackObservation>();
  auto owner = std::make_unique<ShippingContextProbe>(observation);
  std::array<Completion, shipping_callback_role_count> completions;
  for (size_t index = 0; index < completions.size(); index++) {
    completions[index] = owner->make_completion(Role(index));
  }

  /* Exercise the seven ordinary shipping roles while the owner and device are active. */
  for (size_t index = 0; index < size_t(Role::FallbackDeviceLoss); index++) {
    if (!completions[index]() || observation->deliveries[index] != 1) {
      return false;
    }
  }
  if (!completions[size_t(Role::FallbackDeviceLoss)]() ||
      observation->deliveries[size_t(Role::FallbackDeviceLoss)] != 1 ||
      observation->ready_calls != 1 || observation->ready_success ||
      !observation->pending_cleared)
  {
    return false;
  }

  /* Terminal loss closes owner admission for all already-retained completions. */
  for (Completion &completion : completions) {
    if (completion()) {
      return false;
    }
  }
  owner.reset();
  if (observation->destroyed != 1) {
    return false;
  }
  for (Completion &completion : completions) {
    if (completion()) {
      return false;
    }
  }

  /* Independent destruction before any delivery rejects every role, including loss. */
  const auto destroyed_observation = std::make_shared<ShippingCallbackObservation>();
  auto destroyed_owner = std::make_unique<ShippingContextProbe>(destroyed_observation);
  std::array<Completion, shipping_callback_role_count> delayed;
  for (size_t index = 0; index < delayed.size(); index++) {
    delayed[index] = destroyed_owner->make_completion(Role(index));
  }
  destroyed_owner.reset();
  for (Completion &completion : delayed) {
    if (completion()) {
      return false;
    }
  }
  if (destroyed_observation->destroyed != 1 || destroyed_observation->ready_calls != 0) {
    return false;
  }
  for (const int deliveries : destroyed_observation->deliveries) {
    if (deliveries != 0) {
      return false;
    }
  }
  return true;
}

}  // namespace

int main(int argc, char **argv)
{
  if (argc == 2 && std::string_view(argv[1]) == "--unsafe-owner-race") {
    return run_unsafe_owner_race();
  }
  if (argc == 2 && std::string_view(argv[1]) == "--unsafe-ready-self-destroy") {
    return run_unsafe_ready_self_destruction();
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
  if (!run_callback_owner_execution_contract()) {
    std::fprintf(stderr, "FAIL: callback/owner execution contract\n");
    return 1;
  }
  if (!run_cleanup_quiescence_contract()) {
    std::fprintf(stderr, "FAIL: terminal cleanup quiescence contract\n");
    return 1;
  }
  if (!run_destruction_admission_contract()) {
    std::fprintf(stderr, "FAIL: destruction admission contract\n");
    return 1;
  }
  if (!run_imported_loss_contract()) {
    std::fprintf(stderr, "FAIL: imported-device loss callback contract\n");
    return 1;
  }
  if (!run_loss_initialization_contract()) {
    std::fprintf(stderr, "FAIL: fallback loss initialization-settlement contract\n");
    return 1;
  }
  if (!run_ready_callback_lifetime_contract()) {
    std::fprintf(stderr, "FAIL: ready-callback lifetime contract\n");
    return 1;
  }
  if (!run_shipping_callback_matrix_contract()) {
    std::fprintf(stderr, "FAIL: shipping callback role matrix contract\n");
    return 1;
  }
  std::puts("CONTRACT ghost_owner_lifetime PASS concurrent=1 reentrant=1 delayed=blocked");
  std::puts("CONTRACT ghost_owner_serialization PASS concurrent=serialized nested=1");
  std::puts("CONTRACT ghost_owner_execution PASS callback_owner=serialized cleanup=quiescent");
  std::puts("CONTRACT ghost_destruction_admission PASS nested=blocked queued=blocked");
  std::puts("CONTRACT ghost_imported_loss_callback PASS pending=allow settled=block sticky=1 replaced=block");
  std::puts("CONTRACT ghost_loss_init_settlement PASS backbuffer=failed_once configuration=failed_once pending=cleared raw_owner=0");
  std::puts("CONTRACT ghost_ready_callback_lifetime PASS self_destroy=continued member_cleared=1");
  std::puts("CONTRACT ghost_shipping_callback_matrix PASS roles=8 active=7 loss=1 post_loss=blocked post_destroy=blocked");
  return 0;
}
