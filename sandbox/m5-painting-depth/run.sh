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
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-deps/m5-painting-depth/native-contract}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/m5-painting-depth/wasm-contract}"
OUT="${OUT:-$ROOT/build-deps/m5-painting-depth/evidence}"
PATCH="$ROOT/patches/0261-m5-painting-depth-continuation.patch"
CANONICAL="$ROOT/patches/PREVIEW_SNAPSHOT.patch"
CANONICAL_SHA="$ROOT/patches/PREVIEW_SNAPSHOT.sha256"
NATIVE_GRAPH="$ROOT/build-native-m1-parity"
WASM_GRAPH="$ROOT/build-wasm-windowed-opt"
PIN="fbe6228777e7d9afefcd61a413844e790ae75db7"
PROJ_REL="source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc"
OPS_REL="source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc"
PROJ_TARGET="source/blender/editors/sculpt_paint/CMakeFiles/bf_editor_sculpt_paint.dir/mesh/paint_image_proj.cc.o"
OPS_TARGET="source/blender/editors/sculpt_paint/CMakeFiles/bf_editor_sculpt_paint.dir/mesh/paint_image_ops_paint.cc.o"

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
            "$HERE/verify_numbered_patch.py" "$HERE/verify_canonical_source.py" \
            "$HERE/compile_overlay.py" "$PATCH" "$CANONICAL" "$CANONICAL_SHA"; do
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

mkdir -p "$NATIVE_BUILD" "$WASM_BUILD" "$OUT" "$ROOT/build-deps/m5-painting-depth"
SOURCE_ROOT="$(mktemp -d -t bw-m5-painting-source.XXXXXX)"
cleanup_source()
{
  rm -rf -- "$SOURCE_ROOT"
}
trap cleanup_source EXIT

SELECTED_PATHS=(
  "source/blender/editors/include/ED_view3d.hh"
  "source/blender/editors/space_view3d/view3d_draw.cc"
  "source/blender/editors/sculpt_paint/paint_intern.hh"
  "$PROJ_REL"
  "$OPS_REL"
  "source/blender/gpu/GPU_framebuffer.hh"
  "source/blender/gpu/GPU_readback.hh"
)
ARCHIVE_PATHS=()
for relative in "${SELECTED_PATHS[@]}"; do
  if git -C "$ROOT/upstream" cat-file -e "$PIN:$relative" 2>/dev/null; then
    ARCHIVE_PATHS+=("$relative")
  fi
done
git -C "$ROOT/upstream" archive --format=tar "$PIN" -- "${ARCHIVE_PATHS[@]}" |
  tar -xf - -C "$SOURCE_ROOT"
for relative in "${SELECTED_PATHS[@]}"; do
  git -C "$SOURCE_ROOT" apply --check --include="$relative" "$CANONICAL"
  git -C "$SOURCE_ROOT" apply --include="$relative" "$CANONICAL"
done

"$PYBIN" "$HERE/verify_canonical_source.py" \
  --upstream "$ROOT/upstream" --source-root "$SOURCE_ROOT" \
  --canonical "$CANONICAL" --sha256 "$CANONICAL_SHA" >"$OUT/canonical.stdout"
"$PYBIN" "$HERE/verify_source.py" --source-root "$SOURCE_ROOT" --selfcheck \
  >"$OUT/selfcheck.stdout"
"$PYBIN" "$HERE/verify_source.py" \
  --source-root "$SOURCE_ROOT" --output "$OUT/source.json" >"$OUT/source.stdout"
"$PYBIN" "$HERE/verify_numbered_patch.py" --source-root "$SOURCE_ROOT" --patch "$PATCH" \
  >"$OUT/patch.stdout"

"$HOST_CMAKE" -G Ninja -S "$HERE" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/clang++-17
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" m5_painting_depth_contract

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
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" m5_painting_depth_contract

NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/m5_painting_depth_contract" >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/m5_painting_depth_contract.js" >"$WASM_STDOUT" 2>"$WASM_STDERR"

for stderr_file in "$NATIVE_STDERR" "$WASM_STDERR"; do
  if [ -s "$stderr_file" ]; then
    echo "ERROR: contract wrote stderr: $stderr_file" >&2
    exit 1
  fi
done
for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if [ "$(grep -c '^CONTRACT .* PASS ' "$stdout_file")" -ne 8 ] ||
     ! grep -qx 'M5_PAINTING_DEPTH_CONTRACT_PASS contracts=8 cases=13' "$stdout_file"; then
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
  .contracts.shared_owned_progressive_depth == true and
  .contracts.native_immediate_completion == true and
  .contracts.clone_cursor_exact_request == true and
  .contracts.latest_motion_supersedes_pending == true and
  .contracts.cursor_and_context_drift_guard == true and
  .contracts.deferred_finish_event_replay == true and
  .contracts.bounded_timer_failure_cancellation == true and
  .contracts.non_clone_passthrough == true and
  .contracts.live_hardware_receipt == false and
  .converted_consumer == "painting" and
  .remaining_depth_pick_consumers == ["zoom_border", "ndof"] and
  .remaining_sync_family_count == 3' "$OUT/source.json" >/dev/null; then
  echo "ERROR: source receipt contract differs" >&2
  exit 1
fi

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_GRAPH" -t commands "$PROJ_TARGET" \
  >"$OUT/native-proj.commands"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_GRAPH" -t commands "$OPS_TARGET" \
  >"$OUT/native-ops.commands"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_GRAPH" -t commands "$PROJ_TARGET" \
  >"$OUT/wasm-proj.commands"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_GRAPH" -t commands "$OPS_TARGET" \
  >"$OUT/wasm-ops.commands"

for profile in native wasm; do
  graph_build="$NATIVE_BUILD"
  if [ "$profile" = "wasm" ]; then
    graph_build="$WASM_BUILD"
  fi
  "$PYBIN" "$HERE/compile_overlay.py" --commands-log "$OUT/$profile-proj.commands" \
    --relative "$PROJ_REL" --source "$SOURCE_ROOT/$PROJ_REL" \
    --output "$graph_build/paint_image_proj.overlay.o" >"$OUT/$profile-proj-tu.stdout"
  "$PYBIN" "$HERE/compile_overlay.py" --commands-log "$OUT/$profile-ops.commands" \
    --relative "$OPS_REL" --source "$SOURCE_ROOT/$OPS_REL" \
    --output "$graph_build/paint_image_ops_paint.overlay.o" >"$OUT/$profile-ops-tu.stdout"
done

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n m5_painting_depth_contract
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n m5_painting_depth_contract

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(jq -r '.source_sha256' "$OUT/source.json")"
PATCH_SHA256="$(sha256_file "$PATCH")"
printf 'PASS m5-painting-depth native/wasm bytes=%s sha256=%s source_sha256=%s patch_sha256=%s emcc=%s node=v22.16.0 remaining_sync=3 live_receipt=false\n' \
  "$OUTPUT_BYTES" "$OUTPUT_SHA256" "$SOURCE_SHA256" "$PATCH_SHA256" "$EMCC_VERSION"
