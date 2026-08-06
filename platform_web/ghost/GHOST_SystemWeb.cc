/* SPDX-FileCopyrightText: 2011-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from intern/ghost/intern/GHOST_SystemHeadless.hh and
 * GHOST_SystemSDL.cc @ fbe6228777e7. */

/** \file
 * \ingroup GHOST-web
 * Implementation of GHOST_SystemWeb (Emscripten HTML5 platform back-end). */

#include "GHOST_SystemWeb.hh"

#include <emscripten/emscripten.h>
#include <emscripten/html5.h>

#include "GHOST_EventBridgeWeb.hh"
#include "GHOST_WindowWeb.hh"

#include "GHOST_Buttons.hh"
#include "GHOST_Event.hh"
#include "GHOST_EventManager.hh"
#include "GHOST_ModifierKeys.hh"
#include "GHOST_WindowManager.hh"

#include <memory>

#ifdef WITH_WEBGPU_BACKEND
/* M4 T4 selection seam (see GHOST_WindowWeb.cc). */
#  ifdef __EMSCRIPTEN__
#    include "GHOST_ContextWGPUWeb.hh"
#  else
#    include "GHOST_ContextWGPU.hh"
#  endif
#endif
#include "GHOST_ContextNone.hh"

/* -------------------------------------------------------------------------- */
/* HTML5 -> bridge callback thunks. `userData` is the GHOST_SystemWeb*. Returning
 * true marks the DOM event as consumed (preventDefault), which is what Blender
 * wants for input over its canvas. */

namespace {

bool cb_mousemove(int /*t*/, const EmscriptenMouseEvent *e, void *ud)
{
  ghost_web_bridge::on_mouse_move(*static_cast<GHOST_SystemWeb *>(ud), *e);
  return true;
}
bool cb_mousebtn(int t, const EmscriptenMouseEvent *e, void *ud)
{
  ghost_web_bridge::on_mouse_button(*static_cast<GHOST_SystemWeb *>(ud), t, *e);
  return true;
}
bool cb_wheel(int /*t*/, const EmscriptenWheelEvent *e, void *ud)
{
  ghost_web_bridge::on_wheel(*static_cast<GHOST_SystemWeb *>(ud), *e);
  return true;
}
bool cb_key(int t, const EmscriptenKeyboardEvent *e, void *ud)
{
  ghost_web_bridge::on_key(*static_cast<GHOST_SystemWeb *>(ud), t, *e);
  return true;
}
bool cb_resize(int /*t*/, const EmscriptenUiEvent *e, void *ud)
{
  ghost_web_bridge::on_resize(*static_cast<GHOST_SystemWeb *>(ud), *e);
  return true;
}
bool cb_focus(int /*t*/, const EmscriptenFocusEvent * /*e*/, void *ud)
{
  ghost_web_bridge::on_focus(*static_cast<GHOST_SystemWeb *>(ud), true);
  return true;
}
bool cb_blur(int /*t*/, const EmscriptenFocusEvent * /*e*/, void *ud)
{
  ghost_web_bridge::on_focus(*static_cast<GHOST_SystemWeb *>(ud), false);
  return true;
}
bool cb_contextmenu(int /*t*/, const EmscriptenMouseEvent * /*e*/, void * /*ud*/)
{
  /* Swallow the browser context menu so right-drag works. */
  return true;
}

}  // namespace

/* -------------------------------------------------------------------------- */

GHOST_SystemWeb::GHOST_SystemWeb(const char *canvas_selector)
    : canvas_selector_(canvas_selector ? canvas_selector : "#canvas")
{
}

GHOST_SystemWeb::~GHOST_SystemWeb() = default;

GHOST_TSuccess GHOST_SystemWeb::init()
{
  const GHOST_TSuccess success = GHOST_System::init();
  /* Input callbacks are registered in createWindow(), once the canvas + window
   * exist. (Nothing to pump before then.) */
  return success;
}

void GHOST_SystemWeb::registerCanvasCallbacks()
{
  const char *canvas = canvas_selector_.c_str();
  const char *win = EMSCRIPTEN_EVENT_TARGET_WINDOW;

  /* Pointer + wheel on the canvas element (targetX/Y are canvas-relative). */
  emscripten_set_mousemove_callback(canvas, this, false, cb_mousemove);
  emscripten_set_mousedown_callback(canvas, this, false, cb_mousebtn);
  emscripten_set_mouseup_callback(canvas, this, false, cb_mousebtn);
  emscripten_set_wheel_callback(canvas, this, false, cb_wheel);
  emscripten_set_contextmenu_callback(canvas, this, false, cb_contextmenu);
  emscripten_set_focus_callback(canvas, this, false, cb_focus);
  emscripten_set_blur_callback(canvas, this, false, cb_blur);

  /* Keyboard + resize at window scope (keyboard has no per-element target without
   * focus juggling; resize is a window event). */
  emscripten_set_keydown_callback(win, this, false, cb_key);
  emscripten_set_keyup_callback(win, this, false, cb_key);
  emscripten_set_resize_callback(win, this, false, cb_resize);
}

bool GHOST_SystemWeb::processEvents(bool /*waitForEvent*/)
{
  /* Browser input arrives asynchronously via the HTML5 callbacks, which enqueue
   * GHOST events immediately. We cannot block the browser main thread, so
   * waitForEvent is ignored; report whether anything is queued for dispatch. */
  GHOST_EventManager *em = getEventManager();
  return (em != nullptr) && (em->getNumEvents() > 0);
}

GHOST_TSuccess GHOST_SystemWeb::getModifierKeys(GHOST_ModifierKeys &keys) const
{
  /* DOM modifier flags don't distinguish left/right — report left variants. Key
   * events themselves carry the correct left/right GHOST key (via `code`). */
  keys.set(GHOST_kModifierKeyLeftShift, mod_shift_);
  keys.set(GHOST_kModifierKeyRightShift, false);
  keys.set(GHOST_kModifierKeyLeftControl, mod_ctrl_);
  keys.set(GHOST_kModifierKeyRightControl, false);
  keys.set(GHOST_kModifierKeyLeftAlt, mod_alt_);
  keys.set(GHOST_kModifierKeyRightAlt, false);
  keys.set(GHOST_kModifierKeyLeftOS, mod_meta_);
  keys.set(GHOST_kModifierKeyRightOS, false);
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_SystemWeb::getButtons(GHOST_Buttons &buttons) const
{
  buttons = buttons_;
  return GHOST_kSuccess;
}

GHOST_TCapabilityFlag GHOST_SystemWeb::getCapabilities() const
{
  /* Advertise input + windowing, mask the affordances a sandboxed canvas can't do.
   * Same posture as GHOST_SystemHeadless's mask (cursor warp, primary/image
   * clipboard, desktop sampling, IME, decoration styles, hyper key, RGBA/generated
   * cursors, multi-monitor placement, window path) plus WindowPosition (a canvas
   * has no OS-level position). IME is a documented deferral. */
  return GHOST_TCapabilityFlag(
      GHOST_CAPABILITY_FLAG_ALL &
      ~(GHOST_kCapabilityWindowPosition | GHOST_kCapabilityCursorWarp |
        GHOST_kCapabilityClipboardPrimary | GHOST_kCapabilityClipboardImage |
        GHOST_kCapabilityDesktopSample | GHOST_kCapabilityInputIME |
        GHOST_kCapabilityWindowDecorationStyles | GHOST_kCapabilityKeyboardHyperKey |
        GHOST_kCapabilityCursorRGBA | GHOST_kCapabilityCursorGenerator |
        GHOST_kCapabilityMultiMonitorPlacement | GHOST_kCapabilityWindowPath));
}

char *GHOST_SystemWeb::getClipboard(bool /*selection*/) const
{
  /* The async Clipboard API can't satisfy GHOST's synchronous contract on the main
   * thread; wired up as a worker-side shim in a later milestone. */
  return nullptr;
}

void GHOST_SystemWeb::putClipboard(const char * /*buffer*/, bool /*selection*/) const
{
  /* See getClipboard(): deferred. */
}

uint64_t GHOST_SystemWeb::getMilliSeconds() const
{
  return uint64_t(emscripten_get_now());
}

GHOST_TSuccess GHOST_SystemWeb::getCursorPosition(int32_t &x, int32_t &y) const
{
  x = cursor_x_;
  y = cursor_y_;
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_SystemWeb::setCursorPosition(int32_t /*x*/, int32_t /*y*/)
{
  /* Cursor warp needs the Pointer Lock API (relative mode) — deferred; we don't
   * advertise GHOST_kCapabilityCursorWarp. */
  return GHOST_kFailure;
}

void GHOST_SystemWeb::getMainDisplayDimensions(uint32_t &width, uint32_t &height) const
{
  int w = 0, h = 0;
  emscripten_get_screen_size(&w, &h);
  width = uint32_t(w);
  height = uint32_t(h);
}

void GHOST_SystemWeb::getAllDisplayDimensions(uint32_t &width, uint32_t &height) const
{
  getMainDisplayDimensions(width, height);
}

GHOST_IContext *GHOST_SystemWeb::createOffscreenContext(GHOST_GPUSettings gpu_settings)
{
#ifdef WITH_WEBGPU_BACKEND
  const GHOST_ContextParams params = GHOST_CONTEXT_PARAMS_FROM_GPU_SETTINGS_OFFSCREEN(gpu_settings);
  if (gpu_settings.context_type == GHOST_kDrawingContextTypeWebGPU) {
#  ifdef __EMSCRIPTEN__
    /* Device pre-acquired by the startup await (notes/m4-integration.md). */
    GHOST_Context *context = new GHOST_ContextWGPUWeb(params, canvas_selector_.c_str());
#  else
    GHOST_Context *context = new GHOST_ContextWGPU(params);
#  endif
    if (context->initializeDrawingContext()) {
      return context;
    }
    delete context;
  }
#else
  (void)gpu_settings;
#endif
  return nullptr;
}

GHOST_TSuccess GHOST_SystemWeb::disposeContext(GHOST_IContext *context)
{
  delete context;
  return GHOST_kSuccess;
}

GHOST_IWindow *GHOST_SystemWeb::createWindow(const char *title,
                                             int32_t left,
                                             int32_t top,
                                             uint32_t width,
                                             uint32_t height,
                                             GHOST_TWindowState state,
                                             GHOST_GPUSettings gpu_settings,
                                             const bool /*exclusive*/,
                                             const bool /*is_dialog*/,
                                             const GHOST_IWindow *parent_window)
{
  const GHOST_ContextParams context_params = GHOST_CONTEXT_PARAMS_FROM_GPU_SETTINGS(gpu_settings);
  GHOST_WindowWeb *window = new GHOST_WindowWeb(title,
                                                left,
                                                top,
                                                width,
                                                height,
                                                state,
                                                parent_window,
                                                gpu_settings.context_type,
                                                context_params,
                                                canvas_selector_.c_str());
  if (window_ == nullptr) {
    window_ = window;
    /* Bind HTML5 input to this (first) window's canvas. */
    canvas_selector_ = window->getCanvasSelector();
    registerCanvasCallbacks();
  }
  if (GHOST_WindowManager *wm = getWindowManager()) {
    wm->addWindow(window);
  }
  /* Deliver an initial size/expose event, exactly as the native back-ends do when a
   * window is first mapped (SDL posts SDL_WINDOWEVENT_EXPOSED/SIZE_CHANGED; X11 posts
   * MapNotify + ConfigureNotify) — that first event is what makes Blender's WM build the
   * drawable and paint frame one. GHOST_WindowWeb posted none, so at idle WM_main had no
   * pending redraw and the canvas stayed black until the first mouse move happened to
   * force a refresh (which only then reconciled the real client bounds). Posting the
   * window-size event here makes the first composite happen unprompted and deterministic
   * — a prerequisite for a headless golden capture, which would otherwise see black. */
  pushEvent(std::make_unique<GHOST_Event>(getMilliSeconds(), GHOST_kEventWindowSize, window));
  return window;
}

GHOST_IWindow *GHOST_SystemWeb::getWindowUnderCursor(int32_t /*x*/, int32_t /*y*/)
{
  return window_;
}
