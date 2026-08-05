<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# ADR-004: 64-bit `.blend` address truncation on wasm32 — interim loud detector now; wasm64-vs-interner decided by probe

Date: 2026-08-04. Status: ACCEPTED (driver) for the interim; structural choice OPEN pending
the Memory64 probe. Evidence: notes/m2-bhead-pointer-collision.md (c374c50) — proven
colliding pair 6 bytes apart in a real file; corpus clean 8/8 by luck; both map keys AND
pointer fields truncated via the same `>>3` (BLO_core_bhead.hh:124, dna_genfile.cc:929).

## The problem, precisely

Reading 64-bit `.blend` files on wasm32 compresses 8-byte block addresses into 4 bytes
assuming 8-byte alignment. Real writers emit sub-8-aligned adjacent DATA blocks → distinct
addresses collide → duplicate map insert (loud abort) or, worse, mis-resolved pointer
fields (SILENT corruption). Data-dependent: most files pass, some files break, nothing in
the file format forbids the breaking layout. Launch requires drag-drop of arbitrary user
`.blend` files — this cannot ship as-is on wasm32.

## Decision 1 (NOW): loud collision detector, patch 0017

At BHead-index build time (wasm32 only, `#ifdef`-guarded), detect any duplicate truncated
address across the file's block set and REFUSE the read with an explicit error naming this
ADR. Converts the silent-corruption risk into a deterministic, user-visible failure with
zero behavior change for non-colliding files (the overwhelming majority). This is a
guarded safety check within the documented fix class — not the fix.

## Decision 2 (gate math): affected m2b suites reclassify to blocked-by-ADR-004

Honest accounting: they fail because wasm32 cannot yet represent these files, detector
makes that loud; they are not "passing with tolerance" and not silently dropped. They
re-enter the gate when the structural fix lands.

## Decision 3 (STRUCTURAL, probe-gated): wasm64 vs pointer interning

- **wasm64 (`-sMEMORY64`)** — structurally clean: pointers are 8 bytes, the truncation
  machinery disappears, readfile matches native exactly; also retires the entire ILP32
  bug class (patches 0002/0014 models become native-like). Costs: full-stack rebuild
  (all deps + libpython + Blender), Memory64 browser floor (Chrome ≥133/Firefox ≥134 —
  INSIDE our Chrome-137 JSPI floor), and a historical wasm64 perf tax (bounds checks) that
  must be measured, not assumed. GOAL anticipates "wasm64 later behind a flag."
- **Pointer interning on wasm32** — per-FileData 64→32 id assignment applied consistently
  to keys and every reconstructed field. Correct in principle; invasive in practice (the
  interner must thread through `DNA_struct_reconstruct` or live in save/restore
  thread-local state across nested library reads); silent corruption if done wrong.
- REJECTED regardless: alternative shifts/low-bits (pigeonhole — still collides).

**Probe (dispatched):** under emcc 6.0.5 `-sMEMORY64`: (a) toolchain reality — hello +
zlib + one mid-size dep build; (b) Chrome Memory64 runtime check in a tab; (c) micro-bench
(BLI-style hash/loop workload) wasm32 vs wasm64 for the perf tax; (d) inventory what else
breaks (JSPI×Memory64 interaction? emdawnwebgpu?). Decision lands on the probe's numbers:
if the tax is acceptable and the toolchain is clean, wasm64 is the path (likely post-M4,
pre-launch); else the interner gets designed as its own ADR with the coupling solved.

## Decision 3 RESOLVED (appended 2026-08-05, probe evidence b75ef36): **wasm64**

The Memory64 probe answered every dimension in wasm64's favor: emcc 6.0.5 builds our dep
shapes clean; Chrome (Memory64 since 133 — inside our 137 floor) instantiates and runs
correctly; the feared perf tax DOES NOT EXIST (BLI-flavored map churn ran ~14% FASTER on
wasm64 under V8's trap/guard-page bounds checks; float loop equal); and `-sMEMORY64`
links with the full flag set — WASM_BIGINT, growth, pthread+PROXY_TO_PTHREAD, dlmalloc,
NODERAWFS, EXIT_RUNTIME, JSPI, and `--use-port=emdawnwebgpu`. wasm64 also retires the
entire ILP32 class structurally (0002/0014 models become native-like; detector 0018 goes
inert). **Scheduled: post-M4, pre-launch.** Named prerequisite: the node-based harness
runners cannot instantiate wasm64 (V8 12.4 rejects 64-bit table limits) — bump the
harness node (≥23-era V8) or move those gates in-browser first. The pointer-interner
option is closed. Patch 0018 holds the line until the migration lands.

## Consequences

- M2's promise can proceed on the honest bar with the reclassification named in the gate.
- The deferral registry gains `wasm32-64bit-blend-collision` (detector active, structural
  fix scheduled) — visible, not buried.
- LAUNCH.md's drag-drop bar depends on Decision 3 landing before M8.
