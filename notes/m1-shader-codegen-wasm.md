<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M1 — GPU shader codegen (shader_tool) blocks blenkernel/depsgraph/blentranslation/animrig

Date: 2026-08-03. Owner: build-deps worker.
Deliverable target: bf_blenkernel, bf_depsgraph, bf_blentranslation, bf_animrig → wasm.
Outcome: **BLOCKED. 0/4 archives green.** Single root blocker: the GPU shader-info
codegen host tool `shader_tool` does not run correctly under wasm/node.
WIP progress preserved in `patches/wip-0007-shader-codegen-hosttool-wasm.patch`
(kept OUT of the verified 0001-0006 series — no green target). upstream pristine.

## Why all 4 archives are gated on GPU shader codegen (not avoidable by config)

Each of the 4 libs PRIVATE-links `bf::draw` and/or `bf::gpu`
(`blenkernel/CMakeLists.txt` LIB list: `bf::draw`, plus gpu via the web). CMake
therefore attaches, as **order-only object dependencies** of every one of that
lib's `.cc.o` files, the generated-source targets of those link deps:

    || cmake_object_order_depends_target_bf_gpu_shaders
    || cmake_object_order_depends_target_bf_draw_shaders
    || cmake_object_order_depends_target_bf_compositor_shaders
    || cmake_object_order_depends_target_bf_imbuf_opencolorio_shaders
    (+ bf_dna, bf_dna_defaults, bf_editor_datafiles, bf_nodes_compositor_generated)

Verified for ALL four targets via `ninja -t query cmake_object_order_depends_target_<t>`.
So ninja will not compile a single blenkernel/depsgraph/blentranslation/animrig
object until the shader codegen for gpu+draw(+compositor) has fully succeeded —
even though **0 of these libs' own TUs `#include` any generated `*_infos.hh`**
(`grep -rl _infos.hh blenkernel/` = 0). The dependency is a legitimate
consequence of real link edges (not a blanket global add_dependencies), so it
CANNOT be cleanly severed without removing genuine `bf::draw`/`bf::gpu` link deps.

The next wave (bmesh_core_test → ~150-archive closure) links bf_gpu/bf_draw
directly, so this blocker gates the **entire M1 tier-(a) bmesh_core gate**, not
just this worker's 4 archives.

## The tool: `shader_tool` (source/blender/gpu/shader_tool/)

A build-time host codegen tool. Reads `*.bsl.hh` / `*_infos.hh` shader-create-info
sources and emits `.hh/.info/.tmp` (then `datatoc` → `.c`, compiled into
`bf_gpu_shaders`/`bf_draw_shaders`). Invoked per-shader via
`add_custom_command(COMMAND "$<TARGET_FILE:shader_tool>" ...)` in
`build_files/cmake/macros.cmake:1179` (datatoc at 1118/1142/1184). Output is
target-independent TEXT — it does NOT bake target ABI (unlike makesdna).

## Three layers hit, in order (2 fixed, 1 unresolved)

### Layer 1 — rc=126 "Permission denied" (host-tool wiring) — FIXED
Same class as makesdna/makesrna (patch 0003). `shader_tool.js`/`datatoc.js` were
executed directly. Fix (WIP patch, both halves):
- `macros.cmake`: prepend `${CMAKE_CROSSCOMPILING_EMULATOR}` before the 4
  `$<TARGET_FILE:...>` invocations (shader_tool ×1, datatoc ×3).
- `blender_web_host_tool(datatoc)` / `(shader_tool)` after their `add_executable`
  (datatoc/CMakeLists.txt, gpu/shader_tool/CMakeLists.txt) → node link profile.
Result: 906 rc=126 failures → 0. shader_tool now runs under node.

### Layer 2 — SIMD lexer has no correct wasm path — PARTIALLY FIXED
shader_tool's `lexit` lexer (`lexit/simd.hh`, `lexit/lexit.cc`) is vectorized:
`#if defined(__ARM_NEON)`→NEON, `(__x86_64__||_M_X64)&&__SSE4_2__`→SSE4.2, and the
whole `lexit::simd` namespace is `#if USE_NEON||USE_SSE4_2` with **NO scalar
`#else`**. Under wasm neither is defined → the lexer falls to a scalar tokenizer
path (`tokenize_scalar`) that is **buggy under wasm**: with asserts live it aborts
(`scope.hh:369 assert(this->type()==ScopeType::Attributes)` ×156), and with asserts
off (`NDEBUG`) it **infinite-loops** on eevee shaders (observed 32 shader_tool node
procs all hung ~6.5 min).
Fix (WIP patch): enable Emscripten's SSE4.2→wasm-SIMD emulation for shader_tool —
widen the `simd.hh` guard to `(...|| defined(__EMSCRIPTEN__)) && defined(__SSE4_2__)`
and add `-msse4.2 -msimd128` to the shader_tool target (EMSCRIPTEN-gated). Verified:
`-msse4.2 -msimd128` makes emcc define `__SSE4_2__/__SSE4_1__/__SSSE3__` and compile
every intrinsic simd.hh uses (`_mm_shuffle_epi8`, `_mm_alignr_epi8`, `_mm_blendv_epi8`,
`_mm_movemask_epi8`, `_mm_extract_epi8`). Result: the hang is gone for MOST shaders;
`draw_curves_infos` and the bulk generate cleanly. Assert-abort count dropped
156 → ~1 (in a 2-file probe).

### Layer 3 — residual tokenization discrepancy on complex EEVEE shaders — UNRESOLVED
With the SSE path active, ~6 complex EEVEE shaders still fail — shader_tool emits a
legitimate-looking diagnostic on VALID attributes:

    eevee_closure.bsl.hh:101:37: This attribute requires no argument   [[resource_table]]
    eevee_deferred_eval.bsl.hh:28:5: This attribute requires no argument  [[smooth]]
    eevee_depth_of_field_accumulator.bsl.hh:59:5: This attribute requires no argument  [[compilation_constant]]
    (also eevee_bxdf_microfacet, eevee_camera_lib)

i.e. the parser wrongly sees an argument after an argument-less attribute — a
residual mis-tokenization. `foreach_attribute` does
`attr[1] == '(' ? attr[1].scope() : Scope(*parser_)`; `attr[1]` is being resolved to
the wrong token. Root cause is almost certainly either (a) a specific SSE-intrinsic
emulation edge case in emscripten (e.g. `_mm_movemask_epi8`/`_mm_shuffle_epi8`) that
differs from x86 on certain byte patterns, or (b) the SIMD/scalar **tail** boundary
(`lexit.cc:630 "Finish tail using scalar loop"` — the scalar tail is the same buggy
path). NOT further diagnosed — this is deep GPU/shader-tooling work (M3-adjacent),
beyond a build-deps compile-fix worker, and past 3 distinct fix attempts on this
tool (wiring, NDEBUG, SSE).

NOTE: `NDEBUG` on host tools was tried (native Release builds these tools with
NDEBUG; our WITH_ASSERT_RELEASE=ON strips it) — it silences the benign scope.hh
assert but converts the underlying bad-state into an **infinite loop**, which is a
strictly worse failure mode for diagnosis. NOT kept. The WIP patch leaves asserts
LIVE so the failure is a fast, precise abort at scope.hh:369.

## Recommended paths forward (driver decision — likely an ADR)

1. **Run shader_tool + datatoc as NATIVE host binaries** (not wasm-under-node).
   Their output is target-independent text, so a native build produces identical
   headers and sidesteps every wasm-lexer bug. This is the clean architecture for
   text-codegen host tools (makesdna/makesrna must stay wasm — they bake ABI). Cost:
   a native host-tools sub-build (separate toolchain) — Blender's cross-build has no
   such mechanism at the pin. RECOMMENDED.
2. **Finish the wasm lexer port**: give `lexit/simd.hh` a correct scalar `#else`
   fallback, OR isolate the residual SSE-emulation/tail discrepancy. Deep, GPU-domain.
3. Investigate whether the M1 GPU-stub posture can legitimately exclude the eevee
   engine's shaders from the codegen set (they are pure-render; M1 has no renderer) —
   but this touches Blender's shader target composition and risks the eventual bf_gpu
   build; verify against a native oracle before trusting any trimmed create-info set.

## Receipts
- rc=126 (pre-wiring): ledger/buildlogs/20260803T202541.log (906 × code=126).
- post-wiring, scalar asserts: ledger/buildlogs/20260803T202923.log (156 × scope.hh:369).
- post-SSE, residual eevee parse errors: ledger/buildlogs/20260803T210138.log
  (6 × "This attribute requires no argument"; then mass hang under NDEBUG).
- SSE probe: `em++ -msse4.2 -msimd128` defines __SSE4_2__ + compiles all intrinsics.
- upstream/ restored pristine (git -C upstream status --porcelain empty); 0001-0006
  re-apply --check clean; wip-0007 applies clean on top of the series.

## ADR-002 byte-identity audit — VERDICT: PASS (2026-08-03, native-tool arm)

Native tools built with host clang (Apple clang 17, arm64 -> `lexit` NEON path, the
path Blender's own macOS CI exercises) into `build-hosttools/bin-native/{shader_tool,
datatoc}`. Both are fully self-contained (datatoc: stdlib only; shader_tool: only its
own local headers — no blenlib/GPU/external link deps), so a minimal direct clang++
compile suffices.

Native tool VALIDATION (the previously-blocking shaders): native shader_tool
processes ALL of eevee_closure, eevee_bxdf_microfacet, eevee_deferred_eval,
eevee_depth_of_field_accumulator, eevee_bxdf_lut_lib (which HUNG under wasm),
draw_curves_infos — every one rc=0 with complete output.

### datatoc audit — byte-identical
- ALL 752 shader `.tmp` (text) inputs: native == wasm datatoc  -> 752/752 identical.
- 25 binary data files (release/datafiles .png/.dat/.ttf/.svg; the data_to_c path):
  25/25 identical. datatoc has no wasm defect.

### shader_tool audit — target-independence CONFIRMED
Two methods:
1. Controlled fresh head-to-head (run BOTH tools now on the same inputs, diff
   .tmp/.hh/.info, ignore .d absolute paths): 66/66 byte-identical across a
   stratified sample (gpu, draw/intern, workbench, overlay, gpencil, image, select,
   eevee subset).
2. Native vs ALL existing wasm-generated artifacts (527 gpu/draw): 466 identical,
   44 differing, 17 no-input/native-skip.

The 44 differing were triaged (re-run current wasm fresh, classify) — NONE are
genuine target-dependence:
- **20 wasm-cannot-generate** (crash/hang) — the eevee mis-tokenizers + others.
  EXCLUDED by ADR-002 (wasm output known-broken; this is why the ADR exists).
- **24 wasm-silent-corruption** (wasm runs to rc=0 but emits WRONG bytes; native is
  the complete/correct superset). Two signatures, both inspected:
  * 16 files: native emits `<Struct>_ctor_() {...}` constructors + `#line` directives
    that wasm OMITS (wasm side is blank where native has content).
  * 8 files (mostly `*_shared.hh`, `osd_patch_basis.glsl`): wasm emits DEGENERATE
    `#define <X>_host_shared_uniform_ <X>` fallback aliases INSTEAD of native's
    proper `_ctor_()` + `#line`. The real build argv is identical for both; neither
    build defines WITH_GPU_SHADER_ASSERT — so this is the wasm lexer/parser
    mis-handling struct defs, not a flag or target difference.
- **0 genuine target-dependence** (no case of both-sides-clean-but-validly-different).

CONCLUSION: shader_tool/datatoc output is target-INDEPENDENT text — identical
wherever the wasm tool functions correctly. The wasm shader_tool is simply
unreliable (crashes AND silently corrupts a broader set than the 6 known eevee
crashers), so ADR-002's native-tool route is validated AND necessary: native output
is the correct reference (== Blender macOS CI). Proceeding to wire the native tools
into the wasm build and resume the archive grind.

## M1.13/M1.14 RESULT — all four archives GREEN via ADR-002 native tools

Native tools (build-hosttools/bin-native/, via scripts/build-hosttools.sh) + the
patch series produce all four target archives on wasm32:

| target | bytes | members | notes |
|---|---|---|---|
| bf_blenkernel      | 34,379,340 | 288 | needed patch 0008 (image.cc/IDCacheKey ILP32) |
| bf_depsgraph       |  1,976,410 |  68 | no fixes |
| bf_blentranslation |     46,954 |   5 | WITH_INTERNATIONAL=OFF — small, not a stub |
| bf_animrig         |    591,922 |  22 | no fixes |

Two build-integration blockers surfaced once native codegen unblocked the path, both
fixed (see porting-patterns.md Class 3 / Class 4):
1. `discover_nodes.py` (node-registration codegen) invoked directly -> rc 126. It is
   a HOST python build script with no shebang / no +x; PYTHON_EXECUTABLE was empty
   (WITH_PYTHON=OFF, emscripten sets no host interpreter). Fix: platform_wasm.cmake
   sets a host PYTHON_EXECUTABLE (emsdk-bundled python 3.13).
2. `image.cc` `constexpr size_t runtime_base_id = size_t(1) << 32u` -> wasm32 ILP32
   (patch 0008).

Full cycle verified: upstream restored pristine, 0001-0008 re-apply --check clean,
all 4 rebuilt green from the clean re-apply (ledger/buildlogs/20260804T014155.log),
upstream pristine after final restore.
