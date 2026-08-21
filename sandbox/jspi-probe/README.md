<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M2.7 probe — `-sJSPI` × setjmp/longjmp on emcc 6.0.5

This probe was created while the standing architecture used `-sJSPI`. The shipped windowed
profile now deliberately omits JSPI under ADR-006, but the measured JS-EH/Wasm-EH boundary is
retained as a regression contract for any future reintroduction. Our stack is JS-EH
(`-fexceptions`, `SUPPORT_LONGJMP=emscripten` — longjmp is implemented as a JS exception).
The probe characterizes whether setjmp/longjmp survives a real suspension, and whether
libjpeg's setjmp error path and libpython init/run tolerate a JSPI-enabled link.

Run from any working directory: `bash /path/to/blender-web/sandbox/jspi-probe/run.sh` (every
emcc build goes through `harness/buildwrap.sh`). Full results matrix + analysis live in
`notes/python-emcc605-probe.md` § "M2.7 JSPI probe".

## JSPI runtime requirement

`-sJSPI` is `ASYNCIFY=2` internally. emcc 6.0.5's runtime glue instantiates suspending
imports via **`new WebAssembly.Suspending(...)`** (emscripten `src/preamble.js:534`) — the
*new* JSPI JS API (Chrome 129+/V8 12.9+/Node ≥23). The bundled Node 22.16.0 cannot run the
real matrix. `run.sh` selects, in order, an explicit `JSPI_NODE`, the historical ignored
`tools/node24/` installation, or a capable `node` on `PATH`; Node 24 may use
`--experimental-wasm-jspi`, while newer runtimes can expose the API unflagged. An explicit
unsupported runtime is rejected before any build. The Asyncify variants remain comparison
controls because they previously false-positived the JS-EH setjmp shape; they never substitute
for a real-JSPI run.

The runner fails closed on every expected exit status and verdict, the exact JS-EH
`invoke_*` counts (7/7/8 versus Wasm-EH 0/0/0), and the zero-SjLj archive/linked-image census.

## Cases

| file | case | what it tests |
|---|---|---|
| `a.c` | A | setjmp/longjmp, no suspension — baseline that enabling `-sJSPI` at link doesn't break JS-EH longjmp |
| `b.c` | B | B1 = setjmp → suspend → longjmp back after resume (the dangerous shape); B2 = suspend inside the setjmp region, normal return |
| `c_jpeg.c` | C | libjpeg-turbo's classic `error_exit`→`longjmp` path on a corrupt stream (one of our 29 deps) |
| `d_embed.c` | D | `Py_Initialize` + `PyRun_SimpleString` (raise/except + `import json`) against `libpython3.13.a` — static init + call-trampoline under a JSPI link |
| `b.c` (Wasm-EH flags) | E | B-shape rebuilt `-fwasm-exceptions -sSUPPORT_LONGJMP=wasm` — data point for the deferred Wasm-EH-migration ADR |
| `f_try.cpp` (`-DCASE=1\|2\|3`) | F1/F2/F3 | M2.7c: does C++ try/catch break real JSPI suspension like setjmp? F1 suspend inside an active try; F2 try present but not active at the suspend; F3 active try several plain frames above the suspend. Built JS-EH and Wasm-EH; run.sh also reports invoke_* counts (F5) and a setjmp census. Feeds ADR-003. |

Case D prefers the retained M2.0b CONFIG-A tree (`build-python-probe/build-jseh/`) when it is
present. On a migrated/cold checkout it instead links the harvested `libpython3.13.a` and
`libexpat.a`, preloading the harvested Python 3.13 standard library; the case is never silently
skipped.

Build artifacts (`*.js *.wasm *.data`) are git-ignored; only sources, `run.sh`, this README,
and `.gitignore` are committed.
