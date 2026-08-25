// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

#include <array>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace {

enum class State : uint8_t { Pending, Ready, Failed };
enum class Result : uint8_t { Pending, Failed, Cancelled, Finished };

struct ProducerState {
  int frame = 1;
  int object_transform = 2;
  int edit_state = 3;

  auto identity() const
  {
    return std::array<int, 3>{frame, object_transform, edit_state};
  }
};

struct Context {
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
  int edit = 12;
  bool xray = false;
  ProducerState producer_state;

  auto identity() const
  {
    return std::array<int, 12>{manager,
                               window,
                               screen,
                               area,
                               region,
                               region_view,
                               view3d,
                               depsgraph,
                               scene,
                               view_layer,
                               object,
                               edit};
  }
};

struct DepthSession {
  std::array<int, 12> producing{};
  std::array<int, 3> producing_state{};
  State backend = State::Pending;
  bool producing_xray = false;
  bool initialized = false;
  bool consumed = false;
  bool cancelled = false;

  State begin(const Context &context, const State initial)
  {
    producing = context.identity();
    producing_state = context.producer_state.identity();
    producing_xray = context.xray;
    initialized = true;
    backend = context.xray ? State::Ready : initial;
    return state(context);
  }

  State state(const Context &context) const
  {
    if (!initialized || consumed || cancelled || context.identity() != producing ||
        context.producer_state.identity() != producing_state || context.xray != producing_xray)
    {
      return State::Failed;
    }
    return backend;
  }

  bool take(const Context &context)
  {
    if (state(context) != State::Ready) {
      return false;
    }
    consumed = true;
    return true;
  }

  void cancel()
  {
    cancelled = true;
  }
};

struct Input {
  int kind = 0;
  int x = 0;
  int y = 0;
  int value = 0;
  bool flag = false;

  auto identity() const
  {
    return std::array<int, 5>{kind, x, y, value, flag ? 1 : 0};
  }
};

struct Event {
  int type = 0;
  int timer = 0;
  int payload = 0;
  bool custom = false;
  bool cancel = false;
};

struct Continuation {
  DepthSession depth;
  Context producing;
  Input input;
  std::vector<Event> events;
  int timer = 41;
  int tick_count = 0;
  int max_ticks = 240;
  size_t max_events = 256;
  bool pending = false;
  bool initialized = false;
  bool cleaned = false;

  Result start(const Context &context, const Input &exact, const State initial)
  {
    producing = context;
    input = exact;
    const State state = depth.begin(context, initial);
    if (state == State::Ready) {
      initialized = depth.take(context);
      return initialized ? Result::Finished : Result::Failed;
    }
    if (state == State::Failed) {
      cleanup();
      return Result::Failed;
    }
    pending = true;
    return Result::Pending;
  }

  Result event(const Context &context, const Event &event)
  {
    if (!pending || cleaned || event.cancel) {
      cleanup();
      return Result::Cancelled;
    }
    if (depth.state(context) == State::Failed) {
      cleanup();
      return Result::Failed;
    }
    if (event.type != 1 || event.timer != timer) {
      if (event.type == 1) {
        return Result::Pending;
      }
      if (event.custom || events.size() >= max_events) {
        cleanup();
        return Result::Failed;
      }
      events.push_back(Event{event.type, 0, event.payload, false, false});
      return Result::Pending;
    }
    if (++tick_count > max_ticks) {
      cleanup();
      return Result::Failed;
    }
    const State state = depth.state(context);
    if (state == State::Pending) {
      return Result::Pending;
    }
    if (state != State::Ready || !depth.take(context)) {
      cleanup();
      return Result::Failed;
    }
    pending = false;
    initialized = true;
    return Result::Finished;
  }

  void cleanup()
  {
    depth.cancel();
    events.clear();
    pending = false;
    cleaned = true;
  }
};

[[noreturn]] void fail(const std::string &message)
{
  std::cerr << "FAIL " << message << '\n';
  std::exit(1);
}

void require(const bool condition, const std::string &message)
{
  if (!condition) {
    fail(message);
  }
}

uint64_t hash_text(const std::string &text)
{
  uint64_t hash = UINT64_C(1469598103934665603);
  for (const unsigned char byte : text) {
    hash ^= byte;
    hash *= UINT64_C(1099511628211);
  }
  return hash;
}

void emit_contract(const char *name, const int cases, const std::string &evidence)
{
  std::ostringstream digest;
  digest << std::hex << hash_text(evidence);
  std::cout << "CONTRACT " << name << " PASS cases=" << cases << " hash=" << digest.str()
            << '\n';
}

void contract_owned_prepare_consume()
{
  Context context;
  DepthSession session;
  require(session.begin(context, State::Pending) == State::Pending, "owned begin pending");
  require(session.state(context) == State::Pending, "owned poll pending");
  session.backend = State::Ready;
  require(session.state(context) == State::Ready, "owned poll ready");
  require(session.take(context), "owned take");
  require(session.state(context) == State::Failed, "owned one-shot");
  DepthSession failed;
  require(failed.begin(context, State::Failed) == State::Failed, "owned backend failure");
  failed.cancel();
  require(failed.state(context) == State::Failed, "owned cancel");
  emit_contract("owned_prepare_consume", 7, "pending-ready-take-once-fail-cancel");
}

void contract_xray_native()
{
  Context xray;
  xray.xray = true;
  DepthSession bypass;
  require(bypass.begin(xray, State::Pending) == State::Ready, "xray immediate");
  require(bypass.take(xray), "xray consume");
  Context native;
  DepthSession ready;
  require(ready.begin(native, State::Ready) == State::Ready, "native immediate");
  require(ready.take(native), "native consume");
  emit_contract("xray_native", 4, "xray-bypass-native-ready");
}

void contract_one_shot_inputs()
{
  Context context;
  const std::array<Input, 4> inputs = {{{1, 10, 20, 3, true},
                                        {2, 30, 40, 5, false},
                                        {3, 4, 9, 7, true},
                                        {4, 8, 6, 2, false}}};
  for (const Input &input : inputs) {
    Continuation operation;
    require(operation.start(context, input, State::Pending) == Result::Pending,
            "one-shot pending");
    operation.depth.backend = State::Ready;
    require(operation.event(context, Event{1, operation.timer, 0, false, false}) ==
                Result::Finished,
            "one-shot finish");
    require(operation.input.identity() == input.identity(), "one-shot exact input");
  }
  Continuation cancel;
  require(cancel.start(context, inputs[0], State::Pending) == Result::Pending,
          "one-shot cancel start");
  require(cancel.event(context, Event{0, 0, 0, false, true}) == Result::Cancelled,
          "one-shot cancel");
  Continuation failure;
  require(failure.start(context, inputs[1], State::Failed) == Result::Failed,
          "one-shot initial failure");
  emit_contract("one_shot_inputs", 6, "click-linked-box-lasso-exact-cancel-fail");
}

void contract_gesture_owners()
{
  Context context;
  Continuation box;
  require(box.start(context, Input{3, 1, 2, 17, false}, State::Pending) == Result::Pending,
          "box handoff");
  require(box.event(context, Event{8, 0, 91, false, false}) == Result::Pending,
          "box retains owner");
  require(box.events.size() == 1 && box.events[0].payload == 91, "box sanitized queue");
  box.depth.backend = State::Ready;
  require(box.event(context, Event{1, box.timer, 0, false, false}) == Result::Finished,
          "box ready");
  Continuation lasso;
  require(lasso.start(context, Input{4, 6, 7, 23, true}, State::Ready) == Result::Finished,
          "lasso immediate");
  emit_contract("gesture_owners", 5, "box-handoff-owner-queue-ready-lasso");
}

void contract_circle_continuation()
{
  Context context;
  Continuation circle;
  circle.max_events = 512;
  const Input first{5, 110, 220, 32, true};
  require(circle.start(context, first, State::Pending) == Result::Pending, "circle pending");
  require(circle.event(context, Event{7, 0, 1, false, false}) == Result::Pending,
          "circle queue first");
  require(circle.event(context, Event{7, 0, 2, false, false}) == Result::Pending,
          "circle queue second");
  circle.depth.backend = State::Ready;
  require(circle.event(context, Event{1, circle.timer, 0, false, false}) == Result::Finished,
          "circle consume");
  require(circle.input.identity() == first.identity(), "circle exact first input");
  require(circle.events.size() == 2 && circle.events[0].payload == 1 &&
              circle.events[1].payload == 2,
          "circle fifo");
  emit_contract("circle_continuation", 6, "pending-queue-queue-consume-input-fifo");
}

void contract_brush_continuation()
{
  Context context;
  Continuation brush;
  const Input start{6, 75, 95, 1, true};
  require(brush.start(context, start, State::Pending) == Result::Pending, "brush pending");
  require(!brush.initialized, "brush pre-init suspension");
  require(brush.event(context, Event{9, 0, 11, false, false}) == Result::Pending,
          "brush queue move");
  require(brush.event(context, Event{10, 0, 12, false, false}) == Result::Pending,
          "brush queue release");
  brush.depth.backend = State::Ready;
  require(brush.event(context, Event{1, brush.timer, 0, false, false}) == Result::Finished,
          "brush settle");
  require(brush.initialized && brush.events.size() == 2 && brush.input.identity() == start.identity(),
          "brush exact replay");
  emit_contract("brush_continuation", 6, "pending-preinit-move-release-settle-replay");
}

void contract_same_pointer_producer_state()
{
  const std::array<int, 3> caller_kinds = {1, 3, 6};
  for (const int caller_kind : caller_kinds) {
    for (int drift = 0; drift < 3; drift++) {
      Context producing;
      Continuation operation;
      require(operation.start(producing, Input{caller_kind, 4, 5, 6, false}, State::Pending) ==
                  Result::Pending,
              "producer-state pending");

      Context current = producing;
      if (drift == 0) {
        current.producer_state.frame++;
      }
      else if (drift == 1) {
        current.producer_state.object_transform++;
      }
      else {
        current.producer_state.edit_state++;
      }
      operation.depth.backend = State::Ready;
      require(current.identity() == producing.identity(),
              "producer-state case changed a context pointer");
      require(operation.event(current, Event{1, operation.timer, 0, false, false}) ==
                  Result::Failed,
              "same-pointer producer-state drift was accepted");
      require(operation.cleaned && !operation.initialized && !operation.depth.consumed,
              "producer-state failure consumed old depth or initialized a caller");
    }
  }
  emit_contract("same_pointer_producer_state", 9, "click-gesture-brush-frame-transform-edit");
}

void contract_bounds_identified_timer()
{
  Context context;
  Continuation operation;
  operation.max_events = 2;
  operation.max_ticks = 2;
  require(operation.start(context, Input{1, 0, 0, 0, false}, State::Pending) == Result::Pending,
          "bound start");
  require(operation.event(context, Event{1, 999, 0, false, false}) == Result::Pending,
          "foreign timer ignored");
  require(operation.event(context, Event{2, 0, 1, false, false}) == Result::Pending,
          "bound event one");
  require(operation.event(context, Event{2, 0, 2, false, false}) == Result::Pending,
          "bound event two");
  require(operation.event(context, Event{2, 0, 3, false, false}) == Result::Failed,
          "bound overflow");
  emit_contract("bounds_identified_timer", 5, "start-foreign-two-events-overflow");
}

void contract_failure_cleanup()
{
  Context context;
  Continuation drift;
  require(drift.start(context, Input{2, 1, 1, 1, false}, State::Pending) == Result::Pending,
          "drift start");
  Context changed = context;
  changed.region_view++;
  require(drift.event(changed, Event{1, drift.timer, 0, false, false}) == Result::Failed,
          "drift failure");
  require(drift.cleaned && drift.events.empty(), "drift cleanup");
  Continuation unsafe;
  require(unsafe.start(context, Input{6, 2, 2, 2, false}, State::Pending) == Result::Pending,
          "unsafe start");
  require(unsafe.event(context, Event{8, 0, 0, true, false}) == Result::Failed,
          "unsafe cleanup");
  emit_contract("failure_cleanup", 5, "drift-start-fail-clean-unsafe-fail");
}

}  // namespace

int main()
{
  contract_owned_prepare_consume();
  contract_xray_native();
  contract_one_shot_inputs();
  contract_gesture_owners();
  contract_circle_continuation();
  contract_brush_continuation();
  contract_same_pointer_producer_state();
  contract_bounds_identified_timer();
  contract_failure_cleanup();
  std::cout << "M5_PARTICLE_EDIT_DEPTH_CACHE_CONTRACT_PASS contracts=9 cases=53\n";
  return 0;
}
