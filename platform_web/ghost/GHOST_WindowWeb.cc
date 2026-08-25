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

#include <atomic>
#include <cmath>

#include <emscripten/emscripten.h>
#include <emscripten/html5.h>

#include "GHOST_Context.hh"
#include "GHOST_WGPUTransaction.hh"
#include "GHOST_WebDisplayState.hh"

#ifdef WITH_WEBGPU_BACKEND
/* M4 T4 selection seam: emdawnwebgpu (browser) vs native Dawn are different link
 * targets (different webgpu.h/surface/wait model — wgpu-context note deltas). */
#  ifdef __EMSCRIPTEN__
#    include "GHOST_ContextWGPUWeb.hh"
#  else
#    include "GHOST_ContextWGPU.hh"
#  endif
#endif

/* devicePixelRatio source. Under -sPROXY_TO_PTHREAD this window lives on the WM worker,
 * which has NO `window`/`document` (they exist only on the browser main thread), so a bare
 * `window.devicePixelRatio` probe there returns 1.0, which made Blender's UI draw at half
 * physical size on a HiDPI display. The real DPR is now forwarded from the main thread by
 * the shell (bw_shell_set_display) and read via ghost_web::device_pixel_ratio(); see
 * GHOST_WebDisplayState.hh. */

/* -------------------------------------------------------------------------- */
/* WM-worker -> browser-main cursor handshake.
 *
 * The transferred OffscreenCanvas owned by this worker has no DOM `style`; CSS cursor
 * changes must be applied to the original HTMLCanvasElement on the browser main thread.
 * Keep the desired GHOST state in shared wasm memory and publish it with a release
 * generation. diagnostics-bootstrap.js polls that generation from the main thread and
 * applies the corresponding CSS cursor. This mirrors the opposite-direction display-state
 * bridge in GHOST_SystemWeb.cc and remains valid before wasm constructors run because all
 * atomics are constant-initialized. */
namespace {

std::atomic<int32_t> g_cursor_shape{int32_t(GHOST_kStandardCursorDefault)};
std::atomic<int32_t> g_cursor_visible{1};
std::atomic<uint32_t> g_cursor_generation{1};

}  // namespace

extern "C" EMSCRIPTEN_KEEPALIVE uint32_t bw_shell_cursor_generation(void)
{
  return g_cursor_generation.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int32_t bw_shell_cursor_shape(void)
{
  return g_cursor_shape.load(std::memory_order_relaxed);
}

extern "C" EMSCRIPTEN_KEEPALIVE int32_t bw_shell_cursor_visible(void)
{
  return g_cursor_visible.load(std::memory_order_relaxed);
}

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
  valid_ = ghost_web::drawing_context_initialize_if_valid(
      GHOST_kSuccess, [&]() { return setDrawingContextType(type); });
}

void GHOST_WindowWeb::setTitle(const char *title)
{
  title_ = title ? title : "";
  /* The window lives on the PROXY_TO_PTHREAD WM worker, which has no `document`.
   * Title changes are rare and GHOST's input pointer is only guaranteed for this call,
   * so synchronously proxy the copy to the browser main runtime thread. In particular,
   * do not use the asynchronous proxy macro here: title_.c_str() could be invalidated by a
   * subsequent setTitle() before the queued callback consumes it. */
  MAIN_THREAD_EM_ASM(
      {
        if (typeof document !== "undefined") {
          document.title = UTF8ToString($0);
        }
      },
      title_.c_str());
}

std::string GHOST_WindowWeb::getTitle() const
{
  return title_;
}

void GHOST_WindowWeb::getClientBounds(GHOST_Rect &bounds) const
{
  /* Report LOGICAL (CSS-point) client bounds, mirroring the macOS Cocoa backend where
   * getClientBounds returns NSView points and getNativePixelSize() carries the backing
   * scale. The canvas element size is the PHYSICAL backing store (cssPx * devicePixelRatio,
   * set by the shell / by the resize poll), so divide it back down by the DPR. Blender then
   * lays the UI out in logical units and multiplies by getNativePixelSize()==DPR to reach
   * the physical framebuffer (wm_subwindow.cc wmWindowViewport_ex uses
   * WM_window_native_pixel_size = sizex * nativePixelSize). At DPR 1 this is the identity, so
   * the golden/gate path (DPR forced 1) is unchanged. */
  int w = 0, h = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &w, &h);
  const double dpr = ghost_web::device_pixel_ratio();
  if (dpr > 0.0 && dpr != 1.0) {
    w = int(std::lround(double(w) / dpr));
    h = int(std::lround(double(h) / dpr));
  }
  bounds = GHOST_Rect(0, 0, w, h);
}

void GHOST_WindowWeb::getWindowBounds(GHOST_Rect &bounds) const
{
  /* No OS window frame around a canvas — window bounds == client bounds. */
  getClientBounds(bounds);
}

/* setClient* take LOGICAL sizes (Blender's window units), matching getClientBounds; scale
 * to the PHYSICAL backing store the same way getClientBounds scales back down, so a round
 * trip is stable. (Blender does not resize its own browser window in M4, so these are
 * defensive: kept consistent with the DPR model rather than left as a physical/logical
 * mismatch.) */
static int ghost_web_logical_to_backing(uint32_t logical)
{
  const double dpr = ghost_web::device_pixel_ratio();
  return (dpr > 0.0 && dpr != 1.0) ? int(std::lround(double(logical) * dpr)) : int(logical);
}

GHOST_TSuccess GHOST_WindowWeb::setClientWidth(uint32_t width)
{
  int w = 0, h = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &w, &h);
  emscripten_set_canvas_element_size(canvas_selector_.c_str(), ghost_web_logical_to_backing(width), h);
  reconfigureSurface();
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_WindowWeb::setClientHeight(uint32_t height)
{
  int w = 0, h = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &w, &h);
  emscripten_set_canvas_element_size(canvas_selector_.c_str(), w, ghost_web_logical_to_backing(height));
  reconfigureSurface();
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_WindowWeb::setClientSize(uint32_t width, uint32_t height)
{
  emscripten_set_canvas_element_size(canvas_selector_.c_str(),
                                     ghost_web_logical_to_backing(width),
                                     ghost_web_logical_to_backing(height));
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
  const auto result_succeeded = [](const EMSCRIPTEN_RESULT result) {
    /* A deferred request is accepted by Emscripten and runs from the next browser
     * event carrying transient user activation. This is the required path when
     * Blender dispatches the original DOM event through its WM queue first. */
    return result == EMSCRIPTEN_RESULT_SUCCESS || result == EMSCRIPTEN_RESULT_DEFERRED;
  };

  switch (state) {
    case GHOST_kWindowStateNormal:
    case GHOST_kWindowStateMaximized: {
      /* A browser canvas already fills its page, so normal and maximized share
       * the same non-fullscreen state. This also cancels a deferred entry request. */
      const EMSCRIPTEN_RESULT result = emscripten_exit_fullscreen();
      return result_succeeded(result) ? GHOST_kSuccess : GHOST_kFailure;
    }
    case GHOST_kWindowStateMinimized:
      /* A tab cannot minimize its browser window. */
      return GHOST_kFailure;
    case GHOST_kWindowStateFullScreen: {
      EmscriptenFullscreenStrategy strategy = {};
      strategy.scaleMode = EMSCRIPTEN_FULLSCREEN_SCALE_STRETCH;
      /* The DOM side cannot resize a transferred canvas's backing store. Keep
       * its resolution here; the shell's display bridge observes the new CSS
       * extent and resizes the worker-owned OffscreenCanvas coherently. */
      strategy.canvasResolutionScaleMode = EMSCRIPTEN_FULLSCREEN_CANVAS_SCALE_NONE;
      strategy.filteringMode = EMSCRIPTEN_FULLSCREEN_FILTERING_DEFAULT;
      const EMSCRIPTEN_RESULT result = emscripten_request_fullscreen_strategy(
          canvas_selector_.c_str(), true, &strategy);
      return result_succeeded(result) ? GHOST_kSuccess : GHOST_kFailure;
    }
  }
  return GHOST_kFailure;
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

float GHOST_WindowWeb::getNativePixelSize()
{
  /* Backing scale factor, mirroring GHOST_WindowCocoa::setNativePixelSize() (drawableSize /
   * clientBounds == devicePixelRatio). This is the ONE knob that drives Blender's HiDPI UI
   * scale on non-macOS builds: wm_window.cc WM_window_dpi_set_userdef does
   * `auto_dpi *= getNativePixelSize()` (unconditional), so at DPR 2 U.pixelsize becomes 2 and
   * the whole interface renders at native size. It also converts logical<->physical for the
   * viewport and cursor (WM_window_native_pixel_size, wm_cursor_position_*). */
  const double dpr = ghost_web::device_pixel_ratio();
  return float(dpr > 0.0 ? dpr : 1.0);
}

uint16_t GHOST_WindowWeb::getDPIHint()
{
  /* Constant 96, mirroring the desktop bases (GHOST_Window::getDPIHint) and macOS Cocoa
   * (which does NOT override it): the display SCALE is reported through getNativePixelSize()
   * instead, and WM_window_dpi_set_userdef multiplies the two. Returning 96*DPR here would
   * DOUBLE-count against getNativePixelSize()==DPR and blow the UI up ~DPR x too large. */
  return uint16_t(96);
}

GHOST_TSuccess GHOST_WindowWeb::hasCursorShape(GHOST_TStandardCursor shape)
{
  const int cursor = int(shape);
  return (cursor >= GHOST_kStandardCursorFirstCursor &&
          cursor < int(GHOST_kStandardCursorCustom)) ?
             GHOST_kSuccess :
             GHOST_kFailure;
}

GHOST_TSuccess GHOST_WindowWeb::setWindowCursorShape(GHOST_TStandardCursor shape)
{
  if (hasCursorShape(shape) != GHOST_kSuccess) {
    return GHOST_kFailure;
  }
  g_cursor_shape.store(int32_t(shape), std::memory_order_relaxed);
  g_cursor_generation.fetch_add(1, std::memory_order_release);
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_WindowWeb::setWindowCursorVisibility(bool visible)
{
  g_cursor_visible.store(visible ? 1 : 0, std::memory_order_relaxed);
  g_cursor_generation.fetch_add(1, std::memory_order_release);
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_WindowWeb::setWindowCursorGrab(GHOST_TGrabCursorMode mode)
{
  const auto request_succeeded = [](const EMSCRIPTEN_RESULT result) {
    /* Blender reaches this method from its WM-worker event queue, after the
     * originating DOM callback has returned. Emscripten's deferred result is a
     * real accepted request: it runs from the next user-activation event. */
    return result == EMSCRIPTEN_RESULT_SUCCESS || result == EMSCRIPTEN_RESULT_DEFERRED;
  };

  switch (mode) {
    case GHOST_kGrabDisable:
      /* This also removes an entry request that was deferred but not activated. */
      return request_succeeded(emscripten_exit_pointerlock()) ? GHOST_kSuccess :
                                                                GHOST_kFailure;
    case GHOST_kGrabNormal:
      /* Browsers expose no visible-pointer confinement API. Match the SDL
       * backend's successful no-adjustment grab without hiding the pointer. */
      return GHOST_kSuccess;
    case GHOST_kGrabWrap:
    case GHOST_kGrabHide:
      /* Pointer Lock supplies unbounded relative motion for continuous viewport
       * navigation and hides the system pointer. Relative coordinates are
       * accumulated by GHOST_EventBridgeWeb while these modes are active. */
      return request_succeeded(emscripten_request_pointerlock(canvas_selector_.c_str(), true)) ?
                 GHOST_kSuccess :
                 GHOST_kFailure;
  }
  return GHOST_kFailure;
}

bool GHOST_WindowWeb::getCursorGrabUseSoftwareDisplay()
{
  /* Pointer Lock hides the DOM cursor for both unbounded modes. Wrap retains
   * Blender's visible-cursor semantics through WM's capability-driven software
   * cursor; Hide intentionally remains invisible. */
  return getCursorGrabMode() == GHOST_kGrabWrap;
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
  return GHOST_Window::activateDrawingContext();
}

GHOST_Context *GHOST_WindowWeb::newDrawingContext(GHOST_TDrawingContextType type)
{
#ifdef WITH_WEBGPU_BACKEND
  if (type == GHOST_kDrawingContextTypeWebGPU) {
#  ifdef __EMSCRIPTEN__
    /* Async emdawnwebgpu context; device pre-acquired by the system's one-time
     * startup await (notes/m4-integration.md), so the sync init succeeds here. */
    GHOST_Context *context = new GHOST_ContextWGPUWeb(
        context_params_web_,
        canvas_selector_.c_str(),
        ghost_web::DrawingContextMode::PresentableWindow);
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
