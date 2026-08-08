/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup GHOST-web
 *
 * Shared display-state handshake between the browser MAIN thread (the shell) and the
 * PROXY_TO_PTHREAD WM worker that owns the OffscreenCanvas + WebGPU surface.
 *
 * The two live-window facts the WM worker cannot read on its own are:
 *
 *   1. `window.devicePixelRatio` - the worker has no `window`/`document`, so a bare
 *      DPR probe returns 1.0 and Blender's UI draws at half physical size on a HiDPI
 *      display (`U.pixelsize` stays 1 while the backing store is 2x).
 *   2. A live browser resize - after boot the `#canvas` is an OffscreenCanvas owned by
 *      this worker; only this worker may call `emscripten_set_canvas_element_size`, so
 *      the main thread cannot grow the backing store and the shell can only CSS-stretch
 *      (blur) or letterbox (black bars).
 *
 * Both are pushed from the shell via the EMSCRIPTEN_KEEPALIVE export `bw_shell_set_display`
 * (defined in GHOST_SystemWeb.cc), which the main thread may call safely: it only performs
 * relaxed/release atomic stores into shared wasm linear memory (SharedArrayBuffer under
 * -pthread). The WM worker consumes them here - DPR via #device_pixel_ratio() (fed to
 * getNativePixelSize/getClientBounds/getDPIHint), and the pending backing size via
 * #poll_pending_backing() once per WM tick (GHOST_SystemWeb::processEvents), where the
 * worker performs the actual canvas resize + surface reconfigure + GHOST_kEventWindowSize.
 */

#pragma once

#include <cstdint>

namespace ghost_web {

/** Device pixel ratio last posted by the shell (main thread). Defaults to 1.0 until the
 * shell posts a value; safe to call on any thread (a single relaxed atomic load). */
double device_pixel_ratio();

/** If the shell has posted a NEW target backing extent (physical pixels =
 * cssPx * devicePixelRatio) since the previous call, returns true and fills \a w / \a h.
 * Returns false when nothing changed. Single-consumer: call only from the canvas-owning
 * (WM) worker's per-tick poll. */
bool poll_pending_backing(int32_t &w, int32_t &h);

/** Total WebGPU presents (surface submits) since boot. Defined in GHOST_ContextWGPUWeb.cc
 * and bumped once per GHOST_ContextWGPUWeb::presentBackbuffer(). Read on the WM worker by
 * GHOST_SystemWeb::processEvents to tell whether a frame was drawn since the last tick
 * (idle-keepalive activity detection) and exported for the no-idle-burn proof
 * (bw_present_count). A single relaxed atomic load; safe to call on any thread. */
uint64_t present_count();

/** Called by GHOST_ContextWGPUWeb::presentBackbuffer() to record one present. */
void note_present();

}  // namespace ghost_web
