#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M7 store — NODE PATH-ROUTING half. Proves that the mount-recipe env vars
# (BLENDER_USER_RESOURCES / BLENDER_USER_CONFIG / TMPDIR) are honored by Blender's
# appdir path resolution UNDER EMSCRIPTEN, and that a save into the routed tree
# works — i.e. Blender's DEFAULTS (userpref.blend, recent-files.txt, autosave/
# quit.blend, user saves) will land on whatever directory the env points at.
#
# WHY node (NODERAWFS), not the browser: this half proves the *path routing* (which
# is Blender object code identical across FS backends). It does NOT prove OPFS
# persistence — that is the browser half (web/, port 8131). NODERAWFS writes hit the
# host FS, so we route the env at a scratch host dir and assert Blender lands there.
# In the real browser binary the same env points at the OPFS mount (/projects/...).
# See notes/m7-store-design.md for the joint-proof caveat.
#
# Read-only use of the pre-built node binary build-wasm-cycles/bin/blender.js (fresh);
# builds nothing. Usage: bash sandbox/m7-store-probe/node_route.sh
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
NODE="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
JS="$ROOT/build-wasm-cycles/bin/blender.js"
[ -x "$NODE" ] || NODE="node"
[ -f "$JS" ] || { echo "MISSING node blender.js: $JS" >&2; exit 1; }

# System resources so Blender can boot Python/scripts (read-only), as m7-prep did.
export BLENDER_SYSTEM_RESOURCES="$ROOT/upstream"
export BLENDER_SYSTEM_PYTHON="$ROOT/lib/wasm"
export BLENDER_SYSTEM_DATAFILES="$ROOT/upstream/release/datafiles"

# The recipe under test: route the user resource root + tempdir onto a scratch tree
# (host FS here; OPFS mount in the browser). We pre-create USERROOT so appdir's
# read-path (check_is_dir=true) accepts the env; the config subdir is created by
# Blender via BKE_appdir_folder_id_create (_notest -> BLI_dir_create_recursive).
OUT="${TMPDIR:-/tmp}/m7route.$$"
USERROOT="$OUT/userroot"      # -> BLENDER_USER_RESOURCES  (== OPFS /projects)
TEMPROOT="$OUT/recovery"      # -> TMPDIR (BKE_tempdir_base) (== OPFS /projects/.recovery)
mkdir -p "$USERROOT" "$TEMPROOT"
export BLENDER_USER_RESOURCES="$USERROOT"

echo "== probe R1: appdir resolution honors BLENDER_USER_RESOURCES under emscripten =="
TMPDIR="$TEMPROOT" "$NODE" "$JS" --background --factory-startup \
  --python-expr "import bpy,os
ur='$USERROOT'; tr='$TEMPROOT'
usr=bpy.utils.resource_path('USER')
cfg=bpy.utils.user_resource('CONFIG')        # -> BKE_appdir_folder_id_create(BLENDER_USER_CONFIG)
dat=bpy.utils.user_resource('DATAFILES')
print('RESOURCE_USER', usr.startswith(ur), repr(usr))
print('USER_CONFIG', cfg.startswith(ur) and cfg.rstrip('/').endswith('config'), repr(cfg))
print('CONFIG_CREATED', os.path.isdir(cfg))
print('USER_DATAFILES', dat.startswith(ur), repr(dat))
print('TEMPDIR', bpy.app.tempdir.startswith(tr), repr(bpy.app.tempdir))" \
  2>/dev/null | grep -aE 'RESOURCE_USER|USER_CONFIG|CONFIG_CREATED|USER_DATAFILES|TEMPDIR'

echo "== probe R2: userpref + recent-files land in the routed config dir =="
TMPDIR="$TEMPROOT" "$NODE" "$JS" --background --factory-startup \
  --python-expr "import bpy,os
cfg=bpy.utils.user_resource('CONFIG')
bpy.ops.wm.save_userpref()                    # -> config/userpref.blend
up=os.path.join(cfg,'userpref.blend')
print('USERPREF_SAVED', os.path.exists(up), os.path.getsize(up) if os.path.exists(up) else 0)
# Save a user .blend into the routed project tree, then confirm recent-files is tracked.
proj=os.path.join('$USERROOT','scene_route.blend')
bpy.ops.wm.save_as_mainfile(filepath=proj)
print('SAVEAS_ROUTED', os.path.exists(proj), 'magic='+open(proj,'rb').read(7).decode('latin1'))" \
  2>/dev/null | grep -aE 'USERPREF_SAVED|SAVEAS_ROUTED'

echo "== R-check: on-disk tree Blender produced under the routed roots =="
find "$USERROOT" "$TEMPROOT" -maxdepth 3 \( -name '*.blend' -o -name 'recent-files.txt' \) 2>/dev/null \
  | sed "s#$OUT/##" | sort

rm -rf "$OUT"
# Expected:
#  RESOURCE_USER True .../userroot ; USER_CONFIG True .../userroot/config ; CONFIG_CREATED True
#  USER_DATAFILES True .../userroot/datafiles ; TEMPDIR True .../recovery/blender_XXXXXX
#  USERPREF_SAVED True <bytes> ; SAVEAS_ROUTED True magic=BLENDER
