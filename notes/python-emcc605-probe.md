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

## M2.7c — C++ try/catch × real JSPI, + setjmp census (ADR-003 evidence)

Real JSPI (Node v24.19.0). Source `sandbox/jspi-probe/f_try.cpp` (parametrized `-DCASE=`),
driven by `run.sh`. Question: emscripten JS-EH try/catch uses the same JS `invoke_*` trampoline
as setjmp — does it equally break suspension?

### F-matrix
| case | shape | JS-EH (`-fexceptions`) | Wasm-EH (`-fwasm-exceptions`, control) |
|---|---|---|---|
| F1 | suspend **inside an ACTIVE try** | **FAIL** `SuspendError: trying to suspend JS frames` | **PASS** (r=42) |
| F2 | fn **contains** try/catch, suspend is **outside/after** it (no active try) | **PASS** (r=42) | **PASS** |
| F3 | **active try 6 plain frames above** the suspend | **FAIL** same `SuspendError` | **PASS** |
| F5 | invoke_* (JS-frame) imports in the wasm | 7 / 7 / 8 (present) | **0** (none) |

### The precise rule (and how it differs from setjmp)
- Under JS-EH, a C++ `try` whose body may throw compiles the enclosing call to a JS `invoke_*`
  wrapper (a JS frame). JSPI cannot suspend across JS frames, so **suspending while ANY try is
  ACTIVE on the stack fails** — whether the suspend is directly inside it (F1) or many plain
  frames below it (F3). F5 confirms invoke_* exist only in JS-EH (7-8) and never in Wasm-EH (0).
- **Crucial contrast with setjmp:** try/catch only poisons suspension while a try is *active*.
  A dormant/absent try does not (F2 PASS). setjmp is worse — the mere *presence* of a `setjmp`
  transforms the **whole function** through JS frames, so a suspend fails even lexically
  *before* the setjmp (see the node24 update above). So: try-scope discipline is per-active-
  scope (tractable); setjmp discipline would be per-whole-function (much harder) — but the
  census below shows setjmp barely exists in our stack.

### Census — setjmp/longjmp machinery in our built JS-EH libs
Detection: `emscripten_longjmp`/`saveSetjmp` symbol refs (longjmp lowers to `emscripten_longjmp`;
setjmp is link-time-lowered so counted in the *linked* wasm via the SjLj runtime symbols).
- `lib/wasm/lib/libpython3.13.a`: **0** setjmp/longjmp refs. `ceval`/`marshal`/`pystate` are
  NOT longjmp callers.
- `lib/wasm/lib/libjpeg.a`: **0**. libjpeg-turbo's error model calls an app-provided
  `error_exit` function pointer — the actual `setjmp`/`longjmp` lives in the **embedding app**
  (our `c_jpeg.c`), not in the library. `jerror`/`jdmarker` carry no SjLj.
- **Full libpython link** `d.wasm` (libpython + libmpdec + libexpat + libHacl): **0** SjLj-
  runtime refs (`saveSetjmp/testSetjmp/emscripten_longjmp/__wasm_setjmp/__wasm_longjmp`). i.e.
  the *entire* Python static image contains no emscripten setjmp region. (CPython's real setjmp
  users are `_ctypes`/libffi — not built for us — and test modules.)

### Read for ADR-003 — is option (a) engineerable, or is Wasm-EH forced?
**Option (a) [keep JS-EH + suspend-topology discipline] is ENGINEERABLE, with bounded guardrails
— not obviously forced to Wasm-EH.** Evidence:
1. **The two feared setjmp deps are effectively non-issues.** CPython contributes **zero** setjmp
   regions to the linked image (so Python running — ceval, import, bytecode — is suspend-safe re
   setjmp). libjpeg's setjmp is app-side and active only inside the narrow `jpeg_read_*` window
   under the app's error handler; you do not suspend mid-synchronous-decode.
2. **try/catch only bites when a try is ACTIVE** (F2). So the discipline reduces to one rule:
   *never place a JSPI suspend point where a C++ `try` (or the app's jpeg `setjmp`) is live on
   the stack.* Suspends confined to top-level async boundaries (main-loop tick, event handler
   entry, a synchronous-fs shim that awaits OPFS at a defined call site) satisfy this.
3. **The residual risk is the C++ EH-heavy deps (OIIO/OCIO/OpenEXR):** their operations run with
   active try blocks. A suspend nested *inside* such an operation would `SuspendError`. Option
   (a) holds only if the architecture guarantees suspends never fire inside those scopes.

**Recommendation:** adopt **(a) provisionally** for the suspending M4+ stack — it avoids the
29-dep + libpython Wasm-EH rebuild — **gated by a hard architectural invariant**: JSPI suspend
points live only at top-level async boundaries, never under an active C++ `try` or the jpeg
`setjmp` scope. Enforce it with the mandatory **M4 Chrome ≥137 browser smoke** asserting the
real suspend topology (no `SuspendError` under the shipped config). Keep **Wasm-EH as the
declared fallback** (F1/F3/F4 prove it removes the constraint entirely: invoke_*=0, all suspend
shapes pass) to switch to iff the suspend surface cannot be confined — that decision is a
size/perf/dep-rebuild tradeoff, now cleanly separable from JSPI feasibility.

---

# M4.python-debt — `_sha3` + `_multiprocessing` for the windowed boot (2026-08-06)

The windowed browser boot (M4.T11+) surfaced two caught-but-noisy Python gaps that the
M2.3 "optional C-exts off" debt now had real consumers for:
- `ERROR:root:code for hash md5/sha1/blake2/sha3/shake was not found` — hashlib logs this at
  import for every builtin hash module that is absent.
- `ModuleNotFoundError: No module named '_multiprocessing'` during **bl_pkg register**
  (addons_core/bl_pkg → `_bpy_internal/http/downloader.py:49`
  `from multiprocessing.synchronize import Event`, whose module top does
  `from _multiprocessing import SemLock, sem_unlink`). Caught by `addon_utils.enable`, but the
  failed register makes Blender pop the **asset-library recovery dialog** on boot → pollutes
  the M4 first-pixels golden.

## `_sha3` (+ `_md5`/`_sha1`/`_blake2`) — the M2.3 rationale was backwards, now RE-ENABLED
M2.3 disabled these four with "need CPython's bundled Hacl archives that DON'T build as a
standalone `.a` (only SHA2 does)". Reading `Modules/Setup.stdlib.in` (3.13.13) shows the
opposite: **only `_sha2` links a *prebuilt* archive** (`Modules/_hacl/libHacl_Hash_SHA2.a`,
line 84); `_md5`/`_sha1`/`_sha3` compile their Hacl source (`_hacl/Hacl_Hash_*.c`, lines
82/83/85) **directly into the module object**, and `_blake2` compiles its own
`_blake2/*_impl.c` (line 86). None needs a standalone `.a`; none has an external dep.
`Hacl_Hash_SHA3.c` is pure scalar C (no `libintvector`/SIMD/`__int128`); `_blake2` falls back
to its reference rounds because emcc defines no `HAVE_SSE2`/`__SSSE3__`. Fix = **drop the four
`py_cv_module__{md5,sha1,sha3,blake2}=n/a`** in `scripts/deps/python.sh`; their objects land
in `libpython3.13.a` directly. Rebuild BUILD OK 149s. Only cosmetic warning: `htobe16` macro
redefined (Hacl `lowstar_endianness.h` vs emscripten `endian.h`).

## `_multiprocessing` — GENUINELY unbuildable single-threaded, so a stdlib shim
`Modules/_multiprocessing/semaphore.c` implements `SemLock` on POSIX **named** semaphores.
Empirical probe (emcc `-fexceptions -matomics -mbulk-memory`, no `-pthread`): `sem_open`,
`sem_close`, `sem_unlink`, `sem_getvalue`, `sem_timedwait` are **undefined at link** (only
`sem_init`/`sem_wait`/`sem_post`/`sem_destroy` resolve) — emscripten ships the named-semaphore
symbols only in its `-pthread` libc, and our browser libpython is single-threaded
(`--with-emscripten-target=browser`, no `__EMSCRIPTEN_PTHREADS__`, ADR-001). So configure
correctly resolves `ac_cv_func_sem_unlink=no` → `_multiprocessing … n/a`. It cannot be built
in our config; forcing `-pthread` into libpython is off-posture and processes don't exist in a
tab regardless.

Precedent: **Pyodide ships no `_multiprocessing`** and its ecosystem answer is "patch the
*consumer* to make the import optional". Our consumer is **pinned/read-only bl_pkg**, so
instead we install a **thread-backed pure-python shim**
(`scripts/deps/python-shims/_multiprocessing.py`) into the harvested stdlib — the honest
single-process degradation (a one-process "multiprocessing" semaphore IS a threading
semaphore; cf. `multiprocessing.dummy`), NOT a raise-on-use stub. It implements the
`SemLock`/`sem_unlink` interface `synchronize.py` needs (kind/value/maxvalue/name ctor;
acquire/release/`__enter__`/`__exit__`/`_get_value`/`_count`/`_is_mine`/`_is_zero`/`_after_fork`/
`_rebuild`; `SEM_VALUE_MAX`). `name=None` (a thread-backed sem has no OS name) makes
`synchronize.py` skip the `resource_tracker`/`_posixshmem` path — the one other absent C
extension it would otherwise reach. Verified drop-in against a real 3.13.13
`multiprocessing.synchronize` (Lock/RLock-recursive/Semaphore/Event, non-block + timeout
paths). `connection.py`'s `_multiprocessing` import is `try/except`-guarded (re-raises only on
win32) so it was never the blocker.

## Verification (authoritative, wasm runtime)
A node embed linked against the **harvested** `lib/wasm/lib/libpython3.13.a` + `libz.a` with the
harvested stdlib+shim preloaded (MEMFS; `NODERAWFS` hit an unrelated emsdk-node `fstat64`
quirk) prints `ALL_OK`:
- `hashlib.sha3_512`/`shake_128`/`md5`/`sha1`/`blake2b`/`sha256` — digests **byte-identical to
  native** `python3.13.13`.
- `import multiprocessing.synchronize` OK (`SEM_VALUE_MAX=2147483647`); `ctx.Lock()`
  acquire/release → `<Lock(owner=MainProcess)>`; `ctx.Event().set()` → `True`.

Size: `libpython3.13.a` 39,085,186 → 40,174,574 B (**+1,089,388 B**, +1.04 MB); defined-`T`
syms 2850 → 2870; `Hacl_Hash_SHA3` syms = 36. `scripts/deps/python.sh` stays idempotent
(2nd run 0.01s); added `PYTHON_FORCE_REBUILD=1` to rebuild without deleting the live artifact,
and the harvest now ends in a single `rename(2)` **atomic swap** of the `.a` (a concurrent gpu
relink of `build-wasm-windowed` reads the old file until that instant). `bl_pkg`/`upstream`
untouched.

---

# M4.python-debt (cont.) — `cattrs` for bl_pkg register (2026-08-06)

The **next** import after the mp shim on the same `bl_pkg` register boot path fails:
`_bpy_internal/http/downloader.py:51-52` does `import cattrs` / `import cattrs.preconf.json`
(and `_bpy_internal/assets/remote_library/json_parsing.py:16-17` the same), right after the
line-49 `from multiprocessing.synchronize import Event` the shim fixed. Absent →
`ModuleNotFoundError: No module named 'cattrs'` → register aborts → asset-library recovery
dialog (M4 first-pixels golden pollution). Measured in the r20 windowed boot (gpu-backend
progress entry: "cattrs ModuleNotFoundError aborting bl_pkg register").

**Unlike the hash exts / `_multiprocessing`, this is NOT a libpython problem** — `cattrs` and
its deps are **pure-python** (zero compiled `.so`, verified against the oracle's shipped
`site-packages`), so nothing links into `libpython3.13.a`. They are just files on `sys.path`.

**Native mechanism:** the superbuild `pip install --no-binary :all:` installs `attrs` +
`cattrs` (+ the whole extras list) into the bundled python's `site-packages`
(`build_files/build_environment/cmake/python_site_packages.cmake:35-58`; versions at
`versions.cmake:443-446`). For a pure-python package the `--no-binary` sdist build and the
`py3-none-any` wheel yield byte-equivalent modules.

**Wasm mirror:** new `scripts/deps/wheels.sh` — fetches the SAME pinned versions' pure-python
wheels from PyPI (version + **SHA-256** pinned & verified, like python.sh pins the tarball
MD5) and extracts them additively into `lib/wasm/lib/python3.13/site-packages/`:
- `attrs 25.3.0` (MIT) → `attr/` `attrs/`
- `cattrs 25.1.1` (MIT) → `cattr/` `cattrs/`  (needs the two below)
- `typing_extensions 4.14.1` (PSF-2.0) → `typing_extensions.py`  (cattrs unconditional dep)
`exceptiongroup` is cattrs' `python_version < '3.11'`-only dep → **N/A on 3.13** (absent from
the oracle too). The script is idempotent (2nd run ~0s) and **additive** — it swaps only the
8 paths it owns via per-package `rename(2)`, preserving `site-packages/numpy` + the stdlib
`_multiprocessing.py` shim (the e3c8158 protections). Payload is gitignored like `numpy/`; the
recipe is the committed artifact and the tree rides into the gpu worker's next `.data` regen.

**Verification (both pass):**
- host CPython **3.13.13** with only the harvested tree prepended to `sys.path`: `import
  cattrs, cattrs.preconf.json, attrs, attr, cattr, typing_extensions` + a
  `make_converter().loads(dumps())` attrs round-trip, every module `__file__` under the
  harvested tree.
- **wasm** CPython 3.13.13 node embed (`build-python-probe/build-jseh/python.js`, harvested
  `site-packages` **NODEFS-mounted** at `/sp`): same import chain + round-trip →
  `WASM_IMPORT_OK`. (For pure-python the host test is already authoritative since import
  resolution/bytecode are platform-independent; the wasm embed confirms it end-to-end.)
- `harness/run.sh --scope m2b` stays **4/4** (core_green 64/64 — numpy preserved).

## `requests` closure (the rest of downloader.py's third-party imports, one pass)

Reading `_bpy_internal/http/downloader.py` **to the end**, the register/boot import chain's
non-stdlib, non-Blender imports are exactly: `cattrs`/`cattrs.preconf.json` (done),
`requests`/`requests.adapters` (:53-54), `urllib3.util.retry` (:55). `requests` transitively
imports `urllib3`, `certifi`, `charset_normalizer`, `idna` at load. The only other non-stdlib
name anywhere under `bl_pkg`+`_bpy_internal` is `setuptools`, and it appears **solely** in
`bl_pkg/tests/modules/python_wheel_generate.py` (CLI wheel-gen, not the register path) — so it
is deliberately excluded. `scripts/deps/wheels.sh` now installs the full pinned closure in one
pass (all versions from `versions.cmake:443-458`, matching the native oracle):

| pkg | ver | license | lays down |
|---|---|---|---|
| requests | 2.32.3 | Apache-2.0 | `requests/` |
| urllib3 | 2.4.0 | MIT | `urllib3/` |
| certifi | 2025.4.26 | MPL-2.0 | `certifi/` |
| charset_normalizer | 3.4.1 | MIT | `charset_normalizer/` (pure `md.py`, not the mypyc `.so`) |
| idna | 3.10 | BSD-3-Clause | `idna/` |

All pure-python (zero `.so`, vs the oracle's shipped trees), all GPL-2.0-or-later compatible
(Apache-2.0 via the -or-later→GPLv3 path; MPL-2.0/BSD-3/MIT directly). **Host** py3.13.13
imports the whole chain + `requests.certs.where()` resolves to the harvested certifi.

## THE NEXT WALL (not a wheel gap) — urllib3 auto-injects Pyodide on `sys.platform=='emscripten'`

The **wasm** embed (which correctly reports `sys.platform=='emscripten'`, unlike the host's
`darwin`) surfaced the real next blocker, so we do not pay another round to discover it:
`urllib3/__init__.py:208-211` **unconditionally** runs
```python
if sys.platform == "emscripten":
    from .contrib.emscripten import inject_into_urllib3
    inject_into_urllib3()
```
and `contrib/emscripten/fetch.py:45-46` does `import js` + `from pyodide.ffi import (JsArray,
JsException, JsProxy, to_js)`. Those are **Pyodide runtime modules**; our non-Pyodide browser
CPython ships neither, so `import urllib3` (hence `import requests`) raises
`ModuleNotFoundError: No module named 'js'` **at register** on the actual wasm build. There is
no native precedent — desktop Blender's `sys.platform` is never `emscripten`, so the branch is
dead there.

**Proven to be the SOLE remaining wall:** with trivial throwaway `js` + `pyodide.ffi` stubs
(scratchpad only, NOT committed) on `sys.path`, the **entire** downloader.py third-party chain
(`cattrs`, `cattrs.preconf.json`, `requests`, `requests.adapters`, `urllib3.util.retry`,
`urllib3`, `certifi`, `charset_normalizer`, `idna`) imports clean on the wasm interpreter and
`requests.certs.where()` resolves to the harvested certifi → `WASM_IMPORT_OK`. (Full tree
verified by mounting the harvested `lib/python3.13` — full stdlib + site-packages — via NODEFS,
since the M2.0b probe embed's reduced `python313.zip` trims `http`.)

**This is a networking-transport decision, flagged to the driver — NOT shipped here.** Options:
(A) a minimal `js` + `pyodide.ffi` **import-shim** (python-shims precedent) that lets
`inject_into_urllib3()` install cleanly so register completes, with actual HTTP deferred
(honest degradation: raise-on-use until a real browser transport exists) — closes the M4
first-pixels golden now; (B) a real emscripten fetch transport backing `js`/`pyodide.ffi`
(a substantial platform_web feature, later milestone); (C) defer the extensions-download
feature entirely in `ledger/deferred.json`. The wheel install itself is correct and
byte-equivalent to native regardless of which option the driver picks.
