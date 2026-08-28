<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I modal-extrude frame-coherence diagnosis — 2026-08-27

## Outcome

P0-I remains open pending Apple pixels. The first instrumentation pass rejected the filed
binding/shadow hypothesis and narrowed both hardware symptoms to temporal accumulation of
transient region draws. Patch 0295 provides the first runtime candidate: browser queue writes and
command-buffer submissions happen in their JavaScript calling turn, while error-scope results
remain asynchronous diagnostics. Patch 0296 adds the independently observed missing-compute-draw
candidate: exact buffer binding intent survives asynchronous allocation, and only successful
publication emits one bounded redraw-readiness edge. Patch 0297 closes the same intent-loss window
in typed vertex and index buffers after an exact cumulative-interaction run identified polyline
bindings 0, 1, and 2 as missing. The fallback diagnostics complete with no page error or hard
incomplete-group warning, but they bind no hardware pixel claim, receipt, profile, APPLY bundle,
or release tag. A separately reproduced cumulative workspace-click failure remains open.

The driver-operated Apple M4 Pro remains the pixel authority. Its accepted v0.1.1 candidate
(`.wasm.orig` SHA-256 prefix `505702dbf41c`) shows multiple constraint-guide trails during modal
extrusion and overlapping HUD-sized grey bars after confirmation. The last two settled PNGs
are byte-identical, so this is persistent content, not capture noise.

## What the live trace falsified

The diagnostic runs the real `Tab -> E -> mouse move -> click` sequence and independently attests
`OBJECT/8 -> EDIT/8 -> OBJECT/16`; the click genuinely confirmed an extrusion. It then exercises
and cancels constrained move, rotate, and scale. On the current fallback product it captured 35
six-vertex constraint-line submissions: 15 extrusion, 12 move, four rotate, and four scale:

- every render attachment and viewport is the live 1048x621 `VIEW_3D` region;
- every push UBO carries viewport 1048x621 and line width 2;
- all 35 immediate vertex resources are distinct;
- the shader cache reports HIT and no bind-group completeness warning or page error occurs;
- no `widget-shadow` pass occurs during extrusion (one appears later during constrained move).

Thus the white spindles are not P0-G's undefined widget-shadow RGB, a stale extent, or a huge line
width. Keeping the original P0-G call-site audit open is still honest, but patching the shadow
shader again cannot repair this modal symptom.

The same trace records five extrusion redraw clusters but zero surface-copy submissions in that
phase. After confirmation, at least 160 widget-base passes and 73 region-image composites drain
before the captured settle-phase surface copy. The final image composites precede that copy in
actual queue-submit order. That last fact also rejects the first, overly broad diagnosis that the
surface submit simply overtakes all window composites in this run. Once this first-use backlog has
drained, constrained move, rotate, and scale reach later surface copies (10, 10, and 13 captured
respectively), narrowing the defect from all modal frames to the first-use/pending window.

## Rejected frame-barrier attempt

The first candidate extended resize's completed-frame admission barrier to every ordinary frame.
The exact fallback modal capture disproved that shape: only two surface traces appeared across the
run, intermediate frames were white/black, and the retained spindle remained. A follow-up recovery
variant deterministically closed the browser twice. Both variants were removed before patch 0295;
no ordinary-frame queue or asynchronous GHOST present seam remains in the product.

## Same-turn queue candidate

The actual temporal gap is below GHOST. `command_encode_submit_scoped()` encoded immediately but
deferred `Queue::Submit` until browser `PopErrorScope` completion and the ordered scheduler; direct
buffer and texture writes used the same asynchronous admission. WM could therefore synchronously
copy the persistent backbuffer before ordinary draw submissions and their uniform uploads had even
entered the WebGPU queue. Patch 0295 keeps native Dawn's validation-ordered scheduler unchanged, but
on Emscripten it issues `Submit`, `WriteBuffer`, and `WriteTexture` synchronously in program order.
Nested error scopes still settle later and report the exact combined validity result. GHOST retains
its synchronous surface acquire/encode/submit boundary, and patch 0288 / `2c887da` remains absent.

The fail-first Wasm behavior fixture observed zero submits before scope settlement. The candidate
observes each handle-valid submit immediately, keeps later browser queue calls unstalled, and still
reports the delayed encode/submit validation result. The six-source contract rejects 12 mutations;
native/Wasm integration is green and canonical replay matches the 20,258-entry frozen source.

The exact fallback modal run now reports 152 constraint submissions, ten extrusion redraw clusters,
and surface copies during every modal phase: extrusion 2, move 2, rotate 3, scale 2 (26 total in the
bounded trace). The mid-extrude guide is visually thin, toolbar icons are intact, and the 0.5, 3,
and 6-second settled screenshots are byte-identical SHA-256
`dc325d92a328b18e36c0de5e1227a95e9849deef25faf37eef68d63f3b492a29` with no retained grey bar.
There are zero page errors, queue rejections, or completeness warnings. This is strong diagnostic
evidence for the candidate, not hardware closure.

## Receipt-wide completeness census

The backend diagnostic added by patch 0281 was already shader-agnostic: every failed
`bind_group_entries_complete()` call printed the shader plus sorted `surviving`, `assembled`,
`missing`, and `extra` sets. The sanctioned profile capture narrowed that generic signal back to an
allowlist of only `overlay_grid_next`, `overlay_outline_detect`,
`overlay_antialiasing_pipeline`, and `OCIO_Display`. Consequently, an arbitrary later shader could
drop a draw while both hardware receipts still passed.

That was not hypothetical. The accepted Apple success-r2 console contains 18 warnings that the old
capture ignored: one `draw_resource_finalize`, nine `draw_visibility_compute`, and eight
`draw_command_generate`. All three signatures are missing binding 1 with no extra binding. These
compute shaders are relevant to the later missing-mesh symptom, but the log alone does not prove
that they caused P0-I and this iteration does not repair their resource assembly.

Commit `3056f7c` removes the shader-name allowlist. Both capture scenarios now collect every unique
incomplete-group signature, preserve all four exact binding sets plus a duplicate count and the
first raw line, retain malformed matching diagnostics fail-closed, and require the resulting
`incompleteBindGroups` array to be empty. The producer self-check covers the three real Apple names,
arbitrary future names, duplicated signatures, and malformed diagnostics. Under this strengthened
contract the old success-r2 run would correctly fail; fresh current-generation Apple receipts must
report an empty census before APPLY or release promotion.

## Pending buffer binding intent

The three Apple signatures share a narrower state than an arbitrary missing resource. In the
accepted success-r2 timeline, `draw_resource_finalize`, `draw_visibility_compute`, and
`draw_command_generate` all miss dense binding 1 during one roughly 26 ms interaction window.
Their draw-manager call sites bind lazily allocated bounds/visibility storage buffers immediately
before dispatch. `WGPUStorageBuffer::bind()` previously called `ensure()` and returned before
recording the frontend slot whenever browser allocation validation was still pending. Uniform
buffer bind and storage-rebind had the same ordering. Consequently, resource assembly could not
distinguish a bound-but-pending resource from a buffer that Blender never bound at all, and the
strict completeness gate emitted the hard warning and abandoned the dispatch.

Patch 0296 preserves the frontend slot while `Buffer::create_scoped()` is pending. Resource
assembly carries pending dense IDs separately from live `BindGroupEntry` objects, prevents an
identity-fallback resource from stealing that mapped slot, and classifies the result with three
fail-closed states:

- `Complete` still requires the exact live surviving set;
- `Pending` requires every missing ID to be owned by an exact pending binding, with no undeclared
  live or pending ID;
- `Incomplete` retains the existing shader/set diagnostic for every unaccounted missing or extra
  ID.

A pending result records the dropped draw but does not enter the hard receipt census. Crucially,
it also does not publish readiness on every retry: that would let a permanently pending allocation
re-arm the 180-tick ceiling indefinitely. The persistent buffer's successful publication callback
emits exactly one readiness generation, which re-tags the window only after the real handle is
available; rejection emits none. Native and Wasm fixtures prove pending slot retention, rejected
publication, accepted publication, one readiness edge, exact/missing/extra classification, and
native/Wasm parity. This repairs the observed resource-state distinction without weakening the
all-shader receipt gate.

## Typed geometry binding intent and cumulative interaction

The filed production battery mixed navigation, workspace hit testing, and pixels, so the new
diagnostic first binds every screenshot to Blender-native state. It records the active workspace,
screen areas, mode and topology, live `VIEW_3D` rectangle, view transform, and the projected Cube
position. It also proves that the exact Modeling-tab coordinate is accepted before navigation,
then runs ten orbits, ten Shift-pans, ten wheel zooms, and all nine filed tab coordinates. A stock
Frame Selected operation distinguishes a legitimately distant Cube from a missing geometry draw.
Raw PNG byte size is never used as the visual verdict.

On the pre-candidate product the scene remained alive and the Cube remained projected inside the
view, but the all-shader census emitted six identical hard failures:

```text
WGPUShader 'gpu_shader_3D_polyline_flat_color': assembled group-0 resources do not match
surviving WGSL bindings surviving=[0,1,2,3] assembled=[3] missing=[0,1,2] extra=[]
```

Binding 3 is the already-live push constant. Bindings 0, 1, and 2 are the polyline position,
color, and index storage resources; a single `WGPUVertexBuffer` can supply the first two and the
`WGPUIndexBuffer` supplies the third. Both typed `bind_as_ssbo()` frontends uploaded on first use
and then returned whenever the WebGPU handle was not yet valid. In the browser, that includes the
ordinary allocation-validation pending window, so the frontend never recorded the bindings and
resource assembly could only see binding 3. This exactly repeats the intent-loss ordering class
that patch 0296 repaired for storage/uniform buffers.

Patch 0297 changes only that predicate: a valid or `creation_pending_or_retryable()` buffer records
its exact SSBO slot. Existing assembly then classifies the exact pending IDs as `Pending`, keeps
genuine unbound/extra resources as hard `Incomplete`, and retries after publication. The strict
set-completeness gate is unchanged.

After relinking, the final 21-step run records 74 Blender-native state changes, 121 presents,
zero hard completeness warnings, zero page/lifecycle errors, a Cube projected inside every
required `VIEW_3D` sample, byte-identical Frame Selected pixels at three and six seconds, and a
pixel-changing final orbit. Visual inspection shows intact text, toolbar icons, grid, gizmo, and
shaded Cube. The preflight Modeling click is accepted, but none of the eight later state-changing
workspace clicks is accepted while Blender stays in Layout; the already-active Layout click is not
counted as a transition. That is direct evidence for separate P0-J cumulative input/modal-state
failure; patch 0297 neither claims nor receives credit for fixing it.

## Evidence and acceptance

- Apple screenshots: `~/bw-logs/mac-capture-evidence-20260827-extrude-artifact/`.
- Successful four-operator real-product fallback trace:
  `ledger/buildlogs/20260827T202538-2419572.log`.
- Final diagnostic syntax, analyzer self-check, and trace analysis:
  `ledger/buildlogs/20260827T202832-2421504.log`,
  `ledger/buildlogs/20260827T202832-2421479.log`, and
  `ledger/buildlogs/20260827T202832-2421495.log`.
- One diagnostic-browser close during capture, followed by the successful unchanged retry:
  `ledger/buildlogs/20260827T202523-2419125.log`.
- Patch 0295 Wasm fail-first and final behavior:
  `ledger/buildlogs/20260827T215503-2489496.log` and
  `ledger/buildlogs/20260827T222509-2508205.log`.
- Final native/Wasm integration and canonical freeze:
  `ledger/buildlogs/20260827T222555-2511296.log` and
  `ledger/buildlogs/20260827T222431-2507573.log`.
- Relinked fallback modal capture and analysis:
  `ledger/buildlogs/20260827T222614-2512605.log`,
  `ledger/buildlogs/20260827T222751-2514148.log`, and
  `ledger/buildlogs/20260827T222825-2514577.log`.
- Committed-state relink reproduced all five tested artifact hashes byte-for-byte, followed by
  locked no-work: `ledger/buildlogs/20260827T224438-2524458.log` and
  `ledger/buildlogs/20260827T224636-2525105.log`.
- Capture allowlist fail-first, pinned producer self-check, and two-phase source verification:
  `ledger/buildlogs/20260827T225613-2531382.log`,
  `ledger/buildlogs/20260827T225833-2532789.log`, and
  `ledger/buildlogs/20260827T225836-2532827.log`.
- Pending-binding fail-first, final focused buffer parity, and full pipeline parity:
  `ledger/buildlogs/20260827T231350-2544092.log`,
  `ledger/buildlogs/20260827T233739-2566105.log`, and
  `ledger/buildlogs/20260827T233625-2563882.log`.
- Final canonical replay and capture-profile self-check:
  `ledger/buildlogs/20260827T233612-2563747.log` and
  `ledger/buildlogs/20260827T233158-2560718.log`.
- Final CAPTURE relink, unchanged pinned-Node modal rerun/analysis, and committed-state no-work:
  `ledger/buildlogs/20260827T233803-2567595.log`,
  `ledger/buildlogs/20260827T233933-2568490.log`,
  `ledger/buildlogs/20260827T234005-2568972.log`, and
  `ledger/buildlogs/20260827T234211-2570387.log`.
- Cumulative interaction fail-first run with six exact polyline failures, source fail-first, and
  final source mutation checks:
  `ledger/buildlogs/20260828T000504-2587117.log`,
  `ledger/buildlogs/20260828T001114-2591748.log`,
  `ledger/buildlogs/20260828T001858-2595679.log`, and
  `ledger/buildlogs/20260828T001858-2595686.log`.
- Patch-0297 affected-object build, CAPTURE relink/no-work, final cumulative browser run, analyzer,
  and analyzer self-check:
  `ledger/buildlogs/20260828T001204-2592052.log`,
  `ledger/buildlogs/20260828T001215-2592117.log`,
  `ledger/buildlogs/20260828T001323-2592576.log`,
  `ledger/buildlogs/20260828T002703-2604404.log`,
  `ledger/buildlogs/20260828T002908-2605812.log`, and
  `ledger/buildlogs/20260828T002908-2605813.log`.
- Fresh canonical freeze/replay and focused buffer plus full pipeline parity:
  `ledger/buildlogs/20260828T002036-2597024.log`,
  `ledger/buildlogs/20260828T002119-2597501.log`, and
  `ledger/buildlogs/20260828T002131-2598038.log`.

The patch-0296 CAPTURE generation is bound by JS SHA-256 `763dba372ec3`, split Wasm
`67554d3a4871`, `.wasm.orig` `518dcdffa7cc` (118,976,355 bytes), data
`095d0ba748c3`, and split manifest `b6f4b5ff558c`.

The patch-0297 CAPTURE generation retains JS/data identities and is bound by JS SHA-256
`763dba372ec3`, split Wasm `e834745977a5`, `.wasm.orig` `8ff3a2d87544`, data
`095d0ba748c3`, and split manifest `b6b4f8a0337f`.

Closure requires the driver to run modal extrude, move, rotate, and scale with active constraints on
the Apple rig and show thin guides with no retained trails; confirmed-operation HUDs must remain
correct for at least six idle seconds. Boot, idle paint, orbit, and the P0-E 10x resize/stress bars
must remain green on the same candidate. The fallback diagnostic binds only control flow and queue
facts, never pixels.
