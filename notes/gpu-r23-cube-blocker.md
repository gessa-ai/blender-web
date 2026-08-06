<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 23 (M4.T20) — VISIBLE rig live; RW-storage cascade killed; cube blocker = surface-present seam

Pin: Blender 5.2 `fbe6228777e7`; build `build-wasm-windowed` + patches through **0108** +
r22 ghost commits. Verification rig THIS round = a **VISIBLE, unthrottled browser** (below),
not the hidden Browser pane — this changed the diagnosis twice.

## Task 1 — the visible verification rig (SOLVED; everything below depends on it)

The in-app Browser pane reports `visibilityState "hidden"` → Chrome pauses rAF → the emscripten
main loop never ticks unprompted (r22's "idle-black"). **Fix: drive with a headed Playwright
(node) context using the bundled Chromium** (the plugin's configured `chrome` channel points at
a stub `/Applications/Google Chrome.app` with no binary — dead; bundled `chromium-1234` under
`~/Library/Caches/ms-playwright` works). Launch `chromium.launch({headless:false,
args:['--enable-unsafe-webgpu','--enable-features=Vulkan']})`. Receipts at :8123/windowed.html:
`visibilityState="visible"`, `crossOriginIsolated=true` (SAB), `navigator.gpu` adapter OK
(**apple/metal-3, 23 features**), canvas 1280x720, rAF **~120 ticks/s with ZERO input**. Boot
reaches WM_main and the **full UI composites unprompted** — the r22 boot-settle burst is now
verifiable. No dev-fallback setTimeout pump was needed (task 1b unused). Rig scripts:
`scratchpad/rig_{env,boot,fullpage,wscapture,capture}.js` (node, one-shot; keep the page alive
for capture+read in one run). **CDP `page.screenshot` captures the transferred OffscreenCanvas
faithfully** (the r22 JS-readback wall is `toDataURL`/element-screenshot only; the compositor
path shows real pixels — proven by a full-UI 1280x720 capture).

## Task 2 — `--python-expr` REDIAGNOSED (r22's "FINAL pass not reached" was wrong)

Subagent trace: the creator FINAL arg pass runs `arg_handle_python_expr_run` straight-line at
**creator.cc:622**, unconditionally BEFORE `WM_main` (creator.cc:663 → wm.cc:619
`emscripten_set_main_loop(lambda,0,1)`). So `--python-expr` **executes**. Its `print()` is
invisible only because Blender never sets `config.buffered_stdio=0` (bpy_interface.cc) and the
windowed process never exits (the loop's `simulate_infinite_loop=1` throws "unwind"), so the
block-buffered stdout never flushes — plus the documented threaded-wasm stdout drop. The
**side-effect still fires**: an expr that registers a `bpy.app.timer` runs the timer inside the
tick (wm.cc:624 `wm_event_do_notifiers` → `BLI_timer_execute`) after first pixels, where the
surface is configured. → No C fix needed for the trigger; shell dev-hook only (commit
`1850313`: `window.__BW_PYEXPR`/`?pyexpr=` appends `--python-expr`, and `window.__bwModule`
exposes the runtime for main-thread `FS.readFile`). NB at line 622 the surface is NOT yet
configured, so a screenshot fired there reads empty — the timer defer is mandatory.

## Task 3 — THE CAPTURE + comparator verdict (delivered via the compositor path)

Recipe proven end-to-end: inject `--python-expr` = `bpy.context.preferences.view.show_splash =
False` + a `bpy.app.timer` → `bpy.ops.screen.screenshot(...)`. show_splash=False (runs at line
622, before WM_init_splash_on_startup) **suppresses the splash → the WORKSPACE renders** (the
M4 gate state). The screenshot operator WRITES a valid **1280x720x3 PNG** to WasmFS and it
pulls out cleanly via main-thread `mod.FS.readFile` (base64 over CDP to node — never through
LLM context). **BUT the in-app readback is blank**: `WM_window_pixels_read` copies the Dawn
surface texture, which is transient — 725× `GPUValidationError: Destroyed texture [IOSurface …
WebgpuSwapChainTexture] used in a submit`. So the readback PNG is a uniform 12333-byte blank.

**Comparator run on the real composited output** (CDP compositor capture of the canvas at exact
1280x720, splash suppressed):
```
bash sandbox/m4-golden-prep/compare_m4.sh <cand> workspace 1280x720
FAIL workspace_1280x720  Max error = 1  over: 327199 pixels (35.5%) over 0.016   (exit 1)
```
Identical pre- and post-0108 (35.6% → 35.5%) — the UI chrome matches the golden; the **~35% is
the blank 3D viewport interior** (no grid/axes/cube vs the golden's shaded cube+grid). Evidence:
`platform_web/shell/evidence/m4-r23-workspace-post0108-1280x720.png` (workspace, viewport blank)
and `m4-r23-splash-composite-1280x720.png` (full splash UI composites). NOTE the capture path is
the CDP compositor, not the in-app operator (blocked, above) nor toDataURL (blank, r22).

## Task 4 — viewport interior: patch 0108 killed one layer; the cube blocker is now the present seam

**Patch 0108 (committed `984414a`) — strip Vertex from RW storage-buffer bind-group
visibility.** The visible rig surfaced a per-frame validation STORM invisible before:
`Read-write storage buffer binding is used with a visibility that contains ShaderStage::Vertex`
→ Invalid BindGroupLayout → PipelineLayout → RenderPipeline → CommandBuffer. Root cause:
`wgpu_shader.cc:2112` applies one `Vertex|Fragment` `stages` mask to EVERY draw resource, so a
fragment-only RW SSBO carried Vertex visibility (WebGPU forbids RW storage in the vertex stage;
a WGSL vertex entry can't write storage). Fix in `build_interface_map`: RW-storage entries get
Vertex stripped. **Live result: this error class dropped from ~80/boot to ZERO.** m3 gate 5/5,
census 148/158 held (native binary not relinked — run-only). Maps to the census
`vertex-stage-rw-storage` deferral.

**But the viewport interior is STILL blank** and the comparator is unchanged. The dominant
residual is now **725× `Destroyed texture … WebgpuSwapChainTexture used in a submit`** — a
surface-present lifecycle bug, NOT the throttling artifact r22 attributed it to (r22 saw the
OffscreenCanvas *retain* a good frame in the hidden tab and concluded "present is fine"; the
visible rig proves most per-frame submits actually ERROR and are dropped, and the canvas just
holds the last good frame). Mechanism: `WGPUContext::sync_backbuffer()` (wgpu_context.cc:662,
called from `activate()`:153) does `surface.GetCurrentTexture()` and adopts it into
back_left/front_left every activate. emdawnwebgpu auto-presents (destroying that texture) when
the rAF callback returns; a command buffer that references the surface texture but is submitted
after the callback yields (Blender's on-demand-redraw cadence vs per-frame GetCurrentTexture) is
then submitting a destroyed texture. The UI composites on the frames that DO submit in time;
the workbench-solid + overlay-grid viewport passes (the ones that would draw the cube) do not.

### Next-round cube recipe (for the driver)
1. **Fix the present seam (the prize).** Ensure `GetCurrentTexture` is acquired AND every
   command buffer referencing back_left/front_left is submitted within the SAME rAF frame,
   before the browser auto-presents; or composite into a PERSISTENT offscreen backbuffer and
   blit-to-surface as the last op of the frame (r20/r21 sync_backbuffer/0094 territory). Verify
   in the visible rig: `Destroyed texture` count → 0, viewport interior non-black.
2. **Instrument the offscreen** (task-4 as dispatched): blit the GPUViewport offscreen texture
   to a debug readback and check non-black % — confirms whether the workbench draw PRODUCES
   content (present-seam only) or produces nothing (a further draw blocker behind 0108).
3. Then re-capture (compositor path works now) + re-run the comparator; expect the ~35% to
   collapse toward the idiff tolerance once the cube+grid draw.

## Secondary / other-worker items (flagged, not owned)
- **python-wasm debt:** bl_pkg register aborts on `ModuleNotFoundError: No module named
  'requests'` (`_bpy_internal/http/downloader.py:53`) — the next missing import after r20's
  cattrs fix. Non-fatal to the workspace state (no dialog seen), but a python-wasm gap.
- **select-click TypeError** (r22): all draw/compute CreateBindGroup sites already route through
  `create_bind_group_checked` (only the ctx:405 blit is separate); the select-pass null-buffer
  needs live repro (a select-click) which the workspace gate does not require — deferred.

## Receipts
- Commits: `984414a` (patch 0108), `1850313` (shell capture hook). m3 5/5 GREEN
  (ledger/results/m3.json): census 148/158, static_shaders 956/973, patches_series all
  clean-or-applied incl. `0108:applied`. Mirror 0-drift; series updated.
