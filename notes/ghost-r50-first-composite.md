<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# ghost-r50 - first-composite (P2 blocker #6): FALSIFIED on the current tree, root cause is the inline shader compile

**Outcome: diagnosis-only. The "first composite needs an input event" defect does NOT
reproduce on the current windowed-opt build.** A genuinely zero-input fresh boot composites
the FULL UI (splash + workspace chrome, including the shaded cube) at ~+15-17 s, deterministically,
with no mouse or key event ever sent. The blank period before that is the WM worker blocking in
the inline shader compile of the first engine draw - a GPU/engine-lane concern outside the ghost
fence - NOT a missing GHOST expose/activate event. No GHOST code was changed; no patch was cut.

Build under test: `build-wasm-windowed-opt/bin` (linked 2026-08-08 18:17, the i18n-restored relink).
Rigs + evidence: `sandbox/ghost-r50-first-composite/` (headed bundled-Chromium node-Playwright,
`NODE_PATH=/Users/paws/plushly/game-platform/node_modules`, served on :8132).

---

## 1. What the mission hypothesised, and why it is falsified

The dispatch hypothesis: web GHOST never synthesises the initial window-expose/activate that
native GHOST delivers on window creation, so `wm_draw_update` finds no dirty window until an input
event marks one - hence "the tab stays background until the first mouse move." Verify, do not assume.

Verified against source and behaviour - the hypothesis is **false on the current tree**:

- **Web GHOST already delivers the initial events.** `GHOST_SystemWeb::createWindow` posts an
  initial `GHOST_kEventWindowSize` (`platform_web/ghost/GHOST_SystemWeb.cc:595`, the r19 fix
  0412052, "exactly as the native back-ends do"), and `GHOST_SystemWeb::processEvents` bursts
  `GHOST_kEventWindowActivate` every 12 ticks across the first 180 ticks
  (`GHOST_SystemWeb.cc:399-405`, the r22 boot-settle burst 1cc0089). The activate handler
  (`upstream/.../wm_window.cc:1827-1864`) sets `winactive`, `wm_window_make_drawable`,
  `addmousemove=1`, and injects a synthetic `MOUSEMOVE` - the native focus-repaint path.
- **`--debug-events` at boot with zero input shows `screen_refresh_if_needed: set screen`** firing
  (twice) unprompted (evidence `debug-events-console.log`). That is the `ED_screen` refresh that
  sets `screen->do_refresh`, which makes `wm_draw_update_test_window` return true
  (`upstream/.../wm_draw.cc:1578`) - i.e. the window IS marked drawable at boot without input.
- **A real first mouse event does not change first-composite timing** (the decisive test the
  mission asked for). Two fresh tabs: (A) zero input, (B) one mouse-move over the canvas at +2 s
  then nothing. First composite: **A = +17 s, B = +16 s - identical** (`input-compare.log`). If the
  composite were gated on an input event, B would beat A by ~15 s; it does not. The +2 s mouse-move
  is queued but cannot be processed until the worker returns from its synchronous block at ~+15 s.

## 2. The real mechanism (what actually happens on a zero-input boot)

Timeline, sampled every 2 s, zero input (`tl_run1.log`, `tl_run2.log`; counters via the keepalive
`bw_wm_tick_count` / `bw_present_count` exports):

| t after WM_main | WM tick | present | canvas | what |
|---|---|---|---|---|
| 0-2 s | 0 | 0 | black | main() still doing synchronous boot work on the WM worker |
| +3-4 s | 1 | 1 | black | first WM iteration; present frame 0 = the initial window clear (black) |
| +4-14 s | **stuck at 1** | 1 | **black** | **WM worker blocked in the inline shader compile - no rAF/setTimeout/input callback can fire** |
| ~+15-17 s | jumps to 23-46 | 9 | **FULL UI** | compile finishes; the already-tagged draw completes and composites |
| +18 s on | climbs steadily | 9 (idle) | holds | keepalive idle back-off; OffscreenCanvas holds the last frame |

The frozen tick counter (1 for ~10 s) is the signature of a long **synchronous** C++ call on the WM
worker: during it the worker's JS event loop is starved, so neither the rAF loop, the keepalive
`setTimeout`, nor queued input callbacks run. `?keepalive=0` (rAF baseline) shows the identical
stall and identical +16 s composite (`tl_ka0.log`) - so this is not a rAF-vs-setTimeout gating
effect and the keepalive is not load-bearing for first composite.

**The blocking op is the shader compile, timestamped.** Boot with `?args=--debug-gpu --log
gpu.shader --log-level 4` (shell dev hook, no rebuild), zero input (`shader-timing-console.log`):
first `Compiling Shader` at **+1.0 s**, last shader line at **+17.4 s**, `presentBackbuffer frame 0`
(black) at +3.3 s, `presentBackbuffer frame 1` (full UI) at **+17.5 s - the instant compilation
finishes**. The whole engine shader set compiles INLINE on the WM thread because the web build runs
`use_main_context_workaround=true` (workerless `ShaderCompiler`, `gpu_shader.cc`; r25 finding,
notes/gpu-r25-*.md). That is the ~15 s "dead tab", and it is squarely in the GPU/webgpu lane's
fence (`upstream/source/blender/gpu/webgpu`), not GHOST's.

## 3. Why the driver saw "+30 s background-only" and I do not

The 2026-08-09T18:00Z driver entry re-confirmed the defect on this same binary. The most likely
reconciliation: the inline compile is **load-sensitive**. My runs completed the compile in ~16 s at
machine load ~7-10; under the heavier build contention the program routinely runs (`ninja`
relinks + census), the same compile stretches past a fixed +30 s capture, so the driver's shot
caught it mid-compile (still the black frame-0 clear). The "a neutral mouse nudge composited
everything" observation is consistent with coincidence: the nudge cannot un-block a synchronous
C++ call, and my A/B test shows input does not move the composite time. This is not proof the
driver erred; it is that the symptom is a timing/throughput problem, not an event-delivery problem.

## 4. What I falsified / DO-NOT-RE-RUN

- **Do not add more initial GHOST events** (expose / activate / size / update) to "fix first
  composite." They are already posted and already work; the composite is not waiting on an event.
  A plain `GHOST_kEventWindowUpdate` was already tried and found too weak (r22 comment,
  `GHOST_SystemWeb.cc:387`); the WindowSize+Activate that superseded it is in place.
- **Do not add a shell-JS forced draw / paint-a-background-before-compile.** The dispatch forbids it
  and it would not be faithful to native; it only masks the compile stall.
- **Do not attribute the stall to the keepalive or to rAF present-gating.** Falsified: `?keepalive=0`
  stalls and composites identically (`tl_ka0.log`).
- **The fix, if one is wanted, belongs to the GPU/engine lane, not GHOST:** move first-draw shader
  compilation off the WM worker (async / real `ShaderCompiler` worker), or cache compiled shaders
  (OPFS shader-binary cache) so a fresh tab does not pay ~15 s of inline compile before frame one.

## 5. Regression / tree-health re-check (no code change this lane; post-i18n sanity)

- **keepalive holds:** after the zero-input composite, 12 s idle -> tick +247 (loop alive),
  present +0 (no idle GPU burn) (`health-result.json`).
- **interaction works:** click Continue + Esc -> splash dismissed to workspace, present +22
  (`health_interaction_pre/post.png`).
- **resize recomposites (r28):** non-gate backing 1400x850 -> 1000x700 (changed), present +8
  (`health_resize_after.png`).
- **whole-window parity 1600x900 = 1.15% over 0.016** (16583 px, mean 0.0028) via
  `sandbox/m4-fullscreen-parity/compare_fullscreen.sh` on `parity_web_1600x900.png` - in line with
  the ~1.1% baseline, no material post-i18n regression. The i18n restore is visible in the splash
  (the "Language: English (US)" row is present, `before_1600x900_t30.png`).
- **census:** N/A - no source was touched, and the ghost web files under `platform_web/ghost/` are
  wasm-only (not shared with native GHOST back-ends).

## 6. Evidence index (`sandbox/ghost-r50-first-composite/`)

| file | what |
|---|---|
| `drive-first-composite.mjs` + `before_1600x900_t10.png` / `_t30.png` | BEFORE: zero-input +10 s (black) / +30 s (FULL UI, splash+chrome) |
| `probe-timeline.mjs` + `tl_run1.log` `tl_run2.log` `tl_ka0.log` | 2 s-sampled zero-input timelines (keepalive on x2, `?keepalive=0`) |
| `probe-nosplash.mjs` + `nosplash.log` `nosplash_final.png` | zero-input + `show_splash=False`: workspace + cube composite unprompted |
| `probe-input-compare.mjs` + `input-compare.log` | zero-input vs one-early-mouse-move: +17 s vs +16 s (input-independent) |
| `probe-debug-events.mjs` + `debug-events-console.log` | `--debug-events`: `screen_refresh_if_needed: set screen` at boot, zero input |
| `probe-shader-timing.mjs` + `shader-timing-console.log` | `--debug-gpu --log gpu.shader`: compile +1.0 s -> +17.4 s, frame 1 at +17.5 s |
| `probe-health.mjs` + `health-*.png` `health-result.json` | keepalive / interaction / resize re-checks |
| `parity-capture.mjs` + `parity_web_1600x900.png` | whole-window parity candidate (1.15%) |

## 7. Reproduce
```
BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin BLENDER_WEB_SHELL=$PWD/platform_web/shell \
  /opt/homebrew/bin/bash scripts/serve-web.sh 8132 &
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/ghost-r50-first-composite/probe-input-compare.mjs 8132   # the decisive A/B
```
