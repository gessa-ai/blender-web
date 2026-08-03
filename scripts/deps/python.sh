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

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/python"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(sysctl -n hw.ncpu)"

PY_VERSION="3.13.13"
PY_SHORT="3.13"
PY_URL="https://www.python.org/ftp/python/${PY_VERSION}/Python-${PY_VERSION}.tar.xz"
PY_MD5="3a19dd420883dd599728c9dd07c141e7"
TARBALL="$CACHE/Python-${PY_VERSION}.tar.xz"

LIB_MARKER="$PREFIX/lib/libpython${PY_SHORT}.a"
HDR_MARKER="$PREFIX/include/python${PY_SHORT}/Python.h"
STD_MARKER="$PREFIX/lib/python${PY_SHORT}/abc.py"
if [ -f "$LIB_MARKER" ] && [ -f "$HDR_MARKER" ] && [ -f "$STD_MARKER" ]; then
  echo "python ${PY_VERSION}: already installed — skip"; exit 0
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
BUILD_TRIPLE="$("$SRC/config.guess")"

# --- 1. native bootstrap interpreter (host tool, config-independent) ------------
NATIVE="$SCRATCH/build-native"
rm -rf "$NATIVE"; mkdir -p "$NATIVE"
( cd "$NATIVE" && "$SRC/configure" -C >/dev/null && make -j"$NPROC" >/dev/null )
# macOS case-insensitive FS names it python.exe (avoids clash with the Python/ object dir).
BUILD_PY="$NATIVE/python.exe"; [ -x "$BUILD_PY" ] || BUILD_PY="$NATIVE/python"
[ -x "$BUILD_PY" ] || { echo "python: native bootstrap interpreter not found"; exit 1; }
"$BUILD_PY" --version

# --- 2. cross-configure: browser static, JS-EH (-fexceptions) -------------------
XBUILD="$SCRATCH/build-wasm"
rm -rf "$XBUILD"; mkdir -p "$XBUILD"
cd "$XBUILD"
CONFIG_SITE="$SRC/Tools/wasm/config.site-wasm32-emscripten" \
CFLAGS="-fexceptions" LDFLAGS="-fexceptions" \
  emconfigure "$SRC/configure" -C \
    --host=wasm32-unknown-emscripten \
    --build="$BUILD_TRIPLE" \
    --with-emscripten-target=browser \
    --with-build-python="$BUILD_PY" \
    --disable-shared --disable-ipv6

# --- 3. build libpython + generated files, then harvest via install targets -----
emmake make -j"$NPROC"
[ -f "$XBUILD/libpython${PY_SHORT}.a" ] || { echo "python: libpython not built"; exit 1; }

STAGE="$SCRATCH/stage"; rm -rf "$STAGE"
# inclinstall -> headers (+pyconfig.h); libinstall -> stdlib (+ generated _sysconfigdata).
# Default configure prefix is /usr/local, so DESTDIR nests under usr/local/.
emmake make DESTDIR="$STAGE" inclinstall libinstall

mkdir -p "$PREFIX/lib" "$PREFIX/include"
install -m644 "$XBUILD/libpython${PY_SHORT}.a" "$PREFIX/lib/libpython${PY_SHORT}.a"
rm -rf "$PREFIX/include/python${PY_SHORT}"
cp -R "$STAGE/usr/local/include/python${PY_SHORT}" "$PREFIX/include/python${PY_SHORT}"
rm -rf "$PREFIX/lib/python${PY_SHORT}"
cp -R "$STAGE/usr/local/lib/python${PY_SHORT}" "$PREFIX/lib/python${PY_SHORT}"

# --- verify harvested triple ----------------------------------------------------
[ -f "$LIB_MARKER" ] || { echo "python: harvest missing $LIB_MARKER"; exit 1; }
[ -f "$HDR_MARKER" ] || { echo "python: harvest missing $HDR_MARKER"; exit 1; }
[ -f "$STD_MARKER" ] || { echo "python: harvest missing $STD_MARKER"; exit 1; }
TSYMS="$(emnm "$LIB_MARKER" 2>/dev/null | grep -c ' T ')"
echo "python: libpython${PY_SHORT}.a defined-text symbols = $TSYMS (probe baseline 2850)"

rm -rf "$SCRATCH"
echo "python ${PY_VERSION}: installed (JS-EH) -> $LIB_MARKER + include/python${PY_SHORT}/ + lib/python${PY_SHORT}/"
