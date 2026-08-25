/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <cstdint>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

enum class PrimitiveType { Line, Polyline, Arc, Curve, Box, Circle };
enum class CacheState { Ready, Pending, Failed };
enum class OperationState { Idle, Pending, Modal, Finished, Cancelled, Failed };
enum class EventKind { MouseMove, Navigation, Confirm, Cancel, Other };

struct Context {
  int manager;
  int window;
  int screen;
  int area;
  int region;
  int region_view;
  int view3d;
  int depsgraph;
  int scene;
  int view_layer;
  int object;
  int grease_pencil;
  int layer;
  int drawing;
  int paint;
  int brush;
  int frame;

  bool operator==(const Context &) const = default;
};

struct InvokeInput {
  PrimitiveType type;
  int subdivision;
  int start_x;
  int start_y;

  bool operator==(const InvokeInput &) const = default;
};

struct Event {
  EventKind kind;
  int x;
  int y;
  int custom;
  bool has_customdata;
  bool has_next;
  bool has_prev;
  bool customdata_free;
};

[[noreturn]] void fail(const std::string &message)
{
  throw std::runtime_error(message);
}

void expect(const bool condition, const std::string &message)
{
  if (!condition) {
    fail(message);
  }
}

uint64_t mix(uint64_t hash, const uint64_t value)
{
  hash ^= value;
  hash *= UINT64_C(1099511628211);
  return hash;
}

class PrimitiveDepthContinuation {
 public:
  static constexpr int max_ticks = 240;
  static constexpr int max_events = 256;

  void begin(const bool needs_depth,
             const CacheState cache_state,
             const InvokeInput &input,
             const Context &context)
  {
    expect(state_ == OperationState::Idle, "begin state");
    invoke_input_ = input;
    cursor_owned_ = true;
    if (!needs_depth || cache_state != CacheState::Pending) {
      initialize();
      return;
    }

    producing_context_ = context;
    request_owned_ = true;
    timer_owned_ = true;
    modal_handler_owned_ = true;
    state_ = OperationState::Pending;
  }

  OperationState handle(const Event &event)
  {
    if (state_ == OperationState::Pending) {
      if (event.kind == EventKind::Cancel) {
        cancel();
        return state_;
      }
      if (event.custom != 0 || event.has_customdata ||
          queued_events_.size() >= max_events)
      {
        fail_closed();
        return state_;
      }
      Event safe = event;
      safe.custom = 0;
      safe.has_customdata = false;
      safe.has_next = false;
      safe.has_prev = false;
      safe.customdata_free = false;
      queued_events_.push_back(safe);
      return state_;
    }
    if (state_ == OperationState::Modal) {
      dispatch(event);
    }
    return state_;
  }

  OperationState tick(const Context &context, const CacheState cache_state)
  {
    if (state_ != OperationState::Pending) {
      return state_;
    }
    if (context != producing_context_ || ++tick_count_ > max_ticks ||
        cache_state == CacheState::Failed)
    {
      fail_closed();
      return state_;
    }
    if (cache_state == CacheState::Pending) {
      return state_;
    }

    request_owned_ = false;
    timer_owned_ = false;
    tick_count_ = 0;
    std::vector<Event> queued = std::move(queued_events_);
    initialize();
    for (const Event &event : queued) {
      if (state_ != OperationState::Modal) {
        break;
      }
      dispatch(event);
    }
    return state_;
  }

  void cancel()
  {
    terminal_cleanup();
    state_ = OperationState::Cancelled;
  }

  OperationState state() const
  {
    return state_;
  }
  int initialization_count() const
  {
    return initialization_count_;
  }
  int navigation_event_count() const
  {
    return navigation_event_count_;
  }
  size_t queued_event_count() const
  {
    return queued_events_.size();
  }
  bool cursor_owned() const
  {
    return cursor_owned_;
  }
  bool navigation_owned() const
  {
    return navigation_owned_;
  }
  bool request_owned() const
  {
    return request_owned_;
  }
  bool timer_owned() const
  {
    return timer_owned_;
  }
  bool modal_handler_owned() const
  {
    return modal_handler_owned_;
  }
  const std::optional<std::pair<int, int>> &first_projection() const
  {
    return first_projection_;
  }
  const std::optional<std::pair<int, int>> &latest_mouse() const
  {
    return latest_mouse_;
  }
  const std::vector<EventKind> &dispatched_events() const
  {
    return dispatched_events_;
  }

  uint64_t digest() const
  {
    uint64_t hash = UINT64_C(1469598103934665603);
    hash = mix(hash, static_cast<uint64_t>(state_));
    hash = mix(hash, static_cast<uint64_t>(initialization_count_));
    hash = mix(hash, static_cast<uint64_t>(navigation_event_count_));
    hash = mix(hash, cursor_owned_);
    hash = mix(hash, navigation_owned_);
    hash = mix(hash, request_owned_);
    hash = mix(hash, timer_owned_);
    hash = mix(hash, modal_handler_owned_);
    if (first_projection_) {
      hash = mix(hash, static_cast<uint32_t>(first_projection_->first));
      hash = mix(hash, static_cast<uint32_t>(first_projection_->second));
    }
    for (const EventKind kind : dispatched_events_) {
      hash = mix(hash, static_cast<uint64_t>(kind));
    }
    return hash;
  }

 private:
  void initialize()
  {
    expect(invoke_input_.has_value(), "missing invoke snapshot");
    expect(initialization_count_ == 0, "double initialization");
    first_projection_ = std::pair(invoke_input_->start_x, invoke_input_->start_y);
    navigation_owned_ = true;
    modal_handler_owned_ = true;
    ++initialization_count_;
    state_ = OperationState::Modal;
  }

  void dispatch(const Event &event)
  {
    expect(initialization_count_ == 1, "event before initialization");
    dispatched_events_.push_back(event.kind);
    if (event.kind == EventKind::Navigation) {
      ++navigation_event_count_;
    }
    else if (event.kind == EventKind::MouseMove) {
      latest_mouse_ = std::pair(event.x, event.y);
    }
    else if (event.kind == EventKind::Confirm) {
      terminal_cleanup();
      state_ = OperationState::Finished;
    }
    else if (event.kind == EventKind::Cancel) {
      cancel();
    }
  }

  void terminal_cleanup()
  {
    request_owned_ = false;
    timer_owned_ = false;
    cursor_owned_ = false;
    navigation_owned_ = false;
    modal_handler_owned_ = false;
    queued_events_.clear();
    tick_count_ = 0;
  }

  void fail_closed()
  {
    terminal_cleanup();
    state_ = OperationState::Failed;
  }

  OperationState state_ = OperationState::Idle;
  Context producing_context_ = {};
  std::optional<InvokeInput> invoke_input_;
  std::vector<Event> queued_events_;
  std::vector<EventKind> dispatched_events_;
  std::optional<std::pair<int, int>> first_projection_;
  std::optional<std::pair<int, int>> latest_mouse_;
  int tick_count_ = 0;
  int initialization_count_ = 0;
  int navigation_event_count_ = 0;
  bool cursor_owned_ = false;
  bool navigation_owned_ = false;
  bool request_owned_ = false;
  bool timer_owned_ = false;
  bool modal_handler_owned_ = false;
};

constexpr Context base_context = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17};
constexpr InvokeInput line_input = {PrimitiveType::Line, 4, 120, 240};
constexpr Event mouse_event = {EventKind::MouseMove, 130, 255, 0, false, true, true, false};
constexpr Event navigation_event = {
    EventKind::Navigation, 0, 0, 0, false, true, true, false};
constexpr Event confirm_event = {EventKind::Confirm, 0, 0, 0, false, true, true, false};
constexpr Event cancel_event = {EventKind::Cancel, 0, 0, 0, false, false, false, false};

uint64_t contract_native_immediate()
{
  uint64_t digest = 0;
  for (const PrimitiveType type : {PrimitiveType::Line,
                                   PrimitiveType::Polyline,
                                   PrimitiveType::Arc,
                                   PrimitiveType::Curve,
                                   PrimitiveType::Box,
                                   PrimitiveType::Circle})
  {
    PrimitiveDepthContinuation continuation;
    const InvokeInput input = {type, 3, 40 + int(type), 80 + int(type)};
    continuation.begin(true, CacheState::Ready, input, base_context);
    expect(continuation.state() == OperationState::Modal, "ready modal state");
    expect(continuation.first_projection() ==
               std::optional(std::pair(input.start_x, input.start_y)),
           "ready first projection");
    expect(continuation.navigation_owned() && continuation.cursor_owned(),
           "ready modal ownership");
    digest ^= continuation.digest();
  }

  PrimitiveDepthContinuation view_plane;
  view_plane.begin(false, CacheState::Pending, line_input, base_context);
  expect(view_plane.state() == OperationState::Modal, "non-depth immediate path");
  digest ^= view_plane.digest();

  PrimitiveDepthContinuation failed;
  failed.begin(true, CacheState::Failed, line_input, base_context);
  expect(failed.state() == OperationState::Modal && failed.cursor_owned() &&
             failed.first_projection() == std::optional(std::pair(120, 240)),
         "initial failure fallback");
  return digest ^ failed.digest();
}

uint64_t contract_pending_before_projection()
{
  PrimitiveDepthContinuation continuation;
  InvokeInput mutable_input = line_input;
  continuation.begin(true, CacheState::Pending, mutable_input, base_context);
  mutable_input.start_x = 999;
  mutable_input.start_y = 999;
  expect(continuation.state() == OperationState::Pending, "pending state");
  expect(!continuation.first_projection() && continuation.initialization_count() == 0,
         "projection occurred while pending");
  expect(!continuation.navigation_owned() && continuation.cursor_owned() &&
             continuation.modal_handler_owned(),
         "pending cursor/navigation ownership");
  expect(continuation.tick(base_context, CacheState::Ready) == OperationState::Modal,
         "pending settlement");
  expect(continuation.first_projection() == std::optional(std::pair(120, 240)),
         "invoke snapshot ownership");
  return continuation.digest();
}

uint64_t contract_event_fifo_navigation()
{
  PrimitiveDepthContinuation continuation;
  continuation.begin(true, CacheState::Pending, line_input, base_context);
  continuation.handle(mouse_event);
  continuation.handle(navigation_event);
  continuation.handle(confirm_event);
  expect(continuation.queued_event_count() == 3, "queued event count");
  expect(continuation.tick(base_context, CacheState::Ready) == OperationState::Finished,
         "queued confirm result");
  expect(continuation.dispatched_events() ==
             std::vector<EventKind>(
                 {EventKind::MouseMove, EventKind::Navigation, EventKind::Confirm}),
         "event FIFO order");
  expect(continuation.latest_mouse() == std::optional(std::pair(130, 255)),
         "mouse replay");
  expect(continuation.navigation_event_count() == 1, "navigation replay");
  expect(!continuation.cursor_owned() && !continuation.navigation_owned() &&
             !continuation.modal_handler_owned(),
         "confirm teardown");
  return continuation.digest();
}

uint64_t contract_context_guards()
{
  uint64_t digest = 0;
  for (int lane = 0; lane < 6; ++lane) {
    PrimitiveDepthContinuation continuation;
    continuation.begin(true, CacheState::Pending, line_input, base_context);
    Context drift = base_context;
    if (lane == 0) {
      drift.manager += 100;
    }
    else if (lane == 1) {
      drift.region += 100;
    }
    else if (lane == 2) {
      drift.view3d += 100;
    }
    else if (lane == 3) {
      drift.scene += 100;
    }
    else if (lane == 4) {
      drift.object += 100;
    }
    else {
      drift.layer += 100;
    }
    expect(continuation.tick(drift, CacheState::Ready) == OperationState::Failed,
           "context drift result");
    expect(continuation.initialization_count() == 0 && !continuation.request_owned(),
           "context drift mutation");
    digest ^= continuation.digest();
  }
  return digest;
}

uint64_t contract_failure_timeout()
{
  PrimitiveDepthContinuation backend_failure;
  backend_failure.begin(true, CacheState::Pending, line_input, base_context);
  backend_failure.handle(mouse_event);
  expect(backend_failure.tick(base_context, CacheState::Failed) == OperationState::Failed,
         "backend failure");
  expect(backend_failure.queued_event_count() == 0 && !backend_failure.timer_owned(),
         "backend failure cleanup");

  PrimitiveDepthContinuation timeout;
  timeout.begin(true, CacheState::Pending, line_input, base_context);
  for (int tick = 0; tick < PrimitiveDepthContinuation::max_ticks; ++tick) {
    expect(timeout.tick(base_context, CacheState::Pending) == OperationState::Pending,
           "bounded pending tick");
  }
  expect(timeout.tick(base_context, CacheState::Pending) == OperationState::Failed,
         "timeout boundary");
  return backend_failure.digest() ^ timeout.digest();
}

uint64_t contract_event_safety_bound()
{
  PrimitiveDepthContinuation accepted;
  accepted.begin(true, CacheState::Pending, line_input, base_context);
  for (int index = 0; index < PrimitiveDepthContinuation::max_events; ++index) {
    accepted.handle({EventKind::Other, index, index + 1, 0, false, true, true, false});
  }
  expect(accepted.state() == OperationState::Pending &&
             accepted.queued_event_count() == PrimitiveDepthContinuation::max_events,
         "exact event bound");

  PrimitiveDepthContinuation overflow;
  overflow.begin(true, CacheState::Pending, line_input, base_context);
  for (int index = 0; index <= PrimitiveDepthContinuation::max_events; ++index) {
    overflow.handle({EventKind::Other, index, index, 0, false, false, false, false});
  }
  expect(overflow.state() == OperationState::Failed && overflow.queued_event_count() == 0,
         "event overflow cleanup");

  PrimitiveDepthContinuation borrowed;
  borrowed.begin(true, CacheState::Pending, line_input, base_context);
  borrowed.handle({EventKind::Other, 0, 0, 7, true, true, true, true});
  expect(borrowed.state() == OperationState::Failed && !borrowed.request_owned(),
         "borrowed payload rejection");
  return accepted.digest() ^ overflow.digest() ^ borrowed.digest();
}

uint64_t contract_cancel_teardown()
{
  PrimitiveDepthContinuation pending;
  pending.begin(true, CacheState::Pending, line_input, base_context);
  expect(pending.handle(cancel_event) == OperationState::Cancelled, "pending cancel");
  expect(!pending.cursor_owned() && !pending.request_owned() && !pending.timer_owned() &&
             !pending.modal_handler_owned(),
         "pending cancel teardown");

  PrimitiveDepthContinuation modal;
  modal.begin(false, CacheState::Pending, line_input, base_context);
  expect(modal.handle(cancel_event) == OperationState::Cancelled, "modal cancel");
  expect(!modal.navigation_owned() && !modal.cursor_owned(), "modal navigation teardown");
  return pending.digest() ^ modal.digest();
}

uint64_t contract_exact_once()
{
  PrimitiveDepthContinuation continuation;
  continuation.begin(true, CacheState::Pending, line_input, base_context);
  continuation.handle(mouse_event);
  expect(continuation.tick(base_context, CacheState::Ready) == OperationState::Modal,
         "first settlement");
  expect(continuation.tick(base_context, CacheState::Ready) == OperationState::Modal,
         "second settlement observation");
  expect(continuation.initialization_count() == 1 &&
             continuation.dispatched_events() == std::vector<EventKind>({EventKind::MouseMove}),
         "exact-once initialization/replay");

  PrimitiveDepthContinuation immediate;
  immediate.begin(true, CacheState::Ready, line_input, base_context);
  expect(immediate.tick(base_context, CacheState::Ready) == OperationState::Modal &&
             immediate.initialization_count() == 1,
         "native exact-once observation");
  return continuation.digest() ^ immediate.digest();
}

void emit(const char *name, const int cases, const uint64_t digest)
{
  std::cout << "CONTRACT " << name << " PASS cases=" << cases << " digest=" << digest << '\n';
}

}  // namespace

int main()
{
  try {
    emit("native_immediate", 8, contract_native_immediate());
    emit("pending_before_projection", 2, contract_pending_before_projection());
    emit("event_fifo_navigation", 3, contract_event_fifo_navigation());
    emit("context_guards", 6, contract_context_guards());
    emit("failure_timeout", 2, contract_failure_timeout());
    emit("event_safety_bound", 3, contract_event_safety_bound());
    emit("cancel_teardown", 2, contract_cancel_teardown());
    emit("exact_once", 2, contract_exact_once());
    std::cout <<
        "M5_GREASE_PENCIL_PRIMITIVE_DEPTH_CACHE_CONTRACT_PASS contracts=8 cases=28\n";
  }
  catch (const std::exception &error) {
    std::cerr << "M5_GREASE_PENCIL_PRIMITIVE_DEPTH_CACHE_CONTRACT_FAIL " << error.what()
              << '\n';
    return 1;
  }
  return 0;
}
