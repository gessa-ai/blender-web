<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-D bounded WebGPU redraw recovery — 2026-08-26

## Outcome

Commit `c2b6182` and patch 0283 remove the hardware-falsified assumption that two submitted
frames mean every Blender region has drawn. Browser Dawn can accept a shader module, explicit
layout, compute pipeline, or render pipeline after the first draw that requested it has already
returned. Each accepted publication now advances one atomic readiness generation. GHOST-web
consumes that generation as an ordinary `GHOST_kEventWindowUpdate`, whose existing Emscripten WM
handler invalidates the screen without manufacturing focus or pointer input.

The recovery source remains bounded. A new window receives the existing 180-tick boot episode,
with one periodic update every 12 ticks so visible lazy variants are discovered. Accepted async
readiness requests an immediate update and may rearm a completed episode. An incomplete bind-group
draw has a separate drop generation: it requests an immediate retry only while an episode is
active, is acknowledged at the ceiling, and cannot rearm that ceiling. Failed async publications
also cannot rearm. This distinction prevents a persistent validation failure from becoming a
per-frame-forever redraw loop while allowing a genuinely accepted later variant to recover an idle
region.

This complements patch 0281 rather than weakening its exact bind-group gate. The sorted
surviving/assembled/missing/extra diagnostic remains intact, and a missing live resource still
drops the draw. Patch 0283 makes that drop visible to bounded recovery and publishes only accepted
module/layout/pipeline settlements.

## Device-free and local evidence

- Fail-first compile: `20260826T045607-341088` failed only because the recovery generation API did
  not exist.
- Final behavior: `20260826T052115-368220` passes 15 native cases, including 15 periodic boot
  requests, immediate accepted readiness, immediate active-episode drop retry, repeated-drop hard
  bounding, accepted-readiness rearming, and counter wrap.
- Source contract: `20260826T052111-368191` rejects 29 mutations across the GHOST state/system/WM
  seam and both WebGPU shader/pipeline cache sources.
- Integrated native/wasm32 matrix and series replay: `20260826T052230-368983` is green. Canonical
  freeze `20260826T052155-368526` replays 20,258 source entries byte-exactly; the snapshot is
  2,351,520 bytes at SHA-256
  `1a648740d397d3a3873b4efcc530a6044d2af0e85b70651bdb7867f0d28dd4d4`.
- Locked CAPTURE relink/no-work: `20260826T052332-370951` and
  `20260826T052436-372365`. Inventory preflight, producer self-check (`positive=21`,
  `negative=23`, zero browser launches), and the two-phase source contract are green at
  `20260826T052444-372433`, `20260826T052444-372434`, and
  `20260826T052444-372438`.
- Exact-artifact fallback diagnostic `20260826T052500-372577` reaches running `WM_main`, advances
  uncapped ticks and a presentation after trusted input, and reports zero target-shader incomplete
  bindings, submit/transaction rejection, or device loss. It is explicitly
  `diagnostic-nonreceipt`; it proves neither semantic pixels nor P0-D closure.
- Pinned REUSE 6.2.0 covers the complete checkout at `20260826T052849-376040`.

The current hash-bound CAPTURE input is `blender_browser.wasm.orig` at 119,142,827 bytes and
SHA-256 `b0ecf56ee5dcfaf3e3ad46f93b9a533a60130d3a2828dfb08ca4336eacddc3e0`.
No software profile or receipt was produced.

## Remaining pixel acceptance

P0-D is still pending the driver-operated Apple M4 Pro run. Boot to idle without input must show
and retain the grid, shaded Cube, world axes, camera wireframe, selection outline, and labelled
navigation gizmo; Outliner and Properties must not remain stale. A middle-drag orbit must produce
a semantic pixel delta. The run must also capture the real `overlay_grid_next` diagnostic set and
retain complete `OCIO_Display`, with no region depending on an external redraw gesture to recover.

The required M4 gate therefore remains RED (`20260826T052535-373119`), and the full regression
retains the existing receipt/APPLY/browser/run-label/release boundaries
(`20260826T052539-373187`). Container-backed M0 is restored to 6/6 GREEN at
`20260826T052543-373430`.
