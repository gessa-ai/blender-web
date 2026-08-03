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
