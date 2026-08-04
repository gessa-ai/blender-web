#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# M7.pre probe — proves the open/save OPERATORS work end-to-end on the wasm binary
# (real BLO_write_file / BLO_read_file), independent of the FS backend. Run on the
# NODE build (NODERAWFS -> writes hit the host FS); the browser build differs ONLY
# in the FS backend (WASMFS today, WASMFS+OPFS at M7) and the JS byte-bridge — the
# Blender-side write/read path is byte-for-byte the same object code.
# Usage: bash sandbox/m7-prep/probe_fs_roundtrip.sh
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
NODE="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
JS="$ROOT/build-wasm/bin/blender.js"
export BLENDER_SYSTEM_RESOURCES="$ROOT/upstream"
export BLENDER_SYSTEM_PYTHON="$ROOT/lib/wasm"
export BLENDER_SYSTEM_DATAFILES="$ROOT/upstream/release/datafiles"
OUT="${TMPDIR:-/tmp}/m7probe.$$"; mkdir -p "$OUT"

echo "== probe 1: save startup (real BLO_write_file) =="
"$NODE" "$JS" --background --factory-startup \
  --python-expr "import bpy,os;p='$OUT/save.blend';bpy.ops.wm.save_mainfile(filepath=p);print('SAVE_OK', os.path.exists(p), os.path.getsize(p), 'magic='+open(p,'rb').read(4).hex())" \
  2>/dev/null | grep -aE 'SAVE_OK'

echo "== probe 2: add-cube -> save -> reopen -> count (write+read round-trip) =="
"$NODE" "$JS" --background --factory-startup \
  --python-expr "import bpy;n0=len(bpy.data.objects);bpy.ops.mesh.primitive_cube_add();p='$OUT/rt.blend';bpy.ops.wm.save_mainfile(filepath=p);bpy.ops.wm.open_mainfile(filepath=p);print('ROUNDTRIP start=%d saved+reopened=%d' % (n0, len(bpy.data.objects)))" \
  2>/dev/null | grep -aE 'ROUNDTRIP'

rm -rf "$OUT"
# Expected: SAVE_OK True <bytes> magic=28b52ffd (zstd) ; ROUNDTRIP start=3 saved+reopened=4
