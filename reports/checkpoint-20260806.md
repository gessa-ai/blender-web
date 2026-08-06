<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Checkpoint — 2026-08-06 (5th; delta since HANDOFF-20260805.md)

_Cadence report per GOAL.md "Budget and cadence" (every $250: progress, burn, blockers, projection).
Outcome-first with receipts. Every number below is cited to a file on disk; failures and deferrals
carry equal weight._

## Headline

The handoff's state was **"one draw-validation error from first frames"** (mid-M3,
HANDOFF-20260805.md). That gap is closed and then some. **M3 WEBGPU BACKEND is promised** — the m3
gate scope is installed and ran **5/5 GREEN** (commit `52ec8a5`; driver reconcile 2026-08-06T11:55Z,
progress.txt), pinning the 158-test census at **148 PASS / 8 FAIL / 2 CRASH** (all characterized,
`notes/gpu-gate-census.md`) and static_shaders at **956/973** (progress r17–r20). **Blender's real UI
now renders upright and interactive in a Chrome tab** — Quick Setup splash, viewport-header menus,
toolbar icons, panels, mouse+Escape driving the UI, zero Dawn validation errors in the render path
(r16 first pixels `536a8e6`, r17 upright `f2291fc`, r18 UI-composite `6605e98`; evidence under
`platform_web/shell/evidence/`). The last identified M4-cube blocker — a residual depth
Float-vs-UnfilterableFloat sampleType mismatch that left the 3D viewport interior **~92% black** —
had its fix land this round: **patch 0103 (r20, commit `d9e90f0`)** builds explicit pipeline layouts
from the interface map, holds the native gate EXACTLY (148/158 + 956/973, zero regressions) — **but
the in-browser cube composite and the M4 golden idiff are NOT yet driver-verified.** The cube is now a
verification step, not a code fix, from the `M4_FIRST_PIXELS` promise.

## Milestone bar (verbatim from reports/dashboard.md)

**4 DONE · 1 IN-PROGRESS · 4 pending**

| Milestone | Status | Receipt |
|---|---|---|
| **M0** TOOLCHAIN + ORACLE | DONE | results/m0.json 6/6 @ 2026-08-06T11:40:14Z |
| **M1** CORE BOOTS + FREE ORACLE | DONE | commit ba34e75 M1.12 wasm-side: corpus state-dump parity 9/9 byte-identical — closes M1_CORE_BOOTS; results/m1.json 5/5 |
| **M2** DEPS + PYTHON BOOTS | DONE | commit 7976b84 harness v1.4: m2b tier-(b) scope — M2_DEPS_PYTHON gate green; results/m2b.json 4/4 |
| **M3** WEBGPU BACKEND (Dawn) | DONE | commit 52ec8a5 harness v1.5: m3 gate scope installed + first green run — M3_GPU_BACKEND receipts |
| **M4** FIRST PIXELS IN A TAB | IN-PROGRESS | commit 536a8e6 M4 gpu round 16: Blender's UI renders in a browser tab — promise tag not yet issued |
| **M5** INTERACTIVE PARITY | pending | awaiting M5_INTERACTIVE |
| **M6** RENDER PARITY | pending | awaiting M6_RENDER |
| **M7** FILES + PIPELINE | pending | awaiting M7_FILES |
| **M8** LAUNCH GATE | pending | awaiting M8_LAUNCH_GATE |

_(dashboard.md was regenerated at HEAD `52ec8a5`, so its static_shaders cell reads 951/973 — one
regen behind; progress.txt r17–r20 record the current **956/973**. Census 148/158 matches.)_

## Receipts (all green suites + first-pixels evidence)

| What | Count | Source |
|---|---|---|
| m0 toolchain/oracle | 6/6 | `ledger/results/m0.json` @ 2026-08-06T11:40:14Z |
| m1 core-boot | 5/5 | `ledger/results/m1.json` @ 2026-08-06T11:40:22Z |
| m1 › blenlib gtests | 1655/1665 (10 characterized: 9 fenv-defer + 1 host-chdir) | `ledger/results/m1.json` |
| m1 › bmesh_core gtests | 1/1 (full upstream suite) | `ledger/results/m1.json` |
| m1 › corpus state-dump parity | 9/9 (sha256==MANIFEST, tolerance 0) | `ledger/results/m1.json` |
| m2b tier-(b) | 4/4 | `ledger/results/m2b.json` @ 2026-08-06T11:42:43Z |
| m2b › CORE must-pass suites | 64/64 | `ledger/results/m2b.json` |
| m3 gate scope | 5/5 GREEN | commit `52ec8a5`; progress.txt driver 11:55Z |
| gpu gate census (native Dawn) | 148/158 (8 FAIL / 2 CRASH, all characterized) | `notes/gpu-gate-census.md` |
| gpu static_shaders compile | 956/973 (17 non-pass = pre-characterized deferrals) | progress.txt r20 (`d9e90f0`) |
| dependencies harvested | 27 wasm_built archives (reconciled) | `reports/dashboard.md` / `ledger/deps.json` |
| deferral registry | 23 entries (deferred 15 · by-goal 5 · detector-active 1 · prototype-proven 1 · resolved 1) | `reports/dashboard.md` (c) |
| first pixels — UI splash | `platform_web/shell/evidence/m4-first-ui-pixels-quicksetup-splash.png` (1800×1169) + `-transcript.md` | r16 `536a8e6` |
| first pixels — UI upright | `platform_web/shell/evidence/m4-ui-upright-r17.jpg` + `.md` | r17 `f2291fc` |
| first pixels — UI composite | `platform_web/shell/evidence/m4-ui-upright-r18-viewport-dark.png` (900×585) | r18 `6605e98` |

## Risk register NOW (genuinely open)

- **M4 cube residual (the live front).** Explicit-layout fix landed native-green (patch 0103 /
  `d9e90f0`, census 148/158 + 956/973 held, zero regressions), but the **in-tab cube composite is not
  yet confirmed**: r19's live capture was blocked by a browser-pane canvas staying 1280×720 vs the
  1800×1169-configured surface (not a render bug), and the M4 golden idiff has not been run. First
  composite is now deterministic (28% non-black at boot, 0 input events; r19 `0412052`). This is
  verification-open, not code-open.
- **M5–M8 scope** — real weeks of work, but the prep is banked (all pre-M4, verified):
  M5 tier-(c) sessions **8/8** authored + cross-run deterministic (`sandbox/m5-prep`, `eda1608`);
  M6 render goldens **72/77** oracle (5 = validated adapter deltas incl. 2 upstream-BLOCKLIST-verbatim;
  `1fe4360`) + Cycles-CPU **compiles clean** for wasm32 (`96e3a0f`); M7 OPFS/WasmFS **proven in a tab**
  (`b9611cf`) with open/save operators already round-tripping; the **-O2 / release-link (opt) probe is
  in flight** (progress.txt driver 12:50Z "release-link probe", 18:50Z "still building", 14:05Z
  "opt-link finishing").
- **Two HUMAN decisions pending** (dashboard-only until a gate needs them):
  1. **Public brand name** — D-7 (`notes/decisions.md:106-119`): "blender-web" is a local working name
     only; "Pick the public brand before anything ships. LAUNCH.md gates it."
  2. **wasm64 window** — ADR-004: the technical choice is *resolved* (wasm64, probe evidence `b75ef36`,
     no perf tax, toolchain clean incl. emdawnwebgpu); the **timing/go-ahead** for the multi-day
     all-deps rebuild — scheduled "likely post-M4, pre-launch" — is the human call.

## Projection (honest ranges, no compression)

- **M4 FIRST PIXELS — days.** The last-identified code blocker (explicit pipeline layouts, patch 0103
  / `d9e90f0`) has landed native-green. Remaining before the promise: (a) re-capture the in-tab cube
  composite on the relinked windowed build (r19's live capture was blocked by a browser-pane
  1280×720-vs-1800×1169 canvas-size mismatch, not a render bug), (b) idiff the captured frame against
  the native cube golden (`sandbox/m4-goldens/`, `D_fullwindow_splash`, thresholds 0.016 /
  failpercent 1). Both are verification, not development. **Days.**
- **M5–M8 — weeks, not days, and not compressible.** M5 INTERACTIVE: the 8/8 tier-(c) event-simulate
  sessions are authored and cross-run deterministic (`sandbox/m5-prep`, `eda1608`); the wasm half is
  that runner re-pointed onto the windowed tree once M4's loop is stable, plus Playwright canvas smoke.
  M6 RENDER: 77 goldens staged with oracle 72/77 and upstream-verbatim thresholds (`1fe4360`),
  Cycles-CPU compiles clean for wasm32 (`96e3a0f`); the wasm half is a WebGPU offscreen render→PNG path
  + idiff. M7 FILES: open/save operators already round-trip and OPFS/WasmFS is proven in a tab
  (`b9611cf`); M7 is the persistent backend + JS byte-bridge + staged loading. M8 LAUNCH: the
  30-second bar (LAUNCH.md). Gating human inputs sit on this path (brand, wasm64 window — above), so
  the honest figure is **weeks across M5–M8**, not a single-milestone sprint.

## Burn

**Tracked wrapper-side, unavailable in-repo.** (The cost-per-iteration ledger is wrapper-side per
GOAL.md; this worker cannot read it and does not invent figures. CI minutes are budget too — GOAL.md.)

## Infrastructure note — interruptions survived, zero work lost

This checkpoint window (`fd007d8..HEAD`, 69 commits) survived **at least 3 kill/restart recoveries**
with **zero work lost**: git commits `693a711` ("session-limit recovery") and `81734fd` (audit
"committed by driver after session-limit kill"); progress.txt logs a restart recovery at 11:07Z and a
session-limit recovery at 21:40Z on 2026-08-05 ("pulse-check clean … no lost landings"). The window
itself opens on the spend-limit that produced `reports/HANDOFF-20260805.md` (whose §Operating model
records ~8 such interruptions in the prior session, also zero lost). The mechanism holding: one
verified unit per commit, driver pulse-check on every resume, upstream series never restored mid-push.
