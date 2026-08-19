#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build CPython (libpython3.13.a) for wasm32-emscripten, static, JS-EH.
# Version + hash pinned from upstream/build_files/build_environment/cmake/versions.cmake
# (PYTHON_VERSION 3.13.13, PYTHON_HASH MD5 3a19dd420883dd599728c9dd07c141e7, line ~385).
# Idempotent.
#
# Exception model = JS-EH (`-fexceptions`, SUPPORT_LONGJMP defaults to emscripten), decided
# by the M2.0b probe (notes/python-emcc605-probe.md) + ADR-001 appendix: the 29 harvested
# deps are already JS-EH, so libpython joins the existing stack with zero dep rebuild.
# CONFIG B (Wasm-EH) is a validated fallback but NOT what we ship for M2.
#
# Method (vanilla 3.13.13, ZERO source patches needed on emcc 6.0.5 — see the probe notes):
#   1. native bootstrap interpreter from the SAME source tree (cross builds need a
#      --with-build-python of the same minor). On a case-insensitive macOS FS the binary is
#      `python.exe`, not `python` (it collides with the in-tree `Python/` object dir); we
#      accept either name.
#   2. emconfigure the documented Tools/wasm browser-static target with -fexceptions.
#   3. emmake the full target (builds libpython3.13.a + generated files e.g. the
#      _sysconfigdata module), then harvest with the Makefile's own inclinstall/libinstall.
#
# HARVEST layout (unix-prefix, consistent with every other lib/wasm dep + exactly what
# build_files/cmake/Modules/FindPythonLibsUnix.cmake probes for):
#   lib/wasm/lib/libpython3.13.a            <- find_library(python3.13)
#   lib/wasm/include/python3.13/Python.h    <- headers (+ cpython/, internal/, pyconfig.h)
#   lib/wasm/lib/python3.13/abc.py ...      <- unzipped stdlib (FindPythonLibsUnix abc.py
#                                              probe; libinstall also drops the build-
#                                              generated _sysconfigdata_*_emscripten_*.py
#                                              here, which a raw Lib/ copy would miss)
# We harvest the FULL unzipped stdlib for correctness/parity now; freezing / trimming it and
# the browser python313.zip preload are later size optimisations, not a first move (GOAL).
#
# NOTE: this does NOT enable WITH_PYTHON in blender_web.cmake — that is M2.3 (driver-gated,
# after M1 closes). This script only produces + harvests the artifact.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/python"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(getconf _NPROCESSORS_ONLN)"

PY_VERSION="3.13.13"
PY_SHORT="3.13"
PY_URL="https://www.python.org/ftp/python/${PY_VERSION}/Python-${PY_VERSION}.tar.xz"
PY_MD5="3a19dd420883dd599728c9dd07c141e7"
TARBALL="$CACHE/Python-${PY_VERSION}.tar.xz"

LIB_MARKER="$PREFIX/lib/libpython${PY_SHORT}.a"
HDR_MARKER="$PREFIX/include/python${PY_SHORT}/Python.h"
STD_MARKER="$PREFIX/lib/python${PY_SHORT}/abc.py"

# Single-process _multiprocessing shim (see the header block): install our
# thread-backed stand-in into the harvested stdlib. Idempotent + cheap (one
# file copy), so it is refreshed even on the no-op early-exit below.
SHIM_SRC="$ROOT/scripts/deps/python-shims/_multiprocessing.py"
SHIM_DST="$PREFIX/lib/python${PY_SHORT}/_multiprocessing.py"
install_mp_shim() {
  [ -f "$SHIM_SRC" ] || { echo "python: missing mp shim $SHIM_SRC"; exit 1; }
  install -m644 "$SHIM_SRC" "$SHIM_DST"
}

# Idempotent by default (2nd run 0s). PYTHON_FORCE_REBUILD=1 forces a rebuild
# when the recipe changes (e.g. module set) WITHOUT first deleting the live .a —
# a concurrent gpu relink keeps reading the old artifact until the atomic swap
# at the very end replaces it in one rename(2).
if [ -z "${PYTHON_FORCE_REBUILD:-}" ] \
   && [ -f "$LIB_MARKER" ] && [ -f "$HDR_MARKER" ] && [ -f "$STD_MARKER" ]; then
  install_mp_shim
  echo "python ${PY_VERSION}: already installed — skip (mp shim ensured; PYTHON_FORCE_REBUILD=1 to rebuild)"; exit 0
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"
mkdir -p "$CACHE" "$SCRATCH"

# --- fetch + verify -------------------------------------------------------------
[ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$PY_URL"
GOT="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
[ "$GOT" = "$PY_MD5" ] || { echo "python: MD5 mismatch ($GOT != $PY_MD5)"; exit 1; }

SRC="$SCRATCH/Python-${PY_VERSION}"
rm -rf "$SRC"
tar -xf "$TARBALL" -C "$SCRATCH"
BUILD_TRIPLE="$(CC=cc CC_FOR_BUILD=cc "$SRC/config.guess")"

# --- 1. native bootstrap interpreter (host tool, config-independent) ------------
NATIVE="$SCRATCH/build-native"
rm -rf "$NATIVE"; mkdir -p "$NATIVE"
( export CC=cc CXX=c++ AR=ar RANLIB=ranlib; cd "$NATIVE" && "$SRC/configure" -C >/dev/null && make -j"$NPROC" >/dev/null )
# macOS case-insensitive FS names it python.exe (avoids clash with the Python/ object dir).
BUILD_PY="$NATIVE/python.exe"; [ -x "$BUILD_PY" ] || BUILD_PY="$NATIVE/python"
[ -x "$BUILD_PY" ] || { echo "python: native bootstrap interpreter not found"; exit 1; }
"$BUILD_PY" --version

# --- 2. cross-configure: browser static, JS-EH (-fexceptions) -------------------
XBUILD="$SCRATCH/build-wasm"
rm -rf "$XBUILD"; mkdir -p "$XBUILD"
cd "$XBUILD"
# -matomics -mbulk-memory (M2.3): libpython links into Blender's shared-memory
# (-pthread) mono-wasm module, and wasm-ld refuses any object in a --shared-memory
# link that lacks the atomics/bulk-memory wasm features. These flags add exactly
# those features WITHOUT emscripten's full -pthread runtime (no __EMSCRIPTEN_PTHREADS__),
# so CPython keeps its single-threaded browser build (ADR-001 posture) yet every
# object (incl. bundled libmpdec/Hacl) is link-compatible with the threaded host.
# py_cv_module_*=n/a: disable the optional stdlib C-extensions that would each drag
# a companion / external native library into the Blender mono-wasm link, none of
# which is needed to boot `import bpy`, and every one of which has a safe fallback:
#   _sqlite3, _bz2            -> only satisfiable by the emscripten sqlite3/bzip2
#                               PORTS (the standalone probe used them; the mono-wasm
#                               does not). No stdlib import fatals without them.
#   _decimal                 -> needs bundled libmpdec; the `decimal` module falls
#                               back to the pure-python `_pydecimal` automatically.
#   pyexpat _elementtree     -> need CPython's bundled expat, which would duplicate
#                               lib/wasm's libexpat.a (linked for OCIO). XML parsing
#                               is not on the bpy boot path.
# HASH MODULES — all Hacl-based, all KEPT (M4.python-debt correction of M2.3):
#   _sha2 _sha3 _md5 _sha1 _blake2 are ENABLED (none passed py_cv_module_*=n/a).
#   The M2.3 note "the Hacl archives DON'T build as a standalone .a (only SHA2
#   does), so disable _md5/_sha1/_sha3/_blake2" was BACKWARDS: only _sha2 LINKS
#   a *prebuilt* archive (Modules/_hacl/libHacl_Hash_SHA2.a, see
#   Modules/Setup.stdlib.in:84); _md5/_sha1/_sha3 compile their Hacl source
#   (_hacl/Hacl_Hash_*.c, lines 82/83/85) DIRECTLY into the module object, and
#   _blake2 compiles its own _blake2/*_impl.c (line 86) — NONE needs a standalone
#   .a, and none has an external dep. All are pure-scalar C on wasm32 (SHA3/MD5/
#   SHA1 carry no SIMD/int128; _blake2 falls back to its reference rounds because
#   configure detects no HAVE_SSE2/__SSSE3__ under emcc). Their objects land in
#   libpython3.13.a directly. Enabling them clears hashlib's boot-time
#   "code for hash md5/sha1/blake2/sha3/shake was not found" error and gives
#   hashlib.sha3_512 (M4.python-debt). SELF-CONTAINED preserved.
# _multiprocessing — NOT built (genuinely unbuildable, not merely disabled).
#   Its semaphore.c uses POSIX *named* semaphores (sem_open/sem_close/sem_unlink/
#   sem_getvalue/sem_timedwait); emscripten exposes those only in its -pthread
#   libc, and our browser-target libpython is single-threaded (no
#   __EMSCRIPTEN_PTHREADS__), so those symbols are UNDEFINED at link — configure
#   correctly resolves ac_cv_func_sem_unlink=no and drops the module. bl_pkg's
#   register imports multiprocessing.synchronize, which does
#   `from _multiprocessing import SemLock, sem_unlink`; absent, that raises and
#   Blender pops the asset-library dialog on boot (M4-golden pollution). Pyodide
#   ships no _multiprocessing and its ecosystem patches the consumer, but bl_pkg
#   is pinned/read-only. So we install a thread-backed pure-python shim
#   (scripts/deps/python-shims/_multiprocessing.py) into the harvested stdlib —
#   the honest single-process degradation (a one-process "multiprocessing"
#   semaphore IS a threading semaphore), not a raise-on-use stub. See the harvest
#   step below.
# Result: a SELF-CONTAINED libpython whose only external symbols are zlib's, resolved
# by lib/wasm's libz.a already on the Blender link. Re-enable any of the dep-bearing
# exts later by harvesting/porting its dep (M2.6+), guarded by that milestone's needs.
# -DPY_CALL_TRAMPOLINE (M2.5): vanilla 3.13.13 SHIPS Python/emscripten_trampoline.c
# but its build system never defines PY_CALL_TRAMPOLINE, so the file compiles to an
# EMPTY object and CPython's C-method calls go through a DIRECT wasm call_indirect
# (pycore_object.h:847 `#if !(__EMSCRIPTEN__ && PY_CALL_TRAMPOLINE)`). emscripten
# type-checks indirect calls, and CPython casts C method pointers to a uniform
# PyCFunction signature (METH_NOARGS/O/FASTCALL differ), so any bpy/RNA method call
# traps "null function or function signature mismatch". Defining the macro activates
# the shipped trampoline, which adapts the signature (via wasm type-reflection when
# present, else the universal `wasmTable.get(func)(a,b,c)` EM_JS fallback). This is
# the C-function trampoline the M2.0b probe never exercised (it only tested a Python
# lambda callback, which needs no signature adaptation).
CONFIG_SITE="$SRC/Tools/wasm/config.site-wasm32-emscripten" \
CFLAGS="-fexceptions -matomics -mbulk-memory -DPY_CALL_TRAMPOLINE" \
CPPFLAGS="-matomics -mbulk-memory -DPY_CALL_TRAMPOLINE -I$PREFIX/include" \
LDFLAGS="-fexceptions" \
  emconfigure "$SRC/configure" -C \
    --host=wasm32-unknown-emscripten \
    --build="$BUILD_TRIPLE" \
    --with-emscripten-target=browser \
    --with-build-python="$BUILD_PY" \
    --disable-shared --disable-ipv6 \
    py_cv_module__sqlite3=n/a py_cv_module__bz2=n/a \
    py_cv_module__decimal=n/a py_cv_module__lzma=n/a \
    py_cv_module_pyexpat=n/a py_cv_module__elementtree=n/a

# --- 3. build libpython + generated files, then harvest via install targets -----
emmake make -j"$NPROC"
[ -f "$XBUILD/libpython${PY_SHORT}.a" ] || { echo "python: libpython not built"; exit 1; }

STAGE="$SCRATCH/stage"; rm -rf "$STAGE"
# inclinstall -> headers (+pyconfig.h); libinstall -> stdlib (+ generated _sysconfigdata).
# Default configure prefix is /usr/local, so DESTDIR nests under usr/local/.
emmake make DESTDIR="$STAGE" inclinstall libinstall

mkdir -p "$PREFIX/lib" "$PREFIX/include"
# Merge CPython's in-tree companion static libs (libmpdec for _decimal, the Hacl
# archives for the builtin _sha*/_md5/_blake2 hash modules) INTO libpython so the
# embed is a single self-contained archive — dependency_targets.cmake links one
# ${PYTHON_LIBRARIES}, and a single archive makes symbol resolution order-independent
# (_decimal.o -> mpd_*, hashlib -> Hacl_* resolve within the one archive). Anything
# CPython leaves external (zlib) is satisfied by lib/wasm at the Blender link.
COMPANION_LIBS=$(find "$XBUILD" -name '*.a' ! -name "libpython${PY_SHORT}.a" 2>/dev/null | sort)
COMBINED="$SCRATCH/libpython${PY_SHORT}.combined.a"
rm -f "$COMBINED"
if [ -n "$COMPANION_LIBS" ]; then
  echo "python: merging companion archives into libpython${PY_SHORT}.a:"
  echo "$COMPANION_LIBS" | sed 's#.*/#  - #'
  {
    echo "CREATE $COMBINED"
    echo "ADDLIB $XBUILD/libpython${PY_SHORT}.a"
    for _a in $COMPANION_LIBS; do echo "ADDLIB $_a"; done
    echo "SAVE"
    echo "END"
  } | emar -M
  emranlib "$COMBINED"
else
  echo "python: no companion archives found — using libpython${PY_SHORT}.a as-is"
  cp "$XBUILD/libpython${PY_SHORT}.a" "$COMBINED"
fi
# Headers + stdlib first (a concurrent Blender RELINK consumes only the .a, not
# these), then install the mp shim into the stdlib, and swap the .a LAST and
# ATOMICALLY — a gpu worker may be relinking build-wasm-windowed against this
# exact file, so the replace window is a single rename(2), not a byte copy.
rm -rf "$PREFIX/include/python${PY_SHORT}"
cp -R "$STAGE/usr/local/include/python${PY_SHORT}" "$PREFIX/include/python${PY_SHORT}"
# Refresh the stdlib but PRESERVE site-packages. Sibling dep scripts install pure
# trees there (numpy -> lib/python3.13/site-packages/numpy, scripts/deps/numpy.sh);
# the fresh CPython stdlib from $STAGE carries NONE, so a blind rm+cp of the whole
# python3.13/ dir would wipe them and re-red the m2b numpy-importing sculpt/paint
# suites. Move site-packages aside (same-FS rename), refresh, then restore it.
STDLIB_DST="$PREFIX/lib/python${PY_SHORT}"
SP_KEEP="$PREFIX/lib/.site-packages.keep.$$"
rm -rf "$SP_KEEP"
[ -d "$STDLIB_DST/site-packages" ] && mv "$STDLIB_DST/site-packages" "$SP_KEEP"
rm -rf "$STDLIB_DST"
cp -R "$STAGE/usr/local/lib/python${PY_SHORT}" "$STDLIB_DST"
if [ -d "$SP_KEEP" ]; then
  rm -rf "$STDLIB_DST/site-packages"          # drop the fresh stdlib's placeholder
  mv "$SP_KEEP" "$STDLIB_DST/site-packages"   # restore preserved trees (numpy, ...)
fi
install_mp_shim

# Prune the triplicate __pycache__ (.pyc at plain/opt-1/opt-2) that `make libinstall`
# just compiled into the harvested stdlib. Emscripten --preload-file has no exclude
# globs, so leaving these makes blender_browser.data ship each stdlib module up to 4x
# (source + 3 bytecode levels). Keeping .py only is import-safe (CPython recompiles to
# memory; node-embed reads this same tree and is equally safe). See
# scripts/deps/prune-preload-pycache.sh + notes/m8-pycache-strip.md.
"$ROOT/scripts/deps/prune-preload-pycache.sh" "$STDLIB_DST"

LIB_TMP="$PREFIX/lib/.libpython${PY_SHORT}.a.tmp.$$"
cp "$COMBINED" "$LIB_TMP"; chmod 644 "$LIB_TMP"
mv -f "$LIB_TMP" "$PREFIX/lib/libpython${PY_SHORT}.a"   # atomic on the same FS

# --- verify harvested triple ----------------------------------------------------
[ -f "$LIB_MARKER" ] || { echo "python: harvest missing $LIB_MARKER"; exit 1; }
[ -f "$HDR_MARKER" ] || { echo "python: harvest missing $HDR_MARKER"; exit 1; }
[ -f "$STD_MARKER" ] || { echo "python: harvest missing $STD_MARKER"; exit 1; }
[ -f "$SHIM_DST" ]   || { echo "python: harvest missing mp shim $SHIM_DST"; exit 1; }
TSYMS="$(emnm "$LIB_MARKER" 2>/dev/null | grep -c ' T ')"
SHA3SYMS="$(emnm "$LIB_MARKER" 2>/dev/null | grep -c 'Hacl_Hash_SHA3')"
echo "python: libpython${PY_SHORT}.a defined-text symbols = $TSYMS (M2.2 baseline 2850, +hash exts now)"
echo "python: Hacl_Hash_SHA3 symbols in libpython = $SHA3SYMS (expect > 0)"
[ "$SHA3SYMS" -gt 0 ] || { echo "python: _sha3 not linked into libpython"; exit 1; }

rm -rf "$SCRATCH"
echo "python ${PY_VERSION}: installed (JS-EH) -> $LIB_MARKER + include/python${PY_SHORT}/ + lib/python${PY_SHORT}/"
