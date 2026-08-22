#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T3 verify: require patches 0149, 0167, and 0171's integrated
# GHOST_ContextWGPU postimage, stage it outside upstream/, compile the canonical
# source against Blender's real GHOST headers inside Dawn's CMake graph, and run
# its optional-feature selector without a device. A software adapter can only
# produce the explicit blocked control; it cannot produce a T3 receipt.
#
#   harness/buildwrap.sh bash sandbox/dawn-probe/ghost-wgpu/build_verify.sh hardware
#   harness/buildwrap.sh bash sandbox/dawn-probe/ghost-wgpu/build_verify.sh software-blocked
#   harness/buildwrap.sh bash sandbox/dawn-probe/ghost-wgpu/build_verify.sh parser-selfcheck
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
UP="$REPO/upstream"
DAWN_SRC="${DAWN_SRC:-$REPO/build-dawn/dawn}"
BUILD="${BUILD:-$REPO/build-dawn/probe-build}"
PLATFORM_PATCH="$REPO/patches/0149-ghost-webgpu-native-platform-backend.patch"
FEATURE_PATCH="$REPO/patches/0167-gpu-webgpu-native-float32-filterable.patch"
SWIZZLE_PATCH="$REPO/patches/0171-gpu-webgpu-texture-component-swizzle.patch"
FEATURE_EXTRACTOR="$HERE/extract_optional_features.py"
CMAKE="$REPO/.host-tools/bin/cmake"
PYTHON="$REPO/.host-tools/bin/python3.13"
EXPECTED_UPSTREAM="fbe6228777e7d9afefcd61a413844e790ae75db7"
EXPECTED_DAWN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
MODE="${1:-hardware}"

case "$MODE" in
  hardware | software-blocked | build-only | parser-selfcheck) ;;
  *)
    echo "ERROR: usage: build_verify.sh [hardware|software-blocked|build-only|parser-selfcheck]" >&2
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

hardware_transcript_is_exact()
{
  local status="$1"
  local output="$2"
  local adapter_count
  local pass_count
  local blocked_count

  adapter_count="$(printf '%s\n' "$output" | grep -Ec '^GHOST_ContextWGPU adapter: .+$' || true)"
  pass_count="$(printf '%s\n' "$output" | grep -Fxc \
    "T3 VERIFY PASS: live WGPUDevice obtained through GHOST_ContextWGPU (offscreen, headless, $backend_name)." || true)"
  blocked_count="$(printf '%s\n' "$output" | grep -c '^PROBE_BLOCKED:' || true)"

  [ "$status" -eq 0 ] && [ "$adapter_count" -eq 1 ] && [ "$pass_count" -eq 1 ] && \
    [ "$blocked_count" -eq 0 ]
}

backend_name="$(case "$(uname -s)" in Darwin) printf Metal ;; Linux) printf Vulkan ;; esac)"

if [ "$MODE" = parser-selfcheck ]; then
  "$PYTHON" "$FEATURE_EXTRACTOR" --selfcheck
  good_output="GHOST_ContextWGPU adapter: Audit Hardware Adapter
T3 VERIFY PASS: live WGPUDevice obtained through GHOST_ContextWGPU (offscreen, headless, $backend_name)."
  if ! hardware_transcript_is_exact 0 "$good_output"; then
    echo "ERROR: exact hardware transcript was rejected" >&2
    exit 1
  fi
  for mutation in \
    "GHOST_ContextWGPU adapter: Audit Hardware Adapter" \
    "$good_output
T3 VERIFY PASS: live WGPUDevice obtained through GHOST_ContextWGPU (offscreen, headless, $backend_name)." \
    "$good_output
PROBE_BLOCKED: synthetic mutation" \
    "GHOST_ContextWGPU adapter: Audit Hardware Adapter
GHOST_ContextWGPU adapter: Second Adapter
T3 VERIFY PASS: live WGPUDevice obtained through GHOST_ContextWGPU (offscreen, headless, $backend_name)."
  do
    if hardware_transcript_is_exact 0 "$mutation"; then
      echo "ERROR: malformed hardware transcript was accepted" >&2
      exit 1
    fi
  done
  if hardware_transcript_is_exact 1 "$good_output"; then
    echo "ERROR: nonzero hardware status was accepted" >&2
    exit 1
  fi
  echo "T3 HARDWARE TRANSCRIPT PARSER SELFCHECK PASS cases=6"
  exit 0
fi

for required in \
  "$UP" \
  "$DAWN_SRC" \
  "$PLATFORM_PATCH" \
  "$FEATURE_PATCH" \
  "$SWIZZLE_PATCH" \
  "$FEATURE_EXTRACTOR" \
  "$CMAKE" \
  "$PYTHON"
do
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

# All allocations happen after both source pins pass. Stage only the two
# canonical files under the ignored build tree and require the exact 0149+0167+0171
# postimage before compiling. Reverse-checking all three patches is a read-only proof;
# the source worktree remains byte-for-byte untouched.
mkdir -p "$BUILD"
stage_tmp="$(mktemp -d "${TMPDIR:-/tmp}/blender-web-t3-ghost.XXXXXX")"
trap 'rm -rf -- "$stage_tmp"' EXIT
stage_rel="intern/ghost/intern"
mkdir -p "$stage_tmp/$stage_rel"
cp "$UP/$stage_rel/GHOST_ContextWGPU.cc" "$stage_tmp/$stage_rel/"
cp "$UP/$stage_rel/GHOST_ContextWGPU.hh" "$stage_tmp/$stage_rel/"
(
  cd "$stage_tmp"
  git apply --reverse --check "$PLATFORM_PATCH"
  git apply --include="$stage_rel/GHOST_ContextWGPU.cc" --reverse --check "$SWIZZLE_PATCH"
  git apply --include="$stage_rel/GHOST_ContextWGPU.cc" --reverse "$SWIZZLE_PATCH"
  git apply --reverse --check "$FEATURE_PATCH"
  git apply --reverse "$FEATURE_PATCH"
  git apply "$FEATURE_PATCH"
  git apply --include="$stage_rel/GHOST_ContextWGPU.cc" "$SWIZZLE_PATCH"
)

stage="$BUILD/bw-ghost-wgpu-source/$stage_rel"
mkdir -p "$stage"
for name in GHOST_ContextWGPU.cc GHOST_ContextWGPU.hh; do
  if [ ! -f "$stage/$name" ] || ! cmp -s "$stage_tmp/$stage_rel/$name" "$stage/$name"; then
    cp "$stage_tmp/$stage_rel/$name" "$stage/$name.tmp"
    mv "$stage/$name.tmp" "$stage/$name"
  fi
done
feature_source_dir="$BUILD/bw-ghost-wgpu-feature-source"
feature_source="$feature_source_dir/ghost_wgpu_optional_features.inc"
"$PYTHON" "$FEATURE_EXTRACTOR" \
  --source "$stage/GHOST_ContextWGPU.cc" \
  --output "$feature_source"

"$CMAKE" -G Ninja -S "$REPO/sandbox/dawn-probe" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DPython3_EXECUTABLE="$PYTHON" \
  -DBW_GHOST_WGPU_SOURCE_DIR="$stage" \
  -DBW_GHOST_WGPU_FEATURE_SOURCE_DIR="$feature_source_dir" \
  -DBW_UPSTREAM_DIR="$UP"
"$REPO/scripts/ninja-locked.sh" -C "$BUILD" \
  ghost_wgpu_verify ghost_wgpu_feature_contract

feature_output="$("$BUILD/ghost_wgpu_feature_contract")"
if [ "$feature_output" != \
  "T3 OPTIONAL FEATURE CONTRACT PASS features=9 masks=512 float32_index=2 swizzle_index=3" ]
then
  echo "ERROR: optional-feature contract lacks the exact PASS verdict" >&2
  exit 1
fi
printf '%s\n' "$feature_output"

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
  if printf '%s\n' "$verify_output" | grep -q '^T3 VERIFY PASS:'; then
    echo "ERROR: software-blocked control emitted a hardware PASS verdict" >&2
    exit 1
  fi
  echo "T3 SOFTWARE ADAPTER REJECTION PASS"
  exit 0
fi

if ! hardware_transcript_is_exact "$verify_status" "$verify_output"; then
  echo "ERROR: hardware run lacks one exact adapter/PASS transcript or contains a blocked marker" >&2
  exit 1
fi
