<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# deps: runtime shader chain for the BROWSER WebGPU backend (shaderc + Tint → wasm)

The browser WebGPU backend translates Blender's GLSL at runtime:

    GLSL → shaderc(SPIR-V 1.3, env vulkan_1_1) → Tint(ReadIR → ProgramFromIR → Generate) → WGSL

Natively the in-tree `source/blender/gpu/webgpu/wgpu_shader_compiler.cc` links
Dawn's precompiled Tint + Blender's precompiled shaderc dylib. The **browser**
build needs both as cross-compiled static wasm archives. This note records how
they were built, the SPIRV-Tools duplication resolution, and three load-bearing
wasm findings.

Pin: Blender 5.2 `fbe6228777e7`; Dawn/Tint `chromium/7989 @ 36cf1fae`
(`build-dawn/dawn`, shared with the M3 native probe). Built by
`scripts/deps/tint.sh` + `scripts/deps/shaderc.sh` (idempotent).

## Versions

| component | version / commit | license |
|---|---|---|
| shaderc | v2025.4 (md5 `02208e374e610808c4ca3b1e7627b82d`) | Apache-2.0 |
| Tint | Dawn `chromium/7989 @ 36cf1fae` | BSD-3-Clause |
| SPIRV-Tools (SHARED) | Dawn pin `a9cdf5bdd25d516294b5c25502b67e6116ed7eb5` | Apache-2.0 |
| SPIRV-Headers | Dawn pin `4015a331f5ffd6fc5c6fa7b03e08fb4a692491d7` | MIT |
| glslang (shaderc front-end) | Dawn pin `8d6dd0e41424c25806ca20523430f2e4c3aeb1a1` | BSD-3-Clause AND Apache-2.0 AND MIT |
| abseil (Tint dep) | Dawn pin `63f52bfdb2ebc0ef3add13b98af45778d0040278` | Apache-2.0 |

## Sizes (harvested to lib/wasm)

| bundle | path | archives | size |
|---|---|---|---|
| Tint (+ single SPIRV-Tools + abseil) | `lib/wasm/tint/lib` | 63 | 25 MB |
| shaderc (+ glslang) | `lib/wasm/shaderc/lib` | 4 | 9.2 MB |
| **total lib/wasm growth** | | | **~34 MB** |

Largest: `libSPIRV-Tools-opt.a` 8.7M, `libglslang.a` 9.3M, `libSPIRV-Tools.a` 3.7M.
(glslang is monolithic at this pin — `MachineIndependent`/`GenericCodeGen`/
`OSDependent`/`SPIRV` are consolidated into `libglslang.a`; `libSPIRV.a` is a 574 B
stub kept only for link completeness.) Ordered link lists ship alongside the
archives: `lib/wasm/tint/tint-archives.txt`, `lib/wasm/shaderc/shaderc-archives.txt`.

## THE SPIRV-Tools single-copy discipline (the #1 expected trap)

**Collision.** shaderc bundles glslang + SPIRV-Tools; Tint's SPV reader ALSO links
SPIRV-Tools (its `SplitCombinedImageSamplerPass`). Two static `libSPIRV-Tools{,-opt}.a`
on one wasm link line = duplicate `spvtools::*` symbols. Natively this is dodged by
linking Blender's shaderc *shared* dylib (bundled symbols PRIVATE); a static wasm
link has no such hiding (`notes/gpu-t7pre-findings.md` §2).

**What actually collides (measured, `llvm-nm`):** `libSPIRV-Tools-opt.a` exports
**1580** `spvtools::*` text symbols; `libshaderc_util.a` has **17** *undefined*
`spvtools::*` references; Tint's reader/opt objects reference the same namespace.
Any second copy of those 1580 definitions on the link line is a hard duplicate.

**Chosen discipline — single SHARED SPIRV-Tools, by construction.** Build shaderc
against the SAME SPIRV-Tools + SPIRV-Headers SOURCE that Tint uses (Dawn's checkout)
via shaderc's own `SHADERC_SPIRV_TOOLS_DIR` / `SHADERC_SPIRV_HEADERS_DIR` knobs — the
same knobs Blender's `build_environment/cmake/shaderc.cmake` uses to substitute deps.
glslang is shaderc-only (Tint uses no glslang), so it stays on Dawn's matched glslang
pin. shaderc's SPIRV-Tools objects therefore carry the *identical* symbols as Tint's,
so exactly **ONE** `libSPIRV-Tools{,-opt}.a` satisfies both consumers. That single
copy ships in `lib/wasm/tint/lib`; `scripts/deps/shaderc.sh` deliberately does NOT
harvest a second one (it asserts none leaked into the shaderc bundle). Verified: the
combined wasm link resolves with **zero duplicate and zero undefined symbols**, and
the chain runs correctly. This is preferred over "link two, drop one" because
identical-source guarantees no `spvtools` ODR/ABI skew (shaderc v2025.4 and Dawn pin
DIFFERENT spirv-tools commits — `19042c89` vs `a9cdf5bd` — so cross-linking their
mismatched objects would be an ODR hazard, not just a duplicate).

Consumer link order: shaderc archives → Tint archives (carrying the single
SPIRV-Tools) → all wrapped in one `-Wl,--start-group … --end-group` so residual
cross-references resolve order-independently.

## Three load-bearing wasm findings (each would silently break T7)

1. **Dawn's CMake refuses SPIRV-Tools under Emscripten.** `dawn/third_party/
   CMakeLists.txt:119` does `if (EMSCRIPTEN) return()` BEFORE the SPIRV-Tools /
   SPIRV-Headers block (:126-145) — Dawn only ever expected emscripten for its
   JS-binding *samples*, which never need Tint's SPIR-V reader. So an `emcmake`
   configure with `TINT_BUILD_SPV_READER=ON` still never configures SPIRV-Tools,
   and Tint's parser fails on the missing generated `core_tables_header.inc`. FIX
   (non-invasive; the Dawn checkout is shared): `scripts/deps/tint.sh` generates a
   thin wrapper `CMakeLists.txt` that `add_subdirectory`s SPIRV-Headers + SPIRV-Tools
   as targets (replicating Dawn's own flags) BEFORE `add_subdirectory(dawn)`, so
   Tint's `SPIRV-Tools`/`SPIRV-Tools-opt` link deps resolve and the `core_tables`
   codegen runs. Build SPIRV-Tools first to defeat the generated-header race.

2. **Tint's IR validator is disabled for wasm.** Dawn defaults
   `TINT_ENABLE_IR_VALIDATION_ASSERTS=ON` (CMakeLists.txt:276); it runs INSIDE
   `ReadIR`. It is an internal IR self-consistency assert — it never shapes the
   output. Under wasm its recursive Switch/Castable dispatch overflowed the stack
   (finding 3) and trapped. `tint.sh` sets it (and `TINT_ENABLE_IR_DUMPING`) OFF —
   the correct posture for a shipping browser runtime. Output is unaffected: the
   wasm WGSL is byte-identical to the native chain (which has the validator ON).

3. **`-sSTACK_SIZE` is load-bearing — emscripten's 64 KB default overflows.**
   (`settings.js:113 var STACK_SIZE = 64*1024`.) glslang's recursive preprocessor/
   parser and Tint's recursive IR passes blow a 64 KB stack; the overflow corrupts
   the heap and surfaces as *bogus* "null function or function signature mismatch"
   / "invalid free → abort" traps far from the real cause. `-sSTACK_SIZE=32MB` (or
   any multi-MB value) fixes it. **T7 integration MUST give the shader-compile call
   path a multi-MB stack** (the main Blender wasm already runs `PROXY_TO_PTHREAD`;
   set `STACK_SIZE`/`DEFAULT_PTHREAD_STACK_SIZE` accordingly).

## Link smoke + native parity (verified)

`sandbox/wgpu-shader-wasm-smoke/{smoke.cc,build.sh}`. One GLSL vertex shader with a
UBO → shaderc (env vulkan_1_1 → SPIR-V 1.3) → Tint → WGSL, the SAME source built two
ways:

- **native reference:** Blender's precompiled shaderc dylib + native Tint archives →
  498 bytes WGSL.
- **wasm:** the harvested archives in one `--start-group`, `-sSTACK_SIZE=32MB`, run
  under node → 498 bytes WGSL, contains `@group(0u) @binding(0u) var<uniform> ubo`.
- **`diff` = 0: the wasm WGSL is BYTE-IDENTICAL to the native chain.** No divergence.

(Same shaderc *version* both sides — v2025.4 — and the same Dawn/Tint pin; the wasm
side's glslang differs from Blender's precompiled shaderc's glslang, yet the emitted
SPIR-V→WGSL matched byte-for-byte for this shader.)

## Build posture (both bundles)

emcc 6.0.5, `-pthread`, static archives, JS-EH (`-fexceptions`) at the consumer link.
Tint objects are its own `-fno-exceptions -fno-rtti` (EH-model-neutral — the
`-fexceptions` final link is unaffected). No source patches to the Dawn checkout, no
host `brew` deps. Build trees: `build-deps/tint`, `build-deps/shaderc` (own trees, not
ninja-locked). Cold build ≈ Tint 136 s, shaderc 36 s.

## For T7 integration (in-tree wgpu_shader_compiler.cc, browser build)

- Link the two ordered archive lists in one `--start-group`; ship the single
  SPIRV-Tools from the tint bundle only.
- `-sSTACK_SIZE` multi-MB on the main blender.wasm link (finding 3).
- Tint validator/dumping OFF (finding 2) — no effect on output.
- Include roots: `-I lib/wasm/shaderc/include` (shaderc/*.hpp) and `-I build-dawn/dawn`
  (Tint `src/tint/...` headers, consumed from the pinned Dawn source as native does).
- shaderc env stays `vulkan_1_1` / SPIR-V 1.3 (`notes/gpu-dawn-probe.md` §4a) — NOT 1.2.
