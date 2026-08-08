<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 29 (gpu-backend worker) - the workbench SOLID cube: predecessor's Bug B premise FALSIFIED; root cause re-localized to "the workbench opaque prepass PIPELINE rasterizes ZERO fragments" (deep, 0-error). No fix landed; precise characterization + full elimination chain below.

Continues notes/gpu-r28-solid-composite.md (r28b-take3 Bug A fixed as patch 0116; Bug B = "the
opaque draw-group's GPU-generated DrawIndexedIndirect args produce no geometry"). Rig = the r23
visible recipe (headed Playwright bundled Chromium, `?gate=1280x720`, `?pyexpr=` splash-off + a
per-0.3s VIEW_3D `tag_redraw()` kick), opt tree `build-wasm-windowed-opt` port 8124. Method =
temporary CPU fingerprints + translated-WGSL dumps + framebuffer-op traces + composite-shader
visualizers (`[bw-r29-*]`), a 2D-canvas `drawImage`+`getImageData` center-pixel probe (background
= 63,63,63; a composited shaded cube would leave it), all reverted before landing (grep `bw-r29`
across upstream/ is empty; census re-ran GREEN on the clean source). Rig driver:
`sandbox/gpu-r29/diag_opaque.mjs`.

## HEADLINE: the predecessor's Bug B is WRONG. It is NOT the indirect args.

r28b concluded the OPAQUE group's GPU-generated `DrawIndexedIndirect` args (instance_len) are 0.
That is FALSIFIED here three independent ways:

1. **CPU DrawGroup/DrawPrototype fingerprint** (`[bw-r29-cpu]`, in `draw_command.cc`
   `DrawMultiBuf::generate_commands`, at push_update time - CPU-written, no readback): the cube's
   tris draw-group is PERFECT - `len=1 front_facing_len=1 vertex_len=36 vertex_first=0
   base_index=0 start=0 expand=GPU_PRIM_NONE`, prototype `res_id=1 (inv=0) instance_len=1
   custom=0`. Only TWO distinct DrawMultiBuf fingerprints exist in the default scene: this tris
   cube (prim=TRIS) and a degenerate prim=LINES vlen=0 group. The workbench-opaque prepass and
   the overlay-outline mesh prepass draw the SAME cube mesh as tris and collapse to this one
   fingerprint (both `res_id=1`), which means they SHARE the draw::Manager + the View's
   visibility_buffer (`Manager::compute_visibility` runs once per view; `view.get_visibility_buffer()`).
   The outline renders ⇒ res_id=1's visibility bit is set ⇒ the opaque group's generate reads the
   identical inputs and produces the identical valid command.
2. **Draw-site fingerprint** (`[bw-r29-draw]`, `wgpu_batch.cc::multi_draw_indirect`): the opaque
   prepass issues `DrawIndexedIndirect` at `off=32` (= front-facing command `command_buf[2*grp+1]`,
   correct), indexed, `color_count=3 depth_fmt=49 write_mask=0x3f dwrite=1 depth_test=3(LESS_EQUAL)
   flip_y=1` - STRUCTURALLY IDENTICAL to the working outline draw except color_count (3 vs 1).
3. **Forced DIRECT draws** (bypass command_buf entirely): a forced `DrawIndexed(36,1,0,0,0)` AND a
   forced non-indexed `Draw(24,1,0,0)` on the workbench prepass pipeline BOTH produce ZERO
   fragments too. Since a direct draw with instanceCount=1 does not read command_buf, the
   GPU-generated instance_len is irrelevant. **H1 (indirect args) is dead.**

## THE ACTUAL SYMPTOM (re-localized): the workbench opaque prepass rasterizes NOTHING

Confirmed via the composite visualizers (temporarily editing `workbench_composite.bsl.hh`'s resolve
to output the gbuffer directly instead of `discard depth==1.0`):
- Binary depth viz (`depth<0.9999 ? red : black`) via BOTH `texture(depth_tx,uv)` and
  `texelFetch(depth_tx, ivec2(fragCoord), 0)`: NO red anywhere ⇒ the sampled gbuffer depth is 1.0
  everywhere (the prepass wrote no cube depth). The texelFetch path rules out any resolve
  UV/`textureSize` bug.
- gbuffer material.rgb + normal-length viz: uniform empty ⇒ the gbuffer COLOR attachments are also
  empty. So the prepass produced no fragments at all (not merely a depth-store or resolve-read
  fault).

So even a valid draw of on-screen geometry with `depthWrite=1`, cull=None, and a render pass whose
loadOp-clears DO reach the resolve (proven: forcing the prepass begin_load_pass to Clear depth=0.5
made the whole viewport shade and occluded the grid - the render-pass→resolve path works and the
gbuffer identity is correct) still yields ZERO rasterized fragments, with ZERO GPU validation
errors, while the structurally identical single-attachment overlay-outline prepass (same cube, same
view, same `multi_draw_indirect` path, LESS_EQUAL, depth cleared 1.0) DOES rasterize.

## FULL ELIMINATION CHAIN (each ruled out by a live experiment on the opt build)

- indirect args / instance_len - forced direct DrawIndexed + non-indexed Draw(24,1) both fail.
- geometry / matrix / resource_id - hardcoded `out_position = vec4(pos*0.3,1)` (verified compiled:
  WGSL `v.gl_Position = vec4(pos*0.30000001, 1.0)` then the std z-remap+y-flip; on-screen ±0.3 NDC,
  z∈[0.35,0.65]) still fails.
- vertex-buffer binding - `[bw-r29-vbind]`: pos bound (slot1, vbo1, valid, vertex_len=24), nor
  bound (slot0), uv/color dummy-filled. pos IS fed.
- culling - `[bw-r29-pipe]`: workbench prepass `culling_test=0 (None)`, frontFace=CW (correct
  y-flip winding compensation, same as outline); forcing `cullMode=None` explicitly changed
  nothing.
- depth - cleared 1.0 (`[bw-r29-fb]` seq trace: clear_fb clears 0x…818 → gbuffer_fb LOADS it,
  nothing re-clears before the resolve), LESS_EQUAL, resolve reads 1.0; forcing depth-clear-to-0.5
  reaches the resolve (path works). depthWriteEnabled follows write_mask&GPU_WRITE_DEPTH = True.
- gbuffer identity - `[bw-r29-draw]` fb attachment ptrs == `[bw-r29-sample]` resolve sampled ptrs
  (depth 0x…818→0x…818, material/normal match). The resolve samples the exact prepass targets.
- resolve UV / depth sampling - texelFetch bypass reads 1.0; clear-to-0.5 read as 0.5. Sampling OK.
- MRT count - reducing the gbuffer to a SINGLE color attachment (material)+depth (matching the
  outline) STILL fails.
- color formats - material RGBA16F→RGBA8Unorm: no change (0 errors).
- integer target - object_id R16Uint→SFLOAT_16 + float output: no change (confounded by 24
  consumer-side errors, but the prepass still didn't rasterize).
- fragment complexity / discard - a CONSTANT fragment (`material = vec4(1,0,0,1)`, no resource
  reads) still fails; the real fragment has no `discard`/`frag_depth`.
- flat integer varying - `[[flat]] int object_id`→`float`: no change.
- clip distances - the vertex WGSL declares `gl_ClipDistance` in the internal `gl_PerVertex` but
  Tint does NOT emit it in the entry-point output struct (`tint_symbol` = position + varyings only),
  so no clip-distance output. Ruled out.
- viewport - `[bw-r29-vp]`: workbench prepass and outline both report viewport [0,0,1048,621];
  `multi_draw_indirect` applies neither (default = full attachment), identical for both.
- pipeline validity - pipeline builds (draw executes; loadOp clears reach the resolve ⇒ not an
  error pipeline); zero GPU validation/uncaptured/Dawn errors across every boot.

## RESIDUAL: the ONLY surviving difference is the workbench_prepass shader/pipeline itself

Even fully minimized - hardcoded on-screen vertex + constant single-output fragment + single color
attachment + forced non-indexed direct draw - the `workbench_prepass_mesh_opaque_studio_material_no_clip`
pipeline rasterizes ZERO fragments, 0 errors, while `overlay_outline_prepass_mesh` (built through
the identical `build_pipeline`→`multi_draw_indirect` path) works. The failure therefore lives in
how THIS shader's create-info/interface is compiled into a Dawn render pipeline (something about its
resource table / inter-stage set / entry-point that produces a valid-but-non-rasterizing pipeline),
NOT in the vertex logic, fragment logic, attachments, formats, depth, cull, viewport, indirect args,
or the resolve. This is a Dawn/emdawnwebgpu-level or pipeline-assembly subtlety that the available
CPU-only + WGSL-dump + visual toolset (GPU readback is the registered `gpu-sync-readback-windowed`
deferral) could not pierce within this round's budget.

## NEXT-ROUND STARTING POINTS (do NOT re-run the eliminated experiments above)

1. Diff the FULL Dawn `RenderPipelineDescriptor` (vertex+fragment WGSL entry points, all
   inter-stage `@location`s and interpolation, bind-group layout entries, buffer layouts) between
   `overlay_outline_prepass_mesh` (works) and `workbench_prepass_mesh_opaque_...` (fails), by
   dumping the descriptor fields at `build_pipeline` time - the divergence is in there.
2. Try the OUTLINE shader rendering into the workbench 3-attachment gbuffer (and vice versa) to
   nail "shader vs framebuffer" definitively (this round could not swap them cleanly).
3. Inspect whether Dawn's async pipeline creation for this shader is completing (emdawnwebgpu is a
   JS binding; a pending/async pipeline could SetPipeline a not-yet-valid object that no-ops the
   draw without an uncaptured error) - check `CreateRenderPipeline` vs `CreateRenderPipelineAsync`
   usage and completion.
4. The `@interpolate(flat)` Tint emits on the u32 object_id FRAGMENT output (invalid WGSL on an
   entry-point return member) is tolerated by Dawn here and is NOT the cause (the constant
   single-output fragment has no such attribute and still fails), but is worth cleaning regardless.

## Landing state (this round)
- [x] All `[bw-r29-*]` instrumentation reverted; grep `bw-r29`/`BW_R29` across upstream/ is empty.
- [x] Clean opt-build compiles; native census re-ran GREEN 5/5 (148/158 + static 956/973) on the
      restored shared source - the reverts are exact, other lanes unaffected.
- [x] NO fix landed ⇒ NO patch 0117; predecessor's Bug-B localization corrected for the next lane.
- [ ] Root cause of the non-rasterizing workbench_prepass pipeline - OPEN; see starting points.
