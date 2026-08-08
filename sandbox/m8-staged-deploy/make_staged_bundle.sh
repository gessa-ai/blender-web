#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# make_staged_bundle.sh - assemble a STAGED static-hosting bundle: the app boots on
# the stage-0 critical payload and streams the rest post-first-pixels. Prepare-only;
# writes a LOCAL bundle dir, reads the build tree read-only, never relinks.
#
# What differs from sandbox/m8-deploy/make_bundle.sh (the monolith assembler):
#   - bin/blender_browser.data  = STAGE-0 only (stage_pack.py re-slice)
#   - bin/blender_browser.js     = glue with the baked manifest rewritten to stage-0
#                                  real files + zero-length placeholders (dir tree)
#   - bin/stage1.data + bin/stage1-manifest.json = the deferred payload
#   - stage1-loader.js injected after boot-windowed.js (streams stage-1 post-boot)
#   - file-bridge.js included (current windowed.html references it; the monolith
#     assembler predates it)
#
# Usage: make_staged_bundle.sh [--copy] [--brotli] [--no-defer-datafiles]
#                              [--out DIR] [--bin DIR]
set -euo pipefail
REPO="/Users/paws/blender-web"
SHELL_DIR="${REPO}/platform_web/shell"
SELF_DIR="${REPO}/sandbox/m8-staged-deploy"
OUT="${SELF_DIR}/bundle-staged"
BIN="${BLENDER_WEB_BIN:-${REPO}/build-wasm-windowed-opt/bin}"
MODE="symlink"; DO_BROTLI=0; DEFER_DF="--defer-datafiles"

while [ $# -gt 0 ]; do
  case "$1" in
    --copy) MODE="copy" ;;
    --brotli) DO_BROTLI=1 ;;
    --no-defer-datafiles) DEFER_DF="--no-defer-datafiles" ;;
    --out) OUT="$2"; shift ;;
    --bin) BIN="$2"; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done
die() { echo "make_staged_bundle: FATAL: $*" >&2; exit 1; }

for f in windowed.html boot-windowed.js file-bridge.js wgpu-preinit-worker.js; do
  [ -f "${SHELL_DIR}/${f}" ] || die "shell ${f} missing (${SHELL_DIR})"
done
[ -f "${SELF_DIR}/_headers" ] || [ -f "${REPO}/sandbox/m8-deploy/_headers" ] || die "_headers template missing"
[ -f "${SELF_DIR}/stage1-loader.js" ] || die "stage1-loader.js missing"
for f in blender_browser.js blender_browser.wasm blender_browser.data; do
  [ -f "${BIN}/${f}" ] || die "gate build artifact missing: ${BIN}/${f}"
done

echo "make_staged_bundle: bin=${BIN}"
echo "make_staged_bundle: out=${OUT}  mode=${MODE}  ${DEFER_DF}"
rm -rf "${OUT}"; mkdir -p "${OUT}/bin"

# --- shell: index.html (+inject stage1-loader) + boot + bridge + preinit + headers -
cp "${SHELL_DIR}/windowed.html"          "${OUT}/index.html"
cp "${SHELL_DIR}/boot-windowed.js"       "${OUT}/boot-windowed.js"
cp "${SHELL_DIR}/file-bridge.js"         "${OUT}/file-bridge.js"
cp "${SHELL_DIR}/wgpu-preinit-worker.js" "${OUT}/wgpu-preinit-worker.js"
cp "${SELF_DIR}/stage1-loader.js"        "${OUT}/stage1-loader.js"
# inject the stage-1 loader AFTER boot-windowed.js (bundle-only edit)
python3 - "$OUT/index.html" <<'PY'
import sys
p=sys.argv[1]; t=open(p).read()
needle='<script src="/boot-windowed.js"></script>'
add='<script src="/boot-windowed.js"></script>\n  <!-- STAGED DEPLOY: stream the deferred payload after first pixels -->\n  <script src="/stage1-loader.js"></script>'
assert needle in t, "boot-windowed.js script tag not found in index.html"
open(p,"w").write(t.replace(needle,add,1))
PY

# --- _headers: copy template, add a .json rule for stage1-manifest.json -----------
TEMPLATE="${SELF_DIR}/_headers"; [ -f "$TEMPLATE" ] || TEMPLATE="${REPO}/sandbox/m8-deploy/_headers"
cp "$TEMPLATE" "${OUT}/_headers"
cat >> "${OUT}/_headers" <<'EOF'

/bin/*.json
  Content-Type: application/json; charset=utf-8
  Cache-Control: public, max-age=3600
EOF

# --- payload: stage_pack.py re-slices the monolith into stage-0 + stage-1 ----------
python3 "${SELF_DIR}/stage_pack.py" --bin "${BIN}" --out "${OUT}/bin" ${DEFER_DF}

# --- wasm is UNCHANGED (never relinked): symlink or copy --------------------------
if [ "${MODE}" = "copy" ]; then cp "${BIN}/blender_browser.wasm" "${OUT}/bin/blender_browser.wasm"
else ln -sf "${BIN}/blender_browser.wasm" "${OUT}/bin/blender_browser.wasm"; fi

# --- manifest ---------------------------------------------------------------------
MAN="${OUT}/BUNDLE_MANIFEST.txt"; sz(){ stat -f '%z' "$1"; }
head_short="$(cd "${REPO}" && git rev-parse --short HEAD)"
{
  echo "blender-web STAGED static-hosting bundle - manifest"
  echo "generated:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "repo HEAD:   ${head_short}    source bin: ${BIN}    defer-datafiles: ${DEFER_DF}"
  echo ""
  printf "%-30s %12s\n" "index.html"                "$(sz "${OUT}/index.html")"
  printf "%-30s %12s\n" "boot-windowed.js"          "$(sz "${OUT}/boot-windowed.js")"
  printf "%-30s %12s\n" "file-bridge.js"            "$(sz "${OUT}/file-bridge.js")"
  printf "%-30s %12s\n" "stage1-loader.js"          "$(sz "${OUT}/stage1-loader.js")"
  printf "%-30s %12s\n" "bin/blender_browser.js"    "$(sz "${OUT}/bin/blender_browser.js")"
  printf "%-30s %12s\n" "bin/blender_browser.wasm"  "$(sz "${BIN}/blender_browser.wasm")"
  printf "%-30s %12s   (STAGE-0)\n" "bin/blender_browser.data"  "$(sz "${OUT}/bin/blender_browser.data")"
  printf "%-30s %12s   (STAGE-1, deferred)\n" "bin/stage1.data"  "$(sz "${OUT}/bin/stage1.data")"
  printf "%-30s %12s\n" "bin/stage1-manifest.json"  "$(sz "${OUT}/bin/stage1-manifest.json")"
  echo ""
  wasm=$(sz "${BIN}/blender_browser.wasm"); glue=$(sz "${OUT}/bin/blender_browser.js")
  s0=$(sz "${OUT}/bin/blender_browser.data"); s1=$(sz "${OUT}/bin/stage1.data")
  crit=$(( wasm + glue + s0 ))
  printf "critical wire-to-interactive (wasm+glue+stage0): %s bytes (%.1f MiB)\n" "${crit}" "$(echo "scale=1;${crit}/1048576"|bc)"
  printf "deferred (stage1):                               %s bytes (%.1f MiB)\n" "${s1}" "$(echo "scale=1;${s1}/1048576"|bc)"
} > "${MAN}"

if [ "${DO_BROTLI}" = "1" ]; then
  echo "make_staged_bundle: measuring brotli-q11 (slow)..." >&2
  {
    echo ""; echo "brotli-q11 wire sizes:"
    for f in bin/blender_browser.js bin/blender_browser.wasm bin/blender_browser.data bin/stage1.data; do
      raw=$(sz "${OUT}/${f}"); br=$(brotli -q 11 -c "${OUT}/${f}" | wc -c | tr -d ' ')
      printf "  %-26s raw %12s -> br %11s\n" "${f##*/}" "${raw}" "${br}"
    done
  } >> "${MAN}"
fi
echo ""; cat "${MAN}"
echo ""; echo "make_staged_bundle: assembled at ${OUT}"
