<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# ADR-005 — WebGPU Y-orientation convention: flip at vertex clip output, row-flip on render-target readback

Date: 2026-08-05. Status: **ACCEPTED**. Owner: driver. Implementing lanes: A (codegen), B (pipeline + readback).

## Context

Blender's `gpu` frontend and its test oracles assume GL-style framebuffer orientation
(bottom-left origin). WebGPU rasterizes with a top-left-origin framebuffer space and,
unlike Vulkan (`VK_KHR_maintenance1`), offers **no negative-viewport-height** escape
hatch — so the backend must pick a flip site explicitly.

**Evidence this is real and load-bearing (B1, 2026-08-05):** with a *correct identity*
MVP, `blend_none`'s `[0,1]²` preset-quad corner lands on the pixel centre as a
BOTTOM+LEFT corner under y-down and is excluded by the top-left fill rule → zero
coverage → the "invisible" frames-gate failure (no validation error at all). The
decisive experiment: `diag(1,-1,1,1)` (negate only Y) makes `blend_none` PASS;
identity does not. With this flip + the `populate_builtins` fix temp-wired, the full
blend family renders **12/12 byte-matching** Blender's expected pixels
(`sandbox/gpu-render-harness/evidence/first_frames_blend.png`).

## Decision

1. **Single flip at the vertex-shader clip-space output** (lane A, codegen/glsl_patch):
   negate `gl_Position.y` equivalently for every vertex stage the backend compiles.
   One injection point, applies uniformly to all shaders.
2. **Winding compensation at pipeline creation** (lane B): a Y flip inverts effective
   triangle winding; swap front-face (CW↔CCW) in `wgpu_pipeline` state translation.
   Verify empirically against the suite (blend stays green; cull/two-sided tests when
   reached).
3. **Row-flip on render-target readback only** (lane B): `read_pixels`/attachment
   readback returns GL-convention bottom-up rows. Pure texture upload→read paths
   (no render pass) are symmetric and MUST NOT flip — do not regress the 52 passing
   texture tests.
4. **Presentation path (M4 canvas)** is expected to need NO additional flip; verify at
   first canvas frames. If frames arrive inverted there, the fix is revisiting sites
   1–3's consistency — never adding a fourth flip site.

## Rejected

- **Full-screen blit flip pass at present/readback** — extra pass + bandwidth on every
  frame; hides the convention instead of defining it.
- **Rewriting projection/matrix math in the shared frontend** — touches backend-agnostic
  `gpu/intern`/blenlib code used by all backends; unauditable patch surface; forbidden
  direction under GOAL ground rules.
- **Leaving y-down and adjusting test expectations** — the tests are the oracle;
  weakening them is forbidden (GOAL: no weakened tests, no parity theater).

## Consequences

- Real-path blend-family green requires lane A's flip + `populate_builtins` landing
  together (both proven sufficient by the temp-wire).
- Readback flip is inert for 1×1 targets (blend tests) — sequencing lane A first is
  safe; multi-row correctness lands with lane B's readback change.
- Also fixes the upside-down-frames failure mode pre-emptively for M4 in-tab pixels.
