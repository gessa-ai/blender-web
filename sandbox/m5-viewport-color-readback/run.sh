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
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-deps/m5-viewport-color-readback/native}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/m5-viewport-color-readback/wasm}"
OUT="${OUT:-$ROOT/build-deps/m5-viewport-color-readback/evidence}"

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
            "$ROOT/sandbox/series-replay/verify.py" "$HERE/CMakeLists.txt" \
            "$HERE/contract_test.cc" "$HERE/verify_source.py"; do
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

"$PYBIN" "$HERE/verify_source.py" --source-root "$ROOT/upstream" --selfcheck
SOURCE_PROOF="$("$PYBIN" "$ROOT/sandbox/series-replay/verify.py" --canonical-only)"
case "$SOURCE_PROOF" in
  CANONICAL_REPLAY_PASS\ *) ;;
  *) echo "ERROR: canonical source replay verdict differs" >&2; exit 1 ;;
esac

mkdir -p "$NATIVE_BUILD" "$WASM_BUILD" "$OUT"
printf '%s\n' "$SOURCE_PROOF" >"$OUT/source-replay.txt"
"$PYBIN" "$HERE/verify_source.py" \
  --source-root "$ROOT/upstream" --output "$OUT/source.json" >"$OUT/source.stdout"

"$HOST_CMAKE" -G Ninja -S "$HERE" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/clang++-17 \
  -DBW_UPSTREAM_DIR="$ROOT/upstream"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" m5_viewport_color_readback_contract

export EMSDK_QUIET=1
# shellcheck disable=SC1091
source "$EMSDK/emsdk_env.sh" >/dev/null
EMCC_VERSION="$(em++ --version | sed -n '1s/.* \([0-9][0-9.]*\) (.*/\1/p')"
if [ "$EMCC_VERSION" != "6.0.5" ]; then
  echo "ERROR: expected em++ 6.0.5, got ${EMCC_VERSION:-unknown}" >&2
  exit 1
fi
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja \
  -S "$HERE" -B "$WASM_BUILD" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_EXE_LINKER_FLAGS= -DBW_UPSTREAM_DIR="$ROOT/upstream"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" m5_viewport_color_readback_contract

NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/m5_viewport_color_readback_contract" >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/m5_viewport_color_readback_contract.js" >"$WASM_STDOUT" 2>"$WASM_STDERR"

for stderr_file in "$NATIVE_STDERR" "$WASM_STDERR"; do
  if [ -s "$stderr_file" ]; then
    echo "ERROR: contract wrote stderr: $stderr_file" >&2
    exit 1
  fi
done
for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if [ "$(grep -c '^CONTRACT .* PASS ' "$stdout_file")" -ne 5 ] ||
     ! grep -qx 'M5_VIEWPORT_COLOR_READBACK_CONTRACT_PASS contracts=5 cases=12' "$stdout_file"; then
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
  .contracts.exact_owned_request == true and
  .contracts.pending_skips_sync_fallback == true and
  .contracts.native_immediate_completion == true and
  .contracts.failure_retryable == true and
  .contracts.live_hardware_receipt == false and
  .retired_sync_family == "viewport_color_sample" and
  .remaining_sync_family_count == 4' "$OUT/source.json" >/dev/null; then
  echo "ERROR: source receipt contract differs" >&2
  exit 1
fi

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n m5_viewport_color_readback_contract
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n m5_viewport_color_readback_contract

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(jq -r '.source_sha256' "$OUT/source.json")"
printf 'PASS m5-viewport-color-readback native/wasm bytes=%s sha256=%s source_sha256=%s emcc=%s node=v22.16.0 live_receipt=false\n' \
  "$OUTPUT_BYTES" "$OUTPUT_SHA256" "$SOURCE_SHA256" "$EMCC_VERSION"
