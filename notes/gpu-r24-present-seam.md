<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 24 (M4.T21) — present seam KILLED by construction; workspace composite blocked by a boot regression

Pin: Blender 5.2 `fbe6228777e7`; build `build-wasm-windowed` (-O2 -g, 884 MB) + patches through
**0109**. Rig = headed node-Playwright, bundled Chromium (both `chromium-1208`/v145 and
`chromium-1234`/v151 tested), `:8123/windowed.html`, CDP `page.screenshot` at exact 1280x720,
`deviceScaleFactor:1`. Env receipts: `visibilityState "visible"`, `crossOriginIsolated true`,
`navigator.gpu` adapter OK, canvas 1280x720, page rAF ~122/s.

## The present seam — FIXED (patch 0109 + GHOST present), Destroyed-texture 0/boot by construction

r23 named the M4 blocker: 725x/boot `Destroyed texture [… WebgpuSwapChainTexture] used in a
submit` — command buffers referencing the surface's per-frame `GetCurrentTexture()` submitted
after the browser auto-presented (and destroyed) it on the rAF yield. Chose recipe **(b)** — the
persistent-offscreen model — because it eliminates the whole family by construction:

- **patch 0109 (backend, `wgpu_context.cc::sync_backbuffer`)**: adopt the GHOST context's
  PERSISTENT offscreen back-buffer as `back_left`/`front_left`, NOT `surface.GetCurrentTexture()`.
  The backend now NEVER references the transient surface — every viewport/overlay/UI pass
  accumulates into a texture with no per-frame lifetime. `is_window_backbuffer` still returns
  true (flip_y stays false → upright), so orientation is preserved. Guarded
  `__EMSCRIPTEN__ && !WITH_HEADLESS` → native gpu census byte-identical (m3 5/5, 148/158,
  static_shaders 956/973 held).
- **GHOST (`platform_web/ghost`, owned files, not patched):**
  - `GHOST_ContextWGPUWeb`: owns the persistent offscreen (`backbuffer_`, BGRA8Unorm,
    RenderAttachment|TextureBinding|CopySrc), recreated on resize in `configureSurface` →
    `ensureBackbuffer`. `presentBackbuffer()` is a **render-pass blit** (fullscreen triangle,
    `textureLoad(fragCoord)` 1:1 upright, no sampler/flip) into the surface's current texture,
    submitted once per frame. Chosen over `CopyTextureToTexture` because **emdawnwebgpu rejects a
    `CopyDst` canvas surface** — the copy silently fails validation and the canvas stays on its
    last render-pass content (observed live: the canvas was stuck teal from the old surface-proof
    clear). Removed the M4.T12 teal "surface-proof" clear from `finishSetup` (it re-ran during
    boot and stomped presented frames).
  - `GHOST_WindowWeb::swapBufferRelease()` was a **stub returning `GHOST_kFailure`** — it never
    delegated to the drawing context, so `wm_draw`'s `wm_window_swap_buffer_release`
    (wm_draw.cc:1692) never reached the present. Now delegates to
    `getContext()->swapBufferRelease()` when a context exists (harness path unchanged). THIS was
    the missing wire; before it, `presentBackbuffer` was never called.

**VERIFIED:** with the seam dead, the WM-worker console shows the Destroyed-texture family at
**0/boot** (was 725x in r23). `presentBackbuffer frame 0` fires (present path reached). Native
census unaffected (m3 5/5).

## BLOCKER (not gpu-backend lane): the workspace never COMPOSITES — a boot/main-loop regression since r23

The M4 gate capture still FAILs. Comparator on the CDP compositor capture, exact 1280x720,
splash suppressed (`bpy.context.preferences.view.show_splash=False` via `?pyexpr=`):
```
bash sandbox/m4-golden-prep/compare_m4.sh <cand> workspace 1280x720
FAIL workspace_1280x720  Max error = 0.957 over: 921540 pixels (100%) over 0.016   (exit 1)
```
100% (was 35.5% in r23) because the canvas shows only its CSS background — the OffscreenCanvas
**never composites a single rendered frame** (not even the UI chrome r23 captured at 35.5%).

**This is NOT the present seam and NOT in the GPU backend.** Decisive A/B: restoring r23's EXACT
`sync_backbuffer` (surface-backed `back_left`, `git show HEAD:sandbox/lane-a-staging/webgpu/
wgpu_context.cc`) into the build tree and rebuilding **also renders black** (evidence
`m4-r24-r23code-black-1280x720.png`) — on both chromium v145 and v151. So r23's code that
produced the 35.5% workspace composite no longer does.

Signatures of the regression (reliable signals only — WM-worker stdout is dropped after early
boot, so per-frame printf counts are unreliable):
- Boot reaches `WM_main` (state pill), `--python-expr` runs (side effect confirmed).
- The single reliable draw signal (`presentBackbuffer frame 0` C-printf; canvas pixels) shows at
  most the first frame, then nothing composites.
- **NEW since r23**: `ModuleNotFoundError: No module named 'js'` during `bl_pkg` register
  (`_bpy_internal/http/downloader.py` → `requests` → `urllib3.contrib.emscripten.fetch` →
  `import js`). r23 failed EARLIER (`No module named 'requests'`); the requests wheel added in
  `679ebbf` (wheels.sh) now imports urllib3's emscripten backend, which needs Pyodide's `js`
  module. This is the only boot-payload change between r23 (`984414a`) and HEAD (`679ebbf`) that
  touches the windowed profile.

**Prime suspect for the driver (python-wasm lane):** the requests/urllib3 emscripten import path
introduced in the wheels change perturbed boot such that the WM redraw/composite no longer
completes. Recommended next step: boot the windowed build at the r23 payload (before the requests
wheel) and confirm the 35.5% composite returns; if so, the requests wheel / urllib3 emscripten
backend is the M4 regression and must be shimmed or excluded (Pyodide ships a `js` module; our
runtime does not).

## Receipts
- Patch 0109 (`wgpu_context.cc`) reverse-applies clean vs the build tree; series updated with
  full rationale; lane-a-staging mirror 0-drift. GHOST changes in `platform_web/ghost/`
  (GHOST_ContextWGPUWeb.{cc,hh}, GHOST_WindowWeb.cc) committed directly (owned, compiled directly
  — confirmed via build.ninja).
- m3 census GREEN 5/5 (148 PASS / 8 FAIL / 2 CRASH; static_shaders 956/973) — native gpu path
  byte-identical (all changes `__EMSCRIPTEN__`-guarded or platform_web-only).
- Comparator FAIL 100% (both capture paths blank; boot regression). Evidence:
  `platform_web/shell/evidence/m4-r24-{final-black,r23code-black}-1280x720.png`.
