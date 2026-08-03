# Path ownership manifest

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

Why this exists: on the first concurrent round (2026-08-03) two workers wrote `REUSE.toml`
simultaneously and left it duplicated/self-conflicting. Git worktrees prevent *physical*
collisions between workers; they do not prevent two agents from editing the same logical
file. This manifest is the coordination contract. The driver enforces it at merge.

## Rule

A worker may create/modify files **only** under paths its area owns. Anything else it needs
changed goes in its final report as a request to the driver. Shared files have exactly one
owner per round — never two workers in the same round.

## Areas → owned paths

| Area | Owns |
|---|---|
| `build-deps` | `patches/**` (cmake/config/toolchain), `ledger/deps.json`, `notes/deps-*.md` |
| `python-wasm` | `platform_web/python/**`, `notes/python-*.md` |
| `gpu-backend` | `patches/gpu/**`, `notes/gpu-*.md` |
| `ghost-web` | `platform_web/ghost/**`, `platform_web/shell/**`, `notes/ghost-*.md` |
| `harness` | `harness/**`, `oracle/**` — **locked**: only unlockable by the driver at a milestone boundary |
| `compliance` | `LICENSES/**`, `LICENSE`, `NOTICE`, `PROVENANCE.md`, `THIRD-PARTY.md`, `REUSE.toml` |
| driver (orchestrator only) | `GOAL.md`, `fix_plan.md`, `reports/**`, `notes/path-ownership.md`, `.claude/**` |

## Always-shared, append-only (safe for any worker)

- `ledger/progress.txt` — **append one terse line only**; never rewrite or reorder.

## Always read-only (hook-enforced)

- `upstream/**` — pinned Blender source. Changes go in `patches/` as diffs.
- `tests/golden/**` — oracle-generated references.
- `harness/**`, `oracle/**` — while `.claude/harness.lock` exists.

## Conflict protocol

1. Need a file you don't own? Report the request; do not edit it.
2. Hit a rebase conflict on a shared file? Take upstream's version, re-apply only your own
   lines, and note it — never resolve by overwriting someone else's block wholesale.
3. Two workers in one round needing the same file = a planning bug. The driver splits the
   task or serializes the round instead.
