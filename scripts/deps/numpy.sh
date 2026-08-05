#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build NumPy (static, baked-into-the-inittab shape) for our wasm32-emscripten CPython 3.13.
# Version + hash pinned from upstream/build_files/build_environment/cmake/versions.cmake
# (NUMPY_VERSION 2.3.4, MD5 8717ed1828a8a390c454c6636e91c46a, BSD-3-Clause). Idempotent.
#
# BUILD SHAPE (a) — static archive registered in a custom inittab, NOT .so side-modules.
# Pyodide builds numpy as dlopen'd .so + dynamic linking, which CONFLICTS with our mono-wasm
# posture (GOAL: no dynamic linking). We instead compile numpy's C extensions to objects with
# meson (the ONLY supported numpy build path since 1.26) and archive them into ONE combined
# libnumpy.a; the 13 production PyInit_* functions are registered in Blender's Python inittab
# (bpy_interface.cc bpy_internal_modules) at the eventual relink (the driver follow-up — this
# script only produces + harvests the artifact, exactly like python.sh does for libpython).
#
# ZERO source patches (recon: notes/deps-numpy.md). Current Pyodide carries NO numpy patches
# either — upstream 2.3.4's meson build is emscripten-aware; the toolchain fixes (fenv,
# longdouble, cross detection, f2py signatures) that used to need Pyodide patches are absorbed
# upstream. The whole cross build is meson OPTIONS + an emscripten CROSS FILE, no edits.
#
# HARVEST layout (consistent with lib/wasm + how the pure-python stdlib is harvested):
#   lib/wasm/lib/libnumpy.a                                   <- driver links this into blender
#   lib/wasm/lib/python3.13/site-packages/numpy/ ...          <- pure-python tree (site auto-adds)
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/numpy"
CACHE="$ROOT/build-deps/_cache"

NP_VERSION="2.3.4"
NP_MD5="8717ed1828a8a390c454c6636e91c46a"
NP_URL="https://github.com/numpy/numpy/releases/download/v${NP_VERSION}/numpy-${NP_VERSION}.tar.gz"
TARBALL="$CACHE/numpy-${NP_VERSION}.tar.gz"

PY_SHORT="3.13"
SITE="$PREFIX/lib/python${PY_SHORT}/site-packages"
LIB_MARKER="$PREFIX/lib/libnumpy.a"
TREE_MARKER="$SITE/numpy/__init__.py"
if [ -f "$LIB_MARKER" ] && [ -f "$TREE_MARKER" ]; then
  echo "numpy ${NP_VERSION}: already installed — skip"; exit 0
fi

# Native build-python (host): drives meson/cython/generators, must be CPython 3.13 to match
# the target minor. Prefer Homebrew's python3.13; else any python3.13 on PATH.
BUILD_PY="/opt/homebrew/bin/python3.13"
[ -x "$BUILD_PY" ] || BUILD_PY="$(command -v python3.13 || true)"
[ -x "$BUILD_PY" ] || { echo "numpy: need a native CPython 3.13 build-python (python3.13) on PATH"; exit 1; }

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1
EM="$ROOT/tools/emsdk/upstream/emscripten"
NODE="$(ls -d "$ROOT"/tools/emsdk/node/*/bin/node 2>/dev/null | head -1)"
mkdir -p "$CACHE" "$SCRATCH"

# --- fetch + verify -------------------------------------------------------------
[ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$NP_URL"
GOT="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
[ "$GOT" = "$NP_MD5" ] || { echo "numpy: MD5 mismatch ($GOT != $NP_MD5)"; exit 1; }

SRC="$SCRATCH/numpy-${NP_VERSION}"
rm -rf "$SRC"; tar -xf "$TARBALL" -C "$SCRATCH"

# --- 1. build venv (meson-python/meson/ninja/cython on the native build-python) -------------
VENV="$SCRATCH/buildvenv"
if [ ! -x "$VENV/bin/meson" ]; then
  rm -rf "$VENV"; "$BUILD_PY" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet "meson>=1.4" "meson-python>=0.16" ninja "cython>=3.0"
fi

# --- 2. cross environment (target-sysconfig injection + emscripten meson cross file) ---------
# The native build-python must REPORT the wasm32 target sysconfig (EXT_SUFFIX/SOABI + the
# lib/wasm include dir) so meson/cython compile against wasm32 pyconfig.h (void*=4, LONG_BIT=32)
# — NOT the 64-bit host headers. Mechanism: _PYTHON_SYSCONFIGDATA_NAME + PYTHONPATH -> a patched
# _sysconfigdata (prefix/INCLUDEPY re-pointed to the lib/wasm harvest) + a sitecustomize that
# overrides sysconfig's scheme-derived include path (which is rooted at the running interpreter's
# base_prefix, hence native). This is the crossenv problem, solved minimally for a static build.
XENV="$SCRATCH/crossenv"
rm -rf "$XENV"; mkdir -p "$XENV"
"$BUILD_PY" - "$ROOT" "$XENV" <<'PYEOF'
import sys
root, xenv = sys.argv[1], sys.argv[2]
src = root + "/lib/wasm/lib/python3.13/_sysconfigdata__emscripten_wasm32-emscripten.py"
ns = {}; exec(open(src).read(), ns); d = ns['build_time_vars']
d['prefix'] = d['exec_prefix'] = root + '/lib/wasm'
d['INCLUDEPY'] = root + '/lib/wasm/include/python3.13'
d['LIBDIR'] = root + '/lib/wasm/lib'
with open(xenv + "/_sysconfigdata__emscripten_wasm32-emscripten.py", "w") as f:
    f.write("build_time_vars = " + repr(d))
inc = root + '/lib/wasm/include/python3.13'
open(xenv + "/sitecustomize.py", "w").write(f'''import sysconfig
_INC = {inc!r}
_gp, _g1 = sysconfig.get_paths, sysconfig.get_path
def get_paths(*a, **k):
    x = dict(_gp(*a, **k)); x['include'] = _INC; x['platinclude'] = _INC; return x
def get_path(n, *a, **k):
    return _INC if n in ('include', 'platinclude') else _g1(n, *a, **k)
sysconfig.get_paths = get_paths; sysconfig.get_path = get_path
''')
PYEOF

CROSSPY="$XENV/cross-python.sh"
cat > "$CROSSPY" <<EOF
#!/usr/bin/env bash
export _PYTHON_SYSCONFIGDATA_NAME=_sysconfigdata__emscripten_wasm32-emscripten
export PYTHONPATH="$XENV\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$BUILD_PY" "\$@"
EOF
chmod +x "$CROSSPY"

CROSS="$SCRATCH/emscripten.cross"
cat > "$CROSS" <<EOF
[binaries]
c = '$EM/emcc'
cpp = '$EM/em++'
ar = '$EM/emar'
ranlib = '$EM/emranlib'
strip = '$EM/emstrip'
python = '$CROSSPY'
exe_wrapper = '$NODE'

[host_machine]
system = 'emscripten'
cpu_family = 'wasm32'
cpu = 'wasm32'
endian = 'little'

[properties]
needs_exe_wrapper = true
skip_sanity_check = true
# emscripten long double is 128-bit IEEE quad (sizeof==16); numpy detects this by RUNNING a
# probe (numpy/_core/meson.build:439) — supply it as a property (matches Pyodide's cross file).
longdouble_format = 'IEEE_QUAD_LE'

[built-in options]
c_args = ['-fexceptions', '-matomics', '-mbulk-memory']
cpp_args = ['-fexceptions', '-matomics', '-mbulk-memory']
c_link_args = ['-fexceptions', '-matomics', '-mbulk-memory']
cpp_link_args = ['-fexceptions', '-matomics', '-mbulk-memory']
EOF

# --- 3. meson setup + compile (numpy's VENDORED meson ships the 'features' CPU module) -------
BUILD="$SCRATCH/build"
VMESON="$SRC/vendored-meson/meson/meson.py"
export PATH="$VENV/bin:$PATH"
export PYTHONPATH="$XENV"
export _PYTHON_SYSCONFIGDATA_NAME=_sysconfigdata__emscripten_wasm32-emscripten
rm -rf "$BUILD"
"$VENV/bin/python" "$VMESON" setup "$BUILD" "$SRC" \
  --cross-file "$CROSS" \
  -Dallow-noblas=true \
  -Ddisable-optimization=true -Ddisable-threading=true \
  -Ddisable-highway=true -Ddisable-svml=true -Ddisable-intel-sort=true \
  -Dwerror=false
ninja -C "$BUILD"

# --- 4. combine the 13 production module objects + internal libs into ONE libnumpy.a ---------
# Dedup by basename: numpy compiles the bundled f2c lapack-lite into BOTH linalg modules; in one
# static link those are duplicate strong symbols. Exclude the 6 test/_simd extensions.
B="$BUILD/numpy"
declare -A seen; OBJS=()
for m in \
  _core/_multiarray_umath linalg/lapack_lite linalg/_umath_linalg fft/_pocketfft_umath \
  random/mtrand random/_common random/bit_generator random/_bounded_integers \
  random/_generator random/_mt19937 random/_philox random/_pcg64 random/_sfc64; do
  while IFS= read -r o; do
    b="$(basename "$o")"; [ -z "${seen[$b]:-}" ] && { seen[$b]=1; OBJS+=("$o"); }
  done < <(find "$B/${m}.cpython-313-wasm32-emscripten.so.p" -name '*.o')
done
INTLIBS=("$B/_core/libnpymath.a" "$B/_core/libunique_hash.a"
         "$B/_core/lib_multiarray_umath_mtargets.a"
         "$B/_core/libargfunc.dispatch.h_baseline.a"
         "$B/random/libnpyrandom.a")
for a in "$B"/_core/libloops_*.dispatch.h_baseline.a; do INTLIBS+=("$a"); done

ARCHIVE="$SCRATCH/libnumpy.a"; rm -f "$ARCHIVE"
{
  echo "CREATE $ARCHIVE"
  for o in "${OBJS[@]}"; do echo "ADDMOD $o"; done
  for a in "${INTLIBS[@]}"; do echo "ADDLIB $a"; done
  echo "SAVE"; echo "END"
} | emar -M
emranlib "$ARCHIVE"

# --- 5. compose the pure-python tree (source *.py + the 3 meson-generated files) -------------
TREE="$SCRATCH/site/numpy"; rm -rf "$SCRATCH/site"; mkdir -p "$TREE"
rsync -am --include='*/' --include='*.py' --exclude='*' "$SRC/numpy/" "$TREE/"
for g in numpy/__init__.py numpy/__config__.py numpy/random/__init__.py; do
  cp "$BUILD/$g" "$SCRATCH/site/$g"
done

# --- 6. harvest to lib/wasm -----------------------------------------------------------------
mkdir -p "$PREFIX/lib" "$SITE"
install -m644 "$ARCHIVE" "$LIB_MARKER"
rm -rf "$SITE/numpy"; cp -R "$SCRATCH/site/numpy" "$SITE/numpy"

[ -f "$LIB_MARKER" ]  || { echo "numpy: harvest missing $LIB_MARKER"; exit 1; }
[ -f "$TREE_MARKER" ] || { echo "numpy: harvest missing $TREE_MARKER"; exit 1; }
NSYMS="$(emnm "$LIB_MARKER" 2>/dev/null | grep -c ' T PyInit_' || true)"
echo "numpy ${NP_VERSION}: installed (static, JS-EH) -> libnumpy.a ($(du -h "$LIB_MARKER" | awk '{print $1}'), ${NSYMS} PyInit_*) + site-packages/numpy/"
