<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 30 (gpu-backend worker) - the workbench SOLID cube: the r30 driver hypothesis (async pipeline) FALSIFIED, and r29's "the pipeline rasterizes zero fragments" FALSIFIED. The workbench prepass pipeline is PROVEN good in standalone Chrome; the defect is in the backend draw-execution path (a valid, on-screen, depth-bypassed forced draw still writes nothing to the gbuffer the composite reads). No fix landed.

Continues notes/gpu-r29-opaque-indirect.md. Rig = the r29 visible recipe (headed
Playwright bundled Chromium, opt tree `build-wasm-windowed-opt` port 8124, `?gate=1280x720`
+ `?pyexpr=` splash-off + a per-0.3s VIEW_3D `tag_redraw()` kick). Method = temporary
`[bw-r30-*]` stderr instrumentation in the OWNED webgpu backend + a NEW standalone Chrome
WebGPU probe (`sandbox/gpu-r30/standalone_probe.mjs`) that compiles the EXACT dumped
workbench WGSL and draws it directly. All instrumentation reverted before landing (grep
`bw-r30` across `upstream/` is empty).

## HEADLINE 1: the driver's PRIMARY r30 hypothesis (async CreateRenderPipeline never resolves) is FALSE.

The backend calls the SYNCHRONOUS `device.CreateRenderPipeline(&desc)` (wgpu_pipeline.cc
build_pipeline, last line). In the emdawnwebgpu port that maps to `wgpuDeviceCreateRenderPipeline`
(library_webgpu.js:1753) which calls the SYNCHRONOUS JS `device.createRenderPipeline(desc)` -
NOT `createRenderPipelineAsync`. There is no pending/async handle to leak. The port's async
path (`emwgpuDeviceCreateRenderPipelineAsync`, webgpu.cpp:2020) is unused by the backend. So
"draws recorded with a pending pipeline are silent no-ops" cannot be the cause.

## HEADLINE 2: r29's core conclusion ("the workbench_prepass PIPELINE rasterizes ZERO fragments") is FALSIFIED by standalone Chrome.

`sandbox/gpu-r30/standalone_probe.mjs` compiled the EXACT dumped workbench vertex+fragment
WGSL (dumped live via `[bw-r30-wgsl]` from finalize) in the SAME bundled Chromium the rig
uses, built a render pipeline, bound identity matrices so the vertex maps a triangle
on-screen, drew it, and read back the object_id target. RESULTS (all center=1, 512 nonzero
px, 0 uncaptured errors; a hardcoded-triangle positive control also rasterized):

- `getCompilationInfo()` on both workbench stage modules = EMPTY (Chrome's Tint accepts the
  WGSL cleanly, incl. the `@interpolate(flat)` Tint emits on the u32 fragment output).
- workbench modules + `layout:'auto'` -> RASTERIZES.
- workbench modules + a backend-style EXPLICIT layout (all 6 @binding decls, Vertex|Fragment
  visibility, read-only-storage at 1/3/4) -> RASTERIZES.
- workbench modules + the EXACT backend vertex layout (nor=Unorm10_10_10_2@slot0 Vertex,
  pos=Float32x3@slot1 Vertex, ac=Float32x4@slot2 INSTANCE dummy, au=Float32x2@slot3 INSTANCE
  dummy) -> RASTERIZES.

=> the pipeline, both shader modules, the explicit pipeline layout, and the exact vertex
buffer layout are ALL good. The bug is NOT in the pipeline. It is in the backend's DRAW
EXECUTION into the workbench gbuffer render pass.

## The descriptor diff (outline-vs-workbench) has NO smoking gun

`[bw-r30-desc]` dumped the full RenderPipelineDescriptor for both. Structurally equivalent:
- multisample DEFAULT count=1 mask=0xffffffff a2c=0 (BOTH) — the sample-mask hypothesis is dead.
- primitive topo=TriangleList frontFace=CW cull=None (BOTH), flip_y=1 (BOTH).
- depth fmt=Depth32Float compare=LessEqual writeEnabled=1 (BOTH).
- workbench: color_count=3 (RGBA16Float/RG16Float/R16Uint), pos=loc0 Float32x3 (SAME as the
  outline's pos), plus nor/ac/au. Outline: color_count=1 (R16Uint), pos=loc0 only.
- clip_distances count=0 in every dumped WGSL (Tint drops the spec-const-folded no_clip
  clip-distance output despite the writer enabling `kClipDistances`). Clip distances ruled out.

## r29's key experiment was CONFOUNDED (why "hardcode still fails" was misread)

r29 hardcoded `out_position = vec4(pos*0.3, 1)` — which STILL READS `pos`. If the real draw
fed `pos=0`, that collapses every vertex to the origin (degenerate, zero fragments), which
r29 read as "geometry ruled out". r30 removed the confound: a pos-INDEPENDENT hardcode
(`v.gl_Position = fixed_triangle[vertex_index % 3]`, injected into the emitted vertex WGSL,
`[bw-r30-hack]`) — verified to COMPILE and RASTERIZE standalone (`sandbox/gpu-r30/verify_injected.mjs`,
center=1) — STILL produced no composited output in the backend. So it is not vertex-data feeding.

## THE DECISIVE BACKEND ELIMINATION CHAIN (each a live experiment on the opt build; do NOT re-run)

With the pos-independent `vertex_index`-only on-screen triangle injected into the workbench
prepass vertex, and a standalone-PROVEN pipeline:

1. `[bw-r30-force]` forced a DIRECT non-indexed `Draw(3,1,0,0)` (explicit instanceCount=1) in
   multi_draw_indirect, bypassing the GPU-generated indirect args entirely. STILL no
   composited fragments, 0 errors. => not the indirect args / instanceCount (definitively
   closes r28b's original Bug B and re-confirms r29's falsification, now un-confounded).
2. `[bw-r30-depthbypass]` forced `depthCompare=Always` in the pipeline (fragments cannot be
   depth-rejected). STILL nothing. => not the depth test / loaded depth value.
3. `[bw-r30-fbid]` + `[bw-r30-cmpid]` compared the prepass WRITE targets to the composite READ
   textures by pointer. IDENTITY CONFIRMED (0116 works): prepass depth=0x..64fc0 /
   normal=0x..0a958 / material=0x..a57c0 are EXACTLY what the resolve samples at dense
   bindings 0/1/2. So the composite reads the gbuffer the prepass writes.
4. `[bw-r30-rp]` dumped the render-pass config begin_load_pass builds for the prepass: 3 color
   attachments + depth, ALL 1048x621, layers=1, samples=1, correct formats
   (RGBA16Float/RG16Float/R16Uint/Depth32Float), depthLoadOp=Load, depthStoreOp=Store,
   colorAtt loadOp=Load storeOp=Store. Structurally identical to the standalone pass that
   rasterizes. No viewport/scissor is set on the single-pass batch path (default = full).

## RESIDUAL (re-localized): a valid draw into the workbench gbuffer render pass writes NOTHING, while a CLEAR does

r29 proved that force-CLEARING this same begin_load_pass depth to 0.5 shades the whole
viewport (the render-pass -> resolve -> visible path works). r30 proves the pipeline, modules,
layout, vertex layout, descriptor, fb identity, and render-pass config are ALL correct, and
that a forced DIRECT draw of an on-screen triangle with the depth test bypassed and 0 errors
STILL produces nothing the composite reflects. So: clears store and reach the composite, but
DRAWS into the same pass produce no rasterized fragments in the gbuffer the composite reads.

This is a backend draw-execution defect, NOT a pipeline defect, that the available
CPU + WGSL-dump + standalone-Chrome + visual toolset could not pierce the last layer of
within this round's budget (GPU readback of the gbuffer contents right after the prepass
submit is the registered `gpu-sync-readback-windowed` deferral; it is exactly what would
distinguish "the draw wrote the gbuffer but it was lost/overwritten before the composite"
from "the draw produced no fragments").

## LEADING NEXT-ROUND HYPOTHESES (do NOT re-run the eliminated experiments above)

The port is UNIQUE in its pass-per-draw + one-CommandEncoder-and-Submit-per-draw model
(multi_draw_indirect and draw() each `CreateCommandEncoder -> begin_load_pass -> ... ->
Finish -> queue.Submit`). Native Blender records one big command buffer. The surviving
candidates all live in that seam:

1. SUBMIT ORDERING / cross-submit hazard: the prepass draw's Submit and the composite's
   Submit are independent. If a workbench depth/color pass (e.g. workbench_merge_depth /
   overlay depth-copy) or a lazy-init/clear lands between them in submit order and resets the
   gbuffer depth to 1.0, the composite discards. r28b's `[bw-r28c-seq]` said "nothing
   re-clears" but only tracked clears, not depth-WRITING copy passes. INSTRUMENT: log every
   queue.Submit with (shader, fb depth-tex ptr, first color-tex ptr, op) across a full frame
   and read the ACTUAL submit order into the shared gbuffer depth.
2. GBUFFER CONTENTS after the prepass submit (the real discriminator): needs the
   gpu-sync-readback-windowed deferral. If it clears for even a single blocking readback,
   read the gbuffer depth immediately after the prepass Submit — 0.5-in-triangle vs 1.0
   settles "written-then-lost" vs "never-written" in one shot.
3. A Dawn resource-STATE / usage issue specific to a texture used as a render attachment in
   one submit and a sampled texture in another within the same frame (the gbuffer is both).
   Standalone used the texture only as an attachment; the app alternates. Check whether the
   attachment's contents survive the transition across submits in this backend's usage flags.

## Landing state (this round)
- [x] All `[bw-r30-*]` instrumentation reverted; grep `bw-r30`/`BW_R30` across `upstream/` is empty.
- [x] Clean opt-build relinks (build-wasm-windowed-opt blender_browser, 40 s) on the restored source.
- [ ] Native census (build-native-gpu + run.sh --scope m3) — running; expect UNCHANGED baseline
      (148/158 + static 956/973) since the net source change is zero (pure revert).
- [x] NO fix landed => NO patch 0117. r29's + the driver's r30 hypotheses corrected for the next lane.
- [ ] Root cause of the non-writing workbench prepass DRAW — OPEN; see the pass-per-submit hypotheses.
- Evidence: `platform_web/shell/evidence/m4-r29-r30-{vidhack,force,depthbypass}-shot.png` (viewport
  shows the cube OUTLINE only, no shaded triangle), `sandbox/gpu-r30/*.wgsl` (dumped modules),
  `sandbox/gpu-r30/standalone_probe.mjs` + `verify_injected.mjs` (the pipeline-exoneration proofs).
