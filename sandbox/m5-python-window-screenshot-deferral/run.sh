#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PYBIN="$ROOT/.host-tools/bin/python3.13"
EMSDK="$ROOT/tools/emsdk"
PATCH="$ROOT/patches/0275-m5-python-window-screenshot-browser-deferral.patch"
CANONICAL="$ROOT/patches/PREVIEW_SNAPSHOT.patch"
CANONICAL_SHA="$ROOT/patches/PREVIEW_SNAPSHOT.sha256"
COMPILE_OVERLAY="$ROOT/sandbox/m5-curve-depth-cache/compile_overlay.py"
NATIVE_GRAPH="$ROOT/build-native-m1-parity"
WASM_GRAPH="$ROOT/build-wasm-windowed-opt"
LLVM_NM="$EMSDK/upstream/bin/llvm-nm"
PIN="fbe6228777e7d9afefcd61a413844e790ae75db7"
SOURCE_ROOT="${BW_SOURCE_ROOT:-}"
OUT="${OUT:-$ROOT/build-deps/m5-python-window-screenshot-deferral/evidence}"
RELATIVE_PYTHON="source/blender/python/intern/bpy_rna_wm.cc"
RELATIVE_SCREEN="source/blender/editors/screen/screendump.cc"
PYTHON_OBJECT="source/blender/python/intern/CMakeFiles/bf_python.dir/bpy_rna_wm.cc.o"
ERROR="Window.screenshot() is unavailable in the browser because WebGPU readback is asynchronous; use bpy.ops.screen.screenshot() for file capture"

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

for file in "$PYBIN" "$PATCH" "$CANONICAL" "$CANONICAL_SHA" "$COMPILE_OVERLAY" \
            "$HERE/verify_source.py" "$HERE/verify_numbered_patch.py" "$LLVM_NM"; do
  require_file "$file"
done
if [ "$(uname -s):$(uname -m)" != "Linux:x86_64" ]; then
  echo "ERROR: this receipt requires Linux x86_64" >&2
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

mkdir -p "$OUT"
if [ -z "$SOURCE_ROOT" ]; then
  SOURCE_ROOT="$(mktemp -d -t bw-m5-python-screenshot-source.XXXXXX)"
  cleanup_source()
  {
    rm -rf -- "$SOURCE_ROOT"
  }
  trap cleanup_source EXIT
  git -C "$ROOT/upstream" archive --format=tar "$PIN" -- \
    "$RELATIVE_PYTHON" "$RELATIVE_SCREEN" | tar -xf - -C "$SOURCE_ROOT"
  git -C "$SOURCE_ROOT" apply --check --include="$RELATIVE_PYTHON" \
    --include="$RELATIVE_SCREEN" "$CANONICAL"
  git -C "$SOURCE_ROOT" apply --include="$RELATIVE_PYTHON" \
    --include="$RELATIVE_SCREEN" "$CANONICAL"
fi

"$PYBIN" "$HERE/verify_source.py" --source-root "$SOURCE_ROOT" --selfcheck \
  >"$OUT/selfcheck.stdout"
"$PYBIN" "$HERE/verify_source.py" --source-root "$SOURCE_ROOT" \
  --output "$OUT/source.json" >"$OUT/source.stdout"
"$PYBIN" "$HERE/verify_numbered_patch.py" --source-root "$SOURCE_ROOT" --patch "$PATCH" \
  >"$OUT/patch.stdout"

for graph in "$NATIVE_GRAPH" "$WASM_GRAPH"; do
  graph_label="$(basename "$graph")"
  commands="$OUT/${graph_label}-bpy_rna_wm.commands"
  "$ROOT/scripts/ninja-locked.sh" -C "$graph" -t commands "$PYTHON_OBJECT" >"$commands"
  "$PYBIN" "$COMPILE_OVERLAY" --commands-log "$commands" \
    --relative "$RELATIVE_PYTHON" --source-root "$SOURCE_ROOT" \
    --source "$SOURCE_ROOT/$RELATIVE_PYTHON" \
    --output "$OUT/${graph_label}-bpy_rna_wm.o" \
    >"$OUT/${graph_label}-bpy_rna_wm.stdout"
  "$LLVM_NM" --undefined-only "$OUT/${graph_label}-bpy_rna_wm.o" \
    >"$OUT/${graph_label}-bpy_rna_wm.nm"
  strings "$OUT/${graph_label}-bpy_rna_wm.o" \
    >"$OUT/${graph_label}-bpy_rna_wm.strings"
done

NATIVE_LABEL="$(basename "$NATIVE_GRAPH")"
WASM_LABEL="$(basename "$WASM_GRAPH")"
if ! rg -q "WM_window_pixels_read" "$OUT/${NATIVE_LABEL}-bpy_rna_wm.nm"; then
  echo "ERROR: native object lost synchronous window capture" >&2
  exit 1
fi
if rg -q "WM_window_pixels_read" "$OUT/${WASM_LABEL}-bpy_rna_wm.nm"; then
  echo "ERROR: wasm object retains synchronous window capture" >&2
  exit 1
fi
if rg -Fq "$ERROR" "$OUT/${NATIVE_LABEL}-bpy_rna_wm.strings"; then
  echo "ERROR: native object embeds browser-only error" >&2
  exit 1
fi
if ! rg -Fq "$ERROR" "$OUT/${WASM_LABEL}-bpy_rna_wm.strings"; then
  echo "ERROR: wasm object lacks browser policy error" >&2
  exit 1
fi
if ! jq -e '
  .verdict == "PASS" and
  .contracts.public_surface_preserved == true and
  .contracts.argument_parsing_preserved == true and
  .contracts.background_error_preserved == true and
  .contracts.native_memoryview_preserved == true and
  .contracts.browser_fail_closed == true and
  .contracts.browser_sync_call_excluded == true and
  .contracts.async_file_capture_workaround == true and
  .contracts.live_hardware_receipt == false and
  .deferred_callers == ["python_window_screenshot_memoryview"] and
  .remaining_window_capture_callers == [] and
  .remaining_sync_families == []' "$OUT/source.json" >/dev/null; then
  echo "ERROR: focused source receipt differs" >&2
  exit 1
fi

SOURCE_SHA256="$(jq -r '.source_sha256' "$OUT/source.json")"
PATCH_SHA256="$(sha256_file "$PATCH")"
CANONICAL_SHA256="$(sha256_file "$CANONICAL")"
printf 'PASS m5-python-window-screenshot source_sha256=%s patch_sha256=%s canonical_sha256=%s native_sync=1 wasm_sync=0 deferred=1 remaining=0 live_receipt=false\n' \
  "$SOURCE_SHA256" "$PATCH_SHA256" "$CANONICAL_SHA256"
