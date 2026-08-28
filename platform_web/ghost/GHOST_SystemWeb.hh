/* SPDX-FileCopyrightText: 2011-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from intern/ghost/intern/GHOST_SystemHeadless.hh and
 * GHOST_SystemSDL.hh @ fbe6228777e7. */

/** \file
 * \ingroup GHOST-web
 *
 * GHOST_SystemWeb — the GHOST system back-end for the browser (Emscripten HTML5).
 *
 * Responsibilities (the platform half; the translation half is GHOST_EventBridgeWeb):
 *  - register HTML5 input callbacks (mouse / wheel / keyboard / resize / focus) on
 *    the canvas + window, forwarding to the bridge;
 *  - own the single canvas window and the tracked input state (modifiers, buttons,
 *    cursor position) the bridge updates and GHOST queries;
 *  - drive the GHOST event queue (processEvents / dispatchEvents at the top-level
 *    main-loop tick — see the main-loop design in notes/ghost-web-design.md and
 *    ADR-003's suspend-topology invariant).
 */

#pragma once

#include <string>

#include "GHOST_System.hh"

class GHOST_WindowWeb;

class GHOST_SystemWeb : public GHOST_System {
 public:
  /** \param canvas_selector: CSS selector of the backing canvas (default "#canvas"). */
  explicit GHOST_SystemWeb(const char *canvas_selector = "#canvas");
  ~GHOST_SystemWeb() override;

  /* --- GHOST_System overrides -------------------------------------------------- */

  GHOST_TSuccess init() override;

  bool processEvents(bool waitForEvent) override;
  bool setConsoleWindowState(GHOST_TConsoleWindowState /*action*/) override
  {
    return false;
  }

  GHOST_TSuccess getModifierKeys(GHOST_ModifierKeys &keys) const override;
  GHOST_TSuccess getButtons(GHOST_Buttons &buttons) const override;
  GHOST_TCapabilityFlag getCapabilities() const override;

  char *getClipboard(bool selection) const override;
  void putClipboard(const char *buffer, bool selection) const override;

  uint64_t getMilliSeconds() const override;
  uint8_t getNumDisplays() const override
  {
    return 1;
  }

  GHOST_TSuccess getCursorPosition(int32_t &x, int32_t &y) const override;
  GHOST_TSuccess setCursorPosition(int32_t x, int32_t y) override;

  void getMainDisplayDimensions(uint32_t &width, uint32_t &height) const override;
  void getAllDisplayDimensions(uint32_t &width, uint32_t &height) const override;

  GHOST_IContext *createOffscreenContext(GHOST_GPUSettings gpu_settings) override;
  GHOST_TSuccess disposeContext(GHOST_IContext *context) override;
  GHOST_TSuccess disposeWindow(GHOST_IWindow *window) override;

  GHOST_IWindow *createWindow(const char *title,
                              int32_t left,
                              int32_t top,
                              uint32_t width,
                              uint32_t height,
                              GHOST_TWindowState state,
                              GHOST_GPUSettings gpu_settings,
                              const bool exclusive,
                              const bool is_dialog,
                              const GHOST_IWindow *parent_window) override;

  GHOST_IWindow *getWindowUnderCursor(int32_t x, int32_t y) override;

  /* --- Bridge-facing state API (called by GHOST_EventBridgeWeb) ---------------- */

  /** The live single canvas window (event target, independent of DOM focus). */
  GHOST_WindowWeb *activeWindow() const
  {
    return window_;
  }

  void noteCursor(int32_t x, int32_t y)
  {
    cursor_x_ = x;
    cursor_y_ = y;
  }

  /** Reconcile aggregate DOM ctrl/shift/alt/meta flags with the tracked side-aware state.
   * Preserve a known side; when no key event established one, use the left side as fallback. */
  void noteModifierFlags(bool ctrl, bool shift, bool alt, bool meta);

  /** Update one exact left/right modifier from a DOM keyboard event's `code`. */
  void noteModifierKey(GHOST_TKey key, bool down);

  /** Update one tracked button and publish a diagnostic edge only on a real state transition. */
  void noteButton(GHOST_TButton button, bool down);

  /** Publish one coalescible bounded redraw retry for accepted ordinary input.
   * This deliberately does not start the resize-only drawable episode/barrier. */
  void requestInputRedrawRetry();

  const std::string &canvasSelector() const
  {
    return canvas_selector_;
  }

  /** Refresh the DOM canvas rectangle used by window-scoped pointer callbacks.
   * Registration and resize are rare synchronous main-thread boundaries; each
   * mouse move then translates locally on the owning WM worker. */
  bool refreshCanvasClientRect();

  /** Translate a viewport/client point into canvas-relative logical pixels.
   * Returns true when the point is inside the last complete DOM rectangle. */
  bool windowToCanvasCoordinates(
      int32_t client_x, int32_t client_y, int32_t &canvas_x, int32_t &canvas_y) const;

  /** True while browser focus belongs to either the canvas or Blender's enabled
   * hidden IME textarea. The two DOM elements form one logical GHOST window. */
  bool browserFocusIsOwned() const;

  /** Publish the logical browser-focus state once. Returns true only for a transition. */
  bool transitionBrowserFocus(bool focused);

  /** Mark DOM-event-time loss publications satisfied by an ordinary proxied blur. */
  void acknowledgePublishedBrowserFocusLoss();

  /** Consume any DOM-event-time focus loss before the current proxied callback.
   * Focus and input callbacks share Emscripten's worker queue, so calling this
   * from the focus callback preserves their browser-event order. */
  void reconcilePublishedBrowserFocus();

 private:
  bool registerCanvasCallbacks();
  void unregisterCanvasCallbacks();

  std::string canvas_selector_;
  GHOST_WindowWeb *window_ = nullptr;
  bool callbacks_registered_ = false;
  void *callback_user_data_ = nullptr;

  /* Per-window readiness/input generations and bounded tick counter for draw recovery. */
  uint64_t redraw_retry_generation_seen_ = 0;
  uint64_t input_redraw_retry_generation_seen_ = 0;
  uint64_t redraw_episode_generation_seen_ = 0;
  uint64_t redraw_drop_generation_seen_ = 0;
  uint64_t redraw_present_barrier_completion_seen_ = 0;
  uint64_t present_replay_generation_seen_ = 0;
  uint32_t redraw_heartbeat_ = 0;

  /* Idle-keepalive bookkeeping (ghost-keepalive; all touched only on the WM worker in
   * processEvents). current_timing_ms_ starts at -1 so the first tick performs the initial
   * switch from rAF to setTimeout scheduling. */
  int32_t current_timing_ms_ = -1;
  double last_activity_ms_ = 0.0;
  uint64_t last_present_count_ = 0;

  int32_t cursor_x_ = 0;
  int32_t cursor_y_ = 0;
  int32_t canvas_client_left_ = 0;
  int32_t canvas_client_top_ = 0;
  int32_t canvas_client_width_ = 0;
  int32_t canvas_client_height_ = 0;
  GHOST_ModifierKeys modifiers_;
  bool browser_focus_active_ = false;
  uint32_t browser_focus_loss_generation_ = 0;
  GHOST_Buttons buttons_;
};
