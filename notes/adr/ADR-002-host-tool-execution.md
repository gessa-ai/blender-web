<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# ADR-002: Host code-generator execution policy — ABI-baking tools run as wasm, text/byte tools run native

Date: 2026-08-03. Status: ACCEPTED (driver). Trigger: M1.13 worker blocked 0/4 core libs on
shader codegen (notes/m1-shader-codegen-wasm.md) — every blenkernel/depsgraph/blentranslation/
animrig object is order-only-gated on `bf_gpu_shaders`/`bf_draw_shaders` (real link edges to
bf::gpu/bf::draw), and the wasm-compiled `shader_tool` mis-tokenizes ~6 EEVEE shaders under
node even after SSE4.2→wasm-SIMD emulation fixes (residual lexer divergence, 3 fix attempts).

## Policy

Blender's build compiles AND executes its own code generators. Under the wasm cross-build,
generators split into two classes with different execution requirements:

1. **ABI-baking generators — MUST run as wasm32 under node:** `makesdna`, `makesrna`.
   Their *output encodes target ABI* (struct sizes/offsets/alignment). Running them native
   would bake LP64 layouts into wasm builds — exactly the Scene.customdata_mask 5012-vs-5016
   class of bug that patch 0002 fixed. Wiring: patch 0003 (`CMAKE_CROSSCOMPILING_EMULATOR` +
   `blender_web_host_tool()`); both proven under node (makesrna first executed successfully
   2026-08-03).
2. **Target-independent text/byte generators — run as NATIVE host binaries:** `shader_tool`
   (GLSL create-info → C++ string headers), `datatoc` (file bytes → C arrays), and later
   `msgfmt` (INTERNATIONAL). Their output is byte-identical regardless of host word size or
   endianness-free (text; byte-for-byte embedding). Building them wasm buys nothing (they
   never ship) and costs correctness (the lexit SIMD lexer has NO scalar fallback — SSE4.2/
   NEON only — and its wasm-SIMD emulation path mis-tokenizes; natively on this arm64 host it
   uses the NEON path Blender's own macOS CI exercises).

## Verification requirement (per tool, once)

Byte-identity audit: for outputs the wasm-built tool DID generate correctly, `diff` them
against the native tool's outputs — must be identical. For datatoc this covers all outputs;
for shader_tool the subset that generated cleanly pre-blocker. Any diff = the tool is NOT
target-independent = revert to wasm execution for it and diagnose.

## Rejected

- **Finishing the wasm lexer port** (scalar fallback / SSE-emulation debugging): build-time
  tool never shipped to users; zero product value; open-ended debugging of an upstream SIMD
  header. The upstream portability gap is noted in notes/m1-shader-codegen-wasm.md.
- **Excluding EEVEE shaders from M1 codegen:** touches shader target composition, only defers
  the problem to M4/M6, risks silent divergence from the native oracle.

## Consequences

- A small native host-tools build tree (`build-hosttools/`, clang, gitignored) builds
  `shader_tool` + `datatoc`; the wasm tree's custom commands invoke those native binaries
  when `EMSCRIPTEN` (patch to macros.cmake sites replaces the emulator-prefix for these two
  tools). makesdna/makesrna wiring unchanged.
- The worker's SSE4.2-emulation widening of `lexit/simd.hh` is dropped from the patch series
  (kept in notes as an upstream finding) — patch surface stays minimal per GOAL.
- msgfmt adopts the native route when WITH_INTERNATIONAL returns (post-launch tier).
