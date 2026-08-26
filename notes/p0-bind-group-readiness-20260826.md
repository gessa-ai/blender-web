<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-D WebGPU bind-group readiness — 2026-08-26

## Outcome

Patch 0281 implements a hardware-validation candidate for the blank 3D viewport without relaxing
the exact surviving-WGSL bind-group completeness rule. It improves the failure warning, starts the
backend push-constant allocation before shader-module/layout validation, and lets a pending shared
sampler be used only behind a queue dependency in every frame epoch that observes it. Rejection
cancels every such epoch; acceptance publishes the sampler normally.

This item is not closed. The required semantic-pixel verification on the Apple M4 Pro hardware rig
is external to WSL, and `overlay_grid_next` must be measured there because the software fallback
run never reached its draw. P0-E resize coherence is a separate open launch blocker.

## Diagnostic before the fix

The first relink added sorted `surviving`, `assembled`, `missing`, and `extra` sets while preserving
the hard failure. The real windowed fallback run selected the missing-resource branch, not the
extra-resource branch:

- `overlay_antialiasing_pipeline`: surviving `[0,1,2,3,4,256,257,258]`, assembled
  `[0,1,2,3]`, missing `[4,256,257,258]`, extra `[]`.
- `overlay_outline_detect`: surviving `[0,1,2,4,5,256,257,258]`, assembled `[0,1,2,4]`,
  missing `[5,256,257,258]`, extra `[]`.
- `OCIO_Display`: surviving `[0,1,2,3,256,257]`, assembled `[0,1,2,256,257]`, missing `[3]`,
  extra `[]`.

The low dense IDs are the backend-injected push-constant uniform buffer. The `256+` IDs are Tint's
split sampler halves. After eager push-buffer creation, the low IDs were present and only the split
samplers remained missing, proving the two readiness defects independently. A same-epoch-only
provisional sampler was insufficient: several UI draws reused one context-wide sampler after
`begin_frame()` had advanced the queue epoch but before the browser scope callback could run.

`overlay_grid_next` emitted no completeness call in this box's fallback run. The fallback canvas
remained black even after the named completeness warnings reached zero, so neither a fabricated
set nor those software pixels are used as evidence for that shader.

## Fix and failure boundary

- `WGPUShader::finalize()` builds the interface and begins persistent push-constant buffer
  validation before module and explicit-layout validation. The later pipeline retry cannot become
  drawable before that earlier resource scope has had the opportunity to publish.
- `ScopedHandleCache::get_or_create_ordered()` retains one provisional candidate and one shared
  validation result. Each scheduler epoch that receives the candidate reserves exactly one
  dependency. A rejected error object fails all observing epochs and leaves a clean retry; an
  accepted handle becomes an ordinary cache hit.
- `WGPUContext::get_sampler()` uses that ordered cache. The exact expected/assembled equality test
  remains unchanged, and a genuinely absent surviving resource still drops the draw with complete
  set diagnostics.

## Regression evidence

- Fail-first live diagnostics: `20260826T031625-250430` and
  `20260826T034429-273270`.
- Native and wasm32 ordered-cache parity, including cross-epoch acceptance, multi-epoch rejection,
  cancellation, and retry: `20260826T040039-289570`.
- Canonical source freeze/replay: `20260826T035935-287048`; patch SHA-256 begins
  `08d656e99ee4`.
- Final locked product relink: `20260826T040053-290878`.
- Final headed fallback diagnostic: `20260826T040135-291238` reaches running `WM_main`, advances
  the exported uncapped tick/present counters across trusted input, and reports zero incomplete
  bind groups for `overlay_grid_next`, `overlay_outline_detect`,
  `overlay_antialiasing_pipeline`, and `OCIO_Display`, with zero present rejection or device loss.
  This is diagnostic-nonreceipt evidence only.
- The strict hardware split-profile producer now records and rejects any matching incomplete
  warning before it can emit a PASS receipt; its current/legacy adapter guard remains strict.

The `presentBackbuffer` console line is deliberately not cited as liveness evidence: that message
is capped at two lines. The live diagnostic uses `_bw_present_count`, which is an uncapped exported
counter. Final P0-D acceptance still requires the driver to capture semantic viewport pixels and
pixel deltas on conformant hardware, including a real `overlay_grid_next` draw and `OCIO_Display`.
