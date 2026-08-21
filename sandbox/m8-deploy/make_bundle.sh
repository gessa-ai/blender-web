#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# make_bundle.sh - assemble a static-hosting bundle for the blender-web windowed
# gate build (M8 deploy prep). Prepare-only: this writes a LOCAL bundle dir; it
# never deploys, pushes, or names anything public.
#
# Layout produced (Cloudflare-Pages-style; docroot = the bundle dir):
#   <out>/index.html                  <- platform_web/shell/windowed.html verbatim
#   <out>/diagnostics-bootstrap.js    <- early error capture used by the current shell
#   <out>/boot-windowed.js            <- shell boot (loads /bin/blender_browser.js)
#   <out>/file-bridge.js              <- trusted file/open/save bridge used by the shell
#   <out>/wgpu-preinit-worker.js      <- PROVENANCE COPY ONLY (see note below)
#   <out>/_headers                    <- COOP/COEP/CORP + MIME + cache
#   <out>/bin/blender_browser.js      <- Emscripten glue (has the preinit post-js baked in)
#   <out>/bin/blender_browser.wasm    <- symlink by default, real copy with --copy
#   <out>/bin/blender_browser.data    <- symlink by default, real copy with --copy
#   <out>/BUNDLE_MANIFEST.txt         <- generated sizes + provenance
#
# NOTE on wgpu-preinit-worker.js: it is a `--post-js` compiled INTO
# blender_browser.js at link time (it runs at the tail of the module body in the
# main thread and in every pthread `new Worker(pthreadMainJs)` - there is no
# separate `.worker.js`). The copy in the bundle is documentation/provenance only;
# nothing fetches it at runtime. It is included so the served bundle is a complete,
# auditable snapshot of the shell sources.
#
# Usage:
#   sandbox/m8-deploy/make_bundle.sh [--copy] [--brotli] [--out DIR] [--bin DIR]
#                                      [--selfcheck]
#     --copy     real file copies for wasm/data (a self-contained ~230 MB bundle
#                you could rsync/upload). Default: symlink (fast, local-serve only).
#     --brotli   also measure brotli-q11 wire size of js/wasm/data (SLOW on the
#                150 MB+ wasm; off by default). Raw sizes are always recorded.
#     --out DIR  bundle output dir (default sandbox/m8-deploy/bundle).
#     --bin DIR  gate build bin dir (default build-wasm-windowed-opt/bin, or
#                $BLENDER_WEB_BIN if set).
#
# The gate binary is a moving target in this shared checkout (the gpu/render lanes
# rebuild it); the manifest records the exact bytes + mtime of whatever was current
# at assembly time.
set -euo pipefail

SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(cd -- "${SELF_DIR}/../.." && pwd -P)"
SHELL_DIR="${REPO}/platform_web/shell"

OUT="${SELF_DIR}/bundle"
BIN="${BLENDER_WEB_BIN:-${REPO}/build-wasm-windowed-opt/bin}"
MODE="symlink"
DO_BROTLI=0
SELF_CHECK=0

die() { echo "make_bundle: FATAL: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --copy)   MODE="copy" ;;
    --brotli) DO_BROTLI=1 ;;
    --out)
      [ $# -ge 2 ] || die "--out requires a directory"
      OUT="$2"; shift
      ;;
    --bin)
      [ $# -ge 2 ] || die "--bin requires a directory"
      BIN="$2"; shift
      ;;
    --selfcheck) SELF_CHECK=1 ;;
    -h|--help) sed -n '2,45p' "$0"; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
  shift
done

# Resolve caller-relative inputs before creating any output. The assembler replaces
# its output tree, so that tree is confined to this script's generated namespace.
case "${BIN}" in /*) ;; *) BIN="$(pwd -P)/${BIN}" ;; esac
case "${OUT}" in /*) ;; *) OUT="$(pwd -P)/${OUT}" ;; esac
BIN="$(python3 - "${BIN}" <<'PY'
import pathlib, sys
print(pathlib.Path(sys.argv[1]).resolve(strict=False))
PY
)"
OUT="$(python3 - "${OUT}" <<'PY'
import pathlib, sys
print(pathlib.Path(sys.argv[1]).resolve(strict=False))
PY
)"
case "${OUT}" in
  "${SELF_DIR}/bundle"|"${SELF_DIR}/bundle-"*) ;;
  *) die "--out must be a generated bundle path under ${SELF_DIR} (bundle or bundle-*): ${OUT}" ;;
esac

if [ "${SELF_CHECK}" -eq 1 ]; then
  [ "${SELF_DIR}" = "${REPO}/sandbox/m8-deploy" ] || \
    die "derived deploy source directory does not match repository layout: ${SELF_DIR}"
  [ -f "${REPO}/GOAL.md" ] || die "derived repository root is missing GOAL.md: ${REPO}"
  for f in windowed.html diagnostics-bootstrap.js boot-windowed.js file-bridge.js \
    wgpu-preinit-worker.js; do
    [ -f "${SHELL_DIR}/${f}" ] || die "self-check shell source missing: ${f}"
  done
  [ -f "${SELF_DIR}/_headers" ] || die "self-check _headers template missing"
  echo "M8_DEPLOY_ASSEMBLY_SELFCHECK_PASS root=derived shell_sources=5 writes=0"
  exit 0
fi

for f in windowed.html diagnostics-bootstrap.js boot-windowed.js file-bridge.js \
  wgpu-preinit-worker.js; do
  [ -f "${SHELL_DIR}/${f}" ] || die "shell ${f} missing (${SHELL_DIR})"
done
[ -f "${SELF_DIR}/_headers" ]           || die "committed _headers template missing"
for f in blender_browser.js blender_browser.wasm blender_browser.data; do
  [ -f "${BIN}/${f}" ] || die "gate build artifact missing: ${BIN}/${f} (build the windowed-opt target first)"
done

echo "make_bundle: bin=${BIN}"
echo "make_bundle: out=${OUT}  mode=${MODE}  brotli=${DO_BROTLI}"

rm -rf "${OUT}"
mkdir -p "${OUT}/bin"

# --- shell (index + boot + provenance preinit + _headers) --------------------
cp "${SHELL_DIR}/windowed.html"          "${OUT}/index.html"
cp "${SHELL_DIR}/diagnostics-bootstrap.js" "${OUT}/diagnostics-bootstrap.js"
cp "${SHELL_DIR}/boot-windowed.js"       "${OUT}/boot-windowed.js"
cp "${SHELL_DIR}/file-bridge.js"          "${OUT}/file-bridge.js"
cp "${SHELL_DIR}/wgpu-preinit-worker.js" "${OUT}/wgpu-preinit-worker.js"
cp "${SELF_DIR}/_headers"                "${OUT}/_headers"

# --- glue js (always a copy; tiny) -------------------------------------------
cp "${BIN}/blender_browser.js"           "${OUT}/bin/blender_browser.js"

# --- payload (symlink or copy) -----------------------------------------------
place() {
  local src="$1" dst="$2"
  if [ "${MODE}" = "copy" ]; then
    cp "${src}" "${dst}"
  else
    ln -s "${src}" "${dst}"
  fi
}
place "${BIN}/blender_browser.wasm" "${OUT}/bin/blender_browser.wasm"
place "${BIN}/blender_browser.data" "${OUT}/bin/blender_browser.data"

# --- manifest ----------------------------------------------------------------
MAN="${OUT}/BUNDLE_MANIFEST.txt"
sz() {
  python3 - "$1" <<'PY'
import os, sys
print(os.stat(sys.argv[1]).st_size)
PY
}
mt() {
  python3 - "$1" <<'PY'
import datetime, os, sys
stamp = os.stat(sys.argv[1]).st_mtime
print(datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).isoformat())
PY
}
head_short="$(cd "${REPO}" && git rev-parse --short HEAD)"

{
  echo "blender-web static-hosting bundle - manifest"
  echo "generated:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "repo HEAD:   ${head_short}"
  echo "source bin:  ${BIN}"
  echo "payload mode:${MODE}"
  echo ""
  echo "file                          raw bytes      mtime"
  printf "%-28s %12s   %s\n" "index.html"            "$(sz "${OUT}/index.html")"           "$(mt "${OUT}/index.html")"
  printf "%-28s %12s   %s\n" "diagnostics-bootstrap.js" "$(sz "${OUT}/diagnostics-bootstrap.js")" "$(mt "${OUT}/diagnostics-bootstrap.js")"
  printf "%-28s %12s   %s\n" "boot-windowed.js"      "$(sz "${OUT}/boot-windowed.js")"     "$(mt "${OUT}/boot-windowed.js")"
  printf "%-28s %12s   %s\n" "file-bridge.js"        "$(sz "${OUT}/file-bridge.js")"       "$(mt "${OUT}/file-bridge.js")"
  printf "%-28s %12s   %s\n" "wgpu-preinit-worker.js" "$(sz "${OUT}/wgpu-preinit-worker.js")" "$(mt "${OUT}/wgpu-preinit-worker.js")"
  printf "%-28s %12s   %s\n" "_headers"              "$(sz "${OUT}/_headers")"             "$(mt "${OUT}/_headers")"
  printf "%-28s %12s   %s\n" "bin/blender_browser.js"   "$(sz "${BIN}/blender_browser.js")"   "$(mt "${BIN}/blender_browser.js")"
  printf "%-28s %12s   %s\n" "bin/blender_browser.wasm" "$(sz "${BIN}/blender_browser.wasm")" "$(mt "${BIN}/blender_browser.wasm")"
  printf "%-28s %12s   %s\n" "bin/blender_browser.data" "$(sz "${BIN}/blender_browser.data")" "$(mt "${BIN}/blender_browser.data")"
  total=$(( $(sz "${BIN}/blender_browser.js") + $(sz "${BIN}/blender_browser.wasm") + $(sz "${BIN}/blender_browser.data") ))
  echo ""
  total_mib="$(awk -v total="${total}" 'BEGIN { printf "%.1f", total / 1048576 }')"
  printf "payload total (js+wasm+data): %s bytes  (%s MiB)\n" "${total}" "${total_mib}"
} > "${MAN}"

if [ "${DO_BROTLI}" = "1" ]; then
  echo "make_bundle: measuring brotli-q11 (slow)..." >&2
  {
    echo ""
    echo "brotli-q11 wire sizes (measured now on THIS build):"
    for f in blender_browser.js blender_browser.wasm blender_browser.data; do
      raw=$(sz "${BIN}/${f}")
      br=$(brotli -q 11 -c "${BIN}/${f}" | wc -c | tr -d ' ')
      ratio="$(awk -v raw="${raw}" -v br="${br}" 'BEGIN { printf "%.2f", raw / br }')"
      printf "  %-24s raw %12s -> br %11s  (%sx)\n" "${f}" "${raw}" "${br}" "${ratio}"
    done
  } >> "${MAN}"
fi

echo ""
echo "make_bundle: bundle assembled at ${OUT}"
cat "${MAN}"
echo ""
echo "make_bundle: NEXT - serve + verify:"
echo "  python3 ${SELF_DIR}/serve_bundle.py 8130 ${OUT}   # COOP/COEP static server"
echo "  BW_NODE_MODULES=${REPO}/.m4-node/node_modules \\"
echo "    ${REPO}/tools/emsdk/node/22.16.0_64bit/bin/node ${SELF_DIR}/verify_boot.mjs 1280x720 8130"
