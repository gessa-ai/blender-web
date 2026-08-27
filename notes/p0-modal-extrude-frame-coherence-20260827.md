<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I modal-extrude frame-coherence diagnosis — 2026-08-27

## Outcome

P0-I remains open, but the first instrumentation pass rejects the filed binding/shadow hypothesis
and narrows both hardware symptoms to temporal accumulation of transient region draws. No runtime
fix, product relink, pixel claim, receipt, profile, APPLY bundle, or release tag is made here.

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

## Remaining root boundary

Ordinary modal frames have no equivalent of the resize path's completed-frame admission barrier.
Each WebGPU draw is encoded immediately but its actual queue mutation is serialized through browser
error-scope completion. Meanwhile Blender continues producing logical WM redraws into persistent
offscreen region/window attachments. Several temporal versions of the first-use constraint guide or
HUD can therefore drain into the same persistent target before one coherent frame is admitted to
the surface. The Apple screenshots are the visual form of that accumulation: moving line trails
during the modal operator and overlapping HUD backgrounds after it. Later modal operations
presenting normally after the drain argue against a permanently broken shader or transform path.

This is a guarded diagnosis, not hardware closure. The next runtime candidate should preserve one
completed ordinary dirty frame until its synchronous GHOST surface copy has been submitted, using
the already hardware-proven resize barrier pattern or an equivalent frame-scoped transaction. It
must not restore patch 0288 / commit `2c887da`: that design invoked `presentBackbuffer()` from an
asynchronous backend callback and its relink hard-aborted 10/10 Apple boots in `BLI_strdupn`.
Surface acquire, encode, and submit must stay inside GHOST's synchronous swap boundary.

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

Closure requires the driver to run modal extrude, move, rotate, and scale with active constraints on
the Apple rig and show thin guides with no retained trails; confirmed-operation HUDs must remain
correct for at least six idle seconds. Boot, idle paint, orbit, and the P0-E 10x resize/stress bars
must remain green on the same candidate. The fallback diagnostic binds only control flow and queue
facts, never pixels.
