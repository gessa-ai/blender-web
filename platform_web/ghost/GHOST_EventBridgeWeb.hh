/* SPDX-FileCopyrightText: 2011-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from the event-translation halves of
 * intern/ghost/intern/GHOST_SystemSDL.cc / GHOST_SystemX11.cc @ fbe6228777e7. */

/** \file
 * \ingroup GHOST-web
 *
 * GHOST_EventBridgeWeb — the pure translation layer between Emscripten HTML5 input
 * events and GHOST events. These free functions take an Emscripten event struct,
 * build the matching GHOST_Event*, update the system's tracked input state, and
 * enqueue the event via GHOST_System::pushEvent(). They contain NO platform
 * registration or lifetime logic — that lives in GHOST_SystemWeb.
 */

#pragma once

#include <emscripten/html5.h>

#include "GHOST_Types.hh"

class GHOST_SystemWeb;

namespace ghost_web_bridge {

/** DOM MouseEvent.button (0=left,1=middle,2=right,3=back,4=forward) -> GHOST_TButton. */
GHOST_TButton button_from_dom(unsigned short dom_button);

/** #GHOST_kEventCursorMove from a mousemove event (canvas-relative coords). */
void on_mouse_move(GHOST_SystemWeb &sys, const EmscriptenMouseEvent &e);

/** #GHOST_kEventButtonDown / #GHOST_kEventButtonUp.
 * \param em_event_type: EMSCRIPTEN_EVENT_MOUSEDOWN or EMSCRIPTEN_EVENT_MOUSEUP. */
void on_mouse_button(GHOST_SystemWeb &sys, int em_event_type, const EmscriptenMouseEvent &e);

/** #GHOST_kEventWheel (vertical + horizontal), one discrete step per notch. */
void on_wheel(GHOST_SystemWeb &sys, const EmscriptenWheelEvent &e);

/** #GHOST_kEventKeyDown / #GHOST_kEventKeyUp (code->GHOST_TKey + utf8 from key).
 * \param em_event_type: EMSCRIPTEN_EVENT_KEYDOWN or EMSCRIPTEN_EVENT_KEYUP. */
void on_key(GHOST_SystemWeb &sys, int em_event_type, const EmscriptenKeyboardEvent &e);

/** #GHOST_kEventWindowSize from a browser resize (canvas is ressynced by the system). */
void on_resize(GHOST_SystemWeb &sys, const EmscriptenUiEvent &e);

/** #GHOST_kEventWindowActivate / #GHOST_kEventWindowDeactivate from focus/blur. */
void on_focus(GHOST_SystemWeb &sys, bool focused);

#ifdef WITH_INPUT_IME
/** Enable or disable acceptance of browser-main composition events. */
void set_ime_enabled(bool enabled);

/** Drain browser-main composition events into the WM worker's GHOST queue. */
void poll_ime(GHOST_SystemWeb &sys);
#endif

}  // namespace ghost_web_bridge
