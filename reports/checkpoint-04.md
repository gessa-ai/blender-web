<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Checkpoint 04 — tier-(a) closed; full Blender links and boots; M3 four tasks deep

Date: 2026-08-04 04:00 EDT. Author: driver. Period: checkpoint-03 → now (~7 hours).
Receipts: commits db88bd3…ab3fd30 + five in-flight lanes (state surveyed on disk).

## OUTCOME (first)

- **M1 tier-(a) gate: 2/2 GREEN, harness-locked.** Wave-2 compiled all 90 remaining core
  archives (2,147 TUs, 5 parallel lanes) with TWO source fixes total — both latent upstream
  WITH_PYTHON=OFF bugs. `bmesh_core_test` (62 MB wasm, ~200 archives) links with one
  undefined symbol (fixed, patch 0009) and passes 1/1 (= the full upstream suite at pin,
  verified). Harness v1.2 registers the `m1` scope (gtest-JSON counting — threaded-wasm
  stdout drops lines under capture); m0 6/6 + m1 4/4 + full regress green; lock restored.
- **M2 ~95%: the real `blender.js` (82 MB) links and BOOTS under node** — WITH_PYTHON ON,
  bf_python zero fixes, libpython rebuilt self-contained. Blocked at the first `.blend`
  read by a now-DIAGNOSED ABI bug: the runtime `DNA_struct_reconstruct` re-computes target
  offsets UNPADDED (an independent copy of the i386 model patch 0002 fixed in makesdna) —
  invisible on LP64, drifts on wasm32; measured blast radius = exactly 1 struct of 993
  (Scene). Fix decided (single-source: reconstruct consumes makesdna's verified offsets;
  patch 0014) and was mid-verification (full-993-struct scan) at the quota kill.
- **M3 is 4/10 tasks deep, both #1 risks retired:** T1 shader chain PASS on native Dawn
  (with 3 load-bearing API corrections incl. the SPIR-V-1.3 ceiling); T2 normative binding
  spec pipeline-validated with a negative control; T3 GHOST_ContextWGPU device-live (130
  LOC, patch 0011); T4 (backend registration + native gpu-suite link, patch 0012 drafted)
  was mid-link at the kill. T7's hardest half developed standalone (4/4 cases passing +
  the sampler-array limitation characterized at Tint parser.cc:200) — pending final note.
- **The browser lane exists:** `blender_browser.{js,wasm,data}` BUILT (non-NODERAWFS
  profile + payload packaging), shell page + COOP/COEP server written — was at artifact
  inspection when killed. The local link is one resume + one DNA fix away.
- **Tier-(b) prep done on the oracle side:** runnable-suite baselines captured
  (bl_animation_*, bl_brush, …) + scope draft — pending final note.

## Estimate

- **Blender-in-a-tab console proof: days** (M2.5b fix + M4.pre landing; both were in
  final verification when the quota window closed).
- **First rendered images (native Dawn, gpu-suite parity): ~1–2 weeks.**
- **First pixels in the tab (M4): ~2–4 weeks** at observed cadence. CPU-side work ran
  ~5–10× faster than the original sizing (mechanical + parallelizable); M3 remains the
  novel-code risk and is deliberately front-loaded.

## Incidents (honesty section)

- **Quota kills #2 (~01:00) and #3 (~03:5x, resets 07:00)** — five lanes down twice;
  recovery is routine (on-disk state + transcript resume; nothing lost across any kill).
  A wake-timer resumes all five at 07:00. Codex remains quota-dead until Aug 10 — no
  engine-diversity fallback this week.
- **Host-process restart (~02:5x)** — same recovery, zero loss.
- Worker hygiene debt to collect at resume: a stray `bl_pyapi_bmesh.blend` at repo root
  (tier-b lane), `patches/9999-t4-verify-harness.patch` temp file (T4 lane).

## Live lanes at kill (all resume 07:00 with precise briefs)

1. M2.5b DNA fix — table emitted, dna_verify green, mid full-scan verify.
2. M4.pre browser shell — artifacts built, mid inspection → then Chrome verify.
3. M3.T4 — verify-target link running at kill; patch 0012 + 9999-harness on disk.
4. M3.T7.pre — 4/4 passing, note finalization + commit remaining.
5. M2.6.pre tier-b — baselines done, note write + commit remaining.
