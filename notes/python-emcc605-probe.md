<!--
SPDX-FileCopyrightText: 2026 KA
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M2.0b — CPython 3.13.13 probe on emcc 6.0.5, both EH models

Experiment (characterization), not a delivery. Date 2026-08-03. Toolchain: emcc **6.0.5**
(1db513782be24469589d7cb8a1f1834e9a33f271), node v22.23.1, host macOS aarch64
(darwin25.0.0). Build area: `build-python-probe/` (gitignored). All builds via
`harness/buildwrap.sh`; log ids cited inline. **Headline: BOTH EH configs build vanilla
3.13.13 to a runnable interpreter with ZERO source patches.**

## Tarball + provenance
- `Python-3.13.13.tar.xz`, python.org. MD5 `3a19dd420883dd599728c9dd07c141e7` — **matches**
  `versions.cmake:385` (PYTHON_HASH, MD5). (versions.cmake also gives the download URI;
  hash form is MD5, verified exactly.)

## Build-python (cross-compile bootstrap) situation
- Host has **python3.13.13** (`/opt/homebrew/bin/python3.13`) and python3.12.9. So a host
  3.13 exists.
- Nonetheless built the documented native bootstrap from the SAME tree (config-independent
  host tool, shared by both configs): `build-native/` — `../configure -C` (57s) + `make -j14`
  (35s) → `build-native/python.exe` (5.5 MB), `--version` = 3.13.13.
  - **macOS case-insensitivity note:** the native binary is `python.exe`, not `python`
    (collides with the `Python/` object dir on APFS). Pass
    `--with-build-python=.../build-native/python.exe`. This bit once (`ls python` showed the
    dir); not a blocker.
- Build triple (`config.guess`): `aarch64-apple-darwin25.0.0`.

## Configure invocation (both configs, browser static target)
`CONFIG_SITE=Tools/wasm/config.site-wasm32-emscripten emconfigure ../configure -C
--host=wasm32-unknown-emscripten --build=aarch64-apple-darwin25.0.0
--with-emscripten-target=browser --with-build-python=.../python.exe --disable-shared
--disable-ipv6`, differing only in CFLAGS/LDFLAGS below. Followed the in-tree
`Tools/wasm/README.md` documented emconfigure flow (manual, for flag control).

## THE MATRIX

| stage | CONFIG A — JS-EH (`-fexceptions`) | CONFIG B — Wasm-EH (`-fwasm-exceptions -sSUPPORT_LONGJMP=wasm`) |
|---|---|---|
| configure | **OK** (114s, log 20260803T204012) | **OK** (218s, log 20260803T204433) |
| compile | **100%** (187 TU) | **100%** (187 TU) |
| link (`python.js`) | **OK** (17s total make, log 204217) | **OK** (28s total make, log 204819) |
| artifact `libpython3.13.a` | **42,248,200 B**, 234 objs, 2850 `T` syms | **42,253,360 B**, 234 objs, 2850 `T` syms |
| `python.wasm` | 7,365,292 B | 7,366,754 B |
| `python.js` | 136,506 B | 136,183 B |
| runtime (node) | **OK** | **OK** |
| patches needed | **NONE** | **NONE** |

Symbol sanity (both): `Py_Initialize`, `_PyEval_EvalFrameDefault`, `PyList_New` all defined
`T`. Flags verified in-log: A = `-fexceptions` only, SUPPORT_LONGJMP defaulted to
`emscripten`; B = `-fwasm-exceptions` + `-sSUPPORT_LONGJMP=wasm` on all 254 compile+link
invocations. **No EH/SjLj mixing warnings in either build.**

### Runtime validation (both identical, correct)
`node python.js -c` (run from the build dir so `python.data` resolves):
- basic: `import sys; print(sys.platform, sys.version)` → `emscripten 3.13.13`; `2**64` exact.
- richer (exercises the concerns ADR-001 flagged): `sorted(..., key=lambda)` (call
  **trampoline** through a Python callback), `raise/except ValueError` (**EH unwind**),
  `json.dumps`, `re.sub`, `functools.reduce` (C-ext modules) — **identical correct output on
  both builds**.

## ADR-001 prediction matches / surprises
- **SURPRISE (the big one):** ADR-001 predicted a minimal-but-real forward-port —
  `0003 LONG_BIT` + a back-ported call-trampoline fix (the emcc≥4.0.19 fix living in Pyodide
  MAIN, not in the 3.13 patch tree). **Neither was needed on 6.0.5.** Vanilla 3.13.13 ships
  `Python/emscripten_trampoline.c` + `emscripten_signal.c` in-tree; both compiled and the
  trampoline works at runtime (the key-callback test proves the call path). LONG_BIT: no
  header error surfaced. Nobody had published 3.13 on emcc 6.x — now build-tested: it just
  works for the browser-static target.
- **Match:** static-only (`--disable-shared`) is the right posture; the browser target
  preloads a reduced, thread-less stdlib (`python313.zip`, 3.31 MiB) — aligns with D-1 /
  single-thread-for-M2.
- **Not exercised (honest gaps):**
  - `-sJSPI × setjmp/longjmp` interaction (ADR/M2.7) — **NOT tested**; no `-sJSPI` in this
    probe (that flag is for the eventual full Blender link, not for `libpython.a`). Door
    still open; validate when the Blender link is assembled.
  - Optional modules **missing** (need deps we haven't harvested): `_ctypes` (libffi),
    `_hashlib`/`_ssl` (OpenSSL), `_lzma` (xz), `_uuid`. ADR flagged `0002 ctypes.find_library`
    as "only if bpy startup touches ctypes" — `_ctypes` is absent here, so if bpy startup
    needs ctypes, libffi must be harvested first. Out of scope for this probe.

## EH recommendation (with evidence)
**Build libpython with JS-EH (`-fexceptions`) for M2.** Reasoning:
- The probe **removes libpython as the deciding constraint**: both EH models build clean,
  run clean, zero patches, and are **size-indistinguishable** in isolation (Δ`.a` ≈ 5 KB,
  Δ`.wasm` ≈ 1.5 KB, Δ`.js` ≈ 0.3 KB). The theoretical JS-EH size/perf tax does **not**
  show up at libpython scale here.
- So the choice reverts to the rest of the stack. The **29 harvested deps + platform are
  already JS-EH** (`-fexceptions`, `SUPPORT_LONGJMP=emscripten`). JS-EH lets libpython join
  the existing stack with **zero dep rebuild** and no divergence from `lib/wasm`. Wasm-EH
  would match Pyodide's validated config and is the forward-looking model, but only at the
  cost of **rebuilding all 29 deps + platform** — a large cross-cutting cost for negligible
  libpython-level benefit as measured.
- **Fallback stays open:** CONFIG B proves libpython fully supports Wasm-EH too, so if a
  later stack-wide decision (JSPI ergonomics, or a dep that needs Wasm-EH) favors migrating
  everything, libpython is not the blocker. Recommend that migration be its own ADR driven by
  JSPI/size data, not forced now.

## Reproduce
Dirs under `build-python-probe/`: `build-native/` (host bootstrap), `build-jseh/` (A),
`build-wasmeh/` (B). Each cross dir has `libpython3.13.a`, `python.js`, `python.wasm`,
`python.data`. Smoke: `cd build-jseh && node python.js -c "print(2**64)"`.

---

# M2.7 JSPI probe — `-sJSPI` × setjmp/longjmp

Experiment, sandbox-scale (2026-08-03). Sources + reproducer: `sandbox/jspi-probe/`
(`run.sh`, committed). emcc 6.0.5; every build via buildwrap. `-sJSPI` is `ASYNCIFY=2`
internally.

## Node blocker (the pivotal finding)
emcc 6.0.5's JSPI glue instantiates suspending imports via `new WebAssembly.Suspending(...)`
(emscripten `src/preamble.js:534`) — the **new** JSPI API (Chrome 129+/V8 12.9+/Node ≥23).
Every node here (emsdk-bundled **v22.16.0**, system v22.15/v22.23) exposes only the **old**
`WebAssembly.Suspender` API. So **ANY `-sJSPI` module aborts at instantiation** (before
`main`): `Aborted(Assertion failed: JSPI not supported by current environment...)`, with or
without `--experimental-wasm-jspi` (that flag IS accepted by node — it just gates the old
Suspender API, not the new one). JSPI *runtime* is therefore only exercisable in a browser
(Chrome ≥137, GOAL's floor) or Node ≥23 — not on this toolchain's node.
→ Suspension cases are run under **`-sASYNCIFY` (=1)** as a runnable proxy (same "suspend a C
frame holding a live `jmp_buf`, then resume" hazard). JSPI's native stack-switching preserves
the linear-memory C stack more transparently than Asyncify's instrument-and-rewind, so an
Asyncify PASS conservatively predicts a JSPI PASS. Definitive JSPI-native runtime = follow-up
browser/Playwright harness.

## Results matrix
| case | shape | link (emcc 6.0.5) | runtime |
|---|---|---|---|
| A | setjmp/longjmp, NO suspension, JS-EH + `-sJSPI` | **OK** | baseline (no JSPI) **PASS**; JSPI **aborts at init** (node blocker) |
| B1 | setjmp → suspend → longjmp back after resume, JS-EH | **OK** | Asyncify proxy **PASS** (n=42); JSPI aborts at init |
| B2 | suspend inside setjmp region, normal return, JS-EH | **OK** | Asyncify proxy **PASS** (captured=100); JSPI aborts at init |
| C | libjpeg-turbo `error_exit`→`longjmp` on corrupt stream, JS-EH + `-sJSPI` | **OK** | baseline **PASS** (error path fires); JSPI runtime browser-gated |
| D | libpython embed `Py_Initialize`+raise/except+`import json` + `-sJSPI` | **OK** (full dep closure: `libmpdec`/`libHacl`/`libexpat` + zlib/bzip2/sqlite ports) | baseline **PASS** (`{"ok":1024}`); JSPI runtime browser-gated |
| E | B-shape under Wasm-EH (`-fwasm-exceptions -sSUPPORT_LONGJMP=wasm`) + `-sJSPI` | **OK** (emcc does NOT refuse the combo) | Asyncify proxy **PASS** (B1=42, B2=100) |

## emcc flag-combo findings (no refusals)
- emcc 6.0.5 accepts **both** EH models with `-sJSPI` at link: JS-EH (`-fexceptions`,
  default `SUPPORT_LONGJMP=emscripten`) **and** Wasm-EH (`-fwasm-exceptions` +
  `-sSUPPORT_LONGJMP=wasm`). No combo is refused; no linker error.
- Only diagnostic: `warning: -sJSPI (ASYNCIFY=2) is still experimental [-Wexperimental]`.
  No correctness warning about setjmp/longjmp × JSPI from the compiler.
- setjmp/longjmp survives suspend/resume under the Asyncify proxy for **both** EH models —
  no observed corruption of the `jmp_buf` or control flow across the suspension.

## Implications for M2.5 / M4
- **No stop-energy for JS-EH + JSPI at the toolchain level.** Everything links; the one
  concrete hazard (longjmp across a suspension) passes the runnable proxy on both EH models.
  This does not *prove* JSPI-native safety, but removes the "emcc refuses it / it obviously
  breaks" failure modes and shifts the residual risk to a browser confirmation.
- **M4 must add a browser (Chrome ≥137 / Playwright) smoke that actually suspends** — the
  emsdk node cannot run `-sJSPI` at all (new-API gap). Treat "runs under node" as false for
  any JSPI artifact; CI's JSPI gate is browser-only. (Node ≥23 in CI would also unblock it,
  but the browser is the shipping target regardless.)
- **Python stays synchronous on the (proxied) main thread for M2** (ADR-001 consequence):
  none of these cases needed Python to suspend, and D's init+trampoline works under a JSPI
  link. The suspend×setjmp question only becomes load-bearing if Blender drives JSPI through
  a libpython or libjpeg setjmp region — keep those off the suspend path where possible.
- **Wasm-EH migration (deferred ADR):** E shows the Wasm-EH + wasm-longjmp + JSPI combo both
  links and passes the proxy, so the deferred migration is not blocked by JSPI on the EH
  axis — the decision stays a size/perf/dep-rebuild tradeoff, not a JSPI-compatibility one.

## UPDATE — real JSPI under a tools-local Node 24 (supersedes the Asyncify proxy)

The proxy gap is now closed with a real JSPI runtime. Installed tools-local (gitignored,
no PATH changes): **Node v24.19.0 darwin-arm64**, official nodejs.org prebuilt, SHA-256
`8294b7aa9b03997481c06babf1e8b270c859358f27da57a11509afe537ac381d` (verified vs published
SHASUMS256.txt) at `tools/node24/node-v24.19.0-darwin-arm64/`. It exposes the new
`WebAssembly.Suspending`/`promising` API under `--experimental-wasm-jspi` (still flagged in
24.x; unflagged in Chrome ≥137). Re-ran the committed `-sJSPI` artifacts under it:

| case | shape | real-JSPI runtime (node24 `--experimental-wasm-jspi`) |
|---|---|---|
| A | JS-EH setjmp/longjmp, NO suspension | **PASS** (instantiates + runs; longjmp ok) |
| B1 | JS-EH, setjmp → **real** suspend → longjmp | **FAIL** — `SuspendError: trying to suspend JS frames` (proxy said PASS — **false positive**) |
| B2 | JS-EH, suspend inside setjmp region, normal return | **FAIL** — same `SuspendError` (fails at the suspend, before any longjmp) |
| E | Wasm-EH (`-fwasm-exceptions -sSUPPORT_LONGJMP=wasm`), setjmp → **real** suspend → longjmp | **PASS** (B1=42, B2=100) |
| D | libpython embed, `-sJSPI` link, NO suspension | **PASS** (`{"ok":1024}`; init + trampoline fine under a real JSPI link) |

### What the proxy got wrong, and the precise rule
Asyncify (=1) keeps everything in wasm via instrument-and-rewind and tolerated the JS-EH
setjmp frames; **native JSPI cannot suspend across JS frames**, and emscripten's
`SUPPORT_LONGJMP=emscripten` (our JS-EH default) implements setjmp/longjmp with JS-level
`invoke_*` wrappers. Isolation runs on node24 pin the boundary:
- suspend with **no EH, no setjmp** → PASS; suspend with **`-fexceptions` but no setjmp** →
  PASS. So JS/C++ **exceptions alone are JSPI-safe**.
- a function that merely **contains a `setjmp`** (emscripten SjLj) → **`SuspendError`** for a
  suspend anywhere in it — *even when the suspend executes before the `setjmp` lexically*
  (emscripten wraps the whole setjmp-containing function through JS frames).
- Wasm SjLj (`-sSUPPORT_LONGJMP=wasm`, requires `-fwasm-exceptions`) stays in wasm → suspends
  fine (case E).

**Rule:** under real JSPI, you may not suspend while a function compiled with emscripten
setjmp/longjmp (JS-EH SjLj) is on the stack. `-fexceptions` by itself does not block it —
`setjmp` does.

### Revised implications (these supersede the proxy-based ones above)
- **This re-opens ADR-001's deferred EH sub-decision as JSPI-load-bearing, not just size/perf.**
  Our two setjmp-using deps — **libjpeg-turbo** (error path) and **CPython** (internals) —
  are compiled JS-EH today. If Blender ever JSPI-suspends while either is on the stack, it
  will `SuspendError`. Options: (a) keep JS-EH and **architecturally guarantee suspends occur
  only at top-level yield points, never nested inside a setjmp-using dep**; or (b) migrate the
  stack to **Wasm-EH** (`-fwasm-exceptions` + `-sSUPPORT_LONGJMP=wasm`), which case E proves is
  JSPI-suspend-clean — at the cost of rebuilding the 29 deps + libpython (mixing is forbidden
  in one link). The M2 "JS-EH is free" conclusion still holds for *linking/running without
  suspension* (A, D pass), but not for *suspending across setjmp*.
- **M4 browser smoke remains MANDATORY** regardless: node24 is a proxy for the API, but Chrome
  ≥137 is the shipping runtime. It must (1) confirm A/D-style JSPI links instantiate + run in
  Chrome; (2) reproduce the B-shape `SuspendError` (or its absence) for whatever EH model ships;
  (3) exercise the **actual suspend topology** Blender uses — i.e. prove no JSPI suspend point
  sits inside a libjpeg/CPython setjmp region under the shipped config. Node cannot stand in
  for that last one.
