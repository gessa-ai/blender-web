/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <cassert>
#include <cmath>
#include <cstdio>

enum class ReadbackState { Pending, Ready, Failed };
enum class StrokeResult { Complete, Pending, Failed };
enum class OperatorState { Running, Finished, Cancelled };

struct FinishEvent {
  int type = 0;
  int value = 0;
  int xy[2] = {0, 0};
  bool has_customdata = false;
};

struct PaintingDepthModel {
  float cursor[3] = {1.0f, 2.0f, 3.0f};
  float cursor_before[3] = {};
  float pending_location[3] = {};
  int pending_mval[2] = {};
  int request_context = 0;
  int context = 11;
  int generation = 0;
  int active_generation = 0;
  int tick_count = 0;
  int cursor_updates = 0;
  int depsgraph_tags = 0;
  int redraw_tags = 0;
  int replayed_finish_events = 0;
  StrokeResult result = StrokeResult::Complete;
  OperatorState operator_state = OperatorState::Running;
  ReadbackState readback_state = ReadbackState::Ready;
  FinishEvent deferred_finish;
  bool has_depth = false;
  bool timer = false;
  bool finish_deferred = false;
  bool clone_cursor_pick = true;

  static bool close(const float a, const float b)
  {
    return std::fabs(a - b) < 1.0e-6f;
  }

  bool cursor_unchanged() const
  {
    return close(cursor[0], cursor_before[0]) && close(cursor[1], cursor_before[1]) &&
           close(cursor[2], cursor_before[2]);
  }

  StrokeResult fail()
  {
    result = StrokeResult::Failed;
    timer = false;
    finish_deferred = false;
    operator_state = OperatorState::Cancelled;
    return result;
  }

  StrokeResult apply()
  {
    if (readback_state == ReadbackState::Failed || request_context != context ||
        !cursor_unchanged())
    {
      return fail();
    }
    if (readback_state == ReadbackState::Pending) {
      return StrokeResult::Pending;
    }

    result = StrokeResult::Complete;
    timer = false;
    if (has_depth) {
      for (int i = 0; i < 3; i++) {
        cursor[i] = pending_location[i];
      }
      cursor_updates++;
      depsgraph_tags++;
      redraw_tags++;
    }
    if (finish_deferred) {
      finish_deferred = false;
      replayed_finish_events++;
      operator_state = OperatorState::Finished;
    }
    return result;
  }

  StrokeResult request(const int mval[2],
                       const ReadbackState state,
                       const bool depth_hit,
                       const float location[3])
  {
    if (!clone_cursor_pick) {
      return StrokeResult::Complete;
    }
    generation++;
    active_generation = generation;
    request_context = context;
    for (int i = 0; i < 3; i++) {
      cursor_before[i] = cursor[i];
      pending_location[i] = location[i];
    }
    pending_mval[0] = mval[0];
    pending_mval[1] = mval[1];
    readback_state = state;
    has_depth = depth_hit;
    tick_count = 0;
    finish_deferred = false;
    result = state == ReadbackState::Failed ? StrokeResult::Failed : StrokeResult::Pending;
    timer = state == ReadbackState::Pending;
    return state == ReadbackState::Pending ? result : apply();
  }

  StrokeResult settle(const int settled_generation,
                      const ReadbackState state,
                      const bool depth_hit,
                      const float location[3])
  {
    if (settled_generation != active_generation) {
      return result;
    }
    readback_state = state;
    has_depth = depth_hit;
    for (int i = 0; i < 3; i++) {
      pending_location[i] = location[i];
    }
    return apply();
  }

  OperatorState finish(const FinishEvent &event)
  {
    if (result == StrokeResult::Pending) {
      if (event.has_customdata) {
        fail();
        return operator_state;
      }
      deferred_finish = event;
      finish_deferred = true;
      timer = true;
      return operator_state;
    }
    operator_state = result == StrokeResult::Failed ? OperatorState::Cancelled :
                                                      OperatorState::Finished;
    return operator_state;
  }

  OperatorState tick()
  {
    if (++tick_count > 240) {
      fail();
    }
    return operator_state;
  }

  OperatorState cancel()
  {
    fail();
    return operator_state;
  }
};

static void contract_native_immediate()
{
  PaintingDepthModel model;
  const int mval[2] = {41, 73};
  const float location[3] = {4.0f, 5.0f, 6.0f};
  assert(model.request(mval, ReadbackState::Ready, true, location) == StrokeResult::Complete);
  assert(model.cursor[0] == 4.0f && model.cursor[1] == 5.0f && model.cursor[2] == 6.0f);
  assert(model.cursor_updates == 1 && model.depsgraph_tags == 1 && model.redraw_tags == 1);
  assert(!model.timer && model.pending_mval[0] == 41 && model.pending_mval[1] == 73);
  std::puts("CONTRACT native_immediate PASS cursor=4,5,6 tags=1 redraw=1");
}

static void contract_no_hit_preserves_cursor()
{
  PaintingDepthModel model;
  const int mval[2] = {8, 9};
  const float unused[3] = {99.0f, 99.0f, 99.0f};
  assert(model.request(mval, ReadbackState::Ready, false, unused) == StrokeResult::Complete);
  assert(model.cursor[0] == 1.0f && model.cursor[1] == 2.0f && model.cursor[2] == 3.0f);
  assert(model.cursor_updates == 0 && model.operator_state == OperatorState::Running);
  std::puts("CONTRACT no_hit PASS cursor=1,2,3 updates=0");
}

static void contract_pending_release_replay()
{
  PaintingDepthModel model;
  const int mval[2] = {17, 29};
  const float requested[3] = {};
  const float settled[3] = {7.0f, 8.0f, 9.0f};
  assert(model.request(mval, ReadbackState::Pending, false, requested) == StrokeResult::Pending);
  const int generation = model.generation;
  const FinishEvent release = {1, 2, {117, 229}, false};
  assert(model.finish(release) == OperatorState::Running && model.finish_deferred);
  assert(model.settle(generation, ReadbackState::Ready, true, settled) == StrokeResult::Complete);
  assert(model.operator_state == OperatorState::Finished && model.replayed_finish_events == 1);
  assert(model.deferred_finish.type == 1 && model.deferred_finish.value == 2 &&
         model.deferred_finish.xy[0] == 117 && model.deferred_finish.xy[1] == 229);
  std::puts("CONTRACT pending_release PASS event=1/2 xy=117,229 replay=1");
}

static void contract_completion_before_release()
{
  PaintingDepthModel model;
  const int mval[2] = {5, 6};
  const float requested[3] = {};
  const float settled[3] = {2.0f, 4.0f, 8.0f};
  model.request(mval, ReadbackState::Pending, false, requested);
  assert(model.settle(model.generation, ReadbackState::Ready, true, settled) ==
         StrokeResult::Complete);
  assert(model.operator_state == OperatorState::Running && model.cursor_updates == 1);
  assert(model.finish(FinishEvent{3, 4, {5, 6}, false}) == OperatorState::Finished);
  assert(model.replayed_finish_events == 0);
  std::puts("CONTRACT completion_before_release PASS updates=1 replay=0");
}

static void contract_latest_motion_supersedes()
{
  PaintingDepthModel model;
  const int first_mval[2] = {10, 20};
  const int latest_mval[2] = {30, 40};
  const float empty[3] = {};
  const float stale[3] = {50.0f, 50.0f, 50.0f};
  const float latest[3] = {3.0f, 6.0f, 12.0f};
  model.request(first_mval, ReadbackState::Pending, false, empty);
  const int old_generation = model.generation;
  model.request(latest_mval, ReadbackState::Pending, false, empty);
  const int latest_generation = model.generation;
  assert(model.settle(old_generation, ReadbackState::Ready, true, stale) == StrokeResult::Pending);
  assert(model.cursor_updates == 0);
  assert(model.settle(latest_generation, ReadbackState::Ready, true, latest) ==
         StrokeResult::Complete);
  assert(model.cursor[0] == 3.0f && model.cursor[1] == 6.0f && model.cursor[2] == 12.0f);
  std::puts("CONTRACT latest_motion PASS generations=2 cursor=3,6,12");
}

static void contract_drift_guards()
{
  const int mval[2] = {1, 2};
  const float empty[3] = {};
  const float settled[3] = {9.0f, 9.0f, 9.0f};

  PaintingDepthModel context_drift;
  context_drift.request(mval, ReadbackState::Pending, false, empty);
  context_drift.context++;
  assert(context_drift.settle(context_drift.generation, ReadbackState::Ready, true, settled) ==
         StrokeResult::Failed);
  assert(context_drift.cursor_updates == 0 &&
         context_drift.operator_state == OperatorState::Cancelled);

  PaintingDepthModel cursor_drift;
  cursor_drift.request(mval, ReadbackState::Pending, false, empty);
  cursor_drift.cursor[1] = 77.0f;
  assert(cursor_drift.settle(cursor_drift.generation, ReadbackState::Ready, true, settled) ==
         StrokeResult::Failed);
  assert(cursor_drift.cursor[1] == 77.0f && cursor_drift.cursor_updates == 0);
  std::puts("CONTRACT drift_guards PASS context=1 cursor=1 stale_updates=0");
}

static void contract_terminal_guards()
{
  const int mval[2] = {12, 13};
  const float empty[3] = {};

  PaintingDepthModel failed;
  failed.request(mval, ReadbackState::Pending, false, empty);
  assert(failed.settle(failed.generation, ReadbackState::Failed, false, empty) ==
         StrokeResult::Failed);

  PaintingDepthModel timed_out;
  timed_out.request(mval, ReadbackState::Pending, false, empty);
  for (int i = 0; i < 241; i++) {
    timed_out.tick();
  }
  assert(timed_out.operator_state == OperatorState::Cancelled && !timed_out.timer);

  PaintingDepthModel cancelled;
  cancelled.request(mval, ReadbackState::Pending, false, empty);
  assert(cancelled.cancel() == OperatorState::Cancelled && !cancelled.timer);

  PaintingDepthModel customdata;
  customdata.request(mval, ReadbackState::Pending, false, empty);
  assert(customdata.finish(FinishEvent{1, 2, {12, 13}, true}) ==
         OperatorState::Cancelled);
  assert(!customdata.finish_deferred && customdata.cursor_updates == 0);
  std::puts("CONTRACT terminal_guards PASS failed=1 timeout=241 cancel=1 customdata=1");
}

static void contract_non_clone_passthrough()
{
  PaintingDepthModel model;
  model.clone_cursor_pick = false;
  const int mval[2] = {33, 44};
  const float location[3] = {100.0f, 100.0f, 100.0f};
  assert(model.request(mval, ReadbackState::Pending, true, location) == StrokeResult::Complete);
  assert(model.generation == 0 && model.cursor_updates == 0 && !model.timer);
  assert(model.finish(FinishEvent{1, 2, {33, 44}, false}) == OperatorState::Finished);
  std::puts("CONTRACT non_clone PASS requests=0 updates=0 finish=1");
}

int main()
{
  contract_native_immediate();
  contract_no_hit_preserves_cursor();
  contract_pending_release_replay();
  contract_completion_before_release();
  contract_latest_motion_supersedes();
  contract_drift_guards();
  contract_terminal_guards();
  contract_non_clone_passthrough();
  std::puts("M5_PAINTING_DEPTH_CONTRACT_PASS contracts=8 cases=13");
  return 0;
}
