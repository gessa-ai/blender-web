<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 28 (gpu-backend worker) — the missing index-buffer upload: crumpled outline + no nav-gizmo FIXED, solid pass isolated to the framebuffer depth path

Continues notes/gpu-r26-bind-collision-root-cause.md (the "r28 queue"). Rig = the r23
visible recipe (headed Playwright, bundled Chromium, `?gate=1280x720` +
`?pyexpr=` splash-off + per-second VIEW_3D `tag_redraw()` kick). Method: temporary
once-per-tuple stderr fingerprints in the OWNED webgpu backend, visible boots, read
the console, fix, revert. All diagnostics reverted before landing.

## THE ROOT CAUSE (one bug, two of the three defects)

`WGPUBatch::draw` and `WGPUBatch::multi_draw_indirect` **never uploaded the index
buffer before binding it.** The GPU frontend (`GPU_indexbuf_build_in_place`) transfers
the index data to the `IndexBuf` and defers the GPU upload to "first use"; both the
Vulkan and Metal backends force that upload inside their draw path
(`vk_batch.cc:34/97`, `mtl_batch.mm:253`). The WebGPU draw path had no equivalent —
proven live: a top-of-`WGPUIndexBuffer::upload_data` fingerprint NEVER fired across a
full boot, yet indexed batches drew. Consequence per draw path:

- **`draw()` (indexed):** `if (wibo->buffer().valid())` was FALSE → `DrawIndexed`
  **skipped entirely**. Every indexed immediate/preset batch silently vanished —
  including the instanced `gpu_shader_2D_widget_base_inst` roundbox batch that is the
  **navigation-gizmo ball** (6 axis balls via `GPU_batch_draw_instance_range`,
  ilen=18). = **defect #3.**
- **`multi_draw_indirect()` (indexed):** `indexed = buffer().valid()` was FALSE →
  the loop fell through to the **non-indexed `DrawIndirect`** branch. The GPU-generated
  `DrawCommandIndexed` args `{indexCount,instanceCount,firstIndex,baseVertex,
  firstInstance}` were then consumed as `DrawIndirect` args `{vertexCount,...}` and the
  cube's 24 `pos` verts were drawn in **raw order** instead of via the 36-index
  connectivity → the **crumpled cube outline** (`overlay_outline_prepass_mesh`) =
  **defect #2**, and the same raw-order geometry landed in the workbench gbuffer.

Ground truth captured (diagnostics, since reverted):
- `pos` VBO perfect: 24 verts, cube corners ±1 (F32x3, stride 12, plan slot loc0 fmt
  Float32x3 off0 — binding was always correct).
- IBO data perfect once uploaded: `0 1 2 0 2 3 4 5 6 4 6 7 ...` (textbook cube tris,
  u16, subrange, start 0, base 0).
- `validBefore=0` on the first `workbench_prepass_mesh_*` and `gpu_shader_2D_widget_base`
  mdi/draw of the boot; `validAfter=1` after the added `upload_data()`.

### FIX (patch 0114, landed) — the ONLY code change this round

`WGPUBatch::draw` and `WGPUBatch::multi_draw_indirect` call `elem->upload_data()`
after the vertex-buffer upload loop, before the index buffer is bound (mirrors VK/MTL).
`upload_data()` is a no-op once the buffer is valid, so no double-upload. Unguarded —
semantically correct for native Dawn too; census re-ran GREEN (148/158 + static
956/973, 5/5 scopes, 2026-08-07T22:xxZ). Reverse-apply clean; series + lane-a
`sandbox/lane-a-staging/webgpu/wgpu_batch.cc` mirror synced.

RESULT (evidence m4-r28-outline-gizmo-fixed-1280x720.png vs the before shot
m4-r28-before-crumple-nogizmo-1280x720.png): the cube outline is now a clean cube
silhouette, and the nav-gizmo ball composites in full (blue Z / green Y / pink X +
the three hollow negative-axis balls, letters upright). Byte-region stable across
boots.

## Defect #1 (workbench SOLID pass) — NOT mine; isolated to the gbuffer depth path

With #2 fixed the workbench prepass now draws the cube **indexed and correctly**
(same geometry the clean outline proves), into the 3-attachment gbuffer
(color_count=3 + depth_fmt), yet **no shaded cube appears.** Isolation:

- The composite/resolve (`workbench_composite.bsl.hh:66`) discards any pixel where
  `depth == 1.0` (background). So the solid needs the prepass cube-depth (<1.0) to
  survive into the composite's `depth_tx` read.
- My pipeline is correct: logged prepass STATE = `write_mask=0x3f depth_test=3
  (LESS_EQUAL) write_depth=1` → `wgpu_pipeline.cc` maps this to
  `depthWriteEnabled=True`, `depthCompare=LessEqual`. Correct.
- **Decisive test:** forcing `depthCompare=Always` for the 3-attachment gbuffer prepass
  (temporary, reverted) still produced NO solid. Always bypasses the test, so the
  cube's depth writes would unconditionally reach the composite if they persisted —
  they do not. The workbench clears depth to 1.0
  (`workbench_engine.cc:494 GPU_framebuffer_clear_depth_stencil(..., 1.0f, ...)`).

Conclusion: the prepass depth writes are **not persisting to the composite's depth
read** — a gbuffer depth attachment store-op / depth-texture identity / sampled-depth
binding issue. That lives in `wgpu_framebuffer.cc` (begin_load_pass store actions,
patch 0110 family) and/or `wgpu_context.cc`/`wgpu_texture.cc` (depth_tx bind) — the
**r28b / framebuffer lane's files, NOT the batch/pipeline/buffer files I own.** Handing
off with this precise localization (see report). The single-attachment offscreen path
(outline prepass) works, so this is specific to the multi-attachment gbuffer + its
sampled-depth consumer.

## Also observed (not blocking, noted for owners)

- **UI chrome renders VERTICALLY INVERTED** (File/Edit menu bar at window bottom,
  status bar at top) in the current shared build. My diff is instrumentation-free and
  touches none of the flip/present path (`flip_y`, `is_window_backbuffer`, the
  constant-1000 y-sign override, presentBackbuffer). The modified files on the flip
  path are the **ghost lane's** in-flight WIP: `platform_web/ghost/GHOST_SystemWeb.cc`,
  `GHOST_WindowWeb.cc/.hh`, `platform_web/shell/boot-windowed.js` (resize/DPR work).
  Not this lane's defect. The 3D viewport interior itself is upright (gizmo Z-up,
  grid receding correctly).
- **Packed normals:** `to_wgpu_vertex_format` maps `GPU_COMP_I10` →
  `Unorm10_10_10_2` (unsigned) for the workbench `nor` attribute, which is a SIGNED
  2-10-10-10 normal. WebGPU has no `Snorm10_10_10_2`, so signed packed normals cannot
  be represented directly; this will misshade (not hide) surfaces once the solid pass
  renders. Deferred — a shading-correctness item, not a geometry/visibility one.

## Landing checklist (this round)

- [x] Patch 0114 written, reverse-apply clean, series entry added.
- [x] All temporary instrumentation reverted (wgpu_batch/index_buffer/vertex_buffer/
      pipeline) — grep for `bw-r28`/`bw_r28`/`TEMPORARY` is empty across owned files.
- [x] Native census GREEN 5/5 (148/158 + static 956/973).
- [x] lane-a mirror synced (wgpu_batch.cc).
- [x] Evidence PNGs + SPDX sidecars under platform_web/shell/evidence/.
- [ ] Defect #1 solid pass: handoff to the r28b/framebuffer lane (depth store/persist).
