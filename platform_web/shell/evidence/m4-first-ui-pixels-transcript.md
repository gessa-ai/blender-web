<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4.T13 — Blender's UI renders in a browser tab (first pixels)

**Date:** 2026-08-06 (gpu-backend worker, round 16)
**Binary:** `build-wasm-windowed/bin/blender_browser.{wasm 922 MB, js, data 117 MB}`,
patches through **0095**.
**How:** real Chrome, `:8123/windowed.html`, argv `blender --factory-startup`
(NO `--background`), canvas `#canvas`, COOP/COEP (`crossOriginIsolated: true`),
device acquired on the WM worker (ADR-007, `features=22`).
**Evidence image:** `m4-first-ui-pixels-quicksetup-splash.png` (1800×1169, read back
from the live `#canvas` via `toDataURL`).

## Outcome

**Blender's interface composites end-to-end in the tab.** The captured frame is the
Blender **"Quick Setup" splash over the default Layout workspace**. Legible in the PNG:

- Quick Setup panel: **"Quick Setup"**, **"Theme: Blender Dark"**, **"Keymap: Blender"**,
  **"Mouse Select: Left / Right"**, **"Separate Action: Play"**, **"Continue"** — text
  glyphs, dropdown values and the blue arrow widgets all render.
- 3D-viewport header menus: **"Object Mode", "View", "Select", "Add", "Object"**.
- Bottom toolbar (transform/snap/overlay gizmo icons; viewport-shading mode buttons on
  the right), the **"Options"** side panel, editor-region borders, and the focused-window
  blue outline.
- An asset-library error dialog (red circle-X icon + text) appeared first and was
  dismissed with `Escape`, revealing the splash beneath — i.e. **input events over the
  canvas drive the UI** (mouse move, click, Escape all reached WM).

## Imperfections (characterized, NOT chased — outside the M4.T13 triplet)

1. **Y-flip (dominant):** the whole window is vertically mirrored (text upside-down,
   header at the bottom). ADR-005 corrected the offscreen-render orientation
   (clip-space + readback flips) but the **window-surface composite is not flipped** —
   the backbuffer is presented with WebGPU's top-down origin where Blender's window
   compositor assumes bottom-up. A window-composite flip is the fix; deferred (a distinct
   orientation task, not the bind/draw/backbuffer triplet).
2. **Splash artwork is black:** `IMB_load_image_from_memory: unknown file-format
   (<splash screen>)` — the known imbuf reader gap. The splash *chrome* (text/widgets)
   renders; only the bitmap artwork is missing.
3. **Theme:** Blender Dark background (correct); no color-management surprises observed.
4. **Python C-ext debt (non-fatal, pre-existing):** `_multiprocessing` /
   `_sha3`/`_hashlib` (md5/sha1/blake2/sha3/shake) missing → `bl_pkg` register fails
   (caught by `addon_utils.enable`), and the "restore Asset Library backups" step raises
   the dialog above. Boot continues.
5. **OIIO `physical_memory` assert-print** — environmental, identical to headless.

## Main-loop health

- **Stable, no abort:** state pill `main loop (WM_main)`, `exit: —` throughout (20 s+
  observed, survives interaction). The T12 wall (`wgpu_batch.cc:249` draw_indirect abort)
  is gone; no uncaught exceptions; **zero Dawn validation warnings/errors** in the render
  path once the bind-group remap landed.
- Input: mouse move/click/Escape over `#canvas` reach WM and redraw the window.
- Memory: JS heap ~121 MB (wasm linear memory is separate, 512 MB initial). No leak
  signature observed over the session; a dedicated 60 s soak was not run this round.

## Backend fixes that produced the picture (this round, patches 0092-0095)

1. **`WGPUBatch::draw_indirect` / `multi_draw_indirect`** (0093) — real
   `DrawIndirect`/`DrawIndexedIndirect` (loop-emulated multi-draw). Cleared the first-UI
   abort.
2. **Draw/compute/immediate bind-group assembly completion** (0092): shared
   `WGPUContext::append_resource_bind_entries` (textures+samplers, storage buffers,
   VBO/IBO-as-SSBO, storage images, bound UBOs), **type-aware** (each entry matched to the
   layout kind, robust to stale binds), a `wgpu::Sampler` cache, and — the load-bearing
   fix for real UI shaders — a **frontend-slot → dense-binding remap**
   (`WGPUShader::remap_*_binding`): Blender binds resources at per-type create-info slots,
   but the WGPU backend flattens all classes into one dense group-0 space, so the widget
   SSBO bound at slot 0 belonged at dense binding 1. Plus `sampled_view()` now resolves
   texture **views** (so a bound view isn't dropped). Native gpu gate held **148/158**
   across every change.
3. **`WGPUContext::sync_backbuffer`** (0094) — wraps the window surface's per-frame
   `GetCurrentTexture()` as `back_left`/`front_left`'s colour attachment each `activate()`
   (mirrors `vk_context.cc:67`), so Blender draws into the presented surface. Guarded
   `__EMSCRIPTEN__ && !WITH_HEADLESS` (no-op for native/headless).
4. **Finite depth-clear** (0095) — `beginRenderPass` in emdawnwebgpu reads
   `depthClearValue` at descriptor-marshal time and **rejects the default
   `WGPU_DEPTH_CLEAR_VALUE_UNDEFINED` (NaN) even on `loadOp=Load`** — a browser-only trap
   native Dawn never hits (it ignores the value on Load). `begin_load_pass` now sets a
   finite far value; `submit_clear` / `WGPUTexture::clear` clamp non-finite inputs.

## Notes

- GHOST/shell required NO change this round (surface, device, OffscreenCanvas transfer,
  teal proof all from M4.T12). The teal surface-proof in `finishSetup` is overwritten by
  Blender's frame and left in place (it lives in platform_web, read-only reference).
