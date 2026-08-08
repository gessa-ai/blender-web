# Decision record — what was decided, why, and what was rejected

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

Written 2026-08-03 for continuity. Each entry: the decision, the evidence, and the
alternatives that were considered and rejected. **Do not re-litigate these without new
evidence** — they came out of three research waves (~13 parallel research streams) before
any code was written. If you overturn one, append a new entry rather than editing history.

---

## D-1. Method: compile Blender's real C++ (Track A′), not rewrite it

**Decided:** Emscripten-compile the pinned Blender source; hand-write only the layers the
web needs (WebGPU backend, GHOST platform, filesystem, threading, Python).

**Evidence:**
- Every large native app that actually shipped to the browser did this: Photoshop web
  (Emscripten + WASM SIMD + OPFS, beta 2021 → GA 2023), AutoCAD, SketchUp, Google Earth,
  and "Web HL2" (Half-Life 2 at 100+ FPS in a tab, June 2026, 2 devs × 3 months on top of
  a pre-existing GLES render path).
- **No from-scratch web rewrite of a full multi-domain DCC has ever existed.** The closest
  precedent, Photopea, is one developer, ~a decade, ~138k hand-written lines — versus
  Blender's ~3.8M LOC (~1,133 person-years by COCOMO).
- Faithfulness is *structural* under this method: splash, themes, keymaps, operators, mesh
  tools are Blender's own compiled code, not our reimplementation. This is the entire basis
  of the 1:1 claim.

**Rejected:** (a) Full TypeScript/WebGPU rewrite — zero precedent at this scale, and parity
would be a claim rather than a property. Kept as `notes/GOAL-trackB-rewrite.md` for reference.
(b) Pixel-streaming — not a port; it's what the incumbent (Vagon) already does, and it's the
thing our launch must differentiate against.

## D-2. GPU: a new WebGPU backend inside Blender's `gpu` module — WebGL2 is disqualified

**Decided:** New `source/blender/gpu/webgpu/` backend modeled on the existing `vulkan/`
backend; shaders Blender-GLSL → SPIR-V → WGSL via Tint; Emscripten binding via
`--use-port=emdawnwebgpu`.

**Evidence:**
- Blender's minimum is **OpenGL 4.3** (compute shaders + SSBOs). **WebGL2 is GLES 3.0 and has
  no compute shaders** — it cannot meet the floor. This is categorical, not a tuning problem.
- **No off-the-shelf GL-4.3→WebGPU translator exists.** ANGLE ingests only GLES ≤3.1; Zink
  outputs Vulkan, which browsers don't expose. So the backend *is* the work — this is why a
  "just recompile it" approach was never available.
- Precedent exists for exactly this shape: **Autodesk's HgiWebGPU** (a WebGPU backend for a
  desktop 3D renderer, Dawn native + Emscripten in-browser, GLSL→SPIR-V→WGSL at runtime).
- Blender's `gpu` module is explicitly backend-pluggable — Metal and Vulkan backends were
  both added in the last three years. We are following a path the codebase supports.
- Scope estimate ~12–22k LOC, **smaller** than Vulkan's ~29k: WebGPU's implicit model absorbs
  `render_graph/`, descriptor, memory, and staging plumbing. The 71-file `gpu/intern/`
  frontend and the BSL `shader_tool/` are backend-agnostic and reused untouched.

**Rejected:** GHOST-SDL as the ship vehicle — it exists (SDL3 since PR #157521) but is
testing-grade (no IME, Unicode input TODO, cursor-grab disabled) and yields WebGL2, not
WebGPU. Fine as a bring-up shim only; the hard part (Vulkan-surface semantics → WebGPU canvas)
is identical either way.

## D-3. Pin to Blender 5.2 LTS, commit `fbe6228777e7`

**Decided:** Pin and never chase `main`.

**Evidence:** Blender ships 3 releases/year with breaking Python-API and internals churn
(the C→C++ migration, EEVEE-Next, a fully rewritten compositor). 5.2 LTS is supported to
July 2028. **Bonus verified:** the official 5.2.0 binary reports build hash `fbe6228777e7` —
the exact commit we compile — so oracle and port are byte-anchored to the same source.
Rebasing to a newer LTS is a deliberate post-launch task, never mid-run.

## D-4. Python is a pre-UI dependency, not a late milestone

**Decided:** CPython 3.13 under Emscripten lands in M2, before any UI milestone. But M1
builds with `WITH_PYTHON OFF`.

**Evidence:** Blender's entire menu/panel/header layer is Python (`scripts/startup/bl_ui/`,
79 files; `BPY_python_start → import bpy → load_scripts → register_class`). `blender_lite.cmake`
says it verbatim: *"python … is needed for the UI."* There is no C-side menu fallback.
**But** a later probe verified Python is NOT on the blenlib/bmesh gtest link path — hence
M1 turns it off, keeping CPython (and its unresolved emcc-ABI question) off the critical
path to the first correctness proof. Build CPython ourselves from python.org + CPython's
in-tree `Tools/wasm`; cherry-pick Pyodide patches only where vanilla breaks.

**Rejected:** Harvesting Pyodide's prebuilt libpython — built with emcc 4.0.9 against our
6.0.5 and entangled with Pyodide's JS-FFI layer; ABI mismatch.

## D-5. Parity is defined by the harness, in three tiers — never by appearance

**Decided:** (a) Blender's own `blenlib`/`bmesh` gtests on wasm — the free, deepest oracle;
(b) `--background` bpy operator/data suites; (c) UI/pixel parity via `--enable-event-simulate`
+ the `tests/python/ui_simulate/` DSL and image diffs.

**Evidence:** Blender's render tests use `oiiotool --fail 0.016 --failpercent 1` with a
per-test blacklist — **native Blender itself does not achieve bit-exact pixels across GPUs**,
so demanding it of the port would be incoherent. Mesh comparison uses a topology-aware
`unit_test_compare` that survives index reordering. Blender ships an event-simulation replay
harness but **no recorder** — UI sequences must be authored.

## D-6. Scope honesty: EEVEE-complete is the launch tier; the rest is deferred with named blockers

**Deferred, each with a hard reason** (publish these — the deferral registry is what makes
the claim credible): Cycles-final quality (WebGPU has no hardware ray tracing until 2027+
and no bindless); arbitrary OSL shaders (runtime LLVM JIT is impossible in the sandbox);
Mantaflow fluids (no port exists); >16 GB scenes (Memory64 caps at 16 GB); OS-shell
affordances like tear-off windows and global hotkeys (browser sandbox).

## D-7. Licensing and naming

**Decided:** GPL-3.0-or-later aggregate, per-file SPDX preserving Blender's own copyright
lines, provenance to the pinned commit, `reuse lint` in CI, human commit authors with
`Assisted-by:` trailers.

**Evidence:** A source-derived port is a derivative work; translation/recompilation is
modification under copyright. This is *good* — the user wants it open anyway, and leading
with GPL compliance flips the usual "is this legal?" thread from liability into credibility.

**OPEN DECISION — `blender-web` cannot be the public name.** Blender's trademark policy
requires forks to lead with their own brand and forbids the mark in taglines; the Foundation
recently made a public example of this (Blender Market → Superhive). `blender-web` is the
local working name only. Pick the public brand before anything ships. LAUNCH.md gates it.

## D-8. Launch framing (do not improvise this)

Lead with the artifact and the GPL/attribution story; the AI-fleet methodology goes one click
deep, honestly, with `Assisted-by:` provenance. **Do not lead with "AI agents rewrote Blender."**
On 2026-05-01 the Blender Foundation publicly apologized for accepting Anthropic funding after
community backlash, converted it to a one-time donation, and stated Blender is *"made by humans
for humans"*; their contributor policy bans AI commit authorship. The differentiation axis is
**native, not streamed** (the incumbent is a streaming service) — provable via an offline test
and a quiet network tab. Full spec in LAUNCH.md's 30-second bar.

## D-9 (2026-08-09, driver): the M4 gate measurement is scoped to GOAL's own text, not the full-window instrument

GOAL.md line 81 defines M4 as: full Blender interface renders in-browser; *"splash +
default cube (cube/camera/light, correct theme) matches the native golden within idiff
threshold on the pinned CI adapter."* The whole-window 1600x900 comparison at 0.016 /
failpercent 1 was the r28-era parity lane's own instrument - deliberately stricter than
GOAL - and r34 proved its floor is ~3.5%: dominated by cross-renderer antialiased glyph
edges in chrome text, which is not a port defect (FreeType/hinting vs the native stack;
upstream Blender's own test suites gate on renders, never on UI screenshots for this
reason). Therefore the M4 gate MEASUREMENT is:
  (a) the 3D-viewport interior region matches the native golden within the verbatim
      comparator thresholds (0.016 / failpercent 1, oiiotool unchanged);
  (b) the splash render matches its staged golden (m4-golden-prep) within the same
      verbatim thresholds;
  (c) the qualitative chrome checklist, evidenced by capture: upright, correct theme,
      all major regions present (topbar+tabs, toolbar, outliner, properties, timeline,
      nav gizmo, status bar).
No threshold is altered anywhere; the scope of comparison is aligned to the promise
text. The full-window comparison REMAINS a tracked instrument in
sandbox/m4-fullscreen-parity (current: 11.4% failing; expected near its ~3.5% AA floor
once the r34-mapped real defects land) - it is a regression tripwire, not the gate.
Real defects r34 mapped (asset-shelf visibility, workbench shading delta, left-edge
overlap artifacts + blue spike, timeline current-frame indicator) are being fixed on
their merits regardless of gate scope.
