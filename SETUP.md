# SETUP.md — Wiring the port factory (Track A′) in Claude Code

How GOAL.md runs as a self-driving loop, on your machine and on GitHub. Human does the nine one-time actions in §7; the loop does everything else.

## 1. Repo scaffold

```
<port-repo>/
├─ GOAL.md                    # driver prompt (Track A′)
├─ fix_plan.md                # backlog (agent edits)
├─ upstream/                  # Blender v5.2.0 source + lib/ deps  [READ-ONLY, submodule or vendored]
├─ patches/                   # the port's changes to upstream, as patch series
├─ platform_web/              # GHOST-web, main loop, OPFS/FSA glue, shell page
├─ oracle/                    # native Blender 5.2.0 Docker + bpy.sh + rna-dump  [PROTECTED]
├─ harness/                   # run.sh/status.sh, state-dump differ, idiff gate, Playwright e2e  [PROTECTED]
├─ tests/golden/              # oracle-rendered references (stored in R2, fetched by hash)  [PROTECTED]
├─ ledger/                    # progress.txt, deps.json, deferred.json, suite results
├─ notes/                     # porting-patterns.md (the stdlib), ADRs, stuck reports
├─ reports/                   # checkpoints + public dashboard source
├─ LICENSES/ NOTICE PROVENANCE.md REUSE.toml THIRD-PARTY.md LAUNCH.md
└─ .claude/  (settings.json + hooks/)
```

Note: the new GPU backend lives inside the source tree the build sees (`source/blender/gpu/webgpu/` via `patches/` or an overlay dir) — GOAL.md's "standing architecture decisions" govern.

## 2. Guardrail hooks (`.claude/settings.json`) — unchanged mechanism, updated paths

PreToolUse deny-writes for `^(upstream|oracle|harness|tests/golden)/` and `ledger/*.json` result fields; Stop-gate runs the current milestone's harness scope (plus a holdout suite) and blocks stopping while red (always honoring `stop_hook_active`); PostCompact reinjects "re-read GOAL.md". Same JSON shapes as kit v1.

## 3. Drivers

**A — bash Ralph loop (recommended):** same loop as kit v1 (`cat GOAL.md | claude -p --max-turns 80 --output-format json`), cost-capped, promise-tag exit on `M8_LAUNCH_GATE`. Fresh context per iteration; GOAL.md + ledger + git are the memory.
**B — in-app:** `/ralph-loop` (official plugin), `/loop` (built-in), or `/goal:goal` (chrischabot plugin) with `--completion-promise M8_LAUNCH_GATE --max-iterations 500`.
**C — nightly bounded cron/CI runs** merging one small PR per night.

**Autonomy posture (from the unattended-runs research):** prefer **auto mode** over raw `--dangerously-skip-permissions` — it classifier-gates risky actions, blocks destroy/exfiltrate classes, and has built-in escalation (3 consecutive or 20 total denials stops the worker; in headless it terminates, which your watchdog catches). Run each worker in a container with **default-deny egress** (allowlist: Anthropic API, emsdk, package registries) and no host keychain or unrelated credentials — every published agent disaster was access control, not model failure. Set `DISABLE_AUTOUPDATER=1` so a Claude Code upgrade never lands mid-run (resuming after an upgrade reprocesses the whole session uncached).

**Model routing:** driver/planner on Fable or Opus; workers (worktree loops per area: `build-deps`, `python-wasm`, `gpu-backend`, `ghost-web`, `harness`, `compliance`) on cheaper models. Planner never implements; workers never plan — this is the documented ~8x cost lever. Keep every worker's prompt byte-identical (machine-specific paths/timestamps in prompts silently defeat prompt-cache sharing). For "as fast as possible," run on Console/API billing — Max subscriptions cap weekly compute and will pace this to a slow burn. Claude Code **Agent Teams** (research preview) natively provides the shared-task-list + team-lead + worktree pattern if you prefer it over hand-rolled worker loops.

## 3b. Watchdogs & notifications (zero check-in)

- **Liveness:** a launchd/cron job checks a heartbeat file AND `git log -1 --format=%ct` — no commit in N hours ⇒ kill and restart the worker with fresh context (it re-orients from GOAL.md + ledger). `claude-auto-retry`-style backoff with jitter for 429/529 windows.
- **Notifications:** Stop/Notification hooks → ntfy.sh (or Slack webhook). The loop pings on milestone completion (FYI) and pages only on GOAL.md's five conditions (budget, gate decision, 5x wall, security escalation, unrecoverable worker). Everything else lands on the dashboard.
- **Observability:** enable Claude Code's OpenTelemetry export — cache read:write ratio and per-session cost are the two numbers that catch silent money leaks.
- **Weekly human ritual (~15 min):** read the Pages dashboard, skim the latest checkpoint report, unstick any 5x wall, adjust the next milestone's plan if needed. Never read transcripts.

## 4. CI (GitHub Actions) — the QA facts baked in

- **Build job:** pinned emsdk container (record exact version; ≥4.0.10 for the emdawnwebgpu port); TWO caches persisted — `EM_CACHE` (Emscripten sysroot) and ccache/sccache object cache via the `ccache emcc` wrapper; dev links `-O0/-O1` with no LTO (LTO alone is 50–80% of link time — release builds only); full cached wasm build must stay under ~30 min. Artifacts: the web bundle.
- **Oracle job:** pinned Blender 5.2.0 tarball from download.blender.org (+ `libgl1 libxrender1 libxi6 libxkbcommon0`), runs `blender -b` — **Cycles CPU renders are the reliable oracle**; EEVEE references only via `xvfb-run` + llvmpipe with pinned Mesa in the container.
- **Web-render job:** headless Chrome new-mode with explicit flags — `--headless=new --enable-unsafe-webgpu --enable-unsafe-swiftshader --use-angle=vulkan --enable-features=Vulkan --enable-dawn-features=allow_unsafe_apis,disable_adapter_blocklist` (Chrome 137+ removed the SwiftShader auto-fallback; the flag is mandatory). Pin the Chrome + SwiftShader container image; compare via texture readback, not canvas snapshots; Playwright `toHaveScreenshot` with `maxDiffPixelRatio: 0.01`, `threshold: 0.2`, baselines generated inside the official Playwright image. Real-GPU checks (optional): GitHub `gpu-t4-4-core` runners, ~$0.07/min.
- **Goldens storage:** NOT GitHub LFS (1 GB free bandwidth/month, then $0.0875/GiB — CI would blow through it; Blender itself avoids GitHub LFS). Use **Cloudflare R2** (zero egress), fetched by content hash in CI.
- **Repo autonomy:** protected `main` + required checks; agent works on branches (claude-code-action can push branches/PRs but cannot merge); merges happen via repo-level **auto-merge on green** (`gh pr merge --auto --squash`); check names must exactly match. Dashboard + demo deploy via `actions/deploy-pages`; live conformance badge via a shields.io endpoint JSON written each run.
- **Compliance gate:** `reuse lint` + license scan of deps (fail on non-GPL-compatible).

## 5. Hosting the demo

WASM pthreads ⇒ SharedArrayBuffer ⇒ **COOP/COEP headers required**. GitHub Pages cannot set headers — host the demo on **Cloudflare Pages** with a `_headers` file (`Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`). Keep the dashboard on GitHub Pages if you like (no SAB needed there). The coi-serviceworker hack is the fallback only.

## 6. What to watch (failure modes, updated)

1. Parity theater / reward hacking → protected paths, holdout suite in the Stop gate, 25-iteration audit pass.
2. Premature victory → promise tags only count with harness receipts; Stop gate re-checks.
3. Governance decay after compaction → PostCompact reinjection; bash driver avoids it via fresh context.
4. **Toolchain grind spirals** (the historical Blender-wasm killer): link-time and build-cache discipline are tracked work items; recurring walls escalate to `reports/` after 5 hits instead of silently burning budget.
5. Overbaking/scope drift → iteration caps, one-task discipline, deferral registry instead of heroics.

## 7. The nine one-time human actions (everything else is the loop's job)

1. Create the GitHub repo/org (name per LAUNCH.md rules) and grant the agent access.
2. Install the Claude GitHub App + add `ANTHROPIC_API_KEY` as a secret (Console billing recommended).
3. Enable GitHub Pages (Source = GitHub Actions) for the dashboard.
4. Branch protection on `main` + enable "Allow auto-merge" + workflow Read-and-write + "Actions can create/approve PRs".
5. Billing: Actions spending limit; set the LFS budget to $0-and-unused (we don't use it) or a guard value.
6. (Optional) GPU runner group if you want real-hardware render checks.
7. Create the Cloudflare R2 bucket for goldens + add its credentials as secrets.
8. Create the Cloudflare Pages project for the demo (connect repo, add `_headers`).
9. (Later, if ever needed) a fine-grained PAT for cross-repo ops.

Then: run the loop (driver §3), watch `reports/`, and hold the X post until LAUNCH.md is green.
