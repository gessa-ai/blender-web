<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Checkpoint 03 — orchestrator handoff session: M1 resized, M2 de-risked, M3 launched

Date: 2026-08-03 (evening). Author: driver (new orchestrator, same day as handoff).
Period covered: handoff → now. Receipts: commits f17bfef…b6b1dfe + in-flight worker lanes.

## OUTCOME (first)

- **M1 is bigger than the handoff sized it — and the plan now reflects reality.** Recon
  (5 agents) proved there is NO minimal bmesh closure: blenkernel is the whole-core hub;
  the tier-(a) bmesh gate needs ~150 more archives (~90% of the combined test binary).
  Offset: every hazard scan on that surface is CLEAN — wide mechanical grind, not ABI work.
  Gate vehicle decided: standalone `bmesh_core_test` via `WITH_TESTS_SINGLE_BINARY OFF`.
- **First M1 wall found, decided, rerouted same-day (ADR-002):** all 4 core libs were
  order-only-gated on GPU shader codegen; wasm-built `shader_tool` mis-tokenizes ~6 EEVEE
  shaders. Policy: ABI-baking generators (makesdna/makesrna) stay wasm-under-node;
  target-independent text/byte generators (shader_tool/datatoc) run NATIVE, gated by a
  byte-identity audit (fresh controlled comparison: 66/66 identical; 44 suspected-stale
  diffs in triage now). makesrna executed successfully under node for the first time.
- **M2's core risk collapsed (ADR-001 + probe):** vanilla CPython 3.13.13 builds AND runs
  on emcc 6.0.5 in BOTH exception models with ZERO source patches — first known 3.13-on-6.x
  result anywhere; the predicted patch needs (LONG_BIT, trampoline back-port) were
  unnecessary. EH decided: JS-EH (joins all 29 deps, zero rebuilds). `scripts/deps/python.sh`
  landed; libpython + headers + stdlib harvested to `lib/wasm` (42.2 MB .a, 2850 syms,
  idempotence proven). M2.4 verified already-done (OCIO/freetype/brotli forced during M1).
  M2 remaining: WITH_PYTHON flip (gated on M1), import bpy, tier-(b) gate, JSPI probe (in
  flight).
- **M3 started ~a month early.** Architecture measured, not guessed: Vulkan backend =
  28,062 LOC; webgpu/ estimate 13–17k (render_graph's 6,658 LOC eliminated by WebGPU's
  implicit model); 30-file skeleton; 19 pure-virtual backend surface (corrected);
  geometry-shader gap affects ZERO create-infos at the pin (M6 concern, not M3). T1–T10
  dependency-ordered tasks in fix_plan; T1 (Dawn+Tint native toolchain probe) in flight.

## Estimate (unchanged in direction, firmer in basis)

~20% of the way to first-pixels-in-a-tab by effort; ~5–9 weeks at current cadence, wide
error bars owned by M3 shader-chain conformance. M3 starting early is the main lever pulled
this session; the second (unattended 24/7 loop) still needs the human (`claude setup-token`).

## Incidents (honesty section)

- **Disk blocker recurred twice** (4.9→3.8 GiB; other projects' /private/tmp artifacts,
  not ours to delete). Paged precisely; human cleared → 38-46 GiB. Standing: keep ≥40 for M2/M3.
- **Session quota kill (21:00 EDT):** all 3 worker lanes terminated mid-task by the API
  limit; upstream left with the patch series applied (expected transient state, snapshotted);
  zero work lost (wip patch + notes on disk); all 3 resumed with context at 21:05.
- **Estimate corrections made against ourselves:** checkpoint-02's "bmesh needs animrig
  transitively" was false (needed via blenkernel/rna instead); "GPU/UI stubbed" was loose
  (full-tree configure with backends OFF); both corrected in notes/m1-closure-recon.md.

## Live lanes (as of this checkpoint)

1. M1.13a→M1.13/14: byte-identity triage → native host tools → blenkernel/depsgraph grind.
2. M2.7: JSPI × setjmp/longjmp probe matrix (final verification + report).
3. M3.T1: Dawn+Tint native build (mid-diagnosis of a build failure — characterization is an
   acceptable T1 outcome).

Next driver actions on worker reports: integrate patches 0007+, dispatch wave-2 grind
(claude+codex partitioned by module), M1.16 harness reconcile at the boundary, then the
WITH_PYTHON flip.
