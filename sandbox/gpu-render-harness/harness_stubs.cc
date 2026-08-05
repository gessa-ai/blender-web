/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * HARNESS-ONLY stubs for the 5 externals the GPU module references but that live in
 * heavier modules (blenkernel globals, intern/eigen, draw) — none exercised by a
 * standalone offscreen triangle. The FULL blender binary links the real ones; this
 * TU exists only so the minimal render-harness closes without dragging blenkernel +
 * draw + eigen into the link. (notes/gpu-wasm-render-harness.md §closure.)
 *
 *  - blender::G / blender::U : the process globals. Real DNA types (correct layout,
 *    so gpu_context.cc's G.debug read hits the right offset), zero-initialised.
 *  - EIG_invert_m4_m4        : intern/eigen. Returning false makes blenlib's
 *    invert_m4_m4 take its (correct) non-Eigen fallback.
 *  - draw::DebugDraw::{clear_gpu_data,reset} : the GPU context's optional debug-draw
 *    hook (get()/acquire()/release() are header-inline and already resolved). */

#include "BKE_global.hh"
#include "DNA_userdef_types.h"

namespace blender {
Global G;
UserDef U;
}  // namespace blender

extern "C" bool EIG_invert_m4_m4(float /*inverse*/[4][4], const float /*matrix*/[4][4])
{
  return false; /* -> blenlib invert_m4_m4 uses its analytic fallback */
}

namespace blender::draw {
/* Minimal decl to mint the two out-of-line method symbols; empty bodies touch no
 * members, so the real (header-inline) DebugDraw instance is unaffected. */
class DebugDraw {
 public:
  void clear_gpu_data();
  void reset();
};
void DebugDraw::clear_gpu_data() {}
void DebugDraw::reset() {}
}  // namespace blender::draw
