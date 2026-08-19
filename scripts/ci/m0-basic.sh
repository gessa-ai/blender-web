#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

# CI's executable M0 subset: exact identities, hello wasm, the emdawnwebgpu
# compile probe, and proof that Emscripten and ccache use separate persisted
# directories.  It never writes project receipts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BLENDER_COMMIT="fbe6228777e7d9afefcd61a413844e790ae75db7"
EMSDK_REPO_COMMIT="1ab2e627b1a84567f5284d1baaa5f6be7ccf07de"
EMSCRIPTEN_RELEASE_COMMIT="dbd755b5da399329c2576f6e3dfa7f419f5d8409"
EMCC_COMMIT="1db513782be24469589d7cb8a1f1834e9a33f271"
EMSDK_ROOT="${EMSDK_ROOT:-$ROOT/tools/emsdk}"
export EM_CACHE="${EM_CACHE:-$ROOT/.ci-cache/emscripten}"
export CCACHE_DIR="${CCACHE_DIR:-$ROOT/.ci-cache/ccache}"

die() {
  echo "m0-basic: $*" >&2
  exit 1
}

[[ "$(awk 'NR == 1 { print $1; exit }' "$ROOT/oracle/PIN")" == "${BLENDER_COMMIT:0:12}" ]] \
  || die "oracle/PIN drift"
[[ -d "$EMSDK_ROOT/.git" ]] || die "emsdk checkout is missing: $EMSDK_ROOT"
[[ "$(git -C "$EMSDK_ROOT" rev-parse HEAD)" == "$EMSDK_REPO_COMMIT" ]] \
  || die "emsdk repository drift"

release_commit="$(python3 - "$EMSDK_ROOT/emscripten-releases-tags.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as stream:
    print(json.load(stream)["releases"]["6.0.5"])
PY
)"
[[ "$release_commit" == "$EMSCRIPTEN_RELEASE_COMMIT" ]] \
  || die "emsdk 6.0.5 release identity drift"

# shellcheck disable=SC1091
source "$EMSDK_ROOT/emsdk_env.sh" >/dev/null 2>&1
export EM_CACHE="${EM_CACHE:-$ROOT/.ci-cache/emscripten}" # emsdk_env.sh unsets EM_CACHE when its stored config does not define a cache (fresh Linux emsdk); re-assert the hermetic default
export CCACHE_DIR="${CCACHE_DIR:-$ROOT/.ci-cache/ccache}" # emsdk_env.sh clears CCACHE_DIR too; same re-assert
emcc_version="$(emcc --version | head -n 1)"
[[ "$emcc_version" == *"6.0.5 ($EMCC_COMMIT)"* ]] \
  || die "unexpected emcc identity: $emcc_version"
[[ -x "${EMSDK_NODE:-}" ]] || die "emsdk Node executable is missing"
[[ "$("$EMSDK_NODE" --version)" == "v22.16.0" ]] \
  || die "unexpected emsdk Node identity"
command -v ccache >/dev/null 2>&1 || die "ccache is missing"

mkdir -p "$EM_CACHE" "$CCACHE_DIR"
ccache --set-config=compiler_check=content >/dev/null
ccache --zero-stats >/dev/null

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

cat >"$tmpdir/hello.c" <<'C'
#include <stdio.h>
int main(void) {
  puts("hello from m0 ci");
  return 0;
}
C

ccache emcc -c "$tmpdir/hello.c" -O0 -o "$tmpdir/hello.o"
rm "$tmpdir/hello.o"
ccache emcc -c "$tmpdir/hello.c" -O0 -o "$tmpdir/hello.o"
emcc "$tmpdir/hello.o" -O0 -o "$tmpdir/hello.js"
"$EMSDK_NODE" "$tmpdir/hello.js" | grep --fixed-strings --line-regexp 'hello from m0 ci'

cache_hits="$(ccache --print-stats | awk '$1 == "direct_cache_hit" || $1 == "preprocessed_cache_hit" { total += $2 } END { print total + 0 }')"
(( cache_hits >= 1 )) || die "ccache did not record the repeated compile as a hit"

ccache emcc --use-port=emdawnwebgpu -c "$tmpdir/hello.c" -o "$tmpdir/emdawn.o"
[[ -s "$tmpdir/emdawn.o" ]] || die "emdawnwebgpu probe did not emit an object"
[[ -d "$EM_CACHE" ]] || die "EM_CACHE was not created"
[[ -d "$CCACHE_DIR" ]] || die "CCACHE_DIR was not created"
ccache --show-stats

if [[ "${M0_VERIFY_UPSTREAM_FETCH:-0}" == "1" ]]; then
  upstream_probe="$(mktemp -d)"
  git -C "$upstream_probe" init --quiet
  git -C "$upstream_probe" remote add origin https://github.com/blender/blender.git
  git -C "$upstream_probe" fetch --quiet --depth=1 origin "$BLENDER_COMMIT"
  [[ "$(git -C "$upstream_probe" rev-parse FETCH_HEAD)" == "$BLENDER_COMMIT" ]] \
    || die "fetched upstream pin does not match"
  rm -rf "$upstream_probe"
fi

echo "M0_BASIC_CI_OK"
