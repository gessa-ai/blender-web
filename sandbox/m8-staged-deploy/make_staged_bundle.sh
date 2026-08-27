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
#   - bin/blender_browser.js     = glue with the baked manifest rewritten to Stage-0
#                                  real files plus discovery-only zero-byte names;
#                                  baked directory creation remains
#   - bin/stage1.data + bin/stage1-manifest.json = the deferred payload
#   - stage1-loader.js injected after boot-windowed.js (streams stage-1 post-boot)
#   - file-bridge.js included (current windowed.html references it; the monolith
#     assembler predates it)
#
# Usage: make_staged_bundle.sh [--copy] [--brotli] [--no-defer-datafiles]
#                              [--out DIR] [--bin DIR] [--selfcheck]
set -euo pipefail
SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(cd -- "${SELF_DIR}/../.." && pwd -P)"
SHELL_DIR="${REPO}/platform_web/shell"
BROTLI_CODEC="${SELF_DIR}/brotli_q11.mjs"
PUBLIC_MINIFIER="${SELF_DIR}/public_shell_minify.mjs"
PTHREAD_LOADER_CONTRACT="${SELF_DIR}/test_pthread_main_loader.mjs"
TERSER_BUNDLE="${REPO}/tools/emsdk/upstream/emscripten/node_modules/terser/dist/bundle.min.js"
PINNED_NODE="${EMSDK_NODE:-${REPO}/tools/emsdk/node/22.16.0_64bit/bin/node}"
OUT="${SELF_DIR}/bundle-staged"
BIN="${BLENDER_WEB_BIN:-${REPO}/build-wasm-windowed-opt/bin}"
DO_BROTLI=1; DEFER_DF="--defer-datafiles"; SELF_CHECK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --copy) : ;; # retained as an explicit, backwards-compatible assertion
    --brotli) : ;; # production q11 siblings are mandatory for an exact bundle
    --no-defer-datafiles) DEFER_DF="--no-defer-datafiles" ;;
    --out) OUT="$2"; shift ;;
    --bin) BIN="$2"; shift ;;
    --selfcheck) SELF_CHECK=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done
die() { echo "make_staged_bundle: FATAL: $*" >&2; exit 1; }

# Resolve CLI paths before creating symlinks. A relative --bin previously made a
# link relative to OUT/bin (and therefore silently produced a missing wasm).
case "${BIN}" in /*) ;; *) BIN="$(pwd -P)/${BIN}" ;; esac
case "${OUT}" in /*) ;; *) OUT="$(pwd -P)/${OUT}" ;; esac
OUT="$(python3 - "${OUT}" <<'PY'
import pathlib, sys
print(pathlib.Path(sys.argv[1]).resolve(strict=False))
PY
)"
# The assembler replaces its output tree. Keep that destructive operation inside
# its exact generated-tree namespace even when --out is supplied.
case "${OUT}" in
  "${SELF_DIR}"/*) ;;
  *) die "--out must be a child of ${SELF_DIR}: ${OUT}" ;;
esac

if [ "${SELF_CHECK}" -eq 1 ]; then
  [ "${SELF_DIR}" = "${REPO}/sandbox/m8-staged-deploy" ] || \
    die "derived staged source directory does not match repository layout: ${SELF_DIR}"
  for f in GOAL.md platform_web/shell/windowed.html \
    platform_web/shell/fonts/bw-interface-sans.woff2 \
    platform_web/shell/fonts/bw-console-mono.woff2 \
    LICENSES/Bitstream-Vera.txt \
    LICENSES/OFL-1.1.txt \
    sandbox/m8-staged-deploy/brotli_q11.mjs \
    sandbox/m8-staged-deploy/stage_pack.py \
    sandbox/m8-staged-deploy/prepare_split_inventory.py \
    sandbox/m8-staged-deploy/public_shell_hardening.py \
    sandbox/m8-staged-deploy/public_shell_minify.mjs \
    sandbox/m8-staged-deploy/pthread-main-loader.js \
    sandbox/m8-staged-deploy/test_pthread_main_loader.mjs \
    sandbox/m8-staged-deploy/test_pthread_shared_main_cache.mjs \
    sandbox/m8-staged-deploy/service-worker.js \
    sandbox/m8-staged-deploy/service-worker-register.js; do
    [ -f "${REPO}/${f}" ] || die "self-check source missing: ${f}"
  done
  [ -x "${PINNED_NODE}" ] || die "pinned Node executable missing: ${PINNED_NODE}"
  "${PINNED_NODE}" "${BROTLI_CODEC}" --selfcheck >/dev/null || \
    die "deterministic Brotli q11/lgwin=24 self-check failed"
  "${PINNED_NODE}" "${PUBLIC_MINIFIER}" --selfcheck >/dev/null || \
    die "deterministic public-shell minifier self-check failed"
  "${PINNED_NODE}" "${PTHREAD_LOADER_CONTRACT}" >/dev/null || \
    die "pthread main-script Blob loader contract failed"
  echo "M8_STAGED_ASSEMBLY_SELFCHECK_PASS root=derived sources=15 brotli=q11-lgwin24 minifier=terser-5.39.0 pthread=single-transfer apply_manifest_reads=0 writes=0"
  exit 0
fi

for f in windowed.html diagnostics-bootstrap.js boot-windowed.js file-bridge.js wgpu-preinit-worker.js; do
  [ -f "${SHELL_DIR}/${f}" ] || die "shell ${f} missing (${SHELL_DIR})"
done
[ -f "${SHELL_DIR}/fonts/bw-interface-sans.woff2" ] || \
  die "shell font missing (${SHELL_DIR}/fonts/bw-interface-sans.woff2)"
[ -f "${SHELL_DIR}/fonts/bw-console-mono.woff2" ] || \
  die "Stage-0 mono font missing (${SHELL_DIR}/fonts/bw-console-mono.woff2)"
[ -x "${PINNED_NODE}" ] || die "pinned Node executable missing: ${PINNED_NODE}"
[ "$("${PINNED_NODE}" --version)" = "v22.16.0" ] || \
  die "public bundle requires pinned Node v22.16.0: ${PINNED_NODE}"
[ -f "${BROTLI_CODEC}" ] || die "deterministic Brotli codec missing: ${BROTLI_CODEC}"
"${PINNED_NODE}" "${BROTLI_CODEC}" --selfcheck >/dev/null || \
  die "deterministic Brotli q11/lgwin=24 self-check failed"
[ -f "${PUBLIC_MINIFIER}" ] || die "deterministic public-shell minifier missing: ${PUBLIC_MINIFIER}"
[ -f "${PTHREAD_LOADER_CONTRACT}" ] || die "pthread main-script Blob loader contract missing: ${PTHREAD_LOADER_CONTRACT}"
[ -f "${TERSER_BUNDLE}" ] || die "pinned Terser executable bundle missing: ${TERSER_BUNDLE}"
"${PINNED_NODE}" "${PUBLIC_MINIFIER}" --selfcheck >/dev/null || \
  die "deterministic public-shell minifier self-check failed"
"${PINNED_NODE}" "${PTHREAD_LOADER_CONTRACT}" >/dev/null || \
  die "pthread main-script Blob loader contract failed"
[ -f "${SELF_DIR}/_headers" ] || [ -f "${REPO}/sandbox/m8-deploy/_headers" ] || die "_headers template missing"
[ -f "${SELF_DIR}/stage1-loader.js" ] || die "stage1-loader.js missing"
[ -f "${SELF_DIR}/pthread-main-loader.js" ] || die "pthread-main-loader.js missing"
[ -f "${SELF_DIR}/service-worker.js" ] || die "service-worker.js missing"
[ -f "${SELF_DIR}/service-worker-register.js" ] || die "service-worker-register.js missing"
[ -f "${REPO}/sandbox/corpus-prep/corpus/stress_mixed.blend" ] || die "allowlisted share scene missing"
[ -f "${SELF_DIR}/share-scene.license" ] || die "share scene license missing"
for f in LICENSE AUTHORS NOTICE THIRD-PARTY.md PROVENANCE.md; do
  [ -f "${REPO}/${f}" ] || die "public legal file missing: ${f}"
done
for f in Apache-2.0.txt BSD-3-Clause.txt Bitstream-Vera.txt CC0-1.0.txt GPL-2.0-or-later.txt GPL-3.0-or-later.txt OFL-1.1.txt; do
  [ -f "${REPO}/LICENSES/${f}" ] || die "public license text missing: LICENSES/${f}"
done
for f in LicenseRef-OpenSubdiv-TOST-1.0.txt; do
  [ -f "${REPO}/LICENSES/${f}" ] || die "public license text missing: LICENSES/${f}"
done
[ -f "${REPO}/THIRD_PARTY_NOTICES/OpenSubdiv-3.7.0-NOTICE.txt" ] || \
  die "OpenSubdiv 3.7.0 notice missing"
OPENUSD_LEGAL="${REPO}/lib/wasm/share/licenses/OpenUSD-26.03"
[ -f "${OPENUSD_LEGAL}/LICENSE.txt" ] || die "OpenUSD 26.03 LICENSE.txt missing"
[ -f "${OPENUSD_LEGAL}/NOTICE.txt" ] || die "OpenUSD 26.03 NOTICE.txt missing"
for f in blender_browser.js blender_browser.data blender_browser.split-build.json; do
  [ -f "${BIN}/${f}" ] || die "gate build artifact missing: ${BIN}/${f}"
done

echo "make_staged_bundle: bin=${BIN}"
echo "make_staged_bundle: out=${OUT}  mode=copy  ${DEFER_DF}"
rm -rf "${OUT}"; mkdir -p "${OUT}/bin" "${OUT}/fonts" "${OUT}/scenes" "${OUT}/legal/LICENSES" \
  "${OUT}/legal/OpenUSD-26.03" "${OUT}/legal/THIRD_PARTY_NOTICES"

# --- shell: index.html (+inject stage1-loader) + boot + bridge + preinit + headers -
cp "${SHELL_DIR}/windowed.html"          "${OUT}/index.html"
cp "${SHELL_DIR}/diagnostics-bootstrap.js" "${OUT}/diagnostics-bootstrap.js"
cp "${SHELL_DIR}/boot-windowed.js"       "${OUT}/boot-windowed.js"
cp "${SHELL_DIR}/file-bridge.js"         "${OUT}/file-bridge.js"
cp "${SHELL_DIR}/wgpu-preinit-worker.js" "${OUT}/wgpu-preinit-worker.js"
cp "${SHELL_DIR}/fonts/bw-interface-sans.woff2" \
  "${OUT}/fonts/bw-interface-sans.woff2"
cp "${SELF_DIR}/stage1-loader.js"        "${OUT}/stage1-loader.js"
cp "${SELF_DIR}/pthread-main-loader.js" "${OUT}/pthread-main-loader.js"
cp "${SELF_DIR}/service-worker-register.js" "${OUT}/service-worker-register.js"
cp "${REPO}/sandbox/corpus-prep/corpus/stress_mixed.blend" "${OUT}/scenes/stress-mixed.blend"
cp "${SELF_DIR}/share-scene.license" "${OUT}/scenes/stress-mixed.blend.license"
cp "${REPO}/LICENSE" "${OUT}/legal/LICENSE.txt"
cp "${REPO}/AUTHORS" "${OUT}/legal/AUTHORS.txt"
cp "${REPO}/NOTICE" "${OUT}/legal/NOTICE.txt"
cp "${REPO}/THIRD-PARTY.md" "${OUT}/legal/THIRD-PARTY.md"
cp "${REPO}/PROVENANCE.md" "${OUT}/legal/PROVENANCE.md"
for f in Apache-2.0.txt BSD-3-Clause.txt Bitstream-Vera.txt CC0-1.0.txt GPL-2.0-or-later.txt GPL-3.0-or-later.txt OFL-1.1.txt; do
  cp "${REPO}/LICENSES/${f}" "${OUT}/legal/LICENSES/${f}"
done
cp "${REPO}/LICENSES/LicenseRef-OpenSubdiv-TOST-1.0.txt" \
  "${OUT}/legal/LICENSES/LicenseRef-OpenSubdiv-TOST-1.0.txt"
cp "${REPO}/THIRD_PARTY_NOTICES/OpenSubdiv-3.7.0-NOTICE.txt" \
  "${OUT}/legal/THIRD_PARTY_NOTICES/OpenSubdiv-3.7.0-NOTICE.txt"
cp "${OPENUSD_LEGAL}/LICENSE.txt" "${OUT}/legal/OpenUSD-26.03/LICENSE.txt"
cp "${OPENUSD_LEGAL}/NOTICE.txt" "${OUT}/legal/OpenUSD-26.03/NOTICE.txt"
openusd_license_sha="$(shasum -a 256 "${OUT}/legal/OpenUSD-26.03/LICENSE.txt" | cut -d' ' -f1)"
openusd_notice_sha="$(shasum -a 256 "${OUT}/legal/OpenUSD-26.03/NOTICE.txt" | cut -d' ' -f1)"
[ "${openusd_license_sha}" = "4d6e8e3a9bd0104e10c48e3bc6af2f0976448a70a377d20cef674740f96f4452" ] || \
  die "OpenUSD 26.03 license integrity drift: ${openusd_license_sha}"
[ "${openusd_notice_sha}" = "f6ad9d41f77b1bd8edaecd64bd1e13f4224876b010e2415e308267a84862bc14" ] || \
  die "OpenUSD 26.03 notice integrity drift: ${openusd_notice_sha}"
share_sha="$(shasum -a 256 "${OUT}/scenes/stress-mixed.blend" | cut -d' ' -f1)"
[ "${share_sha}" = "c2a7974ceec3da3ed11a102d924f3318ea82ffa29fd393a8ff5103b6181b4e2e" ] || \
  die "allowlisted share scene integrity drift: ${share_sha}"
# Public static bundles MUST NOT expose arbitrary Python/argv execution through
# URL parameters. Development source retains the hooks for local rigs; the
# shared deterministic transformer fails if the literal seam moves.
python3 "${SELF_DIR}/public_shell_hardening.py" \
  --input "${OUT}/boot-windowed.js" --output "${OUT}/boot-windowed.js"
# --- _headers: copy template, add a .json rule for stage1-manifest.json -----------
TEMPLATE="${SELF_DIR}/_headers"; [ -f "$TEMPLATE" ] || TEMPLATE="${REPO}/sandbox/m8-deploy/_headers"
cp "$TEMPLATE" "${OUT}/_headers"
cat >> "${OUT}/_headers" <<'EOF'

/bin/*.json
  Content-Type: application/json; charset=utf-8
  Cache-Control: no-cache, must-revalidate

/service-worker.js
  Content-Type: text/javascript; charset=utf-8
  Cache-Control: no-cache

/service-worker-register.js
  Content-Type: text/javascript; charset=utf-8
  Cache-Control: no-cache, must-revalidate

/scenes/*.blend
  Content-Type: application/octet-stream
  Cache-Control: public, max-age=31536000, immutable
EOF

# --- payload: stage_pack.py re-slices the monolith into stage-0 + stage-1 ----------
python3 "${SELF_DIR}/stage_pack.py" --bin "${BIN}" --out "${OUT}/bin" ${DEFER_DF}
main_glue_sha="$(shasum -a 256 "${OUT}/bin/blender_browser.js" | cut -d' ' -f1)"
# Bind both consumers to one immutable, content-addressed response. The ordinary
# same-origin script remains CSP-compliant; pthread-main-loader fetches the exact
# same URL from Chromium's HTTP cache and verifies the decoded SHA-256 before
# handing the Blob to Emscripten.
python3 - "${OUT}/index.html" "${OUT}/pthread-main-loader.js" "${main_glue_sha}" <<'PY'
import pathlib, re, sys
index_path = pathlib.Path(sys.argv[1])
loader_path = pathlib.Path(sys.argv[2])
digest = sys.argv[3]
if not re.fullmatch(r"[0-9a-f]{64}", digest):
    raise SystemExit("page-glue SHA-256 is not canonical")
loader = loader_path.read_text(encoding="utf-8")
token = "__BW_PAGE_GLUE_SHA256__"
if loader.count(token) != 1:
    raise SystemExit("pthread page-glue identity token is absent/ambiguous")
loader_path.write_text(loader.replace(token, digest), encoding="utf-8")

index = index_path.read_text(encoding="utf-8")
boot_tag = '<script src="/boot-windowed.js"></script>'
boot_injected = boot_tag + \
    '\n  <!-- STAGED DEPLOY: stream the deferred payload after first pixels, then cache it -->' + \
    '\n  <script src="/stage1-loader.js"></script>' + \
    '\n  <script src="/service-worker-register.js"></script>'
main_tag = '<script src="/bin/blender_browser.js"></script>'
main_url = f"/bin/blender_browser.js?sha256={digest}"
main_injected = f'<script src="{main_url}"></script>' + \
    '\n  <!-- PUBLIC: one immutable page-glue body also supplies every pthread Blob. -->' + \
    '\n  <script src="/pthread-main-loader.js"></script>'
if index.count(boot_tag) != 1 or index.count(main_tag) != 1:
    raise SystemExit("public loader injection seam is absent/ambiguous")
index_path.write_text(
    index.replace(main_tag, main_injected, 1).replace(boot_tag, boot_injected, 1),
    encoding="utf-8")
PY
# Public bundle JavaScript is derived from the reviewed source with one pinned,
# deterministic compressor. This stays bundle-only: CAPTURE/APPLY Wasm bytes and
# their profile generation are untouched.
for f in diagnostics-bootstrap.js file-bridge.js boot-windowed.js pthread-main-loader.js \
         stage1-loader.js; do
  "${PINNED_NODE}" "${PUBLIC_MINIFIER}" \
    --input "${OUT}/${f}" --output "${OUT}/${f}"
done
"${PINNED_NODE}" "${PTHREAD_LOADER_CONTRACT}" \
  "${OUT}/pthread-main-loader.js" "${OUT}/bin/blender_browser.js" >/dev/null || \
  die "assembled pthread shared-source loader contract failed"

# --- exact split inventory: validate once, copy every shipping shard ---------------
split_rows="$(mktemp "${TMPDIR:-/tmp}/bw-split-rows.XXXXXX")"
trap 'rm -f "${split_rows}"' EXIT
python3 "${SELF_DIR}/prepare_split_inventory.py" --bin "${BIN}" \
  --public-manifest "${OUT}/bin/split-build.json" --rows "${split_rows}"
shipped_wasm=()
while IFS=$'\t' read -r filename role bytes sha critical request_phase; do
  [ -n "${filename}" ] || die "empty split inventory row"
  cp "${BIN}/${filename}" "${OUT}/bin/${filename}"
  shipped_wasm+=("${filename}")
done < "${split_rows}"
[ "${#shipped_wasm[@]}" -ge 2 ] || die "split inventory did not yield primary+deferred Wasm"

# The service worker version is a content digest, not a hand-maintained release
# string. Stable binary names therefore cannot retain stale bytes across deploys.
cache_files=(
  index.html diagnostics-bootstrap.js boot-windowed.js file-bridge.js pthread-main-loader.js \
           wgpu-preinit-worker.js _headers \
           fonts/bw-interface-sans.woff2 \
           stage1-loader.js service-worker-register.js \
           scenes/stress-mixed.blend scenes/stress-mixed.blend.license \
           legal/LICENSE.txt legal/AUTHORS.txt legal/NOTICE.txt \
           legal/THIRD-PARTY.md legal/PROVENANCE.md \
           legal/LICENSES/Apache-2.0.txt legal/LICENSES/BSD-3-Clause.txt \
           legal/LICENSES/Bitstream-Vera.txt \
           legal/LICENSES/CC0-1.0.txt legal/LICENSES/GPL-2.0-or-later.txt \
           legal/LICENSES/GPL-3.0-or-later.txt \
           legal/LICENSES/OFL-1.1.txt \
           legal/LICENSES/LicenseRef-OpenSubdiv-TOST-1.0.txt \
           legal/THIRD_PARTY_NOTICES/OpenSubdiv-3.7.0-NOTICE.txt \
           legal/OpenUSD-26.03/LICENSE.txt legal/OpenUSD-26.03/NOTICE.txt \
           bin/blender_browser.js bin/blender_browser.data bin/split-build.json \
           bin/stage1-manifest.json bin/stage1.data)
for filename in "${shipped_wasm[@]}"; do cache_files+=("bin/${filename}"); done

if [ "${DO_BROTLI}" = "1" ]; then
  echo "make_staged_bundle: writing mandatory production Brotli q11/lgwin=24 siblings (slow)..." >&2
  for f in bin/blender_browser.js bin/blender_browser.data bin/stage1.data; do
    "${PINNED_NODE}" "${BROTLI_CODEC}" encode "${OUT}/${f}" "${OUT}/${f}.br"
  done
  for filename in "${shipped_wasm[@]}"; do
    "${PINNED_NODE}" "${BROTLI_CODEC}" encode \
      "${OUT}/bin/${filename}" "${OUT}/bin/${filename}.br"
  done
fi

cache_identity_files=()
for f in "${cache_files[@]}"; do
  [ "${f}" = "service-worker-register.js" ] || cache_identity_files+=("${f}")
done
for f in bin/blender_browser.js bin/blender_browser.data bin/stage1.data; do
  cache_identity_files+=("${f}.br")
done
for filename in "${shipped_wasm[@]}"; do
  cache_identity_files+=("bin/${filename}.br")
done
cache_version="$(python3 - "${OUT}" "${SELF_DIR}/service-worker.js" \
  "${SELF_DIR}/service-worker-register.js" \
  "${cache_identity_files[@]}" <<'PY'
import hashlib, pathlib, sys
root, worker_template, register_template, *names = sys.argv[1:]
rows = []
for name in names:
    data = (pathlib.Path(root) / name).read_bytes()
    rows.append((name, hashlib.sha256(data).hexdigest()))
rows.append(("service-worker.js.template", hashlib.sha256(pathlib.Path(worker_template).read_bytes()).hexdigest()))
rows.append(("service-worker-register.js.template", hashlib.sha256(pathlib.Path(register_template).read_bytes()).hexdigest()))
payload = "".join(f"{digest}  {name}\n" for name, digest in sorted(rows)).encode()
print(hashlib.sha256(payload).hexdigest()[:20])
PY
)"
python3 - "${SELF_DIR}/service-worker-register.js" \
  "${OUT}/service-worker-register.js" "${cache_version}" <<'PY'
import pathlib, sys
template, output, version = sys.argv[1:]
text = pathlib.Path(template).read_text(encoding="utf-8")
token = "__BW_EXPECTED_CACHE_VERSION__"
if text.count(token) != 1:
    raise SystemExit(f"service-worker registration token is absent/ambiguous: {token}")
pathlib.Path(output).write_text(text.replace(token, version), encoding="utf-8")
PY
python3 - "${SELF_DIR}/service-worker.js" "${OUT}/service-worker.js" \
  "${cache_version}" "${split_rows}" "${cache_files[@]}" <<'PY'
import hashlib, json, pathlib, sys
template, output, version, rows, *cache_files = sys.argv[1:]
precache = ["/"] + sorted("/" + name for name in cache_files if name != "_headers")
cache_first = []
deferred = {}
main_url = "/bin/blender_browser.js?sha256=" + hashlib.sha256(
    (pathlib.Path(output).parent / "bin/blender_browser.js").read_bytes()).hexdigest()
for line in pathlib.Path(rows).read_text(encoding="utf-8").splitlines():
    filename, role, _bytes, sha, _critical, _phase = line.split("\t")
    if role == "deferred":
        query_url = f"/bin/{filename}?sha256={sha}"
        cache_first.append(query_url)
        precache[precache.index(f"/bin/{filename}")] = query_url
        deferred[f"/bin/{filename}"] = query_url
precache[precache.index("/bin/blender_browser.js")] = main_url
cache_first.append(main_url)
precache = [precache[0]] + sorted(precache[1:])
# Once this exact worker controls a page, every generated precache URL except the
# version-discovery registration script is cache-first within its content-versioned
# namespace. The registration script must revalidate online so an old controlled
# shell can discover/authenticate the newly active generated worker; its same-version
# cached copy remains the exact offline fallback.
cache_first = [url for url in precache if url != "/service-worker-register.js"]
digests = {}
root = pathlib.Path(output).parent
for name in cache_files:
    if name == "_headers":
        continue
    url = main_url if name == "bin/blender_browser.js" else deferred.get(f"/{name}", f"/{name}")
    digests[url] = hashlib.sha256((root / name).read_bytes()).hexdigest()
digests["/"] = digests["/index.html"]
text = pathlib.Path(template).read_text(encoding="utf-8")
tokens = {
    "__BW_CACHE_VERSION__": version,
    "__BW_PRECACHE_URLS__": json.dumps(precache, separators=(",", ":")),
    "__BW_CACHE_FIRST_URLS__": json.dumps(cache_first, separators=(",", ":")),
    "__BW_CACHE_SHA256__": json.dumps(sorted(digests.items()), separators=(",", ":")),
}
for token, value in tokens.items():
    if text.count(token) != 1:
        raise SystemExit(f"service-worker token is absent/ambiguous: {token}")
    text = text.replace(token, value)
pathlib.Path(output).write_text(text, encoding="utf-8")
PY
if [ "${DO_BROTLI}" = "1" ]; then
  # These responses all start before the first semantic interaction. Keep their
  # exact transport bytes inside the same q11/lgwin=24 release contract as the
  # Emscripten payload instead of letting the 15 MB receipt omit shell overhead.
  for f in index.html diagnostics-bootstrap.js file-bridge.js boot-windowed.js \
           pthread-main-loader.js \
           stage1-loader.js service-worker-register.js service-worker.js \
           fonts/bw-interface-sans.woff2; do
    "${PINNED_NODE}" "${BROTLI_CODEC}" encode "${OUT}/${f}" "${OUT}/${f}.br"
  done
fi
rm -f "${split_rows}"; trap - EXIT
echo "make_staged_bundle: assembled exact split-aware tree at ${OUT} cache=${cache_version}"
