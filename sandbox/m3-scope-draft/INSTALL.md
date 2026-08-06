<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Driver install guide — M3 GPU-backend gate (`scope_m3`)

This is a **staging draft**. `harness/` is lock-protected; only the driver installs it, at
the M3 boundary, following the reconcile procedure in `notes/harness-issues.md`. Nothing here
touches `harness/**` — the driver lifts the lock, pastes the drafted block, re-verifies, and
re-locks in one commit.

## Files in this draft

| File | Role | Destination |
|---|---|---|
| `scope_m3.fragment.sh` | the exact `scope_m3()` block (+ banner comment) | pasted into `harness/run.sh` |
| `dryrun.sh` | standalone runner that reproduces run.sh's scaffolding | stays in staging (dev tool) |
| `m3.dryrun.json` | the dry-run's result JSON (schema sample; **not** the ledger file) | stays in staging |

## Dry-run FIRST (validate before installing)

The fragment runs unchanged from staging — `dryrun.sh` supplies the same `record`/JSON-emit
scaffolding run.sh has, but writes `m3.dryrun.json` here instead of `ledger/results/m3.json`.

```sh
bash sandbox/m3-scope-draft/dryrun.sh
# optional alternate build:  M3_TEST_BIN=/path/to/blender_test bash sandbox/m3-scope-draft/dryrun.sh
```

Expected: `dryrun: scope=m3 ALL GREEN (5/5)`, exit 0, and a well-formed `m3.dryrun.json`
(`"pass": true`, five checks). Wall time ~35-40 s (158 native one-per-process runs). The
`build-native-gpu` `blender_test` is **not** relinked by the concurrent gpu round; if it is
mid-rebuild the `gpu_binary` preflight FAILs with a "busy/relinking? retry after ~3 min" detail
— wait and re-run (per `notes/harness-issues.md` / the r18 note), do not install on a red
preflight.

## Install into harness/run.sh (driver only)

Follow `notes/harness-issues.md` "Reconciliation procedure":

1. `rm .claude/harness.lock`
2. **Register the scope** — one-token edit at `harness/run.sh:17`:
   ```diff
   -SCOPES_REGISTERED="m0 m1 m2b"
   +SCOPES_REGISTERED="m0 m1 m2b m3"
   ```
3. **Paste the scope body** — insert the whole of `scope_m3.fragment.sh` **below** the closing
   `}` of `scope_m2b()` and **above** the `# ------ scope runner` banner (currently
   `harness/run.sh:359`, the blank line between `scope_m2b` and `run_one_scope`). Drop the
   fragment's leading SPDX/DRAFT comment block if preferred; keep the `# ---- scope: m3`
   banner to match the m0/m1/m2b house style. No other edits — the fragment only calls
   `record` (runner-supplied) and reads repo-root-relative paths (run.sh already `cd`s to ROOT).
4. Confirm the earlier scopes are undisturbed: `harness/run.sh --scope m0` (6/6),
   `--scope m1` (5/5), `--scope m2b` (4/4).
5. `harness/run.sh --scope m3` → expect `ALL GREEN (5/5)` and a fresh `ledger/results/m3.json`.
6. `harness/run.sh --regress` → every prior scope + m3 green; `harness/GATE_RED` removed.
7. `touch .claude/harness.lock`
8. **Commit together** — the run.sh edit **and** the re-lock in ONE commit (procedure step 4).
   The driver may also commit `ledger/results/m3.json` (the real gate receipt).

## The five checks (what each asserts)

1. **`gpu_binary`** — `build-native-gpu/bin/tests/blender_test` exists, is executable, and
   enumerates the `GPUWebGPUTest` suite (preflight; FAILs with a rebuild recipe if absent, or a
   retry hint if it lists 0 tests).
2. **`patches_series`** — the `patches/0*.patch` clean-or-applied/​in-development invariant,
   byte-identical to `scope_m1`'s `patches_series` (see "Reuse note" below).
3. **`gpu_suite_census`** — runs all 158 tests one-per-process. GREEN iff `PASS ≥ 148`, **and**
   every non-PASS test is in the expected-non-pass map (each mapped to a `deferred.json` id or a
   blacklist group), **and** no mapped (deferred/blacklisted) test has started passing
   (un-defer candidate), **and** none vanished. Reports `148 PASS / 8 FAIL / 2 CRASH`.
4. **`static_shaders`** — parses the aggregate compile test bucket-style: requires
   `total == 973` and `passed ≥ 956` (a **MINIMUM** — a concurrent gpu round that compiles more
   stays green), and every remaining non-compile buckets by error signature into a registered
   class (`imageAtomic`→storage-texture-atomics, `vertex pipeline stage`→vertex-stage-rw-storage,
   `OsdPatchParamIsRegular`→subdiv blacklist, `fullscreen_blit`→Metal-only blacklist). Any
   un-bucketed non-compile = a NEW class = RED.
5. **`deferral_consistency`** — the honesty cross-check (mirrors `scope_m2b`): the 5 M3-gate
   deferral ids exist in `ledger/deferred.json` and the 4 blacklist tokens are documented in
   `notes/gpu-gate-blacklist.md`.

## What the driver must decide at install

Nothing is blocking — the dry-run is 5/5 green as drafted. Judgement calls, if any:

- **GPU test-set size.** The census pins `PASS ≥ 148` and reconciles all non-passes by name. A
  concurrent gpu round that only *fixes shaders* keeps the set at 158 and the census green
  (fixed shaders raise `static_shaders`, which is a minimum). If a future patch *adds or removes
  a GPUWebGPUTest*, update `EXPECT_NONPASS` / re-census (the check will flag it, not silently
  pass). Measured now: exactly 158 tests, 148/8/2.
- **A deferral that starts passing** (e.g. subpass emulation lands) trips the census un-defer
  guard → RED-with-flag, exactly as `m2b` treats a passing deferred suite. That is intended: the
  driver removes the entry from `deferred.json` + `EXPECT_NONPASS`, not silence it.
- **Reuse note (`patches_series`).** The check is a verbatim copy of `scope_m1`'s loop (same
  logic, same record name) so m3 re-asserts the patch tree without a locked-harness refactor. A
  later optional cleanup could hoist it into a shared helper used by both m1 and m3; out of scope
  for the gate.
- **Runtime.** ~35-40 s added to `--regress` (158 native processes, GPU init each). Acceptable
  for a milestone gate; no build step (the gate consumes the pre-built native binary).

## Shader-chain byte-parity check (item 1d)

`rg` over the current `harness/` finds **no** shader-chain byte-parity check to reuse (the only
parity check is `scope_m1`'s `corpus_parity`, which is `.blend` state-dump parity, unrelated).
Per the "reuse, don't reinvent" instruction, none is added here. If a shader byte-parity oracle
is introduced later (e.g. golden WGSL for a fixed create-info set), it belongs as a 6th m3 check
then — not invented now.
