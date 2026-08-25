#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
HOST_CMAKE="$ROOT/.host-tools/bin/cmake"
PYBIN="$ROOT/.host-tools/bin/python3.13"
EMSDK="$ROOT/tools/emsdk"
NODE="$EMSDK/node/22.16.0_64bit/bin/node"
SOURCE_ROOT="${BW_SOURCE_ROOT:-}"
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-deps/m5-grease-pencil-fill-depth-cache/native}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/m5-grease-pencil-fill-depth-cache/wasm}"
OUT="${OUT:-$ROOT/build-deps/m5-grease-pencil-fill-depth-cache/evidence}"
PATCH="$ROOT/patches/0270-m5-grease-pencil-fill-depth-cache-continuation.patch"
CANONICAL="$ROOT/patches/PREVIEW_SNAPSHOT.patch"
CANONICAL_SHA="$ROOT/patches/PREVIEW_SNAPSHOT.sha256"
PIN="fbe6228777e7d9afefcd61a413844e790ae75db7"
COMPILE_OVERLAY="$ROOT/sandbox/m5-curve-depth-cache/compile_overlay.py"
NATIVE_GRAPH="$ROOT/build-native-m1-parity"
WASM_GRAPH="$ROOT/build-wasm-windowed-opt"
RELATIVES=(
  "source/blender/editors/include/ED_grease_pencil.hh"
  "source/blender/editors/sculpt_paint/grease_pencil/draw_ops.cc"
  "source/blender/editors/sculpt_paint/grease_pencil/fill.cc"
)
SOURCES=(
  "source/blender/editors/sculpt_paint/grease_pencil/draw_ops.cc"
  "source/blender/editors/sculpt_paint/grease_pencil/fill.cc"
)
OBJECTS=(
  "source/blender/editors/sculpt_paint/CMakeFiles/bf_editor_sculpt_paint.dir/grease_pencil/draw_ops.cc.o"
  "source/blender/editors/sculpt_paint/CMakeFiles/bf_editor_sculpt_paint.dir/grease_pencil/fill.cc.o"
)
LABELS=("draw_ops" "fill")

require_file()
{
  if [ ! -f "$1" ]; then
    echo "ERROR: required file missing: $1" >&2
    exit 1
  fi
}

sha256_file()
{
  sha256sum "$1" | awk '{print $1}'
}

for file in "$HOST_CMAKE" "$PYBIN" "$NODE" "$ROOT/scripts/ninja-locked.sh" \
            "$HERE/CMakeLists.txt" "$HERE/contract_test.cc" "$HERE/verify_source.py" \
            "$HERE/verify_numbered_patch.py" "$COMPILE_OVERLAY" "$PATCH" \
            "$CANONICAL" "$CANONICAL_SHA"; do
  require_file "$file"
done

if [ "$(uname -s):$(uname -m)" != "Linux:x86_64" ]; then
  echo "ERROR: this receipt requires Linux x86_64" >&2
  exit 1
fi
if [ "$("$HOST_CMAKE" --version | sed -n '1s/^cmake version //p')" != "4.0.3" ]; then
  echo "ERROR: expected host CMake 4.0.3" >&2
  exit 1
fi
if [ "$("$NODE" --version)" != "v22.16.0" ]; then
  echo "ERROR: expected Node v22.16.0" >&2
  exit 1
fi
if [ "$(git -C "$ROOT/upstream" rev-parse HEAD)" != "$PIN" ]; then
  echo "ERROR: upstream pin differs" >&2
  exit 1
fi
if ! (cd "$ROOT/patches" && sha256sum -c PREVIEW_SNAPSHOT.sha256 >/dev/null); then
  echo "ERROR: canonical source checksum differs" >&2
  exit 1
fi

mkdir -p "$NATIVE_BUILD" "$WASM_BUILD" "$OUT"
if [ -z "$SOURCE_ROOT" ]; then
  SOURCE_ROOT="$(mktemp -d -t bw-m5-gp-fill-depth-source.XXXXXX)"
  cleanup_source()
  {
    rm -rf -- "$SOURCE_ROOT"
  }
  trap cleanup_source EXIT

  git -C "$ROOT/upstream" archive --format=tar "$PIN" -- "${RELATIVES[@]}" | \
    tar -xf - -C "$SOURCE_ROOT"
  git -C "$SOURCE_ROOT" apply --check \
    --include="${RELATIVES[0]}" --include="${RELATIVES[1]}" --include="${RELATIVES[2]}" \
    "$CANONICAL"
  git -C "$SOURCE_ROOT" apply \
    --include="${RELATIVES[0]}" --include="${RELATIVES[1]}" --include="${RELATIVES[2]}" \
    "$CANONICAL"
fi

"$PYBIN" "$HERE/verify_source.py" --source-root "$SOURCE_ROOT" --selfcheck
"$PYBIN" "$HERE/verify_source.py" \
  --source-root "$SOURCE_ROOT" --selfcheck --output "$OUT/source.json" >"$OUT/source.stdout"
"$PYBIN" "$HERE/verify_numbered_patch.py" --source-root "$SOURCE_ROOT" --patch "$PATCH" \
  >"$OUT/patch.stdout"

"$HOST_CMAKE" -G Ninja -S "$HERE" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/clang++-17
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" \
  m5_grease_pencil_fill_depth_cache_contract

export EMSDK_QUIET=1
# shellcheck disable=SC1091
source "$EMSDK/emsdk_env.sh" >/dev/null
EMCC_VERSION="$(em++ --version | sed -n '1s/.* \([0-9][0-9.]*\) (.*/\1/p')"
if [ "$EMCC_VERSION" != "6.0.5" ]; then
  echo "ERROR: expected em++ 6.0.5, got ${EMCC_VERSION:-unknown}" >&2
  exit 1
fi
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja \
  -S "$HERE" -B "$WASM_BUILD" -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXE_LINKER_FLAGS=
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" \
  m5_grease_pencil_fill_depth_cache_contract

NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/m5_grease_pencil_fill_depth_cache_contract" \
  >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/m5_grease_pencil_fill_depth_cache_contract.js" \
  >"$WASM_STDOUT" 2>"$WASM_STDERR"

for stderr_file in "$NATIVE_STDERR" "$WASM_STDERR"; do
  if [ -s "$stderr_file" ]; then
    echo "ERROR: contract wrote stderr: $stderr_file" >&2
    exit 1
  fi
done
for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if [ "$(grep -c '^CONTRACT .* PASS ' "$stdout_file")" -ne 8 ] ||
     ! grep -qx \
       'M5_GREASE_PENCIL_FILL_DEPTH_CACHE_CONTRACT_PASS contracts=8 cases=28' \
       "$stdout_file"; then
    echo "ERROR: PASS census differs: $stdout_file" >&2
    exit 1
  fi
done
if ! cmp -s "$NATIVE_STDOUT" "$WASM_STDOUT"; then
  echo "ERROR: native and Wasm evidence differs" >&2
  diff -u "$NATIVE_STDOUT" "$WASM_STDOUT" | head -n 40 >&2
  exit 1
fi
if ! jq -e '
  .verdict == "PASS" and
  .contracts.operation_owned_request == true and
  .contracts.native_immediate_and_initial_fallback == true and
  .contracts.pre_result_suspension == true and
  .contracts.pixel_and_delaunay_ready_only == true and
  .contracts.retained_fill_point == true and
  .contracts.producing_context_guard == true and
  .contracts.bounded_identified_poll == true and
  .contracts.failure_timeout_cancellation == true and
  .contracts.live_hardware_receipt == false and
  .converted_callers == ["pixel_fill", "delaunay_fill"] and
  .remaining_grease_pencil_callers == ["pen-helper"] and
  .remaining_sync_families == ["depth_cache", "window_capture"] and
  .mutation_controls == 12' "$OUT/source.json" >/dev/null
then
  echo "ERROR: source receipt contract differs" >&2
  exit 1
fi

for graph in "$NATIVE_GRAPH" "$WASM_GRAPH"; do
  graph_label="$(basename "$graph")"
  for index in 0 1; do
    commands="$OUT/${graph_label}-${LABELS[$index]}.commands"
    object="$OUT/${graph_label}-${LABELS[$index]}.o"
    "$ROOT/scripts/ninja-locked.sh" -C "$graph" -t commands "${OBJECTS[$index]}" >"$commands"
    "$PYBIN" "$COMPILE_OVERLAY" --commands-log "$commands" \
      --relative "${SOURCES[$index]}" --source-root "$SOURCE_ROOT" \
      --source "$SOURCE_ROOT/${SOURCES[$index]}" --output "$object" \
      >"$OUT/${graph_label}-${LABELS[$index]}.stdout"
  done
done

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n \
  m5_grease_pencil_fill_depth_cache_contract
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n \
  m5_grease_pencil_fill_depth_cache_contract

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(jq -r '.source_sha256' "$OUT/source.json")"
PATCH_SHA256="$(sha256_file "$PATCH")"
CANONICAL_DIGEST="$(sha256_file "$CANONICAL")"
printf 'PASS m5-grease-pencil-fill-depth-cache native/wasm bytes=%s sha256=%s source_sha256=%s patch_sha256=%s canonical_sha256=%s emcc=%s node=v22.16.0 callers=2 gp_followups=1 remaining_sync=2 live_receipt=false\n' \
  "$OUTPUT_BYTES" "$OUTPUT_SHA256" "$SOURCE_SHA256" "$PATCH_SHA256" \
  "$CANONICAL_DIGEST" "$EMCC_VERSION"
