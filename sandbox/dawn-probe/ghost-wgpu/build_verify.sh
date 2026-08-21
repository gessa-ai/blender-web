#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T3 verify: stage patch 0149 over Blender's current GHOST_ContextWGPU source,
# compile it against Blender's real GHOST headers inside Dawn's CMake graph, and
# run a standalone main that requires a hardware device. The source worktree is
# never modified. A software adapter can only produce the explicit blocked
# control; it cannot produce a T3 receipt.
#
#   harness/buildwrap.sh bash sandbox/dawn-probe/ghost-wgpu/build_verify.sh hardware
#   harness/buildwrap.sh bash sandbox/dawn-probe/ghost-wgpu/build_verify.sh software-blocked
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
UP="$REPO/upstream"
DAWN_SRC="${DAWN_SRC:-$REPO/build-dawn/dawn}"
BUILD="${BUILD:-$REPO/build-dawn/probe-build}"
PATCH="$REPO/patches/0149-ghost-webgpu-native-platform-backend.patch"
CMAKE="$REPO/.host-tools/bin/cmake"
PYTHON="$REPO/.host-tools/bin/python3.13"
EXPECTED_UPSTREAM="fbe6228777e7d9afefcd61a413844e790ae75db7"
EXPECTED_DAWN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
MODE="${1:-hardware}"

case "$MODE" in
  hardware | software-blocked | build-only) ;;
  *)
    echo "ERROR: usage: build_verify.sh [hardware|software-blocked|build-only]" >&2
    exit 2
    ;;
esac

case "$(uname -s)" in
  Darwin) CMAKE_HOST_ARGS=(-DCMAKE_OSX_DEPLOYMENT_TARGET=11.2) ;;
  Linux) CMAKE_HOST_ARGS=(-U CMAKE_OSX_DEPLOYMENT_TARGET) ;;
  *)
    echo "ERROR: T3 GHOST verify supports macOS/Metal or Linux/Vulkan only" >&2
    exit 2
    ;;
esac

for required in "$UP" "$DAWN_SRC" "$PATCH" "$CMAKE" "$PYTHON"; do
  if [ ! -e "$required" ]; then
    echo "ERROR: required T3 input is missing: $required" >&2
    exit 2
  fi
done

upstream_head="$(git -C "$UP" rev-parse HEAD)"
dawn_head="$(git -C "$DAWN_SRC" rev-parse HEAD)"
if [ "$upstream_head" != "$EXPECTED_UPSTREAM" ]; then
  echo "ERROR: upstream pin mismatch: $upstream_head" >&2
  exit 2
fi
if [ "$dawn_head" != "$EXPECTED_DAWN" ]; then
  echo "ERROR: Dawn pin mismatch: $dawn_head" >&2
  exit 2
fi

# All allocations happen after both source pins pass. Stage only the two patched
# files under the ignored build tree, apply the product patch there, and leave
# upstream/ byte-for-byte untouched.
mkdir -p "$BUILD"
stage_tmp="$(mktemp -d "${TMPDIR:-/tmp}/blender-web-t3-ghost.XXXXXX")"
trap 'rm -rf -- "$stage_tmp"' EXIT
stage_rel="intern/ghost/intern"
mkdir -p "$stage_tmp/$stage_rel"
cp "$UP/$stage_rel/GHOST_ContextWGPU.cc" "$stage_tmp/$stage_rel/"
cp "$UP/$stage_rel/GHOST_ContextWGPU.hh" "$stage_tmp/$stage_rel/"
(
  cd "$stage_tmp"
  git apply --check "$PATCH"
  git apply "$PATCH"
)

stage="$BUILD/bw-ghost-wgpu-source/$stage_rel"
mkdir -p "$stage"
for name in GHOST_ContextWGPU.cc GHOST_ContextWGPU.hh; do
  if [ ! -f "$stage/$name" ] || ! cmp -s "$stage_tmp/$stage_rel/$name" "$stage/$name"; then
    cp "$stage_tmp/$stage_rel/$name" "$stage/$name.tmp"
    mv "$stage/$name.tmp" "$stage/$name"
  fi
done

"$CMAKE" -G Ninja -S "$REPO/sandbox/dawn-probe" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DPython3_EXECUTABLE="$PYTHON" \
  -DBW_GHOST_WGPU_SOURCE_DIR="$stage" \
  -DBW_UPSTREAM_DIR="$UP"
"$REPO/scripts/ninja-locked.sh" -C "$BUILD" ghost_wgpu_verify

if [ "$MODE" = build-only ]; then
  echo "T3 GHOST BUILD PASS"
  exit 0
fi

set +e
verify_output="$("$BUILD/ghost_wgpu_verify" 2>&1)"
verify_status=$?
set -e
printf '%s\n' "$verify_output"

if [ "$MODE" = software-blocked ]; then
  if [ "$verify_status" -ne 77 ]; then
    echo "ERROR: software-blocked control returned $verify_status, expected 77" >&2
    exit 1
  fi
  if [ "$(printf '%s\n' "$verify_output" | grep -c '^PROBE_BLOCKED: refusing non-hardware ')" -ne 1 ]; then
    echo "ERROR: software-blocked control lacks the exact single rejection marker" >&2
    exit 1
  fi
  echo "T3 SOFTWARE ADAPTER REJECTION PASS"
  exit 0
fi

if [ "$verify_status" -ne 0 ]; then
  exit "$verify_status"
fi
