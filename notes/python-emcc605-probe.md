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
