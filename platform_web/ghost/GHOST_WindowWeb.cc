/* SPDX-FileCopyrightText: 2011-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from intern/ghost/intern/GHOST_WindowNULL.hh and
 * GHOST_WindowSDL.cc @ fbe6228777e7. */

/** \file
 * \ingroup GHOST-web
 * Implementation of GHOST_WindowWeb (HTML5 <canvas> backed window). */

#include "GHOST_WindowWeb.hh"

#include <emscripten/emscripten.h>
#include <emscripten/html5.h>

#ifdef WITH_WEBGPU_BACKEND
/* M4 T4 selection seam: emdawnwebgpu (browser) vs native Dawn are different link
 * targets (different webgpu.h/surface/wait model — wgpu-context note deltas). */
#  ifdef __EMSCRIPTEN__
#    include "GHOST_ContextWGPUWeb.hh"
#  else
#    include "GHOST_ContextWGPU.hh"
#  endif
#endif

/* Read window.devicePixelRatio without pulling in a JS library dependency. Under
 * -sPROXY_TO_PTHREAD this runs on the WM worker, which has NO `window`/`document`
 * (they exist only on the browser main thread) — guard both, or a bare `window`
 * reference throws ReferenceError and aborts the boot. DPR defaults to 1.0 on the
 * worker (a later refinement can forward the real DPR from the main thread); the
 * title update is a main-thread-only affordance, so it no-ops on the worker. */
EM_JS(double, ghost_web_device_pixel_ratio, (), {
  return (typeof window !== "undefined" && window.devicePixelRatio) ? window.devicePixelRatio : 1.0;
});
EM_JS(void, ghost_web_set_document_title, (const char *title), {
  if (typeof document !== "undefined") {
    document.title = UTF8ToString(title);
  }
});

GHOST_WindowWeb::GHOST_WindowWeb(const char *title,
                                 int32_t /*left*/,
                                 int32_t /*top*/,
                                 uint32_t width,
                                 uint32_t height,
                                 GHOST_TWindowState state,
                                 const GHOST_IWindow * /*parent_window*/,
                                 GHOST_TDrawingContextType type,
                                 const GHOST_ContextParams &context_params,
                                 const char *canvas_selector)
    : GHOST_Window(width, height, state, context_params, false),
      canvas_selector_(canvas_selector ? canvas_selector : "#canvas"),
      title_(title ? title : ""),
      context_params_web_(context_params)
{
  /* In the browser the HTML <canvas> owns its own backing-store dimensions — a canvas has
   * no OS window to derive a size from, so the shell sizes it deliberately and the M4
   * first-pixels golden is captured at exactly that size. ADOPT the canvas's existing
   * extent as the window client size (getClientBounds reads it back) instead of
   * overwriting it with the WM's requested size, which is display-derived
   * (emscripten_get_screen_size — e.g. 1800x1169 on this host) and would blow the capture
   * past the golden's 1280x720. Only size the canvas from the requested extents as a
   * fallback, when the shell left it unsized. The initial GHOST_kEventWindowSize +
   * heartbeat expose (GHOST_SystemWeb) then reconcile Blender's layout to the canvas. */
  {
    int cw = 0, ch = 0;
    emscripten_get_canvas_element_size(canvas_selector_.c_str(), &cw, &ch);
    if (cw <= 0 || ch <= 0) {
      emscripten_set_canvas_element_size(canvas_selector_.c_str(), int(width), int(height));
    }
  }

  /* Create + initialize the window's drawing context. Native GHOST window ctors
   * (GHOST_WindowSDL/Win32/X11/Wayland) all call setDrawingContextType(type) here;
   * GHOST_WindowWeb previously dropped the `type` param, so the base GHOST_Window kept
   * its default GHOST_ContextNone and the WebGPU context (GHOST_ContextWGPUWeb) was
   * never created. GPU_context_create(ghost_window, nullptr) → WGPUBackend::context_alloc
   * → ghost_window->getDrawingContext() then handed the WGPUContext ctor that
   * GHOST_ContextNone, whose uninitialized instance_ slot is garbage (misaligned) → the
   * first wgpuInstanceAddRef trapped. setDrawingContextType() → newDrawingContext(type)
   * → GHOST_ContextWGPUWeb::initializeDrawingContext(). */
  setDrawingContextType(type);
}

void GHOST_WindowWeb::setTitle(const char *title)
{
  title_ = title ? title : "";
  ghost_web_set_document_title(title_.c_str());
}

std::string GHOST_WindowWeb::getTitle() const
{
  return title_;
}

void GHOST_WindowWeb::getClientBounds(GHOST_Rect &bounds) const
{
  int w = 0, h = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &w, &h);
  bounds = GHOST_Rect(0, 0, w, h);
}

void GHOST_WindowWeb::getWindowBounds(GHOST_Rect &bounds) const
{
  /* No OS window frame around a canvas — window bounds == client bounds. */
  getClientBounds(bounds);
}

GHOST_TSuccess GHOST_WindowWeb::setClientWidth(uint32_t width)
{
  int w = 0, h = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &w, &h);
  emscripten_set_canvas_element_size(canvas_selector_.c_str(), int(width), h);
  reconfigureSurface();
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_WindowWeb::setClientHeight(uint32_t height)
{
  int w = 0, h = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &w, &h);
  emscripten_set_canvas_element_size(canvas_selector_.c_str(), w, int(height));
  reconfigureSurface();
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_WindowWeb::setClientSize(uint32_t width, uint32_t height)
{
  emscripten_set_canvas_element_size(canvas_selector_.c_str(), int(width), int(height));
  reconfigureSurface();
  return GHOST_kSuccess;
}

void GHOST_WindowWeb::reconfigureSurface()
{
#if defined(WITH_WEBGPU_BACKEND) && defined(__EMSCRIPTEN__)
  /* Only the WebGPU context owns a surface; guard the type before the down-cast so a
   * GHOST_ContextNone (no drawing context yet) is never mis-cast. */
  if (getDrawingContextType() != GHOST_kDrawingContextTypeWebGPU) {
    return;
  }
  GHOST_Context *ctx = getContext();
  if (ctx == nullptr) {
    return;
  }
  int w = 0, h = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &w, &h);
  /* configureSurface re-queries the canvas itself and is idempotent, so these extents
   * are only a fallback; passing them keeps a sane value if the query races. */
  static_cast<GHOST_ContextWGPUWeb *>(ctx)->configureSurface(uint32_t(w > 0 ? w : 0),
                                                             uint32_t(h > 0 ? h : 0));
#endif
}

void GHOST_WindowWeb::screenToClient(
    int32_t inX, int32_t inY, int32_t &outX, int32_t &outY) const
{
  /* Canvas is the screen origin for now (single surface). */
  outX = inX;
  outY = inY;
}

void GHOST_WindowWeb::clientToScreen(
    int32_t inX, int32_t inY, int32_t &outX, int32_t &outY) const
{
  outX = inX;
  outY = inY;
}

GHOST_TSuccess GHOST_WindowWeb::setState(GHOST_TWindowState state)
{
  /* Fullscreen via the HTML5 Fullscreen API is a later refinement; a canvas is
   * always "normal" in the single-surface M4 model. Accept the request. */
  (void)state;
  return GHOST_kSuccess;
}

GHOST_TWindowState GHOST_WindowWeb::getState() const
{
  EmscriptenFullscreenChangeEvent fs;
  if (emscripten_get_fullscreen_status(&fs) == EMSCRIPTEN_RESULT_SUCCESS && fs.isFullscreen) {
    return GHOST_kWindowStateFullScreen;
  }
  return GHOST_kWindowStateNormal;
}

GHOST_TSuccess GHOST_WindowWeb::invalidate()
{
  /* Redraws are driven by the main loop / rAF, not by an OS invalidate region. */
  return GHOST_kSuccess;
}

uint16_t GHOST_WindowWeb::getDPIHint()
{
  const double dpr = ghost_web_device_pixel_ratio();
  const int dpi = int(96.0 * (dpr > 0.0 ? dpr : 1.0) + 0.5);
  return uint16_t(dpi);
}

GHOST_TSuccess GHOST_WindowWeb::setWindowCursorVisibility(bool visible)
{
  /* On the WM worker `Module['canvas']` is the transferred OffscreenCanvas (M4.T12),
   * which has NO `.style` — guard it, or setting `.style.cursor` throws
   * "Cannot set properties of undefined (setting 'cursor')". Cursor styling is a
   * main-thread DOM affordance (an OffscreenCanvas cannot show a CSS cursor), so this
   * simply no-ops on the worker. */
  EM_ASM(
      {
        if (Module['canvas'] && Module['canvas'].style) {
          Module['canvas'].style.cursor = $0 ? 'auto' : 'none';
        }
      },
      visible ? 1 : 0);
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_WindowWeb::swapBufferRelease()
{
  /* Delegate the end-of-frame present to the WebGPU drawing context (M4.T21):
   * GHOST_ContextWGPUWeb::swapBufferRelease() -> presentBackbuffer() blits the persistent
   * offscreen back-buffer onto the surface's current texture and submits, in-tick. Before
   * this delegation the override was a stub returning kFailure, so wm_draw's
   * wm_window_swap_buffer_release never reached the present path and the canvas stayed on
   * GHOST's one-time surface-proof clear. The standalone event harness has no GPU context
   * (getContext() == nullptr) and keeps the old failure behaviour. */
  GHOST_Context *context = getContext();
  if (context != nullptr) {
    return context->swapBufferRelease();
  }
  return GHOST_kFailure;
}

GHOST_TSuccess GHOST_WindowWeb::activateDrawingContext()
{
  return GHOST_kFailure;
}

GHOST_Context *GHOST_WindowWeb::newDrawingContext(GHOST_TDrawingContextType type)
{
#ifdef WITH_WEBGPU_BACKEND
  if (type == GHOST_kDrawingContextTypeWebGPU) {
#  ifdef __EMSCRIPTEN__
    /* Async emdawnwebgpu context; device pre-acquired by the system's one-time
     * startup await (notes/m4-integration.md), so the sync init succeeds here. */
    GHOST_Context *context = new GHOST_ContextWGPUWeb(context_params_web_,
                                                      canvas_selector_.c_str());
#  else
    GHOST_Context *context = new GHOST_ContextWGPU(context_params_web_);
#  endif
    if (context->initializeDrawingContext()) {
      return context;
    }
    delete context;
  }
#else
  (void)type;
#endif
  return nullptr;
}
