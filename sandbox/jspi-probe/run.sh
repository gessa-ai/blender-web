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
# This script auto-detects a tools-local Node 24 (tools/node24/, gitignored); if present it
# runs REAL JSPI, else it falls back to the Asyncify(=1) proxy for the suspend cases.
set -uo pipefail

ROOT="/Users/paws/blender-web"
HERE="$ROOT/sandbox/jspi-probe"
BW="$ROOT/harness/buildwrap.sh"
INC="$ROOT/lib/wasm/include"
LIBJPEG="$ROOT/lib/wasm/lib/libjpeg.a"
PYINC="$ROOT/lib/wasm/include/python3.13"
LP="$ROOT/build-python-probe/build-jseh"   # M2.0b CONFIG-A tree (has _decimal/_hacl sublibs)
# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"
cd "$HERE"
JFLAG="--experimental-wasm-jspi"

# --- pick a JSPI-capable node -------------------------------------------------
NODE24="$(ls "$ROOT"/tools/node24/node-v*/bin/node 2>/dev/null | head -1)"
if [ -n "$NODE24" ] && [ "$("$NODE24" $JFLAG -e 'process.stdout.write(typeof WebAssembly.Suspending)' 2>/dev/null)" = "function" ]; then
  JNODE="$NODE24"; REAL=1; MODE="REAL JSPI ($("$NODE24" --version))"
else
  JNODE="$EMSDK_NODE"; REAL=0; MODE="NO real-JSPI node (emsdk $($EMSDK_NODE --version) has old API) -> -sJSPI aborts at init; suspend cases use Asyncify proxy"
fi
echo "== JSPI runtime: $MODE =="

filt() { grep -iE "RESULT|Aborted|not supported|SuspendError|Suspend|Traceback|Error:|Trap|unreachable" | head -4; }
runj()  { "$JNODE" $JFLAG "$@" 2>&1 | filt; }         # run a -sJSPI module
run()   { "$EMSDK_NODE" "$@" 2>&1 | filt; }           # run a non-JSPI module (any node)

echo "--- A: setjmp/longjmp, NO suspension | JS-EH + JSPI ---"
$BW emcc a.c -fexceptions -sJSPI -o a_jspi.js >/dev/null && echo "  link: OK"
echo -n "  run(jspi): "; runj a_jspi.js
$BW emcc a.c -fexceptions -o a.js >/dev/null; echo -n "  run(baseline): "; run a.js

echo "--- B: setjmp x REAL suspension (B1 longjmp-after-resume, B2 suspend-normal-return), JS-EH ---"
$BW emcc b.c -fexceptions -sJSPI -o b_jspi.js >/dev/null && echo "  link(JSPI): OK"
echo "  run(jspi):"; runj b_jspi.js
$BW emcc b.c -fexceptions -sASYNCIFY -o b_async.js >/dev/null
echo "  (Asyncify proxy, for comparison — NOTE: proxy is a FALSE POSITIVE here vs real JSPI):"; run b_async.js

echo "--- C: libjpeg-turbo setjmp error path ---"
$BW emcc c_jpeg.c -I "$INC" "$LIBJPEG" -fexceptions -o c.js >/dev/null; echo -n "  run(baseline): "; run c.js
$BW emcc c_jpeg.c -I "$INC" "$LIBJPEG" -fexceptions -sJSPI -o c_jspi.js >/dev/null && echo "  link(JSPI): OK (error path is inside a setjmp region -> not suspend-safe under real JSPI)"

echo "--- D: libpython embed (Py_Initialize + raise/except + import json) ---"
if [ -f "$LP/libpython3.13.a" ]; then
  DLIBS=(-Wl,--start-group "$LP/libpython3.13.a" "$LP/Modules/_decimal/libmpdec/libmpdec.a" "$LP/Modules/_hacl/libHacl_Hash_SHA2.a" "$LP/Modules/expat/libexpat.a" -Wl,--end-group -sUSE_ZLIB -sUSE_BZIP2 -sUSE_SQLITE3 -lm)
  DFLAGS=(-I "$PYINC" -fexceptions -sALLOW_MEMORY_GROWTH -sWASM_BIGINT -sFORCE_FILESYSTEM --preload-file "$LP/usr/local@/usr/local")
  $BW emcc d_embed.c "${DFLAGS[@]}" "${DLIBS[@]}" -o d.js >/dev/null; echo -n "  run(baseline): "; run d.js
  $BW emcc d_embed.c "${DFLAGS[@]}" "${DLIBS[@]}" -sJSPI -o d_jspi.js >/dev/null && echo "  link(JSPI): OK"
  echo -n "  run(jspi, no suspension): "; runj d_jspi.js
else
  echo "  SKIP: needs the M2.0b CONFIG-A build tree at $LP (rebuild via scripts/deps/python.sh)."
fi

echo "--- E: B-shape under Wasm-EH (-fwasm-exceptions -sSUPPORT_LONGJMP=wasm) — Wasm-EH data point ---"
$BW emcc b.c -fwasm-exceptions -sSUPPORT_LONGJMP=wasm -sJSPI -o e_jspi.js >/dev/null && echo "  link(Wasm-EH+wasm-longjmp+JSPI): OK (emcc does NOT refuse the combo)"
echo "  run(jspi, REAL suspend across setjmp):"; runj e_jspi.js
$BW emcc b.c -fwasm-exceptions -sSUPPORT_LONGJMP=wasm -sASYNCIFY -o e_async.js >/dev/null
echo "  (Asyncify proxy, for comparison):"; run e_async.js

echo "== done (REAL=$REAL) =="
