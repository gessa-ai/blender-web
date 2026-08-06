#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Install the pure-python wheels bl_pkg (the extensions system) imports at register,
# into the embedded CPython's site-packages. Idempotent, additive.
#
# WHY: bl_pkg register (addons_core/bl_pkg) walks
#   _bpy_internal/http/downloader.py:51            `import cattrs`
#   _bpy_internal/assets/remote_library/json_parsing.py:16-17  `import cattrs[.preconf.json]`
# on the windowed browser boot. Absent, register raises ModuleNotFoundError and Blender
# pops the asset-library recovery dialog (M4 first-pixels golden pollution) — the same
# boot path whose `import multiprocessing.synchronize` gap the mp shim already closed
# (scripts/deps/python.sh, notes/python-emcc605-probe.md M4.python-debt); cattrs is the
# NEXT import in downloader.py right after it (line 49 multiprocessing, line 51 cattrs).
#
# HOW NATIVE GETS THEM: Blender's superbuild does a build-time
#   `pip install --no-binary :all: ... attrs==${ATTRS_VERSION} cattrs==${CATTRS_VERSION} ...`
# into the bundled python's site-packages (upstream/build_files/build_environment/cmake/
# python_site_packages.cmake:35-58; versions in versions.cmake:443-446). For PURE-PYTHON
# packages the `--no-binary` sdist build and the `py3-none-any` wheel produce byte-equivalent
# importable modules, so we mirror the mechanism the standard way: fetch the SAME pinned
# versions' pure-python wheels from PyPI (version + SHA-256 pinned/verified, exactly like
# scripts/deps/python.sh pins the CPython tarball MD5) and extract them into
#   lib/wasm/lib/python3.13/site-packages/
# The embedded interpreter is the same CPython 3.13.13; these carry NO compiled extension
# (verified: zero .so in the oracle's shipped trees), so no cross-compile is involved —
# they are the identical modules native Blender 5.2.0 ships.
#
# VERSIONS (pinned to upstream versions.cmake so the wasm payload == the native oracle):
#   attrs   25.3.0  (versions.cmake:443 ATTRS_VERSION)   MIT      -> attr/ attrs/
#   cattrs  25.1.1  (versions.cmake:444 CATTRS_VERSION)  MIT      -> cattr/ cattrs/  (needs attrs, typing_extensions)
#   typing_extensions 4.14.1 (versions.cmake:446)        PSF-2.0  -> typing_extensions.py  (cattrs hard dep, unconditional)
# cattrs' `exceptiongroup` requirement is `python_version < '3.11'` only, so it is NOT
# needed on 3.13 (confirmed absent from the oracle's shipped site-packages).
#
# ADDITIVE / CONCURRENCY: this only creates the eight package paths it owns (listed in
# OWNED below); it never touches site-packages/numpy or the stdlib _multiprocessing shim
# (the e3c8158 preservation the harvest depends on). Each package is staged then swapped
# into place with a single rename(2) so a concurrent gpu .data regen never observes a
# half-written tree.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
PY_SHORT="3.13"
SITE="$PREFIX/lib/python${PY_SHORT}/site-packages"
CACHE="$ROOT/build-deps/_cache"
SCRATCH="$ROOT/build-deps/wheels"

# name|version|filename|sha256|url
WHEELS=(
"attrs|25.3.0|attrs-25.3.0-py3-none-any.whl|427318ce031701fea540783410126f03899a97ffc6f61596ad581ac2e40e3bc3|https://files.pythonhosted.org/packages/77/06/bb80f5f86020c4551da315d78b3ab75e8228f89f0162f2c3a819e407941a/attrs-25.3.0-py3-none-any.whl"
"cattrs|25.1.1|cattrs-25.1.1-py3-none-any.whl|1b40b2d3402af7be79a7e7e097a9b4cd16d4c06e6d526644b0b26a063a1cc064|https://files.pythonhosted.org/packages/18/b0/215274ef0d835bbc1056392a367646648b6084e39d489099959aefcca2af/cattrs-25.1.1-py3-none-any.whl"
"typing_extensions|4.14.1|typing_extensions-4.14.1-py3-none-any.whl|d1e1e3b58374dc93031d6eda2420a48ea44a36c2b4766a4fdeb3710755731d76|https://files.pythonhosted.org/packages/b5/00/d631e67a838026495268c2f6884f3711a15a9a2a96cd244fdaea53b823fb/typing_extensions-4.14.1-py3-none-any.whl"
)

# Import-time markers proving each wheel's tree is materialised (used for the idempotent
# early-exit and the final verify). attrs -> attr/; cattrs -> cattrs/; te -> module file.
MARKERS=(
  "$SITE/attr/__init__.py"
  "$SITE/attrs/__init__.py"
  "$SITE/cattr/__init__.py"
  "$SITE/cattrs/__init__.py"
  "$SITE/typing_extensions.py"
)

all_present() { for m in "${MARKERS[@]}"; do [ -e "$m" ] || return 1; done; return 0; }

# Idempotent (2nd run ~0s). WHEELS_FORCE_REINSTALL=1 re-extracts even if present.
if [ -z "${WHEELS_FORCE_REINSTALL:-}" ] && all_present; then
  echo "wheels: attrs+cattrs+typing_extensions already installed in site-packages — skip (WHEELS_FORCE_REINSTALL=1 to force)"
  exit 0
fi

sha256_of() { shasum -a 256 "$1" 2>/dev/null | awk '{print $1}' || sha256sum "$1" | awk '{print $1}'; }

mkdir -p "$CACHE" "$SITE"
STAGE="$SCRATCH/stage"
rm -rf "$STAGE"; mkdir -p "$STAGE"

for spec in "${WHEELS[@]}"; do
  IFS='|' read -r name version fname sha url <<<"$spec"
  whl="$CACHE/$fname"
  # fetch + verify (cache survives across runs; re-verify every time)
  [ -f "$whl" ] || curl -fL --retry 3 -o "$whl" "$url"
  got="$(sha256_of "$whl")"
  if [ "$got" != "$sha" ]; then
    # a truncated/poisoned cache entry: drop and refetch once
    rm -f "$whl"; curl -fL --retry 3 -o "$whl" "$url"; got="$(sha256_of "$whl")"
  fi
  [ "$got" = "$sha" ] || { echo "wheels: SHA-256 mismatch for $fname ($got != $sha)"; exit 1; }
  # a wheel is a zip; extract its package + dist-info trees into the stage
  unzip -q -o "$whl" -d "$STAGE"
  echo "wheels: staged $name $version ($fname)"
done

# Atomic per-path swap into site-packages. OWNED lists exactly what these three wheels
# lay down (nothing else in site-packages is ours to touch). dist-info dirs are matched
# by glob so a version bump doesn't strand the old metadata.
OWNED=( attr attrs cattr cattrs typing_extensions.py )
OWNED_GLOBS=( "attrs-*.dist-info" "cattrs-*.dist-info" "typing_extensions-*.dist-info" )

# prune any stale versioned dist-info this script previously installed
for g in "${OWNED_GLOBS[@]}"; do
  for old in "$SITE"/$g; do [ -e "$old" ] && rm -rf "$old"; done
done
# swap in the freshly staged trees (dirs = rename; single file = install)
for item in "${OWNED[@]}"; do
  src="$STAGE/$item"
  [ -e "$src" ] || { echo "wheels: expected $item in staged wheels but it is absent"; exit 1; }
  dst="$SITE/$item"
  if [ -d "$src" ]; then
    rm -rf "$dst"; mv "$src" "$dst"
  else
    install -m644 "$src" "$dst"
  fi
done
for g in "${OWNED_GLOBS[@]}"; do
  for src in "$STAGE"/$g; do
    [ -e "$src" ] || continue
    mv "$src" "$SITE/$(basename "$src")"
  done
done

# --- verify harvested trees -----------------------------------------------------
for m in "${MARKERS[@]}"; do
  [ -e "$m" ] || { echo "wheels: install missing $m"; exit 1; }
done
# guard the e3c8158 protections: numpy + the mp shim must still be present alongside us
[ -e "$SITE/numpy/__init__.py" ] || { echo "wheels: WARNING site-packages/numpy is absent (unexpected — not ours to fix, but the payload is incomplete)"; }
[ -e "$PREFIX/lib/python${PY_SHORT}/_multiprocessing.py" ] || { echo "wheels: WARNING stdlib _multiprocessing shim is absent (unexpected)"; }

rm -rf "$SCRATCH"
echo "wheels: installed attrs 25.3.0 + cattrs 25.1.1 + typing_extensions 4.14.1 -> $SITE/{attr,attrs,cattr,cattrs,typing_extensions.py}"
