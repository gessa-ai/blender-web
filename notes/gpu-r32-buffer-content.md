<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 32 (gpu-backend worker) - the workbench SOLID cube: buffer-content + wrong-slot-bind suspects FALSIFIED; root cause GPU-proven as the DEPTH-STENCIL ATTACHMENT's presence blocking ALL rasterization into the SHARED, composite-sampled gbuffer depth (Depth32FloatStencil8). No fix landed (deep Dawn/emdawn cross-submit resource-state seam; characterized after the full elimination chain below).

Continues notes/gpu-r31-readback-discriminator.md (its DO-NOT-RE-RUN list + r30's stand). Rig =
the r31 recipe (headed Playwright bundled Chromium, `NODE_PATH=/Users/paws/plushly/game-platform/node_modules`,
opt tree `build-wasm-windowed-opt` port 8124, `?gate=1280x720` + `?pyexpr=` splash-off + per-0.3s
VIEW_3D `tag_redraw()` kick, `os.environ["BW_DIAG"]="1"`). Drivers: `sandbox/gpu-r32/{bufcap,pooltest,injecttest}.mjs`.
All `[bw-r32]` instrumentation reverted before commit - grep `bw-r32`/`BW_*` across `upstream/source/blender/gpu/webgpu/` is EMPTY.

## STAGE 0 - THE TOOL (buffer-content readback, self-test with teeth = PASS)

Extended r31's texture readback to buffers: a kick-then-consume `CopyBufferToBuffer` into a
MapRead|CopyDst staging buffer + `MapAsync(CallbackMode::AllowSpontaneous)` (the ONLY mode that
delivers on the imported-device windowed profile - ADR-007/r31), returning immediately; the
callback dumps raw bytes + an 8-word header to `/tmp/bw_bufread_<n>.bin`, pulled from the rig via
`window.__bwModule.FS.readFile`. A BW_DIAG-gated CopySrc grant (wgpu_buffer.cc) made UBOs
readable too (UBOs are created `readable=false`; SSBOs/VBOs already carry CopySrc).

SELF-TEST (has teeth): read back the GPU-generated indirect-args buffer that the prepass
DrawIndexedIndirect actually consumes - it shows `[36,0,0,0,0]` at offset 0 and `[36,1,0,0,0]` at
offset 32 (idxCount=36, instCount=1, firstIdx=0, baseVtx=0, firstInst=0). Independent ground truth
(the cube's 36-index / 1-instance command) confirms the buffer path is real. 0 GPU errors.

## STAGE A/B - the CONSUMED CONTENT is CORRECT and BYTE-IDENTICAL to the working outline

Captured, once per distinct target, EVERY bound buffer + vertex buffer + the indirect args, for
BOTH `workbench_prepass_mesh_opaque_studio_material_no_clip` (fails) and
`overlay_outline_prepass_mesh` (works). Both draw the same default cube via `multi_draw_indirect`
at `draw_offset=32 count=1` reading the same `[36,1]` command.

Workbench prepass @binding map (from the dumped WGSL, confirmed by the interface map):
`b0 ubo drw_clipping_` · `b1 ssbo materials_data` · `b2 ubo view_buf` · `b3 ssbo drw_matrix_buf` ·
`b4 ssbo res_id_with_custom_id_buf (vec2<u32>)` · `b5 ubo push-constants`. Transform chain:
`resource_id = res_id_with_custom_id_buf[gl_InstanceIndex].x` → `model = drw_matrix_buf[resource_id]`,
`view = view_buf[0]`, `gl_Position = view.winmat * view.viewmat * model * pos`.

| resource (role) | workbench | outline | readback verdict |
|---|---|---|---|
| view matrices (winmat/viewmat) | b2 UBO | b0 UBO | IDENTICAL, valid viewmat (translation 0.05,-0.0007,-18.388) |
| object model matrix SSBO | b3 | b1 | SAME buffer; drw_matrix_buf[0]=identity, [1]=cube (default cube = identity) |
| resource-id SSBO | b4 (res_id_with_custom_id, `[1,0]`) | b2 (res_id_buf, `1`) | resource_id = **1** for BOTH |
| materials SSBO | b1 (`0.8,0.8,0.8`) | - | valid gray |
| pos VBO (@location 0) | slot1, `1,1,1,-1,1,1,-1,-1,1,…` | slot0, IDENTICAL bytes | correct ±1 cube coords |
| nor VBO (@location 1) | slot0 (packed) | - | valid |
| indirect args | `[36,1]` @off32 | `[36,1]` @off32 | correct |

**VERDICT - r31's BOTH suspects FALSIFIED.** (1) Buffer content is correct: every transform input
is valid and byte-identical to the working outline. (2) NO wrong-slot bind: all 6 bindings carry
the correct-kind, correct-content buffer. Computing the clip position from the captured matrices for
pos=(1,1,1): ndc≈(0.109, 0.089, **0.9994**) - on-screen, valid depth, NOT degenerate. So the vertex
stage produces the same on-screen triangles the outline does.

## STAGE C - the pipeline is EXONERATED, the DRAW rasterizes zero fragments regardless of shader

- **Pool (wgpu_pipeline `get`) trace:** the workbench prepass gets its OWN uniquely-hashed
  (`2c00fce0…`), freshly-built (MISS→HIT) pipeline; NO collision with the outline (`c9c614e3…`).
  `BW_NOCACHE` (rebuild fresh every draw) → still zero fragments. Pool/staleness dead (busts the
  r32-handoff confound).
- **BW_INJECT (fragment-only):** keep the REAL vertex module (proven on-screen) + a TRIVIAL
  no-discard fragment writing constants to the 3 MRT targets, pipeline `build=OK` non-null,
  cull=none, ff=cw, dwrite=1, dcompare=LessEqual → ALL FOUR gbuffer attachments EMPTY (depth 1.0,
  material/normal/objectid nz=0). The prepass fragment has no `discard`/no clip, so this is not a
  fragment defect.
- **BW_INJECT_VS (guaranteed on-screen triangle):** a fullscreen-ish triangle (ndc −0.8..0.8,
  z=0.3) that ignores all attributes, pipeline `build=OK` → STILL EMPTY. The draw produces zero
  fragments no matter the geometry or shader.

## THE ROOT CAUSE - the SHARED gbuffer DEPTH-STENCIL attachment's PRESENCE blocks rasterization

Discriminator matrix (BW_NOCACHE fresh pipeline throughout; 0 GPU errors in every non-error case):

| experiment | prepass gbuffer write |
|---|---|
| baseline (depth attachment present) | **EMPTY** (depth 1.0, colors 0) |
| `BW_NODEPTH` (drop depth attachment + depthStencil state) | **RASTERIZES** - material fills 0.4% (the cube) |
| `BW_DALWAYS` depthCompare=Always (depth present) | EMPTY (not the depth test) |
| `BW_FIXSTENCIL` stencil pass-through Always/Keep (depth present) | EMPTY (not the stencil test) |
| `BW_DCLEAR` force depth loadOp=Clear(1.0) in the draw's own pass | EMPTY (not clear-vs-load / cross-submit clear separation) |
| `BW_DVIEW` explicit DepthOnly view | GPU-ERROR "attachment must encompass all aspects (Depth32FloatStencil8)" → default `CreateView()` is CORRECT |
| `BW_1MRT` reduce to a single color attachment + depth | EMPTY (not the MRT count) |
| viewport/scissor (`BW_VP`) | identical to outline: `0,0,1048,621`, sctest=0 (not viewport/scissor) |

So removing the depth-stencil attachment is the ONLY thing that restores rasterization, and it is
NOT the depth test, stencil test, clear/load, view, MRT count, or viewport.

**The distinguishing texture (the decisive comparison):**
- The WORKING outline prepass writes ITS OWN depth: `outline_depth` writtenFrac 0.0157, min
  **0.99938** (= the cube at the computed 0.9994), into a DEDICATED Depth32FloatStencil8
  (`dptr 0x2c7d8968`). So Depth32FloatStencil8 rasterization WORKS.
- The workbench prepass shares the gbuffer depth (`dptr 0x2d068340`) across MANY passes
  (`BW_DALL`: ccount 1/2/3 all share it) AND it is the composite's SAMPLED depth (r30 `[bw-r30-fbid]`:
  prepass-depth-ptr == composite-read-depth-ptr). Both depths are byte-for-byte the same descriptor:
  fmt=49 (Depth32FloatStencil8), usage=0x17 (RenderAttachment|TextureBinding|CopyDst|CopySrc),
  samples=1, layers=1, mip=1, size 1048x621 - indistinguishable via the API.
- Hazard check (`BW_HZ`): the gbuffer depth is NOT bound as a sampled texture in the state manager
  during the prepass draw (`depth_bound_as_sampler_slot=-1`) - so it is NOT a live within-encoder
  attachment-and-sampled binding hazard (which would also raise a Dawn error; none seen).

**CONCLUSION - confirms r30's leading hypothesis #3.** A Dawn/emdawnwebgpu cross-submit
resource-STATE issue on a texture used as a render ATTACHMENT in one submit and a SAMPLED texture in
another within the same frame (the shared gbuffer depth is both; the port's pass-per-draw /
one-CommandEncoder-and-Submit-per-draw model records each in a separate submit). The identical
geometry rasterizes into a DEDICATED depth (outline). It is NOT attributable to any Blender-side
pipeline / pass / bind-group / depth-stencil-state configuration - every one is proven correct and
matches the working outline. No in-app-configurable fix restored rasterization within the attempt
bound; the fix lives in the cross-submit / pass-per-submit resource-state seam.

## NEXT ROUND - do NOT re-run the eliminated experiments

DO-NOT-RE-RUN (r32; plus r29/r30/r31 lists):
1. Buffer/VBO CONTENT of the 6 bound buffers + vertex buffers - all correct and byte-identical to
   the working outline (view/model/resource_id/materials/pos/nor/indirect args). Suspect (1) dead.
2. Wrong-slot bind - none; the 6-entry bind group is correct-kind + correct-content. Suspect (2) dead.
3. Pipeline pool collision / staleness - exonerated; unique hash, fresh `BW_NOCACHE` build still fails.
4. Depth TEST (depthCompare=Always), stencil TEST (pass-through Always/Keep), depth clear-vs-load
   (self-clear to 1.0 in the draw pass), explicit depth view, MRT-count reduction to 1, forcing the
   frontend viewport/scissor - NONE restore rasterization.
5. Shader-module injection (trivial FS + fullscreen-triangle VS) - the pass blocks ALL draws
   regardless of shader; this busts r30's confounded injection (now with the pool proven fresh).

The fix must target the cross-submit state of the SHARED gbuffer Depth32FloatStencil8 depth
(attachment-in-one-submit + sampled-in-another). Candidate directions, in order:
- (a) Give the workbench prepass a DEDICATED depth texture (like the outline's, which works) and
  blit/copy it into the composite-sampled gbuffer depth after the prepass. Attachment-only depth
  avoids the alternating-usage state entirely.
- (b) Build a standalone Dawn/emdawnwebgpu repro that alternates a Depth32FloatStencil8 texture
  between depth-attachment (submit A) and sampled-texture (submit B) across submits in the
  imported-device windowed profile, and confirm/file whether draws into it silently no-op. If it is
  a Dawn bug, a targeted usage/barrier workaround or a pinned-port note is the disposition.
- (c) Reduce the pass-per-submit fan-out for the workbench frame so the attachment→sampled
  transition is tracked intra-encoder (large architectural change; r30 flagged the model).

## Landing state (this round)
- [ ] Gray shaded cube: NOT fixed. Root cause re-localized (from r31's "buffer content / wrong-slot
      bind", both FALSIFIED) to the shared gbuffer depth-stencil attachment's presence blocking
      rasterization - a Dawn/emdawn cross-submit resource-state seam. No patch landed (0118 reserved;
      no 0119).
- [x] Buffer-content readback tool built + self-tested with teeth (indirect args 36/1); kept as a
      TEMPLATE here (not landed as a patch - fully reverted with the rest of the hunt instrumentation,
      grep-clean). Re-land as a keeper (sibling of 0117) in a dedicated tooling round if wanted.
- [x] ALL `[bw-r32]` instrumentation reverted; grep `bw-r32`/`BW_*` across `upstream/…/webgpu/` EMPTY.
- [x] Windowed opt relinks clean on the restored source (build-wasm-windowed-opt blender_browser).
- [x] Native census GREEN (build-native-gpu blender_test relinked at HEAD, 2.3s = zero net change):
      m3 5/5 - 148 PASS / 8 FAIL / 2 CRASH + static_shaders 956/973; patches_series attests
      0110-0117 applied, NO 0118/0119. ledger/results/m3.json regenerated.
- Evidence: `sandbox/gpu-r32/{bufcap,pooltest,injecttest}.mjs` + `sandbox/gpu-r32/r32-*.analyses.json`
  (distilled per-run readback analyses; raw `.all.log` dumps dropped as reproducible data);
  `platform_web/shell/evidence/m4-r32-{cap1,nodepth}-shot.png` (baseline no-cube + the NODEPTH
  rasterizes-the-cube breakthrough).
