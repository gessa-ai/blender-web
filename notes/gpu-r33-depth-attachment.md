<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 33 (gpu-backend worker) - THE LAST M4 SOLID-CUBE DEFECT IS FIXED (patch 0118). Root cause: the WebGPU backend never emitted the dynamic STENCIL REFERENCE, so the workbench opaque gbuffer prepass (GPU_STENCIL_NEQUAL at reference 0xFF) compared against reference 0 and rejected every fragment. r29-r32 mis-localized this to the depth-stencil attachment / a Dawn cross-submit seam because dropping the combined Depth32FloatStencil8 attachment ALSO drops the stencil test.

Continues notes/gpu-r32-buffer-content.md (its + r29/r30/r31 DO-NOT-RE-RUN lists still stand; none re-run this round). Rig = the r32 recipe (headed Playwright bundled Chromium, `NODE_PATH=/Users/paws/plushly/game-platform/node_modules`, opt tree `build-wasm-windowed-opt` port 8124, `?gate=1280x720` / `1600x900` + `?pyexpr=` splash-off + per-0.3s VIEW_3D `tag_redraw()` kick, `os.environ["BW_DIAG"]="1"`). Drivers: `sandbox/gpu-r33/{disc1,verify}.mjs`. All `[bw-r33]` hunt instrumentation reverted before commit; grep `bw-r33`/`BW_RO_CANARY` across `upstream/source/blender/gpu/webgpu/` is EMPTY.

## DISCRIMINATOR 1 (the driver's prime suspect) - readOnly theory FALSIFIED, a NEW discriminator surfaced

Field dump of the exact `RenderPassDepthStencilAttachment` (begin_load_pass) + the pipeline
depth/stencil state, per draw, for the failing workbench prepass vs the working outline
(both draw the default cube through `multi_draw_indirect` @ off=32 count=1):

| field | workbench prepass (FAILS) | outline (WORKS) |
|---|---|---|
| pipeline depthFmt | 49 (Depth32FloatStencil8) | 49 |
| writeMask | 0x3f (color+depth+STENCIL) | 0x1f (color+depth, NO stencil) |
| depthTest | 3 (LessEqual) | 3 |
| **stencilTest** | **3 = GPU_STENCIL_NEQUAL** | **0 = GPU_STENCIL_NONE** |
| stencilRef (frontend mutable_state) | **255 (0xFF)** | (unused; test NONE) |
| dsa depthReadOnly | **0** | **0** |
| dsa stencilReadOnly | **0** | **0** |
| dsa dLoad/dStore/sLoad/sStore | 1/1/1/1 (Load/Store) | 1/1/1/1 |
| attachment fmt (dtex) | 58 | 58 |

- **readOnly theory DEAD.** Both passes are `depthReadOnly=0 stencilReadOnly=0`. `begin_load_pass`
  is the SHARED draw path (wgpu_framebuffer.cc) and NEVER sets either readOnly flag, so it is
  structurally impossible for the backend to poison the sampled depth read-only. No invalid pass,
  no dropped command buffer from that cause.
- **The only state difference is STENCIL.** The workbench prepass enables `GPU_STENCIL_NEQUAL`
  (writeMask has the stencil bit 0x20); the outline has no stencil test. This is the discriminator
  r29-r32 never saw because they treated the combined depth-stencil texture as "the depth".

## ROOT CAUSE - the dynamic stencil reference was never emitted (compared against 0)

- WebGPU splits stencil state: the PIPELINE carries `stencilFront/Back` ops + `stencilReadMask`/
  `stencilWriteMask` (wgpu_pipeline.cc:244-249, correct); the REFERENCE is render-pass DYNAMIC
  state set by `renderPassEncoder.setStencilReference(ref)`. `grep SetStencilReference
  upstream/.../webgpu/` was EMPTY - the backend never called it, so the reference is always 0.
- The workbench opaque gbuffer prepass sets `state_stencil(write=OBJECT, reference=0xFF,
  compare=OBJECT_IN_FRONT)` (workbench_mesh_passes.cc:120-123) under `DRW_STATE_STENCIL_NEQUAL`;
  the DRW system records it via `GPU_stencil_reference_set(0xFF)` -> `mutable_state.stencil_reference`
  (draw_command.cc:354, gpu_state.cc:195). NEQUAL passes when `(ref & mask) != (buf & mask)`.
  - Correct (Vulkan/GL apply the reference): `(0xFF & 0x02)=0x02 != (0 & 0x02)=0` -> TRUE -> draw.
  - WebGPU bug (reference 0): `(0 & 0x02)=0 != 0` -> FALSE -> EVERY fragment rejected. The whole
    solid pass writes nothing. NO GPU error - a stencil test rejecting fragments is VALID behavior.
- The Vulkan oracle applies exactly this as dynamic state (vk_context.cc:342-349), guarded by
  `stencil_test != GPU_STENCIL_NONE`.

## ERROR-CHANNEL FINDING (proven, not assumed)

The JS `uncapturederror` listener on the imported WM-worker device (wgpu-preinit-worker.js:100)
routes to the page console as `[bw][GPU-ERROR]`. A `BW_RO_CANARY` probe (forced a valid read-only
depth-stencil attachment while the pipeline still writes depth) surfaced the invalid pass at BOTH
encoding AND submit: `GPUValidationError: [RenderPipeline] writes depth while [RenderPassEncoder]'s
depthReadOnly is true - While encoding ... SetPipeline` and `[Invalid CommandBuffer] ... While
calling [Queue].Submit`. So the channel is LIVE for the draw/submit class - r32's "0 GPU errors"
was GENUINE: there was never an error to swallow, because the stencil rejection is error-free.

## THE FIX (patch 0118) - honest to the pass-per-draw model, minimal

`WGPUContext::apply_stencil_reference(pass)` (wgpu_context.cc): when `state.stencil_test !=
GPU_STENCIL_NONE`, call `pass.SetStencilReference(mutable_state.stencil_reference)`. Called after
`SetPipeline` in every draw path: wgpu_batch draw / multi-viewport / multi_draw_indirect +
wgpu_immediate. No shader/codegen/pipeline change; mirrors vk_context.cc.

## VERIFY-DONT-TRUST (patch 0117 readback + composite)

- ATTACHMENT level (BW_DIAG + BW_DIAG_ARM=3, state (a) right after the prepass Submit, x3 identical):
  every previously-EMPTY gbuffer target now written - `prepass_material` nzByteFrac 0.0157,
  `prepass_normal` 0.0157, `prepass_objectid` 0.00785, `prepass_depth` writtenFrac 0.0157 min
  0.99941 (= the cube; matches r32's outline cube depth 0.99938). 0 GPU errors.
- COMPOSITE level: the SOLID SHADED CUBE composites in-tab with the full UI (topbar/toolbar/
  outliner/properties/timeline/nav gizmo/grid+axes/camera+light gizmos/selection outline).
  Evidence `platform_web/shell/evidence/m4-r33-solid-cube-shot.png` (+ m4-r33-fix-shot.png), CC0.
- Native census GREEN, unchanged: m3 148 PASS / 8 FAIL / 2 CRASH (158) + static_shaders 956/973;
  patches_series attests 0118 applied. windowed-opt AND gate trees relinked clean.
- PARITY (sandbox/m4-fullscreen-parity/compare_fullscreen.sh VERBATIM, 0.016/1, SELFTEST_PASS):
  1600x900 whole-window FAIL **11.4%** over (mean err 0.0087), DOWN from the **60.2%** baseline.
  Per-region: topbar 1.64 / toolbar 19.7 / viewport 12.4 / sidebar 8.93 / statusbar 10.7. The
  viewport region collapsed (was the dominant contributor); residuals are chrome/AA/interaction,
  NOT the cube.

## DO-NOT-RE-RUN (r33; plus r29/r30/r31/r32 lists which all stand)
1. depthReadOnly / stencilReadOnly derivation - both are ALWAYS 0 in begin_load_pass (the shared
   draw path never sets them). The r32-handoff "prime suspect" readOnly-vs-write poisoning is DEAD.
2. Error-channel doubt - PROVEN live for encoding AND submit (BW_RO_CANARY surfaced the invalid
   pass at both). r32's 0-errors is real; do not re-question whether submit drops are swallowed.
3. The depth-attachment / cross-submit-seam direction (r32's (a) dedicated depth + copy, (b)
   standalone Dawn repro, (c) intra-encoder fan-out) is MOOT - the cube was never a depth or
   cross-submit problem. It was the missing stencil reference. Do NOT build the dedicated-depth
   workaround or the standalone repro.

## Landing state (this round)
- [x] Solid shaded cube: FIXED (patch 0118). First solid workbench cube in a browser.
- [x] Root cause: missing dynamic stencil reference (SetStencilReference never called; ref 0 vs the
      workbench NEQUAL @ 0xFF). GPU-verified at the attachment + composite levels.
- [x] ALL `[bw-r33]` instrumentation + `BW_RO_CANARY` reverted; grep-clean across upstream/webgpu.
- [x] Patch 0118 round-trips (git apply --check forward on clean tree + --reverse on applied tree);
      series entry added with rationale.
- [x] Native census GREEN 148/158 + 956/973 (0118 applied); windowed-opt + gate trees relinked.
- [x] Parity 60.2% -> 11.4% failing at 1600x900 (thresholds unchanged, SELFTEST_PASS).
- [ ] OPTIONAL KEEPER deferred: r32's buffer-content readback primitive (template in
      notes/gpu-r32-buffer-content.md) NOT re-landed this round - the fix did not need it and it is
      its own tooling patch. Re-land as a BW_DIAG-gated sibling of 0117 in a dedicated round if the
      driver still wants it kept.
- Evidence: `sandbox/gpu-r33/{disc1,verify}.mjs` + `sandbox/gpu-r33/r33-*.analyses.json`;
  `platform_web/shell/evidence/m4-r33-{solid-cube,fix}-shot.png` (+ .license CC0).
