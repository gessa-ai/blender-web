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
#include "GHOST_IEventConsumer.hh"
#include "GHOST_Types.hh"

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
    default:
      return "Other";
  }
}

/** Logs each GHOST event's decoded payload — the harness's proof surface. */
class LoggingConsumer : public GHOST_IEventConsumer {
 public:
  bool processEvent(const GHOST_IEvent *event) override
  {
    char line[256];
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
static std::atomic<int> g_requested_clipboard_operation{-1};
static std::atomic<int> g_clipboard_result{-2};

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
    const int requested_clipboard =
        g_requested_clipboard_operation.exchange(-1, std::memory_order_acq_rel);
    if (requested_clipboard >= 0 && requested_clipboard <= 7) {
      g_clipboard_result.store(run_clipboard_operation(requested_clipboard) ?
                                   int(GHOST_kSuccess) : int(GHOST_kFailure),
                               std::memory_order_release);
    }
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

  GHOST_GPUSettings gpu_settings = {};
  gpu_settings.context_type = GHOST_kDrawingContextTypeNone;
  g_window = g_system->createWindow(
      "blender-web ghost harness", 0, 0, 800, 600, GHOST_kWindowStateNormal, gpu_settings,
      false, false, nullptr);
  if (!g_window) {
    harness_log("[harness] createWindow FAILED");
    return 1;
  }

  harness_log("[harness] window created; move/click/scroll/type over the canvas.");
  std::printf("GHOST-web harness: ready\n");

  emscripten_set_main_loop(main_loop_tick, 0, 1);
  return 0;
}
