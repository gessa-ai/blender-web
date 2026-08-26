/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup GHOST-web
 *
 * Standalone harness for GHOST_SystemWeb / GHOST_WindowWeb / GHOST_EventBridgeWeb.
 *
 * Builds the web GHOST classes against the REAL upstream GHOST base classes
 * (GHOST_System / GHOST_Window / GHOST_EventManager / ... — read-only include), wires
 * a logging GHOST_IEventConsumer, creates the canvas window, and pumps the GHOST
 * event queue from an emscripten main loop. Real browser input over the canvas then
 * appears as GHOST-shaped events on the page + console — proving the whole bridge
 * against the genuine GHOST event machinery.
 *
 * Runs main() on the same PROXY_TO_PTHREAD worker topology as the product. This is
 * required by the worker-only WasmFS/OPFS mount and lets state requests exercise
 * the real WM-worker -> browser-main HTML5 proxy boundary.
 */

#include <atomic>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <memory>

#include <emscripten/emscripten.h>
#include <emscripten/html5.h>

#include "GHOST_SystemWeb.hh"
#include "GHOST_WindowWeb.hh"

#include "GHOST_Event.hh"
#include "GHOST_Buttons.hh"
#include "GHOST_IEventConsumer.hh"
#include "GHOST_ModifierKeys.hh"
#include "GHOST_Types.hh"
#include "GHOST_WindowManager.hh"

/* Append a line to the on-page log (and it also goes to the console via printf). */
static void harness_log(const char *msg)
{
  MAIN_THREAD_EM_ASM(
      {
        if (typeof globalThis.ghostLog === "function") {
          globalThis.ghostLog(UTF8ToString($0));
        }
      },
      msg);
}

static const char *event_type_name(GHOST_TEventType t)
{
  switch (t) {
    case GHOST_kEventCursorMove:
      return "CursorMove";
    case GHOST_kEventButtonDown:
      return "ButtonDown";
    case GHOST_kEventButtonUp:
      return "ButtonUp";
    case GHOST_kEventWheel:
      return "Wheel";
    case GHOST_kEventKeyDown:
      return "KeyDown";
    case GHOST_kEventKeyUp:
      return "KeyUp";
    case GHOST_kEventWindowSize:
      return "WindowSize";
    case GHOST_kEventWindowActivate:
      return "WindowActivate";
    case GHOST_kEventWindowDeactivate:
      return "WindowDeactivate";
#ifdef WITH_INPUT_IME
    case GHOST_kEventImeCompositionStart:
      return "ImeStart";
    case GHOST_kEventImeComposition:
      return "ImeComposition";
    case GHOST_kEventImeCompositionEnd:
      return "ImeEnd";
#endif
    default:
      return "Other";
  }
}

/** Logs each GHOST event's decoded payload — the harness's proof surface. */
class LoggingConsumer : public GHOST_IEventConsumer {
 public:
  bool processEvent(const GHOST_IEvent *event) override
  {
    char line[1024];
    const GHOST_TEventType type = event->getType();
    const char *name = event_type_name(type);
    const void *raw = event->getData();

    switch (type) {
      case GHOST_kEventCursorMove: {
        auto *d = (const GHOST_TEventCursorData *)raw;
        std::snprintf(line, sizeof(line), "GHOST %-16s x=%d y=%d", name, d->x, d->y);
        break;
      }
      case GHOST_kEventButtonDown:
      case GHOST_kEventButtonUp: {
        auto *d = (const GHOST_TEventButtonData *)raw;
        std::snprintf(line, sizeof(line), "GHOST %-16s button=%d", name, int(d->button));
        break;
      }
      case GHOST_kEventWheel: {
        auto *d = (const GHOST_TEventWheelData *)raw;
        std::snprintf(line, sizeof(line), "GHOST %-16s axis=%d value=%d", name, int(d->axis),
                      d->value);
        break;
      }
      case GHOST_kEventKeyDown:
      case GHOST_kEventKeyUp: {
        auto *d = (const GHOST_TEventKeyData *)raw;
        char utf8[7] = {0};
        for (int i = 0; i < 6 && d->utf8_buf[i]; i++) {
          utf8[i] = d->utf8_buf[i];
        }
        std::snprintf(line, sizeof(line), "GHOST %-16s key=0x%03X utf8='%s' repeat=%d", name,
                      int(d->key), utf8, int(d->is_repeat));
        break;
      }
#ifdef WITH_INPUT_IME
      case GHOST_kEventImeCompositionStart:
      case GHOST_kEventImeComposition:
      case GHOST_kEventImeCompositionEnd: {
        auto *d = static_cast<const GHOST_TEventImeData *>(raw);
        std::snprintf(line,
                      sizeof(line),
                      "GHOST %-16s result='%s' composite='%s' cursor=%d target=%d:%d",
                      name,
                      d->result.c_str(),
                      d->composite.c_str(),
                      d->cursor_position,
                      d->target_start,
                      d->target_end);
        break;
      }
#endif
      default:
        std::snprintf(line, sizeof(line), "GHOST %-16s", name);
        break;
    }
    std::printf("%s\n", line);
    harness_log(line);
    return true;
  }
};

static GHOST_SystemWeb *g_system = nullptr;
static GHOST_IWindow *g_window = nullptr;
static std::atomic<int> g_requested_window_state{-1};
static std::atomic<int> g_window_state_result{-2};
static std::atomic<int> g_requested_cursor_grab{-1};
static std::atomic<int> g_cursor_grab_result{-2};
static std::atomic<int> g_requested_custom_cursor{-1};
static std::atomic<int> g_custom_cursor_result{-2};
static std::atomic<int> g_requested_clipboard_operation{-1};
static std::atomic<int> g_clipboard_result{-2};
static std::atomic<int> g_requested_window_lifecycle{-1};
static std::atomic<int> g_window_lifecycle_result{-2};
#ifdef WITH_INPUT_IME
static std::atomic<int> g_requested_ime_action{-1};
static std::atomic<int> g_ime_result{-2};
static std::atomic<int> g_ime_x{0};
static std::atomic<int> g_ime_y{0};
static std::atomic<int> g_ime_w{0};
static std::atomic<int> g_ime_h{0};
static std::atomic<int> g_ime_completed{0};
#endif

static constexpr const char *CLIPBOARD_EXTERNAL =
    "from-browser-paste-\xF0\x9F\xAA\xB6";
static constexpr const char *CLIPBOARD_OUTBOUND =
    "from-ghost-worker-\xE2\x9C\x93-\xF0\x9F\xAA\xB6\nline-2";

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_request_window_state(const int state)
{
  if (state < int(GHOST_kWindowStateNormal) || state > int(GHOST_kWindowStateFullScreen)) {
    return int(GHOST_kFailure);
  }
  g_window_state_result.store(-2, std::memory_order_relaxed);
  g_requested_window_state.store(state, std::memory_order_release);
  return int(GHOST_kSuccess);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_window_state_result()
{
  return g_window_state_result.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_request_cursor_grab(const int mode)
{
  if (mode < int(GHOST_kGrabDisable) || mode > int(GHOST_kGrabHide)) {
    return int(GHOST_kFailure);
  }
  g_cursor_grab_result.store(-2, std::memory_order_relaxed);
  g_requested_cursor_grab.store(mode, std::memory_order_release);
  return int(GHOST_kSuccess);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_cursor_grab_result()
{
  return g_cursor_grab_result.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_cursor_grab_state()
{
  if (g_window == nullptr) {
    return -1;
  }
  auto *window = static_cast<GHOST_WindowWeb *>(g_window);
  GHOST_TGrabCursorMode actual_mode = GHOST_kGrabDisable;
  GHOST_TAxisFlag wrap_axis = GHOST_kAxisNone;
  GHOST_Rect bounds;
  bool software_cursor = false;
  window->getCursorGrabState(actual_mode, wrap_axis, bounds, software_cursor);
  return int(actual_mode) | (int(window->pointerLockRequestedMode()) << 4) |
         (int(window->pointerLockState()) << 8);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_request_custom_cursor(const int operation)
{
  if (operation < 0 || operation > 5) {
    return int(GHOST_kFailure);
  }
  g_custom_cursor_result.store(-2, std::memory_order_relaxed);
  g_requested_custom_cursor.store(operation, std::memory_order_release);
  return int(GHOST_kSuccess);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_custom_cursor_result()
{
  return g_custom_cursor_result.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_custom_cursor_capabilities()
{
  if (g_system == nullptr) {
    return -1;
  }
  const GHOST_TCapabilityFlag capabilities = g_system->getCapabilities();
  return ((capabilities & GHOST_kCapabilityCursorRGBA) ? (1 << 0) : 0) |
         ((capabilities & GHOST_kCapabilityCursorGenerator) ? (1 << 1) : 0);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_input_state()
{
  if (g_system == nullptr) {
    return -1;
  }

  GHOST_ModifierKeys keys;
  GHOST_Buttons buttons;
  if (g_system->getModifierKeys(keys) != GHOST_kSuccess ||
      g_system->getButtons(buttons) != GHOST_kSuccess)
  {
    return -1;
  }

  int state = 0;
  state |= (keys.get(GHOST_kModifierKeyLeftControl) ||
            keys.get(GHOST_kModifierKeyRightControl)) ?
               (1 << 0) :
               0;
  state |= (keys.get(GHOST_kModifierKeyLeftShift) ||
            keys.get(GHOST_kModifierKeyRightShift)) ?
               (1 << 1) :
               0;
  state |= (keys.get(GHOST_kModifierKeyLeftAlt) ||
            keys.get(GHOST_kModifierKeyRightAlt)) ?
               (1 << 2) :
               0;
  state |= (keys.get(GHOST_kModifierKeyLeftOS) || keys.get(GHOST_kModifierKeyRightOS)) ?
               (1 << 3) :
               0;
  state |= buttons.get(GHOST_kButtonMaskLeft) ? (1 << 4) : 0;
  state |= buttons.get(GHOST_kButtonMaskMiddle) ? (1 << 5) : 0;
  state |= buttons.get(GHOST_kButtonMaskRight) ? (1 << 6) : 0;
  state |= buttons.get(GHOST_kButtonMaskButton4) ? (1 << 7) : 0;
  state |= buttons.get(GHOST_kButtonMaskButton5) ? (1 << 8) : 0;
  return state;
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_modifier_state_exact()
{
  if (g_system == nullptr) {
    return -1;
  }

  GHOST_ModifierKeys keys;
  if (g_system->getModifierKeys(keys) != GHOST_kSuccess) {
    return -1;
  }

  int state = 0;
  for (int modifier = int(GHOST_kModifierKeyLeftShift);
       modifier <= int(GHOST_kModifierKeyRightOS);
       modifier++)
  {
    if (keys.get(GHOST_TModifierKey(modifier))) {
      state |= 1 << modifier;
    }
  }
  return state;
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_request_clipboard_operation(
    const int operation)
{
  if (operation < 0 || operation > 7) {
    return int(GHOST_kFailure);
  }
  g_clipboard_result.store(-2, std::memory_order_relaxed);
  g_requested_clipboard_operation.store(operation, std::memory_order_release);
  return int(GHOST_kSuccess);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_clipboard_result()
{
  return g_clipboard_result.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_request_window_lifecycle(const int action)
{
  if (action < 0 || action > 2) {
    return int(GHOST_kFailure);
  }
  g_window_lifecycle_result.store(-2, std::memory_order_relaxed);
  g_requested_window_lifecycle.store(action, std::memory_order_release);
  return int(GHOST_kSuccess);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_window_lifecycle_result()
{
  return g_window_lifecycle_result.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_window_manager_state()
{
  if (g_system == nullptr || g_system->getWindowManager() == nullptr) {
    return -2;
  }
  GHOST_IWindow *active = g_system->getWindowManager()->getActiveWindow();
  if (active == nullptr) {
    return 0;
  }
  return active == g_window ? 1 : -1;
}

#ifdef WITH_INPUT_IME
extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_ime_capability()
{
  return g_system && (g_system->getCapabilities() & GHOST_kCapabilityInputIME) != 0;
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_request_ime(const int action,
                                                               const int x,
                                                               const int y,
                                                               const int w,
                                                               const int h,
                                                               const int completed)
{
  if ((action != 0 && action != 1) || x < 0 || y < 0 || w < 0 || h < 0 ||
      (completed != 0 && completed != 1))
  {
    return int(GHOST_kFailure);
  }
  g_ime_x.store(x, std::memory_order_relaxed);
  g_ime_y.store(y, std::memory_order_relaxed);
  g_ime_w.store(w, std::memory_order_relaxed);
  g_ime_h.store(h, std::memory_order_relaxed);
  g_ime_completed.store(completed, std::memory_order_relaxed);
  g_ime_result.store(-2, std::memory_order_relaxed);
  g_requested_ime_action.store(action, std::memory_order_release);
  return int(GHOST_kSuccess);
}

extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_ime_result()
{
  return g_ime_result.load(std::memory_order_acquire);
}
#endif

static bool clipboard_equals(const char *expected, const bool selection = false)
{
  char *actual = g_system->getClipboard(selection);
  const bool equal = actual != nullptr && std::strcmp(actual, expected) == 0;
  std::free(actual);
  return equal;
}

static bool clipboard_is_null(const bool selection = false)
{
  char *actual = g_system->getClipboard(selection);
  const bool is_null = actual == nullptr;
  std::free(actual);
  return is_null;
}

static bool run_clipboard_operation(const int operation)
{
  switch (operation) {
    case 0:
      return clipboard_is_null();
    case 1:
      return clipboard_equals(CLIPBOARD_EXTERNAL);
    case 2:
      g_system->putClipboard(CLIPBOARD_OUTBOUND, false);
      return true;
    case 3:
      return clipboard_equals(CLIPBOARD_OUTBOUND);
    case 4:
      g_system->putClipboard("primary-selection-must-not-replace-ordinary", true);
      return true;
    case 5:
      return clipboard_is_null(true) && clipboard_equals(CLIPBOARD_OUTBOUND);
    case 6:
      g_system->putClipboard("", false);
      return true;
    case 7:
      return clipboard_equals("");
  }
  return false;
}

static GHOST_TSuccess run_custom_cursor_operation(const int operation)
{
  if (g_window == nullptr) {
    return GHOST_kFailure;
  }
  switch (operation) {
    case 0: {
      static constexpr uint8_t rgba[16] = {
          255, 0, 0, 255, 0, 255, 0, 128, 0, 0, 255, 64, 255, 255, 255, 0};
      const int size[2] = {2, 2};
      const int hot_spot[2] = {1, 0};
      return g_window->setCustomCursorShape(rgba, nullptr, size, hot_spot, false);
    }
    case 1: {
      static constexpr uint8_t bitmap[2] = {0b01, 0b10};
      static constexpr uint8_t mask[2] = {0b11, 0b10};
      const int size[2] = {2, 2};
      const int hot_spot[2] = {0, 1};
      return g_window->setCustomCursorShape(bitmap, mask, size, hot_spot, false);
    }
    case 2: {
      static constexpr uint8_t rgba[16] = {};
      const int size[2] = {2, 2};
      const int invalid_hot_spot[2] = {2, 0};
      return g_window->setCustomCursorShape(rgba, nullptr, size, invalid_hot_spot, false);
    }
    case 3:
      return g_window->setCursorShape(GHOST_kStandardCursorText);
    case 4:
      return g_window->setCursorVisibility(false);
    case 5:
      return g_window->setCursorVisibility(true);
  }
  return GHOST_kFailure;
}

static GHOST_IWindow *create_harness_window()
{
  GHOST_GPUSettings gpu_settings = {};
  gpu_settings.context_type = GHOST_kDrawingContextTypeNone;
  return g_system->createWindow("blender-web ghost harness",
                                0,
                                0,
                                800,
                                600,
                                GHOST_kWindowStateNormal,
                                gpu_settings,
                                false,
                                false,
                                nullptr);
}

static void main_loop_tick()
{
  /* Top-level event pump: pull native (already-queued) events, dispatch to the
   * consumer. This is exactly where a suspend point is permitted per ADR-003. */
  if (g_system) {
    const int requested = g_requested_window_state.exchange(-1, std::memory_order_acq_rel);
    if (requested >= int(GHOST_kWindowStateNormal) &&
        requested <= int(GHOST_kWindowStateFullScreen))
    {
      const int result = g_window ? int(g_window->setState(GHOST_TWindowState(requested))) :
                                    int(GHOST_kFailure);
      g_window_state_result.store(result, std::memory_order_release);
    }
    const int requested_grab = g_requested_cursor_grab.exchange(-1, std::memory_order_acq_rel);
    if (requested_grab >= int(GHOST_kGrabDisable) && requested_grab <= int(GHOST_kGrabHide)) {
      const int result = g_window ?
                             int(g_window->setCursorGrab(GHOST_TGrabCursorMode(requested_grab),
                                                         GHOST_TAxisFlag(GHOST_kAxisX |
                                                                         GHOST_kAxisY),
                                                         nullptr,
                                                         nullptr)) :
                             int(GHOST_kFailure);
      g_cursor_grab_result.store(result, std::memory_order_release);
    }
    const int requested_custom_cursor =
        g_requested_custom_cursor.exchange(-1, std::memory_order_acq_rel);
    if (requested_custom_cursor >= 0 && requested_custom_cursor <= 5) {
      g_custom_cursor_result.store(int(run_custom_cursor_operation(requested_custom_cursor)),
                                   std::memory_order_release);
    }
    const int requested_clipboard =
        g_requested_clipboard_operation.exchange(-1, std::memory_order_acq_rel);
    if (requested_clipboard >= 0 && requested_clipboard <= 7) {
      g_clipboard_result.store(run_clipboard_operation(requested_clipboard) ?
                                   int(GHOST_kSuccess) : int(GHOST_kFailure),
                               std::memory_order_release);
    }
    const int requested_lifecycle =
        g_requested_window_lifecycle.exchange(-1, std::memory_order_acq_rel);
    if (requested_lifecycle == 0) {
      GHOST_IWindow *disposed_window = g_window;
      int result = 0;
      result |= (disposed_window != nullptr && g_system->activeWindow() == disposed_window) ?
                    (1 << 0) :
                    0;
      const GHOST_TSuccess disposed =
          disposed_window ? g_system->disposeWindow(disposed_window) : GHOST_kFailure;
      result |= disposed == GHOST_kSuccess ? (1 << 1) : 0;
      if (disposed == GHOST_kSuccess) {
        g_window = nullptr;
      }
      result |= g_system->activeWindow() == nullptr ? (1 << 2) : 0;
      result |= g_system->getWindowUnderCursor(0, 0) == nullptr ? (1 << 3) : 0;
      g_window_lifecycle_result.store(result, std::memory_order_release);
    }
    else if (requested_lifecycle == 1) {
      if (g_window == nullptr) {
        g_window = create_harness_window();
      }
      int result = 0;
      result |= g_window != nullptr ? (1 << 0) : 0;
      result |= (g_window != nullptr && g_system->activeWindow() == g_window) ? (1 << 1) : 0;
      result |= g_window != nullptr && g_system->getWindowUnderCursor(0, 0) == g_window ?
                    (1 << 2) :
                    0;
      g_window_lifecycle_result.store(result, std::memory_order_release);
    }
    else if (requested_lifecycle == 2) {
      int result = 0;
      if (g_window != nullptr) {
        GHOST_Rect bounds;
        g_window->getClientBounds(bounds);
        const auto hits_window = [&](const int32_t x, const int32_t y) {
          return g_system->getWindowUnderCursor(x, y) == g_window;
        };
        const auto hits_nothing = [&](const int32_t x, const int32_t y) {
          return g_system->getWindowUnderCursor(x, y) == nullptr;
        };
        result |= (!bounds.isEmpty() && g_system->activeWindow() == g_window) ? (1 << 0) : 0;
        result |= hits_window(bounds.l_, bounds.t_) ? (1 << 1) : 0;
        result |= hits_window(bounds.r_, bounds.b_) ? (1 << 2) : 0;
        result |= hits_window(bounds.l_ + bounds.getWidth() / 2,
                              bounds.t_ + bounds.getHeight() / 2) ?
                      (1 << 3) :
                      0;
        result |= hits_nothing(bounds.l_ - 1, bounds.t_) ? (1 << 4) : 0;
        result |= hits_nothing(bounds.l_, bounds.t_ - 1) ? (1 << 5) : 0;
        result |= hits_nothing(bounds.r_ + 1, bounds.b_) ? (1 << 6) : 0;
        result |= hits_nothing(bounds.r_, bounds.b_ + 1) ? (1 << 7) : 0;
      }
      g_window_lifecycle_result.store(result, std::memory_order_release);
    }
#ifdef WITH_INPUT_IME
    const int requested_ime = g_requested_ime_action.exchange(-1, std::memory_order_acq_rel);
    if (requested_ime == 0) {
      if (g_window) {
        g_window->beginIME(g_ime_x.load(std::memory_order_relaxed),
                           g_ime_y.load(std::memory_order_relaxed),
                           g_ime_w.load(std::memory_order_relaxed),
                           g_ime_h.load(std::memory_order_relaxed),
                           g_ime_completed.load(std::memory_order_relaxed) != 0);
        g_ime_result.store(int(GHOST_kSuccess), std::memory_order_release);
      }
      else {
        g_ime_result.store(int(GHOST_kFailure), std::memory_order_release);
      }
    }
    else if (requested_ime == 1) {
      if (g_window) {
        g_window->endIME();
        g_ime_result.store(int(GHOST_kSuccess), std::memory_order_release);
      }
      else {
        g_ime_result.store(int(GHOST_kFailure), std::memory_order_release);
      }
    }
#endif
    g_system->processEvents(false);
    g_system->dispatchEvents();
  }
}

int main()
{
  std::printf("GHOST-web harness: init\n");
  harness_log("[harness] init GHOST_SystemWeb on '#blender-canvas'");

  g_system = new GHOST_SystemWeb("#blender-canvas");
  if (g_system->init() != GHOST_kSuccess) {
    std::printf("GHOST-web harness: init FAILED\n");
    harness_log("[harness] init FAILED");
    return 1;
  }

  g_system->addEventConsumer(new LoggingConsumer());

  g_window = create_harness_window();
  if (!g_window) {
    harness_log("[harness] createWindow FAILED");
    return 1;
  }

  harness_log("[harness] window created; move/click/scroll/type over the canvas.");
  std::printf("GHOST-web harness: ready\n");

  emscripten_set_main_loop(main_loop_tick, 0, 1);
  return 0;
}
