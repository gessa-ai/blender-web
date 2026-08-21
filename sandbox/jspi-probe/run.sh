#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M2.7 probe: -sJSPI x setjmp/longjmp interaction on emcc 6.0.5.
# Reproduces the results matrix in notes/python-emcc605-probe.md (§ M2.7 JSPI probe).
# Every emcc build goes through harness/buildwrap.sh; node runs print only verdict lines.
#
# Real JSPI needs the NEW WebAssembly.Suspending API (Node >=23 / Chrome >=137). The emsdk
# node (v22.x) has only the old Suspender API, so any -sJSPI module aborts at init there.
# This script auto-detects an explicit JSPI_NODE, a tools-local Node 24, or a capable node
# on PATH. If none is present, it fails before building: the accepted matrix depends on real
# JSPI, while the retained Asyncify runs are controls only.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd -- "$HERE/../.." && pwd -P)"
BW="$ROOT/harness/buildwrap.sh"
INC="$ROOT/lib/wasm/include"
LIBJPEG="$ROOT/lib/wasm/lib/libjpeg.a"
PYINC="$ROOT/lib/wasm/include/python3.13"
LP="$ROOT/build-python-probe/build-jseh"   # M2.0b CONFIG-A tree (has _decimal/_hacl sublibs)
# shellcheck disable=SC1091
EMSDK_QUIET=1 source "$ROOT/tools/emsdk/emsdk_env.sh"
cd "$HERE"

for required in "$BW" "$LIBJPEG" "$ROOT/lib/wasm/lib/libpython3.13.a" \
  "$ROOT/tools/emsdk/upstream/bin/wasm-dis"; do
  if [ ! -e "$required" ]; then
    echo "PROBE FAIL: missing required input: $required" >&2
    exit 2
  fi
done

# --- pick a JSPI-capable node -------------------------------------------------
JNODE=""
JFLAGS=()
node_candidates=()
if [ -n "${JSPI_NODE:-}" ]; then
  node_candidates+=("$JSPI_NODE")
else
  shopt -s nullglob
  node_candidates+=("$ROOT"/tools/node24/node-v*/bin/node)
  shopt -u nullglob
  if PATH_NODE="$(command -v node 2>/dev/null)"; then
    node_candidates+=("$PATH_NODE")
  fi
fi

for candidate in "${node_candidates[@]}"; do
  [ -x "$candidate" ] || continue
  if [ "$("$candidate" -e 'process.stdout.write(typeof WebAssembly.Suspending)' 2>/dev/null || true)" = "function" ]; then
    JNODE="$candidate"
    JFLAGS=()
    break
  fi
  if [ "$("$candidate" --experimental-wasm-jspi -e 'process.stdout.write(typeof WebAssembly.Suspending)' 2>/dev/null || true)" = "function" ]; then
    JNODE="$candidate"
    JFLAGS=(--experimental-wasm-jspi)
    break
  fi
done

if [ -n "$JNODE" ]; then
  REAL=1
  MODE="REAL JSPI ($("$JNODE" --version), $JNODE${JFLAGS[*]:+ ${JFLAGS[*]}})"
elif [ -n "${JSPI_NODE:-}" ]; then
  echo "PROBE FAIL: JSPI_NODE is not executable or lacks WebAssembly.Suspending: $JSPI_NODE" >&2
  exit 2
else
  echo "PROBE FAIL: no JSPI-capable node found; set JSPI_NODE to Node >=23" >&2
  exit 2
fi
echo "== JSPI runtime: $MODE =="

filt() { grep -iE "RESULT|Aborted|not supported|SuspendError|Suspend|Traceback|Error:|Trap|unreachable" | sed -n '1,4p'; }
run_checked() {
  local expected_status="$1"
  shift
  local -a expected_patterns=()
  while [ "$1" != "--" ]; do
    expected_patterns+=("$1")
    shift
  done
  shift

  local output rc pattern
  set +e
  output=$("$@" 2>&1)
  rc=$?
  set -e

  if { [ "$expected_status" = "zero" ] && [ "$rc" -ne 0 ]; } || \
    { [ "$expected_status" = "nonzero" ] && [ "$rc" -eq 0 ]; }; then
    echo "PROBE ERROR: unexpected runtime status $rc for: $*" >&2
    printf '%s\n' "$output" | filt || true
    return 1
  fi
  for pattern in "${expected_patterns[@]}"; do
    if ! grep -Eq -- "$pattern" <<<"$output"; then
      echo "PROBE ERROR: missing runtime pattern '$pattern' for: $*" >&2
      printf '%s\n' "$output" | filt || true
      return 1
    fi
  done
  printf '%s\n' "$output" | filt
}

echo "--- A: setjmp/longjmp, NO suspension | JS-EH + JSPI ---"
$BW emcc a.c -fexceptions -sJSPI -o a_jspi.js >/dev/null && echo "  link: OK"
echo -n "  run(jspi): "; run_checked zero 'RESULT A: PASS.*step=1' -- "$JNODE" "${JFLAGS[@]}" a_jspi.js
$BW emcc a.c -fexceptions -o a.js >/dev/null; echo -n "  run(baseline): "; run_checked zero 'RESULT A: PASS.*step=1' -- "$EMSDK_NODE" a.js

echo "--- B: setjmp x REAL suspension (B1 longjmp-after-resume, B2 suspend-normal-return), JS-EH ---"
$BW emcc b.c -fexceptions -sJSPI -o b_jspi.js >/dev/null && echo "  link(JSPI): OK"
echo "  run(jspi):"; run_checked nonzero 'SuspendError: trying to suspend JS frames' -- "$JNODE" "${JFLAGS[@]}" b_jspi.js
$BW emcc b.c -fexceptions -sASYNCIFY -o b_async.js >/dev/null
echo "  (Asyncify proxy, for comparison — NOTE: proxy is a FALSE POSITIVE here vs real JSPI):"; run_checked zero 'RESULT B1: PASS.*n=42' 'RESULT B2: PASS.*captured=100' -- "$EMSDK_NODE" b_async.js

echo "--- C: libjpeg-turbo setjmp error path ---"
$BW emcc c_jpeg.c -I "$INC" "$LIBJPEG" -fexceptions -o c.js >/dev/null; echo -n "  run(baseline): "; run_checked zero 'RESULT C: PASS' -- "$EMSDK_NODE" c.js
$BW emcc c_jpeg.c -I "$INC" "$LIBJPEG" -fexceptions -sJSPI -o c_jspi.js >/dev/null && echo "  link(JSPI): OK (error path is inside a setjmp region -> not suspend-safe under real JSPI)"

echo "--- D: libpython embed (Py_Initialize + raise/except + import json) ---"
if [ -f "$LP/libpython3.13.a" ]; then
  DLIBS=(-Wl,--start-group "$LP/libpython3.13.a" "$LP/Modules/_decimal/libmpdec/libmpdec.a" "$LP/Modules/_hacl/libHacl_Hash_SHA2.a" "$LP/Modules/expat/libexpat.a" -Wl,--end-group -sUSE_ZLIB -sUSE_BZIP2 -sUSE_SQLITE3 -lm)
  DFLAGS=(-I "$PYINC" -fexceptions -sALLOW_MEMORY_GROWTH -sWASM_BIGINT -sFORCE_FILESYSTEM --preload-file "$LP/usr/local@/usr/local")
else
  DLIBS=(-Wl,--start-group "$ROOT/lib/wasm/lib/libpython3.13.a" "$ROOT/lib/wasm/lib/libexpat.a" -Wl,--end-group -sUSE_ZLIB -sUSE_BZIP2 -sUSE_SQLITE3 -lm)
  DFLAGS=(-I "$PYINC" -fexceptions -sALLOW_MEMORY_GROWTH -sWASM_BIGINT -sFORCE_FILESYSTEM --preload-file "$ROOT/lib/wasm/lib/python3.13@/usr/local/lib/python3.13")
fi
$BW emcc d_embed.c "${DFLAGS[@]}" "${DLIBS[@]}" -o d.js >/dev/null; echo -n "  run(baseline): "; run_checked zero 'RESULT D: PASS.*1024' -- "$EMSDK_NODE" d.js
$BW emcc d_embed.c "${DFLAGS[@]}" "${DLIBS[@]}" -sJSPI -o d_jspi.js >/dev/null && echo "  link(JSPI): OK"
echo -n "  run(jspi, no suspension): "; run_checked zero 'RESULT D: PASS.*1024' -- "$JNODE" "${JFLAGS[@]}" d_jspi.js

echo "--- E: B-shape under Wasm-EH (-fwasm-exceptions -sSUPPORT_LONGJMP=wasm) — Wasm-EH data point ---"
$BW emcc b.c -fwasm-exceptions -sSUPPORT_LONGJMP=wasm -sJSPI -o e_jspi.js >/dev/null && echo "  link(Wasm-EH+wasm-longjmp+JSPI): OK (emcc does NOT refuse the combo)"
echo "  run(jspi, REAL suspend across setjmp):"; run_checked zero 'RESULT B1: PASS.*n=42' 'RESULT B2: PASS.*captured=100' -- "$JNODE" "${JFLAGS[@]}" e_jspi.js
$BW emcc b.c -fwasm-exceptions -sSUPPORT_LONGJMP=wasm -sASYNCIFY -o e_async.js >/dev/null
echo "  (Asyncify proxy, for comparison):"; run_checked zero 'RESULT B1: PASS.*n=42' 'RESULT B2: PASS.*captured=100' -- "$EMSDK_NODE" e_async.js

# ---- M2.7c: does C++ try/catch break suspension like setjmp? -----------------
echo "== M2.7c: C++ try/catch × real JSPI (F1 active-try-inside, F2 try-present-not-active, F3 active-try-6-frames-up) =="
WASMDIS="$(ls "$ROOT"/tools/emsdk/upstream/bin/wasm-dis 2>/dev/null)"
for c in 1 2 3; do
  $BW em++ f_try.cpp -DCASE=$c -fexceptions -sJSPI -o fjs_$c.js >/dev/null 2>&1
  $BW em++ f_try.cpp -DCASE=$c -fwasm-exceptions -sSUPPORT_LONGJMP=wasm -sJSPI -o fwe_$c.js >/dev/null 2>&1
  echo -n "  F$c JS-EH  : "
  if [ "$c" -eq 2 ]; then
    run_checked zero "RESULT F$c: reached r=42" -- "$JNODE" "${JFLAGS[@]}" "fjs_$c.js"
  else
    run_checked nonzero 'SuspendError: trying to suspend JS frames' -- "$JNODE" "${JFLAGS[@]}" "fjs_$c.js"
  fi
  echo -n "  F$c Wasm-EH: "; run_checked zero "RESULT F$c: reached r=42" -- "$JNODE" "${JFLAGS[@]}" "fwe_$c.js"
done
echo "  F5 mechanism — invoke_* (JS-frame) imports per build:"
for c in 1 2 3; do
  j=$("$WASMDIS" fjs_$c.wasm 2>/dev/null | awk '/\(import "env" "invoke_/{n++} END{print n+0}')
  w=$("$WASMDIS" fwe_$c.wasm 2>/dev/null | awk '/\(import "env" "invoke_/{n++} END{print n+0}')
  expected_j=(0 7 7 8)
  if [ "$j" -ne "${expected_j[$c]}" ] || [ "$w" -ne 0 ]; then
    echo "PROBE ERROR: F$c invoke_* count changed: JS-EH=$j Wasm-EH=$w" >&2
    exit 1
  fi
  echo "    F$c: JS-EH invoke_*=$j  Wasm-EH invoke_*=$w"
done

# ---- census: setjmp/longjmp machinery in our JS-EH deps -----------------------
echo "== census: setjmp/longjmp (emscripten_longjmp/saveSetjmp) refs in built libs =="
for a in "$ROOT/lib/wasm/lib/libpython3.13.a" "$ROOT/lib/wasm/lib/libjpeg.a"; do
  if [ -f "$a" ]; then
    count=$(emnm "$a" 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /setjmp|longjmp/{n++} END{print n+0}')
    if [ "$count" -ne 0 ]; then
      echo "PROBE ERROR: unexpected SjLj archive symbols in $a: $count" >&2
      exit 1
    fi
    echo "  $(basename "$a"): $count archive-symbol refs"
  fi
done
if [ -f d.wasm ]; then
  count=$("$WASMDIS" d.wasm 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /saveSetjmp|testSetjmp|emscripten_longjmp|__wasm_setjmp|__wasm_longjmp/{n++} END{print n+0}')
  if [ "$count" -ne 0 ]; then
    echo "PROBE ERROR: linked libpython image contains $count SjLj runtime refs" >&2
    exit 1
  fi
  echo "  d.wasm (linked harvested libpython image): $count SjLj-runtime refs"
fi

echo "== done (REAL=$REAL) =="
