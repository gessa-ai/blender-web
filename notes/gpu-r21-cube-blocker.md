<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 21 — the viewport draw finally VISIBLE: two blockers down, two residuals

Pin: Blender 5.2 `fbe6228777e7`; browser = emdawnwebgpu (M4 pin), real Chrome via the
Browser pane at `:8123/windowed.html`, canvas 1280x720. Build: build-wasm-windowed,
patches through **0105** + the r20 ghost surface commit + this round's shell error listener.

## The round-20 hypotheses were BOTH wrong — evidence killed them on the first boot

Task 1 (worker-side Dawn error capture) was the whole round. It landed immediately and
redirected everything: booting with the `uncapturederror` listener (commit 25f3cfe,
platform_web/shell/wgpu-preinit-worker.js) printed, on the FIRST viewport draw:

    GPUValidationError: Vertex attribute slot 0 used in ([ShaderModule], [EntryPoint "main"])
    is not present in the VertexState. — While calling [Device].CreateRenderPipeline.

Not a composite gap (r20 hyp. 1) and not the depth Float/UnfilterableFloat residual (0103).
The workbench-cube / overlay-grid / overlay-outline **pipelines were being rejected at
creation**, so those draws dropped. Every subsequent round should trust this listener — it is
now permanent in the shell and proxies WM-worker Dawn errors to the page console.

## Fix 1 — patch 0104 (multi-vertex-buffer draw path). THE primary cube blocker.

A temporary `[r21-pipe]` diagnostic in build_pipeline named it exactly:
`workbench_prepass_mesh_* vf_attr=1 added=1 needs{0:pos!MISS 1:nor 3:au!MISS 2:ac!MISS}`,
`overlay_grid_next needs{0:pos!MISS}`, `overlay_outline_prepass_mesh needs{0:pos!MISS}`.
Root cause: the WebGPU draw path bound ONLY `verts[0]` (SetVertexBuffer slot 0) and built the
pipeline VertexState from that single format. Blender mesh/overlay batches spread a shader's
inputs across SEVERAL `verts[]` VBOs, so every `@location` the module consumed that this one
VBO didn't supply was absent from the VertexState → Dawn rejected the pipeline. (The editor
UI was unaffected because its region composite uses a procedural fullscreen triangle with no
vertex inputs — which is exactly why r20 saw UI-but-no-viewport.)
Fix: `build_vertex_plan()` resolves ALL bound VBOs (every name/alias) + an Instance-stepped
dummy slot over a shared zero buffer for shader-required locations no VBO provides (GL's
disabled-array-reads-a-constant; WebGPU forbids Vulkan's arrayStride-0 trick). Commit
f469454; census held EXACTLY 148/158 + 956/973.

## Fix 2 — patch 0105 (sampled-view dimension reconciliation). THE composite blocker.

With 0104 the offscreen viewport draws SUCCEED (confirmed live: a `[r21-draw]` dedup showed
`overlay_background`, `overlay_antialiasing_pipeline`, `gpu_shader_3D_polyline_flat_color`
(the grid) all drawing into a non-window fmt-23 offscreen). But the viewport still didn't
composite — the error listener then caught the NEXT blocker on the viewport→window draws
(win=1: `OCIO_Display`, `gpu_shader_2D_image_rect_color`):

    GPUValidationError: Dimension (TextureViewDimension::e2DArray) of [TextureView of Texture
    (1x1 px, RGBA8Unorm)] doesn't match the expected dimension (e2D). — entries[6], binding 2
    — While calling [Device].CreateBindGroup.

Root cause: DRW fills an unbound sampler slot with the 1x1 `g_dummy_texture_array`
(GPU_TEXTURE_2D_ARRAY) even where the shader samples a plain `texture_2d`; sampled_view() built
the view at the texture's NATIVE dimension (e2DArray), which Dawn rejects against the e2D
binding. Fix: append_resource_bind_entries passes the binding's declared viewDimension (from
the interface map, `infer_view_dimension`) to sampled_view(), which builds the view at THAT
dimension (arrayLayerCount=1 for a single-plane view over a multi-layer source). Commit
babfd76; census held EXACTLY 148/158 + 956/973.

RESULT, verified live: **the 3D viewport now composites overlay content** — selecting the cube
draws its orange selection outline ON SCREEN (first non-UI viewport pixels in the tab; the
GPU-fallback dialog was overlapping it in the capture frame). No GPU validation errors remain
on the viewport draw.

## The two residuals (next round) — no cube PNG yet, honestly

1. **The persistent workbench-solid pass + grid do not composite reliably.** Only the
   overlay/outline was confirmed on screen. The offscreen DOES receive `overlay_background`
   and the grid polyline draws (fmt-23, win=0), and the win=1 composite draws (OCIO_Display /
   2D-image-rect) now run without error — yet the solid cube faces + grid + background gradient
   are not visibly landing. Suspect: the workbench color result reaches the GPUViewport color
   texture but the OCIO_Display / color-management composite samples an empty/wrong texture, OR
   the workbench pass writes a target that is not the one sampled for the final draw. Next
   round: re-instrument (the `[r21-draw]` fb-dedup + `[r21-blit]` src/dst-dims/fmt printfs used
   this round are the right tools — keep the log volume LOW, they evict the signal fast) and
   trace the workbench color texture from its render pass to the OCIO_Display bind.

2. **The window present is flaky between input events (black between nudges).** After the first
   composite the canvas frequently goes fully black (UI included) until the next mouse event
   nudges a redraw. This is the r20 "needs an input nudge" symptom, worse now that more draws
   run. Likely the WGPU surface present model vs Blender's on-demand redraw: `sync_backbuffer`
   (WGPUContext::activate) calls `surface.GetCurrentTexture()`; if a main-loop tick acquires a
   fresh surface texture but the WM does not redraw the window that tick, the browser presents
   the un-rendered (black) texture. Fix direction: only acquire/swap when the window actually
   redraws, or re-blit the last composited frame; this is also task-6 (first-composite at boot
   / after resize). This flakiness is what blocks a stable golden-size cube PNG capture.

## Round-21 tasks not completed (budget) — precise state for the next worker

- **Task 3 (GPU-fallback dialog "Failed to load using Vulkan, using OpenGL instead").** Still
  present live (dismissable, non-fatal). NOT root-caused this round. The Vulkan/OpenGL strings
  are Blender's generic backend-fallback popup text; find the wm fallback path that formats it
  under GPU_BACKEND_WEBGPU (likely a backend-enum → name mapping in the wm fallback text, an
  __EMSCRIPTEN__-guarded seam or a wm patch). In-lane if the seam is guarded; else characterize.
- **Task 4 (mouse-wheel capture, ghost-web).** NOT done. The canvas wheel listener needs
  `preventDefault` + GHOST wheel-event delivery (platform_web/ghost event bridge —
  GHOST_EventBridgeWeb / the canvas listener setup in GHOST_SystemWeb/WindowWeb). Small; land
  it. Currently the wheel scrolls the HTML page instead of zooming the viewport.
- **Task 5a (0098 header-comment fix).** wgpu_context.hh's blit_color_render comment still says
  the copy has "no flip", but blit_color_render's WGSL samples `uv.y = y` (a flip) and its own
  in-.cc comment says so. Fix the .hh comment to the truth. NOTE: wgpu_context.hh is now a
  0104-touched file (dummy_vertex_buffer); a comment-only fix should be folded carefully (its
  own micro-patch, or amend 0104's mirror) to avoid churning the committed stack.
- **Task 5b (retire the 0100 16 KiB UBO pad?).** EVALUATED — **KEEP IT.** The 0103 explicit
  layout builds buffer entries via `make_buffer_entry` and never sets `buffer.minBindingSize`
  (stays 0 → unenforced), so the pad IS redundant WHERE explicit layouts engage. BUT shaders
  that log incomplete interface-map coverage fall back to Dawn's AUTO layout, which still infers
  `minBindingSize = 16384` from the WGSL block; without the pad those UBOs would fail
  ("binding size smaller than min binding size (16384)") and drop the draw. The fallback path
  keeps the pad necessary. Revisit only if/when every shader carries an explicit layout.
- **Task 6 (first-composite at 1800x1169 / after resize).** Same mechanism as residual (2);
  the resize path doesn't drive a redraw/swap the way the r19 initial-size event did.

## Census / provenance receipts
- Native Dawn (build-native-gpu) census held EXACTLY **148/158 (8 FAIL / 2 CRASH) +
  static_shaders 956/973**, harness m3 5/5 GREEN, for BOTH 0104 and 0105.
- Patches 0104 + 0105 reverse-apply clean; lane-a-staging mirror 0-drift (8 + 3 files); series
  updated with full rationale blocks. Commits: 25f3cfe (task 1), f469454 (0104), babfd76 (0105).
