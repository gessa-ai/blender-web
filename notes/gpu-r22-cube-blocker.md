<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 22 — clean UI composite at golden size, but the capture READBACK is the wall

Pin: Blender 5.2 `fbe6228777e7`; browser = emdawnwebgpu (M4 pin), real Chrome via the Browser
pane at `:8123/windowed.html`, canvas 1280x720. Build: build-wasm-windowed, patches through
**0107** + the r22 ghost commits (canvas-size, CopySrc + boot-settle burst).

## What landed this round (committed, verified where possible)

- **Patch 0106 — bind-group dedup over the FULL binding range.** r21's keep-first duplicate
  guard used a fixed `bool seen[64]`, so it only de-duplicated the LOW dense bindings. A
  combined texture's sampler half lives at `sampler_base` (kSamplerBindingBaseFixed = 256) + n;
  the collision that dropped the workbench-solid + grid pass was at **binding 257** ("In
  entries[8], binding index 257 already used"). Track EVERY emitted binding. VERIFIED LIVE:
  the binding-257 collision + its Invalid-pipeline/command-buffer cascade are GONE — the
  workspace UI now composites with **zero GPU validation errors on the compose path**.
  Census held EXACTLY **148/158 + static 956/973** on native Dawn (harness m3 5/5). Commit
  7635719.
- **Patch 0107 — suppress the spurious "Failed to load using Vulkan, using OpenGL instead"
  dialog.** WebGPU is the only backend and `is_supported()==true`, so the fallback is
  spurious; `WGPUBackend::init_resources()` marks it QUIET (`G_FLAG_GPU_BACKEND_FALLBACK_QUIET`),
  `__EMSCRIPTEN__`-guarded (native census byte-identical). VERIFIED LIVE: the splash boots
  clean, no dialog. Commit 7635719.
- **Canvas-size authority (ghost, commit a71ada0).** GHOST_WindowWeb's ctor forced the canvas
  to the WM's display-derived window size (`emscripten_get_screen_size` = **1800x1169** on this
  host) — so every readback/surface-configure came out at the wrong size. Now ADOPT the
  canvas's existing extent (the shell's deliberate 1280x720). VERIFIED LIVE: surface-proof now
  clears at **1280x720**; the whole UI lays out at that size. This is the operative golden size.
- **CopySrc + boot-settle burst (ghost, commit 1cc0089).** See below.

## THE CAPTURE — precisely characterized blocker (no comparator run this round, honestly)

The capture needs an EXACT 1280x720 PNG of the canvas. The canvas is transferred to the WM
pthread as an OffscreenCanvas (`OFFSCREENCANVASES_TO_PTHREAD='#canvas'`). Every path was tried:

1. **JS-side readback of the surface is BLANK.** On the main thread the placeholder <canvas>
   has no context (`getContext` throws InvalidStateError); `drawImage`/`getImageData`/
   `toDataURL`/`createImageBitmap` all return transparent-black. On the WORKER
   (`Module.canvas` = the real OffscreenCanvas) `convertToBlob` throws **"Readback of the
   source image has failed"** and `createImageBitmap → 2D → convertToBlob` yields a valid
   **1280x720 PNG that is entirely transparent** (20831 bytes) even while the browser
   screenshot shows the composited UI. Root cause (architectural): the **Dawn `Surface`
   manages the canvas OUTSIDE the standard `GPUCanvasContext`**, so the presented frame reaches
   the compositor but never populates the JS-readable canvas bitmap. Adding
   `TextureUsage::CopySrc` to the surface config (commit 1cc0089) did NOT change this — it is
   groundwork for the in-app path below, not the JS path.
2. **The only viable readback is Blender's own GPU copy** — `WM_window_pixels_read` /
   `bpy.ops.screen.screenshot` (exactly what the native golden uses), which copies the surface
   texture (now CopySrc-capable) to a buffer → CPU → PNG on WasmFS. BLOCKER: **`--python-expr`
   does not execute in the wasm windowed boot** — a print as its first statement never appears
   in the log, so the FINAL arg pass (`arg_handle_python_expr_run`, creator_args.cc:2795/3385)
   is not reached on this path (creator's windowed arm; needs tracing). Without it there is no
   in-app trigger for the screenshot.
3. **Data transport WORKS and is proven** for the next round:
   - Worker → OPFS → local CORS upload sink (`scratchpad/upload_server.py`, :8199 → evidence/)
     transfers bytes out with no base64-through-context.
   - `window.__bwModule.FS.readFile` works FROM THE MAIN THREAD (read a 77502-byte preloaded
     file, and would read any worker/Python-written file — reads proxy to the runtime WasmFS).
   - `FS.writeFile` from the main thread does NOT reach the worker's native WasmFS (the Python
     `os.path.exists` on the worker never saw a main-thread-written request file). So a
     file-based main→worker TRIGGER does not work; a worker-driven capture (Python writes, main
     reads) is the right shape.

**Next-round capture recipe (highest-value unblock):** get an in-app GPU readback firing.
Either (a) fix `--python-expr` execution in the windowed creator arm and have a bpy.app.timer
run `screen.screenshot(filepath='/bw_shot.png')` unconditionally (bpy timers ARE processed by
the emscripten loop — `wm_event_do_notifiers → wm_event_timers_execute → BLI_timer_execute`),
then read `/bw_shot.png` via `Module.FS.readFile` on the main thread; or (b) export a small C
`bw_capture()` that does `WM_window_pixels_read` + IMB PNG write, called via `Module.ccall`
from the worker capture facility. Then `compare_m4.sh <png> <state> 1280x720`. NB the r22 shell
experiments (worker OffscreenCanvas facility in wgpu-preinit-worker.js + `--python-expr`
screenshot hook in boot-windowed.js) were REVERTED — they are dead ends as-is; this note is
the record.

## Idle-black is an ENVIRONMENT artifact, not a present bug

The tab reports `document.visibilityState === "hidden"` in the Browser pane, so Chrome
throttles/pauses `requestAnimationFrame`; the emscripten main loop is rAF-driven
(`emscripten_set_main_loop(fps=0)`), so it does NOT tick unprompted — the canvas stays black
until an input event forces a proxied tick, and then the OffscreenCanvas **retains** that frame
indefinitely (verified: stable with zero input after a compose). So the r20/r21 "black between
events / needs a nudge" symptom is this throttling. The **boot-settle GHOST_kEventWindowActivate
burst** (commit 1cc0089) is the correct fix for a normally-visible tab (the initial
GHOST_kEventWindowSize does not redraw because the size is unchanged — WindowActivate's
focus-repaint path re-tags unconditionally) but is UNVERIFIABLE here because the loop never
ticks unprompted. A worker-native `setInterval` DOES run under throttling (it drove the capture
facility), so a future robust option is a timer-driven main-loop pump instead of rAF.

## Workbench-solid + grid STILL do not render (r21 residual persists past binding-257)

With 0106 the UI composites error-free, but the 3D VIEWPORT interior stays empty: after the
splash is dismissed the viewport shows only the overlay text/gizmos ("User Perspective", nav
gizmos, Z/Y/X labels) — **no grid, no axes, no cube**. Console is clean on the plain compose,
but a viewport SELECT click (GPU select pass) then throws an **Invalid RenderPipeline /
Invalid BindGroupLayout cascade** plus an **uncaught `createBindGroup ... 'buffer' undefined`
TypeError** that halts the loop. The uncaught null-buffer is from a path NOT covered by
`create_bind_group_checked` (the only non-guarded `CreateBindGroup` at wgpu_context.cc:405 is
the blit and uses textureView+sampler, so it is a different site — likely the select engine).
So task-2 is multi-layered: binding-257 was ONE blocker; the workbench-solid/grid draw and the
select pass have further pipeline/bind-group faults to isolate (re-instrument per-pass with the
uncapturederror listener while forcing a clean viewport redraw — hard under hidden-tab
throttling; nudge with a wheel/rotate, not a select-click, to avoid the select fault).

## Golden delta to expect even once the cube renders

The native splash golden has a **"Language: English (US)"** row (WITH_INTERNATIONAL ON in the
oracle build). The wasm build has INTERNATIONAL OFF, so its Quick Setup lacks that row and the
remaining rows shift up — the SPLASH comparison will fail structurally regardless of GPU parity.
Flag for the driver: either re-cut the splash golden from an INTERNATIONAL-OFF native build, or
blacklist the splash-state size delta, or gate M4 on the WORKSPACE state only.

## Census / provenance receipts
- Native Dawn census held EXACTLY **148/158 (8 FAIL / 2 CRASH) + static_shaders 956/973**,
  harness m3 5/5 GREEN, with 0106+0107 applied (ledger/results/m3.json).
- Patches 0106 + 0107 reverse-apply clean; lane-a-staging mirror 0-drift (wgpu_context.cc,
  wgpu_backend.cc); series updated with full rationale. Commits 7635719 (patches), a71ada0
  (canvas-size), 1cc0089 (CopySrc + burst).
