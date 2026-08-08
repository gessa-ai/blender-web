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

#include <atomic>
#include <cerrno>
#include <cstdio>

#include <sys/stat.h>

#include <emscripten/emscripten.h>
#include <emscripten/html5.h>
#include <emscripten/wasmfs.h>

#include "GHOST_EventBridgeWeb.hh"
#include "GHOST_WebDisplayState.hh"
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
/* Shell -> WM-worker display-state handshake (GHOST_WebDisplayState.hh).
 *
 * All state lives in shared wasm linear memory (SharedArrayBuffer under -pthread) so the
 * shell's `bw_shell_set_display` call on the MAIN thread and the WM worker's consumers
 * (ghost_web::device_pixel_ratio / poll_pending_backing) see the same values. The atomics
 * are constant-initialized (no dynamic ctor), so `bw_shell_set_display` is safe to call
 * from preRun (before __wasm_call_ctors) as the shell does to seed the DPR pre-window. */
namespace {

std::atomic<int32_t> g_target_backing_w{0};
std::atomic<int32_t> g_target_backing_h{0};
std::atomic<uint32_t> g_backing_generation{0};
/* devicePixelRatio * 1000, so the DPR travels as an integer atomic. Default 1000 = 1.0. */
std::atomic<int64_t> g_device_pixel_ratio_milli{1000};

}  // namespace

/* Called from the browser MAIN thread by the shell (boot-windowed.js) on boot and on every
 * window resize / DPR change. EMSCRIPTEN_KEEPALIVE forces it into the module exports as
 * `Module._bw_shell_set_display` without touching the (unowned) link flags; it performs only
 * atomic stores, so running it on the main thread and consuming on the WM worker is race-free
 * and realm-independent. `backing_w`/`backing_h` are PHYSICAL pixels (cssPx * dpr). */
extern "C" EMSCRIPTEN_KEEPALIVE void bw_shell_set_display(int32_t backing_w,
                                                          int32_t backing_h,
                                                          double dpr)
{
  if (dpr > 0.0) {
    g_device_pixel_ratio_milli.store(int64_t(dpr * 1000.0 + 0.5), std::memory_order_relaxed);
  }
  if (backing_w > 0 && backing_h > 0) {
    g_target_backing_w.store(backing_w, std::memory_order_relaxed);
    g_target_backing_h.store(backing_h, std::memory_order_relaxed);
    /* Release-bump the generation LAST so a consumer that sees the new generation is
     * guaranteed to also see the paired width/height. */
    g_backing_generation.fetch_add(1u, std::memory_order_release);
  }
}

/* -------------------------------------------------------------------------- */
/* M7 project store - persistent OPFS mount seam (notes/m7-store-design.md
 * §1a/§3 T1; joint proof in notes/m7-store-wired.md).
 *
 * The whole project store is a pure ROUTING of Blender's default user paths onto
 * a persistent OPFS WasmFS mount at /projects. This is the one C seam: create the
 * OPFS backend and the /projects mount point, then pre-create /projects/.recovery
 * so the TMPDIR read-path (appdir.cc test_env_path with check_is_dir=true) accepts
 * it. Everything nested under /projects is then OPFS-backed; Blender's own
 * BLI_dir_create_recursive (via BKE_appdir_folder_id_create) makes config/,
 * datafiles/, etc. on demand. The env routing itself lives in the shell
 * (boot-windowed.js ENV_VARS: BLENDER_USER_RESOURCES=/projects,
 * TMPDIR=/projects/.recovery) - no upstream edits.
 *
 * MUST run on the main()-owning (PROXY_TO_PTHREAD WM) worker, pre-main, before
 * WM_init runs BKE_tempdir_init: OPFS sync access handles are worker-only
 * (notes/m7-opfs-probe.md test 3, the coupled-decision proof). The shell calls it
 * from wgpu-preinit-worker.js - the same pre-main worker seam that awaits the
 * WebGPU device - via the EMSCRIPTEN_KEEPALIVE export Module._bw_mount_opfs,
 * BEFORE dispatching the cmd:2 entry message that runs main(). KEEPALIVE forces it
 * into the module exports without touching the (unowned) link flags, exactly like
 * bw_shell_set_display above.
 *
 * Boot NEVER fails on a store failure (graceful degrade). Return codes (the shell
 * logs them):
 *    0  OPFS mounted at /projects (+ /projects/.recovery) - PERSISTENT
 *    1  OPFS unavailable -> /projects created on the in-memory backend so env
 *       routing still resolves - SESSION-ONLY (no persistence)
 *   -1  could not create /projects at all - user paths fall back to defaults */
extern "C" EMSCRIPTEN_KEEPALIVE int bw_mount_opfs(void)
{
  /* Idempotent: mount exactly once. 2 = not-yet-called sentinel. */
  static int s_rc = 2;
  if (s_rc != 2) {
    return s_rc;
  }
  backend_t opfs = wasmfs_create_opfs_backend();
  if (opfs != nullptr && wasmfs_create_directory("/projects", 0777, opfs) == 0) {
    /* Pre-create the TMPDIR base; the config/ subtree is made on demand by
     * BKE_appdir_folder_id_create's BLI_dir_create_recursive. */
    mkdir("/projects/.recovery", 0777);
    s_rc = 0;
    return s_rc;
  }
  /* Graceful degrade: no OPFS (or the mount failed). Give Blender a writable
   * /projects on the default in-memory backend so the env routing still resolves;
   * persistence is lost but boot proceeds. */
  if (mkdir("/projects", 0777) == 0 || errno == EEXIST) {
    mkdir("/projects/.recovery", 0777);
    s_rc = 1;
    return s_rc;
  }
  s_rc = -1;
  return s_rc;
}

namespace ghost_web {

double device_pixel_ratio()
{
  const int64_t milli = g_device_pixel_ratio_milli.load(std::memory_order_relaxed);
  return (milli > 0) ? double(milli) / 1000.0 : 1.0;
}

bool poll_pending_backing(int32_t &w, int32_t &h)
{
  /* Single-consumer (the WM worker's processEvents tick); a function-static high-water
   * mark is sufficient and needs no lock. */
  static uint32_t seen_generation = 0;
  const uint32_t gen = g_backing_generation.load(std::memory_order_acquire);
  if (gen == seen_generation) {
    return false;
  }
  seen_generation = gen;
  w = g_target_backing_w.load(std::memory_order_relaxed);
  h = g_target_backing_h.load(std::memory_order_relaxed);
  return (w > 0 && h > 0);
}

}  // namespace ghost_web

/* -------------------------------------------------------------------------- */

GHOST_SystemWeb::GHOST_SystemWeb(const char *canvas_selector)
    : canvas_selector_(canvas_selector ? canvas_selector : "#canvas")
{
}

GHOST_SystemWeb::~GHOST_SystemWeb() = default;

GHOST_TSuccess GHOST_SystemWeb::init()
{
  /* M7 project store: mount the persistent OPFS /projects tree HERE - inside main()
   * on the WM (PROXY_TO_PTHREAD) worker, at GHOST creation (wm_ghost_init ->
   * GHOST_ISystem::createSystem(), wm_init_exit.cc:205), which runs BEFORE WM_init
   * reads the user config dir (wm_homefile_read_ex, :283) and BEFORE BKE_tempdir_init
   * (wm_files.cc:550). This is the proven-safe site: a synchronous WasmFS OPFS backend
   * creation in the pre-invokeEntryPoint worker seam DEADLOCKS (it blocks the worker
   * message loop before the pthread/OPFS-backend machinery is ready), whereas the same
   * call deep inside main() succeeds (notes/m7-opfs-probe.md test 3; joint proof in
   * notes/m7-store-wired.md). The env routing that points Blender's default user paths
   * at this mount lives in the shell (boot-windowed.js ENV_VARS:
   * BLENDER_USER_RESOURCES=/projects, TMPDIR=/projects/.recovery). bw_mount_opfs is
   * idempotent and never aborts boot (graceful degrade to an in-memory store). */
  {
    const double t0 = emscripten_get_now();
    const int rc = bw_mount_opfs();
    const double dt = emscripten_get_now() - t0;
    const char *what = (rc == 0) ? "OPFS mounted at /projects (+/.recovery) - PERSISTENT" :
                       (rc == 1) ? "OPFS UNAVAILABLE - /projects on in-memory backend (session-only)" :
                                   "mount FAILED - user paths fall back to defaults";
    printf("[bw] M7 store: %s rc=%d in %.1f ms\n", what, rc, dt);
    fflush(stdout);
  }

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

  /* Live backing-store resize (bug #1: black bars / blur on window resize).
   * After boot the `#canvas` is an OffscreenCanvas owned by THIS worker, so only this
   * worker may resize its backing store. The shell (main thread) computes the new physical
   * extent (cssPx * devicePixelRatio) and posts it via bw_shell_set_display; we apply it
   * here (the natural per-tick poll point) by resizing the canvas element (legal on the
   * owning worker), reconfiguring the WebGPU surface + persistent back-buffer to match, and
   * delivering a GHOST_kEventWindowSize so the WM relayouts (and recomputes UI scale, since
   * wm_window.cc GHOST_kEventWindowSize -> WM_window_dpi_set_userdef). Blender then renders
   * at the true pixel size: no CSS stretch (blur), no letterbox (black bars). */
  if (window_ != nullptr) {
    int32_t nw = 0, nh = 0;
    if (ghost_web::poll_pending_backing(nw, nh)) {
      int cw = 0, ch = 0;
      emscripten_get_canvas_element_size(canvas_selector_.c_str(), &cw, &ch);
      if (cw != nw || ch != nh) {
        emscripten_set_canvas_element_size(canvas_selector_.c_str(), nw, nh);
      }
      /* Reconfigure even when the backing extent is unchanged: a DPR-only change still
       * needs the WM to recompute pixelsize via the size event below. reconfigureSurface
       * is idempotent for an unchanged extent. */
      window_->reconfigureSurface();
      pushEvent(std::make_unique<GHOST_Event>(
          getMilliSeconds(), GHOST_kEventWindowSize, window_));

      /* Bounded diagnostic (worker printf reaches the tab console): confirms the live
       * resize path applied the shell-posted extent to the OffscreenCanvas backing store
       * this worker owns. Capped so a resize-drag cannot flood. */
      static int resize_log_count = 0;
      if (resize_log_count < 24) {
        int aw = 0, ah = 0;
        emscripten_get_canvas_element_size(canvas_selector_.c_str(), &aw, &ah);
        std::printf("WGPUWeb-resize: backing -> %dx%d (canvas readback %dx%d, dpr %.3f)\n",
                    nw, nh, aw, ah, ghost_web::device_pixel_ratio());
        resize_log_count++;
      }
    }
  }

  /* Boot-settle redraw burst. Blender redraws on demand, but at boot the tab stays BLACK
   * until the first real input: the initial GHOST_kEventWindowSize only forces a redraw
   * when the size actually CHANGES (wm_window_update_size_position), which it does not once
   * the window already matches the canvas — so WM_main has no pending redraw and never
   * composites unprompted. A plain GHOST_kEventWindowUpdate (NC_WINDOW only) proved too
   * weak to kick the first frame. GHOST_kEventWindowActivate is the window's focus-repaint
   * path: its wm_window.cc handler sets winactive, wm_window_make_drawable, addmousemove=1
   * and injects a MOUSEMOVE — the same broad re-tag a real pointer entering the window
   * does, which is what actually composited the first frame in testing. Burst it a few
   * times a second across the first ~3 s (boot has async settle — device import, surface
   * configure, script register) so one lands after the window is fully drawable, then STOP:
   * the OffscreenCanvas retains the last composited frame indefinitely, so no ongoing
   * heartbeat is needed to HOLD the image (verified: stable with zero input). Bounding the
   * burst avoids injecting perpetual MOUSEMOVEs that would fight real interaction.
   * (M4 first-pixels; a proper invalidate-driven present is a later optimization —
   * notes/gpu-r22-*.md.) */
  if (window_ != nullptr && redraw_heartbeat_ < 180u) {
    if ((redraw_heartbeat_ % 12u) == 0u) {
      pushEvent(
          std::make_unique<GHOST_Event>(getMilliSeconds(), GHOST_kEventWindowActivate, window_));
    }
    redraw_heartbeat_++;
  }

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
