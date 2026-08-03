<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# PAGE: disk blocker recurred (M0.8-CRIT) — 4.9 GiB free, floor is 8 GiB

Date: 2026-08-03 (afternoon, new orchestrator session). Second occurrence: you cleared
to ~26 GiB earlier today; it refilled within hours — **not by blender-web**.

## The numbers (measured this session)

- `df /Users/paws`: **4.9 GiB free of 926 GiB (100%)**. Workers abort under 8 GiB.
  GOAL requires ≥40 GB headroom before M2 (CPython superbuild).
- **blender-web's total footprint is ~3.5 GiB** (emsdk 1.8 G, oracle image data 906 M,
  pinned upstream 633 M, build trees ~210 M, harvested `lib/wasm` 74 M) plus its share
  of Docker below. We have nothing significant left to clean on our side.

## Where the space went (none of it ours to delete)

| Consumer | Size | Status |
|---|---|---|
| `/private/tmp/hermes-*` | ~11 GB | idle since Aug 1–2 |
| `/private/tmp/boots-*` | ~7 GB | idle since Aug 1–2 (one touched Aug 3 09:00) |
| `/private/tmp/gessa-*` | ~6.4 GB | **ACTIVE — written Aug 3 15:43, minutes before this page** |
| `/private/tmp/zipcheck` + misc | ~1 GB | idle |
| Docker (total 12 GB) | 4.3 GB unused images, 1.1 GB build cache, 0.6 GB volumes reclaimable per `docker system df` | 25 images, only 4 active |
| `~/.cache` | codex-runtimes 1.5 GB, uv 1.4 GB | tool caches |
| Your data (`plushly` 232 GB, `Desktop` 98 GB, `Library` 82 GB) | 412 GB | untouched, yours |

These `/private/tmp` directories look like build/test artifacts from your other agents'
sessions (hermes, boots, gessa projects). I will not delete another session's files.

## Ranked options (pick any; I execute nothing without your go-ahead)

1. **Clear the idle `/private/tmp` build dirs (~18–19 GB)** — hermes + boots are 1–2 days
   stale. If no session of yours is mid-flight on them:

   ```bash
   sudo rm -rf /private/tmp/hermes-* /private/tmp/boots-* /private/tmp/zipcheck
   ```

   A plain **reboot also clears `/private/tmp` entirely (~34 GB)** — but would kill the
   active gessa session, so time it accordingly.

2. **Docker prune (~5.4 GB)** — 1.1 GB build cache is safe (`docker builder prune -af`);
   the 4.3 GB of unused images may include images your other projects want
   (`docker image prune -a` removes all unattached ones — the blender-web oracle image is
   active and survives). Say the word and I'll run the safe subset.

3. **Tool caches (~2.9 GB)** — `uv cache clean` + trimming `~/.cache/codex-runtimes`.

## What blender-web needs

- **≥10 GiB free** to run the next wave (compile `blenkernel` + `depsgraph` to wasm,
  ~1–2 GiB of new build objects, plus safety margin over the 8 GiB worker floor).
- **≥40 GiB free before M2** (CPython cross-build), per GOAL.

## What I'm doing meanwhile (zero-disk)

Dispatched a read-only recon fleet mapping the exact build closure, host-tool gaps, and
minimal bmesh-gtest link plan, so the build wave starts the moment disk clears. No builds
run until free space ≥10 GiB.
