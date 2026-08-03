# Harness issues (driver-owned; harness/ is lock-protected)

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

Workers record harness defects here instead of editing `harness/**`. The driver reconciles
them at a milestone boundary by temporarily lifting `.claude/harness.lock`, applying the fix,
re-running the gate, and re-locking.

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

## OPEN — needed to gate the tier-(a) suites (recorded 2026-08-03, M1.10/M1.11 worker)

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
