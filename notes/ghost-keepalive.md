<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# ghost-keepalive - the WM main loop keeps ticking at idle (no Python kick, no idle GPU burn)

**Outcome: the windowed `blender_browser` main loop no longer stalls at idle.** A small,
opt-in GHOST keepalive switches the WM worker's main loop from present-gated
requestAnimationFrame to setTimeout scheduling, so events, `bpy.app.timers`, and the ADR-007
kick-then-consume GPU futures (AllowSpontaneous completions, r31) keep resolving with nothing
on screen changing - WITHOUT forcing a present each tick (no GPU burn at idle). Default ON;
`?keepalive=0` restores the old rAF behaviour for A/B. Shell-only + GHOST-only; no `upstream/`,
cmake, or link-flag change. All files mine: `platform_web/ghost/{GHOST_SystemWeb.cc,
GHOST_SystemWeb.hh, GHOST_ContextWGPUWeb.cc, GHOST_WebDisplayState.hh}` and
`platform_web/shell/boot-windowed.js`; proof rig + evidence under `sandbox/ghost-keepalive/`.

---

## 1. The bug (recap of the M7b §4 load-bearing finding)

Web `WM_main` is `emscripten_set_main_loop(fn, 0, 1)` on the PROXY_TO_PTHREAD WM worker
(patch 0026): `fps=0` => the loop is driven by the worker's `requestAnimationFrame`. A
worker's rAF is **present-gated** - it stops rescheduling once the OffscreenCanvas stops
compositing. Blender draws on demand, so once the boot redraw burst
(`GHOST_SystemWeb::processEvents`, ~180 ticks) finishes and nothing is tagged for redraw, no
frame is presented, rAF stops, and the whole loop stalls. Consequences (all measured in M7b,
`sandbox/m7b-files/probe-burst.mjs` maxHb=1): post-boot `bpy.app.timers` get exactly one tick
then freeze; idle-time GPU MapAsync completions never arrive; a `.blend` dropped on a truly
idle tab is not opened until the loop next ticks. Every driver rig has had to paper over this
with a `bpy.app.timers` kick that `tag_redraw()`s the viewport ~1 Hz to keep frames (and thus
rAF) alive - which also burns the GPU forever.

## 2. The fix - one scheduler swap, on the loop-owning thread

`emscripten_set_main_loop_timing(EM_TIMING_SETTIMEOUT, ms)` re-points the SAME already-running
main loop from rAF to the worker's `setTimeout`. `setTimeout` on a worker is **not**
present-gated, so the loop keeps ticking at idle regardless of compositing. Crucially this
does **not** force a present: the tick still runs `wm_draw_update`, which composites only when
something is tagged, so at true idle no frame is submitted. The keepalive pumps events; it
never `tag_redraw()`s. This is the whole mechanism - no new loop, no upstream edit (the loop
is set by patch 0026 in `wm.cc`; we only change how the existing loop is scheduled, from
`GHOST_SystemWeb::processEvents`, which runs on the WM worker - the only thread allowed to
call the timing API for this loop).

Why not the M7b-recommended "keep the rAF heartbeat forcing a present each tick"? That keeps
the loop alive but burns the GPU at idle (a present per tick), exactly what the mission
forbids. The setTimeout swap gives liveness with zero idle presents.

### Adaptive interval (idle CPU is negligible too)

`processEvents` runs each tick and picks the interval:

- **Fast (16 ms, ~60 Hz)** while anything is happening: the boot burst is running, input is
  queued this tick, or a present happened since the last tick (interaction / playback /
  notifier redraw - detected via the new `ghost_web::present_count()`). Matches the old rAF
  cadence, so interaction and the M5 latency budget are unaffected.
- **Idle (250 ms, ~4 Hz)** after a 1 s grace with none of the above. At deep idle the loop
  wakes ~4x/s (enough to service timers and drain a dropped file / input), presents nothing,
  and the GPU is untouched. Cold-idle input wake latency is <=250 ms; the first input event
  bumps it straight back to 60 Hz.

The first tick (`current_timing_ms_ == -1`) performs the initial rAF->setTimeout switch, so
the loop never relies on rAF and cannot stall - even during boot. Failure modes are benign:
if activity detection under-fires we stay at 60 Hz (still no idle presents, just more idle
CPU); if it over-fires the worst case is a <=250 ms input wake. Neither breaks correctness or
burns the GPU.

Intervals are shell-tunable (`bw_shell_set_keepalive(enabled, active_ms, idle_ms)`;
`?ka_active=` / `?ka_idle=`) for experiments; defaults are baked in.

## 3. What was wired (owned files only)

- `GHOST_SystemWeb.cc`: keepalive atomics (`g_keepalive_enabled` default 1, `active_ms` 16,
  `idle_ms` 250) + a WM tick counter; the `bw_shell_set_keepalive` control export and the
  `bw_wm_tick_count` diagnostic export (both `EMSCRIPTEN_KEEPALIVE`, same main-thread-safe
  relaxed-atomic posture as `bw_shell_set_display`); the timing-switch + activity logic at the
  end of `processEvents`. The boot redraw heartbeat is UNCHANGED (first pixels unaffected).
- `GHOST_SystemWeb.hh`: three per-worker bookkeeping members (`current_timing_ms_ = -1`,
  `last_activity_ms_`, `last_present_count_`).
- `GHOST_ContextWGPUWeb.cc`: `ghost_web::present_count()` / `note_present()` (one relaxed
  atomic bumped once per `presentBackbuffer` submit) + the `bw_present_count` diagnostic
  export. Used both for activity detection and the no-idle-burn proof.
- `GHOST_WebDisplayState.hh`: declarations for the two new `ghost_web` functions.
- `boot-windowed.js`: `keepaliveConfig()` (parses `?keepalive` / `?ka_active` / `?ka_idle`,
  default ON) and `pushKeepaliveToWorker()`, called from preRun in EVERY mode (scheduling-only
  - it never touches argv, size, DPR, or pixels, so `?pyexpr` / `?args` / `?gate` / auto-boot /
  `__bwModule` / the WM_main marker / contextmenu / key capture / DPR backing / resize are all
  byte-for-byte preserved).

## 4. Proof with teeth

Rig: `sandbox/ghost-keepalive/drive-keepalive.mjs` - headed BUNDLED-Chromium node-Playwright
(`NODE_PATH=/Users/paws/plushly/game-platform/node_modules`) against the windowed-opt binary
served on **:8128** (`build-wasm-windowed-opt/bin` + the real `platform_web/shell`). Four
fresh-context boots. Evidence in `sandbox/ghost-keepalive/evidence/` (before/after PNGs with
CC0-1.0 `.license` sidecars, per-scenario console logs, `run.log`, `summary.json`).

**`drive-keepalive.mjs` - the mandated bar, 4/4 PASS** (`summary.json`, `run.log`):

| # | scenario | measured | verdict |
|---|---|---|---|
| A | liveness + no idle burn (NO pyexpr, keepalive default ON): boot -> WM_main, 30 s idle | tick **+293** over 30 s (loop alive); present **+8** = **0.27/s** (NOT a 60 fps burn); post-idle mouse move+click -> tick +73, present +3 (UI responded) | **PASS** |
| B | one-shot `bpy.app.timer` at 20 s, NO tag_redraw, keepalive ON | timer **fired @20019 ms** with zero kicks; tick +282 | **PASS** |
| C | `?keepalive=0` A/B baseline (rAF) reachable | booted on rAF, tick **+1812 (60.4 Hz)** vs ON's idle back-off; baseline restored | **PASS** |
| D | regression WITH the standard 1 Hz `tag_redraw` kick rig | present **+67** over 45 s (kick drives draws); screenshot **99.9% non-black** (grid + UI render) | **PASS** |

A is the no-idle-burn evidence with teeth: the WM tick counter climbs (loop alive) while the
present counter is essentially flat (0.27 presents/s over the 30 s window - the 8 presents are
boot-settle frames, not a continuous 60 fps submit). B proves timers - and therefore the
ADR-007 kick-then-consume GPU futures serviced on the same event loop - resolve at idle with
no kick. D proves the existing kick rigs still work.

**`drive-discriminator.mjs` - honest A/B characterisation** (`discriminator.json`): over a 20 s
foreground idle, keepalive ON ran the loop at **12.7 Hz** and OFF (rAF) at **48 Hz**, while
BOTH presented only **0.4/s** - so ON cuts idle CPU ~4x and NEITHER burns the GPU in a
continuously-composited foreground tab. The rAF idle STALL (M7b `probe-burst` maxHb=1) is a
present-gating effect that only bites when compositing stops; I could NOT force that state in
Playwright (`drive-bg-stall.mjs`, `bg-stall.json`): even with Chromium's anti-throttle flags
removed, a background tab kept `document.visibilityState === "visible"` under automation, so
worker rAF never paused. The keepalive is nonetheless the correct fix because it makes idle
liveness INDEPENDENT of the compositor - `setTimeout` is not present-gated - which is exactly
what A and B demonstrate, and it removes the idle-CPU spin the rAF baseline shows. Reported
straight rather than claiming a stall I did not reproduce here.

## 5. Reproduce
```
# serve the windowed-opt bin + real shell (COOP/COEP) on :8128:
BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin BLENDER_WEB_SHELL=$PWD/platform_web/shell \
  /opt/homebrew/bin/bash scripts/serve-web.sh 8128
# proof (headed bundled Chromium, 4 boots):
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/ghost-keepalive/drive-keepalive.mjs
```
Relink (owned .cc/.hh only, no reconfigure): `export EMSDK_PYTHON=...python3` then
`harness/buildwrap.sh scripts/ninja-locked.sh -C build-wasm-windowed-opt blender_browser`.

## 6. Residuals / carry-forward
- Playback-without-input is covered by present-count activity detection, so it stays at 60 Hz
  while drawing; a future explicit "keep drawing" hint from the WM would be cleaner than
  inferring from the present counter, but is not needed.
- The keepalive removes the need for the kick rig in driver tooling; existing kick rigs still
  work (regression proven) so nothing has to change at once.
- Cross-browser: verified on the bundled Chromium only (same engine as the ship target).
