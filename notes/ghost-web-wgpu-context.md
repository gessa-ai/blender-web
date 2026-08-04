<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4.pre3 — in-tab WebGPU context (emdawnwebgpu), standalone-proven

Status (2026-08-04): **GREEN in a real Chrome tab.** OUR GHOST context pattern
(`GHOST_ContextWGPUWeb`) drives the browser's WebGPU via emdawnwebgpu, renders a
triangle to a canvas surface AND to an offscreen texture that is read back and
displayed as an `<img>`. This is the browser twin of T3's native-Dawn proof and the
last platform unknown before pixels-in-tab.

## What shipped

| file | role |
|---|---|
| `platform_web/ghost/GHOST_ContextWGPUWeb.{hh,cc}` | browser WebGPU context: async instance→adapter→device→queue + `EmscriptenSurfaceSourceCanvasHTMLSelector` surface + configure. Mirrors native `GHOST_ContextWGPU` accessors. |
| `platform_web/ghost/harness-wgpu/` | standalone harness: triangle→surface (present) + triangle→offscreen→readback→`<img>`; `build.sh` (emcc `--use-port=emdawnwebgpu`). |

## Verification (real Chrome, WebGPU) — all targets PASS

Built with `--use-port=emdawnwebgpu` (108 KB wasm), served over http, driven in a
real WebGPU Chrome (`vendor=apple arch=metal-3`). Harness reports:
```
CONTEXT OK: emdawnwebgpu device + canvas surface acquired
ONSCREEN OK: triangle submitted (browser auto-presents on yield)
readback center BGRA=(26,77,255,255)
READBACK PASS: triangle rendered (center is orange)
```
- **Onscreen canvas non-black:** 9600/76800 px lit (the triangle), center pixel
  `RGBA=(255,77,26,255)` = the orange fill. (Screenshot: orange triangle on black.)
- **Offscreen readback:** center `BGRA=(26,77,255,255)` → R=255,G=77,B=26 = orange,
  asserted (`R>180 && B<80 && A>200`). Displayed as a `data:image/png` `<img>`.

## API deltas: native Dawn (chromium/7989 `webgpu_cpp.h`) vs emdawnwebgpu

This is exactly the drift GOAL pins the port for. Three load-bearing differences hit
during bring-up:

1. **Canvas surface source struct.** Native Dawn spells it
   `wgpu::SurfaceSourceCanvasHTMLSelector` (and platform `SurfaceSource*`);
   emdawnwebgpu uses **`wgpu::EmscriptenSurfaceSourceCanvasHTMLSelector`** (distinct
   SType `EmscriptenSurfaceSourceCanvasHTMLSelector`). Chained into
   `SurfaceDescriptor.nextInChain`; `.selector` = the CSS selector.

2. **Device acquisition is async-only.** Native `GHOST_ContextWGPU` drives
   `instance.WaitAny(RequestAdapter/RequestDevice, TimedWaitAny)` **synchronously** on
   the calling thread. In the browser that DEADLOCKS — `requestAdapter`/`requestDevice`
   are JS promises resolved by the very event loop a finite `WaitAny` would block. So
   the browser context uses **`CallbackMode::AllowSpontaneous`** and lets the callbacks
   fire off the event loop; `initAsync()` returns immediately and calls a ready-callback
   when device+surface exist. (`TimedWaitAny` is not requested — it is a native
   blocking-wait feature.)

3. **No `Present()`.** Native calls `surface.Present()` each frame. emdawnwebgpu
   **aborts** on `wgpuSurfacePresent`: *"wgpuSurfacePresent is unsupported (use
   requestAnimationFrame via html5.h instead)"*. The browser **auto-presents** the
   configured canvas when control returns to the event loop, so the render must live in
   a rAF/callback and simply NOT call Present. (This bit us: the first run aborted right
   after the onscreen `Submit`, before the readback.) For the GHOST mapping,
   `swapBufferRelease()` becomes a no-op on the web.

Minor: surface format fixed to `BGRA8Unorm` (the universal browser canvas format) to
serve one pipeline; `surface.GetCapabilities(adapter).formats[0]` is the more general
query — a follow-up, not needed for the proof. Struct names are the current Dawn
spelling (`TexelCopyTextureInfo`/`TexelCopyBufferInfo`, `ShaderSourceWGSL`), which
emdawnwebgpu tracks.

## The wait-shape decision (ADR-003)

**Chosen: plain spontaneous callbacks + `EXIT_RUNTIME=0`. No JSPI, no ASYNCIFY, no
main loop.** The whole flow is callback-chained — RequestAdapter → RequestDevice →
(render) → `Buffer.MapAsync(..., CallbackMode::AllowSpontaneous, cb)` — and every
completion is dispatched by the browser event loop after `main()` returns. There is no
suspend point at all, so ADR-003's suspend-topology invariant is satisfied trivially
(nothing suspends across a C++ `try`/`setjmp`).

**Why "boring":** the readback `MapAsync` is the one wait that matters. Options were
(a) JSPI await, (b) ASYNCIFY, (c) plain callback + return to the loop. (c) is the
smallest and safest and is what the browser wants anyway; JSPI/ASYNCIFY buy nothing
here and ASYNCIFY carries the ~50% size tax GOAL rejects.

**Tradeoff for M4 proper:** Blender's GPU module expects *synchronous-looking* calls
(`GPU_texture_read`, and `GHOST_Context::initializeDrawingContext()` returns a ready
context synchronously). Two ways to bridge the async browser reality, both ADR-003-legal
because the suspend lives at a top-level boundary:
- **Device init:** do a ONE-TIME JSPI await (or a deferred main-loop start) at startup —
  acquire the device before the WM main loop begins, so the rest of GHOST sees a ready
  context. (`initAsync` + ready-callback already models this; the async seam is confined
  to startup.)
- **Per-frame/readback waits:** keep them callback-driven at the main-loop tick (the
  permitted suspend boundary). A synchronous `GPU_texture_read` shim, if unavoidable,
  would JSPI-await the map at the tick — never inside a render `try` scope.
The harness deliberately uses the pure-callback form to prove the path needs neither.

## GHOST integration notes (for M4)

`GHOST_ContextWGPUWeb` is standalone (not a `GHOST_Context` subclass) so the async
lifecycle stays honest. To wire into the GHOST-web system: `newDrawingContext()` /
`createOffscreenContext()` construct it and kick `initAsync`; the WM main loop starts
only after the ready-callback (or a startup JSPI await). Accessors
(`getDevice/getQueue/getSurface/getSurfaceFormat`) mirror native `GHOST_ContextWGPU`
so the WebGPU backend pulls the same handles. `swapBufferRelease()` → no-op (auto
present); `activateDrawingContext()` → no-op (implicit device model).

## Reproduce
```
platform_web/ghost/harness-wgpu/build.sh
BLENDER_WEB_SHELL=$PWD/platform_web/ghost/harness-wgpu scripts/serve-web.sh 8125
# open http://localhost:8125/ in a WebGPU browser -> orange triangle + readback <img>
```
