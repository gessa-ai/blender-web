<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I modal-extrude frame-coherence diagnosis — 2026-08-27

## Outcome

P0-I remains open pending Apple pixels. The first instrumentation pass rejected the filed
binding/shadow hypothesis and narrowed both hardware symptoms to temporal accumulation of
transient region draws. Patch 0295 now provides a testable runtime candidate: browser queue writes
and command-buffer submissions happen in their JavaScript calling turn, while error-scope results
remain asynchronous diagnostics. The fallback product is locally clean, but it binds no hardware
pixel claim, receipt, profile, APPLY bundle, or release tag.

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

Closure requires the driver to run modal extrude, move, rotate, and scale with active constraints on
the Apple rig and show thin guides with no retained trails; confirmed-operation HUDs must remain
correct for at least six idle seconds. Boot, idle paint, orbit, and the P0-E 10x resize/stress bars
must remain green on the same candidate. The fallback diagnostic binds only control flow and queue
facts, never pixels.
