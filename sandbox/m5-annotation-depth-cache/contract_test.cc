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
    std::fprintf(stderr, "M5_ANNOTATION_DEPTH_CACHE_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
}

enum class ReadbackState {
  Pending,
  Ready,
  Failed,
};

enum class DepthMode {
  Projection,
  Eraser,
};

enum class ResumeKind {
  ModalDispatch,
  ApplyEvent,
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
  int view_transform = 9;

  bool operator==(const ContextKey &) const = default;
};

struct Event {
  int id = 0;
  bool safe = true;
  bool needs_cache = true;
  bool invalidates_cache = false;
  bool terminal = false;
};

struct QueuedEvent {
  Event event;
  ResumeKind resume = ResumeKind::ModalDispatch;
  DepthMode mode = DepthMode::Projection;
};

class AnnotationDepthContinuation {
 private:
  static constexpr int timer_id_ = 73;
  static constexpr int max_tick_count_ = 4;
  static constexpr int max_queued_events_ = 4;

  ContextKey producing_context_;
  ReadbackState readback_state_ = ReadbackState::Failed;
  ReadbackState next_begin_state_ = ReadbackState::Pending;
  DepthMode pending_mode_ = DepthMode::Projection;
  DepthMode cache_mode_ = DepthMode::Projection;
  int cache_view_transform_ = 0;
  int tick_count_ = 0;
  int cancel_count_ = 0;
  int take_count_ = 0;
  bool pending_ = false;
  bool timer_active_ = false;
  bool cache_valid_ = false;
  bool aborted_ = false;
  bool finished_ = false;
  std::vector<QueuedEvent> queue_;
  std::vector<std::string> effects_;

  bool cache_matches(const ContextKey &context, const DepthMode mode) const
  {
    return cache_valid_ && cache_mode_ == mode &&
           cache_view_transform_ == context.view_transform;
  }

  void abort()
  {
    if (pending_) {
      cancel_count_++;
    }
    pending_ = false;
    timer_active_ = false;
    queue_.clear();
    readback_state_ = ReadbackState::Failed;
    aborted_ = true;
  }

  bool push(const QueuedEvent &queued)
  {
    if (!queued.event.safe || queue_.size() >= max_queued_events_) {
      abort();
      return false;
    }
    queue_.push_back(queued);
    return true;
  }

  bool dispatch(const QueuedEvent &queued)
  {
    effects_.push_back(std::string(queued.resume == ResumeKind::ApplyEvent ? "apply:" :
                                                                              "dispatch:") +
                       std::to_string(queued.event.id));
    if (queued.event.invalidates_cache) {
      cache_valid_ = false;
    }
    if (queued.event.terminal) {
      finished_ = true;
    }
    return true;
  }

 public:
  void set_next_begin_state(const ReadbackState state)
  {
    next_begin_state_ = state;
  }

  void resolve(const ReadbackState state)
  {
    readback_state_ = state;
  }

  bool submit(const ContextKey &context,
              const Event &event,
              const DepthMode mode,
              const ResumeKind resume = ResumeKind::ModalDispatch)
  {
    if (aborted_ || finished_) {
      return false;
    }
    const QueuedEvent queued{event, resume, mode};
    if (pending_) {
      if (pending_mode_ != mode) {
        abort();
        return false;
      }
      return push(queued);
    }
    if (!event.safe) {
      abort();
      return false;
    }
    if (!event.needs_cache || cache_matches(context, mode)) {
      return dispatch(queued);
    }

    producing_context_ = context;
    pending_mode_ = mode;
    readback_state_ = next_begin_state_;
    next_begin_state_ = ReadbackState::Pending;
    if (readback_state_ == ReadbackState::Failed) {
      abort();
      return false;
    }
    if (readback_state_ == ReadbackState::Ready) {
      take_count_++;
      cache_valid_ = true;
      cache_mode_ = mode;
      cache_view_transform_ = context.view_transform;
      return dispatch(queued);
    }

    pending_ = true;
    timer_active_ = true;
    tick_count_ = 0;
    return push(queued);
  }

  bool poll(const ContextKey &context, const int timer_id)
  {
    if (!pending_ || aborted_ || finished_) {
      return false;
    }
    if (timer_id != timer_id_) {
      return true;
    }
    if (!(context == producing_context_) || ++tick_count_ > max_tick_count_ ||
        readback_state_ == ReadbackState::Failed)
    {
      abort();
      return false;
    }
    if (readback_state_ == ReadbackState::Pending) {
      return true;
    }

    take_count_++;
    cache_valid_ = true;
    cache_mode_ = pending_mode_;
    cache_view_transform_ = context.view_transform;
    pending_ = false;
    timer_active_ = false;
    tick_count_ = 0;
    readback_state_ = ReadbackState::Failed;
    std::vector<QueuedEvent> local = std::move(queue_);
    queue_.clear();

    for (size_t index = 0; index < local.size(); index++) {
      const QueuedEvent &queued = local[index];
      if (queued.event.needs_cache && !cache_matches(context, queued.mode)) {
        if (!submit(context, queued.event, queued.mode, queued.resume)) {
          return false;
        }
      }
      else if (!dispatch(queued)) {
        return false;
      }
      if (finished_) {
        return true;
      }
      if (pending_) {
        for (size_t remaining = index + 1; remaining < local.size(); remaining++) {
          if (!push(local[remaining])) {
            return false;
          }
        }
        return true;
      }
    }
    return true;
  }

  void external_cancel()
  {
    abort();
  }

  const std::vector<std::string> &effects() const
  {
    return effects_;
  }
  bool pending() const
  {
    return pending_;
  }
  bool timer_active() const
  {
    return timer_active_;
  }
  bool aborted() const
  {
    return aborted_;
  }
  bool finished() const
  {
    return finished_;
  }
  bool cache_valid() const
  {
    return cache_valid_;
  }
  int cancel_count() const
  {
    return cancel_count_;
  }
  int take_count() const
  {
    return take_count_;
  }
  static constexpr int timer_id()
  {
    return timer_id_;
  }
};

struct RecordedPoint {
  int id = 0;
  bool is_start = false;
};

class RecordedStrokeContinuation {
 private:
  static constexpr int timer_id_ = 91;
  static constexpr int max_tick_count_ = 4;

  std::vector<RecordedPoint> points_;
  std::vector<ReadbackState> begin_states_;
  std::vector<std::string> effects_;
  ContextKey producing_context_;
  size_t point_index_ = 0;
  size_t begin_index_ = 0;
  int tick_count_ = 0;
  int take_count_ = 0;
  bool first_run_ = true;
  bool needs_depth_ = true;
  bool eraser_ = false;
  bool cache_valid_ = false;
  bool pending_ = false;
  bool finished_ = false;
  bool aborted_ = false;
  ReadbackState readback_state_ = ReadbackState::Failed;

  void abort()
  {
    pending_ = false;
    cache_valid_ = false;
    aborted_ = true;
  }

  bool ensure_cache(const ContextKey &context, const bool applying_point)
  {
    if (!needs_depth_ || (eraser_ && !applying_point) || cache_valid_) {
      return true;
    }
    const ReadbackState state = begin_index_ < begin_states_.size() ?
                                    begin_states_[begin_index_++] :
                                    ReadbackState::Pending;
    if (state == ReadbackState::Failed) {
      abort();
      return false;
    }
    if (state == ReadbackState::Ready) {
      cache_valid_ = true;
      take_count_++;
      return true;
    }
    producing_context_ = context;
    readback_state_ = ReadbackState::Pending;
    pending_ = true;
    tick_count_ = 0;
    return false;
  }

  bool resume(const ContextKey &context)
  {
    while (point_index_ < points_.size()) {
      const RecordedPoint &point = points_[point_index_];
      if (point.is_start && !first_run_) {
        if (!ensure_cache(context, false)) {
          return pending_;
        }
        effects_.push_back("end");
        cache_valid_ = eraser_;
        first_run_ = true;
      }
      if (!ensure_cache(context, true)) {
        return pending_;
      }
      if (first_run_) {
        first_run_ = false;
      }
      effects_.push_back("apply:" + std::to_string(point.id));
      point_index_++;
    }

    if (!ensure_cache(context, false)) {
      return pending_;
    }
    effects_.push_back("end");
    finished_ = true;
    return true;
  }

 public:
  explicit RecordedStrokeContinuation(std::vector<ReadbackState> begin_states,
                                      const bool needs_depth = true,
                                      const bool eraser = false)
      : begin_states_(std::move(begin_states)), needs_depth_(needs_depth), eraser_(eraser)
  {
  }

  bool start(const ContextKey &context, const std::vector<RecordedPoint> &points)
  {
    points_ = points;
    return resume(context);
  }

  void resolve(const ReadbackState state)
  {
    readback_state_ = state;
  }

  bool poll(const ContextKey &context, const int timer_id)
  {
    if (!pending_ || aborted_ || finished_) {
      return false;
    }
    if (timer_id != timer_id_) {
      return true;
    }
    if (!(context == producing_context_) || ++tick_count_ > max_tick_count_ ||
        readback_state_ == ReadbackState::Failed)
    {
      abort();
      return false;
    }
    if (readback_state_ == ReadbackState::Pending) {
      return true;
    }

    pending_ = false;
    cache_valid_ = true;
    take_count_++;
    readback_state_ = ReadbackState::Failed;
    return resume(context);
  }

  bool external_event(const bool escape)
  {
    if (!pending_) {
      return false;
    }
    if (escape) {
      abort();
      return false;
    }
    return true;
  }

  const std::vector<std::string> &effects() const
  {
    return effects_;
  }
  bool pending() const
  {
    return pending_;
  }
  bool finished() const
  {
    return finished_;
  }
  bool aborted() const
  {
    return aborted_;
  }
  int take_count() const
  {
    return take_count_;
  }
  static constexpr int timer_id()
  {
    return timer_id_;
  }
};

bool same(const std::vector<std::string> &actual,
          const std::initializer_list<const char *> expected)
{
  if (actual.size() != expected.size()) {
    return false;
  }
  size_t index = 0;
  for (const char *value : expected) {
    if (actual[index++] != value) {
      return false;
    }
  }
  return true;
}

bool contract_native_immediate()
{
  ContextKey context;
  AnnotationDepthContinuation continuation;
  continuation.set_next_begin_state(ReadbackState::Ready);
  const bool ok = continuation.submit(
      context, Event{10, true, true, false, true}, DepthMode::Projection);
  return require(ok, "native immediate submit") &&
         require(same(continuation.effects(), {"dispatch:10"}), "native immediate effect") &&
         require(continuation.finished(), "native immediate terminal") &&
         require(!continuation.timer_active(), "native immediate timer") &&
         require(continuation.take_count() == 1, "native immediate take");
}

bool contract_pending_terminal()
{
  ContextKey context;
  AnnotationDepthContinuation continuation;
  if (!require(continuation.submit(
                   context, Event{20, true, true, false, true}, DepthMode::Projection),
               "pending terminal submit") ||
      !require(continuation.effects().empty(), "pending terminal early effect") ||
      !require(continuation.timer_active(), "pending terminal timer") ||
      !require(continuation.poll(context, 999), "pending terminal wrong timer") ||
      !require(continuation.effects().empty(), "wrong timer effect"))
  {
    return false;
  }
  continuation.resolve(ReadbackState::Ready);
  return require(continuation.poll(context, AnnotationDepthContinuation::timer_id()),
                 "pending terminal settle") &&
         require(same(continuation.effects(), {"dispatch:20"}), "pending terminal replay") &&
         require(continuation.finished(), "pending terminal finish");
}

bool contract_initial_apply_resume()
{
  ContextKey context;
  AnnotationDepthContinuation continuation;
  if (!require(continuation.submit(context,
                                   Event{30, true, true, false, false},
                                   DepthMode::Eraser,
                                   ResumeKind::ApplyEvent),
               "initial apply submit"))
  {
    return false;
  }
  continuation.resolve(ReadbackState::Ready);
  return require(continuation.poll(context, AnnotationDepthContinuation::timer_id()),
                 "initial apply settle") &&
         require(same(continuation.effects(), {"apply:30"}), "initial apply exact resume") &&
         require(!continuation.finished(), "initial apply remains modal");
}

bool contract_eraser_fifo()
{
  ContextKey context;
  AnnotationDepthContinuation continuation;
  if (!continuation.submit(context, Event{40}, DepthMode::Eraser) ||
      !continuation.submit(context, Event{41}, DepthMode::Eraser) ||
      !continuation.submit(context, Event{42}, DepthMode::Eraser))
  {
    return require(false, "eraser fifo queue");
  }
  continuation.resolve(ReadbackState::Ready);
  return require(continuation.poll(context, AnnotationDepthContinuation::timer_id()),
                 "eraser fifo settle") &&
         require(same(continuation.effects(), {"dispatch:40", "dispatch:41", "dispatch:42"}),
                 "eraser fifo order") &&
         require(continuation.cache_valid(), "eraser cache retained") &&
         require(continuation.take_count() == 1, "eraser one take");
}

bool contract_polyline_refresh()
{
  ContextKey context;
  AnnotationDepthContinuation continuation;
  if (!continuation.submit(
          context, Event{50, true, true, true, false}, DepthMode::Projection) ||
      !continuation.submit(context, Event{51}, DepthMode::Projection))
  {
    return require(false, "polyline queue");
  }
  continuation.resolve(ReadbackState::Ready);
  if (!require(continuation.poll(context, AnnotationDepthContinuation::timer_id()),
               "polyline first settle") ||
      !require(continuation.pending(), "polyline second request") ||
      !require(same(continuation.effects(), {"dispatch:50"}), "polyline first dispatch"))
  {
    return false;
  }
  continuation.resolve(ReadbackState::Ready);
  return require(continuation.poll(context, AnnotationDepthContinuation::timer_id()),
                 "polyline second settle") &&
         require(same(continuation.effects(), {"dispatch:50", "dispatch:51"}),
                 "polyline exact chained order") &&
         require(continuation.take_count() == 2, "polyline two generations");
}

bool contract_failure_guards()
{
  ContextKey context;
  ContextKey drift = context;
  drift.view_transform++;

  AnnotationDepthContinuation drifted;
  drifted.submit(context, Event{60}, DepthMode::Projection);
  drifted.resolve(ReadbackState::Ready);
  const bool drift_ok = !drifted.poll(drift, AnnotationDepthContinuation::timer_id()) &&
                        drifted.aborted() && drifted.effects().empty();

  AnnotationDepthContinuation failed;
  failed.submit(context, Event{61}, DepthMode::Projection);
  failed.resolve(ReadbackState::Failed);
  const bool failure_ok = !failed.poll(context, AnnotationDepthContinuation::timer_id()) &&
                          failed.aborted() && failed.effects().empty();

  AnnotationDepthContinuation timed_out;
  timed_out.submit(context, Event{62}, DepthMode::Projection);
  bool timeout_ok = true;
  for (int i = 0; i < 5; i++) {
    timeout_ok = timed_out.poll(context, AnnotationDepthContinuation::timer_id());
  }
  timeout_ok = !timeout_ok && timed_out.aborted() && timed_out.effects().empty();
  return require(drift_ok, "context drift guard") && require(failure_ok, "failure guard") &&
         require(timeout_ok, "timeout guard");
}

bool contract_safety_bounds()
{
  ContextKey context;
  AnnotationDepthContinuation unsafe_initial;
  const bool initial_ok = !unsafe_initial.submit(
                              context, Event{70, false}, DepthMode::Projection) &&
                          unsafe_initial.aborted() && !unsafe_initial.timer_active();

  AnnotationDepthContinuation unsafe_queued;
  unsafe_queued.submit(context, Event{71}, DepthMode::Projection);
  const bool queued_ok = !unsafe_queued.submit(
                             context, Event{72, false}, DepthMode::Projection) &&
                         unsafe_queued.aborted() && unsafe_queued.effects().empty();

  AnnotationDepthContinuation bounded;
  bool bound_ok = bounded.submit(context, Event{73}, DepthMode::Projection);
  for (int id = 74; id < 78; id++) {
    bound_ok = bounded.submit(context, Event{id}, DepthMode::Projection);
  }
  bound_ok = !bound_ok && bounded.aborted() && bounded.effects().empty();
  return require(initial_ok, "unsafe initial rejection") &&
         require(queued_ok, "unsafe queued rejection") && require(bound_ok, "queue bound");
}

bool contract_external_cancel()
{
  ContextKey context;
  AnnotationDepthContinuation continuation;
  continuation.submit(context, Event{80}, DepthMode::Eraser);
  continuation.external_cancel();
  return require(continuation.aborted(), "external cancel state") &&
         require(!continuation.pending(), "external cancel pending") &&
         require(!continuation.timer_active(), "external cancel timer") &&
         require(continuation.effects().empty(), "external cancel mutation") &&
         require(continuation.cancel_count() == 1, "external cancel ticket");
}

bool contract_recorded_native_immediate()
{
  ContextKey context;
  RecordedStrokeContinuation continuation({ReadbackState::Ready, ReadbackState::Ready});
  const bool ok = continuation.start(
      context, {{100, true}, {101, false}, {102, true}, {103, false}});
  return require(ok, "recorded native resume") &&
         require(continuation.finished(), "recorded native finish") &&
         require(same(continuation.effects(),
                      {"apply:100", "apply:101", "end", "apply:102", "apply:103", "end"}),
                 "recorded native order") &&
         require(continuation.take_count() == 2, "recorded native generations");
}

bool contract_recorded_pending_chain()
{
  ContextKey context;
  RecordedStrokeContinuation continuation({ReadbackState::Pending, ReadbackState::Pending});
  if (!require(continuation.start(
                   context, {{110, true}, {111, false}, {112, true}, {113, false}}),
               "recorded pending start") ||
      !require(continuation.pending(), "recorded first pending") ||
      !require(continuation.effects().empty(), "recorded no early mutation"))
  {
    return false;
  }

  continuation.resolve(ReadbackState::Ready);
  if (!require(continuation.poll(context, RecordedStrokeContinuation::timer_id()),
               "recorded first settle") ||
      !require(continuation.pending(), "recorded successor pending") ||
      !require(same(continuation.effects(), {"apply:110", "apply:111", "end"}),
               "recorded first generation order"))
  {
    return false;
  }

  continuation.resolve(ReadbackState::Ready);
  return require(continuation.poll(context, RecordedStrokeContinuation::timer_id()),
                 "recorded second settle") &&
         require(continuation.finished(), "recorded chained finish") &&
         require(same(continuation.effects(),
                      {"apply:110", "apply:111", "end", "apply:112", "apply:113", "end"}),
                 "recorded chained order") &&
         require(continuation.take_count() == 2, "recorded chained takes");
}

bool contract_recorded_snapshot_and_events()
{
  ContextKey context;
  std::vector<RecordedPoint> input{{120, true}, {121, false}};
  RecordedStrokeContinuation continuation({ReadbackState::Pending});
  if (!continuation.start(context, input) || !continuation.pending()) {
    return require(false, "recorded snapshot start");
  }
  input[0].id = 999;
  input.clear();
  if (!require(continuation.external_event(false), "recorded ignores unrelated event") ||
      !require(continuation.poll(context, 999), "recorded ignores wrong timer"))
  {
    return false;
  }
  continuation.resolve(ReadbackState::Ready);
  return require(continuation.poll(context, RecordedStrokeContinuation::timer_id()),
                 "recorded snapshot settle") &&
         require(same(continuation.effects(), {"apply:120", "apply:121", "end"}),
                 "recorded snapshot isolation") &&
         require(continuation.finished(), "recorded snapshot finish");
}

bool contract_recorded_eraser_and_direct()
{
  ContextKey context;
  RecordedStrokeContinuation eraser({ReadbackState::Pending}, true, true);
  if (!eraser.start(context, {{130, true}, {131, false}})) {
    return require(false, "recorded eraser start");
  }
  eraser.resolve(ReadbackState::Ready);
  const bool eraser_ok = eraser.poll(context, RecordedStrokeContinuation::timer_id()) &&
                         eraser.finished() && eraser.take_count() == 1 &&
                         same(eraser.effects(), {"apply:130", "apply:131", "end"});

  RecordedStrokeContinuation direct({}, false, false);
  const bool direct_ok = direct.start(context, {{132, true}, {133, false}}) && direct.finished() &&
                         direct.take_count() == 0 &&
                         same(direct.effects(), {"apply:132", "apply:133", "end"});
  return require(eraser_ok, "recorded eraser reuse") &&
         require(direct_ok, "recorded non-depth direct path");
}

bool contract_recorded_failure_guards()
{
  ContextKey context;
  ContextKey drift = context;
  drift.view_transform++;

  RecordedStrokeContinuation failed({ReadbackState::Pending});
  failed.start(context, {{140, true}});
  failed.resolve(ReadbackState::Failed);
  const bool failure_ok = !failed.poll(context, RecordedStrokeContinuation::timer_id()) &&
                          failed.aborted() && failed.effects().empty();

  RecordedStrokeContinuation drifted({ReadbackState::Pending});
  drifted.start(context, {{141, true}});
  drifted.resolve(ReadbackState::Ready);
  const bool drift_ok = !drifted.poll(drift, RecordedStrokeContinuation::timer_id()) &&
                        drifted.aborted() && drifted.effects().empty();

  RecordedStrokeContinuation escaped({ReadbackState::Pending});
  escaped.start(context, {{142, true}});
  const bool escape_ok = !escaped.external_event(true) && escaped.aborted() &&
                         escaped.effects().empty();
  return require(failure_ok, "recorded backend failure") &&
         require(drift_ok, "recorded context drift") && require(escape_ok, "recorded escape");
}

}  // namespace

int main()
{
  struct Contract {
    const char *name;
    int cases;
    bool (*run)();
  };
  const Contract contracts[] = {
      {"native_immediate", 2, contract_native_immediate},
      {"pending_terminal", 3, contract_pending_terminal},
      {"initial_apply_resume", 2, contract_initial_apply_resume},
      {"eraser_fifo", 2, contract_eraser_fifo},
      {"polyline_refresh", 2, contract_polyline_refresh},
      {"failure_guards", 3, contract_failure_guards},
      {"safety_bounds", 3, contract_safety_bounds},
      {"external_cancel", 1, contract_external_cancel},
      {"recorded_native_immediate", 2, contract_recorded_native_immediate},
      {"recorded_pending_chain", 3, contract_recorded_pending_chain},
      {"recorded_snapshot_and_events", 3, contract_recorded_snapshot_and_events},
      {"recorded_eraser_and_direct", 2, contract_recorded_eraser_and_direct},
      {"recorded_failure_guards", 3, contract_recorded_failure_guards},
  };

  int case_count = 0;
  for (const Contract &contract : contracts) {
    if (!contract.run()) {
      return 1;
    }
    case_count += contract.cases;
    std::printf("CONTRACT %s PASS cases=%d\n", contract.name, contract.cases);
  }
  std::printf("M5_ANNOTATION_DEPTH_CACHE_CONTRACT_PASS contracts=13 cases=%d\n", case_count);
  return case_count == 31 ? 0 : 1;
}
