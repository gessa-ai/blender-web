<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# HANDOFF - 2026-08-09 (driver 3) - resume the M4/M5/M6/M8 close-out

You are the driver for **blender-web**: a faithful port of pinned Blender 5.2 LTS
(commit `fbe6228777e7`) to the browser via Emscripten/WebAssembly with a hand-written
WebGPU backend. Repo: `/Users/paws/blender-web` (do not touch any other repo tool
context may show you). Branch: `agent/m2.5-python-boot`. **Shared checkout** - other
lanes may leave uncommitted WIP in the tree at any time; never `git add -A`, never
revert files you did not change.

**Read in this order before doing anything else:** `GOAL.md`, `notes/decisions.md`
(D-1..D-10 - **D-9** scopes the M4 gate, **D-10** is a NEW binding human directive),
`fix_plan.md`, the last ~40 lines of `ledger/progress.txt` (the driver VERIFIED lines
are the session narrative), `ledger/deferred.json`, then
`reports/HANDOFF-20260809-continue.md` (the previous handoff - its Standing rules
section is still binding verbatim; this document only records what changed since).
Then read the note for any item you touch before touching it.

## Why you are picking this up

The previous driver session (Claude Fable 5 as driver, Opus 5 subagent lanes) ended
when the harness process exited while THREE subagent lanes (r51, r52, r53) were
mid-flight. Their in-process state is lost, but ALL THREE left substantial partial
work on disk (see "The three dead lanes" below). Before that, the session verified
and landed ELEVEN rounds - the state below is trustworthy because every lane's claims
were independently re-verified by the driver before being ledgered.

## Standing rules (binding - carried from the previous handoff, deltas only)

Everything in `reports/HANDOFF-20260809-continue.md` "Standing rules" still applies:
upstream/ is read-only at the pin with ALL changes as numbered patches in `patches/`
(reconstruct pre-image, hand-built `diff --git` headers, `git apply --check --reverse`
verified inside upstream/, rationale in `patches/series`); never modify `harness/`,
`oracle/`, `tests/golden/`, thresholds, or ledger pass-flags; census via
`/opt/homebrew/bin/bash harness/run.sh` (RUN-ONLY, rebuild `build-native-gpu` first
after any gpu source change); `export EMSDK_PYTHON=/Users/paws/blender-web/tools/emsdk/python/3.13.3_64bit/bin/python3`
before cmake; ALL ninja builds through `scripts/ninja-locked.sh`; verification via
headed node-Playwright with the bundled Chromium,
`NODE_PATH=/Users/paws/plushly/game-platform/node_modules`, never an in-app/hidden
pane; `?pyexpr=`/`?args=`/`?gate=WxH` shell hooks; `os.write(2,...)` reaches the
console, `print()` does not; commit trailers EXACTLY `Assisted-by: Claude (worker)`
(lanes) / `Assisted-by: Claude (driver)` (you) + `Co-Authored-By: Claude Fable 5
<noreply@anthropic.com>`; zero em dashes (U+2014) in authored text; SPDX headers on
new files; PNG evidence + two-line `.license` sidecars; `ledger/progress.txt` is
append-only.

**Deltas to those rules from this session:**
- **Census bar update:** TRUE bar is still 149 PASS / 7 FAIL / 2 CRASH (of 158
  GPUWebGPUTest) + static_shaders 956/973. `harness/GATE_RED` currently exists as an
  untracked artifact of the known-spurious I10 RED (`vertex_buffer_fetch_mode
  GPU_COMP_I10 INT_TO_FLOAT_UNIT` fixed by 0119 but still in `EXPECT_NONPASS`) -
  amending that map is HUMAN-OWED (harness.lock); keep flagging it, never edit it.
- **Zero-input boots now composite on their own** (r50 falsified P2#6): budget ~17s+
  to first present (the inline shader compile r51 was attacking). The mouse-nudge in
  capture rigs is no longer load-bearing on current builds but harmless to keep.
- **D-10 (NEW, human KA, binding):** fidelity-first on every scope tradeoff - take
  the path faithful to native Blender regardless of difficulty; handle wire-size via
  staged/lazy loading, never by cutting native-visible features; deferrals only for
  hard external blockers, and even those get an engineering attack first. Dispatch
  such work without asking per-item.
- **Ports used this session:** 8127/8128/8130/8132/8133/8134/8135/8136 (some stale
  servers may still hold 8124/8125/8126/8129). Pick free ones (`lsof -iTCP:<p>
  -sTCP:LISTEN`) and say so in each brief.
- **Patch numbers:** 0122, 0123, 0124, 0125, 0127 are landed. 0128 and 0133 exist as
  UNCOMMITTED patch files from the dead lanes (below). 0126, 0129-0132, 0134+ are
  free once you reconcile the dead lanes' claims.

## The driver process that produced this state (follow it exactly)

1. One subagent lane per disjoint FILE fence + unique port; 2-4 concurrent lanes max
   (ninja-lock contention dominates beyond that). Subagents are **Opus** (model:
   "opus"), never the driver's own model. Briefs must carry: mission, established
   facts (what NOT to re-test, with the falsified-hypothesis list), file fence, exact
   patch numbers, build/run facts, verification requirements, discipline rules, a
   5-fix-attempt bound, and an explicit REPORT format.
2. **Verify, don't trust - before ledgering ANY lane claim:** read the commit diff
   (`git show <hash> --stat` + the patch body), re-run at least one cheap independent
   repro (the comparator re-runs and code-citation reads this session each caught or
   confirmed something), and OPEN at least one evidence PNG yourself. This session's
   record: r43's premise was overturned by r44r2, whose premise was overturned by
   r46 - three corrections on ONE bug family, each caught because verification was
   independent. Diagnosis-only outcomes that falsify a premise (r50) are SUCCESS.
3. After verifying: append ONE `driver <ISO-time> rNN VERIFIED (<commit>): ...` line
   to `ledger/progress.txt` in your own voice stating what YOU checked, commit it
   (only the files you touched) with driver trailers.
4. **Screenshots as proof at every milestone** (the human's explicit standing
   deliverable): send PNG evidence via file delivery when a user-visible milestone
   lands (this session: the cube-parity heatmap, the i18n splash + Japanese UI).
5. Update `fix_plan.md`/`notes/decisions.md` when an item resolves or scope changes.
6. Dispatch the next round immediately; do not idle. If a lane dies, check for a
   landed commit AND for uncommitted WIP (mtimes in its fence + sandbox dirs) before
   assuming loss - this session recovered a full round (r46 from r44r3's WIP) that
   way.
7. Human paging: only for milestone-gate decisions, 5-failure stalls, or budget
   anomalies. D-10-class scope calls no longer need a page.

## State - DONE this session (all driver-verified; do not re-litigate)

- **Workbench TAA darkening: FIXED** (patch 0123, commit 813f94d). Root:
  push-constant ARRAYS uploaded tightly packed into std140 blocks (16-byte element
  stride); TAA samplesWeights[9] read as [w0,w4,w8,0...]. Viewport region parity now
  **PASS 0.48%** (verbatim 0.016/1 comparator); whole-window 1.1-1.15%; cube face
  linear ratios 1.015/1.014/1.050. **D-9 gate component (a) PASSES.**
- **Bind-unit namespace repair: LANDED** (patch 0122, 8004515). Frontend units =
  create-info slots (the vk/GL contract); dense numbering only at WGSL/BGL + emit.
  Killed the 6v10 + 1v4 resolve collisions. The reverted M4.T15 remap-skip failed
  because it changed only the emit side; 0122 keeps interface+emit+stale-skip
  consistent.
- **Geometry SSBO mask: FIXED** (patch 0124, 938ee0b). `ssbo_attr_mask_` was never
  populated from `geometry_resources_`; the shared gpu_batch gate then never bound
  the index-buffer SSBO. Bindgroup-count errors 100% eliminated. Workbench suite
  TRUE PASS = **4/20** (light_flat_attribute, light_matcap, light_matcap_no_specular,
  light_studio_material); remaining clusters precisely mapped (see r52 below).
- **i18n RESTORED per D-10** (patches 0127 + repo files; commits c5e465b Phase 1,
  422b488 Phase 2). Splash Language row back: splash 17.8% -> **4.54%**; workspace
  2.05% -> **1.11%**; real Noto CJK ja_JP switch proven + en_US round-trip; stage-0
  grew EXACTLY +2,248 B (languages index); 49 .mo (76.72 MiB raw) ride stage-1.
  Host msgfmt at `build-hosttools/bin-native/msgfmt` (gitignored, rebuildable via
  `scripts/build-hosttools.sh`).
- **Splash residual = the WEDGE** (fix_plan M4.T28, GATE-CRITICAL): a dark
  triangular wedge over the splash artwork (one triangle of the image quad not
  sampling its texture) is the ENTIRE 4.54%. Determination owed: r47 captured it
  with (now-committed) WIP in tree; nobody has yet re-captured post-0124 to confirm
  it persists. Evidence: `sandbox/i18n-r45/captures/r47-splash-diff3x_1280x720.png`.
- **P2#6 "first composite needs input": FALSIFIED** (r50, f108934, diagnosis-only).
  Initial GHOST events exist since r19/r22; 8 zero-input boots composite the full UI
  at ~+17s. The dead-tab is the **inline shader compile blocking the WM worker**
  (+1.0s..+17.4s, load-sensitive) - successor item M4.T29 (was r51's mission).
- **EEVEE storage design: ADOPTED** (r48, d4c11b8,
  `notes/eevee-storage-emulation-design.md`). The vertex stage NEVER uses the storage
  resources; blockers are 4 BGL classes + separable atomics. Phase A+A' (storage-
  image visibility strip mirroring the existing SSBO strip at
  `wgpu_shader_interface_map.cc:239` + `wgpu_shader.cc:~2360`, adapter-guarded
  TextureFormatsTier1/2 + requiredLimits in GHOST) = ~26/30 EEVEE scenes; Phase B
  (shadow-atlas SSBO atomics) = the last 4. MANDATORY first step: log
  `adapter.features` in the browser build (risk R1: tier exposure in emdawnwebgpu).
- **M5 readback contract design: ADOPTED** (r49, f4eec9a,
  `notes/m5-sync-readback-contract-design.md`). Sync readback zeros = event-loop
  starvation (blocking WaitAny halts the loop that must deliver mapAsync; asyncify-
  only WaitAny returns unfulfilled under ADR-006). Contract: kick-on-request /
  latch-on-tick / consume-on-settle via the twice-proven AllowSpontaneous primitive.
  Lanes: L-A backend primitive (was r53's mission) -> L-B GPU async API -> L-C
  caller conversion -> L-D M5 harness. Plus safety item: heap-own the WaitAnyOnly
  callbacks (stack-capture = the r25 table-OOB hazard; verified real in source).
- Driver ledger entries for all of the above are in `ledger/progress.txt` (committed
  through 4f57c84). The i18n + cube milestones were screenshot-delivered to KA.

## The three dead lanes - RECOVER FIRST (all have partial work on disk)

The harness process exited mid-flight. Tree state as of this handoff (HEAD 4f57c84):
`ledger/progress.txt` and `patches/series` have UNCOMMITTED modifications (dead
lanes' appends - audit line-by-line before committing anything that touches them);
untracked: `notes/gpu-r51-shader-latency.md`, `notes/gpu-r53-readback-primitive.md`,
`patches/0128-gpu-webgpu-wgsl-translation-opfs-cache.patch`,
`patches/0133-gpu-webgpu-production-readback-primitive.patch`,
`sandbox/gpu-r51-shader-latency/`, `sandbox/gpu-r52/`, `sandbox/gpu-r53-readback/`,
`invaltest-saltbump/` (likely r51 cache-invalidation test junk - inspect, then
delete or relocate), `harness/GATE_RED` (known-spurious, leave). Upstream gpu file
mtimes Aug 9 07:17: `wgpu_context.cc` (r52's edit), NEW FILE `wgpu_shader_cache.cc`
+ `wgpu_shader_compiler.cc` (r51's edits), `wgpu_texture.cc` (r53's edit).

For each, follow the r46 recovery protocol: audit the WIP + note + patch file
against the mission, keep-or-reimplement, verify BEHAVIORALLY, then land with full
patch discipline. The full original briefs are reproduced in the driver ledger
entries and below in compressed form:

### r51 - shader-compile boot latency (M4.T29, fence: wgpu_shader_compiler.cc + new wgpu_shader_cache.cc + platform_web/shell; patch 0128 + 0129 reserve; port 8134)
Mission: measure the ~16s first-draw shader-compile split (wasm-side shaderc+Tint
translation vs browser createShaderModule/pipeline), then fix the dominant term:
OPFS WGSL-translation cache for warm boots (key = hash of GLSL+defines+compiler
versions; byte-identical-to-fresh proof on >=10 shaders; invalidation proof;
browsers expose NO pipeline-binary serialization - cache OUR CPU work only) and/or
off-thread translation for cold. Its partial state (note + 0128 patch + the new
wgpu_shader_cache.cc) suggests it chose the OPFS cache and got far - audit whether
the census ran (wgpu_shader_compiler.cc is in the native build!) and whether
cold/warm boot numbers + correctness proofs exist in `sandbox/gpu-r51-shader-latency/`.
Acceptance: cold+warm time-to-first-present vs the ~+17s r50 baseline, 3x repeats;
census held; parity spot-check ~1.1-1.2%.

### r52 - workbench pixel unlock (fence: wgpu_framebuffer.cc, wgpu_pipeline.cc, wgpu_context.cc, wgpu_batch.cc, wgpu_shader.cc, wgpu_state_manager.cc, wgpu_immediate.cc; patches 0130-0132; port 8135)
Targets in order: (1) depth-Uint bind collision (~8 scenes, Depth32FloatStencil8 on
the Uint object_id sampler slot binding 4; the r43 9v13 site; NOT sample-type/aspect
- r46 falsified that); (2) color-attachment compaction (x-ray family ~5 scenes:
`WGPUFrameBuffer::target_formats` compacts NONE gaps so R16Uint object_id hits
float @location(0); Vulkan preserves gaps via VK_ATTACHMENT_UNUSED - preserve slots
through target_formats + sparse pipeline color targets, probe what Dawn accepts);
(3) 1v4 compute storage-image emit undercount (1 scene); (4) the splash WEDGE
(M4.T28 - first re-capture splash on the current tree to determine persist-vs-WIP,
then hunt in the immediate/widget image path if it persists). Only wgpu_context.cc
carries its WIP (mtime Aug 9 07:17) - it likely only started target (1). Verify via
before/after gpu-error signatures + full 20-scene rescore (`sandbox/gpu-r46/`
tooling; RESCORE_NOTES.md documents the boot-timeout flake mode) + census.

### r53 - readback L-A primitive (fence: wgpu_texture.cc, wgpu_buffer.cc + new wgpu_readback.* files; patches 0133 + 0134 reserve; port 8136)
Mission: implement L-A per `notes/m5-sync-readback-contract-design.md` - promote the
kick/latch/settle AllowSpontaneous readback to production at both seams + fix the
callback-lifetime hazard (heap-owned state; the [&] stack captures at
wgpu_texture.cc:~1277 / wgpu_buffer.cc:~164). NO public GPU API changes (that is
L-B). Its partial state (note + 0133 patch + wgpu_texture.cc edit) - audit
completeness. Acceptance: the r49 probe (`sandbox/m5-readback-design/
probe_sync_readback.mjs`, baseline Constant 0/255) yields TRUE pixels within the
design's tick budget; >=20-iteration snapshot stress with no table-OOB; the
0117/0125 diagnostic bridge still works (M6 rescore depends on it); census held -
CRITICAL: native Dawn has working blocking WaitAny, so the primitive must keep
native semantics exactly (__EMSCRIPTEN__-scoped or settle-immediately-on-native).

## Queue after the recovery (priority order)

1. **M4 gate measurement** (driver-run, D-9 scoped) - as soon as the wedge is fixed
   or characterized-as-preexisting-with-a-plan: capture splash + workspace 1280x720,
   run `bash sandbox/m4-golden-prep/compare_m4.sh <cap> {splash|workspace} 1280x720`;
   component (a) viewport-interior already PASSES; (c) chrome checklist capture
   (topbar+tabs, toolbar, outliner, properties, timeline, nav gizmo, status bar all
   present + correctly themed). If splash+workspace PASS (exit 0) and the checklist
   holds: issue `<promise>M4_FIRST_PIXELS</promise>` IN THE SAME MESSAGE as the
   comparator receipts + screenshot. Never speculatively.
2. **EEVEE Phase A implementation** (fence: wgpu_shader_interface_map.cc +
   wgpu_shader.cc + GHOST device features - collides with r52's fence, so sequence
   after r52 lands; browser adapter.features check FIRST). Then Phase A' residual
   formats; Phase B (shadow atomics) as its own lane.
3. **M6 full 50-scene re-score** (20 workbench + 30 EEVEE) once r52 + EEVEE-A land;
   produce the honest scoreboard + updated `notes/m6-gpu-suite-real-scores.md`
   successor; reconcile `ledger/deferred.json` (vertex-stage-rw-storage narrows to
   its true residue per the r48 findings).
4. **Readback L-B** (GPU async API, upstream-shared code, census-inert proof) and
   **L-C** (pick/depth/color caller conversion + settle barrier), then **L-D** (the
   M5 event-simulate click-pick session per the acceptance spec in the r49 design).
5. **Toolbar-left seam** (r39 Defect D, ~4% of toolbar region; offscreen-region
   overlap blend / icon SDF AA; fence overlaps r52's - sequence accordingly).
6. **M8 wire-size** (`notes/m8-wasm-split-feasibility.md`: function-level
   profile-driven wasm-split, unmeasured; disk is TIGHT ~35GB - watch it).
7. **Human-owed (KA):** the `harness/run.sh` `EXPECT_NONPASS` I10 amendment
   (spurious RED + `harness/GATE_RED` every census run); optionally the roughness
   encode nit (material_tx.a 0.68 vs 0.61, visually negligible, noted r44).

## Deliverables the human explicitly expects

Screenshots proving each milestone (not just numbers) sent via file delivery;
premise corrections stated plainly; the ledger + fix_plan kept truthful; D-10
applied without per-item asking; exact commit trailers; zero em dashes anywhere.
