# Harness issues (driver-owned; harness/ is lock-protected)

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

Workers record harness defects here instead of editing `harness/**`. The driver reconciles
them at a milestone boundary by temporarily lifting `.claude/harness.lock`, applying the fix,
re-running the gate, and re-locking.

## OPEN 2026-08-11 — final owner ratification of accumulated boundary reconciliations

The integration driver committed the accumulated `harness/run.sh` delta in `2bd738f` during a
sanctioned lock-lift while closing M1 through M8. This makes the exact change reviewable; it is
not final human ratification of a file that `GOAL.md` declares immutable. Publication must not
silently treat it as unchanged authority. A human owner must either ratify the exact final
harness digest at the release boundary or restore the prior harness and provide an equivalent
externally reviewed gate.

The committed delta registers receipt-only M4-M8 scopes; records artifact hashes in M1/M2
details; retires only the literal 0117/0125 diagnostic-history patches while asserting their
payload is absent; removes resolved M2/M3 expected-nonpass mappings; rejects `resolved`
deferral IDs; and raises M3 census floors to the measured 189/196 tests and 995/1003 shaders.
It does not lower a pixel tolerance, comparator threshold, suite count, or active failure
expectation.  Before ratification, run the final frozen-source M0–M7 scopes, `--regress`, a
clean ordered `patches/series` replay, and bind the resulting `harness/run.sh` SHA-256 in the
closeout receipt.  Until then, the harness delta is an explicit launch blocker rather than an
implicit exception to the ground rule.

## OPEN 2026-08-11 — final M0–M3 receipts are weaker than the literal GOAL contract

The final read-only audit found several fail-open or stale-evidence seams that must not be hidden
behind the current per-scope green status:

- `scope_m0` checks a live local macOS Blender and semantic emcc version only.  It does not prove
  the promised oracle container, CI workflow, exact emsdk checkout identity, both build caches, or
  CI `reuse lint` step.
- `scope_m1` accepts exactly ten BLI failures by total count without checking their identities.
  A new failure can therefore replace an expected failure without changing the receipt.  Nine
  expected failures are the fenv family; the `/tmp` versus `/private/tmp` chdir mismatch has no
  registry entry.  The literal tier-(a) contract says the suites pass identically.  Only one of
  nine corpus files is live-run by the scope; the other retained dumps are not artifact-bound.
- `scope_m2b` gates suite exit codes while native normalized state diffs are advisory, and it
  requires seven named suites to remain failing.  This is weaker than the tier-(b) native-state
  parity contract and makes an expected improvement turn the scope red.
- `scope_m3` accepts six test failures, one crash, and eight static shader non-compiles.  Its
  current green receipt predates both the current `blender_test` and a later CMake reconfigure;
  a dry run schedules more than one thousand rebuild edges.  The receipt also predates patches
  0147/0148 and does not bind the test binary, CMake cache, Dawn/Tint/shaderc inputs, or frozen
  source manifest.
- A successful single-scope invocation unconditionally removes `harness/GATE_RED`, so
  `harness/status.sh` can say `gate: green` while other scopes are red.  Only a complete final
  `--regress` makes the global flag meaningful.
- The patch checker accepts a dirty target set as `in-development`, which currently masks a
  non-replayable numbered stack.  Final closeout requires the canonical pristine-pin replay and
  byte manifest; dirty-tree state is never acceptable evidence.

Resolution boundary: do not lower any expectation in `harness/run.sh`.  Build the missing M0
artifacts, freeze and replay source, regenerate every M1–M3 artifact, run both corpus families,
and enforce the literal identities/parity with an external fail-closed closeout verifier.  A human
owner must then ratify the exact final harness digest or restore an equivalent reviewed oracle.
The last operation is a complete `--regress`; no intermediate `GATE_RED` state is authoritative.

## RESOLVED 2026-08-20 — audit log allocation and RED-marker hygiene

Commit `2bd738f` reserves build logs with an atomic no-clobber create using a UTC timestamp,
wrapper PID, and bounded collision suffix. The frozen-clock self-check runs 4 sequential and
32 concurrent independent wrappers, then sources 16 concurrent wrappers under one Bash PID to
force the suffix path; all 52 logs remain unique with exact content. The gate scope join now
uses a delimiter-aware join rather than a trailing-space-producing newline translation.
The driver followed the reconciliation procedure, restored `.claude/harness.lock`, retained
M0 at 6/6 GREEN, and left the expected M1-M6 RED blockers unchanged. This resolution does not
close the final owner-ratification item above.

## RESOLVED 2026-08-03 (M1 boundary, commit pending)

All three reconciled in `harness/run.sh` v1.1 + `status.sh`; m0 re-verified 6/6 GREEN; lock restored.
Two further bugs were found by testing the fix itself: unknown-scope typos falsely wrote
GATE_RED (would have blocked every agent via the Stop hook), and the milestone line broke
once SPDX headers landed atop fix_plan.md. Both fixed.

## (historical) OPEN — reconcile at the M1 boundary

**H-1. `run.sh` result schema deviates from the GOAL contract.**
Committed `run.sh` writes `ledger/results/m0.json` as a bare array of `{name, pass, detail}`.
GOAL/harness contract expects an object: `{"scope": ..., "pass": bool, "checks": {...}, "ts": ...}`.
Impact: `status.sh` works today, but any future aggregation (the public conformance dashboard,
per-suite percentages) has to special-case the shape. Fix before the dashboard exists.

**H-2. No `--regress` mode.**
GOAL's per-iteration protocol is `run.sh --scope <item>` then `run.sh --regress`. `--regress`
does not exist, so step 5 of every iteration is silently a no-op. This is the single most
important gap: without it, workers can pass their own scope while breaking a previously-green
one and nothing catches it. **Highest priority of the three.**

**H-3. emcc version check reads `oracle/TOOLCHAIN` instead of probing live.**
A stale or hand-edited TOOLCHAIN file would make the toolchain check pass against a toolchain
that isn't actually installed. Probe `emcc --version` at run time and compare.

## RESOLVED 2026-08-04 (M1 boundary reconcile, driver)

H-4 + H-5 both closed: `m1` scope registered in run.sh (node_runtime, patches_series
clean-or-applied invariant, blenlib 1665/10 + bmesh_core 1/0 via --gtest_output=json —
stdout capture is UNRELIABLE for these binaries: multi-thread wasm stdio drops lines at
exit, so counts must come from the JSON file; relative path required, absolute silently
fails under NODERAWFS). m0 re-verified 6/6, m1 4/4, full --regress green, lock restored.
H-5's blocker chain (blenkernel/depsgraph + datatoc) was resolved by wave-2 + ADR-002.

## (historical) OPEN — needed to gate the tier-(a) suites (recorded 2026-08-03, M1.10/M1.11 worker)

**H-4. `run.sh` has no `m1` scope; the tier-(a) gtest gate cannot be driven by the harness.**
`SCOPES_REGISTERED="m0"` only. The blenlib gtest suite now links and runs on wasm
(`ledger/results/m1.json` written directly by this worker, per the "result file only" allowance).
The driver must, at the M1 boundary: lift `.claude/harness.lock`, add a `scope_m1` that
(1) applies patches 0001-0006 to `upstream/`, (2) `emcmake` configures `build-wasm`,
(3) `ninja BLI_test`, (4) runs it under `tools/emsdk/node/.../node build-wasm/bin/tests/BLI_test.js
--test-assets-dir upstream/tests/files`, (5) parses the gtest tail for `[  PASSED  ]` / `[  FAILED  ]`,
asserting 1655 pass / the 10 characterized non-passes (9 fenv-deferral + 1 macOS-host chdir), then
reverts upstream pristine. Register `m1` in `SCOPES_REGISTERED` and add it to `--regress`.

Runner facts the scope must bake in (already in `patches/platform_wasm.cmake`, gated on WITH_GTESTS):
the gtest binaries link `-sNODERAWFS -sEXIT_RUNTIME=1` so they can read the real UTF-8 asset files
and exit with RUN_ALL_TESTS()'s code (a PROXY_TO_PTHREAD runner otherwise keeps node's worker pool
alive and never exits). Wall time is ~1s; no special node flags needed on node 22 (wasm threads on
by default).

**H-5. bmesh_core gate is blocked upstream of the harness** — see `ledger/results/m1.json`
`bmesh_core_test_link`: bf_bmesh needs blenkernel + depsgraph ported to wasm and the `datatoc`
host tool wired through `blender_web_host_tool()` (datatoc.js -> Permission denied, rc 126). Not a
harness defect; a build-deps task. Do not register an `m1` bmesh check until that lands.

## Reconciliation procedure (driver only)

1. `rm .claude/harness.lock`
2. Apply fixes; run `harness/run.sh --scope m0` and confirm still 6/6 green.
3. Add a regression scope for whatever milestone is closing.
4. `touch .claude/harness.lock`; commit both the fix and the re-lock in one commit.

## Process lessons (recorded 2026-08-03)

- **Duplicate dispatch:** a worker that returns instantly with no tool calls may still be alive;
  resuming it can create two instances of the same task. Before resuming, check whether the work
  already landed (`git log`, target files). Two instances raced the harness task; no damage
  because the second declined to commit, but it burned a full worker cycle.
- **Concurrent writes to shared files:** `REUSE.toml` was left duplicated/self-conflicting by two
  workers in the same round. See `notes/path-ownership.md` — one owner per shared file per round.

## 2026-08-04 gpu-backend (lane A): stacked patches on one CMakeLists block break per-patch reverse-check

`run.sh`'s patch-series check loops `patches/0*.patch` and asserts each patch
either forward-applies (pristine) OR reverse-applies (applied). This assumes each
patch is INDEPENDENTLY reversible. It breaks when two patches edit the SAME file
region: `0012` and `0015` both modify the `if(WITH_WEBGPU_BACKEND) list(APPEND
SRC ...)` block in `source/blender/gpu/CMakeLists.txt` (0015 adds the buffer
sources to the list 0012 created). Consequences:
- Against the all-applied tree, reversing `0012` alone fails (0015's lines sit in
  the same block) → 0012 flagged as conflict.
- Against pristine, `0015` forward-check fails (its hunk context needs 0012).

The SERIES is correct: `git apply 0011 0012 0015` in order applies cleanly from
pristine (verified), and bf_gpu compiles. Only the *per-patch, order-independent*
check is fooled. This will recur as lane B's patch (0016+) also appends to that
same SRC list — the WITH_WEBGPU SRC block is a multi-patch merge point.

Options (orchestrator's call): (a) make `run.sh` reverse-check in REVERSE glob
order and stop at the first clean state; (b) convert the WITH_WEBGPU SRC list to a
`file(GLOB ...)` so per-file patches don't edit CMakeLists at all (needs a 0012
touch — currently frozen); (c) designate ONE patch per round as the sole owner of
the SRC-list edit (path-ownership per `notes/path-ownership.md`). Recommend (b)
long-term, (c) for now. No code correctness impact.

## H-6 (env, 2026-08-08): run.sh requires bash >= 4
harness/run.sh uses associative arrays (line ~436 EXPECT_NONPASS); macOS /bin/bash 3.2
fails with "static_shaders: unbound variable" (arithmetic-parse of the array literal
under set -u). Not a harness defect - an environment requirement: invoke via
/opt/homebrew/bin/bash (5.x) or ensure PATH resolves a modern bash. Shell snapshots
after process restarts can silently drop the homebrew PATH (observed: two invocation
environments in one day). Harness-lock respected: documented here, no run.sh edit.
