/* SPDX-FileCopyrightText: 2011-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from intern/ghost/intern/GHOST_WindowNULL.hh and
 * GHOST_WindowSDL.hh @ fbe6228777e7. */

/** \file
 * \ingroup GHOST-web
 * Declaration of GHOST_WindowWeb — a GHOST window backed by an HTML5 <canvas>.
 *
 * For M4 there is exactly one window: the Emscripten canvas element (a CSS
 * selector, e.g. "#blender-canvas"). Client coordinates are canvas-relative
 * (origin top-left); "screen" == canvas for now (single fullscreen-ish surface),
 * so screenToClient / clientToScreen are the identity plus the canvas offset.
 */

#pragma once

#include <cstdint>
#include <string>

#include "GHOST_Window.hh"

class GHOST_WindowWeb : public GHOST_Window {
 public:
  enum class PointerLockState : uint8_t {
    Inactive = 0,
    Pending = 1,
    Active = 2,
  };

  GHOST_WindowWeb(const char *title,
                  int32_t left,
                  int32_t top,
                  uint32_t width,
                  uint32_t height,
                  GHOST_TWindowState state,
                  const GHOST_IWindow *parent_window,
                  GHOST_TDrawingContextType type,
                  const GHOST_ContextParams &context_params,
                  const char *canvas_selector);

  ~GHOST_WindowWeb() override = default;

  /** The CSS selector of the backing canvas (used by the system to target
   * Emscripten HTML5 input callbacks). */
  const std::string &getCanvasSelector() const
  {
    return canvas_selector_;
  }

  bool getValid() const override
  {
    return valid_;
  }

  void setTitle(const char *title) override;
  std::string getTitle() const override;

  void getWindowBounds(GHOST_Rect &bounds) const override;
  void getClientBounds(GHOST_Rect &bounds) const override;

  GHOST_TSuccess setClientWidth(uint32_t width) override;
  GHOST_TSuccess setClientHeight(uint32_t height) override;
  GHOST_TSuccess setClientSize(uint32_t width, uint32_t height) override;

  /** Re-configure the WebGPU surface to the canvas's current drawing-buffer extent.
   * Called after any canvas resize (setClient*, or a browser resize event) so the
   * surface never diverges from the live canvas. No-op off the WebGPU/Emscripten path
   * or before the drawing context exists. */
  void reconfigureSurface();

  void screenToClient(int32_t inX, int32_t inY, int32_t &outX, int32_t &outY) const override;
  void clientToScreen(int32_t inX, int32_t inY, int32_t &outX, int32_t &outY) const override;

  GHOST_TSuccess setState(GHOST_TWindowState state) override;
  GHOST_TWindowState getState() const override;
  GHOST_TSuccess setOrder(GHOST_TWindowOrder /*order*/) override
  {
    return GHOST_kSuccess; /* Z-order is meaningless for a single canvas. */
  }
  GHOST_TSuccess invalidate() override;

  /** Request a cursor-grab mode without confusing an accepted/deferred browser
   * request with an active Pointer Lock. The GHOST grab becomes Wrap/Hide only
   * after the browser reports a matching pointerlockchange outcome. */
  GHOST_TSuccess setCursorGrab(GHOST_TGrabCursorMode mode,
                               GHOST_TAxisFlag wrap_axis,
                               GHOST_Rect *bounds,
                               int32_t mouse_ungrab_xy[2]) override;

  /** Browser Pointer Lock outcomes, delivered to the WM worker by GHOST_SystemWeb. */
  void onPointerLockChange(bool is_active);
  void onPointerLockError();
  void releasePointerLock();

  bool isPointerLockActive() const
  {
    return pointer_lock_state_ == PointerLockState::Active;
  }

  PointerLockState pointerLockState() const
  {
    return pointer_lock_state_;
  }

  GHOST_TGrabCursorMode pointerLockRequestedMode() const
  {
    return pointer_lock_requested_mode_;
  }

  /** Backing scale factor (== devicePixelRatio, forwarded from the browser main thread).
   * Drives Blender's HiDPI UI scale and logical<->physical coordinate conversion, mirroring
   * the macOS Cocoa backend. Returns 1.0 until the shell posts a DPR. */
  float getNativePixelSize() override;

  /** Constant 96 (macOS/base semantics); the display scale is reported via
   * getNativePixelSize(), which WM_window_dpi_set_userdef multiplies in. */
  uint16_t getDPIHint() override;

#ifdef WITH_INPUT_IME
  void beginIME(int32_t x, int32_t y, int32_t w, int32_t h, bool completed) override;
  void endIME() override;
#endif

  /* NOTE: setPath() is left to GHOST_Window's default (no-op). */

  GHOST_TSuccess hasCursorShape(GHOST_TStandardCursor shape) override;

 protected:
  GHOST_TSuccess setWindowCursorGrab(GHOST_TGrabCursorMode mode) override;
  bool getCursorGrabUseSoftwareDisplay() override;
  GHOST_TSuccess setWindowCursorShape(GHOST_TStandardCursor shape) override;
  GHOST_TSuccess setWindowCustomCursorShape(const uint8_t *bitmap,
                                            const uint8_t *mask,
                                            const int size[2],
                                            const int hot_spot[2],
                                            bool can_invert_color) override;
  GHOST_TSuccess setWindowCursorVisibility(bool visible) override;

  GHOST_TSuccess swapBufferRelease() override;
  GHOST_TSuccess activateDrawingContext() override;

 private:
  GHOST_Context *newDrawingContext(GHOST_TDrawingContextType type) override;

  void applyCursorGrabState(GHOST_TGrabCursorMode mode,
                            GHOST_TAxisFlag wrap_axis,
                            const GHOST_Rect *bounds,
                            const int32_t mouse_ungrab_xy[2]);
  void retirePointerLock(bool request_browser_exit);

  std::string canvas_selector_;
  std::string title_;
  GHOST_ContextParams context_params_web_;
  bool valid_ = true;
  PointerLockState pointer_lock_state_ = PointerLockState::Inactive;
  GHOST_TGrabCursorMode pointer_lock_requested_mode_ = GHOST_kGrabDisable;
  GHOST_TAxisFlag pointer_lock_requested_axis_ = GHOST_kAxisNone;
  GHOST_Rect pointer_lock_requested_bounds_;
  bool pointer_lock_requested_bounds_valid_ = false;
};
