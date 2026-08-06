<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 20 — cube-sequence live findings + the residual viewport blocker

Pin: Blender 5.2 `fbe6228777e7`; browser = emdawnwebgpu (M4 pin), real Chrome via the
Browser pane at `:8123/windowed.html`, canvas backing 1800x1169 (CSS 1240x720, dpr 2).
Boot: `blender_browser --factory-startup`, no `--background`, build-wasm-windowed with
patches through 0103 + the round-20 ghost surface-size commit.

## What WORKS live (verified this round)

- **Full Blender 5.2.0 UI composites** after the first input nudge: menubar, left
  toolbar, Properties editor (Cube transform correct), **Outliner shows Scene Collection
  -> Camera / Cube / Light** (scene DATA is intact), workspace tabs, timeline. Evidence:
  `platform_web/shell/evidence/m4-r20-ui-renders-viewport-flatbg.png` (full canvas).
- **Splash artwork renders** — the real datatoc'd lion PNG (Joanna Kobierska) + Quick
  Setup dialog, sharp and correct.
- **GPU-fallback dialog IS present live** ("Failed to load using Vulkan, using OpenGL
  instead"), contradicting the r19 not-reproducible-via-code-path trace. It is Blender's
  generic backend-fallback popup surfaced under the WebGPU backend; dismissable, non-fatal.
- **Task-2 surface determinism CONFIRMED**: `configureSurface` now queries the canvas and
  configures the surface to the live drawing-buffer extent. Live readback: surface ==
  canvas == 1800x1169 (the r19 1800-surface-vs-1280-canvas mismatch is gone). Capture at a
  fixed size is now reliable.
- Boot load health: reaches `WM_main`, `data: loaded`. Non-fatal boot noise: OIIO
  `physical_memory` assert (known), "Unable to find the Python binary" (multiprocessing),
  and **`ModuleNotFoundError: No module named 'cattrs'`** aborting `bl_pkg` addon register
  (remote-asset-library path) — a python-wasm payload gap, not gpu/ghost. First composite
  still needs an input event (hover/click); it is NOT unprompted at 1800x1169 this session.

## The residual blocker: the 3D VIEWPORT renders nothing (cube absent)

Measured on the live canvas (toDataURL readback, full 1800x1169):
- Viewport interior = **91.6% flat background RGB(56,56,56)**.
- Viewport CENTRE (240x240 and 60x60 boxes) = **0% content** — no cube.
- **0 selection-orange pixels** (clicking where the cube sits produced no outline),
  **~0 lit-grey pixels** (no shaded cube faces). Pressing Home (View All) did not change
  this. The only non-bg content in the sampled region is the bottom Timeline editor UI.

So the cube+grid are wholesale ABSENT, not merely dark — and **patch 0103 (explicit
pipeline layouts + depth sampleType = UnfilterableFloat), verified exact on native Dawn
(census 148/158 + static 956/973, explicit layouts engaged), did NOT produce a rendered
cube in the browser.** No M4 gate PNG exists this round.

### Root-cause hypothesis (ranked) for the next round

1. **Viewport-offscreen -> window-surface composite gap (most likely).** The editor UI
   (drawn directly into the window framebuffer) reaches the surface perfectly; the 3D
   viewport renders into a GPUViewport OFFSCREEN texture and is then blitted/composited
   into the window backbuffer. That composite is the browser-specific seam the native
   `GPUWebGPUTest` never exercises (its `framebuffer clear+cube 5/5` reads the offscreen
   back DIRECTLY, no window surface). The cube being absent even though it does NOT depend
   on the depth-read fix points here, not at 0103. Suspects: `WGPUContext::sync_backbuffer`
   / the GPUViewport-region blit into the surface backbuffer (wgpu_context.cc), and/or the
   ghost present seam.
2. **Browser-Dawn-specific drop of the offscreen viewport passes**, not visible from the
   main thread. The WM runs on a pthread worker; only explicit `std::printf` is proxied to
   the page console — **Dawn's uncaptured validation errors on the worker are NOT visible**
   from `read_console_messages`. No fallback warning ("not covered by interface map") and
   no Dawn error surfaced, but that is inconclusive given the worker-console gap. Next round
   should route the window context's device through an uncaptured-error callback that
   `printf`s (so worker Dawn errors reach the page console) BEFORE further diagnosis.

### Concrete next steps
- Add a `printf`ing uncaptured-error callback to the imported window device
  (GHOST_ContextWGPUWeb) so WM-worker Dawn validation errors become visible in the tab.
- Instrument `sync_backbuffer` / the GPUViewport-offscreen -> window-surface blit: confirm
  whether the viewport offscreen is (a) non-empty but not composited, or (b) empty because
  its passes drop in-browser. That disambiguates hypothesis 1 vs 2.
- Unrelated: register the missing `cattrs` (or stub the `bl_pkg` remote-library import) in
  the python-wasm payload to clean the boot (owner: python-wasm).
