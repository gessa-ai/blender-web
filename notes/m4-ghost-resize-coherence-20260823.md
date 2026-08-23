<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST resize coherence — 2026-08-23

## Outcome

Implementation commit `a52f311` closes audit R6's browser-resize coherence finding. The latest
canvas request is now distinct from the last complete configured surface/backbuffer extent. A
validated current backbuffer candidate configures and publishes the complete size-bound state;
rejected and superseded candidates cannot replace any part of the old state. Presentation requires
the authoritative, backbuffer, and acquired-surface extents to match exactly, and a rejected resize
retries from the next present tick without waiting for another browser resize event.

## Diagnosis and implementation

`configureSurface()` previously published `width_`/`height_`, called `Surface::Configure`, and set
`configured_` before the asynchronously scoped backbuffer candidate was accepted. A literal-null or
non-null error texture preserved the old backbuffer and its extent only, leaving a new surface and
authoritative extent paired with stale source dimensions. The fullscreen present shader could then
issue `textureLoad` outside the old allocation.

The shipping transaction helper now owns three explicit decisions: whether a requested extent needs
a candidate, whether an accepted candidate is current enough to commit, and whether an acquired
surface is coherent enough to present. `configureSurface()` records only the latest requested
extent. The accepted callback synchronously configures the surface and publishes the backbuffer plus
all authoritative dimensions as one worker-local commit. A newer request discards the stale
candidate and starts the latest one immediately; a rejected candidate remains requested and is
retried by `presentBackbuffer()` on a later frame. The old complete extent remains presentable while
the replacement is pending.

## Evidence

- The unchanged compositor fails the new source-bound contract before compilation or evidence
  allocation at its missing requested-extent field (`20260823T150914-2965615`). Ambient Node
  v25.1.0 is independently rejected before its requested evidence directory exists
  (`20260823T151522-2972763`).
- Final root and descendant-CWD runs pass 31 byte-identical native/wasm32 integrated contracts at
  3,602 bytes, SHA-256 `fba4542839dc`, with shipping inputs SHA-256 `dda5bb6c91ae`
  (`20260823T151837-2977541`, `20260823T151858-2978771`). The 17 resize cases cover settled and
  pending candidate decisions, literal-null and non-null-error preservation, no-event retry,
  old-state presentation, stale-candidate supersession, atomic current commit, and six exact
  present-coherence decisions.
- The pinned-Dawn llvmpipe control rebuilds and passes two exact resize cases: a real non-null
  texture error object preserves the old complete state, then a clean retry commits all extents
  together (`20260823T151333-2971069`, `20260823T151344-2971156`). Its verdict remains explicitly
  `SOFTWARE_CONTROL_NON_RECEIPT` and binds no hardware or browser result.
- Canonical clean-pin replay remains green with 257 paths and canonical SHA-256 `dff11e4bc854`
  (`20260823T151545-2974501`). The real `blender_browser` rebuild and locked no-work check are green
  (`20260823T151105-2969174`, `20260823T151148-2969596`). OFF preflight binds the 118,700,623-byte
  primary Wasm and 167,143,248-byte data payload (`20260823T151551-2974599`).
- Required M4 remains red at the unchanged unsupported browser binding. The Docker-backed regression
  at `2026-08-23T15:17:09Z` restores M0 to 6/6 green while M1-M8 retain their existing strict
  receipt, split-product, browser, run-label, hardware, and release boundaries.
- Final REUSE 6.2.0 compliance is green for 2,216/2,216 files
  (`20260823T152137-2981464`).

## Boundary

This is device-free state-machine, source, compile, and link proof. It creates no accepted WebGPU
adapter/device, surface, present, pixel, browser, profile, split-product, or milestone receipt. No
result promotion, dependency decision, deferral, tolerance, golden, blacklist, or promise changed.
The live boundary remains deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry dzn or the staged
post-reboot Windows path. Surface-creation/configuration failure propagation remains the next
independent audit item.
