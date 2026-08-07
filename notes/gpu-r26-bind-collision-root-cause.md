<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 26 (driver) — ROOT CAUSE FOUND + FIRST VIEWPORT GEOMETRY: stale-bind remap collisions

Continues notes/gpu-r25-shim-boot-restored-viewport-isolated.md. Rig throughout = the
r23 visible recipe (headed Playwright, bundled Chromium, kick-timer pyexpr forcing
VIEW_3D `region.tag_redraw()` per second). Every probe below ran on
`build-wasm-windowed` with TEMPORARY stderr instrumentation in the owned webgpu
backend (live diffs banked in the session scratchpad; the two REAL fixes are listed
at the end for the 0110/0111 patch landing).

## The elimination chain (what each probe killed)

1. **Draw map** (once-per-tuple logs in WGPUBatch::draw/multi_draw_indirect): EVERY
   frame draw SUBMITs — workbench prepass via DrawIndexedIndirect into Opaque.Gbuffer,
   resolve/TAA/SMAA/outline/grid/background, OCIO_Display into back_left. Zero
   early-outs. Kills "draws never reach the backend".
2. **Texture identity map** (attachment + sampled-texture logs): the full chain wires
   perfectly (Gbuffer → resolve tex 0x…550 → TAA → SMAA → back into 0x…550; overlays
   → 0x…6c8; OCIO samples exactly those two). Kills wiring/composite-routing bugs.
3. **Compute map**: draw_visibility_compute / draw_command_generate /
   draw_resource_finalize all SUBMIT with bind groups. CPU payload fingerprints:
   ViewMatrices REAL (rotation rows), ViewCullingData real, cube pos VBO PERFECT
   (24 verts of ±1 float3). Kills "no compute / empty uploads / broken extraction".
4. **Magenta loadOp discriminator on Opaque.Deferred**: magenta reached the CANVAS
   through TAA/SMAA/OCIO — downstream transport works; (workbench resolve DISCARDS
   empty-gbuffer pixels by design, so magenta surviving implicates the geometry
   prepass, not the fullscreen chain).
5. **Error-channel canary**: a deliberately invalid submit DID print
   `[bw][GPU-ERROR] GPUValidationError …` — the channel is LIVE, the silence around
   engine draws was real. (First canary attempt was the wrong kind of invalid:
   `mappedAtCreation` misalignment throws a synchronous RangeError, not an async
   validation error — use an oversized CopyBufferToBuffer for channel tests.)
   Also: `HasFeature(IndirectFirstInstance)=1` — kills the silent-no-op-indirect
   theory. Three contexts share ONE JS device (no cross-device split).
6. **Depth**: `depthCompare=Always` forced pipeline-wide → still nothing. Depth
   exonerated (and the draw manager clears depth via its own clear_fb submit_clear,
   which works).
7. **WGSL dump** (overlay_outline_prepass_mesh vertex): textbook — pos from
   @location(0), `res_id_buf[instance_index]` → `drw_matrix_buf[id]`, y-sign via
   override @id(1000), empty clip-distance fn. Kills codegen theories.

## THE ROOT CAUSE (bind-route logging, [bw-r26bind])

`WGPUShader::remap_*_binding(slot)` used `lookup_default(key, slot)` — **identity
pass-through for slots the shader's create-info does NOT declare**. The context
bind-spaces (bound_uniform_buffers_/bound_storage_buffers_/…) are CONTEXT-WIDE and
accumulate stale binds from every previously-drawn shader. A stale slot therefore
masqueraded as a valid dense binding and COLLIDED with the shader's legitimate
resource — observed live: `overlay_outline_prepass_mesh` got TWO SSBOs routed to
@binding(1) (a stale 16-BYTE buffer vs the real 16 KiB ObjectMatrices) and two to
@binding(2) (res_id_buf's slot). Duplicate-binding createBindGroup validation errors
were swallowed by create_bind_group_checked's ERROR SCOPE (why everything was
silent). Wrong-buffer reads (16 B "matrices" → WGSL OOB → zeros) degenerate every
DRW vertex; UI shaders have sparse bind spaces (no stale overlap) — exactly the
dead-DRW/alive-UI split observed since r18.

**FIX 1 (the unlock):** remap_* return -1 for undeclared slots; every builder loop
in wgpu_context.cc skips negatives (5 call sites: UBO, SSBO, buffer-SSBO, image,
sampled/sampler).

**FIX 2 (landed en route, real but secondary):** WGPUFrameBuffer::begin_load_pass
now honors the frontend's recorded per-attachment load-store actions with ONE-SHOT
consume (first pass after bind_loadstore clears with the recorded value, later
passes load; ctor defaults changed CLEAR→LOAD to preserve untouched-fb semantics —
a CLEAR default wiped once-drawn region buffers like the status bar).

## RESULT (r26r boot, evidence m4-r26-first-viewport-geometry-1280x720.png)

**First real 3D viewport geometry ever in a browser tab**: camera wireframe, light
gizmo + ground line, and the cube's orange selection outline all composite live.
Remaining wrongness for r27: (a) outline geometry DEFORMED (vertex displacement —
suspect matrix-buffer stride/indexing or the 10_10_10 normal/format conversion
family); (b) workbench SOLID cube pass still absent; (c) grid still absent;
(d) the new native shell (2294a89) renders full-window — gate captures must use
`?gate=1280x720` from now on.

## Landing checklist (r26 close, driver)

- Revert ALL [bw-r26*] temporary instrumentation (batch/context/backend/shader/
  uniform/storage/vertex-buffer/pipeline discriminators + canary); keep ONLY the
  two fixes above.
- Patches 0110 (remap -1 + builder skips) and 0111 (load-store honor) with
  reverse-apply verification + series update + lane-a mirror sync.
- Native census MUST re-run (the fixes are NOT __EMSCRIPTEN__-guarded — they are
  semantically correct for native Dawn too, but harness/run.sh --scope m3 must
  confirm 148/158 + static 956/973 before landing).
- Then the r27 residual hunt (deformed vertices / solid pass / grid) and the gate
  re-measure via ?gate=1280x720.

## r27a addendum (clean fixes-only rebuild, diagnostics reverted)

Geometry identical to r26r (camera + light + deformed cube outline) on the clean
build — the two fixes stand alone. AND the collisions' removal made the REAL
residual errors loud (error channel now actually reporting): per kick-driven boot,
**767× "Number of entries (3) did not match the expected number (4)" on a
BindGroupLayout** (a shader's declared resource the frontend never routes a bind
for — previously masked by a stale bind accidentally filling the hole; its draws
now drop with 775× invalid-BindGroup/CommandBuffer cascades — prime suspect family
for the missing solid pass/grid) and **8× "Filtering sampler is incompatible with
non-filtering sampler binding"** (explicit-BGL sampler-type mismatch). r27's first
instrumented boot should log, at create_bind_group_checked mismatch time, the
shader name + which interface-map bindings lack entries.
