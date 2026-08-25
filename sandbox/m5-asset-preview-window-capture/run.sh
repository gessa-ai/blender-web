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
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-deps/m5-asset-preview-window-capture/native}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/m5-asset-preview-window-capture/wasm}"
OUT="${OUT:-$ROOT/build-deps/m5-asset-preview-window-capture/evidence}"
PATCH="$ROOT/patches/0274-m5-asset-preview-window-capture-continuation.patch"
CANONICAL="$ROOT/patches/PREVIEW_SNAPSHOT.patch"
CANONICAL_SHA="$ROOT/patches/PREVIEW_SNAPSHOT.sha256"
PIN="fbe6228777e7d9afefcd61a413844e790ae75db7"
COMPILE_OVERLAY="$ROOT/sandbox/m5-curve-depth-cache/compile_overlay.py"
NATIVE_GRAPH="$ROOT/build-native-m1-parity"
WASM_GRAPH="$ROOT/build-wasm-windowed-opt"
RELATIVE_ASSET="source/blender/editors/asset/intern/asset_ops.cc"
RELATIVE_PYTHON="source/blender/python/intern/bpy_rna_wm.cc"
RELATIVE_WM_API="source/blender/windowmanager/WM_api.hh"
RELATIVE_WM_DRAW="source/blender/windowmanager/intern/wm_draw.cc"
ASSET_OBJECT="source/blender/editors/asset/CMakeFiles/bf_editor_asset.dir/intern/asset_ops.cc.o"

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
  SOURCE_ROOT="$(mktemp -d -t bw-m5-asset-preview-source.XXXXXX)"
  cleanup_source()
  {
    rm -rf -- "$SOURCE_ROOT"
  }
  trap cleanup_source EXIT

  git -C "$ROOT/upstream" archive --format=tar "$PIN" -- \
    "$RELATIVE_ASSET" "$RELATIVE_PYTHON" "$RELATIVE_WM_API" "$RELATIVE_WM_DRAW" | \
    tar -xf - -C "$SOURCE_ROOT"
  git -C "$SOURCE_ROOT" apply --check \
    --include="$RELATIVE_ASSET" --include="$RELATIVE_PYTHON" \
    --include="$RELATIVE_WM_API" --include="$RELATIVE_WM_DRAW" "$CANONICAL"
  git -C "$SOURCE_ROOT" apply \
    --include="$RELATIVE_ASSET" --include="$RELATIVE_PYTHON" \
    --include="$RELATIVE_WM_API" --include="$RELATIVE_WM_DRAW" "$CANONICAL"
fi

"$PYBIN" "$HERE/verify_source.py" --source-root "$SOURCE_ROOT" --selfcheck \
  --output "$OUT/source.json" >"$OUT/source.stdout"
"$PYBIN" "$HERE/verify_numbered_patch.py" --source-root "$SOURCE_ROOT" --patch "$PATCH" \
  >"$OUT/patch.stdout"

"$HOST_CMAKE" -G Ninja -S "$HERE" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/clang++-17
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" \
  m5_asset_preview_window_capture_contract

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
  m5_asset_preview_window_capture_contract

NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/m5_asset_preview_window_capture_contract" \
  >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/m5_asset_preview_window_capture_contract.js" \
  >"$WASM_STDOUT" 2>"$WASM_STDERR"

for stderr_file in "$NATIVE_STDERR" "$WASM_STDERR"; do
  if [ -s "$stderr_file" ]; then
    echo "ERROR: contract wrote stderr: $stderr_file" >&2
    exit 1
  fi
done
for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if [ "$(grep -c '^CONTRACT .* PASS ' "$stdout_file")" -ne 8 ] ||
     ! grep -qx 'M5_ASSET_PREVIEW_WINDOW_CAPTURE_CONTRACT_PASS contracts=8 cases=28' \
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
  .contracts.owned_window_capture == true and
  .contracts.native_immediate_completion == true and
  .contracts.exact_crop_and_target == true and
  .contracts.bounded_identified_poll == true and
  .contracts.context_drift_rejected == true and
  .contracts.terminal_cleanup == true and
  .contracts.public_operator_surface_preserved == true and
  .contracts.live_hardware_receipt == false and
  .converted_callers == ["asset_preview_window_capture"] and
  .remaining_window_capture_callers == ["python_window_screenshot"] and
  .mutation_controls == 18' "$OUT/source.json" >/dev/null; then
  echo "ERROR: source receipt contract differs" >&2
  exit 1
fi

for graph in "$NATIVE_GRAPH" "$WASM_GRAPH"; do
  graph_label="$(basename "$graph")"
  commands="$OUT/${graph_label}-asset_ops.commands"
  "$ROOT/scripts/ninja-locked.sh" -C "$graph" -t commands "$ASSET_OBJECT" >"$commands"
  "$PYBIN" "$COMPILE_OVERLAY" --commands-log "$commands" \
    --relative "$RELATIVE_ASSET" --source-root "$SOURCE_ROOT" \
    --source "$SOURCE_ROOT/$RELATIVE_ASSET" \
    --output "$OUT/${graph_label}-asset_ops.o" \
    >"$OUT/${graph_label}-asset_ops.stdout"
done

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n \
  m5_asset_preview_window_capture_contract
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n \
  m5_asset_preview_window_capture_contract

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(jq -r '.source_sha256' "$OUT/source.json")"
PATCH_SHA256="$(sha256_file "$PATCH")"
CANONICAL_SHA256="$(sha256_file "$CANONICAL")"
printf 'PASS m5-asset-preview-window-capture native/wasm bytes=%s sha256=%s source_sha256=%s patch_sha256=%s canonical_sha256=%s emcc=%s node=v22.16.0 converted=1 remaining=1 live_receipt=false\n' \
  "$OUTPUT_BYTES" "$OUTPUT_SHA256" "$SOURCE_SHA256" "$PATCH_SHA256" \
  "$CANONICAL_SHA256" "$EMCC_VERSION"
