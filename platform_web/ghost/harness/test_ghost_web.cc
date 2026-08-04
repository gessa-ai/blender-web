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
 * Single-threaded on purpose (no -pthread / PROXY_TO_PTHREAD): this isolates the
 * event-bridge + GHOST integration from the threading topology. The proxied
 * main-loop design for the real Blender build is documented (citing ADR-003) in
 * notes/ghost-web-design.md and is validated at the M4 gate, not here.
 */

#include <cstdio>
#include <memory>

#include <emscripten/emscripten.h>
#include <emscripten/html5.h>

#include "GHOST_SystemWeb.hh"
#include "GHOST_WindowWeb.hh"

#include "GHOST_Event.hh"
#include "GHOST_IEventConsumer.hh"
#include "GHOST_Types.hh"

/* Append a line to the on-page log (and it also goes to the console via printf). */
EM_JS(void, harness_log, (const char *msg), {
  const s = UTF8ToString(msg);
  if (typeof globalThis.ghostLog === 'function') {
    globalThis.ghostLog(s);
  }
});

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

static void main_loop_tick()
{
  /* Top-level event pump: pull native (already-queued) events, dispatch to the
   * consumer. This is exactly where a suspend point is permitted per ADR-003. */
  if (g_system) {
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
  GHOST_IWindow *win = g_system->createWindow(
      "blender-web ghost harness", 0, 0, 800, 600, GHOST_kWindowStateNormal, gpu_settings,
      false, false, nullptr);
  if (!win) {
    harness_log("[harness] createWindow FAILED");
    return 1;
  }

  harness_log("[harness] window created; move/click/scroll/type over the canvas.");
  std::printf("GHOST-web harness: ready\n");

  emscripten_set_main_loop(main_loop_tick, 0, 1);
  return 0;
}
