<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J selection draw admission — 2026-08-29

## Outcome

Patch `0307-gpu-webgpu-select-draw-admission.patch` closes the remaining synchronous false-empty
selection window in direct and indirect WebGPU batch draws. The CAPTURE product is relinked and
passes the exact slow/sparse software diagnostic. P0-I/J remain open until the unchanged 10/10
Apple-hardware pixel run and same-generation composed resize gauntlet pass.

## Gap

Patch 0306 invalidated a selection readback when a shader module or render pipeline was still
pending. A batch could still pass those named gates and return later while resolving vertex/index
buffers, assembling bindings, opening the load transaction, or creating a render pass. Select-next
would then see an unchanged draw-drop generation and could interpret its untouched
`0xffffffff`-cleared buffer as a genuine empty selection.

## Fix

- A browser-only `SelectionDrawAdmission` guard arms only while `G_FLAG_PICKSEL` is active.
- Both direct and indirect batch paths construct it before the first module gate, retain it across
  every later synchronous return, and disarm it only after an actual `Draw*` or `DrawIndirect*`
  command has been encoded.
- An armed guard invalidates the selection attempt through the existing draw-drop generation and
  emits one bounded shader/stage diagnostic. Native builds and ordinary browser draws do not enter
  the guard.
- The source/model verifier covers module, geometry, pipeline, vertex, binding, and render-pass
  exits; successful encoded and ordinary draws remain admitted. Nine independent source mutations
  fail closed.

## Evidence

- admission and adjacent retry mutation contracts:
  `ledger/buildlogs/20260829T082441-3965067.log`,
  `ledger/buildlogs/20260829T082441-3965076.log`
- canonical one-root freeze, receipt replay, and replay self-check:
  `ledger/buildlogs/20260829T082412-3964621.log`,
  `ledger/buildlogs/20260829T082441-3965059.log`,
  `ledger/buildlogs/20260829T082441-3965060.log`
- integrated native/wasm32 GPU suite:
  `ledger/buildlogs/20260829T082448-3965198.log`
- locked relink and immediate no-work check:
  `ledger/buildlogs/20260829T082534-3967652.log`,
  `ledger/buildlogs/20260829T082641-3968161.log`
- CAPTURE inventory preflight, stream-continuation self-check, and hardware-gauntlet self-check:
  `ledger/buildlogs/20260829T082722-3968500.log`,
  `ledger/buildlogs/20260829T082722-3968501.log`,
  `ledger/buildlogs/20260829T082722-3968504.log`
- exact SwiftShader slow/sparse diagnostic: first orbit 317 ms, projected Cube selection 12,165 ms,
  recovery orbit 1,878 ms, selected count one, balanced GHOST/WM input, zero page/lifecycle/
  selection-readback errors; bounded selection-draw census reports the expected first-use module
  and pipeline exits:
  `ledger/buildlogs/20260829T082726-3968550.log`
- REUSE 6.2.0:
  `ledger/buildlogs/20260829T082851-3970119.log`
- direct M4 remains Apple-receipt RED; pinned-container regression restores M0 6/6 and retains the
  existing strict/APPLY/public-product boundaries for later scopes:
  `ledger/buildlogs/20260829T082922-3970307.log`,
  `ledger/buildlogs/20260829T082943-3970733.log`

The software adapter evidence is diagnostic only. No hardware receipt, profile, APPLY product,
public bundle, tag, result promotion, tolerance, golden, blacklist, deferral, or launch claim was
created or weakened.

## Exact-generation software stability rerun

The relinked `a42be64bbc1c` CAPTURE generation completed 10/10 fresh slow/sparse software runs.
Five completed under WSLg and five under fresh isolated Xvfb; four additional WSLg attempts closed
the target page/context externally with zero page errors and bind no verdict. Every completed run
retired the first isolated orbit, selected exactly Cube through Blender's live projected viewport
coordinate, and retired the separately admitted recovery orbit. Action drain was 317-434 ms,
selection drain was 10,918-12,657 ms, and recovery was 732-2,181 ms. All ten had zero page,
lifecycle, or selection-readback errors and reported the complete native selection/action/recovery
state contract.

Completed-run logs:
`20260829T083709-3977510`, `20260829T083853-3979062`, `20260829T083958-3980135`,
`20260829T084107-3981104`, `20260829T084149-3982128`, `20260829T084324-3983267`,
`20260829T084409-3984525`, `20260829T084451-3985052`, `20260829T084532-3985513`, and
`20260829T084614-3986672`. The admission, adjacent retry, and producer mutation contracts remain
green (`20260829T084741-3987451/3987452/3987456`), as does pinned REUSE 6.2.0
(`20260829T084941-3989787`). Direct M4 remains honestly red at the Apple pixel boundary
(`20260829T084800-3987655`); the authoritative pinned-container regression restores M0 6/6 and
retains every later strict/APPLY/product boundary (`20260829T084826-3988076`).

This rerun changed no runtime source or product byte and does not replace the mandatory Apple
10/10 pixel series or same-generation composed P0-E gauntlet.

## Candidate identity and closure bar

- `blender_browser.js`: `90f60eb449c1`
- `blender_browser.wasm`: `7fd5d902a229`
- `blender_browser.wasm.orig`: `a42be64bbc1c` (118,997,196 bytes)
- `blender_browser.data`: `095d0ba748c3`
- `blender_browser.split-build.json`: `4a1910650f2c`

The driver must bind the exact product inventory above to 10/10 clean slow/sparse Apple runs with
real Cube selection, two independently changed orbits, zero visible artifacts, and zero selection
report/page error. The same generation must then pass the composed P0-E interaction gauntlet.
