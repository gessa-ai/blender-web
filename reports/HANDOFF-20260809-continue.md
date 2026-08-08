<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# HANDOFF — 2026-08-09 — continue the M4/M5/M6/M8 close-out

You are the driver for **blender-web**: a faithful port of pinned Blender 5.2 LTS
(commit `fbe6228777e7`) to the browser via Emscripten/WebAssembly with a
hand-written WebGPU backend. Repo: `/Users/paws/blender-web` (separate from any
other repo you may see referenced in tool context — do not touch other repos).
Branch: `agent/m2.5-python-boot`. This is a **shared checkout** — other lanes may
have uncommitted WIP in the working tree at any time.

**Read in this order before doing anything else:** `GOAL.md`, `notes/decisions.md`
(D-1..D-9, especially **D-9** — it scopes the M4 gate), `fix_plan.md`, the last
~80 lines of `ledger/progress.txt`, `ledger/deferred.json`. Then read every note
named in "State" below before touching its area — each is a completed
investigation; do not re-derive what they already proved.

## Why you're picking this up

The previous driver session hit **the weekly API limit** (resets 2026-08-12
15:00 America/New_York) while two subagents were mid-flight. One (r38) had
already landed a clean commit before dying; the other (r40) died with **nothing
committed** — its investigation is lost and must be redone from scratch. This
handoff exists so you can resume without re-reading the whole session.

**Standing instruction from the human (KA), repeated across this entire program:
"parallelize with as many subagents as possible," "don't stop," "continue until
we finish off the entirety of Blender/OSS per the docs/ledger/plan/spec."** Keep
driving with concurrent subagent lanes exactly as this document illustrates,
verify every lane's claims yourself before trusting them (this has caught real
false positives — see the r34→r36 correction chain below), and produce
**screenshots as proof** at every milestone, not just numbers.

## Standing rules (binding, do not relax any of these)

- `upstream/` is a pinned, otherwise-read-only checkout at `fbe6228777e7`; ALL
  changes to it land as numbered patches in `patches/` (reconstruct the
  pre-image, `diff -u`, hand-build `diff --git a/<rel> b/<rel>` headers, verify
  `git apply --check --reverse` inside `upstream/`), with a rationale comment
  appended to `patches/series`. Never edit upstream/ directly and call it done —
  it must exist as a `.patch` file too (upstream/ itself is untracked-by-outer-git
  and can vanish; the patch is the durable artifact).
- **Never** modify `harness/`, `oracle/`, `tests/golden/`, or ledger pass-flags.
  `harness/` is under `.claude/harness.lock` — even a one-line fix to its
  `EXPECT_NONPASS` map (see "Human-owed item" below) needs the human, not you.
- Census bar (native GPU test suite): run via
  `/opt/homebrew/bin/bash harness/run.sh` (macOS `/bin/bash` 3.2 cannot parse
  it — this is NOT a harness bug). It is **RUN-ONLY**: after any `upstream/gpu`
  source change you MUST rebuild `build-native-gpu` first. **Current TRUE bar:
  149 PASS / 7 FAIL / 2 CRASH (of 158 GPUWebGPUTest) + static_shaders 956/973.**
  The harness's own `EXPECT_NONPASS` map still shows RED for one test that now
  passes (see below) — that specific RED is known; any *other* regression means
  stop and report.
- `export EMSDK_PYTHON=/Users/paws/blender-web/tools/emsdk/python/3.13.3_64bit/bin/python3`
  before any cmake rerun. Serialize ALL ninja builds through
  `scripts/ninja-locked.sh` (concurrent lanes contend on this — expect waits).
- Verification: headed node-Playwright with the **bundled** Chromium,
  `NODE_PATH=/Users/paws/plushly/game-platform/node_modules` — **never** an
  in-app/hidden browser pane (rAF throttling gives false blacks there). Shell
  hooks: `?pyexpr=` (urlencoded, runs pre-`WM_main`), `?args=`, `?gate=WxH`
  (forces DPR 1), hidden `#state` contains `"main loop (WM_main)"` when up.
  `os.write(2, ...)` reaches the browser console; **Python `print()` does not**.
  The **keepalive** (commit `ef64e8f`, default ON) means rigs no longer need a
  `bpy.app.timers` kick to stay alive at idle — but a **fresh boot with zero
  input still composites nothing until the first mouse event** (a known,
  separately-tracked GHOST-web blocker, P2 #6) — so every capture rig should do
  a neutral mouse move over the canvas before waiting-and-shooting. See
  `/private/tmp/claude-501/-Users-paws-plushly-game-platform/d7d2c564-be12-4583-a99d-c860260f9c2a/scratchpad/gate-splash2.js`
  for the working pattern (or just `platform_web` evidence rigs already committed).
- File ownership when running concurrent lanes: assign each lane a disjoint file
  set (usually one `.cc`/`.hh` pair each in `gpu/webgpu/`) and a unique port
  (8123/8124/8126/8127/8128/8129/8130 have all been used this program — pick free
  ones and say so in the brief). `git status --short` before dispatching to see
  what's currently dirty and by whom.
- Commit discipline: never `git add -A`; commit ONLY the files your own lane/you
  touched. Trailers **exactly**: `Assisted-by: Claude (worker)` (subagents) or
  `Assisted-by: Claude (driver)` (you, the orchestrating session) +
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. **Zero em dashes
  (U+2014) in any authored/committed text** — raw pasted tool/console output in
  evidence logs is exempt (it's data, not prose), but notes/commit
  messages/ledger entries must be clean. SPDX headers on new files. PNG evidence
  gets a `.license` sidecar (two lines: `SPDX-FileCopyrightText: 2026
  blender-web contributors` / `SPDX-License-Identifier: CC0-1.0`).
- Ledger: `ledger/progress.txt` is **append-only** — never edit prior lines.
  Every verified lane result gets a `driver YYYY-MM-DDTHH:MMZ ... VERIFIED
  (commit): ...` line from you, in your own voice, stating what you personally
  checked (not just what the lane claimed).
- **Verify, don't trust.** This program has had real false positives from
  subagents that reasoned from indirect evidence instead of direct probes (see
  r34's asset-shelf claim, falsified by r36 with a direct state probe). Before
  ledgering any lane's claim: read its commit diff, open at least one evidence
  image yourself, and re-run its stated repro command if cheap.

## State — what is DONE (do not re-litigate, do not re-run any listed elimination)

- **M4 solid-cube defect: FIXED** (patch 0118, r33, commit `68e2bce`). Root
  cause: the backend never emitted `SetStencilReference`; the workbench opaque
  prepass tests `NEQUAL @ 0xFF`, so every fragment was rejected as a *valid*
  stencil op (zero GPU errors for 4 rounds because there was nothing invalid).
- **Workbench normal-format flip: FIXED** (patch 0119, r37, commit `d0f48c7`).
  `GPU_COMP_I10` (signed packed normals) was mapped to the *unsigned*
  `Unorm10_10_10_2` (WebGPU has no signed snorm10-10-10-2); fixed by transcoding
  to `Snorm8x4` at upload. **This raised the census bar**: a previously-deferred
  native test now passes (148→149 PASS). Deferral `gpu-comp-i10-vertex-format`
  is CLOSED in `ledger/deferred.json`.
- **Window-direct viewport/scissor: FIXED** (patch 0121, r39, commit `63b010b`).
  The WebGPU draw paths never applied `SetViewport`/`SetScissorRect` at all
  (Vulkan does); region-sized offscreens hid it, but window-direct overlay/paint
  draws (timeline playhead, a stray "blue spike" since r27, a viewport bottom
  band r34 had misattributed to a visible asset shelf) all landed off-target.
  **One patch fixed all three.** Full-window parity: **11.0% → 2.19% failing**
  (`sandbox/m4-fullscreen-parity`, verbatim 0.016/failpercent 1 comparator,
  never touch these thresholds).
- **M6 readback bridge: LANDED** (patch 0125, r35, commit `423cbf4`). Extracted
  the first real browser-side F12 render pixels ever. **Corrected the entire M6
  premise**: readback was never the blocker. Real blockers, GPU-proven:
  (1) workbench F12 render path has a BindGroup entry-count mismatch on every
  lighting permutation except the factory default (18/20 workbench suite scenes
  fail); (2) EEVEE-Next is blocked wholesale by a pre-existing registered
  deferral (`vertex-stage-rw-storage`) — pipelines never build (30/30 scenes).
  Full honest 50-row table: `notes/m6-gpu-suite-real-scores.md`.
- **Staged deploy loading: LANDED** (commit `d02c911`). Bundle boots on a
  critical stage-0 payload, streams the rest after first pixels. 4G cold
  time-to-first-pixels: 41.3s → 27.8s (−33%). Deploy-bundle-only change, no
  source/build-tree edits. `notes/m8-staged-deploy.md`.
- **M8 stability: PASSED.** 30-min soak (heap flat, 0 GPU errors, 0 stalls) +
  name-section strip (−1.28 MB brotli). `notes/m8-soak-and-namestrip.md`.
- **GHOST idle-stall keepalive: LANDED** (commit `ef64e8f`). Loop no longer
  needs a Python redraw kick to stay alive at idle, without idle GPU burn.
- **wasm-split (wire-size) feasibility: RESEARCHED, GO on mechanism, bar
  MISSED.** Emscripten `SPLIT_MODULE` works with zero JSPI under this build's
  full constraint set (proven in a sandbox prototype); subsystem-level cold-cuts
  only reach ~19.4 MB brotli vs the 15 MB bar. Registered deferral
  `m8-wasm-15mb-bar` (status `partial`) names the next lever: function-level
  profile-driven splitting via emcc's instrument flow — **unmeasured, not yet
  attempted.** `notes/m8-wasm-split-feasibility.md`.
- **python-trim "dis.py missing" claim: REFUTED**, not a real defect (a stale
  pre-fix binary was A/B-tested by mistake). No action needed; see
  `notes/python-trim-restore.md`.
- **D-9 (decisions.md): the M4 gate promise is measured against GOAL.md's own
  text**, not the full-window screenshot instrument (which has a proven ~3.5%
  irreducible cross-renderer glyph-AA floor). Gate = (a) viewport interior vs
  its golden, (b) splash vs its golden, both at the *verbatim* comparator
  thresholds, `sandbox/m4-golden-prep/compare_m4.sh`; (c) a qualitative chrome
  checklist. The full-window number stays a tracked regression tripwire only.

## State — what is IN PROGRESS or QUEUED (your actual work)

Priority order (top = do first; each has a clean, isolated fence):

### 1. Respawn r40 — workbench F12 BindGroup entry-count mismatch (LOST WORK, redo from scratch)

The lane that was investigating this died with **zero commits** — nothing to
resume from. Re-brief from scratch. Context: `notes/m6-gpu-suite-real-scores.md`
documents the symptom (6-vs-7, 6-vs-10, 1-vs-4 entry mismatches on workbench F12
lighting permutations other than the factory default — studio/flat/matcap/dof/
x-ray). The factory-cube F12 render binds correctly; the *interactive viewport*
renders these same permutations fine — so the bug is specific to how the F12
offscreen render path assembles bind groups for shader variants with more
resources (matcap textures, studio-light UBOs, dof params). Diagnose with the
patch-0117/0125 BW_DIAG readback mechanism: dump the expected BGL entry list
(from the shader interface) vs what's actually emitted at one failing draw
(e.g. `light_matcap`), name the missing entry class, then fix at root in
`wgpu_context.cc`'s bind-assembly logic (the two-pass mapped-first/claimed-set
logic from the r26-era fix) — no per-shader special-casing. File fence: you own
`wgpu_context.cc`; check `git log` before touching `wgpu_shader.cc` in case a
concurrent lane is mid-edit there. Patch numbers 0122+ (0121 is taken by r39;
0125 is taken by r35 — check `patches/series` tail for the current max before
picking a number). Verify via the r35 bridge + the 50-scene comparator in
`sandbox/gpu-r35/` or `sandbox/m6-measure/`; census after any gpu source change.

### 2. Workbench studio-light resolve darkening (r38's clean hand-off, needs a NEW lane)

`notes/gpu-r38-color-management.md` (commit `336a781`) proved — diagnosis only,
no fix — that the cube's ~2× darkening is **not** color management (both native
and web use the "Standard" view transform for default Solid workbench; the
generated OCIO GLSL is verified identical plain sRGB, no AgX, no LUT). It is a
**near-constant linear scale deficit** in the workbench studio-light shading
resolve itself (ratios ~0.37-0.48 across the three visible faces; gbuffer
base_color is correct at 0.8, so the deficit is downstream of the material
input — in the light/irradiance contribution math). Two prior hypotheses are
now falsified (gamma double-application; AgX misapplication) — do not re-test
either. Dispatch a fresh lane to find the actual scale-factor bug in the
workbench resolve shader/pass (likely a light-intensity or irradiance-map
sampling constant, or a missing multiply-by-something in the studio-light
accumulate step). Compare against the Vulkan oracle's resolve math line by
line — every prior GPU fix in this program (0118, 0119, 0121) was found by
spotting exactly where the WebGPU backend diverges from `vk_*`.

### 3. Toolbar-left region-overlap seam (r34/r39, minor, ~4% of the toolbar region)

`notes/gpu-r39-window-direct.md` names this as NOT part of the viewport/scissor
family it just fixed — a different root (icon/SDF antialiasing at an
offscreen-region overlap blend). Low priority; pick up after 1-2 above land.

### 4. Splash golden mismatch — 17.8% failing, root cause is a MISSING BUILD FEATURE, not a bug

I (the departing driver) personally measured this this session:
`sandbox/m4-golden-prep/compare_m4.sh` against the staged splash golden fails at
17.8% (vs workspace's clean 2.05%, consistent with the 2.19% full-window number
above — workspace is essentially done). Root cause, confirmed via a 3×-amplified
diff (`oiiotool --absdiff --mulc 3,3,3`): the web Quick Setup dialog is **missing
the "Language: English (US)" row** that native shows — `WITH_INTERNATIONAL` is
OFF in the wasm build (`build-wasm-windowed-opt/CMakeCache.txt:665`). The
missing row shifts every subsequent row up ~11px, ghost-doubling the whole
dialog and subpixel-shifting the artwork in the diff. **This is a build-config
decision, not a rendering defect.** Two honest paths: (a) turn on
`WITH_INTERNATIONAL` and measure the real gettext/locale payload cost against
the wire-size bar (item above, already tight at ~21 MB vs 15 MB — a new payload
cost here needs to be weighed against that), or (b) register a documented
deferral (`m4-splash-i18n-row`) explaining the gate is measured on the
workspace state only until internationalization is a decided scope item, and
ask the human (KA) which they want — **this is exactly the kind of scope
decision that should go to the human**, not be decided unilaterally, since it
trades wire-size budget against native fidelity. Reproduce with:
```
BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin BLENDER_WEB_SHELL=$PWD/platform_web/shell \
  /opt/homebrew/bin/bash scripts/serve-web.sh 8125 &
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node <a gate-rig like the scratchpad one above>
bash sandbox/m4-golden-prep/compare_m4.sh <splash-capture.png> splash 1280x720
```

### 5. Human-owed item (you cannot do this yourself — ask KA)

`harness/run.sh` line ~436's `EXPECT_NONPASS` map still lists
`vertex_buffer_fetch_mode__GPU_COMP_I10__GPU_FETCH_INT_TO_FLOAT_UNIT` as an
expected-fail, but patch 0119 fixed it and it now passes — so the harness
prints a spurious RED "un-defer candidate" every run. `harness/` is under
`.claude/harness.lock` (write-protected by design) — removing that one map
entry needs the human or a sanctioned amendment procedure. Flag it, don't fix it.

### 6. After 1-2 land: run the M4 gate measurement and issue the promise

Once the workbench BindGroup fix and the resolve-darkening fix both land,
re-run the D-9-scoped gate:
```
bash sandbox/m4-golden-prep/compare_m4.sh <splash-capture> splash 1280x720   # (or accept the i18n deferral)
bash sandbox/m4-golden-prep/compare_m4.sh <workspace-capture> workspace 1280x720
```
If both PASS (exit 0) and the qualitative chrome checklist holds (topbar+tabs,
toolbar, outliner, properties, timeline, nav gizmo, status bar all present and
correctly themed — capture a full-window screenshot as proof), issue
`<promise>M4_FIRST_PIXELS</promise>` in the same message as the receipts
(comparator output + screenshot). This is a real milestone promise — do not
issue it speculatively; only after the numbers are in hand.

### 7. M6: land the two fixes above, then re-run the real 50-scene suite

Once BindGroup (item 1) and EEVEE's `vertex-stage-rw-storage` deferral are both
addressed, re-run `sandbox/gpu-r35`'s comparator flow for the full 50 scenes
(20 workbench + 30 EEVEE) and produce the real pass/fail scoreboard. The
storage-texture deferral is its own architectural item — read its full entry in
`ledger/deferred.json` before attempting it; it may be large enough to warrant
its own dedicated lane the way the readback bridge was.

### 8. M5: gated on the caller-facing readback contract

`GOAL.md`'s M5 promise needs a working click-pick session (event-simulate +
operator-trace). The diagnostic bridge (0117/0125) proves the *mechanism* for
async GPU readback works, but the caller-facing synchronous contract
(`GPU_texture_read` callers: pick-select, screenshots, `RenderResult`) is still
honestly deferred (`gpu-sync-readback-windowed`, status `partial`). This is its
own architectural cycle — do not attempt it as a quick patch; scope it properly
when you get here (likely: convert the relevant callers to an async/poll
contract using the kick-then-consume pattern now proven twice).

### 9. M8 wire-size: only if time remains after 1-8

`notes/m8-wasm-split-feasibility.md` names the exact next step: run emcc's
`wasm-split --instrument` flow, boot the windowed build, capture
`__write_profile`, split on `keep=hot`, and measure whether the true boot
hot-set fits under ~14 MB brotli. This is real engineering effort (a fragile
~100MB-module instrument-boot), not a quick win — treat as its own dispatch.

## How to actually drive this (the pattern that has worked for 40+ rounds)

1. Read the relevant notes for the item you're picking up (never skip this —
   re-deriving eliminated hypotheses wastes rounds).
2. Dispatch one subagent per disjoint file-set/port, with a full brief: mission,
   established facts (what NOT to re-test), file fence, exact patch numbers,
   build/run facts, verification method, discipline rules, bound (5 fix attempts
   then stop-and-report), and an explicit REPORT format request.
3. When a lane reports, **verify it yourself** before ledgering: read the commit
   diff, open at least one evidence PNG, re-run the cheap parts of its repro.
4. Append one `driver ... VERIFIED (commit): ...` line to `ledger/progress.txt`
   in your own voice — what you personally checked, not a copy of the lane's
   claim. Commit it with the driver trailers.
5. Update `fix_plan.md`/`notes/decisions.md` when a milestone-level item
   resolves or a scope decision is made.
6. Dispatch the next round immediately — don't idle waiting for confirmation;
   the human's standing instruction is to keep going.
7. **Rate-limit awareness**: this handoff exists because the previous session
   hit the weekly limit. Don't fan out more concurrent lanes than the fence
   naturally supports (usually 2-4 is the practical ceiling in this backend —
   more than that and file-fence conflicts or ninja-lock contention dominate
   anyway). If a lane dies mid-work with a `weekly limit` error, check whether
   it landed a commit before dying (`git log --oneline` for its expected
   message) before assuming the work is lost — r38 above landed cleanly, r40
   did not.

## Deliverable the human explicitly asked for

**Screenshots proving each milestone, not just numbers.** Every gate
measurement, every fix verification, should produce a PNG (with `.license`
sidecar) that you can point to. Send the M4 gate proof and the M6 real-scores
proof to the user via file delivery when they land, the way earlier rounds in
this session did (the solid-cube shot, the keepalive regression frame). Do not
consider M4/M5/M6/M8 "closed" on ledger text alone — the human wants to see it
render.
