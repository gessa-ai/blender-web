<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Viewport recon — what the 3D viewport actually draws (M4 gate path)

**Date:** 2026-08-06 (viewport-recon worker)
**Binary:** `build-wasm-windowed/bin/blender_browser.{wasm 923 MB, js, data 106 MB}`,
mtime `05:07:25` — post-r16 (patches >= 0095). NOT relinked during this session
(mtime unchanged across the run; no r17 interruption observed).
**How:** real Chrome (Browser pane), `:8123/windowed.html`, argv `blender
--factory-startup` (NO `--background`), canvas `#canvas`, COOP/COEP
(`crossOriginIsolated: true`), device acquired on the WM worker (ADR-007,
`features=22`). Boot must be started by clicking the on-page **Boot Blender
(windowed)** button (the shell does not auto-boot).
**Evidence images (readback of the live `#canvas`, 1800x1169):**
- `viewport-recon-01-ui-splash-raw.png` — faithful main-thread `drawImage`→`toDataURL`
  copy of the displayed frame (dark; the UI is thin light strokes on black).
- `viewport-recon-02-ui-splash-boost6x.png` — same frame, per-channel x6 for
  legibility (structure + text readable). Boost is the ONLY difference.

## OUTCOME (headline)

Boot reaches the **WM_main loop with no abort** (state pill `main loop (WM_main)`,
`exit: —`). Blender's **UI chrome composites**: 3D-viewport header (`Object Mode /
View / Select / Add / Object`, `Global`, transform/snap icons, gizmo + shading +
overlay icons top-right), the left tool row, the `Options` (N-panel) tab, the
right-hand editor panels (dark, grey borders), a bottom status strip, and the
centered **Quick Setup** splash with all widgets legible (`Theme: Blender Dark`,
`Keymap: Blender`, `Mouse Select: Left/Right`, `Spacebar Action: Play`,
`Continue`).

**The 3D VIEWPORT INTERIOR DRAWS NOTHING.** The entire viewport region — the whole
large area around the splash — is **pure black**: **no default cube, no grid, no
navigation/axis gizmos, no world/background gradient**. The workbench scene never
appears. Two **garbled artifacts** stand at the far-left edge: a tall white
vertical streak and a shorter blue/white vertical wedge (mis-blitted region
content, not scene geometry).

So the split is clean: **2D UI overlay = mostly renders; 3D viewport draw = fully
black.** This is the M4-gate blocker — splash renders, default cube does not.

## Does the workbench engine initialize?

No explicit `workbench`/`DRW`/`GPU_init` CLOG line is emitted to stdout, but the
draw manager IS issuing GPU work: the console (below) shows **compute-pass**
bind-group failures and **vertex-stage** UBO-size failures — i.e. the
engine/draw-manager encodes passes, they fail Dawn validation, the command buffer
is dropped at `Queue.Submit`, and the viewport stays black. The engine runs; its
submissions are rejected.

## GPU DIAGNOSTICS — Dawn validation errors (the reason the viewport is black)

All are **non-fatal validation WARNINGS** from the WM-worker `GPUDevice` (surfaced
to the page console). Each bad command buffer becomes `[Invalid CommandBuffer]` →
`Queue.Submit` rejected → nothing composites for that pass. Dawn eventually prints
`WebGPU: too many warnings, no more warnings will be reported ... for this
GPUDevice`. Five distinct classes (verbatim first lines):

1. **Surface blit format mismatch (RGBA8 → BGRA8 CopyTextureToTexture).**
   `Source [Texture ... RGBA8Unorm] format ... and destination [Texture
   "IOSurface(...WebgpuSwapChainTexture...)"] format (BGRA8Unorm) are not copy
   compatible. - While ... CopyTextureToTexture(...)`. Sizes seen: 318x26,
   318x179, 1475x26, 1475x55 (UI region blits — header/panel strips). Region
   offscreen textures are RGBA8Unorm; the window surface is configured BGRA8Unorm
   (T12). `CopyTextureToTexture` requires identical formats, so every such
   region→backbuffer copy fails. **Dominant cause of black/near-black region
   composites.**

2. **UBO bound where SSBO expected (buffer-usage flags).**
   `Binding usage (BufferUsage::(CopyDst|Uniform)) of [Buffer] doesn't match
   expected usage (BufferUsage::Storage)` — compute-pass `entries[1]/[2]`, binding
   1, `Storage` / `ReadOnlyStorage`. A Uniform-usage buffer is bound to a storage
   slot (missing `BufferUsage::Storage` bit, or UBO mapped to an SSBO binding).

3. **Dense-binding remap COLLISION.**
   `In entries[N], binding index K already used by a previous entry` (K=1 and K=3
   observed). Two resources map to the same dense group-0 binding — the
   `remap_*_binding` flatten (patch 0092) produces duplicates for these shaders.

4. **Dense-binding remap GAP / index absent in layout.**
   `In entries[2], binding index 3 not present in the bind group layout` — layout
   expects bindings `0,1,2` (textures), `4,5` (uniform), `256,257,258` (samplers);
   the group supplies binding 3, which the layout skips. Off-by-one / missing slot
   in the remap.

5. **Vertex UBO smaller than declared min binding size.**
   `Binding size (352) of [Buffer] is smaller than the minimum binding size
   (16384). - entries[1] binding 1, visibility Vertex, Uniform, minBindingSize
   16384`. Repeated many times (its own cluster) — a vertex-stage shader declares a
   16384-byte UBO but only a 352-byte buffer is bound. Size/stride mismatch between
   the shader interface and the allocated uniform buffer.

## CRASH SIGNATURE (gold for the next gpu round) — Tab → edit mode

Pressing **Tab** (edit-mode toggle operator) over the canvas escalates from a
droppable warning to an **uncaught JS exception on the WM worker**, verbatim:

```
worker sent an error! http://localhost:8123/bin/blender_browser.js:19731:
Uncaught TypeError: Failed to execute 'createBindGroup' on 'GPUDevice':
Failed to read the 'entries' property from 'GPUBindGroupDescriptor':
Failed to read the 'resource' property from 'GPUBindGroupEntry':
Failed to read the 'buffer' property from 'GPUBufferBinding': Required member is
undefined.
```

A bind-group entry is assembled with an **undefined/null `buffer`** (a VBO/IBO/UBO
that was never created or was dropped). Unlike classes 1–5 (Dawn *validates* and
drops), this throws at the JS binding boundary in `createBindGroup` and **halts the
WM-worker render loop**: immediately after, the canvas goes **fully black** and the
page log freezes. The shell pill still reads `running` / `exit: —` (no clean
Emscripten abort ever fires — the worker exception is not propagated to the Module
promise), but rendering is dead. Reproducible: boot → mouse-move (composites UI) →
Tab.

## Startup GPU-backend error dialog (notable)

Over the splash, an error dialog draws first (red circle-X + `OK`), text (from the
boosted PNG): **"Failed to [init]... using OpenGL instead. Updating GPU drivers may
solve this issue. The graphics backend can be changed in the System section of the
Preferences."** This is Blender's GPU-backend init-fallback report — it fires at
startup **despite the WebGPU device being live** (`features=22`, real render passes
submit). `Escape` dismisses THIS dialog (revealing the splash beneath); `Escape`
does NOT dismiss the Quick Setup splash itself. (r16 called the first dialog an
"asset-library" error; the readable text here is the GPU-fallback message.)

## Interaction results

- **UI composites ONLY after the first input event.** A fresh boot sits at WM_main
  with the canvas still at its initial **1280x720, fully black** (`nonBlackPct
  0.00`). A single mouse-move over `#canvas` triggers the GHOST window resize to
  **1800x1169** and the first UI composite (`nonBlackPct ~3.35`). The pre-event
  WM_main frame paints nothing.
- **Input reaches WM.** Mouse move / click / Escape over `#canvas` drive redraws; a
  splash-image re-read is logged on interaction (`image.read ... <splash screen>` a
  second time). Escape dismisses the GPU-fallback dialog.
- **Hover over the viewport:** no visible highlight change (viewport is black; and
  overlay/highlight draws hit the same validation walls).
- **Click in the viewport:** no visible selection/outline (nothing drawn to
  select; draws rejected).
- **Tab:** the crash above.
- **Middle-drag orbit / numpad:** not exercised (viewport black + crash-on-Tab made
  it low-value this round).

## Non-fatal, pre-existing (NOT this lane, for completeness)

- **Python:** `ModuleNotFoundError: No module named 'cattrs'` at
  `_bpy_internal/http/downloader.py:51` (reached from `bl_pkg/__init__.py:580
  _remote_asset_library_restore_backups`); `addon_utils.enable` catches it, `bl_pkg`
  fails to register, boot continues. Also `Unable to find the Python binary, the
  multiprocessing module may not be functional!`. (r16 saw `_multiprocessing`; this
  binary trips on `cattrs` first.)
- **Splash artwork black:** `IMB_load_image_from_memory: unknown file-format
  (<splash screen>)` — the imbuf reader gap; splash chrome/text render, bitmap does
  not.
- **OIIO `physical_memory` assertion-print** at boot — environmental, identical to
  headless.

## Readback method / caveat

`#canvas` is an **OffscreenCanvas transferred to the WM worker**
(`OFFSCREENCANVASES_TO_PTHREAD='#canvas'`); main-thread `getContext('2d')` throws
`InvalidStateError`. The displayed frame is still copyable via `drawImage(canvas,
...)` into a fresh 2D canvas → `toDataURL` (used for the evidence PNGs). This
reflects the composited light strokes/text faithfully; the compositor screenshot
(pane capture) agrees. Backgrounds read near-black because they ARE near-black
(only header/panel borders carry theme grey; the 3D viewport is 0,0,0).

## BLOCKER LIST — routed by lane

**gpu-backend (`source/blender/gpu/webgpu/`)** — owns the black viewport; all P1:
1. **Surface blit format mismatch RGBA8→BGRA8** (`CopyTextureToTexture`, region
   strips). Configure the surface as RGBA8Unorm, or convert region format, or blit
   via a textured-quad render pass instead of a raw copy. Console class 1.
   Suspect: `wgpu_context.cc` surface configure (BGRA8Unorm, per T12) vs the
   offscreen region texture format; the region→backbuffer present path.
2. **createBindGroup null-`buffer` → uncaught TypeError on Tab/edit-mode** (crash).
   `append_resource_bind_entries` (patch 0092) must never emit a `GPUBufferBinding`
   with an undefined buffer — guard/skip or bind a valid buffer. `wgpu_context.cc`
   `append_resource_bind_entries`.
3. **Dense-binding remap collisions + gaps** (console classes 3 & 4):
   `WGPUShader::remap_*_binding` produces duplicate and missing dense indices for
   real UI/edit shaders. `wgpu_shader.cc` remap.
4. **UBO-vs-SSBO usage-flag mismatch** (console class 2): storage buffers created
   without `BufferUsage::Storage`, or UBOs bound to storage slots. `wgpu_storage_buf.cc`
   / `wgpu_uniform_buf.cc` usage flags + the bind path.
5. **Vertex UBO undersized vs declared minBindingSize 16384** (console class 5):
   per-shader uniform buffer sized 352 vs 16384 expected. `wgpu_uniform_buf.cc`
   allocation / the shader interface min-size.

**ghost-web (`platform_web/ghost/`)** — P2:
6. **First UI composite requires an input event** (WM_main paints a black
   1280x720 frame at idle, only resizes to 1800x1169 + composites after the first
   mouse event). Likely a missing initial `WM_window_process_events`/redraw or the
   GHOST resize event not fired at window creation. `GHOST_WindowWeb.cc` /
   `GHOST_SystemWeb.cc` event pump on first frame. (Latent M4-gate risk: a headless
   golden capture would see black unless an event is injected.)
7. **Two garbled vertical streak artifacts at the left edge** — mis-blitted region
   content; likely downstream of blocker 1 (format) / 3 (remap). Confirm after
   1 & 3 land.

**python-wasm** — P3 (non-fatal, does not block pixels):
8. `cattrs` (and `_multiprocessing`) missing C-ext/pure-py deps → `bl_pkg`
   register fails (caught).

**imbuf** — P3: splash-screen decoder gap (`IMB_load_image_from_memory`).

**Startup dialog (triage):** the "Failed to ... using OpenGL instead" GPU-fallback
report firing on a live WebGPU device — trace which GPU capability/sub-init reports
failure (gpu-backend). Non-fatal but a smell.

## Main-loop health

No Emscripten abort at idle (`exit: —`, `crossOriginIsolated: true`). The loop is
stable through mouse move/click/Escape. **Tab kills the render loop** (crash
above). JS heap not separately measured this round.
