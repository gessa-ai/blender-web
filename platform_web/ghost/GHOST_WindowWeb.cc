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
#  include "GHOST_ContextWGPU.hh"
#endif

/* Read window.devicePixelRatio without pulling in a JS library dependency. */
EM_JS(double, ghost_web_device_pixel_ratio, (), { return window.devicePixelRatio || 1.0; });
EM_JS(void, ghost_web_set_document_title, (const char *title), {
  document.title = UTF8ToString(title);
});

GHOST_WindowWeb::GHOST_WindowWeb(const char *title,
                                 int32_t /*left*/,
                                 int32_t /*top*/,
                                 uint32_t width,
                                 uint32_t height,
                                 GHOST_TWindowState state,
                                 const GHOST_IWindow * /*parent_window*/,
                                 GHOST_TDrawingContextType /*type*/,
                                 const GHOST_ContextParams &context_params,
                                 const char *canvas_selector)
    : GHOST_Window(width, height, state, context_params, false),
      canvas_selector_(canvas_selector ? canvas_selector : "#canvas"),
      title_(title ? title : ""),
      context_params_web_(context_params)
{
  /* Size the backing canvas to the requested client size. */
  emscripten_set_canvas_element_size(canvas_selector_.c_str(), int(width), int(height));
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
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_WindowWeb::setClientHeight(uint32_t height)
{
  int w = 0, h = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &w, &h);
  emscripten_set_canvas_element_size(canvas_selector_.c_str(), w, int(height));
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_WindowWeb::setClientSize(uint32_t width, uint32_t height)
{
  emscripten_set_canvas_element_size(canvas_selector_.c_str(), int(width), int(height));
  return GHOST_kSuccess;
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
  EM_ASM({ if (Module['canvas']) { Module['canvas'].style.cursor = $0 ? 'auto' : 'none'; } },
         visible ? 1 : 0);
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_WindowWeb::swapBufferRelease()
{
  /* WebGPU presents implicitly via the canvas context; a real swap lands with the
   * GHOST_ContextWGPU integration. No GPU context in the standalone event harness. */
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
    GHOST_Context *context = new GHOST_ContextWGPU(context_params_web_);
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
