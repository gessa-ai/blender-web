#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Link the browser GPU render harness: the REAL Blender WebGPU backend
# (build-wasm-gpu/lib/libbf_gpu.a) + its minimal dep closure + the emdawnwebgpu web
# context, into a wasm binary that renders a triangle offscreen in a tab.
#
# Flags per the coordinator: --use-port=emdawnwebgpu + WGPU_TINT_LIBS + shaderc + JS-EH
# + -sSTACK_SIZE=32MB (the shader-path stack finding, notes/deps-shader-chain.md).
set -uo pipefail
ROOT="/Users/paws/blender-web"
HARNESS="$ROOT/sandbox/gpu-render-harness"
BWG="$ROOT/build-wasm-gpu"
OUT="$ROOT/build-deps/gpu-harness"
mkdir -p "$OUT"
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

FLAGS=$(cat /private/tmp/claude-501/-Users-paws-blender-web/842d1baa-b07e-4763-8a60-5cf78d22669c/scratchpad/flags.txt)
ADD="--use-port=emdawnwebgpu -DWITH_WEBGPU_BACKEND -I$ROOT/upstream/source/blender/gpu/intern -I$ROOT/upstream/source/blender/gpu/webgpu -I$ROOT/upstream/intern/ghost -I$ROOT/upstream/intern/ghost/intern -I$HARNESS -Iplatform_web/ghost -isystem $ROOT/build-dawn/dawn -isystem $ROOT/lib/wasm/shaderc/include"

echo "== compile TUs =="
eval em++ $FLAGS $ADD -c "$HARNESS/gpu_render_harness.cc" -o "$OUT/main.o" || exit 1
eval em++ $FLAGS $ADD -c "$HARNESS/wgpu_context_web.cc"   -o "$OUT/wgpu_context_web.o" || exit 1
eval em++ $FLAGS $ADD -c "$HARNESS/harness_stubs.cc"      -o "$OUT/stubs.o" || exit 1
# The old "shader-source comments" blocker was a MISDIAGNOSIS: the wasm build's glsl_to_c
# already runs the NATIVE host shader_tool (ADR-002, BLENDER_WEB_HOST_TOOLS_DIR), whose
# remove_comments() strips every shader before datatoc (verified: all 904 *.tmp are
# comment-free). The real blocker was a wasm32 width bug in gpu_shader_dependency.cc: the
# GPUSource() "no comments" assert compared StringRef::find() (int64_t, not_found=-1)
# against std::string::npos (32-bit 0xFFFFFFFF on wasm), firing spuriously on the FIRST
# source. Fixed at root cause by patches/0060-gpu-shader-dependency-wasm32-npos.patch
# (__EMSCRIPTEN__-guarded). We link the REAL gpu_shader_dependency.cc TU from libbf_gpu.a.
eval em++ $FLAGS $ADD -c "$ROOT/platform_web/ghost/GHOST_ContextWGPUWeb.cc" -o "$OUT/ghost_ctx_web.o" || exit 1
eval em++ $FLAGS $ADD -c "$ROOT/upstream/intern/ghost/intern/GHOST_Context.cc" -o "$OUT/ghost_ctx.o" || exit 1

# WGPU shader-chain archives (single SPIRV-Tools discipline): shaderc then tint.
WGPU_LIBS=()
while IFS= read -r a; do WGPU_LIBS+=("$ROOT/lib/wasm/shaderc/lib/$a"); done < "$ROOT/lib/wasm/shaderc/shaderc-archives.txt"
while IFS= read -r a; do WGPU_LIBS+=("$ROOT/lib/wasm/tint/lib/$a"); done < "$ROOT/lib/wasm/tint/tint-archives.txt"

echo "== link =="
# Order: my override objects FIRST (wgpu_context_web.o overrides the stale one in
# libbf_gpu.a), then the Blender archive closure + shader chain in one group.
em++ -std=c++20 -pthread -fexceptions -funsigned-char \
  --use-port=emdawnwebgpu \
  -sSTACK_SIZE=33554432 -sINITIAL_MEMORY=536870912 -sALLOW_MEMORY_GROWTH=1 \
  -sEXIT_RUNTIME=0 -sASSERTIONS=1 -sWASM_BIGINT \
  -sPTHREAD_POOL_SIZE=32 -sPTHREAD_POOL_SIZE_STRICT=0 \
  -sDEFAULT_PTHREAD_STACK_SIZE=33554432 \
  -sMODULARIZE=1 -sEXPORT_NAME=createGpuHarness -sEXPORTED_RUNTIME_METHODS=callMain \
  --profiling-funcs \
  "$OUT/main.o" "$OUT/wgpu_context_web.o" "$OUT/stubs.o" "$OUT/ghost_ctx_web.o" "$OUT/ghost_ctx.o" \
  -Wl,--start-group \
    "$BWG/lib/libbf_gpu.a" \
    "$BWG/lib/libbf_gpu_shaders.a" "$BWG/lib/libbf_draw_shaders.a" \
    "$BWG/lib/libbf_compositor_shaders.a" "$BWG/lib/libbf_imbuf_opencolorio_shaders.a" \
    "$BWG/lib/libbf_blenlib.a" \
    "$BWG/lib/libbf_dna.a" "$BWG/lib/libbf_dna_blenlib.a" \
    "$BWG/lib/libbf_intern_clog.a" \
    "$BWG/lib/libbf_intern_guardedalloc.a" \
    "$ROOT/lib/wasm/lib/libtbb.a" "$ROOT/lib/wasm/lib/libtbbmalloc.a" "$ROOT/lib/wasm/lib/libfmt.a" \
    "${WGPU_LIBS[@]}" \
  -Wl,--end-group \
  -o "$OUT/gpu_harness.js" 2> "$OUT/link.err"
RC=$?
if [ $RC -ne 0 ]; then
  echo "LINK FAIL rc=$RC"
  echo "--- undefined symbols (unique, first 40) ---"
  grep -oE "undefined symbol: [^ ]+" "$OUT/link.err" | sort -u | head -40
  echo "--- other errors ---"
  grep -iE 'error:' "$OUT/link.err" | grep -v 'undefined symbol' | head -10
  exit 1
fi
echo "LINK OK: $(du -h "$OUT/gpu_harness.wasm" | awk '{print $1}') wasm"
