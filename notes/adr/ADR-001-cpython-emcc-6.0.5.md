<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# ADR-001: M2.0 gate — CPython 3.13 builds on emcc 6.0.5 (no toolchain downgrade)

Date: 2026-08-03. Status: ACCEPTED (driver), with one deliberately-deferred sub-decision
(exception model, see below). Evidence: 3-agent research wave (vanilla CPython wasm state,
Pyodide patch triage, emsdk 4.0.9→6.0.5 delta); full transcripts in the session workflow
journal; key sources cited inline.

## Decision

**The project stays on emsdk/emcc 6.0.5 for everything, including CPython 3.13.13.**
M2 builds libpython by forward-porting a *minimal* patch subset onto vanilla 3.13.13 —
NOT by pinning the toolchain back to Pyodide-validated emcc 4.0.9, and NOT by carrying
Pyodide's full patch stack.

## Why the 4.0.9 downgrade is rejected (it was never the cheap option)

- It reverts LLVM 22→20 — a wasm object-ABI break — **invalidating all 29 harvested deps
  in `lib/wasm`** (full rebuild), plus musl 1.2.6→1.2.5 and older mimalloc.
- It drops below the repo's recorded ≥4.0.10 floor, which exists because **emdawnwebgpu
  became the sanctioned WebGPU path at 4.0.10** — i.e. the downgrade would trade M2
  convenience for the M3/M4 GPU-backend path, the project's #1 risk area.
- It trips the harness toolchain-drift gate.
- The only thing it buys is verbatim reuse of Pyodide's patch stack — which the triage
  below shows we mostly don't need.

## Why the forward-port is smaller than the fix_plan feared

Of Pyodide's 10 CPython-3.13 patches, only a toolchain subset matters to a non-Pyodide
*embedding* (Blender owns main() and calls Py_Initialize; the JS-FFI layer is dead weight):

- **Needed:** `0003 LONG_BIT` (libc-header workaround, emscripten ≥3.1.50) + the
  **call-trampoline machinery** — and crucially, the trampoline fix that matters at
  emcc ≥4.0.19 lives in **Pyodide MAIN (against CPython 3.14)** and must be back-ported to
  3.13.13; the 3.13-tree stack (pinned to 4.0.9) does NOT contain it, and its 0008 is a
  4.0.3/4.0.4-only stopgap to drop.
- **Not needed:** JsProxy/jsproxy/jsnull FFI patches, tzdata warning, pymain_run_python
  (we embed, not pymain), iPad wasm-gc detection. `0002 ctypes.find_library` only if bpy
  startup touches ctypes (check empirically).
- Vanilla 3.13 ships the build machinery (`Tools/wasm`, `--with-emscripten-target`,
  `--with-build-python`, CONFIG_SITE) even though the platform lost PEP-11 status at 3.13
  (restored in 3.14/PEP 776). Floor is emcc 3.1.19; no upper bound documented.

**Nobody has published CPython 3.13 on emcc 6.x** — this is unprecedented and must be
build-tested, not assumed. Method: build vanilla 3.13.13 on 6.0.5 FIRST, see what actually
breaks, add patches only as the compiler/linker demands (each as SPDX'd patch in `patches/`).

## Deferred sub-decision: exception model (JS-EH vs Wasm-EH) — settle by experiment

The load-bearing fork is orthogonal to the emcc version: our platform + all 29 deps are
built with JS-based `-fexceptions` (⇒ `SUPPORT_LONGJMP=emscripten`); Pyodide's validated
CPython uses `-fwasm-exceptions` + `-sSUPPORT_LONGJMP=wasm` (as does fix_plan M2.2's
draft flags); **Emscripten forbids mixing the two in one link.** Either:
(i) build libpython with JS-EH, diverging from Pyodide's tested config (patch risk), or
(ii) move the whole stack (Blender + 29 deps + libpython) to Wasm-EH (rebuild everything,
but on modern browsers Wasm-EH is the forward-looking model and Chrome-floor ≥137 for JSPI
already implies it's available).
**Experiment M2.0b decides it:** probe-build vanilla libpython3.13.a on 6.0.5 in BOTH EH
configs (as far as each gets), record failures, then pick uniformly. Also validates the
`-sJSPI` × `setjmp/longjmp` interaction flagged in M2.7 before it's load-bearing.

## Consequences

- M2.1/M2.2 reword: start from vanilla 3.13.13 + {LONG_BIT, trampoline-from-main} only.
- M1's WITH_PYTHON=OFF posture is unaffected (D-4 stands).
- For M2, Python runs synchronously on the (proxied) main thread: vanilla 3.13 libpython
  is single-threaded-by-default and JSPI-unaware; `--enable-wasm-pthreads` is opt-in and
  documented fragile (aligns with M2.7's GIL-gating plan).
- Static linking only (`--disable-shared`, libpython3.13.a into the mono-wasm module) —
  matches both PEP 776's supported posture and D-1/GOAL's no-dynamic-linking stance.
