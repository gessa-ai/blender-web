<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M6-prep — render-parity oracle side, staged early (OUTCOME)

Outcome-first index for the M6 render-parity prep. GOAL.md M6 (tier-c): workbench +
EEVEE regression subsets within Blender's OWN thresholds on the pinned adapter
(justified blacklist allowed) + Cycles-CPU small scenes. This stages the ORACLE
half — ready goldens + a working comparator — so M6 opens with a green oracle
baseline instead of authoring on the critical path (the M5-prep pattern).

## Verdict: 77 tests staged, oracle 72/77 PASS, comparator + blacklist proven, 3×2 deterministic

| suite | tests staged | oracle PASS | engine oracle | ref dir |
|---|---|---|---|---|
| Workbench | 20 | 19 | native macOS **Metal** (`--gpu-backend metal`, headless) | `workbench_renders` |
| EEVEE | 30 | 26 | native macOS **Metal** (headless) | `eevee_renders` |
| Cycles-CPU | 27 | 27 | **CPU** (`--cycles-device CPU`, no GPU) | `cycles_renders` |

All against Blender's OWN committed references, using Blender's OWN pinned oiiotool
idiff (exit-code = verdict). Oracle binary is **at the exact pin** — it self-reports
`Blender 5.2.0 LTS (hash fbe6228777e7)`, so this is a pin-accurate baseline (resolves
the m5-prep "pin-vs-5.2.0-release" caveat: the installed oracle *is* the pin).

### The 5 oracle fails are adapter deltas, not comparator bugs — 2 are VERBATIM in upstream's blocklist

| test | engine | max err / over | status |
|---|---|---|---|
| `raycast/raycast_bump` | eevee | 0.714 / 17.7% | **in upstream EEVEE `BLOCKLIST`** (eevee_render_tests.py:44 — "platform-dependent noise, fast-math") |
| `principled_bsdf/principled_bsdf_thinfilm_transmission` | eevee | 0.192 / 34.5% | **in upstream EEVEE `BLOCKLIST`** (eevee_render_tests.py:35 — "GBuffer IOR encoding differs between platforms") |
| `transparency/transparency_dithered` | eevee | 0.055 / 8.62% | dithered-transparency noise pattern is per-adapter (same class as upstream `BLOCKLIST_METAL`) |
| `transparency/transparency_blended` | eevee | 0.039 / 0.574%* | blended OIT ordering, marginal adapter delta (*over threshold at 4/255, not 1%) |
| `workbench/aa-single-pass` | workbench | 0.294 / 1.01% | single-pass AA sample pattern, marginal (1.01% vs 1% failpercent — a hair over) |

That the two upstream-blocklisted scenes fail here is **positive validation**: the
comparator faithfully reproduces Blender's own known adapter deltas. Per GOAL tier-c
("justified per-test blacklist exactly as native Blender maintains") these are exactly
the adjudication set — but the blacklist is **committed empty** (prep scope), because
the relevant adapter for M6 is the **WebGPU/CI adapter**, not this Metal oracle. M6
re-runs on the pinned CI adapter and blacklists per THAT adapter. A ready candidate
list (the 5 above, 2 citing upstream lines) is here for M6 to activate as justified.

## Thresholds — Blender's OWN, transcribed verbatim (no weakening)

Exact idiff invocation, byte-for-byte from `upstream/tests/python/modules/render_report.py:138-145`:
```
oiiotool <golden> <render> --fail <fail_threshold> --failpercent <fail_percent> --diff   # exit 0 = within tolerance
```
Per-engine/-dir `<fail_threshold>/<fail_percent>` (source cited in `suite_plan.tsv`):
- **Workbench**: `0.016 / 1` — render_report default (`render_report.py:287-288`).
- **EEVEE**: `4/255=0.0156862745 / 0.08` — `eevee_render_tests.py main` (`set_fail_threshold(4.0/255)`, `set_fail_percent(0.08)`); the NVIDIA-OpenGL tightening + camera/image_colorspace/displacement per-dir overrides do NOT apply to my dirs.
- **Cycles**: `0.016 / 1` default; **`colorspace → 0.05 / 1`** (`cycles_render_tests.py main`). principled_bsdf's 0.06 override is OSL-only (we run non-OSL CPU) → default.

## EEVEE oracle verdict: the native macOS Metal host binary, NOT a Linux Docker

EEVEE needs a GPU. On macOS, Blender's GPU backends run **headless under `--background`**
via Metal offscreen (no window server needed — verified: EEVEE renders a real 128×128
PNG in ~7 s/frame, exit 0). So the correct EEVEE oracle is the **host native binary on
`--gpu-backend metal`**, mirroring how Blender CI generates GPU references on real
adapters (references are per-adapter). There is **no oracle Docker on this host** (only
`oracle/blender-5.2.0/Blender.app`), and a Linux headless-GL Docker would need EGL/weston
anyway — the Metal host is strictly simpler and pin-accurate.

**ADAPTER PIN (tier-c requires it):** oracle renders were produced on **Apple Metal**
(`oracle/blender-5.2.0` on this arm64 host). This is the oracle-side adapter; the wasm
side will be a **WebGPU adapter** (Dawn→Metal in-tab). Tier-c is explicitly not
bit-exact-across-GPU — the golden set + thresholds carry across; the per-test blacklist
is re-derived on the actual CI WebGPU adapter at M6.

## LFS accounting — 11.1 MB pulled (done), full suite still one pre-approved (<200 MB) pull

All render inputs + references are LFS pointers (131 B stubs) pointing at
`projects.blender.org/…/info/lfs`. `git lfs pull` works from there (git-lfs 3.7.1).
**Pulled (materialized in `upstream/`, NOT committed):** workbench, colorspace,
transparency, shadow, raycast, principled_bsdf = **11.1 MB** (inputs+refs). Command:
```
( cd upstream && git lfs pull --include="tests/files/render/{workbench,colorspace,transparency,shadow,raycast,principled_bsdf}/**" )
```
**To extend to the FULL CMake render suite** (accurate from pointer sizes, see the
per-dir table method): base `render_tests` inputs ≈ **94 MB** (shared by EEVEE +
Cycles-CPU), + EEVEE refs ≈ 8 MB + Cycles refs ≈ 9 MB; full workbench suite ≈ 43 MB
(inputs overlap render dirs). **Whole M6 render corpus ≈ 115–120 MB total** — under the
200 MB gate, so even the complete suite is a single pre-approved pull. Extending is
mechanical: add dirs to `suite_plan.tsv`, `git lfs pull` them, `stage_goldens.sh`, run.

## Deliverable layout (`sandbox/m6-prep/`)

- `goldens/<engine>/<dir>/<test>.png` — **77 staged references** (1.8 MB, Blender's own
  test references, Apache-2.0 upstream test data; committed so M6 needs no LFS pull for goldens).
- `manifest.tsv` — per-test map `engine · dir · test · input_blend · golden · fail_threshold · fail_percent`.
- `suite_plan.tsv` — `engine · dir · threshold · failpercent` (the thresholds' upstream source cited inline).
- `run_oracle_renders.sh` — the comparator (render on oracle → exact upstream idiff → exit-code verdict; `--engine`, `--filter`, `--determinism`; reads blacklist).
- `stage_goldens.sh` — idempotent golden-copier + manifest writer.
- `blacklist.txt` — the per-test blacklist mechanism, **committed empty**; format documented; SKIP path proven (a temp `raycast_bump` entry → `SKIP`, restored empty).
- `.gitignore` — `oracle_renders/` (regenerable SUT output) + `results/` + `*.log` are NOT committed.

## Exact runner invocation

```
bash sandbox/m6-prep/run_oracle_renders.sh                      # all 77, PASS/FAIL/SKIP + tally
bash sandbox/m6-prep/run_oracle_renders.sh --engine cycles      # one engine
bash sandbox/m6-prep/run_oracle_renders.sh --determinism        # 3 samples ×2
```
Per test the oracle is launched with the VERBATIM upstream arg vector, e.g. workbench:
`Blender --background --factory-startup --enable-autoexec --debug-memory --console-crash-handler --debug-exit-on-error --gpu-backend metal <blend> -E BLENDER_WORKBENCH -P upstream/tests/python/workbench_render_tests.py -o <out> -F PNG -f 1`
(EEVEE: `-E BLENDER_EEVEE`; Cycles: drop `--gpu-backend`, append `-- --cycles-device CPU`).

## Determinism — 3 samples ×2, all within Blender's 0.016/1 threshold

`--determinism` renders one test/engine twice: Cycles-CPU + EEVEE frequently
**byte-identical**; all three **always threshold-identical (0.016/1)** across two
independent runs (receipt: `results/determinism.txt`, `DET_ALL_PASS`). Run-to-run PNG
bytes can differ sub-threshold (multi-thread tiling / metadata) — threshold-identical is
the correct tier-c gate and what the runner asserts.

## What the WASM side needs (blocks on M6 GPU render path; reuses the m2b pattern)

The oracle half is ready. The wasm half needs, from M6:
1. **A WebGPU render path** for `-E BLENDER_WORKBENCH` / `-E BLENDER_EEVEE` producing a
   PNG (`-o … -F PNG -f 1`) under the node/browser wasm build — i.e. M3/M4 GPU backend
   driving an offscreen render, not just the viewport. Cycles-CPU needs no GPU (should
   come first — pure CPU, deterministic).
2. **The exit-code-primary comparator reused as-is**: point the runner's `render()` at
   `node build-wasm/bin/blender.js …` (same arg vector) writing a PNG, then the SAME
   `oiiotool <golden> <wasm.png> --fail <thr> --failpercent <fp> --diff` — exit code is
   the verdict, exactly like tier-b's m2b exit-code gate. No golden re-authoring.
3. **Per-test blacklist re-derived on the pinned CI WebGPU adapter** (Dawn adapter
   string recorded), starting from the 5-entry candidate set above (2 already
   upstream-blocklisted). Cross-adapter deltas are expected and GOAL-sanctioned.

**Boundary note:** staged goldens stay under `sandbox/m6-prep/`. Installing into
`tests/golden/` + wiring `harness/run.sh --scope m6` is a driver-at-boundary action —
NOT done here. Goldens are Blender's Apache-2.0 test references; REUSE coverage for the
binary PNGs is a boundary concern for the driver (as with `sandbox/m4-goldens/`).
