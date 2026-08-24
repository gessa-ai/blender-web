#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Fail-closed identity checks for the integrated bind-space parity driver.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
BINDSPACE_SELFCHECK_DIR="$(mktemp -d)"
trap 'rm -rf "$BINDSPACE_SELFCHECK_DIR"' EXIT

WRONG_DAWN_OUT="$BINDSPACE_SELFCHECK_DIR/wrong-dawn-out"
WRONG_NODE_OUT="$BINDSPACE_SELFCHECK_DIR/wrong-node-out"
WRONG_FMT_OUT="$BINDSPACE_SELFCHECK_DIR/wrong-fmt-out"
WRONG_SAMPLER_OUT="$BINDSPACE_SELFCHECK_DIR/wrong-sampler.inc"
WRONG_SAMPLER_CACHE_OUT="$BINDSPACE_SELFCHECK_DIR/wrong-sampler-cache.inc"
WRONG_DUMMY_OUT="$BINDSPACE_SELFCHECK_DIR/wrong-dummy.inc"
WRONG_DUMMY_CACHE_OUT="$BINDSPACE_SELFCHECK_DIR/wrong-dummy-cache.inc"
WRONG_NODE="$BINDSPACE_SELFCHECK_DIR/wrong-node"
WRONG_FMT="$BINDSPACE_SELFCHECK_DIR/wrong-fmt/include"
case "$(uname -s):$(uname -m)" in
  Linux:x86_64) SOURCE_FMT="$ROOT/lib/linux_x64/fmt/include/fmt/ranges.h" ;;
  Darwin:arm64) SOURCE_FMT="$ROOT/lib/macos_arm64/fmt/include/fmt/ranges.h" ;;
  *)
    echo "ERROR: supported hosts are Linux x86_64 and macOS arm64" >&2
    exit 1
    ;;
esac
mkdir -p "$WRONG_FMT/fmt"
printf '%s\n' '#!/usr/bin/env bash' "printf '%s\\n' v99.0.0" >"$WRONG_NODE"
chmod +x "$WRONG_NODE"
cp "$SOURCE_FMT" "$WRONG_FMT/fmt/ranges.h"
printf '\n// identity drift\n' >>"$WRONG_FMT/fmt/ranges.h"

sed \
  's/GPU_SAMPLER_FILTERING_ANISOTROPIC_ENABLE/GPU_SAMPLER_FILTERING_ANISOTROPIC_MASK/' \
  "$ROOT/upstream/source/blender/gpu/webgpu/wgpu_context.cc" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-sampler.cc"
if "$ROOT/.host-tools/bin/python3.13" "$HERE/extract_sampler_descriptor.py" \
  --source "$BINDSPACE_SELFCHECK_DIR/wrong-sampler.cc" \
  --output "$WRONG_SAMPLER_OUT" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-sampler.stdout" \
  2>"$BINDSPACE_SELFCHECK_DIR/wrong-sampler.stderr"
then
  echo "ERROR: malformed sampler policy was accepted" >&2
  exit 1
fi
if [ -e "$WRONG_SAMPLER_OUT" ]; then
  echo "ERROR: malformed sampler policy allocated generated output" >&2
  exit 1
fi
if [ -s "$BINDSPACE_SELFCHECK_DIR/wrong-sampler.stdout" ] ||
   ! grep -Fqx \
     "SAMPLER_DESCRIPTOR_EXTRACT_FAIL canonical sampler policy lost required structure: ['state.filtering & GPU_SAMPLER_FILTERING_ANISOTROPIC_ENABLE']" \
     "$BINDSPACE_SELFCHECK_DIR/wrong-sampler.stderr"
then
  echo "ERROR: malformed sampler rejection diagnostic differs" >&2
  exit 1
fi

sed \
  's/sampler_cache_\.get_or_create(instance_, device_, key, "sampler creation"/sampler_cache_.get_or_insert(instance_, device_, key, "sampler creation"/' \
  "$ROOT/upstream/source/blender/gpu/webgpu/wgpu_context.cc" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-sampler-cache.cc"
if "$ROOT/.host-tools/bin/python3.13" "$HERE/extract_sampler_descriptor.py" \
  --source "$BINDSPACE_SELFCHECK_DIR/wrong-sampler-cache.cc" \
  --output "$WRONG_SAMPLER_CACHE_OUT" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-sampler-cache.stdout" \
  2>"$BINDSPACE_SELFCHECK_DIR/wrong-sampler-cache.stderr"
then
  echo "ERROR: malformed scoped sampler creation was accepted" >&2
  exit 1
fi
if [ -e "$WRONG_SAMPLER_CACHE_OUT" ]; then
  echo "ERROR: malformed scoped sampler creation allocated generated output" >&2
  exit 1
fi
if [ -s "$BINDSPACE_SELFCHECK_DIR/wrong-sampler-cache.stdout" ] ||
   [ "$(wc -l <"$BINDSPACE_SELFCHECK_DIR/wrong-sampler-cache.stderr" | tr -d ' ')" -ne 2 ] ||
   ! grep -Fqx \
     'SAMPLER_DESCRIPTOR_EXTRACT_FAIL canonical sampler boundary is not unique: ' \
     "$BINDSPACE_SELFCHECK_DIR/wrong-sampler-cache.stderr" ||
   ! grep -Fqx \
     '  return sampler_cache_.get_or_create(instance_, device_, key, "sampler creation", [&]() {' \
     "$BINDSPACE_SELFCHECK_DIR/wrong-sampler-cache.stderr"
then
  echo "ERROR: malformed scoped sampler creation rejection diagnostic differs" >&2
  exit 1
fi

sed \
  's/descriptor.size = sizeof(default_attribute);/descriptor.size = sizeof(default_attribute) * 2;/' \
  "$ROOT/upstream/source/blender/gpu/webgpu/wgpu_common.hh" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-dummy-helper.hh"
if "$ROOT/.host-tools/bin/python3.13" "$HERE/extract_dummy_vertex_buffer.py" \
  --source "$ROOT/upstream/source/blender/gpu/webgpu/wgpu_context.cc" \
  --helper-source "$BINDSPACE_SELFCHECK_DIR/wrong-dummy-helper.hh" \
  --output "$WRONG_DUMMY_OUT" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-dummy.stdout" \
  2>"$BINDSPACE_SELFCHECK_DIR/wrong-dummy.stderr"
then
  echo "ERROR: malformed dummy-vertex policy was accepted" >&2
  exit 1
fi
if [ -e "$WRONG_DUMMY_OUT" ]; then
  echo "ERROR: malformed dummy-vertex policy allocated generated output" >&2
  exit 1
fi
if [ -s "$BINDSPACE_SELFCHECK_DIR/wrong-dummy.stdout" ] ||
   ! grep -Fqx \
     "DUMMY_VERTEX_EXTRACT_FAIL canonical dummy-vertex helper lost required structure: ['descriptor.size = sizeof(default_attribute);']" \
     "$BINDSPACE_SELFCHECK_DIR/wrong-dummy.stderr"
then
  echo "ERROR: malformed dummy-vertex rejection diagnostic differs" >&2
  exit 1
fi

sed \
  's/dummy_vertex_buffer_cache_\.get_or_create(/dummy_vertex_buffer_cache_.get_or_insert(/' \
  "$ROOT/upstream/source/blender/gpu/webgpu/wgpu_context.cc" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-dummy-cache.cc"
if "$ROOT/.host-tools/bin/python3.13" "$HERE/extract_dummy_vertex_buffer.py" \
  --source "$BINDSPACE_SELFCHECK_DIR/wrong-dummy-cache.cc" \
  --helper-source "$ROOT/upstream/source/blender/gpu/webgpu/wgpu_common.hh" \
  --output "$WRONG_DUMMY_CACHE_OUT" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-dummy-cache.stdout" \
  2>"$BINDSPACE_SELFCHECK_DIR/wrong-dummy-cache.stderr"
then
  echo "ERROR: malformed scoped dummy-buffer creation was accepted" >&2
  exit 1
fi
if [ -e "$WRONG_DUMMY_CACHE_OUT" ]; then
  echo "ERROR: malformed scoped dummy-buffer creation allocated generated output" >&2
  exit 1
fi
if [ -s "$BINDSPACE_SELFCHECK_DIR/wrong-dummy-cache.stdout" ] ||
   ! grep -Fqx \
     "DUMMY_VERTEX_EXTRACT_FAIL canonical dummy-vertex cache policy lost required structure: ['return dummy_vertex_buffer_cache_.get_or_create(']" \
     "$BINDSPACE_SELFCHECK_DIR/wrong-dummy-cache.stderr"
then
  echo "ERROR: malformed scoped dummy-buffer rejection diagnostic differs" >&2
  exit 1
fi

if OUT="$WRONG_DAWN_OUT" DAWN_SRC="$ROOT" bash "$HERE/build.sh" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-dawn.stdout" \
  2>"$BINDSPACE_SELFCHECK_DIR/wrong-dawn.stderr"
then
  echo "ERROR: wrong Dawn checkout was accepted" >&2
  exit 1
fi
if [ -e "$WRONG_DAWN_OUT" ]; then
  echo "ERROR: wrong Dawn checkout allocated evidence" >&2
  exit 1
fi
if [ -s "$BINDSPACE_SELFCHECK_DIR/wrong-dawn.stdout" ] ||
   ! grep -Eq \
     "^ERROR: Dawn pin mismatch: expected $DAWN_PIN, got [0-9a-f]{40}$" \
     "$BINDSPACE_SELFCHECK_DIR/wrong-dawn.stderr"
then
  echo "ERROR: wrong Dawn rejection diagnostic differs" >&2
  exit 1
fi

if OUT="$WRONG_NODE_OUT" NODE="$WRONG_NODE" bash "$HERE/build.sh" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-node.stdout" \
  2>"$BINDSPACE_SELFCHECK_DIR/wrong-node.stderr"
then
  echo "ERROR: wrong Node identity was accepted" >&2
  exit 1
fi
if [ -e "$WRONG_NODE_OUT" ]; then
  echo "ERROR: wrong Node identity allocated evidence" >&2
  exit 1
fi
if [ -s "$BINDSPACE_SELFCHECK_DIR/wrong-node.stdout" ] ||
   ! grep -qx 'ERROR: expected Node v22.16.0, got v99.0.0' \
     "$BINDSPACE_SELFCHECK_DIR/wrong-node.stderr"
then
  echo "ERROR: wrong Node rejection diagnostic differs" >&2
  exit 1
fi

if OUT="$WRONG_FMT_OUT" NATIVE_FMT_INCLUDE="$WRONG_FMT" bash "$HERE/build.sh" \
  >"$BINDSPACE_SELFCHECK_DIR/wrong-fmt.stdout" \
  2>"$BINDSPACE_SELFCHECK_DIR/wrong-fmt.stderr"
then
  echo "ERROR: drifted fmt header was accepted" >&2
  exit 1
fi
if [ -e "$WRONG_FMT_OUT" ]; then
  echo "ERROR: drifted fmt header allocated evidence" >&2
  exit 1
fi
if [ -s "$BINDSPACE_SELFCHECK_DIR/wrong-fmt.stdout" ] ||
   ! grep -qx 'ERROR: native and Wasm fmt/ranges.h differ' \
     "$BINDSPACE_SELFCHECK_DIR/wrong-fmt.stderr"
then
  echo "ERROR: drifted fmt rejection diagnostic differs" >&2
  exit 1
fi

echo "BINDSPACE_INTEGRATED_SELFCHECK_PASS wrong_sampler=zero-allocation wrong_sampler_cache=zero-allocation wrong_dummy=zero-allocation wrong_dummy_cache=zero-allocation wrong_dawn=zero-allocation wrong_node=zero-allocation wrong_fmt=zero-allocation"
