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

#include <array>
#include <atomic>
#include <cerrno>
#include <cstdio>

#include <sys/stat.h>

#include <emscripten/emscripten.h>
#include <emscripten/html5.h>
#include <emscripten/wasmfs.h>

#include "GHOST_EventBridgeWeb.hh"
#include "GHOST_WGPUTransaction.hh"
#include "GHOST_WebDisplayState.hh"
#include "GHOST_WindowWeb.hh"

#include "GHOST_Buttons.hh"
#include "GHOST_Event.hh"
#include "GHOST_EventManager.hh"
#include "GHOST_ModifierKeys.hh"
#include "GHOST_WindowManager.hh"

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
/* HTML5 -> bridge callback thunks. Returning true marks the DOM event as consumed
 * (preventDefault), which is what Blender wants for input over its canvas. */

namespace {

/* Browser-main event listeners can already have queued a callback to the WM
 * worker when disposal unregisters them. A system pointer is reused by every
 * replacement window, so it cannot identify the registration that captured the
 * event. Give every attempt a unique opaque token address instead. Tokens are
 * never dereferenced, freed, or reused; a fixed process-lifetime pool bounds the
 * metadata at 4 KiB, and exhaustion fails closed. This includes failed prefix
 * transactions because their briefly installed listeners can already have
 * queued delivery before rollback. */
constexpr uint32_t kCallbackRegistrationBudget = 4096;
std::array<uint8_t, kCallbackRegistrationBudget> g_callback_registration_tokens{};
std::atomic<uint32_t> g_callback_registration_token_count{0};
std::atomic<void *> g_callback_registration{nullptr};
std::atomic<GHOST_SystemWeb *> g_callback_system{nullptr};

void *callback_registration_token_acquire()
{
  uint32_t index = g_callback_registration_token_count.load(std::memory_order_relaxed);
  while (index < kCallbackRegistrationBudget) {
    const uint32_t next = index + 1;
    if (g_callback_registration_token_count.compare_exchange_weak(
            index, next, std::memory_order_relaxed, std::memory_order_relaxed))
    {
      return &g_callback_registration_tokens[index];
    }
  }
  return nullptr;
}

#ifdef WITH_INPUT_IME
constexpr const char *kImeInputSelector = "#bw-ime-input";
constexpr size_t kWebCallbackCount = 16;
#else
constexpr size_t kWebCallbackCount = 14;
#endif

GHOST_SystemWeb *callback_system(void *user_data)
{
  if (user_data == nullptr ||
      g_callback_registration.load(std::memory_order_acquire) != user_data)
  {
    return nullptr;
  }
  return g_callback_system.load(std::memory_order_acquire);
}

bool cb_mousemove(int /*t*/, const EmscriptenMouseEvent *e, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  if (system == nullptr) {
    return false;
  }

  GHOST_WindowWeb *window = system->activeWindow();
  if (window == nullptr) {
    return false;
  }

  /* Mouse-move is registered on `window` so a canvas-owned drag keeps its
   * motion after leaving the element. Restore the canvas-relative coordinate
   * contract before EventBridgeWeb sees the event. */
  EmscriptenMouseEvent event = *e;
  const bool inside_canvas = system->windowToCanvasCoordinates(
      e->clientX, e->clientY, event.targetX, event.targetY);

  GHOST_Buttons buttons;
  const bool have_buttons = system->getButtons(buttons) == GHOST_kSuccess;
  const bool owns_drag = have_buttons &&
                         (buttons.get(GHOST_kButtonMaskLeft) ||
                          buttons.get(GHOST_kButtonMaskMiddle) ||
                          buttons.get(GHOST_kButtonMaskRight) ||
                          buttons.get(GHOST_kButtonMaskButton4) ||
                          buttons.get(GHOST_kButtonMaskButton5) ||
                          buttons.get(GHOST_kButtonMaskButton6) ||
                          buttons.get(GHOST_kButtonMaskButton7));
  if (!inside_canvas && !owns_drag && !window->isPointerLockActive()) {
    /* Window scope must not turn ordinary page motion into Blender input. */
    return false;
  }

  ghost_web_bridge::on_mouse_move(*system, event);
  return true;
}
bool cb_mousebtn(int t, const EmscriptenMouseEvent *e, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  if (system == nullptr) {
    return false;
  }

  EmscriptenMouseEvent event = *e;
  if (t == EMSCRIPTEN_EVENT_MOUSEUP) {
    const GHOST_TButton button = ghost_web_bridge::button_from_dom(e->button);
    bool held = false;
    if (button == GHOST_kButtonMaskNone ||
        system->getButtonState(button, held) != GHOST_kSuccess || !held)
    {
      /* Mouse-up is registered on `window` so a Blender-owned drag cannot lose
       * its terminal release after leaving the canvas. Do not turn unrelated
       * page releases into GHOST input or consume their browser defaults. */
      return false;
    }

    /* A window-targeted Emscripten event reports targetX/Y relative to the
     * viewport. Restore the same cached canvas-relative coordinates used by
     * window-scoped drag motion. The release remains deliverable outside. */
    system->windowToCanvasCoordinates(
        e->clientX, e->clientY, event.targetX, event.targetY);
  }

  ghost_web_bridge::on_mouse_button(*system, t, event);
  return true;
}
bool cb_wheel(int /*t*/, const EmscriptenWheelEvent *e, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  if (system == nullptr) {
    return false;
  }
  ghost_web_bridge::on_wheel(*system, *e);
  return true;
}
bool cb_key(int t, const EmscriptenKeyboardEvent *e, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  if (system == nullptr) {
    return false;
  }
  ghost_web_bridge::on_key(*system, t, *e);
  return true;
}
bool cb_resize(int /*t*/, const EmscriptenUiEvent *e, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  if (system == nullptr) {
    return false;
  }
  system->refreshCanvasClientRect();
  ghost_web_bridge::on_resize(*system, *e);
  return true;
}
bool publish_browser_focus_transition(GHOST_SystemWeb *system, const bool focused)
{
  if (!system->transitionBrowserFocus(focused)) {
    return false;
  }
  ghost_web_bridge::on_focus(*system, focused);
  return true;
}

bool cb_canvas_focus(int /*t*/, const EmscriptenFocusEvent * /*e*/, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  if (system == nullptr) {
    return false;
  }
  system->reconcilePublishedBrowserFocus();
  if (!system->browserFocusIsOwned()) {
    return false;
  }
  return publish_browser_focus_transition(system, true);
}

bool cb_canvas_blur(int /*t*/, const EmscriptenFocusEvent * /*e*/, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  if (system == nullptr) {
    return false;
  }
  /* This callback is queued before any later focus or input callback. Consume
   * the capture-time loss while that ordering is still available; querying the
   * live DOM first would erase a same-task blur/refocus boundary. */
  system->reconcilePublishedBrowserFocus();
  if (system->browserFocusIsOwned()) {
    return false;
  }
  system->acknowledgePublishedBrowserFocusLoss();
  return publish_browser_focus_transition(system, false);
}

bool cb_window_focus(int /*t*/, const EmscriptenFocusEvent * /*e*/, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  if (system == nullptr || !system->browserFocusIsOwned()) {
    return false;
  }
  return publish_browser_focus_transition(system, true);
}

bool cb_window_blur(int /*t*/, const EmscriptenFocusEvent * /*e*/, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  if (system == nullptr) {
    return false;
  }
  /* A browser-window blur leaves the complete canvas/IME focus domain even
   * when the hidden textarea, rather than the canvas, owns activeElement. */
  return publish_browser_focus_transition(system, false);
}
bool cb_contextmenu(int /*t*/, const EmscriptenMouseEvent * /*e*/, void *ud)
{
  if (callback_system(ud) == nullptr) {
    return false;
  }
  /* Swallow the browser context menu so right-drag works. */
  return true;
}

bool cb_pointerlockchange(int /*t*/, const EmscriptenPointerlockChangeEvent *e, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  GHOST_WindowWeb *window = system != nullptr ? system->activeWindow() : nullptr;
  if (window == nullptr) {
    return false;
  }

  const bool reported_active = e != nullptr && e->isActive;
  const bool owns_lock = reported_active &&
                         MAIN_THREAD_EM_ASM_INT(
                             {
                               const selector = UTF8ToString($0);
                               return document.pointerLockElement ===
                                      document.querySelector(selector);
                             },
                             window->getCanvasSelector().c_str()) != 0;
  window->onPointerLockChange(owns_lock);
  return false;
}

bool cb_pointerlockerror(int /*t*/, const void * /*reserved*/, void *ud)
{
  GHOST_SystemWeb *system = callback_system(ud);
  GHOST_WindowWeb *window = system != nullptr ? system->activeWindow() : nullptr;
  if (window != nullptr) {
    window->onPointerLockError();
  }
  return false;
}

template<typename CallbackT>
bool remove_html5_callback(const char *target,
                           void *user_data,
                           const int event_type,
                           CallbackT callback)
{
  return emscripten_html5_remove_event_listener(
             target, user_data, event_type, reinterpret_cast<void *>(callback)) ==
         EMSCRIPTEN_RESULT_SUCCESS;
}

bool remove_html5_callback_prefix(const char *canvas,
                                  const char *window,
                                  void *user_data,
                                  const size_t registered_count)
{
  bool removed = true;
  switch (registered_count) {
    default:
      return false;
#ifdef WITH_INPUT_IME
    case 16:
      removed &= remove_html5_callback(
          window, user_data, EMSCRIPTEN_EVENT_RESIZE, cb_resize);
      [[fallthrough]];
    case 15:
      removed &= remove_html5_callback(
          kImeInputSelector, user_data, EMSCRIPTEN_EVENT_KEYUP, cb_key);
      [[fallthrough]];
    case 14:
      removed &= remove_html5_callback(
          kImeInputSelector, user_data, EMSCRIPTEN_EVENT_KEYDOWN, cb_key);
      [[fallthrough]];
#else
    case 14:
      removed &= remove_html5_callback(
          window, user_data, EMSCRIPTEN_EVENT_RESIZE, cb_resize);
      [[fallthrough]];
#endif
    case 13:
      removed &= remove_html5_callback(
          canvas, user_data, EMSCRIPTEN_EVENT_KEYUP, cb_key);
      [[fallthrough]];
    case 12:
      removed &= remove_html5_callback(
          canvas, user_data, EMSCRIPTEN_EVENT_KEYDOWN, cb_key);
      [[fallthrough]];
    case 11:
      removed &= remove_html5_callback(EMSCRIPTEN_EVENT_TARGET_DOCUMENT,
                                       user_data,
                                       EMSCRIPTEN_EVENT_POINTERLOCKERROR,
                                       cb_pointerlockerror);
      [[fallthrough]];
    case 10:
      removed &= remove_html5_callback(EMSCRIPTEN_EVENT_TARGET_DOCUMENT,
                                       user_data,
                                       EMSCRIPTEN_EVENT_POINTERLOCKCHANGE,
                                       cb_pointerlockchange);
      [[fallthrough]];
    case 9:
      removed &= remove_html5_callback(
          window, user_data, EMSCRIPTEN_EVENT_BLUR, cb_window_blur);
      [[fallthrough]];
    case 8:
      removed &= remove_html5_callback(
          window, user_data, EMSCRIPTEN_EVENT_FOCUS, cb_window_focus);
      [[fallthrough]];
    case 7:
      removed &= remove_html5_callback(
          canvas, user_data, EMSCRIPTEN_EVENT_BLUR, cb_canvas_blur);
      [[fallthrough]];
    case 6:
      removed &= remove_html5_callback(
          canvas, user_data, EMSCRIPTEN_EVENT_FOCUS, cb_canvas_focus);
      [[fallthrough]];
    case 5:
      removed &= remove_html5_callback(
          canvas, user_data, EMSCRIPTEN_EVENT_CONTEXTMENU, cb_contextmenu);
      [[fallthrough]];
    case 4:
      removed &= remove_html5_callback(canvas, user_data, EMSCRIPTEN_EVENT_WHEEL, cb_wheel);
      [[fallthrough]];
    case 3:
      removed &= remove_html5_callback(window, user_data, EMSCRIPTEN_EVENT_MOUSEUP, cb_mousebtn);
      [[fallthrough]];
    case 2:
      removed &= remove_html5_callback(
          canvas, user_data, EMSCRIPTEN_EVENT_MOUSEDOWN, cb_mousebtn);
      [[fallthrough]];
    case 1:
      removed &= remove_html5_callback(
          window, user_data, EMSCRIPTEN_EVENT_MOUSEMOVE, cb_mousemove);
      [[fallthrough]];
    case 0:
      break;
  }
  return removed;
}

}  // namespace

/* Read-only lifecycle diagnostics for the M8 bounded-metadata soak. The count
 * includes successful and rolled-back registration attempts because both consume
 * a never-recycled token. Doubles avoid a BigInt hop in browser harnesses. */
extern "C" EMSCRIPTEN_KEEPALIVE double bw_callback_registration_attempt_count()
{
  return double(g_callback_registration_token_count.load(std::memory_order_relaxed));
}

extern "C" EMSCRIPTEN_KEEPALIVE double bw_callback_registration_budget()
{
  return double(kCallbackRegistrationBudget);
}

extern "C" EMSCRIPTEN_KEEPALIVE double bw_callback_registration_metadata_bytes()
{
  return double(sizeof(g_callback_registration_tokens));
}

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

/* Browser focus events are observed on the DOM main thread but Emscripten delivers
 * their C callbacks later on the PROXY_TO_PTHREAD WM worker. Canvas -> page control
 * -> canvas can therefore complete before the first queued callback runs, hiding
 * the intervening boundary that must retire held keys/buttons. Publish a monotonic
 * loss generation so the WM worker can replay one fail-safe deactivate before
 * querying and reconciling the live DOM state. */
std::atomic<uint32_t> g_browser_focus_loss_generation{0};

/* --- Idle keepalive state (ghost-keepalive) ------------------------------------------
 * The web WM_main is emscripten_set_main_loop(fn, 0, 1) - fps=0 => requestAnimationFrame on
 * THIS (WM/PROXY_TO_PTHREAD) worker (patch 0026). A worker's rAF is PRESENT-GATED: it stops
 * rescheduling once the OffscreenCanvas stops compositing, so at idle (nothing tagged for
 * redraw) the whole loop stalls and bpy.app.timers / GPU MapAsync completions never advance
 * (notes/m7b-files-io.md §4; probe-burst maxHb=1). The keepalive switches the SAME loop to
 * setTimeout scheduling, which is NOT present-gated, so the loop keeps ticking at idle. These
 * are seeded by the shell from preRun on the MAIN thread via bw_shell_set_keepalive; the
 * atomics are constant-initialized so that pre-ctor cross-thread store is race-free, exactly
 * the bw_shell_set_display posture. Default ENABLED - opt out with ?keepalive=0 for the
 * pre-fix (rAF, stalls-at-idle) A/B baseline. */
std::atomic<int32_t> g_keepalive_enabled{1};
/* Fast / idle setTimeout intervals in ms (shell-tunable; <=0 store keeps the default). */
std::atomic<int32_t> g_keepalive_active_ms{16};
std::atomic<int32_t> g_keepalive_idle_ms{250};
/* Total WM main-loop iterations (processEvents ticks) since boot; the liveness half of the
 * proof (rising => the loop is alive; frozen after boot => the old idle stall). */
std::atomic<uint64_t> g_wm_tick_count{0};

/* Stay on the fast interval for this long after the last activity (input / draw / boot) so a
 * brief pause between interactions does not drop to the idle rate and add wake latency. */
constexpr double KEEPALIVE_GRACE_MS = 1000.0;

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

/* DOM-main -> WM-worker focus-domain publication. A counter preserves a rapid
 * loss/reacquisition even when the latest state is already true by the time the
 * worker runs. This function performs one atomic operation only and is therefore
 * safe to call from the browser main runtime thread. */
extern "C" EMSCRIPTEN_KEEPALIVE void bw_shell_focus_lost()
{
  g_browser_focus_loss_generation.fetch_add(1u, std::memory_order_release);
}

extern "C" EMSCRIPTEN_KEEPALIVE double bw_shell_focus_loss_generation()
{
  return double(g_browser_focus_loss_generation.load(std::memory_order_acquire));
}

/* Shell -> WM-worker idle-keepalive control (ghost-keepalive). Called by the shell from
 * preRun on the browser MAIN thread (relaxed atomic stores only, so it is race-free before
 * __wasm_call_ctors, exactly like bw_shell_set_display). \a enabled != 0 turns the setTimeout
 * keepalive ON (default) so the WM loop keeps ticking at idle; 0 leaves the loop on
 * requestAnimationFrame - the pre-fix behaviour that stalls at idle, reachable via
 * ?keepalive=0 for A/B. \a active_ms / \a idle_ms override the fast / idle setTimeout
 * intervals when > 0 (<= 0 keeps the built-in defaults). Consumed on the WM worker in
 * processEvents, the only legal caller of emscripten_set_main_loop_timing for this loop. */
extern "C" EMSCRIPTEN_KEEPALIVE void bw_shell_set_keepalive(int32_t enabled,
                                                            int32_t active_ms,
                                                            int32_t idle_ms)
{
  g_keepalive_enabled.store(enabled ? 1 : 0, std::memory_order_relaxed);
  if (active_ms > 0) {
    g_keepalive_active_ms.store(active_ms, std::memory_order_relaxed);
  }
  if (idle_ms > 0) {
    g_keepalive_idle_ms.store(idle_ms, std::memory_order_relaxed);
  }
}

/* Total WM main-loop iterations since boot, as double (avoids a BigInt hop under
 * -sWASM_BIGINT). The liveness half of the ghost-keepalive proof: the shell polls this across
 * an idle window and shows it keeps rising (loop alive) while bw_present_count stays flat (no
 * GPU submits at idle). */
extern "C" EMSCRIPTEN_KEEPALIVE double bw_wm_tick_count(void)
{
  return double(g_wm_tick_count.load(std::memory_order_relaxed));
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

GHOST_SystemWeb::~GHOST_SystemWeb()
{
#ifdef WITH_INPUT_IME
  ghost_web_bridge::set_ime_enabled(false);
#endif
  if (window_ != nullptr) {
    window_->releasePointerLock();
  }
  unregisterCanvasCallbacks();
  window_ = nullptr;
}

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

bool GHOST_SystemWeb::registerCanvasCallbacks()
{
  if (callbacks_registered_) {
    return true;
  }
  if (!refreshCanvasClientRect()) {
    std::fprintf(stderr, "GHOST-web: canvas client rectangle is unavailable\n");
    return false;
  }
  void *user_data = callback_registration_token_acquire();
  if (user_data == nullptr) {
    std::fprintf(stderr,
                 "GHOST-web: callback registration token budget exhausted (%u attempts)\n",
                 kCallbackRegistrationBudget);
    return false;
  }
  const char *canvas = canvas_selector_.c_str();
  const char *win = EMSCRIPTEN_EVENT_TARGET_WINDOW;

#ifdef WITH_INPUT_IME
  /* Browser composition events originate on the DOM main thread, while the
   * GHOST event manager is owned by the WM worker. Keep the browser's real text
   * input focused at Blender's requested caret rectangle and publish owned UTF-8
   * messages into EventBridgeWeb's bounded SPSC queue. The WM worker drains that
   * queue from processEvents(); no GHOST object is touched cross-thread. */
  MAIN_THREAD_EM_ASM({
    if (typeof globalThis.__bwImeBridge !== "object") {
      var input = document.createElement("textarea");
      input.id = "bw-ime-input";
      input.tabIndex = -1;
      input.autocomplete = "off";
      input.spellcheck = false;
      input.setAttribute("aria-hidden", "true");
      input.style.position = "fixed";
      input.style.opacity = "0";
      input.style.pointerEvents = "none";
      input.style.border = "0";
      input.style.padding = "0";
      input.style.margin = "0";
      input.style.outline = "0";
      input.style.resize = "none";
      input.style.overflow = "hidden";
      input.style.zIndex = "-1";
      document.body.appendChild(input);

      var enabled = false;
      var composing = false;
      var sequence = 0;
      var accepted = 0;
      var rejected = 0;
      var recovered = 0;
      var lastKind = "none";
      var lastUtf8Bytes = 0;
      var activeCanvas = null;
      var rawKeyAdmitted = 0;
      var rawKeySuppressed = 0;

      var recordPublish = function (kind, utf8Bytes, ok) {
        sequence += 1;
        lastKind = kind;
        lastUtf8Bytes = utf8Bytes;
        if (ok) {
          accepted += 1;
        }
        else {
          rejected += 1;
        }
        return ok;
      };

      var cancelComposition = function () {
        var cancelFunction = Module["_bw_shell_ime_cancel"];
        var ok = typeof cancelFunction === "function" && cancelFunction() === 1;
        if (recordPublish("cancel", 0, ok)) {
          recovered += 1;
        }
        composing = false;
        return ok;
      };

      var publish = function (kind, text, cursorPosition, targetStart, targetEnd) {
        text = String(text || "");
        var utf8Bytes = lengthBytesUTF8(text);
        var pointer = 0;
        var ok = 0;
        var publishFunction = Module["_bw_shell_ime_publish"];
        if (typeof publishFunction === "function") {
          if (utf8Bytes === 0) {
            ok = publishFunction(kind, 0, 0, cursorPosition, targetStart, targetEnd);
          }
          else {
            try {
              pointer = _malloc(utf8Bytes + 1);
              if (pointer) {
                stringToUTF8(text, pointer, utf8Bytes + 1);
                ok = publishFunction(
                    kind, pointer, utf8Bytes, cursorPosition, targetStart, targetEnd);
              }
            }
            catch (_) {
              ok = 0;
            }
          }
        }
        if (pointer) {
          _free(pointer);
        }
        var kindName = kind === 0 ? "start" :
                       kind === 1 ? "update" :
                       kind === 2 ? "commit" :
                       kind === 3 ? "end" : "invalid";
        var acceptedMessage = recordPublish(kindName, utf8Bytes, ok === 1);
        if (!acceptedMessage && kind !== 3 && composing) {
          /* A disposable update may saturate or any owned-text allocation may
           * fail. The queue reserves a no-allocation terminal slot, so cancel
           * explicitly before ignoring the rest of this browser composition. */
          cancelComposition();
        }
        return acceptedMessage;
      };

      /* Emscripten's C keyboard payload omits KeyboardEvent.isComposing. This
       * listener is intentionally installed before the Emscripten listeners on
       * the same textarea, so stopImmediatePropagation can keep browser IME
       * process keys out of the raw GHOST path without disturbing composition's
       * default action. Ordinary keys continue to the exact textarea callbacks
       * registered below. */
      var admitRawKey = function (event) {
        var ownsFocus = enabled && document.activeElement === input;
        var compositionKey = composing || event.isComposing || event.key === "Process" ||
                             event.keyCode === 229;
        if (!ownsFocus || compositionKey) {
          rawKeySuppressed += 1;
          event.stopImmediatePropagation();
          return;
        }
        rawKeyAdmitted += 1;
      };
      input.addEventListener("keydown", admitRawKey);
      input.addEventListener("keyup", admitRawKey);

      input.addEventListener("compositionstart", function (event) {
        if (!enabled) {
          return;
        }
        composing = true;
        var text = event.data || "";
        publish(0, text, lengthBytesUTF8(text), -1, -1);
      });
      input.addEventListener("compositionupdate", function (event) {
        if (!enabled || !composing) {
          return;
        }
        var text = event.data || "";
        publish(1, text, lengthBytesUTF8(text), -1, -1);
      });
      input.addEventListener("compositionend", function (event) {
        if (!enabled || !composing) {
          input.value = "";
          return;
        }
        var text = event.data || "";
        if (publish(2, text, -1, -1, -1) && composing) {
          publish(3, "", -1, -1, -1);
        }
        composing = false;
        queueMicrotask(function () {
          if (!composing) {
            input.value = "";
          }
        });
      });
      input.addEventListener("input", function () {
        if (!composing) {
          input.value = "";
        }
      });

      var api = Object.freeze({
        schema: 1,
        begin: function (selector, x, y, width, height, completed) {
          var focusBridge = globalThis.__bwFocusBridge;
          if (focusBridge && typeof focusBridge.beginHandoff === "function") {
            focusBridge.beginHandoff();
          }
          try {
            activeCanvas = document.querySelector(selector);
            if (!activeCanvas) {
              return false;
            }
            enabled = true;
            if (completed && composing) {
              cancelComposition();
              input.blur();
            }
            var bounds = activeCanvas.getBoundingClientRect();
            input.style.left = Math.round(bounds.left + x) + "px";
            input.style.top = Math.round(bounds.top + y) + "px";
            input.style.width = Math.max(1, Math.round(width)) + "px";
            input.style.height = Math.max(1, Math.round(height)) + "px";
            input.focus({preventScroll: true});
            return document.activeElement === input;
          }
          finally {
            if (focusBridge && typeof focusBridge.endHandoff === "function") {
              focusBridge.endHandoff();
            }
          }
        },
        end: function () {
          var focusBridge = globalThis.__bwFocusBridge;
          if (focusBridge && typeof focusBridge.beginHandoff === "function") {
            focusBridge.beginHandoff();
          }
          try {
            if (composing) {
              cancelComposition();
            }
            if (document.activeElement === input) {
              input.blur();
            }
            enabled = false;
            composing = false;
            input.value = "";
            if (activeCanvas && typeof activeCanvas.focus === "function") {
              activeCanvas.focus({preventScroll: true});
            }
            return true;
          }
          finally {
            if (focusBridge && typeof focusBridge.endHandoff === "function") {
              focusBridge.endHandoff();
            }
          }
        },
        snapshot: function () {
          return {
            schema: 1,
            enabled: enabled,
            composing: composing,
            sequence: sequence,
            accepted: accepted,
            rejected: rejected,
            recovered: recovered,
            lastKind: lastKind,
            lastUtf8Bytes: lastUtf8Bytes,
            focused: document.activeElement === input,
            rawKeyAdmitted: rawKeyAdmitted,
            rawKeySuppressed: rawKeySuppressed,
          };
        },
      });
      Object.defineProperty(globalThis, "__bwImeBridge", {
        value: api,
        writable: false,
        configurable: false,
        enumerable: false,
      });
    }
  });
#endif /* WITH_INPUT_IME */

  /* Observe focus-domain losses at DOM-event time. Emscripten's registered focus
   * callbacks below are proxied to the WM worker and may run only after a later
   * refocus, so querying `document.activeElement` from those callbacks can erase
   * an intervening loss. A generation preserves the boundary; the worker queries
   * the live DOM after retiring input to decide whether to reactivate. IME begin/end
   * mark their synchronous canvas/textarea focus moves as one internal handoff. */
  const int focus_bridge_bound = MAIN_THREAD_EM_ASM_INT({
    if (typeof globalThis.__bwFocusBridge !== "object") {
      var activeCanvas = null;
      var handoffDepth = 0;
      var sequence = 0;
      var lossGeneration = 0;

      var imeState = function () {
        var bridge = globalThis.__bwImeBridge;
        if (!bridge || typeof bridge.snapshot !== "function") {
          return null;
        }
        return bridge.snapshot();
      };
      var ownsNode = function (node, state) {
        return !!node && (node === activeCanvas ||
          (state && state.enabled === true &&
           node === document.querySelector("#bw-ime-input")));
      };
      var publishLoss = function () {
        sequence += 1;
        lossGeneration += 1;
        var publishFunction = Module["_bw_shell_focus_lost"];
        if (typeof publishFunction === "function") {
          publishFunction();
        }
      };

      document.addEventListener("blur", function (event) {
        if (!activeCanvas || handoffDepth !== 0) {
          return;
        }
        var state = imeState();
        if (ownsNode(event.target, state) && !ownsNode(event.relatedTarget, state)) {
          publishLoss();
        }
      }, true);
      var api = Object.freeze({
        schema: 1,
        bind: function (selector) {
          if (typeof Module["_bw_shell_focus_lost"] !== "function") {
            return false;
          }
          var canvas = document.querySelector(selector);
          if (!canvas) {
            return false;
          }
          activeCanvas = canvas;
          handoffDepth = 0;
          return true;
        },
        unbind: function (selector) {
          var canvas = document.querySelector(selector);
          if (!activeCanvas || activeCanvas !== canvas) {
            return false;
          }
          activeCanvas = null;
          handoffDepth = 0;
          return true;
        },
        beginHandoff: function () {
          handoffDepth += 1;
        },
        endHandoff: function () {
          if (handoffDepth > 0) {
            handoffDepth -= 1;
          }
        },
        snapshot: function () {
          return {
            schema: 1,
            bound: !!activeCanvas,
            handoffDepth: handoffDepth,
            sequence: sequence,
            lossGeneration: lossGeneration,
          };
        },
      });
      Object.defineProperty(globalThis, "__bwFocusBridge", {
        value: api,
        writable: false,
        configurable: false,
        enumerable: false,
      });
    }
    var bridge = globalThis.__bwFocusBridge;
    return bridge && typeof bridge.bind === "function" && bridge.bind(UTF8ToString($0)) ? 1 : 0;
  }, canvas);
  if (!focus_bridge_bound) {
    std::fprintf(stderr, "GHOST-web: browser focus bridge is unavailable\n");
    return false;
  }

  /* Text clipboard bridge. GHOST's API is synchronous, but navigator.clipboard is
   * promise-based and this system runs on the PROXY_TO_PTHREAD WM worker. Keep the
   * latest ordinary text clipboard value on the browser main thread instead:
   *
   * - a trusted DOM `paste` event publishes its synchronous clipboardData before
   *   Emscripten's queued worker key callback is dispatched;
   * - putClipboard synchronously copies Blender's borrowed pointer into this realm,
   *   then starts the browser write without retaining the Wasm pointer;
   * - getClipboard synchronously proxies here and allocates the GHOST-owned UTF-8
   *   result from the shared Wasm allocator.
   *
   * Pointer-down refresh is permission-gated, so an already-authorized browser can
   * refresh before a menu-driven Paste without prompting on ordinary interaction.
   * Keyboard paste does not require that permission: its trusted paste event is the
   * authoritative path. */
  MAIN_THREAD_EM_ASM({
    if (typeof globalThis.__bwTextClipboardBridge !== "object") {
      var clipboardText = null;
      var sequence = 0;
      var lastSource = "none";
      var writeStatus = "idle";
      var readStatus = "event-only";
      var readPending = false;
      var writeRequest = 0;

      var publish = function (text, source) {
        clipboardText = String(text);
        lastSource = source;
        sequence += 1;
      };

      var refreshIfGranted = function () {
        if (readPending || typeof navigator === "undefined" || !navigator.clipboard ||
            typeof navigator.clipboard.readText !== "function" || !navigator.permissions ||
            typeof navigator.permissions.query !== "function") {
          return;
        }
        readPending = true;
        var startedAt = sequence;
        navigator.permissions.query({name: "clipboard-read"}).then(function (permission) {
          if (!permission || permission.state !== "granted") {
            readStatus = permission ? permission.state : "unavailable";
            return null;
          }
          readStatus = "pending";
          return navigator.clipboard.readText().then(function (text) {
            if (sequence === startedAt) {
              publish(text, "clipboard-read");
              readStatus = "fulfilled";
            }
            else {
              readStatus = "superseded";
            }
          });
        }).catch(function () {
          readStatus = "rejected";
        }).finally(function () {
          readPending = false;
        });
      };

      var api = Object.freeze({
        schema: 1,
        readForBlender: function () {
          return clipboardText;
        },
        writeFromBlender: function (text) {
          publish(text, "blender");
          var request = ++writeRequest;
          if (typeof navigator === "undefined" || !navigator.clipboard ||
              typeof navigator.clipboard.writeText !== "function") {
            writeStatus = "unavailable";
            return;
          }
          writeStatus = "pending";
          navigator.clipboard.writeText(clipboardText).then(function () {
            if (request === writeRequest) {
              writeStatus = "fulfilled";
            }
          }).catch(function () {
            if (request === writeRequest) {
              writeStatus = "rejected";
            }
          });
        },
        refreshIfGranted: refreshIfGranted,
        snapshot: function () {
          return {
            schema: 1,
            sequence: sequence,
            source: lastSource,
            utf8Bytes: clipboardText === null ?
                null :
                new TextEncoder().encode(clipboardText).length,
            writeStatus: writeStatus,
            readStatus: readStatus,
          };
        },
      });
      Object.defineProperty(globalThis, "__bwTextClipboardBridge", {
        value: api,
        writable: false,
        configurable: false,
        enumerable: false,
      });
      document.addEventListener("paste", function (event) {
        if (event.clipboardData) {
          publish(event.clipboardData.getData("text/plain"), "paste-event");
          readStatus = "event";
        }
      }, true);
      document.addEventListener("pointerdown", refreshIfGranted, true);
    }
  });

  size_t failed_position = 0;
  EMSCRIPTEN_RESULT failed_result = EMSCRIPTEN_RESULT_SUCCESS;
  const bool registration_succeeded =
      ghost_web::sequential_registration_transaction<kWebCallbackCount>(
      [&](const size_t position) {
        EMSCRIPTEN_RESULT result = EMSCRIPTEN_RESULT_INVALID_PARAM;
        switch (position) {
          case 0:
            /* Capture continuous motion for an owned drag even after it leaves
             * the canvas; cb_mousemove filters unrelated page motion. */
            result = emscripten_set_mousemove_callback(win, user_data, true, cb_mousemove);
            break;
          case 1:
            result = emscripten_set_mousedown_callback(canvas, user_data, false, cb_mousebtn);
            break;
          case 2:
            /* Capture the terminal half of a Blender-owned press across the
             * browser viewport. cb_mousebtn filters releases with no matching
             * tracked press, preserving ordinary page input ownership. */
            result = emscripten_set_mouseup_callback(win, user_data, true, cb_mousebtn);
            break;
          case 3:
            result = emscripten_set_wheel_callback(canvas, user_data, false, cb_wheel);
            break;
          case 4:
            result = emscripten_set_contextmenu_callback(
                canvas, user_data, false, cb_contextmenu);
            break;
          case 5:
            result = emscripten_set_focus_callback(canvas, user_data, false, cb_canvas_focus);
            break;
          case 6:
            result = emscripten_set_blur_callback(canvas, user_data, false, cb_canvas_blur);
            break;
          case 7:
            /* Canvas blur alone cannot observe a tab/browser-window loss while
             * Blender's hidden IME textarea owns focus. Window focus listeners
             * close that half of the logical focus domain. */
            result = emscripten_set_focus_callback(win, user_data, false, cb_window_focus);
            break;
          case 8:
            result = emscripten_set_blur_callback(win, user_data, false, cb_window_blur);
            break;
          case 9:
            result = emscripten_set_pointerlockchange_callback(
                EMSCRIPTEN_EVENT_TARGET_DOCUMENT, user_data, false, cb_pointerlockchange);
            break;
          case 10:
            result = emscripten_set_pointerlockerror_callback(
                EMSCRIPTEN_EVENT_TARGET_DOCUMENT, user_data, false, cb_pointerlockerror);
            break;
          case 11:
            /* Keyboard ownership follows Blender's DOM focus domain. Keep the
             * canvas target exact so unrelated page controls remain excluded. */
            result = emscripten_set_keydown_callback(canvas, user_data, false, cb_key);
            break;
          case 12:
            result = emscripten_set_keyup_callback(canvas, user_data, false, cb_key);
            break;
#ifdef WITH_INPUT_IME
          case 13:
            /* The hidden textarea owns focus during every ordinary Blender text
             * edit. Its earlier main-thread listener suppresses active-composition
             * process keys; only non-composing keys reach these raw callbacks. */
            result = emscripten_set_keydown_callback(
                kImeInputSelector, user_data, false, cb_key);
            break;
          case 14:
            result = emscripten_set_keyup_callback(
                kImeInputSelector, user_data, false, cb_key);
            break;
          case 15:
#else
          case 13:
#endif
            result = emscripten_set_resize_callback(win, user_data, false, cb_resize);
            break;
        }
        if (result == EMSCRIPTEN_RESULT_SUCCESS) {
          return true;
        }
        failed_position = position;
        failed_result = result;
        return false;
      },
      [&](const size_t registered_count) {
        const bool removed =
            remove_html5_callback_prefix(canvas, win, user_data, registered_count);
        MAIN_THREAD_EM_ASM({
          var bridge = globalThis.__bwFocusBridge;
          if (bridge && typeof bridge.unbind === "function") {
            bridge.unbind(UTF8ToString($0));
          }
        }, canvas);
        std::fprintf(stderr,
                     "GHOST-web: HTML5 callback registration %zu/%zu failed (result %d); "
                     "prefix rollback %s\n",
                     failed_position + 1,
                     kWebCallbackCount,
                     int(failed_result),
                     removed ? "succeeded" : "failed");
      },
      [&]() {
        callback_user_data_ = user_data;
        g_callback_system.store(this, std::memory_order_release);
        g_callback_registration.store(user_data, std::memory_order_release);
        callbacks_registered_ = true;
        /* The shell may have focused the canvas before callback registration.
         * Seed de-duplication from the live DOM without manufacturing an event. */
        browser_focus_loss_generation_ =
            g_browser_focus_loss_generation.load(std::memory_order_acquire);
        browser_focus_active_ = browserFocusIsOwned();
      });
  return registration_succeeded;
}

void GHOST_SystemWeb::unregisterCanvasCallbacks()
{
  browser_focus_active_ = false;
  if (!callbacks_registered_) {
    return;
  }
  const char *canvas = canvas_selector_.c_str();
  const char *win = EMSCRIPTEN_EVENT_TARGET_WINDOW;
  MAIN_THREAD_EM_ASM({
    var bridge = globalThis.__bwFocusBridge;
    if (bridge && typeof bridge.unbind === "function") {
      bridge.unbind(UTF8ToString($0));
    }
  }, canvas);
  void *expected_registration = callback_user_data_;
  if (g_callback_registration.compare_exchange_strong(
          expected_registration, nullptr, std::memory_order_acq_rel, std::memory_order_acquire))
  {
    GHOST_SystemWeb *expected_system = this;
    g_callback_system.compare_exchange_strong(
        expected_system, nullptr, std::memory_order_acq_rel, std::memory_order_acquire);
  }
  const bool removed =
      remove_html5_callback_prefix(canvas, win, callback_user_data_, kWebCallbackCount);
  callback_user_data_ = nullptr;
  callbacks_registered_ = false;
  if (!removed) {
    std::fprintf(stderr, "GHOST-web: one or more HTML5 callbacks failed to unregister\n");
  }
}

bool GHOST_SystemWeb::processEvents(bool /*waitForEvent*/)
{
  /* Browser input arrives asynchronously via the HTML5 callbacks, which enqueue
   * GHOST events immediately. We cannot block the browser main thread, so
   * waitForEvent is ignored; report whether anything is queued for dispatch. */
  GHOST_EventManager *em = getEventManager();

  /* Reconcile focus-domain facts published synchronously in the DOM event turn.
   * This must precede ordinary input dispatch so a hidden rapid blur boundary
   * retires held state before later input from the reacquired canvas is handled. */
  reconcilePublishedBrowserFocus();

#ifdef WITH_INPUT_IME
  /* Composition messages cross from the DOM main thread through a bounded
   * ownership queue; materialize GHOST events only here on the WM worker. */
  ghost_web_bridge::poll_ime(*this);
#endif

  /* ghost-keepalive: count every WM main-loop iteration (this is called once per tick from
   * wm_window_events_process). Exported via bw_wm_tick_count for the liveness proof. */
  g_wm_tick_count.fetch_add(1u, std::memory_order_relaxed);
  /* Input pending for dispatch THIS tick (mouse / key / wheel / resize / focus), sampled
   * before the boot-heartbeat may push its own event - used as a keepalive activity signal. */
  const bool had_input = (em != nullptr) && (em->getNumEvents() > 0);

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

      /* A size event relayouts Blender's areas but does not itself guarantee that every
       * retained region is redrawn. Re-arm the same bounded ordinary-WindowUpdate episode
       * used for asynchronously settled WebGPU draws so the new extent paints at idle
       * without waiting for unrelated user input. */
      ghost_web::request_redraw_retry();

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

  /* Bounded asynchronous-draw recovery. Browser Dawn publishes shader modules, explicit layouts,
   * pipelines, and scoped resources after the draw that first requested them has already returned.
   * Their readiness generation requests an ordinary full-screen update so every dropped region is
   * retried without user input. The boot burst discovers visible lazy variants; resource readiness
   * can rearm a completed burst but cannot extend an active one past the 180-tick hard ceiling.
   * Real input separately restarts one full coalesced tail after its last callback; repeated
   * draw-drop signals remain acknowledged without rearming at the ceiling. */
  const uint64_t redraw_episode_generation = ghost_web::redraw_episode_generation();
  const uint64_t barrier_completion_generation =
      ghost_web::redraw_present_barrier_completion_generation();
  if (barrier_completion_generation != redraw_present_barrier_completion_seen_) {
    redraw_present_barrier_completion_seen_ = barrier_completion_generation;
    if (ghost_web::redraw_present_barrier_completed_episode() == redraw_episode_generation) {
      /* The accepted resize frame is now on the surface. End this synthetic episode so later
       * ticks cannot queue and present another intermediate frame behind it. A separately
       * published shader-readiness generation may still start its own bounded recovery. */
      redraw_heartbeat_ = ghost_web::FIRST_PIXEL_SETTLE_TICKS;
      ghost_web::redraw_trace_finish(redraw_episode_generation);
    }
  }
  const uint64_t redraw_retry_generation = ghost_web::redraw_retry_generation();
  const uint64_t input_redraw_generation = ghost_web::input_redraw_retry_generation();
  const bool redraw_recovery_requested =
      window_ != nullptr &&
      ghost_web::redraw_recovery_tick(redraw_retry_generation,
                                      redraw_retry_generation_seen_,
                                      redraw_episode_generation,
                                      redraw_episode_generation_seen_,
                                      ghost_web::redraw_drop_generation(),
                                      redraw_drop_generation_seen_,
                                      input_redraw_generation,
                                      input_redraw_retry_generation_seen_,
                                      redraw_heartbeat_);
  const uint64_t input_redraw_admitted_generation =
      ghost_web::input_redraw_admitted_count();
  const bool input_redraw_pending_admission =
      input_redraw_generation != input_redraw_admitted_generation;
  const uint64_t present_replay_generation = ghost_web::present_replay_generation();
  const bool present_replay_pending =
      present_replay_generation != present_replay_generation_seen_;
  const bool redraw_update_requested = redraw_recovery_requested || present_replay_pending;
  const bool redraw_update_admitted =
      window_ != nullptr && ghost_web::filter_redraw_present_barrier_update(
                                redraw_episode_generation, redraw_update_requested);
  if (redraw_update_admitted) {
    pushEvent(
        std::make_unique<GHOST_Event>(getMilliSeconds(), GHOST_kEventWindowUpdate, window_));
    if (input_redraw_pending_admission) {
      ghost_web::note_input_redraw_admitted(input_redraw_generation);
      const uint64_t terminal_generation = ghost_web::input_redraw_terminal_count();
      if (terminal_generation > input_redraw_admitted_generation &&
          input_redraw_generation >= terminal_generation)
      {
        static uint32_t input_redraw_admitted_log_count = 0;
        if (input_redraw_admitted_log_count < 64) {
          std::printf("[bw] GHOST-input-redraw admitted input=%llu terminal=%llu "
                      "retry=%llu episode=%llu present=%llu\n",
                      static_cast<unsigned long long>(input_redraw_generation),
                      static_cast<unsigned long long>(terminal_generation),
                      static_cast<unsigned long long>(redraw_retry_generation),
                      static_cast<unsigned long long>(redraw_episode_generation),
                      static_cast<unsigned long long>(ghost_web::present_count()));
          input_redraw_admitted_log_count++;
        }
      }
    }
    if (present_replay_pending) {
      /* Consume only after the ordinary WM update is admitted. A resize barrier may temporarily
       * withhold it, but cannot lose the request at the generic recovery heartbeat ceiling. */
      present_replay_generation_seen_ = present_replay_generation;
    }
  }
  else if (window_ != nullptr && redraw_update_requested && input_redraw_pending_admission) {
    const uint64_t terminal_generation = ghost_web::input_redraw_terminal_count();
    static uint64_t input_redraw_withheld_terminal_seen = 0;
    static uint32_t input_redraw_withheld_log_count = 0;
    if (terminal_generation > input_redraw_admitted_generation &&
        terminal_generation != input_redraw_withheld_terminal_seen &&
        input_redraw_withheld_log_count < 32)
    {
      input_redraw_withheld_terminal_seen = terminal_generation;
      std::printf("[bw] GHOST-input-redraw withheld input=%llu terminal=%llu "
                  "retry=%llu episode=%llu barrier=%d/%d\n",
                  static_cast<unsigned long long>(input_redraw_generation),
                  static_cast<unsigned long long>(terminal_generation),
                  static_cast<unsigned long long>(redraw_retry_generation),
                  static_cast<unsigned long long>(redraw_episode_generation),
                  ghost_web::redraw_present_barrier_is_scheduled() ? 1 : 0,
                  ghost_web::redraw_present_barrier_is_ready() ? 1 : 0);
      input_redraw_withheld_log_count++;
    }
  }

  /* --- Idle keepalive (ghost-keepalive) ---------------------------------------------
   * Convert this same WM main loop from present-gated requestAnimationFrame to setTimeout
   * scheduling so it keeps ticking at idle (see the g_keepalive_* block above and
   * notes/ghost-keepalive.md). setTimeout on a worker is NOT present-gated, so events,
   * bpy.app.timers, and the ADR-007 kick-then-consume GPU futures (AllowSpontaneous
   * completions, r31) keep resolving even with nothing on screen changing. Crucially this
   * does NOT force a present: wm_draw_update (run later in the same tick) only composites when
   * something is tagged, so at true idle no frame is submitted - the keepalive pumps events,
   * it never tag_redraw()s. It runs at a fast interval while anything is happening (boot,
   * input, or a frame was drawn since the last tick) and backs off to a low idle interval
   * after a grace period so idle CPU stays negligible and the GPU is untouched. This runs on
   * the WM worker (same thread as WM_main), the only legal caller of the timing API for this
   * loop; calling it from inside the loop callback updates scheduling for subsequent ticks.
   * When disabled (?keepalive=0) the loop is left on rAF = the pre-fix A/B baseline. */
  if (g_keepalive_enabled.load(std::memory_order_relaxed)) {
    const double now = emscripten_get_now();
    const uint64_t presents = ghost_web::present_count();
    const bool drew = (presents != last_present_count_);
    last_present_count_ = presents;
    const bool booting = (redraw_heartbeat_ < 180u);
    if (drew || booting || had_input) {
      last_activity_ms_ = now;
    }
    const int32_t active_ms = g_keepalive_active_ms.load(std::memory_order_relaxed);
    const int32_t idle_ms = g_keepalive_idle_ms.load(std::memory_order_relaxed);
    const bool active = (now - last_activity_ms_) < KEEPALIVE_GRACE_MS;
    const int32_t desired_ms = active ? active_ms : idle_ms;
    if (desired_ms != current_timing_ms_) {
      /* EM_TIMING_SETTIMEOUT (0): schedule the loop via the worker's setTimeout, interval in
       * ms. The first switch (current_timing_ms_ == -1) happens on tick 0, so the loop never
       * relies on rAF and cannot stall. */
      emscripten_set_main_loop_timing(EM_TIMING_SETTIMEOUT, desired_ms);
      current_timing_ms_ = desired_ms;
    }
  }

  return (em != nullptr) && (em->getNumEvents() > 0);
}

GHOST_TSuccess GHOST_SystemWeb::getModifierKeys(GHOST_ModifierKeys &keys) const
{
  keys = modifiers_;
  return GHOST_kSuccess;
}

namespace {

void reconcile_modifier_pair(GHOST_ModifierKeys &keys,
                             const GHOST_TModifierKey left,
                             const GHOST_TModifierKey right,
                             const bool held)
{
  if (!held) {
    keys.set(left, false);
    keys.set(right, false);
    return;
  }
  if (!keys.get(left) && !keys.get(right)) {
    /* Mouse and wheel events expose only aggregate modifier flags. A missing
     * key history cannot identify the side, so retain the established fallback. */
    keys.set(left, true);
  }
}

}  // namespace

void GHOST_SystemWeb::requestInputRedrawRetry(const char *terminal_kind,
                                              const uint32_t terminal_code)
{
  /* Input can expose a region whose first-use browser resource was not ready during the
   * preceding bounded burst. Publish a distinct input-tail generation in addition to the
   * aggregate retry edge: callbacks observed in one WM tick coalesce, and the last real input
   * always leaves one complete bounded recovery budget without entering resize's barrier. */
  const uint64_t episode_before = ghost_web::redraw_episode_generation();
  const uint64_t input_generation = ghost_web::request_input_redraw_retry();
  const uint64_t episode_after = ghost_web::redraw_episode_generation();
  if (terminal_kind != nullptr) {
    ghost_web::note_input_redraw_terminal(input_generation);
    static uint32_t input_redraw_terminal_log_count = 0;
    if (input_redraw_terminal_log_count < 64) {
      std::printf("[bw] GHOST-input-redraw terminal kind=%s code=%u input=%llu "
                  "admitted=%llu retry=%llu episode=%llu episode_changed=%d\n",
                  terminal_kind,
                  terminal_code,
                  static_cast<unsigned long long>(input_generation),
                  static_cast<unsigned long long>(ghost_web::input_redraw_admitted_count()),
                  static_cast<unsigned long long>(ghost_web::redraw_retry_generation()),
                  static_cast<unsigned long long>(episode_after),
                  episode_after != episode_before ? 1 : 0);
      input_redraw_terminal_log_count++;
    }
  }
}

void GHOST_SystemWeb::noteButton(const GHOST_TButton button, const bool down)
{
  if (button == GHOST_kButtonMaskNone) {
    return;
  }
  const bool was_down = buttons_.get(button);
  buttons_.set(button, down);
  if (was_down != down) {
    ghost_web::note_input_button(uint32_t(button), down);
  }
}

void GHOST_SystemWeb::noteModifierFlags(const bool ctrl,
                                        const bool shift,
                                        const bool alt,
                                        const bool meta)
{
  reconcile_modifier_pair(modifiers_,
                          GHOST_kModifierKeyLeftControl,
                          GHOST_kModifierKeyRightControl,
                          ctrl);
  reconcile_modifier_pair(
      modifiers_, GHOST_kModifierKeyLeftShift, GHOST_kModifierKeyRightShift, shift);
  reconcile_modifier_pair(
      modifiers_, GHOST_kModifierKeyLeftAlt, GHOST_kModifierKeyRightAlt, alt);
  reconcile_modifier_pair(modifiers_, GHOST_kModifierKeyLeftOS, GHOST_kModifierKeyRightOS, meta);
}

void GHOST_SystemWeb::noteModifierKey(const GHOST_TKey key, const bool down)
{
  switch (key) {
    case GHOST_kKeyLeftShift:
      modifiers_.set(GHOST_kModifierKeyLeftShift, down);
      break;
    case GHOST_kKeyRightShift:
      modifiers_.set(GHOST_kModifierKeyRightShift, down);
      break;
    case GHOST_kKeyLeftControl:
      modifiers_.set(GHOST_kModifierKeyLeftControl, down);
      break;
    case GHOST_kKeyRightControl:
      modifiers_.set(GHOST_kModifierKeyRightControl, down);
      break;
    case GHOST_kKeyLeftAlt:
      modifiers_.set(GHOST_kModifierKeyLeftAlt, down);
      break;
    case GHOST_kKeyRightAlt:
      modifiers_.set(GHOST_kModifierKeyRightAlt, down);
      break;
    case GHOST_kKeyLeftOS:
      modifiers_.set(GHOST_kModifierKeyLeftOS, down);
      break;
    case GHOST_kKeyRightOS:
      modifiers_.set(GHOST_kModifierKeyRightOS, down);
      break;
    default:
      break;
  }
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
   * clipboard, desktop sampling, decoration styles, hyper key, generated cursors,
   * multi-monitor placement, window path) plus WindowPosition (a canvas has no
   * OS-level position), synchronous front-buffer reads (browser mapping settles
   * asynchronously), physical trackpad direction (DOM wheel deltas are already
   * preference-adjusted), and server-side decorations (there is no OS window frame).
   * IME and RGBA cursors are supported through browser-main bridges. */
  return GHOST_TCapabilityFlag(
      GHOST_CAPABILITY_FLAG_ALL &
      ~(GHOST_kCapabilityWindowPosition | GHOST_kCapabilityCursorWarp |
        GHOST_kCapabilityClipboardPrimary | GHOST_kCapabilityGPUReadFrontBuffer |
        GHOST_kCapabilityClipboardImage |
        GHOST_kCapabilityDesktopSample | GHOST_kCapabilityTrackpadPhysicalDirection |
        GHOST_kCapabilityWindowDecorationStyles |
        GHOST_kCapabilityKeyboardHyperKey | GHOST_kCapabilityCursorGenerator |
        GHOST_kCapabilityMultiMonitorPlacement | GHOST_kCapabilityWindowPath |
        GHOST_kCapabilityWindowDecorationServerSide));
}

char *GHOST_SystemWeb::getClipboard(bool selection) const
{
  /* Primary selection is intentionally unsupported and absent from capabilities.
   * For the ordinary clipboard, allocate exactly as the desktop backends do: the
   * caller owns the returned null-terminated string and releases it with free(). */
  return static_cast<char *>(MAIN_THREAD_EM_ASM_PTR({
    if ($0 || typeof globalThis.__bwTextClipboardBridge !== "object") {
      return 0;
    }
    var text = globalThis.__bwTextClipboardBridge.readForBlender();
    if (text === null) {
      return 0;
    }
    var size = lengthBytesUTF8(text) + 1;
    var result = _malloc(size);
    if (!result) {
      return 0;
    }
    stringToUTF8(text, result, size);
    return result;
  }, selection ? 1 : 0));
}

void GHOST_SystemWeb::putClipboard(const char *buffer, bool selection) const
{
  if (selection || buffer == nullptr) {
    return;
  }
  /* This is a synchronous main-thread proxy on purpose: UTF8ToString copies the
   * borrowed GHOST pointer before this method returns. The later clipboard promise
   * owns only the resulting JavaScript string. */
  MAIN_THREAD_EM_ASM({
    if (typeof globalThis.__bwTextClipboardBridge === "object") {
      globalThis.__bwTextClipboardBridge.writeFromBlender(UTF8ToString($0));
    }
  }, buffer);
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

bool GHOST_SystemWeb::refreshCanvasClientRect()
{
  const char *selector = canvas_selector_.c_str();
  std::array<int32_t, 4> rect = {};
  MAIN_THREAD_EM_ASM(
      {
        const canvas = document.querySelector(UTF8ToString($0));
        if (canvas) {
          const bounds = canvas.getBoundingClientRect();
          HEAP32[($1 >> 2) + 0] = bounds.left | 0;
          HEAP32[($1 >> 2) + 1] = bounds.top | 0;
          HEAP32[($1 >> 2) + 2] = Math.ceil(bounds.width);
          HEAP32[($1 >> 2) + 3] = Math.ceil(bounds.height);
        }
      },
      selector,
      rect.data());
  if (rect[2] <= 0 || rect[3] <= 0) {
    return false;
  }
  canvas_client_left_ = rect[0];
  canvas_client_top_ = rect[1];
  canvas_client_width_ = rect[2];
  canvas_client_height_ = rect[3];
  return true;
}

bool GHOST_SystemWeb::windowToCanvasCoordinates(const int32_t client_x,
                                                const int32_t client_y,
                                                int32_t &canvas_x,
                                                int32_t &canvas_y) const
{
  canvas_x = client_x - canvas_client_left_;
  canvas_y = client_y - canvas_client_top_;
  return canvas_client_width_ > 0 && canvas_client_height_ > 0 && canvas_x >= 0 &&
         canvas_y >= 0 && canvas_x < canvas_client_width_ && canvas_y < canvas_client_height_;
}

bool GHOST_SystemWeb::browserFocusIsOwned() const
{
  const char *selector = canvas_selector_.c_str();
  return MAIN_THREAD_EM_ASM_INT(
             {
               if (typeof document === "undefined" || !document.hasFocus()) {
                 return 0;
               }
               const active = document.activeElement;
               const canvas = document.querySelector(UTF8ToString($0));
               if (active === canvas) {
                 return 1;
               }
               const bridge = globalThis.__bwImeBridge;
               if (!bridge || typeof bridge.snapshot !== "function") {
                 return 0;
               }
               const state = bridge.snapshot();
               return state && state.enabled === true && state.focused === true ? 1 : 0;
             },
             selector) != 0;
}

void GHOST_SystemWeb::reconcilePublishedBrowserFocus()
{
  const uint32_t loss_generation =
      g_browser_focus_loss_generation.load(std::memory_order_acquire);
  if (window_ == nullptr) {
    browser_focus_loss_generation_ = loss_generation;
    return;
  }

  if (loss_generation == browser_focus_loss_generation_) {
    return;
  }
  browser_focus_loss_generation_ = loss_generation;

  if (browser_focus_active_) {
    publish_browser_focus_transition(this, false);
  }
  if (browserFocusIsOwned()) {
    publish_browser_focus_transition(this, true);
  }
}

void GHOST_SystemWeb::acknowledgePublishedBrowserFocusLoss()
{
  browser_focus_loss_generation_ =
      g_browser_focus_loss_generation.load(std::memory_order_acquire);
}

bool GHOST_SystemWeb::transitionBrowserFocus(const bool focused)
{
  if (browser_focus_active_ == focused) {
    return false;
  }
  browser_focus_active_ = focused;
  return true;
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
    GHOST_Context *context = new GHOST_ContextWGPUWeb(
        params, canvas_selector_.c_str(), ghost_web::DrawingContextMode::DeviceOnly);
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

GHOST_TSuccess GHOST_SystemWeb::disposeWindow(GHOST_IWindow *window)
{
  if (window != window_ || !validWindow(window)) {
    return GHOST_System::disposeWindow(window);
  }

  GHOST_WindowWeb *active_window = window_;
  /* Remove an accepted deferred request or active browser lock while the old
   * window is still a valid callback target. Any later outcome is owner-gated. */
  active_window->releasePointerLock();
#ifdef WITH_INPUT_IME
  /* Blur/commit while the old window is still the event target, then materialize
   * any synchronously published composition transitions. The base disposal below
   * removes those window-owned events before deleting the window. */
  active_window->endIME();
  ghost_web_bridge::poll_ime(*this);
#endif

  /* Detach every callback-facing pointer before the base class deletes the
   * concrete window. A queued browser event can now observe only a null active
   * window, never freed storage. A later createWindow() rebinds the callbacks. */
  window_ = nullptr;
  unregisterCanvasCallbacks();
  buttons_ = GHOST_Buttons();
  noteModifierFlags(false, false, false, false);

  const GHOST_TSuccess result = GHOST_System::disposeWindow(window);
  if (result != GHOST_kSuccess) {
    /* validWindow() made this path defensive-only, but keep the system usable if
     * a platform/base failure does occur before ownership transfers. */
    window_ = active_window;
    registerCanvasCallbacks();
  }
  return result;
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
  /* One OffscreenCanvas backs one callback, input, hit-test, and presentation
   * owner. Publishing another live GHOST window would split those owners from
   * GHOST_WindowManager, so reject it before constructing a context. A later
   * create remains valid after disposeWindow() clears window_. */
  if (window_ != nullptr) {
    return nullptr;
  }

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
  const std::string previous_canvas_selector = canvas_selector_;
  bool publication_succeeded = true;
  GHOST_WindowWeb *result = ghost_web::window_publish_if_valid(
      window,
      [](GHOST_WindowWeb *invalid_window) { delete invalid_window; },
      [&](GHOST_WindowWeb *valid_window) {
        if (window_ == nullptr) {
          window_ = valid_window;
          /* Bind HTML5 input to this (first) valid window's canvas. */
          canvas_selector_ = valid_window->getCanvasSelector();
          if (!registerCanvasCallbacks()) {
            window_ = nullptr;
            canvas_selector_ = previous_canvas_selector;
            publication_succeeded = false;
            return;
          }
          redraw_retry_generation_seen_ = ghost_web::redraw_retry_generation();
          input_redraw_retry_generation_seen_ = ghost_web::input_redraw_retry_generation();
          redraw_episode_generation_seen_ = ghost_web::redraw_episode_generation();
          redraw_drop_generation_seen_ = ghost_web::redraw_drop_generation();
          redraw_present_barrier_completion_seen_ =
              ghost_web::redraw_present_barrier_completion_generation();
          present_replay_generation_seen_ = ghost_web::present_replay_generation();
          redraw_heartbeat_ = 0;
        }
        if (GHOST_WindowManager *wm = getWindowManager()) {
          wm->addWindow(valid_window);
          wm->setActiveWindow(valid_window);
        }
        /* Callback registration can occur after the shell has already focused
         * the canvas. Its live-DOM seed suppresses a duplicate HTML focus
         * callback, so publish the initial GHOST activation only after the
         * window manager owns the window. Without this event Blender leaves
         * wmWindow::active false and re-queries a later global cursor position
         * on every queued button-down. */
        if (browser_focus_active_) {
          ghost_web_bridge::on_focus(*this, true);
        }
        /* Deliver an initial size/expose event, exactly as the native back-ends do when a
         * window is first mapped (SDL posts SDL_WINDOWEVENT_EXPOSED/SIZE_CHANGED; X11 posts
         * MapNotify + ConfigureNotify) — that first event is what makes Blender's WM build the
         * drawable and paint frame one. GHOST_WindowWeb posted none, so at idle WM_main had no
         * pending redraw and the canvas stayed black until the first mouse move happened to
         * force a refresh (which only then reconciled the real client bounds). Posting the
         * window-size event here makes the first composite happen unprompted and deterministic
         * — a prerequisite for a headless golden capture, which would otherwise see black. */
        pushEvent(std::make_unique<GHOST_Event>(
            getMilliSeconds(), GHOST_kEventWindowSize, valid_window));
      });
  if (!publication_succeeded) {
    delete result;
    return nullptr;
  }
  return result;
}

GHOST_IWindow *GHOST_SystemWeb::getWindowUnderCursor(const int32_t x, const int32_t y)
{
  if (window_ == nullptr) {
    return nullptr;
  }

  /* GHOST_ISystem.hh requires nullptr when no owned window contains the supplied
   * screen point. Web screen/client coordinates share the canvas origin, so the
   * base GHOST_System::getWindowUnderCursor() bounds rule applies directly. */
  GHOST_Rect bounds;
  window_->getClientBounds(bounds);
  return bounds.isInside(x, y) ? window_ : nullptr;
}
