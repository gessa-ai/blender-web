#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Install the pure-python wheels bl_pkg (the extensions system) imports at register,
# into the embedded CPython's site-packages. Idempotent, additive.
#
# WHY: bl_pkg register (addons_core/bl_pkg) imports, on the windowed browser boot, the
# whole third-party closure of _bpy_internal/http/downloader.py:51-55 +
# _bpy_internal/assets/remote_library/json_parsing.py:16-17:
#   import cattrs / cattrs.preconf.json          (downloader.py:51-52, json_parsing.py:16-17)
#   import requests / requests.adapters          (downloader.py:53-54)
#   import urllib3.util.retry                     (downloader.py:55)
# `requests` transitively imports urllib3, certifi, charset_normalizer and idna at module
# load. Absent, register raises ModuleNotFoundError and Blender pops the asset-library
# recovery dialog (M4 first-pixels golden pollution) — the same boot path whose
# `import multiprocessing.synchronize` gap the mp shim already closed (scripts/deps/python.sh,
# notes/python-emcc605-probe.md M4.python-debt); these are the imports right after it
# (line 49 multiprocessing, 51 cattrs, 53 requests). Reading downloader.py to the end, the
# ONLY other non-stdlib imports are Blender-internal (bpy/_bpy_internal/bl_pkg); setuptools
# appears solely in bl_pkg/tests/modules/python_wheel_generate.py (CLI wheel-gen, NOT the
# register/boot path), so it is deliberately excluded. This is the full boot closure.
#
# HOW NATIVE GETS THEM: Blender's superbuild does a build-time
#   `pip install --no-binary :all: ... requests==${REQUESTS_VERSION} cattrs==${CATTRS_VERSION} ...`
# into the bundled python's site-packages (upstream/build_files/build_environment/cmake/
# python_site_packages.cmake:35-58; versions in versions.cmake:443-458). For PURE-PYTHON
# packages the `--no-binary` sdist build and the `py3-none-any` wheel produce byte-equivalent
# importable modules, so we mirror the mechanism the standard way: fetch the SAME pinned
# versions' pure-python wheels from PyPI (version + SHA-256 pinned/verified, exactly like
# scripts/deps/python.sh pins the CPython tarball MD5) and extract them into
#   lib/wasm/lib/python3.13/site-packages/
# The embedded interpreter is the same CPython 3.13.13; these carry NO compiled extension
# (verified: zero .so in the oracle's shipped trees — charset_normalizer ships its pure-python
# md.py fallback, not the optional mypyc md.*.so), so no cross-compile is involved —
# they are the identical modules native Blender 5.2.0 ships.
#
# VERSIONS (pinned to upstream versions.cmake so the wasm payload == the native oracle):
#   attrs             25.3.0     (versions.cmake:443 ATTRS_VERSION)              MIT         -> attr/ attrs/
#   cattrs            25.1.1     (versions.cmake:444 CATTRS_VERSION)             MIT         -> cattr/ cattrs/   (needs attrs, typing_extensions)
#   typing_extensions 4.14.1     (versions.cmake:446 TYPING_EXTENSIONS_VERSION) PSF-2.0     -> typing_extensions.py  (cattrs hard dep, unconditional)
#   idna              3.10       (versions.cmake:449 IDNA_VERSION)               BSD-3-Clause-> idna/            (requests dep)
#   charset_normalizer 3.4.1     (versions.cmake:451 CHARSET_NORMALIZER_VERSION) MIT        -> charset_normalizer/ (requests dep)
#   urllib3           2.4.0      (versions.cmake:453 URLLIB3_VERSION)            MIT         -> urllib3/         (requests dep + direct import)
#   certifi           2025.4.26  (versions.cmake:456 CERTIFI_VERSION)            MPL-2.0     -> certifi/         (requests dep; Mozilla CA bundle)
#   requests          2.32.3     (versions.cmake:458 REQUESTS_VERSION)           Apache-2.0  -> requests/        (Apache-2.0 is GPLv3-compatible; Blender ships it under GPL-2.0-or-later)
# cattrs' `exceptiongroup` requirement is `python_version < '3.11'` only, so it is NOT
# needed on 3.13 (confirmed absent from the oracle's shipped site-packages).
#
# SHIMS (web-only, no native counterpart): urllib3's sys.platform=='emscripten' branch
# (urllib3/__init__.py:208-211) unconditionally imports the Pyodide runtime modules `js` +
# `pyodide.ffi` (contrib/emscripten/fetch.py:45-46), which our non-Pyodide CPython lacks —
# so on the actual wasm build `import requests` still dies at register. This script therefore
# also installs the raise-on-use import-shims scripts/deps/python-shims/{js.py,pyodide/} into
# site-packages (same additive/atomic discipline). Import succeeds, networking does NOT —
# an honest deferral: ledger/deferred.json id=emscripten-network-transport; full analysis in
# notes/python-emcc605-probe.md "THE NEXT WALL".
#
# ADDITIVE / CONCURRENCY: this only creates the package paths it owns (listed in OWNED
# below); it never touches site-packages/numpy or the stdlib _multiprocessing shim (the
# e3c8158 preservation the harvest depends on). Each package is staged then swapped into
# place with a single rename(2) so a concurrent gpu .data regen never observes a
# half-written tree.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
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
"idna|3.10|idna-3.10-py3-none-any.whl|946d195a0d259cbba61165e88e65941f16e9b36ea6ddb97f00452bae8b1287d3|https://files.pythonhosted.org/packages/76/c6/c88e154df9c4e1a2a66ccf0005a88dfb2650c1dffb6f5ce603dfbd452ce3/idna-3.10-py3-none-any.whl"
"charset_normalizer|3.4.1|charset_normalizer-3.4.1-py3-none-any.whl|d98b1668f06378c6dbefec3b92299716b931cd4e6061f3c875a71ced1780ab85|https://files.pythonhosted.org/packages/0e/f6/65ecc6878a89bb1c23a086ea335ad4bf21a588990c3f535a227b9eea9108/charset_normalizer-3.4.1-py3-none-any.whl"
"urllib3|2.4.0|urllib3-2.4.0-py3-none-any.whl|4e16665048960a0900c702d4a66415956a584919c03361cac9f1df5c5dd7e813|https://files.pythonhosted.org/packages/6b/11/cc635220681e93a0183390e26485430ca2c7b5f9d33b15c74c2861cb8091/urllib3-2.4.0-py3-none-any.whl"
"certifi|2025.4.26|certifi-2025.4.26-py3-none-any.whl|30350364dfe371162649852c63336a15c70c6510c2ad5015b21c2345311805f3|https://files.pythonhosted.org/packages/4a/7e/3db2bd1b1f9e95f7cddca6d6e75e2f2bd9f51b1246e546d88addca0106bd/certifi-2025.4.26-py3-none-any.whl"
"requests|2.32.3|requests-2.32.3-py3-none-any.whl|70761cfe03c773ceb22aa2f671b4757976145175cdfca038c02654d061d6dcc6|https://files.pythonhosted.org/packages/f9/9b/335f9764261e915ed497fcdeb11df5dfd6f7bf257d4a6a2a686d80da4d54/requests-2.32.3-py3-none-any.whl"
)

# Import-time markers proving each wheel's tree is materialised (used for the idempotent
# early-exit and the final verify). Package dir __init__ (or module file) per wheel.
MARKERS=(
  "$SITE/attr/__init__.py"
  "$SITE/attrs/__init__.py"
  "$SITE/cattr/__init__.py"
  "$SITE/cattrs/__init__.py"
  "$SITE/typing_extensions.py"
  "$SITE/idna/__init__.py"
  "$SITE/charset_normalizer/__init__.py"
  "$SITE/urllib3/__init__.py"
  "$SITE/certifi/__init__.py"
  "$SITE/requests/__init__.py"
  "$SITE/js.py"
  "$SITE/pyodide/__init__.py"
  "$SITE/pyodide/ffi.py"
)

all_present() { for m in "${MARKERS[@]}"; do [ -e "$m" ] || return 1; done; return 0; }

# Idempotent (2nd run ~0s). WHEELS_FORCE_REINSTALL=1 re-extracts even if present.
if [ -z "${WHEELS_FORCE_REINSTALL:-}" ] && all_present; then
  echo "wheels: cattrs+attrs+typing_extensions+requests(+urllib3,certifi,charset_normalizer,idna) + js/pyodide.ffi shims already installed — skip (WHEELS_FORCE_REINSTALL=1 to force)"
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

# Atomic per-path swap into site-packages. OWNED lists exactly what these wheels lay down
# (nothing else in site-packages is ours to touch). dist-info dirs are matched by glob so a
# version bump doesn't strand the old metadata.
OWNED=( attr attrs cattr cattrs typing_extensions.py idna charset_normalizer urllib3 certifi requests )
OWNED_GLOBS=(
  "attrs-*.dist-info" "cattrs-*.dist-info" "typing_extensions-*.dist-info"
  "idna-*.dist-info" "charset_normalizer-*.dist-info" "urllib3-*.dist-info"
  "certifi-*.dist-info" "requests-*.dist-info"
)

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

# --- python-shims: js + pyodide.ffi import-shims (Pyodide-runtime namespace) -----
# Source of truth is scripts/deps/python-shims/ next to this script (works from a
# worktree before merge); the pyodide package is staged then swapped with one
# rename(2), same concurrency discipline as the wheels above.
SHIM_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/python-shims"
install -m644 "$SHIM_DIR/js.py" "$SITE/js.py"
rm -rf "$STAGE/pyodide"; mkdir -p "$STAGE/pyodide"
install -m644 "$SHIM_DIR/pyodide/__init__.py" "$SHIM_DIR/pyodide/ffi.py" "$STAGE/pyodide/"
rm -rf "$SITE/pyodide"; mv "$STAGE/pyodide" "$SITE/pyodide"
echo "wheels: installed js + pyodide.ffi import-shims (raise-on-use; networking deferred)"

# --- verify harvested trees -----------------------------------------------------
for m in "${MARKERS[@]}"; do
  [ -e "$m" ] || { echo "wheels: install missing $m"; exit 1; }
done
# guard the e3c8158 protections: numpy + the mp shim must still be present alongside us
[ -e "$SITE/numpy/__init__.py" ] || { echo "wheels: WARNING site-packages/numpy is absent (unexpected — not ours to fix, but the payload is incomplete)"; }
[ -e "$PREFIX/lib/python${PY_SHORT}/_multiprocessing.py" ] || { echo "wheels: WARNING stdlib _multiprocessing shim is absent (unexpected)"; }

rm -rf "$SCRATCH"
echo "wheels: installed attrs 25.3.0 + cattrs 25.1.1 + typing_extensions 4.14.1 + idna 3.10 + charset_normalizer 3.4.1 + urllib3 2.4.0 + certifi 2025.4.26 + requests 2.32.3 + js/pyodide.ffi shims -> $SITE"
