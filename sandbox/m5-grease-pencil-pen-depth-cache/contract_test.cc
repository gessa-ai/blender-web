// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

#include <functional>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

enum class DepthStart { NonDepth, Ready, Pending, Failed };
enum class DepthPoll { Pending, Ready, Failed };
enum class Status { Running, Finished, Cancelled };
enum class EventType { Press, Move, Release, Escape, Timer };

struct Event {
  EventType type = EventType::Move;
  int serial = 0;
  int value = 0;
  int mouse_x = 0;
  int timer_id = 0;
  bool custom_payload = false;
};

struct ContextIdentity {
  int manager = 1;
  int window = 2;
  int screen = 3;
  int area = 4;
  int region = 5;
  int region_view = 6;
  int view3d = 7;
  int depsgraph = 8;
  int scene = 9;
  int view_layer = 10;
  int object = 11;
  int evaluated_object = 12;
  int grease_pencil = 13;
  int active_layer = 14;
  int frame = 15;
  bool point_selection = true;

  bool operator==(const ContextIdentity &) const = default;
};

class PenInitializationModel {
 public:
  static constexpr int owned_timer = 77;
  static constexpr int max_ticks = 240;
  static constexpr int max_events = 256;

  ContextIdentity producing;
  ContextIdentity current;
  DepthPoll poll_result = DepthPoll::Pending;

  bool pending = false;
  bool initialized = false;
  bool retired = false;
  bool request_owned = false;
  bool cache_ready = false;
  bool initial_fallback = false;
  int tick_count = 0;
  int duplicated_keyframes = 0;
  int captured_drawings = 0;
  int captured_transforms = 0;
  int first_event_calls = 0;
  int modal_event_calls = 0;
  int first_value = -1;
  int first_mouse_x = -1;
  std::optional<Event> start_event;
  std::vector<Event> events;
  std::vector<int> trace;

  Status begin(const DepthStart depth, const Event &event, const bool timer_available = true)
  {
    cache_ready = depth == DepthStart::Ready;
    initial_fallback = depth == DepthStart::Failed;
    if (depth != DepthStart::Pending) {
      initialize_ready();
      invoke_initialized(event);
      return Status::Running;
    }

    if (!safe_event(event) || !timer_available) {
      retire();
      return Status::Cancelled;
    }
    producing = current;
    start_event = event;
    events.clear();
    tick_count = 0;
    pending = true;
    request_owned = true;
    return Status::Running;
  }

  Status dispatch(const Event &event)
  {
    if (!pending || current != producing) {
      retire();
      return Status::Cancelled;
    }
    if (event.type == EventType::Escape) {
      retire();
      return Status::Cancelled;
    }
    if (event.type != EventType::Timer || event.timer_id != owned_timer) {
      if (event.type == EventType::Timer) {
        return Status::Running;
      }
      if (!safe_event(event) || int(events.size()) >= max_events) {
        retire();
        return Status::Cancelled;
      }
      events.push_back(event);
      return Status::Running;
    }

    if (++tick_count > max_ticks) {
      retire();
      return Status::Cancelled;
    }
    if (poll_result == DepthPoll::Pending) {
      return Status::Running;
    }
    if (poll_result == DepthPoll::Failed || !start_event.has_value()) {
      retire();
      return Status::Cancelled;
    }

    const Event retained_start = *start_event;
    std::vector<Event> retained_events = std::move(events);
    start_event.reset();
    pending = false;
    request_owned = false;
    cache_ready = true;
    initialize_ready();
    invoke_initialized(retained_start);
    for (const Event &queued : retained_events) {
      const Status status = modal(queued);
      if (status != Status::Running) {
        return status;
      }
    }
    return Status::Running;
  }

  Status modal(const Event &event)
  {
    ++modal_event_calls;
    trace.push_back(2000 + event.serial);
    return event.type == EventType::Release ? Status::Finished : Status::Running;
  }

  void retire()
  {
    pending = false;
    request_owned = false;
    start_event.reset();
    events.clear();
    retired = true;
  }

 private:
  static bool safe_event(const Event &event)
  {
    return event.type != EventType::Timer && !event.custom_payload;
  }

  void initialize_ready()
  {
    if (initialized || pending) {
      throw std::runtime_error("ready tail entered in the wrong phase");
    }
    duplicated_keyframes = 2;
    captured_drawings = 2;
    captured_transforms = 2;
    initialized = true;
  }

  void invoke_initialized(const Event &event)
  {
    if (!initialized) {
      throw std::runtime_error("first event ran before initialization");
    }
    ++first_event_calls;
    first_value = event.value;
    first_mouse_x = event.mouse_x;
    trace.push_back(1000 + event.serial);
  }
};

void require(const bool condition, const std::string &message)
{
  if (!condition) {
    throw std::runtime_error(message);
  }
}

Event first_event(const int serial = 1, const int value = 11, const int mouse_x = 101)
{
  return {EventType::Press, serial, value, mouse_x, 0, false};
}

Event timer_event(const int timer_id = PenInitializationModel::owned_timer)
{
  return {EventType::Timer, 900, 0, 0, timer_id, false};
}

void contract(const std::string &name, const int cases, const std::function<void()> &body)
{
  body();
  std::cout << "CONTRACT " << name << " PASS cases=" << cases << '\n';
}

}  // namespace

int main()
{
  try {
    contract("operation_owned_request", 3, [] {
      PenInitializationModel model;
      require(model.begin(DepthStart::Pending, first_event()) == Status::Running,
              "pending begin failed");
      require(model.pending && model.request_owned && model.start_event.has_value(),
              "pending request is not owned");
      model.retire();
      require(model.retired && !model.request_owned && !model.start_event.has_value(),
              "retirement retained request state");
    });

    contract("native_immediate_and_initial_fallback", 3, [] {
      for (const DepthStart depth : {DepthStart::NonDepth, DepthStart::Ready, DepthStart::Failed}) {
        PenInitializationModel model;
        require(model.begin(depth, first_event()) == Status::Running, "immediate begin failed");
        require(model.initialized && model.first_event_calls == 1 && !model.pending,
                "immediate path did not finish on the original stack");
        require(model.initial_fallback == (depth == DepthStart::Failed),
                "initial failure fallback differs");
      }
    });

    contract("pre_mutation_suspension", 3, [] {
      PenInitializationModel model;
      model.begin(DepthStart::Pending, first_event());
      require(model.duplicated_keyframes == 0, "keyframes changed before settlement");
      require(model.captured_drawings == 0, "drawings captured before settlement");
      require(model.captured_transforms == 0, "layer transforms captured before settlement");
    });

    contract("shared_post_initialize_seam", 3, [] {
      PenInitializationModel immediate;
      immediate.begin(DepthStart::Ready, first_event(5, 22, 303));
      PenInitializationModel deferred;
      deferred.begin(DepthStart::Pending, first_event(5, 22, 303));
      deferred.poll_result = DepthPoll::Ready;
      require(deferred.dispatch(timer_event()) == Status::Running, "ready poll failed");
      require(immediate.trace == deferred.trace, "immediate/deferred first-event trace differs");
      require(deferred.first_event_calls == 1, "deferred first event ran more than once");
    });

    contract("retained_first_event_and_fifo", 4, [] {
      PenInitializationModel model;
      model.begin(DepthStart::Pending, first_event(7, 33, 404));
      require(model.dispatch({EventType::Move, 8, 0, 405, 0, false}) == Status::Running,
              "move queue failed");
      require(model.dispatch({EventType::Release, 9, 0, 406, 0, false}) == Status::Running,
              "release queue failed");
      model.poll_result = DepthPoll::Ready;
      require(model.dispatch(timer_event()) == Status::Finished, "queued release was not terminal");
      require(model.trace == std::vector<int>({1007, 2008, 2009}), "FIFO replay order differs");
      require(model.first_value == 33 && model.first_mouse_x == 404,
              "initiating event fields were not retained exactly");
    });

    contract("stock_layer_transform_tail", 3, [] {
      PenInitializationModel immediate;
      immediate.begin(DepthStart::Ready, first_event());
      require(immediate.duplicated_keyframes == 2 && immediate.captured_drawings == 2 &&
                  immediate.captured_transforms == 2,
              "immediate stock tail differs");
      PenInitializationModel deferred;
      deferred.begin(DepthStart::Pending, first_event());
      deferred.poll_result = DepthPoll::Ready;
      deferred.dispatch(timer_event());
      require(deferred.duplicated_keyframes == immediate.duplicated_keyframes &&
                  deferred.captured_drawings == immediate.captured_drawings &&
                  deferred.captured_transforms == immediate.captured_transforms,
              "deferred stock tail differs");
    });

    contract("producing_context_guard", 4, [] {
      for (const int drift : {0, 1, 2, 3}) {
        PenInitializationModel model;
        model.begin(DepthStart::Pending, first_event());
        if (drift == 0) {
          ++model.current.manager;
        }
        else if (drift == 1) {
          ++model.current.region;
        }
        else if (drift == 2) {
          ++model.current.object;
        }
        else {
          ++model.current.frame;
        }
        require(model.dispatch({EventType::Move, 2}) == Status::Cancelled,
                "producing-context drift was accepted");
        require(model.retired && !model.initialized, "context failure mutated drawing state");
      }
    });

    contract("bounded_identified_poll", 5, [] {
      PenInitializationModel foreign;
      foreign.begin(DepthStart::Pending, first_event());
      require(foreign.dispatch(timer_event(99)) == Status::Running && foreign.tick_count == 0,
              "foreign timer advanced the request");

      PenInitializationModel timeout;
      timeout.begin(DepthStart::Pending, first_event());
      for (int i = 0; i < PenInitializationModel::max_ticks; ++i) {
        require(timeout.dispatch(timer_event()) == Status::Running, "bounded poll ended early");
      }
      require(timeout.dispatch(timer_event()) == Status::Cancelled, "timeout bound was weakened");

      PenInitializationModel queue;
      queue.begin(DepthStart::Pending, first_event());
      for (int i = 0; i < PenInitializationModel::max_events; ++i) {
        require(queue.dispatch({EventType::Move, i + 10}) == Status::Running,
                "bounded FIFO rejected a safe event early");
      }
      require(queue.events.size() == PenInitializationModel::max_events,
              "bounded FIFO size differs");
      require(queue.dispatch({EventType::Move, 999}) == Status::Cancelled,
              "bounded FIFO accepted overflow");
    });

    contract("failure_timeout_cancellation", 5, [] {
      PenInitializationModel no_timer;
      require(no_timer.begin(DepthStart::Pending, first_event(), false) == Status::Cancelled,
              "timer allocation failure was accepted");

      PenInitializationModel unsafe_start;
      Event unsafe = first_event();
      unsafe.custom_payload = true;
      require(unsafe_start.begin(DepthStart::Pending, unsafe) == Status::Cancelled,
              "unsafe initiating payload was retained");

      PenInitializationModel backend;
      backend.begin(DepthStart::Pending, first_event());
      backend.poll_result = DepthPoll::Failed;
      require(backend.dispatch(timer_event()) == Status::Cancelled,
              "backend failure did not cancel");

      PenInitializationModel escape;
      escape.begin(DepthStart::Pending, first_event());
      require(escape.dispatch({EventType::Escape, 4}) == Status::Cancelled,
              "Escape did not cancel");

      PenInitializationModel external;
      external.begin(DepthStart::Pending, first_event());
      external.retire();
      require(external.retired && !external.pending && !external.request_owned &&
                  external.events.empty(),
              "external cancellation retained owned state");
    });
  }
  catch (const std::exception &error) {
    std::cerr << "M5_GREASE_PENCIL_PEN_DEPTH_CACHE_CONTRACT_FAIL " << error.what() << '\n';
    return 1;
  }

  std::cout << "M5_GREASE_PENCIL_PEN_DEPTH_CACHE_CONTRACT_PASS contracts=9 cases=33\n";
  return 0;
}
