<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M2.7 probe — `-sJSPI` × setjmp/longjmp on emcc 6.0.5

GOAL mandates `-sJSPI` for the final Blender link (Chrome 137 floor; avoids Asyncify's
~50% size tax). Our stack is JS-EH (`-fexceptions`, `SUPPORT_LONGJMP=emscripten` — longjmp
is implemented as a JS exception). JSPI suspends/resumes wasm frames across JS boundaries.
This probe characterizes whether setjmp/longjmp survives a suspension, and whether libjpeg's
setjmp error path and libpython init/run tolerate a JSPI-enabled link.

Run: `bash run.sh` (every emcc build goes through `harness/buildwrap.sh`). Full results
matrix + analysis live in `notes/python-emcc605-probe.md` § "M2.7 JSPI probe".

## The node blocker (read first)

`-sJSPI` is `ASYNCIFY=2` internally. emcc 6.0.5's runtime glue instantiates suspending
imports via **`new WebAssembly.Suspending(...)`** (emscripten `src/preamble.js:534`) — the
*new* JSPI JS API (Chrome 129+/V8 12.9+/Node ≥23). Every node on this box (emsdk-bundled
v22.16.0, system v22.15/22.23) exposes only the **old** `WebAssembly.Suspender` API, so
**any `-sJSPI` module aborts at instantiation** — before `main` — with
`Aborted(... JSPI not supported by current environment ...)`, with or without
`--experimental-wasm-jspi`. JSPI *runtime* therefore can only be exercised in a browser
(Chrome ≥137, GOAL's floor) or Node ≥23. That is the blocker, not a bug in our code.

Consequence: cases that *suspend* under real JSPI cannot be run here. We (a) prove every
combo **links**, and (b) run the suspend×setjmp shape under **`-sASYNCIFY` (=1)** as a
runnable proxy — same "suspend a C frame that holds a live `jmp_buf`, then resume" hazard;
JSPI (native stack switching) preserves the linear-memory C stack even more transparently
than Asyncify's instrument-and-rewind, so an Asyncify PASS is a conservative predictor for
JSPI. The definitive JSPI-native suspend test is a follow-up browser (Playwright) harness.

## Cases

| file | case | what it tests |
|---|---|---|
| `a.c` | A | setjmp/longjmp, no suspension — baseline that enabling `-sJSPI` at link doesn't break JS-EH longjmp |
| `b.c` | B | B1 = setjmp → suspend → longjmp back after resume (the dangerous shape); B2 = suspend inside the setjmp region, normal return |
| `c_jpeg.c` | C | libjpeg-turbo's classic `error_exit`→`longjmp` path on a corrupt stream (one of our 29 deps) |
| `d_embed.c` | D | `Py_Initialize` + `PyRun_SimpleString` (raise/except + `import json`) against `libpython3.13.a` — static init + call-trampoline under a JSPI link |
| `b.c` (Wasm-EH flags) | E | B-shape rebuilt `-fwasm-exceptions -sSUPPORT_LONGJMP=wasm` — data point for the deferred Wasm-EH-migration ADR |
| `f_try.cpp` (`-DCASE=1\|2\|3`) | F1/F2/F3 | M2.7c: does C++ try/catch break real JSPI suspension like setjmp? F1 suspend inside an active try; F2 try present but not active at the suspend; F3 active try several plain frames above the suspend. Built JS-EH and Wasm-EH; run.sh also reports invoke_* counts (F5) and a setjmp census. Feeds ADR-003. |

Case D links against the M2.0b CONFIG-A tree (`build-python-probe/build-jseh/`, which carries
CPython-internal `libmpdec`/`libHacl` sublibs not harvested to `lib/wasm`); `run.sh` skips D
with a note if that tree is absent (rebuild it via `scripts/deps/python.sh`).

Build artifacts (`*.js *.wasm *.data`) are git-ignored; only sources, `run.sh`, this README,
and `.gitignore` are committed.
