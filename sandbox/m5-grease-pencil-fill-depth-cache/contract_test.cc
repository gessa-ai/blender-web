/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>

namespace {

enum class Solver { Pixel, Delaunay };
enum class CacheState { Ready, Pending, Failed };
enum class Status { Running, Finished, Cancelled };
enum class EventKind { OwnTimer, ForeignTimer, Other, Cancel };

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
  int paint;
  int brush;
  int frame;

  bool operator==(const Context &) const = default;
};

struct FillInput {
  int window_x;
  int window_y;
  int region_x;
  int region_y;
  int fit_method;
  int boundary_mask;
  bool invert;

  bool operator==(const FillInput &) const = default;
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

class FillDepthContinuation {
 private:
  Solver solver_ = Solver::Pixel;
  Context producer_{};
  std::optional<FillInput> retained_input_;
  std::optional<FillInput> applied_input_;
  bool needs_depth_ = false;
  bool pending_ = false;
  bool request_owned_ = false;
  bool timer_owned_ = false;
  int tick_count_ = 0;
  int apply_count_ = 0;
  int pixel_count_ = 0;
  int delaunay_count_ = 0;
  bool used_depth_ = false;
  bool used_stock_fallback_ = false;
  Status status_ = Status::Cancelled;

  void clear()
  {
    pending_ = false;
    request_owned_ = false;
    timer_owned_ = false;
    retained_input_.reset();
  }

  Status apply(const bool depth_ready)
  {
    expect(retained_input_.has_value(), "apply lost retained fill input");
    expect(apply_count_ == 0, "fill applied more than once");
    applied_input_ = retained_input_;
    apply_count_++;
    if (solver_ == Solver::Pixel) {
      pixel_count_++;
    }
    else {
      delaunay_count_++;
    }
    used_depth_ = needs_depth_ && depth_ready;
    used_stock_fallback_ = needs_depth_ && !depth_ready;
    clear();
    status_ = Status::Finished;
    return status_;
  }

 public:
  ~FillDepthContinuation()
  {
    clear();
  }

  Status begin(const Solver solver,
               const bool needs_depth,
               const CacheState initial_state,
               const bool in_bounds,
               const bool timer_available,
               const Context context,
               const FillInput input)
  {
    expect(!pending_ && apply_count_ == 0, "fill continuation was reused");
    solver_ = solver;
    producer_ = context;
    needs_depth_ = needs_depth;
    if (!in_bounds) {
      status_ = Status::Cancelled;
      return status_;
    }
    retained_input_ = input;
    if (!needs_depth) {
      return apply(false);
    }
    if (initial_state == CacheState::Ready) {
      return apply(true);
    }
    if (initial_state == CacheState::Failed) {
      return apply(false);
    }

    request_owned_ = true;
    if (!timer_available) {
      clear();
      status_ = Status::Cancelled;
      return status_;
    }
    timer_owned_ = true;
    pending_ = true;
    tick_count_ = 0;
    status_ = Status::Running;
    return status_;
  }

  Status event(const EventKind kind, const CacheState state, const Context &context)
  {
    if (!pending_) {
      return status_;
    }
    if (!(context == producer_) || kind == EventKind::Cancel) {
      clear();
      status_ = Status::Cancelled;
      return status_;
    }
    if (kind != EventKind::OwnTimer) {
      return status_;
    }
    tick_count_++;
    if (tick_count_ > 240) {
      clear();
      status_ = Status::Cancelled;
      return status_;
    }
    if (state == CacheState::Pending) {
      return status_;
    }
    if (state == CacheState::Failed) {
      clear();
      status_ = Status::Cancelled;
      return status_;
    }
    return apply(true);
  }

  void abandon()
  {
    clear();
    status_ = Status::Cancelled;
  }

  bool pending() const
  {
    return pending_;
  }
  bool request_owned() const
  {
    return request_owned_;
  }
  bool timer_owned() const
  {
    return timer_owned_;
  }
  int tick_count() const
  {
    return tick_count_;
  }
  int apply_count() const
  {
    return apply_count_;
  }
  int pixel_count() const
  {
    return pixel_count_;
  }
  int delaunay_count() const
  {
    return delaunay_count_;
  }
  bool used_depth() const
  {
    return used_depth_;
  }
  bool used_stock_fallback() const
  {
    return used_stock_fallback_;
  }
  const std::optional<FillInput> &applied_input() const
  {
    return applied_input_;
  }
};

constexpr Context base_context = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};
constexpr FillInput base_input = {101, 202, 31, 47, 1, 0x35, true};

int native_immediate_and_initial_fallback()
{
  FillDepthContinuation pixel;
  expect(pixel.begin(Solver::Pixel, true, CacheState::Ready, true, true, base_context, base_input) ==
             Status::Finished,
         "native pixel fill did not finish immediately");
  expect(pixel.pixel_count() == 1 && pixel.used_depth(), "native pixel fill lost ready depth");

  FillDepthContinuation delaunay;
  expect(delaunay.begin(
             Solver::Delaunay, true, CacheState::Ready, true, true, base_context, base_input) ==
             Status::Finished,
         "native Delaunay fill did not finish immediately");
  expect(delaunay.delaunay_count() == 1 && delaunay.used_depth(),
         "native Delaunay fill lost ready depth");

  FillDepthContinuation fallback;
  expect(fallback.begin(
             Solver::Pixel, true, CacheState::Failed, true, true, base_context, base_input) ==
             Status::Finished,
         "initial cache failure did not preserve stock fallback");
  expect(fallback.used_stock_fallback(), "initial cache failure manufactured depth");

  FillDepthContinuation no_depth;
  expect(no_depth.begin(
             Solver::Pixel, false, CacheState::Pending, true, true, base_context, base_input) ==
             Status::Finished,
         "non-depth fill was suspended");
  return 4;
}

int pre_result_suspension()
{
  FillDepthContinuation pixel;
  expect(pixel.begin(
             Solver::Pixel, true, CacheState::Pending, true, true, base_context, base_input) ==
             Status::Running,
         "pixel fill did not suspend");
  expect(pixel.pixel_count() == 0 && pixel.apply_count() == 0,
         "pixel image work ran before readiness");

  FillDepthContinuation delaunay;
  expect(delaunay.begin(
             Solver::Delaunay, true, CacheState::Pending, true, true, base_context, base_input) ==
             Status::Running,
         "Delaunay fill did not suspend");
  expect(delaunay.delaunay_count() == 0 && delaunay.apply_count() == 0,
         "Delaunay work ran before readiness");
  expect(pixel.pending() && pixel.request_owned() && pixel.timer_owned(),
         "pending fill does not own request and timer");
  return 3;
}

int pixel_and_delaunay_ready_only()
{
  FillDepthContinuation pixel;
  pixel.begin(Solver::Pixel, true, CacheState::Pending, true, true, base_context, base_input);
  expect(pixel.event(EventKind::OwnTimer, CacheState::Ready, base_context) == Status::Finished,
         "ready pixel fill did not settle");
  expect(pixel.pixel_count() == 1 && pixel.delaunay_count() == 0,
         "pixel solver crossed result paths");
  pixel.event(EventKind::OwnTimer, CacheState::Ready, base_context);
  expect(pixel.apply_count() == 1, "duplicate pixel settlement repeated work");

  FillDepthContinuation delaunay;
  delaunay.begin(
      Solver::Delaunay, true, CacheState::Pending, true, true, base_context, base_input);
  expect(delaunay.event(EventKind::OwnTimer, CacheState::Ready, base_context) == Status::Finished &&
             delaunay.delaunay_count() == 1 && delaunay.pixel_count() == 0,
         "ready Delaunay fill crossed result paths");
  return 4;
}

int retained_fill_inputs()
{
  FillInput mutable_input = base_input;
  FillDepthContinuation pending;
  pending.begin(
      Solver::Pixel, true, CacheState::Pending, true, true, base_context, mutable_input);
  mutable_input = {0, 0, 0, 0, 0, 0, false};
  pending.event(EventKind::OwnTimer, CacheState::Ready, base_context);
  expect(pending.applied_input() == std::optional<FillInput>(base_input),
         "pending fill did not retain exact coordinates/options");

  FillDepthContinuation out_of_bounds;
  expect(out_of_bounds.begin(
             Solver::Pixel, true, CacheState::Pending, false, true, base_context, base_input) ==
             Status::Cancelled &&
             out_of_bounds.apply_count() == 0,
         "out-of-bounds fill allocated work");

  FillDepthContinuation immediate;
  immediate.begin(Solver::Delaunay, true, CacheState::Ready, true, true, base_context, base_input);
  expect(immediate.applied_input() == std::optional<FillInput>(base_input),
         "immediate fill changed exact inputs");
  return 3;
}

int identified_bounded_poll()
{
  FillDepthContinuation fill;
  fill.begin(Solver::Pixel, true, CacheState::Pending, true, true, base_context, base_input);
  expect(fill.event(EventKind::Other, CacheState::Ready, base_context) == Status::Running &&
             fill.tick_count() == 0,
         "unrelated event polled the request");
  expect(fill.event(EventKind::ForeignTimer, CacheState::Ready, base_context) == Status::Running &&
             fill.tick_count() == 0,
         "foreign timer polled the request");
  for (int i = 0; i < 240; i++) {
    expect(fill.event(EventKind::OwnTimer, CacheState::Pending, base_context) == Status::Running,
           "bounded wait ended early");
  }
  expect(fill.tick_count() == 240 && fill.pending(), "240-tick bound changed");
  expect(fill.event(EventKind::OwnTimer, CacheState::Pending, base_context) == Status::Cancelled &&
             !fill.pending() && !fill.request_owned() && !fill.timer_owned(),
         "timeout retained owned work");
  return 4;
}

int producing_context_guard()
{
  Context drifted = base_context;
  drifted.brush++;
  FillDepthContinuation drift;
  drift.begin(Solver::Pixel, true, CacheState::Pending, true, true, base_context, base_input);
  expect(drift.event(EventKind::Other, CacheState::Pending, drifted) == Status::Cancelled,
         "context drift did not cancel before polling");

  FillDepthContinuation stable;
  stable.begin(Solver::Pixel, true, CacheState::Pending, true, true, base_context, base_input);
  expect(stable.event(EventKind::Other, CacheState::Pending, base_context) == Status::Running,
         "stable context cancelled");

  FillDepthContinuation ready_drift;
  ready_drift.begin(
      Solver::Delaunay, true, CacheState::Pending, true, true, base_context, base_input);
  expect(ready_drift.event(EventKind::OwnTimer, CacheState::Ready, drifted) == Status::Cancelled &&
             ready_drift.apply_count() == 0,
         "ready data escaped its producing context");
  return 3;
}

int failure_timeout_cancellation()
{
  FillDepthContinuation failed;
  failed.begin(Solver::Pixel, true, CacheState::Pending, true, true, base_context, base_input);
  expect(failed.event(EventKind::OwnTimer, CacheState::Failed, base_context) == Status::Cancelled,
         "backend failure did not cancel");

  FillDepthContinuation cancelled;
  cancelled.begin(
      Solver::Delaunay, true, CacheState::Pending, true, true, base_context, base_input);
  expect(cancelled.event(EventKind::Cancel, CacheState::Pending, base_context) ==
             Status::Cancelled,
         "explicit cancellation did not settle");

  FillDepthContinuation no_timer;
  expect(no_timer.begin(
             Solver::Pixel, true, CacheState::Pending, true, false, base_context, base_input) ==
             Status::Cancelled,
         "timer allocation failure retained a request");

  FillDepthContinuation abandoned;
  abandoned.begin(
      Solver::Delaunay, true, CacheState::Pending, true, true, base_context, base_input);
  abandoned.abandon();
  expect(!abandoned.pending() && !abandoned.request_owned() && !abandoned.timer_owned(),
         "external destruction retained owned work");
  return 4;
}

int exact_once_cleanup()
{
  FillDepthContinuation success;
  success.begin(Solver::Pixel, true, CacheState::Pending, true, true, base_context, base_input);
  success.event(EventKind::OwnTimer, CacheState::Ready, base_context);
  expect(success.apply_count() == 1 && !success.pending() && !success.request_owned() &&
             !success.timer_owned(),
         "success retained continuation state");

  FillDepthContinuation cancel;
  cancel.begin(Solver::Pixel, true, CacheState::Pending, true, true, base_context, base_input);
  cancel.event(EventKind::Cancel, CacheState::Pending, base_context);
  expect(cancel.apply_count() == 0 && !cancel.pending() && !cancel.request_owned() &&
             !cancel.timer_owned(),
         "cancel retained continuation state");

  cancel.abandon();
  expect(cancel.apply_count() == 0 && !cancel.pending(), "repeated cleanup changed ownership");
  return 3;
}

}  // namespace

int main()
{
  try {
    int cases = 0;
    const int native_cases = native_immediate_and_initial_fallback();
    cases += native_cases;
    std::cout << "CONTRACT native_immediate_and_initial_fallback PASS cases=" << native_cases
              << '\n';
    const int suspension_cases = pre_result_suspension();
    cases += suspension_cases;
    std::cout << "CONTRACT pre_result_suspension PASS cases=" << suspension_cases << '\n';
    const int solver_cases = pixel_and_delaunay_ready_only();
    cases += solver_cases;
    std::cout << "CONTRACT pixel_and_delaunay_ready_only PASS cases=" << solver_cases << '\n';
    const int input_cases = retained_fill_inputs();
    cases += input_cases;
    std::cout << "CONTRACT retained_fill_inputs PASS cases=" << input_cases << '\n';
    const int poll_cases = identified_bounded_poll();
    cases += poll_cases;
    std::cout << "CONTRACT identified_bounded_poll PASS cases=" << poll_cases << '\n';
    const int context_cases = producing_context_guard();
    cases += context_cases;
    std::cout << "CONTRACT producing_context_guard PASS cases=" << context_cases << '\n';
    const int failure_cases = failure_timeout_cancellation();
    cases += failure_cases;
    std::cout << "CONTRACT failure_timeout_cancellation PASS cases=" << failure_cases << '\n';
    const int cleanup_cases = exact_once_cleanup();
    cases += cleanup_cases;
    std::cout << "CONTRACT exact_once_cleanup PASS cases=" << cleanup_cases << '\n';
    expect(cases == 28, "case census changed");
    std::cout << "M5_GREASE_PENCIL_FILL_DEPTH_CACHE_CONTRACT_PASS contracts=8 cases=" << cases
              << '\n';
    return 0;
  }
  catch (const std::exception &error) {
    std::cerr << "M5_GREASE_PENCIL_FILL_DEPTH_CACHE_CONTRACT_FAIL " << error.what() << '\n';
    return 1;
  }
}
