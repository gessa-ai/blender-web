/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <cstdio>
#include <string>
#include <utility>
#include <vector>

namespace {

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "M5_CURVE_DEPTH_CACHE_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
}

enum class ReadbackState {
  Pending,
  Ready,
  Failed,
};

enum class EventType {
  Press,
  Motion,
  Release,
  Escape,
  Timer,
};

struct Event {
  EventType type = EventType::Motion;
  int id = 0;
  int timer_id = 0;
  int custom = 0;
  bool customdata = false;
  int x = 0;
  int y = 0;
  int pressure = 0;
};

struct ContextKey {
  int manager = 1;
  int window = 2;
  int screen = 3;
  int area = 4;
  int region = 5;
  int region_view = 6;
  int view3d = 7;
  int scene = 8;
  int edit_object = 9;
  int view_transform = 10;

  bool operator==(const ContextKey &) const = default;
};

class ControlledDepthCache {
 public:
  ReadbackState state = ReadbackState::Pending;
  ContextKey producing_context;
  int cancel_count = 0;
  int take_count = 0;

  explicit ControlledDepthCache(ContextKey context) : producing_context(context) {}

  bool take(const ContextKey &context)
  {
    if (state != ReadbackState::Ready || context != producing_context) {
      cancel();
      return false;
    }
    take_count++;
    state = ReadbackState::Failed;
    return true;
  }

  void cancel()
  {
    if (state != ReadbackState::Failed) {
      cancel_count++;
    }
    state = ReadbackState::Failed;
  }
};

enum class OperatorState {
  Running,
  Finished,
  Cancelled,
};

class CurveDepthContinuation {
 private:
  static constexpr int timer_id_ = 77;
  static constexpr int max_tick_count_ = 240;
  static constexpr int max_queued_events_ = 256;

  ControlledDepthCache *session_ = nullptr;
  ContextKey producing_context_;
  std::vector<Event> queued_events_;
  std::vector<int> replayed_ids_;
  int init_event_id_ = 0;
  int tick_count_ = 0;
  bool pending_ = false;
  bool timer_active_ = false;
  bool painting_ = false;
  bool use_depth_ = false;
  bool use_plane_ = false;
  bool projection_finalized_ = false;
  OperatorState operator_state_ = OperatorState::Running;

  void cleanup()
  {
    timer_active_ = false;
    pending_ = false;
    queued_events_.clear();
    if (session_ != nullptr) {
      session_->cancel();
      session_ = nullptr;
    }
  }

  OperatorState cancel()
  {
    cleanup();
    operator_state_ = OperatorState::Cancelled;
    return operator_state_;
  }

  void finalize_projection()
  {
    projection_finalized_ = true;
    use_plane_ = !use_depth_;
  }

  bool push(const Event &event)
  {
    if (event.type == EventType::Timer || event.custom != 0 || event.customdata ||
        int(queued_events_.size()) >= max_queued_events_)
    {
      return false;
    }
    queued_events_.push_back(event);
    return true;
  }

  OperatorState dispatch(const Event &event)
  {
    replayed_ids_.push_back(event.id);
    if (event.type == EventType::Escape) {
      return cancel();
    }
    if (event.type == EventType::Press) {
      painting_ = true;
      init_event_id_ = event.id;
    }
    else if (event.type == EventType::Release && painting_) {
      cleanup();
      operator_state_ = OperatorState::Finished;
    }
    return operator_state_;
  }

 public:
  OperatorState begin(ControlledDepthCache &session,
                      const ContextKey &context,
                      const Event &invoke_event,
                      const bool wait_for_input)
  {
    session_ = &session;
    producing_context_ = context;
    if (session.state == ReadbackState::Ready) {
      if (!session.take(context)) {
        return cancel();
      }
      session_ = nullptr;
      use_depth_ = true;
      finalize_projection();
      return wait_for_input ? operator_state_ : dispatch(invoke_event);
    }
    if (session.state == ReadbackState::Failed) {
      session_ = nullptr;
      finalize_projection();
      return wait_for_input ? operator_state_ : dispatch(invoke_event);
    }

    pending_ = true;
    timer_active_ = true;
    if (!wait_for_input && !push(invoke_event)) {
      return cancel();
    }
    return operator_state_;
  }

  OperatorState event(const ContextKey &context, const Event &event)
  {
    if (!pending_) {
      return dispatch(event);
    }
    if (context != producing_context_ || event.type == EventType::Escape) {
      return cancel();
    }
    if (event.type != EventType::Timer || event.timer_id != timer_id_) {
      if (event.type == EventType::Timer) {
        return operator_state_;
      }
      return push(event) ? operator_state_ : cancel();
    }
    if (++tick_count_ > max_tick_count_ || session_ == nullptr) {
      return cancel();
    }
    if (session_->state == ReadbackState::Pending) {
      return operator_state_;
    }
    if (session_->state == ReadbackState::Failed || !session_->take(context)) {
      return cancel();
    }

    session_ = nullptr;
    pending_ = false;
    timer_active_ = false;
    use_depth_ = true;
    finalize_projection();
    const std::vector<Event> replay = std::move(queued_events_);
    queued_events_.clear();
    for (const Event &queued : replay) {
      const OperatorState result = dispatch(queued);
      if (result != OperatorState::Running) {
        return result;
      }
    }
    return operator_state_;
  }

  void external_cancel()
  {
    cancel();
  }

  static Event timer(const int id = timer_id_)
  {
    return {EventType::Timer, 0, id};
  }

  const std::vector<int> &replayed_ids() const
  {
    return replayed_ids_;
  }
  bool pending() const
  {
    return pending_;
  }
  bool timer_active() const
  {
    return timer_active_;
  }
  bool use_depth() const
  {
    return use_depth_;
  }
  bool use_plane() const
  {
    return use_plane_;
  }
  bool projection_finalized() const
  {
    return projection_finalized_;
  }
};

Event press(const int id)
{
  return {EventType::Press, id, 0, 0, false, 100 + id, 200 + id, 300 + id};
}

Event motion(const int id)
{
  return {EventType::Motion, id, 0, 0, false, 100 + id, 200 + id, 300 + id};
}

Event release(const int id)
{
  return {EventType::Release, id, 0, 0, false, 100 + id, 200 + id, 300 + id};
}

bool test_native_immediate_two_lanes()
{
  for (const char *lane : {"curve", "curves"}) {
    (void)lane;
    ContextKey context;
    ControlledDepthCache session(context);
    session.state = ReadbackState::Ready;
    CurveDepthContinuation continuation;
    if (!require(continuation.begin(session, context, press(10), false) == OperatorState::Running,
                 "immediate begin") ||
        !require(continuation.use_depth() && continuation.projection_finalized(),
                 "immediate depth projection") ||
        !require(!continuation.timer_active() && session.take_count == 1,
                 "immediate no timer") ||
        !require(continuation.replayed_ids() == std::vector<int>{10},
                 "immediate exact invoke"))
    {
      return false;
    }
  }
  std::printf("CONTRACT native_immediate_two_lanes PASS cases=2 replay=10\n");
  return true;
}

bool test_pending_nonwait_fifo_two_lanes()
{
  for (const char *lane : {"curve", "curves"}) {
    (void)lane;
    ContextKey context;
    ControlledDepthCache session(context);
    CurveDepthContinuation continuation;
    if (!require(continuation.begin(session, context, press(20), false) == OperatorState::Running,
                 "pending begin") ||
        !require(continuation.event(context, motion(21)) == OperatorState::Running,
                 "pending motion") ||
        !require(continuation.event(context, release(22)) == OperatorState::Running,
                 "pending release queued"))
    {
      return false;
    }
    session.state = ReadbackState::Ready;
    if (!require(continuation.event(context, CurveDepthContinuation::timer()) ==
                     OperatorState::Finished,
                 "pending replay finishes") ||
        !require(continuation.replayed_ids() == std::vector<int>({20, 21, 22}),
                 "pending exact FIFO") ||
        !require(!continuation.timer_active() && session.take_count == 1,
                 "pending ownership released"))
    {
      return false;
    }
  }
  std::printf("CONTRACT pending_nonwait_fifo_two_lanes PASS cases=2 replay=20,21,22\n");
  return true;
}

bool test_pending_wait_for_input_two_lanes()
{
  for (const char *lane : {"curve", "curves"}) {
    (void)lane;
    ContextKey context;
    ControlledDepthCache session(context);
    CurveDepthContinuation continuation;
    if (!require(continuation.begin(session, context, motion(30), true) == OperatorState::Running,
                 "wait begin") ||
        !require(continuation.event(context, press(31)) == OperatorState::Running,
                 "wait press") ||
        !require(continuation.event(context, motion(32)) == OperatorState::Running,
                 "wait motion"))
    {
      return false;
    }
    session.state = ReadbackState::Ready;
    if (!require(continuation.event(context, CurveDepthContinuation::timer()) ==
                     OperatorState::Running,
                 "wait replay stays modal") ||
        !require(continuation.replayed_ids() == std::vector<int>({31, 32}),
                 "wait invoke excluded") ||
        !require(continuation.event(context, release(33)) == OperatorState::Finished,
                 "wait later release finishes"))
    {
      return false;
    }
  }
  std::printf("CONTRACT pending_wait_for_input_two_lanes PASS cases=2 replay=31,32,33\n");
  return true;
}

bool test_producing_context_guards()
{
  ContextKey context;
  ControlledDepthCache pointer_session(context);
  CurveDepthContinuation pointer_continuation;
  if (!require(pointer_continuation.begin(pointer_session, context, press(40), false) ==
                   OperatorState::Running,
               "context begin"))
  {
    return false;
  }
  ContextKey changed_pointer = context;
  changed_pointer.area++;
  if (!require(pointer_continuation.event(changed_pointer, motion(41)) ==
                   OperatorState::Cancelled,
               "pointer drift cancels") ||
      !require(pointer_session.cancel_count == 1, "pointer drift cancels ticket"))
  {
    return false;
  }

  ControlledDepthCache matrix_session(context);
  CurveDepthContinuation matrix_continuation;
  if (!require(matrix_continuation.begin(matrix_session, context, press(42), false) ==
                   OperatorState::Running,
               "matrix begin"))
  {
    return false;
  }
  matrix_session.state = ReadbackState::Ready;
  ContextKey changed_matrix = context;
  changed_matrix.view_transform++;
  const bool ok = require(matrix_continuation.event(changed_matrix,
                                                     CurveDepthContinuation::timer()) ==
                              OperatorState::Cancelled,
                          "matrix drift cancels") &&
                  require(matrix_session.cancel_count == 1, "matrix drift releases ticket");
  if (ok) {
    std::printf("CONTRACT producing_context_guards PASS cases=2 cancelled=2\n");
  }
  return ok;
}

bool test_failure_and_timeout()
{
  ContextKey context;
  ControlledDepthCache failed_session(context);
  CurveDepthContinuation failed;
  if (!require(failed.begin(failed_session, context, press(50), false) == OperatorState::Running,
               "failure begin"))
  {
    return false;
  }
  failed_session.state = ReadbackState::Failed;
  if (!require(failed.event(context, CurveDepthContinuation::timer()) ==
                   OperatorState::Cancelled,
               "backend failure cancels"))
  {
    return false;
  }

  ControlledDepthCache timeout_session(context);
  CurveDepthContinuation timeout;
  if (!require(timeout.begin(timeout_session, context, press(51), false) == OperatorState::Running,
               "timeout begin"))
  {
    return false;
  }
  for (int tick = 0; tick < 240; tick++) {
    if (!require(timeout.event(context, CurveDepthContinuation::timer()) ==
                     OperatorState::Running,
                 "bounded pending tick"))
    {
      return false;
    }
  }
  const bool ok = require(timeout.event(context, CurveDepthContinuation::timer()) ==
                              OperatorState::Cancelled,
                          "timeout cancels") &&
                  require(timeout_session.cancel_count == 1, "timeout releases ticket");
  if (ok) {
    std::printf("CONTRACT failure_timeout PASS cases=2 max_ticks=240\n");
  }
  return ok;
}

bool test_escape_and_external_cancel()
{
  ContextKey context;
  ControlledDepthCache escape_session(context);
  CurveDepthContinuation escape;
  if (!require(escape.begin(escape_session, context, press(60), false) == OperatorState::Running,
               "escape begin") ||
      !require(escape.event(context, {EventType::Escape, 61}) == OperatorState::Cancelled,
               "escape cancels") ||
      !require(!escape.timer_active() && escape_session.cancel_count == 1,
               "escape cleanup"))
  {
    return false;
  }

  ControlledDepthCache external_session(context);
  CurveDepthContinuation external;
  external.begin(external_session, context, press(62), false);
  external.external_cancel();
  const bool ok = require(!external.pending() && !external.timer_active(),
                          "external cancel retires continuation") &&
                  require(external_session.cancel_count == 1, "external cancel releases ticket");
  if (ok) {
    std::printf("CONTRACT escape_external_cancel PASS cases=2 cleanup=2\n");
  }
  return ok;
}

bool test_queue_guards()
{
  ContextKey context;
  ControlledDepthCache unsafe_session(context);
  CurveDepthContinuation unsafe;
  if (!require(unsafe.begin(unsafe_session, context, press(70), true) == OperatorState::Running,
               "unsafe begin"))
  {
    return false;
  }
  Event custom = motion(71);
  custom.customdata = true;
  if (!require(unsafe.event(context, custom) == OperatorState::Cancelled,
               "custom payload rejected"))
  {
    return false;
  }

  ControlledDepthCache bound_session(context);
  CurveDepthContinuation bound;
  if (!require(bound.begin(bound_session, context, press(72), true) == OperatorState::Running,
               "bound begin"))
  {
    return false;
  }
  for (int index = 0; index < 256; index++) {
    if (!require(bound.event(context, motion(1000 + index)) == OperatorState::Running,
                 "bounded event accepted"))
    {
      return false;
    }
  }
  const bool ok = require(bound.event(context, motion(2000)) == OperatorState::Cancelled,
                          "queue overflow cancels") &&
                  require(bound_session.cancel_count == 1, "queue overflow releases ticket");
  if (ok) {
    std::printf("CONTRACT queue_guards PASS cases=2 max_events=256\n");
  }
  return ok;
}

bool test_initial_failure_fallback_two_lanes()
{
  for (const char *lane : {"curve", "curves"}) {
    (void)lane;
    ContextKey context;
    ControlledDepthCache session(context);
    session.state = ReadbackState::Failed;
    CurveDepthContinuation continuation;
    if (!require(continuation.begin(session, context, press(80), false) == OperatorState::Running,
                 "fallback begin") ||
        !require(continuation.use_plane() && continuation.projection_finalized(),
                 "fallback view plane") ||
        !require(continuation.replayed_ids() == std::vector<int>{80},
                 "fallback exact invoke"))
    {
      return false;
    }
  }
  std::printf("CONTRACT initial_failure_fallback_two_lanes PASS cases=2 replay=80\n");
  return true;
}

}  // namespace

int main()
{
  if (!test_native_immediate_two_lanes() || !test_pending_nonwait_fifo_two_lanes() ||
      !test_pending_wait_for_input_two_lanes() || !test_producing_context_guards() ||
      !test_failure_and_timeout() || !test_escape_and_external_cancel() ||
      !test_queue_guards() || !test_initial_failure_fallback_two_lanes())
  {
    return 1;
  }
  std::printf("M5_CURVE_DEPTH_CACHE_CONTRACT_PASS contracts=8 cases=16\n");
  return 0;
}
