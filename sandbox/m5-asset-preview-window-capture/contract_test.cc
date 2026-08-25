/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

namespace {

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "M5_ASSET_PREVIEW_WINDOW_CAPTURE_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
}

enum class CaptureState { Pending, Ready, Failed };
enum class Result { Running, Finished, Cancelled };

struct Context {
  int manager = 1;
  int window = 2;
  int screen = 3;
  int main = 4;
  int asset_type = 5;
  int asset_reference = 6;

  friend bool operator==(const Context &, const Context &) = default;
};

struct Rect {
  int xmin;
  int xmax;
  int ymin;
  int ymax;
};

class ControlledCapture {
 public:
  CaptureState state = CaptureState::Pending;
  int width = 0;
  int height = 0;
  std::vector<uint8_t> bytes;
  std::string *lifetime = nullptr;

  ControlledCapture(const int width,
                    const int height,
                    std::vector<uint8_t> bytes,
                    std::string &lifetime)
      : width(width), height(height), bytes(std::move(bytes)), lifetime(&lifetime)
  {
  }

  ~ControlledCapture()
  {
    lifetime->push_back('R');
  }

  void cancel()
  {
    lifetime->push_back('C');
  }
};

class Session {
 private:
  ControlledCapture *capture_ = nullptr;
  Context producing_;
  Rect crop_ = {};
  bool interactive_ = false;
  bool timer_ = false;
  bool modal_handler_ = false;
  int tick_count_ = 0;
  int applies_ = 0;
  std::vector<uint8_t> cropped_;
  std::string *lifetime_ = nullptr;

  bool context_matches(const Context &current) const
  {
    return current == producing_;
  }

  void cleanup()
  {
    if (timer_) {
      timer_ = false;
      lifetime_->push_back('T');
    }
    if (capture_ != nullptr) {
      capture_->cancel();
      delete capture_;
      capture_ = nullptr;
    }
  }

  bool consume_crop()
  {
    if (capture_->width <= 0 || capture_->height <= 0 ||
        capture_->bytes.size() != size_t(capture_->width) * size_t(capture_->height) * 4)
    {
      return false;
    }
    const int xmin = std::max(0, crop_.xmin);
    const int ymin = std::max(0, crop_.ymin);
    const int xmax = std::min(capture_->width - 1, crop_.xmax);
    const int ymax = std::min(capture_->height - 1, crop_.ymax);
    if (xmin > xmax || ymin > ymax) {
      return false;
    }
    const int crop_width = xmax - xmin + 1;
    cropped_.clear();
    for (int y = ymin; y <= ymax; y++) {
      const size_t begin = (size_t(y) * capture_->width + xmin) * 4;
      cropped_.insert(cropped_.end(),
                      capture_->bytes.begin() + begin,
                      capture_->bytes.begin() + begin + size_t(crop_width) * 4);
    }
    return true;
  }

 public:
  ~Session()
  {
    cleanup();
  }

  void begin(ControlledCapture *capture,
             const Context &producing,
             const Rect crop,
             const bool interactive,
             std::string &lifetime)
  {
    cleanup();
    capture_ = capture;
    producing_ = producing;
    crop_ = crop;
    interactive_ = interactive;
    timer_ = false;
    modal_handler_ = false;
    tick_count_ = 0;
    lifetime_ = &lifetime;
  }

  Result poll(const Context &current)
  {
    if (capture_ == nullptr || !context_matches(current)) {
      cleanup();
      return Result::Cancelled;
    }
    if (capture_->state == CaptureState::Pending) {
      if (!timer_) {
        timer_ = true;
        modal_handler_ = !interactive_;
      }
      return Result::Running;
    }
    if (capture_->state != CaptureState::Ready || !consume_crop()) {
      cleanup();
      return Result::Cancelled;
    }
    applies_++;
    cleanup();
    return Result::Finished;
  }

  Result modal(const Context &current,
               const bool timer_event,
               const bool identified_timer,
               const bool escape)
  {
    if (escape) {
      cleanup();
      return Result::Cancelled;
    }
    if (!timer_event || !identified_timer) {
      return Result::Running;
    }
    if (!context_matches(current)) {
      return poll(current);
    }
    if (capture_->state == CaptureState::Pending) {
      constexpr int max_tick_count = 240;
      tick_count_++;
      if (tick_count_ < max_tick_count) {
        return Result::Running;
      }
      cleanup();
      return Result::Cancelled;
    }
    return poll(current);
  }

  bool timer() const
  {
    return timer_;
  }
  bool modal_handler() const
  {
    return modal_handler_;
  }
  int applies() const
  {
    return applies_;
  }
  const std::vector<uint8_t> &cropped() const
  {
    return cropped_;
  }
};

std::vector<uint8_t> numbered_rgba(const int width, const int height)
{
  std::vector<uint8_t> bytes(size_t(width) * size_t(height) * 4);
  for (size_t index = 0; index < bytes.size(); index++) {
    bytes[index] = uint8_t(index);
  }
  return bytes;
}

bool contract_native_immediate()
{
  Context context;
  std::string lifetime;
  auto *capture = new ControlledCapture(1, 1, {1, 2, 3, 4}, lifetime);
  capture->state = CaptureState::Ready;
  Session session;
  session.begin(capture, context, {0, 0, 0, 0}, true, lifetime);
  const bool ok = require(session.poll(context) == Result::Finished, "native result") &&
                  require(session.applies() == 1, "native apply count") &&
                  require(session.cropped() == std::vector<uint8_t>({1, 2, 3, 4}),
                          "native pixels") &&
                  require(lifetime == "CR", "native cleanup");
  if (ok) {
    std::puts("CONTRACT native_immediate PASS cases=4");
  }
  return ok;
}

bool contract_pending_resume()
{
  Context context;
  std::string lifetime;
  auto *capture = new ControlledCapture(1, 1, {4, 3, 2, 1}, lifetime);
  Session session;
  session.begin(capture, context, {0, 0, 0, 0}, true, lifetime);
  const bool pending = session.poll(context) == Result::Running && session.timer() &&
                       !session.modal_handler() &&
                       session.modal(context, false, false, false) == Result::Running;
  capture->state = CaptureState::Ready;
  const bool ready = session.modal(context, true, true, false) == Result::Finished &&
                     session.applies() == 1 && lifetime == "TCR";
  const bool ok = require(pending, "pending interactive owner") &&
                  require(ready, "pending resume") &&
                  require(!session.timer(), "terminal timer") &&
                  require(session.cropped() == std::vector<uint8_t>({4, 3, 2, 1}),
                          "resumed pixels");
  if (ok) {
    std::puts("CONTRACT pending_resume PASS cases=4");
  }
  return ok;
}

bool contract_exact_crop()
{
  Context context;
  std::string lifetime;
  auto *capture = new ControlledCapture(3, 2, numbered_rgba(3, 2), lifetime);
  capture->state = CaptureState::Ready;
  Session session;
  session.begin(capture, context, {1, 2, 0, 0}, true, lifetime);
  const std::vector<uint8_t> expected = {4, 5, 6, 7, 8, 9, 10, 11};
  const bool ok = require(session.poll(context) == Result::Finished, "crop result") &&
                  require(session.cropped() == expected, "crop bytes") &&
                  require(session.applies() == 1, "crop apply") &&
                  require(lifetime == "CR", "crop cleanup");
  if (ok) {
    std::puts("CONTRACT exact_crop PASS cases=4");
  }
  return ok;
}

bool contract_direct_modal_owner()
{
  Context context;
  std::string lifetime;
  auto *capture = new ControlledCapture(1, 1, {0, 1, 2, 3}, lifetime);
  Session session;
  session.begin(capture, context, {0, 0, 0, 0}, false, lifetime);
  const bool ok = require(session.poll(context) == Result::Running, "direct pending") &&
                  require(session.timer(), "direct timer") &&
                  require(session.modal_handler(), "direct modal handler");
  if (ok) {
    std::puts("CONTRACT direct_modal_owner PASS cases=3");
  }
  return ok;
}

bool contract_context_drift()
{
  Context context;
  Context drifted = context;
  drifted.window++;
  std::string lifetime;
  auto *capture = new ControlledCapture(1, 1, {0, 0, 0, 0}, lifetime);
  Session session;
  session.begin(capture, context, {0, 0, 0, 0}, true, lifetime);
  session.poll(context);
  const bool ok = require(session.modal(drifted, true, true, false) == Result::Cancelled,
                          "context drift result") &&
                  require(session.applies() == 0, "context drift apply") &&
                  require(lifetime == "TCR", "context drift cleanup");
  if (ok) {
    std::puts("CONTRACT context_drift PASS cases=3");
  }
  return ok;
}

bool contract_failure_timeout()
{
  Context context;
  std::string failure_lifetime;
  auto *failed = new ControlledCapture(1, 1, {0, 0, 0, 0}, failure_lifetime);
  failed->state = CaptureState::Failed;
  Session failure;
  failure.begin(failed, context, {0, 0, 0, 0}, true, failure_lifetime);
  const bool failed_ok = failure.poll(context) == Result::Cancelled && failure.applies() == 0 &&
                         failure_lifetime == "CR";

  std::string timeout_lifetime;
  auto *pending = new ControlledCapture(1, 1, {0, 0, 0, 0}, timeout_lifetime);
  Session timeout;
  timeout.begin(pending, context, {0, 0, 0, 0}, true, timeout_lifetime);
  timeout.poll(context);
  for (int tick = 1; tick < 240; tick++) {
    if (timeout.modal(context, true, true, false) != Result::Running) {
      return require(false, "early timeout");
    }
  }
  const bool timeout_ok = timeout.modal(context, true, true, false) == Result::Cancelled &&
                          timeout.applies() == 0 && timeout_lifetime == "TCR";
  const bool ok = require(failed_ok, "backend failure") &&
                  require(timeout_ok, "bounded timeout") &&
                  require(!timeout.timer(), "timeout timer removed") &&
                  require(failure.applies() + timeout.applies() == 0, "failure mutation");
  if (ok) {
    std::puts("CONTRACT failure_timeout PASS cases=4");
  }
  return ok;
}

bool contract_escape_cleanup()
{
  Context context;
  std::string lifetime;
  auto *capture = new ControlledCapture(1, 1, {0, 0, 0, 0}, lifetime);
  Session session;
  session.begin(capture, context, {0, 0, 0, 0}, true, lifetime);
  session.poll(context);
  const bool ok = require(session.modal(context, false, false, true) == Result::Cancelled,
                          "escape result") &&
                  require(session.applies() == 0, "escape apply") &&
                  require(lifetime == "TCR", "escape cleanup order");
  if (ok) {
    std::puts("CONTRACT escape_cleanup PASS cases=3");
  }
  return ok;
}

bool contract_target_identity()
{
  Context context;
  Context other_asset = context;
  other_asset.asset_reference++;
  std::string lifetime;
  auto *capture = new ControlledCapture(1, 1, {0, 0, 0, 0}, lifetime);
  capture->state = CaptureState::Ready;
  Session session;
  session.begin(capture, context, {0, 0, 0, 0}, true, lifetime);
  const bool ok = require(session.poll(other_asset) == Result::Cancelled, "asset drift result") &&
                  require(session.applies() == 0, "asset drift apply") &&
                  require(lifetime == "CR", "asset drift cleanup");
  if (ok) {
    std::puts("CONTRACT target_identity PASS cases=3");
  }
  return ok;
}

}  // namespace

int main()
{
  const std::array contracts = {contract_native_immediate,
                                contract_pending_resume,
                                contract_exact_crop,
                                contract_direct_modal_owner,
                                contract_context_drift,
                                contract_failure_timeout,
                                contract_escape_cleanup,
                                contract_target_identity};
  for (const auto contract : contracts) {
    if (!contract()) {
      return 1;
    }
  }
  std::puts("M5_ASSET_PREVIEW_WINDOW_CAPTURE_CONTRACT_PASS contracts=8 cases=28");
  return 0;
}
