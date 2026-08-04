#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M2.7 probe: -sJSPI x setjmp/longjmp interaction on emcc 6.0.5.
# Reproduces the results matrix in notes/python-emcc605-probe.md (§ M2.7 JSPI probe).
# Every emcc build goes through harness/buildwrap.sh; node runs print only RESULT/verdict
# lines. See README.md for what each case tests and the node/browser caveat.
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
NODE="$EMSDK_NODE"; JFLAG="--experimental-wasm-jspi"

run() { "$NODE" "$@" 2>&1 | grep -iE "RESULT|Aborted|not supported|Traceback|Error:" | head -4; }

echo "== node: $($NODE --version) | new-JSPI-API(WebAssembly.Suspending): $($NODE $JFLAG -e 'console.log(typeof WebAssembly.Suspending)') =="

echo "--- A: setjmp/longjmp, no suspension | JS-EH + JSPI ---"
$BW emcc a.c -fexceptions -sJSPI -o a_jspi.js >/dev/null && echo "  link: OK"
echo -n "  run(jspi): "; run $JFLAG a_jspi.js
$BW emcc a.c -fexceptions -o a.js >/dev/null; echo -n "  run(baseline): "; run a.js

echo "--- B: setjmp x suspension (B1 longjmp-after-resume, B2 suspend-normal-return) ---"
$BW emcc b.c -fexceptions -sASYNCIFY -o b_async.js >/dev/null; echo "  proxy=Asyncify(JS-EH):"; run b_async.js
$BW emcc b.c -fexceptions -sJSPI -o b_jspi.js >/dev/null && echo "  link(JSPI): OK"
echo -n "  run(jspi): "; run $JFLAG b_jspi.js

echo "--- C: libjpeg-turbo setjmp error path ---"
$BW emcc c_jpeg.c -I "$INC" "$LIBJPEG" -fexceptions -o c.js >/dev/null; echo -n "  run(baseline): "; run c.js
$BW emcc c_jpeg.c -I "$INC" "$LIBJPEG" -fexceptions -sJSPI -o c_jspi.js >/dev/null && echo "  link(JSPI): OK (runtime browser-gated)"

echo "--- D: libpython embed (Py_Initialize + raise/except + import json) ---"
if [ -f "$LP/libpython3.13.a" ]; then
  DLIBS=(-Wl,--start-group "$LP/libpython3.13.a" "$LP/Modules/_decimal/libmpdec/libmpdec.a" "$LP/Modules/_hacl/libHacl_Hash_SHA2.a" "$LP/Modules/expat/libexpat.a" -Wl,--end-group -sUSE_ZLIB -sUSE_BZIP2 -sUSE_SQLITE3 -lm)
  DFLAGS=(-I "$PYINC" -fexceptions -sALLOW_MEMORY_GROWTH -sWASM_BIGINT -sFORCE_FILESYSTEM --preload-file "$LP/usr/local@/usr/local")
  $BW emcc d_embed.c "${DFLAGS[@]}" "${DLIBS[@]}" -o d.js >/dev/null; echo -n "  run(baseline): "; run d.js
  $BW emcc d_embed.c "${DFLAGS[@]}" "${DLIBS[@]}" -sJSPI -o d_jspi.js >/dev/null && echo "  link(JSPI): OK (runtime browser-gated)"
else
  echo "  SKIP: needs the M2.0b CONFIG-A build tree at $LP (rebuild via scripts/deps/python.sh, which uses build-deps/python)."
fi

echo "--- E: B-shape under Wasm-EH (-fwasm-exceptions -sSUPPORT_LONGJMP=wasm) — Wasm-EH-migration data point ---"
$BW emcc b.c -fwasm-exceptions -sSUPPORT_LONGJMP=wasm -sASYNCIFY -o e_async.js >/dev/null; echo "  proxy=Asyncify(Wasm-EH):"; run e_async.js
$BW emcc b.c -fwasm-exceptions -sSUPPORT_LONGJMP=wasm -sJSPI -o e_jspi.js >/dev/null && echo "  link(Wasm-EH+wasm-longjmp+JSPI): OK (emcc does NOT refuse the combo)"

echo "== done =="
