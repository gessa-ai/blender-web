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

#include <memory>

#include "GHOST_SystemWeb.hh"
#include "GHOST_WindowWeb.hh"

#include "GHOST_EventButton.hh"
#include "GHOST_EventCursor.hh"
#include "GHOST_EventKey.hh"
#include "GHOST_EventWheel.hh"

#include "GHOST_KeyMapWeb.hh"

namespace ghost_web_bridge {

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
  sys.noteCursor(e.targetX, e.targetY);
  GHOST_IWindow *win = sys.activeWindow();
  sys.pushEvent(std::make_unique<GHOST_EventCursor>(
      sys.getMilliSeconds(), GHOST_kEventCursorMove, win, e.targetX, e.targetY,
      GHOST_TABLET_DATA_NONE));
}

void on_mouse_button(GHOST_SystemWeb &sys, int em_event_type, const EmscriptenMouseEvent &e)
{
  sys.noteModifierFlags(e.ctrlKey, e.shiftKey, e.altKey, e.metaKey);
  sys.noteCursor(e.targetX, e.targetY);
  const GHOST_TButton button = button_from_dom(e.button);
  if (button == GHOST_kButtonMaskNone) {
    return;
  }
  const bool down = (em_event_type == EMSCRIPTEN_EVENT_MOUSEDOWN);
  sys.noteButton(button, down);
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
  sys.noteModifierFlags(e.ctrlKey, e.shiftKey, e.altKey, e.metaKey);
  const bool down = (em_event_type == EMSCRIPTEN_EVENT_KEYDOWN);
  const GHOST_TKey key = ghost_web_key_from_code(e.code);
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
  GHOST_IWindow *win = sys.activeWindow();
  sys.pushEvent(std::make_unique<GHOST_Event>(sys.getMilliSeconds(), GHOST_kEventWindowSize, win));
}

void on_focus(GHOST_SystemWeb &sys, bool focused)
{
  GHOST_IWindow *win = sys.activeWindow();
  sys.pushEvent(std::make_unique<GHOST_Event>(
      sys.getMilliSeconds(),
      focused ? GHOST_kEventWindowActivate : GHOST_kEventWindowDeactivate,
      win));
}

}  // namespace ghost_web_bridge
