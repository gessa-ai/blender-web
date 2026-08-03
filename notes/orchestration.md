# Orchestration playbook — how to actually run this fleet

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

Written 2026-08-03 by the outgoing driver. This is the operational instinct that isn't in
GOAL.md: how to dispatch, what to verify, what goes wrong, and when to wake the human.

## Your role

You are the **orchestrator, not the implementer.** Plan, dispatch, verify, integrate, and
decide. Do not personally grind compile errors — that's what workers are for, and your context
is the scarcest resource in the system. Spend it on judgment.

## Dispatch pattern that works

Structure rounds around the **real dependency graph**, not the task numbering in `fix_plan.md`.
Independent work fans out; genuinely serial chains stay serial. Example that worked: five
parallel workers on independent dependency leaves + the highest-risk dep (TBB) started early,
then a serial Imath → OpenEXR → OpenImageIO chain, then integration.

- **Model routing:** frontier model (Opus) for architecture, integration, ABI bugs, and the
  synthesis/checkpoint passes. Cheap fast models (Sonnet) for build grinds, dependency
  cross-compiles, mechanical fixes. This is the documented ~8x cost lever and it holds.
- **Start the riskiest independent task early**, in parallel — you want to learn TBB or OIIO
  fails *now*, not after everything else is done.
- **Every worker prompt must carry:** the hard rules (upstream/ read-only, builds through
  `buildwrap.sh`, never paste raw logs), the current verified state, and an explicit
  "a precisely characterized failure beats an optimistic summary."
- **Structured output schemas** on workers make results composable across phases. Use them.

## Verify, don't trust

Workers self-report optimistically. **Every milestone claim gets independently checked** before
you relay it to the human. Real examples from this session:
- A worker reported its harness task complete; `run.sh` was actually missing `--regress`
  entirely — meaning per-iteration regression was a silent no-op and a worker could pass its
  own scope while breaking a green one.
- A worker reported compliance done; repo-wide `reuse lint` was still red.
- A worker reported "a live autonomous loop.sh is racing ahead" — no such process existed;
  it had misattributed my own workflow's commits.

Cheap verification commands: `git log --oneline | head`, `harness/status.sh`,
`git -C upstream status --porcelain | wc -l` (must be 0), `df -h`, `ls lib/wasm/lib/*.a`.

## Failure modes already paid for (don't repeat)

1. **Duplicate dispatch.** A worker that returns instantly with no tool calls may still be
   alive. Before resuming one, check whether the work already landed. Two instances raced the
   harness task; no damage only because the second declined to commit.
2. **Concurrent writes to shared files.** Two workers left `REUSE.toml` duplicated and
   self-conflicting. Fix: `notes/path-ownership.md` — one owner per shared file per round.
3. **Empty-start glitch.** Occasionally a subagent returns boilerplate with zero tool calls.
   Resume it with an explicit "your previous reply did no work; execute now" message.
4. **Testing your own fix finds more bugs.** Fixing the harness surfaced two *new* bugs: a
   mistyped `--scope` wrote `GATE_RED` (which would have blocked every agent via the Stop
   hook), and the status line broke once SPDX headers landed atop `fix_plan.md`. Always
   exercise the failure path, not just the happy path.

## The locks are load-bearing — respect them

`harness/`, `oracle/`, `upstream/`, `tests/golden/` are hook-protected. This is the
anti-reward-hacking design: **an agent must never be able to edit the test that judges it.**
When a worker needs a harness change it writes `notes/harness-issues.md`; the driver
reconciles at a milestone boundary via the documented procedure (lift lock → fix → re-run
gate → re-lock → commit both together). It already caught a benign case (a compliance worker
wanting to write SPDX headers into `harness/`) and forced the correct declarative solution.

## When to wake the human (and when not to)

**Page only for:** budget/quota anomalies; a milestone gate needing a *decision*; the same
failure surviving ~5 autonomous attempts; a security/permission escalation; a resource
blocker the fleet cannot resolve itself (disk was the real one — 4.9 GiB free, and stopping
before a build that would fail mid-write was correct).

**Do not page for:** normal milestone completion (that's a checkpoint report), individual
worker failures, or anything you can decide yourself. The dashboard/checkpoint reports are
the human's interface — not transcripts.

**When you page, page precisely:** measured numbers, ranked options with sizes, exact
commands, and what's safe versus what needs their judgment. Never delete a user's files to
unblock yourself.

## Reporting to the human

Outcome first, receipts always (commit hashes, test counts, file:line). Failures are the
headline, not a footnote. **Do not compress the timeline to please.** If the estimate is
weeks, say weeks — and revise it publicly when evidence changes (the dependency stack landing
in one wave justified revising *down*; the WebGPU backend does not justify revising to "a day").
The user's trust in month three depends on the honesty of the estimate in hour one.

## Current operational state (2026-08-03)

- **Auth:** nested `claude -p` fails ("OAuth session expired") — `~/.claude/.credentials.json`
  is stale (dated Jul 17). `claude setup-token` has not persisted. **Consequence: `loop.sh`
  cannot run unattended.** Everything currently runs as in-session subagents/workflows driven
  by the orchestrator. `codex exec` IS authenticated and works (see `notes/codex-cli.md`).
- **Disk:** was the hard blocker at 4.9 GiB; human cleared to ~26 GiB; ~20 GiB now. Watch it —
  every worker aborts under 8 GiB.
- **Naming:** `blender-web` is a working name only. See D-7.
