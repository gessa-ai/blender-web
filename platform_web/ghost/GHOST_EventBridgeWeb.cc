/* SPDX-FileCopyrightText: 2011-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from the event-translation halves of
 * intern/ghost/intern/GHOST_SystemSDL.cc / GHOST_SystemX11.cc @ fbe6228777e7. */

/** \file
 * \ingroup GHOST-web
 * Implementation of GHOST_EventBridgeWeb (HTML5 event -> GHOST event translation). */

#include "GHOST_EventBridgeWeb.hh"

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <limits>
#include <memory>
#include <utility>

#include "GHOST_SystemWeb.hh"
#include "GHOST_WebDisplayState.hh"
#include "GHOST_WindowWeb.hh"

#include "GHOST_IMEQueueWeb.hh"

#include "GHOST_Buttons.hh"
#include "GHOST_EventButton.hh"
#include "GHOST_EventCursor.hh"
#include "GHOST_EventKey.hh"
#include "GHOST_EventWheel.hh"
#include "GHOST_WindowManager.hh"

#include "GHOST_KeyMapWeb.hh"

namespace ghost_web_bridge {

#ifdef WITH_INPUT_IME

namespace {

constexpr int32_t IME_TEXT_LIMIT = 16 * 1024 * 1024;

using ghost_web::ime::Message;
using ghost_web::ime::MessageKind;
using ghost_web::ime::MessageQueue;
using ghost_web::ime::PublishResult;

MessageQueue g_ime_queue;
std::atomic<uint64_t> g_ime_recovered{0};

class GHOST_EventIMEWeb : public GHOST_Event {
 private:
  GHOST_TEventImeData event_ime_data_;

 public:
  GHOST_EventIMEWeb(uint64_t msec,
                    GHOST_TEventType type,
                    GHOST_IWindow *window,
                    GHOST_TEventImeData data)
      : GHOST_Event(msec, type, window), event_ime_data_(std::move(data))
  {
    /* Own the strings until the event manager has dispatched this event. */
    data_ = &event_ime_data_;
  }
};

bool valid_ime_message(const int32_t kind,
                       const int32_t text_length,
                       const int cursor_position,
                       const int target_start,
                       const int target_end)
{
  return kind >= int32_t(MessageKind::Start) && kind <= int32_t(MessageKind::End) &&
         text_length >= 0 && text_length <= IME_TEXT_LIMIT && cursor_position >= -1 &&
         target_start >= -1 && target_end >= -1 &&
         (target_start == -1 || target_end == -1 || target_start <= target_end);
}

}  // namespace

extern "C" EMSCRIPTEN_KEEPALIVE int bw_shell_ime_publish(const int32_t kind,
                                                           const char *text,
                                                           const int32_t text_length,
                                                           const int cursor_position,
                                                           const int target_start,
                                                           const int target_end)
{
  if (!valid_ime_message(kind, text_length, cursor_position, target_start, target_end) ||
      (text_length != 0 && text == nullptr))
  {
    g_ime_queue.reject();
    return 0;
  }

  return g_ime_queue.publish(MessageKind(kind),
                             text,
                             size_t(text_length),
                             cursor_position,
                             target_start,
                             target_end) == PublishResult::Accepted ?
             1 :
             0;
}

extern "C" EMSCRIPTEN_KEEPALIVE int bw_shell_ime_cancel()
{
  if (g_ime_queue.cancel() != PublishResult::Accepted) {
    return 0;
  }
  g_ime_recovered.fetch_add(1, std::memory_order_relaxed);
  return 1;
}

extern "C" EMSCRIPTEN_KEEPALIVE double bw_shell_ime_published_count()
{
  return double(g_ime_queue.published_count());
}

extern "C" EMSCRIPTEN_KEEPALIVE double bw_shell_ime_consumed_count()
{
  return double(g_ime_queue.consumed_count());
}

extern "C" EMSCRIPTEN_KEEPALIVE double bw_shell_ime_dropped_count()
{
  return double(g_ime_queue.dropped_count());
}

extern "C" EMSCRIPTEN_KEEPALIVE double bw_shell_ime_recovered_count()
{
  return double(g_ime_recovered.load(std::memory_order_relaxed));
}

void set_ime_enabled(const bool enabled)
{
  g_ime_queue.set_enabled(enabled);
}

void poll_ime(GHOST_SystemWeb &sys)
{
  Message message;
  while (g_ime_queue.consume(message)) {
    GHOST_TEventImeData data;
    data.cursor_position = message.cursor_position;
    data.target_start = message.target_start;
    data.target_end = message.target_end;

    GHOST_TEventType event_type = GHOST_kEventImeComposition;
    switch (message.kind) {
      case MessageKind::Start:
        event_type = GHOST_kEventImeCompositionStart;
        data.composite = std::move(message.text);
        break;
      case MessageKind::Update:
        data.composite = std::move(message.text);
        break;
      case MessageKind::Commit:
        data.result = std::move(message.text);
        data.cursor_position = -1;
        data.target_start = -1;
        data.target_end = -1;
        break;
      case MessageKind::End:
        event_type = GHOST_kEventImeCompositionEnd;
        data.cursor_position = -1;
        data.target_start = -1;
        data.target_end = -1;
        break;
    }

    sys.pushEvent(std::make_unique<GHOST_EventIMEWeb>(
        sys.getMilliSeconds(), event_type, sys.activeWindow(), std::move(data)));
  }
}

#endif /* WITH_INPUT_IME */

GHOST_TButton button_from_dom(unsigned short dom_button)
{
  switch (dom_button) {
    case 0:
      return GHOST_kButtonMaskLeft;
    case 1:
      return GHOST_kButtonMaskMiddle;
    case 2:
      return GHOST_kButtonMaskRight;
    case 3:
      return GHOST_kButtonMaskButton4;
    case 4:
      return GHOST_kButtonMaskButton5;
    default:
      return GHOST_kButtonMaskNone;
  }
}

void on_mouse_move(GHOST_SystemWeb &sys, const EmscriptenMouseEvent &e)
{
  sys.noteModifierFlags(e.ctrlKey, e.shiftKey, e.altKey, e.metaKey);
  GHOST_WindowWeb *win = sys.activeWindow();
  int32_t x = e.targetX;
  int32_t y = e.targetY;
  if (win != nullptr && win->isPointerLockActive()) {
    /* Pointer Lock freezes DOM absolute coordinates and reports motion only as
     * movementX/Y. Preserve GHOST's desktop contract by accumulating a virtual,
     * unbounded cursor position for Wrap/Hide grabs. Saturation avoids signed
     * overflow during an exceptionally long continuous session. */
    int32_t previous_x = 0;
    int32_t previous_y = 0;
    if (sys.getCursorPosition(previous_x, previous_y) == GHOST_kSuccess) {
      const auto add_motion = [](const int32_t previous, const int movement) {
        const int64_t sum = int64_t(previous) + int64_t(movement);
        return int32_t(std::clamp(sum,
                                  int64_t(std::numeric_limits<int32_t>::min()),
                                  int64_t(std::numeric_limits<int32_t>::max())));
      };
      x = add_motion(previous_x, e.movementX);
      y = add_motion(previous_y, e.movementY);
    }
  }
  sys.noteCursor(x, y);
  sys.requestInputRedrawRetry();
  sys.pushEvent(std::make_unique<GHOST_EventCursor>(
      sys.getMilliSeconds(), GHOST_kEventCursorMove, win, x, y, GHOST_TABLET_DATA_NONE));
}

void on_mouse_button(GHOST_SystemWeb &sys, int em_event_type, const EmscriptenMouseEvent &e)
{
  sys.noteModifierFlags(e.ctrlKey, e.shiftKey, e.altKey, e.metaKey);
  /* Cursor position is owned by the ordered mouse-move stream. With
   * PROXY_TO_PTHREAD, several DOM button events can wait behind one worker
   * turn while Emscripten's event storage advances; re-caching targetX/Y here
   * can roll the correct move position backward to another queued click. */
  const GHOST_TButton button = button_from_dom(e.button);
  if (button == GHOST_kButtonMaskNone) {
    return;
  }
  const bool down = (em_event_type == EMSCRIPTEN_EVENT_MOUSEDOWN);
  sys.noteButton(button, down);
  sys.requestInputRedrawRetry();
  GHOST_IWindow *win = sys.activeWindow();
  sys.pushEvent(std::make_unique<GHOST_EventButton>(
      sys.getMilliSeconds(),
      down ? GHOST_kEventButtonDown : GHOST_kEventButtonUp,
      win,
      button,
      GHOST_TABLET_DATA_NONE));
}

void on_wheel(GHOST_SystemWeb &sys, const EmscriptenWheelEvent &e)
{
  sys.noteModifierFlags(e.mouse.ctrlKey, e.mouse.shiftKey, e.mouse.altKey, e.mouse.metaKey);
  sys.noteCursor(e.mouse.targetX, e.mouse.targetY);
  GHOST_IWindow *win = sys.activeWindow();
  const uint64_t t = sys.getMilliSeconds();

  if (e.deltaY == 0.0 && e.deltaX == 0.0) {
    return;
  }
  sys.requestInputRedrawRetry();

  /* DOM deltaY > 0 means scrolling DOWN; GHOST wheel value is +1 for up. Emit one
   * discrete step per event (Blender treats wheel value as notches, not pixels). */
  if (e.deltaY != 0.0) {
    sys.pushEvent(std::make_unique<GHOST_EventWheel>(
        t, win, GHOST_kEventWheelAxisVertical, e.deltaY > 0.0 ? -1 : 1));
  }
  if (e.deltaX != 0.0) {
    sys.pushEvent(std::make_unique<GHOST_EventWheel>(
        t, win, GHOST_kEventWheelAxisHorizontal, e.deltaX > 0.0 ? 1 : -1));
  }
}

void on_key(GHOST_SystemWeb &sys, int em_event_type, const EmscriptenKeyboardEvent &e)
{
  const bool down = (em_event_type == EMSCRIPTEN_EVENT_KEYDOWN);
  const GHOST_TKey key = ghost_web_key_from_code(e.code);
  ghost_web::note_input_key(down);
  /* `code` preserves the physical left/right modifier side. Publish that exact
   * transition before reconciling the aggregate DOM flags so a first right-side
   * press cannot be mistaken for the left-side fallback. */
  sys.noteModifierKey(key, down);
  sys.noteModifierFlags(e.ctrlKey, e.shiftKey, e.altKey, e.metaKey);
  sys.requestInputRedrawRetry();
  GHOST_IWindow *win = sys.activeWindow();

  char utf8[6] = {0};
  if (down) {
    ghost_web_utf8_from_key(e.key, utf8);
  }
  sys.pushEvent(std::make_unique<GHOST_EventKey>(
      sys.getMilliSeconds(),
      down ? GHOST_kEventKeyDown : GHOST_kEventKeyUp,
      win,
      key,
      e.repeat,
      utf8));
}

void on_resize(GHOST_SystemWeb &sys, const EmscriptenUiEvent & /*e*/)
{
  GHOST_WindowWeb *win = sys.activeWindow();
  /* Keep the WebGPU surface matched to the (possibly shell-resized) canvas before the
   * WM sees the size event, so the very next composite presents at the live extent. */
  if (win != nullptr) {
    win->reconfigureSurface();
  }
  sys.pushEvent(std::make_unique<GHOST_Event>(sys.getMilliSeconds(), GHOST_kEventWindowSize, win));
}

void on_focus(GHOST_SystemWeb &sys, bool focused)
{
  GHOST_WindowWeb *win = sys.activeWindow();
  if (GHOST_WindowManager *window_manager = sys.getWindowManager()) {
    if (focused) {
      window_manager->setActiveWindow(win);
    }
    else {
      window_manager->setWindowInactive(win);
    }
  }
  if (!focused) {
    if (win != nullptr) {
      win->releasePointerLock();
    }
    /* A tab switch, browser-window blur, or programmatic focus move is not
     * required to deliver matching key-up/mouse-up events. Retire GHOST's
     * physical state before WindowDeactivate is dispatched: Blender handles
     * that event by querying GHOST and synthesizing releases for modifiers that
     * are no longer held. Mouse buttons have no equivalent WM reconciliation,
     * so publish their releases explicitly before the deactivate event. */
    GHOST_Buttons held_buttons;
    const bool have_buttons = sys.getButtons(held_buttons) == GHOST_kSuccess;
    const uint64_t time = sys.getMilliSeconds();
    constexpr std::array<GHOST_TButton, 7> buttons = {
        GHOST_kButtonMaskLeft,
        GHOST_kButtonMaskMiddle,
        GHOST_kButtonMaskRight,
        GHOST_kButtonMaskButton4,
        GHOST_kButtonMaskButton5,
        GHOST_kButtonMaskButton6,
        GHOST_kButtonMaskButton7,
    };
    for (const GHOST_TButton button : buttons) {
      const bool was_held = have_buttons && held_buttons.get(button);
      sys.noteButton(button, false);
      if (was_held && win != nullptr) {
        sys.pushEvent(std::make_unique<GHOST_EventButton>(time,
                                                          GHOST_kEventButtonUp,
                                                          win,
                                                          button,
                                                          GHOST_TABLET_DATA_NONE));
      }
    }
    sys.noteModifierFlags(false, false, false, false);
  }
  sys.pushEvent(std::make_unique<GHOST_Event>(
      sys.getMilliSeconds(),
      focused ? GHOST_kEventWindowActivate : GHOST_kEventWindowDeactivate,
      win));
}

}  // namespace ghost_web_bridge
