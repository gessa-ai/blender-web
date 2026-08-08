<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 31 (gpu-backend worker) — the tick-pumped diagnostic GPU readback (LANDED, patch 0117) + the gbuffer discriminator: DIRECT GPU proof that the workbench opaque prepass DRAW rasterizes ZERO fragments (state (a) empty), falsifying r30's surviving "written-then-lost between prepass and composite" residual. No cube fix landed; root cause re-localized to the DRW GPU-driven workbench-prepass draw itself, with the search space cut hard.

Continues notes/gpu-r30-pipeline-pending.md (DO-NOT-RE-RUN list there stands). Rig = the
r30 recipe (headed Playwright bundled Chromium, opt tree `build-wasm-windowed-opt` port
8124, `?gate=1280x720`, `?pyexpr=` splash-off + per-0.3s VIEW_3D `tag_redraw()` kick),
driver `sandbox/gpu-r31/diag_readback.mjs`.

## STAGE 1 — THE TOOL (a keeper; landed as patch 0117, inert unless invoked)

`WGPUTexture::diag_kick_readback(label)` is the kick-then-consume twin of `read()`
(ADR-007): submit `CopyTextureToBuffer` into a fresh MapRead staging buffer +
`MapAsync(..., CallbackMode::AllowSpontaneous, cb)` and RETURN. The callback fires on the
WM worker's own event loop **between** `emscripten_set_main_loop` ticks and writes the raw
device bytes (256-byte row padding stripped) + an 8-word header
`{"BWRB", ver, w, h, wgpu_format, texel_bytes, row_pitch, data_bytes}` to
`/tmp/bw_readback_<n>.bin`, plus one raw-fd-2 stderr line
(`BW_READBACK_DONE seq=.. label=.. file=.. status=ok`). The rig pulls the file via
`window.__bwModule.FS.readFile`.

`wgpu_diag_readback.{cc,hh}` owns the coordination: a named-texture registry
(`viewport_color`, `gbuffer_depth/material/normal/objectid`), a per-frame command poll +
`instance.ProcessEvents()` pump driven from `WGPUContext::activate`, and a gbuffer capture
armed at the workbench-prepass submit (`on_draw_submit`, called after the draw's
`queue.Submit` in `multi_draw_indirect`). INERT unless env `BW_DIAG` is set; a boot-time
`BW_DIAG_ARM=<n>` captures the first N prepass submits.

### DECISIVE toolchain finding (settles the deferral's mechanism)
- `CallbackMode::AllowProcessEvents` + `instance.ProcessEvents()` pumping does **NOT**
  deliver the map completion in the imported-device windowed profile (0 completions across
  a 30 s kicked run). `CallbackMode::AllowSpontaneous` **DOES** — the callback fires on the
  worker event loop between ticks with no ProcessEvents dependency. This is why the old
  synchronous `read()`/`webgpu::Buffer::read` `WaitAny` path returns zeros: there is no
  spontaneous or process-events path there, and a same-thread blocking wait halts the loop
  that would deliver it. **The web readback lever is `AllowSpontaneous` + return-to-loop.**

### Self-test (has teeth) — PASS
`readback viewport_color` after the grid renders: 1280x720, fmt=27 (BGRA8Unorm-class),
texel=4, `nzFrac=0.88` (highly NON-uniform — grid lines + UI), center texel `[63,63,63,0]`
(the background gray). 0 GPU errors. The persistent offscreen backbuffer (CopySrc-usable,
GHOST_ContextWGPUWeb.cc) is the `viewport_color` target.

## STAGE 2 — THE DISCRIMINATOR (answered with direct GPU reads)

Captured three identical times (boot-arm=3):

| target (state) | fmt / texel | result |
|---|---|---|
| `prepass_depth`  (a) after prepass submit | Depth32Float / 4 | **1.0 everywhere** — writtenFrac 0, min=max=1.0 |
| `prepass_material` (a) | RGBA16Float / 8 | **all zero** |
| `prepass_normal` (a)   | RG16Float / 4  | **all zero** |
| `prepass_objectid` (a) | R16Uint / 2    | **all zero** |
| `gbuffer_depth` (b) end of frame | Depth32Float / 4 | 13.4% written, min 0.369 (the OVERLAY reusing the shared depth tex) |
| `gbuffer_objectid` (b) | R16Uint / 2 | 1.6% written (overlay) |
| `viewport_color` (b) | BGRA8-class / 4 | non-uniform, center `[63,63,63]` (composite discards, background shows) |

**VERDICT — BOTH state-(a) samples are empty.** The instant the workbench opaque prepass
`Submit` lands, the entire gbuffer it targets is the pristine clear (depth exactly 1.0, all
three colour attachments 0). The draw rasterizes ZERO fragments — proven directly at the
GPU level, not inferred from a composite visualizer as in r29/r30. This **FALSIFIES r30's
surviving residual** ("something between prepass and composite DESTROYS the content"): the
content was never written. The 13%/1.6% seen at end-of-frame (state b) is the overlay/
outline pass writing the SAME pooled depth/object-id textures LATER — not the cube in the
gbuffer. (State-b material/normal are unreadable: those transient gbuffer colour textures
are freed by the DRW pool after the frame — `texture_==null` when read from a timer — which
is itself why state (a), captured during the frame, is mandatory.)

## The draw encoding is CORRECT yet writes nothing (search space cut)

`[bw-r31-*]` instrumentation (reverted; grep `bw-r31` across `upstream/` is empty) diffed
the failing `workbench_prepass_mesh_opaque_studio_material_no_clip` draw against the WORKING
`overlay_outline_prepass_mesh` draw at the Dawn-call level, and read the GPU-generated
indirect args and the bind group directly:

- **Indirect args (GPU-generated, read via CopyBufferToBuffer):** `idxCount=36 instCount=1
  firstIdx=0 baseVtx=0 firstInst=0` — PERFECT. The GPU is correctly told to draw the full
  36-index cube, 1 instance. (r29 only read the CPU-side pre-generation; this reads the
  post-compute args the draw actually consumes.)
- **Pipeline:** distinct object (`0x2f98df48`) from the outline's (`0x2fac9128`) — NO pool
  cache collision. Builds successfully (non-null), so the r30 "async/pending pipeline"
  family stays dead.
- **Draw state:** indexed, istart=0, off=32, prim=TRIS, dtest=LESS_EQUAL, cull=None,
  flip_y=1, depthWriteEnabled=true, colour writeMask=RGBA on all 3 targets. The only raw
  diff from the outline is `write_mask 0x3f` vs `0x1f` (the extra bit is GPU_WRITE_STENCIL
  on a stencil-less Depth32Float) — BENIGN: `to_color_write_mask` ignores it and
  `depthWriteEnabled` follows GPU_WRITE_DEPTH, both correct (wgpu_pipeline.cc:200,241).
- **Vertex plan:** `s0[R vbo0 nor] s1[R vbo1 pos] s2[D instance] s3[D instance]` — all four
  slots bound (2 real, 2 zero-dummy). Matches the exact layout r30 proved rasterizes
  standalone.
- **Bind group:** 6 entries, no nulls, push-constants present at b5 (16 B); structurally
  complete and error-free — the SAME shape as the working outline. So the defect is NOT a
  missing/dropped binding (patch 0116 fixed the analogous COMPOSITE drop; the prepass has no
  null/absent binding).

So: valid pipeline + correct 36/1 indirect args + fully-bound vertex buffers + complete
6-entry bind group + correct depth/cull/mask + 0 GPU validation errors — and the fragment
count is still zero. The vertex stage produces no on-screen primitives. Everything that is
CHEAP to see is correct; the fault is in the CONTENT the vertex shader consumes (the
model/view/projection it reads from the bound draw-resource buffers) or how this specific
shader's interface maps a bound buffer to the slot it samples — i.e. a wrong-CONTENT /
wrong-slot bind that carries no validation error, exactly the class patch 0116's author
flagged as the remaining "separate DRW GPU-driven-draw defect."

## NEXT ROUND — do NOT re-run the eliminated experiments (r29/r30 lists + these)

The remaining discriminator is BUFFER-CONTENT, now cheap with the landed tool (extend it
with the sibling `CopyBufferToBuffer` readback — the r31 `[bw-r31-iargs]` instrumentation
is the template):
1. Read the CONTENT of the 6 bound buffers for BOTH the workbench prepass and the outline
   (first ~64 B each). The outline transforms the same cube correctly, so its matrix buffer
   is the oracle. Find which workbench binding should hold the ViewProjection / object-matrix
   and confirm whether it holds that data or a DIFFERENT buffer's bytes (wrong-slot bind) or
   zeros (upload/flush miss). `append_resource_bind_entries` + the shader interface map
   (wgpu_shader_interface_map) is where a per-slot remap would go wrong for THIS shader.
2. If the matrix content is correct, the collapse is in resource_id / gl_InstanceID indexing
   into the object-matrix SSBO (patch 0041 alias): read `firstInstance`/the resource-id path
   the workbench vertex uses vs the outline's — a wrong res_id reads matrix[0] not the cube's.

## Landing state (this round)
- [x] Tool landed: patch **0117-gpu-webgpu-diag-readback.patch** (+ patches/series entry).
      New: `wgpu_diag_readback.{cc,hh}` + `WGPUTexture::diag_kick_readback` +
      `WGPUFrameBuffer::diag_attachment_texture` + activate/sync_backbuffer/draw-submit hooks.
- [x] ALL `[bw-r31-*]` hunt instrumentation reverted; grep `bw-r31`/`BW_R31` across
      `upstream/` is empty. The landed tool is inert unless `BW_DIAG` is set.
- [x] Native census GREEN (build-native-gpu blender_test rebuilt clean): m3 148/158 +
      956/973 unchanged, 0117 detected `applied`; `ledger/results/m3.json` committed.
- [x] Windowed opt relinks clean (build-wasm-windowed-opt blender_browser, 34 s); the
      shipping self-test reads the viewport-colour texture back non-uniform, 0 GPU errors.
- [x] `ledger/deferred.json` id=gpu-sync-readback-windowed updated: diagnostic path DONE,
      caller-facing sync/poll API still deferred.
- [ ] Gray shaded cube: NOT fixed. Root cause re-localized to the prepass draw's consumed
      buffer CONTENT / interface-slot mapping; the empty-gbuffer discriminator + the
      cut search space are the handoff.
- Evidence: `sandbox/gpu-r31/diag_readback.mjs`, `sandbox/gpu-r31/r31-{disc,final}.analyses.json`,
  `platform_web/shell/evidence/m4-r31-{disc,final}-shot.png`.
