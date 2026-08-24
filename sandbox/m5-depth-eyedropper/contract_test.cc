/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <cassert>
#include <cmath>
#include <cstdio>

enum class ReadbackState {
  Pending,
  Ready,
  Failed,
};

enum class Action {
  None,
  Accumulate,
  AccumulateAndSet,
};

enum class OperatorState {
  Running,
  Finished,
  Cancelled,
};

struct DepthDropperModel {
  float accum_depth = 0.0f;
  int accum_tot = 0;
  float property = 17.0f;
  int property_sets = 0;
  int generation = 0;
  int tick_count = 0;
  int context_generation = 3;
  int request_context_generation = 0;
  float pending_depth = -1.0f;
  Action action = Action::None;
  ReadbackState readback_state = ReadbackState::Failed;
  OperatorState operator_state = OperatorState::Running;
  bool confirm_after = false;
  bool timer = false;

  void set_accum()
  {
    property = accum_tot == 0 ? 0.0f : accum_depth / float(accum_tot);
    property_sets++;
  }

  OperatorState apply()
  {
    if (request_context_generation != context_generation || readback_state == ReadbackState::Failed)
    {
      timer = false;
      action = Action::None;
      operator_state = OperatorState::Cancelled;
      return operator_state;
    }

    const Action settled_action = action;
    action = Action::None;
    if (settled_action == Action::Accumulate && pending_depth >= 0.0f) {
      accum_depth += pending_depth;
      accum_tot++;
    }
    else if (settled_action == Action::AccumulateAndSet) {
      if (pending_depth >= 0.0f) {
        accum_depth += pending_depth;
        accum_tot++;
      }
      set_accum();
    }
    timer = false;

    if (confirm_after) {
      if (accum_tot != 0) {
        set_accum();
      }
      operator_state = OperatorState::Finished;
    }
    return operator_state;
  }

  OperatorState request(const Action requested_action,
                        const ReadbackState state,
                        const float depth)
  {
    generation++;
    action = requested_action;
    readback_state = state;
    pending_depth = depth;
    request_context_generation = context_generation;
    tick_count = 0;
    confirm_after = false;
    timer = state == ReadbackState::Pending;
    if (state == ReadbackState::Ready) {
      return apply();
    }
    if (state == ReadbackState::Failed) {
      operator_state = OperatorState::Cancelled;
    }
    return operator_state;
  }

  OperatorState settle(const int settled_generation,
                       const ReadbackState state,
                       const float depth)
  {
    if (settled_generation != generation) {
      return operator_state;
    }
    readback_state = state;
    pending_depth = depth;
    return state == ReadbackState::Pending ? operator_state : apply();
  }

  OperatorState confirm()
  {
    if (action != Action::None) {
      confirm_after = true;
      return operator_state;
    }
    if (accum_tot != 0) {
      set_accum();
    }
    operator_state = OperatorState::Finished;
    return operator_state;
  }

  OperatorState timeout()
  {
    tick_count = 241;
    timer = false;
    action = Action::None;
    operator_state = OperatorState::Cancelled;
    return operator_state;
  }

  OperatorState cancel()
  {
    timer = false;
    action = Action::None;
    operator_state = OperatorState::Cancelled;
    return operator_state;
  }
};

static bool close(const float a, const float b)
{
  return std::fabs(a - b) < 1.0e-6f;
}

static void contract_native_immediate()
{
  DepthDropperModel model;
  assert(model.request(Action::Accumulate, ReadbackState::Ready, 6.0f) ==
         OperatorState::Running);
  assert(model.accum_tot == 1 && close(model.accum_depth, 6.0f));
  assert(model.property_sets == 0);
  assert(model.request(Action::AccumulateAndSet, ReadbackState::Ready, 10.0f) ==
         OperatorState::Running);
  assert(model.accum_tot == 2 && close(model.property, 8.0f));
  assert(model.confirm() == OperatorState::Finished);
  assert(close(model.property, 8.0f) && model.property_sets == 2);
  std::puts("CONTRACT native_immediate PASS total=2 average=8 sets=2");
}

static void contract_pending_confirm()
{
  DepthDropperModel model;
  assert(model.request(Action::Accumulate, ReadbackState::Pending, -1.0f) ==
         OperatorState::Running);
  const int generation = model.generation;
  assert(model.timer && model.confirm() == OperatorState::Running && model.confirm_after);
  assert(model.settle(generation, ReadbackState::Ready, 7.5f) == OperatorState::Finished);
  assert(model.accum_tot == 1 && close(model.property, 7.5f));
  assert(!model.timer && model.property_sets == 1);
  std::puts("CONTRACT pending_confirm PASS total=1 average=7.5 sets=1");
}

static void contract_latest_drag_supersedes()
{
  DepthDropperModel model;
  model.accum_depth = 4.0f;
  model.accum_tot = 1;
  model.request(Action::AccumulateAndSet, ReadbackState::Pending, -1.0f);
  const int old_generation = model.generation;
  model.request(Action::AccumulateAndSet, ReadbackState::Pending, -1.0f);
  const int latest_generation = model.generation;
  assert(model.settle(old_generation, ReadbackState::Ready, 100.0f) == OperatorState::Running);
  assert(model.accum_tot == 1 && model.property_sets == 0);
  assert(model.settle(latest_generation, ReadbackState::Ready, 8.0f) ==
         OperatorState::Running);
  assert(model.accum_tot == 2 && close(model.property, 6.0f));
  std::puts("CONTRACT latest_drag PASS generations=2 total=2 average=6");
}

static void contract_reset_and_no_hit()
{
  DepthDropperModel model;
  model.accum_depth = 12.0f;
  model.accum_tot = 2;
  model.accum_depth = 0.0f;
  model.accum_tot = 0;
  assert(model.request(Action::AccumulateAndSet, ReadbackState::Ready, -1.0f) ==
         OperatorState::Running);
  assert(model.accum_tot == 0 && close(model.property, 0.0f));
  assert(model.property_sets == 1);
  model.request(Action::AccumulateAndSet, ReadbackState::Ready, 3.0f);
  assert(model.accum_tot == 1 && close(model.property, 3.0f));
  std::puts("CONTRACT reset_no_hit PASS zero_set=1 recovered=3");
}

static void contract_terminal_guards()
{
  DepthDropperModel drift;
  drift.request(Action::Accumulate, ReadbackState::Pending, -1.0f);
  drift.context_generation++;
  assert(drift.settle(drift.generation, ReadbackState::Ready, 9.0f) ==
         OperatorState::Cancelled);
  assert(drift.accum_tot == 0 && drift.property_sets == 0);

  DepthDropperModel failed;
  failed.request(Action::AccumulateAndSet, ReadbackState::Pending, -1.0f);
  assert(failed.settle(failed.generation, ReadbackState::Failed, -1.0f) ==
         OperatorState::Cancelled);
  assert(failed.property_sets == 0);

  DepthDropperModel timed_out;
  timed_out.request(Action::Accumulate, ReadbackState::Pending, -1.0f);
  assert(timed_out.timeout() == OperatorState::Cancelled && !timed_out.timer);

  DepthDropperModel cancelled;
  cancelled.request(Action::Accumulate, ReadbackState::Pending, -1.0f);
  assert(cancelled.cancel() == OperatorState::Cancelled && !cancelled.timer);
  std::puts("CONTRACT terminal_guards PASS drift=1 failed=1 timeout=241 cancel=1");
}

static void contract_direct_confirm_and_aligned_depth()
{
  DepthDropperModel model;
  assert(model.confirm() == OperatorState::Finished);
  assert(model.accum_tot == 0 && model.property_sets == 0 && close(model.property, 17.0f));

  const float view_origin[3] = {1.0f, 2.0f, 3.0f};
  const float aligned_point[3] = {4.0f, 6.0f, 15.0f};
  const float dx = aligned_point[0] - view_origin[0];
  const float dy = aligned_point[1] - view_origin[1];
  const float dz = aligned_point[2] - view_origin[2];
  const float depth = std::sqrt(dx * dx + dy * dy + dz * dz);
  assert(close(depth, 13.0f));
  std::puts("CONTRACT direct_confirm_aligned PASS direct_sets=0 depth=13");
}

int main()
{
  contract_native_immediate();
  contract_pending_confirm();
  contract_latest_drag_supersedes();
  contract_reset_and_no_hit();
  contract_terminal_guards();
  contract_direct_confirm_and_aligned_depth();
  std::puts("M5_DEPTH_EYEDROPPER_CONTRACT_PASS contracts=6 cases=13");
  return 0;
}
