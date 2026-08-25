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

enum class DepthStart { Ready, Pending, Failed };
enum class DepthPoll { Pending, Ready, Failed };
enum class Status { Running, Finished, Cancelled, PassedThrough };
enum class EventType { Press, Move, Release, Confirm, Cancel, TranslateOn, Escape, Timer };

struct Event {
  EventType type = EventType::Move;
  int serial = 0;
  int value = 0;
  int mouse_x = 0;
  int mouse_y = 0;
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
  int active_object = 11;

  bool operator==(const ContextIdentity &) const = default;
};

struct ProducerState {
  int frame = 1;
  std::vector<int> selected_objects = {11, 12, 13};
  std::vector<int> object_transforms = {101, 102, 103};

  bool operator==(const ProducerState &) const = default;
};

class AxisTargetModel {
 public:
  static constexpr int owned_timer = 72;
  static constexpr int max_ticks = 240;
  static constexpr int max_events = 256;

  ContextIdentity producing;
  ContextIdentity current;
  ProducerState current_state;
  std::optional<ProducerState> producing_state;
  DepthPoll poll_result = DepthPoll::Pending;

  bool overlay_hidden = false;
  bool pending = false;
  bool initialized = false;
  bool retired = false;
  bool request_owned = false;
  bool timer_owned = false;
  bool depths_owned = false;
  bool no_depth_warning = false;
  bool translate = false;
  bool consume_succeeds = true;
  int prepare_calls = 0;
  int restore_calls = 0;
  int tick_count = 0;
  int selected_captures = 0;
  int producer_state_captures = 0;
  int transform_backups = 0;
  int restored_backups = 0;
  int start_type = -1;
  int start_mouse_x = -1;
  int start_mouse_y = -1;
  std::optional<Event> start_event;
  std::vector<Event> events;
  std::vector<int> trace;

  Status begin(const DepthStart depth,
               const Event &event,
               const bool timer_available = true,
               const bool compatible_target = true)
  {
    if (!compatible_target) {
      return Status::PassedThrough;
    }

    overlay_hidden = true;
    ++prepare_calls;
    overlay_hidden = false;
    ++restore_calls;

    if (depth == DepthStart::Failed) {
      no_depth_warning = true;
      retire();
      return Status::Cancelled;
    }
    if (depth == DepthStart::Ready) {
      depths_owned = true;
      initialize_ready(event);
      return Status::Running;
    }
    if (!timer_available) {
      retire();
      return Status::Cancelled;
    }

    producing = current;
    producing_state = current_state;
    ++producer_state_captures;
    Event retained = event;
    retained.custom_payload = false;
    start_event = retained;
    events.clear();
    tick_count = 0;
    pending = true;
    request_owned = true;
    timer_owned = true;
    return Status::Running;
  }

  Status dispatch(const Event &event)
  {
    if (!pending || current != producing || !producing_state.has_value() ||
        current_state != *producing_state || !start_event.has_value())
    {
      retire();
      return Status::Cancelled;
    }
    if (event.type == EventType::Escape || event.type == EventType::Cancel) {
      retire();
      return Status::Cancelled;
    }
    if (event.type != EventType::Timer || event.timer_id != owned_timer) {
      if (event.type == EventType::Timer) {
        return Status::Running;
      }
      if (event.custom_payload || int(events.size()) >= max_events) {
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
    if (poll_result == DepthPoll::Failed || !consume_succeeds) {
      retire();
      return Status::Cancelled;
    }

    const Event retained_start = *start_event;
    std::vector<Event> retained_events = std::move(events);
    start_event.reset();
    producing_state.reset();
    pending = false;
    request_owned = false;
    timer_owned = false;
    depths_owned = true;
    initialize_ready(retained_start);
    for (const Event &queued : retained_events) {
      const Status status = modal(queued);
      if (status != Status::Running) {
        return status;
      }
    }
    return Status::Running;
  }

  void external_cancel()
  {
    retire();
  }

 private:
  void initialize_ready(const Event &event)
  {
    if (initialized || pending || !depths_owned) {
      throw std::runtime_error("ready tail entered in the wrong phase");
    }
    selected_captures = 3;
    transform_backups = 3;
    start_type = int(event.type);
    start_mouse_x = event.mouse_x;
    start_mouse_y = event.mouse_y;
    trace.push_back(1000 + event.serial);
    initialized = true;
  }

  Status modal(const Event &event)
  {
    trace.push_back(2000 + event.serial);
    if (event.type == EventType::TranslateOn) {
      translate = true;
    }
    if (event.type == EventType::Confirm ||
        (event.type == EventType::Release && start_type == int(EventType::Press)))
    {
      return Status::Finished;
    }
    return Status::Running;
  }

  void retire()
  {
    if (initialized) {
      restored_backups = transform_backups;
    }
    overlay_hidden = false;
    pending = false;
    request_owned = false;
    timer_owned = false;
    depths_owned = false;
    start_event.reset();
    producing_state.reset();
    events.clear();
    retired = true;
  }
};

void require(const bool condition, const std::string &message)
{
  if (!condition) {
    throw std::runtime_error(message);
  }
}

Event start_event(const int serial = 1,
                  const int value = 11,
                  const int mouse_x = 101,
                  const int mouse_y = 202,
                  const bool custom = false)
{
  return {EventType::Press, serial, value, mouse_x, mouse_y, 0, custom};
}

Event timer_event(const int timer_id = AxisTargetModel::owned_timer)
{
  return {EventType::Timer, 900, 0, 0, 0, timer_id, false};
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
    contract("owned_prepare_and_restore", 4, [] {
      for (const DepthStart depth : {DepthStart::Ready, DepthStart::Pending, DepthStart::Failed}) {
        AxisTargetModel model;
        model.begin(depth, start_event());
        require(model.prepare_calls == 1 && model.restore_calls == 1 && !model.overlay_hidden,
                "render override was not restored exactly once");
      }
      AxisTargetModel incompatible;
      require(incompatible.begin(DepthStart::Ready, start_event(), true, false) ==
                  Status::PassedThrough,
              "incompatible target did not pass through");
      require(incompatible.prepare_calls == 0, "pass-through target started a depth pass");
    });

    contract("stock_no_depth_cancellation", 3, [] {
      AxisTargetModel model;
      require(model.begin(DepthStart::Failed, start_event()) == Status::Cancelled,
              "initial depth failure did not cancel");
      require(model.no_depth_warning && model.retired, "stock no-depth warning was lost");
      require(model.selected_captures == 0 && model.transform_backups == 0,
              "initial failure captured mutable object state");
    });

    contract("pre_selection_suspension", 3, [] {
      AxisTargetModel model;
      require(model.begin(DepthStart::Pending, start_event()) == Status::Running,
              "pending begin failed");
      require(model.pending && model.request_owned && model.timer_owned,
              "pending request is not operation-owned");
      require(model.selected_captures == 0 && model.transform_backups == 0,
              "selected objects or backups were captured before settlement");
      require(model.producer_state_captures == 1 && model.producing_state.has_value(),
              "safe producer state was not retained before suspension");
    });

    contract("immediate_deferred_exact_initialization", 4, [] {
      AxisTargetModel immediate;
      immediate.begin(DepthStart::Ready, start_event(7, 33, 404, 505));
      AxisTargetModel deferred;
      deferred.begin(DepthStart::Pending, start_event(7, 33, 404, 505, true));
      require(deferred.start_event.has_value() && !deferred.start_event->custom_payload,
              "initiating event retained borrowed custom data");
      deferred.poll_result = DepthPoll::Ready;
      require(deferred.dispatch(timer_event()) == Status::Running, "ready poll failed");
      require(deferred.trace == immediate.trace, "immediate/deferred start trace differs");
      require(deferred.start_mouse_x == 404 && deferred.start_mouse_y == 505,
              "initiating pointer coordinates changed");
      require(deferred.selected_captures == immediate.selected_captures &&
                  deferred.transform_backups == immediate.transform_backups,
              "deferred stock initialization tail differs");
    });

    contract("retained_fifo_and_modal_semantics", 5, [] {
      AxisTargetModel model;
      model.begin(DepthStart::Pending, start_event(4));
      require(model.dispatch({EventType::Move, 5}) == Status::Running, "move queue failed");
      require(model.dispatch({EventType::TranslateOn, 6}) == Status::Running,
              "translate queue failed");
      require(model.dispatch({EventType::Release, 7}) == Status::Running,
              "release queue failed");
      model.poll_result = DepthPoll::Ready;
      require(model.dispatch(timer_event()) == Status::Finished,
              "queued initiating-button release did not finish");
      require(model.trace == std::vector<int>({1004, 2005, 2006, 2007}),
              "modal FIFO replay order differs");
      require(model.translate, "translate-enable modal state was lost");
    });

    contract("producing_context_guard", 6, [] {
      for (const int drift : {0, 1, 2, 3, 4, 5}) {
        AxisTargetModel model;
        model.begin(DepthStart::Pending, start_event());
        if (drift == 0) {
          ++model.current.manager;
        }
        else if (drift == 1) {
          ++model.current.screen;
        }
        else if (drift == 2) {
          ++model.current.region;
        }
        else if (drift == 3) {
          ++model.current.region_view;
        }
        else if (drift == 4) {
          ++model.current.depsgraph;
        }
        else {
          ++model.current.active_object;
        }
        require(model.dispatch({EventType::Move, 2}) == Status::Cancelled,
                "producing-context drift was accepted");
        require(model.retired && !model.initialized, "context failure captured object state");
      }
    });

    contract("same_pointer_producer_state_guard", 3, [] {
      for (const int drift : {0, 1, 2}) {
        AxisTargetModel model;
        model.begin(DepthStart::Pending, start_event());
        if (drift == 0) {
          ++model.current_state.frame;
        }
        else if (drift == 1) {
          model.current_state.selected_objects[1] = 14;
        }
        else {
          ++model.current_state.object_transforms[1];
        }
        require(model.current == model.producing,
                "producer-state case accidentally changed a context pointer");
        require(model.dispatch({EventType::Move, 2}) == Status::Cancelled,
                "same-pointer producer-state drift was accepted");
        require(model.retired && !model.initialized && model.selected_captures == 0 &&
                    model.transform_backups == 0,
                "producer-state failure entered mutable initialization");
      }
    });

    contract("bounded_identified_poll", 5, [] {
      AxisTargetModel foreign;
      foreign.begin(DepthStart::Pending, start_event());
      require(foreign.dispatch(timer_event(99)) == Status::Running && foreign.tick_count == 0,
              "foreign timer advanced the request");

      AxisTargetModel timeout;
      timeout.begin(DepthStart::Pending, start_event());
      for (int index = 0; index < AxisTargetModel::max_ticks; ++index) {
        require(timeout.dispatch(timer_event()) == Status::Running, "bounded poll ended early");
      }
      require(timeout.dispatch(timer_event()) == Status::Cancelled, "timeout bound was weakened");

      AxisTargetModel queue;
      queue.begin(DepthStart::Pending, start_event());
      for (int index = 0; index < AxisTargetModel::max_events; ++index) {
        require(queue.dispatch({EventType::Move, index + 10}) == Status::Running,
                "safe FIFO event rejected early");
      }
      require(queue.events.size() == AxisTargetModel::max_events, "FIFO bound differs");
      require(queue.dispatch({EventType::Move, 999}) == Status::Cancelled,
              "FIFO overflow was accepted");
    });

    contract("failure_and_cancellation_cleanup", 6, [] {
      AxisTargetModel no_timer;
      require(no_timer.begin(DepthStart::Pending, start_event(), false) == Status::Cancelled,
              "timer allocation failure was accepted");

      AxisTargetModel backend;
      backend.begin(DepthStart::Pending, start_event());
      backend.poll_result = DepthPoll::Failed;
      require(backend.dispatch(timer_event()) == Status::Cancelled,
              "backend failure did not cancel");

      AxisTargetModel consume;
      consume.begin(DepthStart::Pending, start_event());
      consume.poll_result = DepthPoll::Ready;
      consume.consume_succeeds = false;
      require(consume.dispatch(timer_event()) == Status::Cancelled,
              "cache-consume failure did not cancel");

      AxisTargetModel unsafe;
      unsafe.begin(DepthStart::Pending, start_event());
      require(unsafe.dispatch({EventType::Move, 3, 0, 0, 0, 0, true}) == Status::Cancelled,
              "borrowed event payload entered the FIFO");

      AxisTargetModel escape;
      escape.begin(DepthStart::Pending, start_event());
      require(escape.dispatch({EventType::Escape, 4}) == Status::Cancelled,
              "Escape did not cancel");

      AxisTargetModel external;
      external.begin(DepthStart::Pending, start_event());
      external.external_cancel();
      require(external.retired && !external.pending && !external.request_owned &&
                  !external.timer_owned && external.events.empty(),
              "external cancellation retained owned state");
    });
  }
  catch (const std::exception &error) {
    std::cerr << "M5_OBJECT_AXIS_TARGET_DEPTH_CACHE_CONTRACT_FAIL " << error.what() << '\n';
    return 1;
  }

  std::cout << "M5_OBJECT_AXIS_TARGET_DEPTH_CACHE_CONTRACT_PASS contracts=9 cases=39\n";
  return 0;
}
