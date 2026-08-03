<!--
SPDX-FileCopyrightText: 2026 KA
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M1/M2 scout: CPython 3.13 under Emscripten for blender-web

Strategy note (no build). Sources cited inline.

## Bottom line

**Build CPython 3.13.13 ourselves** from the python.org tarball, with **our** emcc,
using CPython's in-tree `Tools/wasm` Emscripten config, and cherry-pick Pyodide's
CPython patch stack only where the vanilla build breaks. Produce a static
`libpython3.13.a` + headers + the `Lib/` stdlib tree; harvest to `lib/wasm`.
**Do NOT harvest Pyodide's prebuilt libpython** — it is built with emcc 4.0.9 and is
entangled with `libpyodide`/hiwire (JS-FFI); ABI/flags must match Blender's own emcc.

## Why this, not the alternatives

- **CPython 3.13 requires exactly 3.13** for Blender 5.2 (pin: `versions.cmake` =
  `PYTHON_VERSION 3.13.13`; `FindPythonLibsUnix.cmake:39` hardcodes `3.13`). CPython
  3.14 restored official Emscripten support (Tier 3, PEP 776, approved Oct 2024) — but
  3.14 is off the table. 3.13 *dropped* official Emscripten support, yet the build path
  still exists: `Tools/wasm/wasm_build.py`, `Tools/wasm/config.site-wasm32-emscripten`,
  `emconfigure ../../configure --with-emscripten-target=browser --with-build-python`,
  `emmake make`. Recommended emcc >= 3.1.19. (python.org devguide / Tools/wasm/README.)
- **Pyodide 0.28/0.29 = CPython 3.13.2 + emcc 4.0.9.** Its recipe *does* build a
  `libpython3.13.a` internally then links it with `libpyodide.a`. Reusable as a **patch
  reference** (its `cpython/patches/` fixes setjmp/longjmp, dlopen/syscall stubs), not as
  a binary artifact. (blog.pyodide.org 0.28 release; pyodide DeepWiki build-process.)
- **python-build-standalone** publishes no wasm32-emscripten builds. Not an option.
- **emscripten-forge** targets its own toolchain/ABI — not worth adopting a second
  toolchain when we already run emcc.

## What Blender actually needs (verified against pin)

`FindPythonLibsUnix.cmake` resolves three things, nothing more:
1. `include/python3.13/Python.h` (headers),
2. `libpython3.13.a` (`find_library python3.13`, static ok),
3. the stdlib tree (`.../python3.13/abc.py` probe, line ~161) — i.e. `Lib/`.
Plus Blender's own `scripts/` tree (already in `upstream/scripts/`).

**numpy is NOT needed at startup.** Grep of `upstream/scripts/startup/**` and
`scripts/modules/**` finds zero `import numpy`. The only numpy references are the win32
packaging path and Mantaflow (`WITH_FLUID`, forced OFF). So no numpy wheel for M2.

**Threading is NOT needed at startup.** `bpy_interface.cc:598`
`Py_DECREF(PyImport_ImportModule("threading"))` is inside `#ifdef WITH_FLUID` — OFF for
us. `bl_ui/` and startup `.py` import no `threading`/`_thread`. CPython's `threading`
module still *imports* fine single-threaded if ever pulled in; it just can't spawn.

## Step list (M2 python-wask worker)

1. Fetch `Python-3.13.13.tar.xz` (hash in `versions.cmake:385`); record in `deps.json`
   (PSF license, GPL-compatible).
2. `source tools/emsdk/emsdk_env.sh`; build a native `--with-build-python` first (or use
   `oracle` python 3.13) for the cross-build bootstrap interpreter.
3. `emconfigure ../configure -C --host=wasm32-unknown-emscripten --build=$(...)
   CONFIG_SITE=../Tools/wasm/config.site-wasm32-emscripten
   --with-emscripten-target=browser --with-build-python=<3.13>
   --disable-shared --disable-ipv6 --without-pymalloc-off`; `emmake make -j`.
4. If configure/compile breaks under emcc 6.0.5, apply the minimal subset of Pyodide's
   `cpython/patches/` (setjmp/longjmp, dlopen removal, `faulthandler`/signal, socket
   syscall stubs). Keep the patch surface in `patches/` with SPDX + provenance.
5. Link flags for the eventual Blender link: `-sSUPPORT_LONGJMP=wasm`, `-sWASM_BIGINT`,
   `-sMALLOC=mimalloc` (match GOAL posture); freeze/omit unused stdlib modules to trim MB.
6. Harvest to `lib/wasm`: `libpython3.13.a`, `include/python3.13/`, and `Lib/` staged as
   `python3.13/`. Point `blender_web.cmake` at it (PYTHON_LIBPATH/PYTHON_INCLUDE_DIRS),
   set `_PYTHON_VERSION_SUPPORTED` satisfied.
7. Gate: `import bpy` headless in Node/worker; then tier-(b) background bpy suite subset.

## Top 3 risks

1. **emcc version skew (highest).** Pyodide's validated combo is emcc **4.0.9**; CPython
   3.13 tooling targets ~3.1.x; our toolchain is **6.0.5** — ahead of every known-good
   3.13 build. The *entire* wasm ABI (Blender + libpython + deps) must share one emcc, so
   we can't just grab Pyodide's binary. Pyodide's patches may not apply cleanly to 6.0.5.
   *Mitigation / open decision for milestone gate:* either (a) forward-port patches to
   6.0.5, or (b) pin emsdk to 4.0.9 to reuse Pyodide's stack verbatim (contradicts the
   "emcc 6.0.5 installed" premise — flag to driver). This is a real toolchain decision,
   not a footnote.
2. **setjmp/longjmp x JSPI.** CPython leans on setjmp/longjmp; GOAL mandates `-sJSPI`
   (not Asyncify, which Pyodide historically used). Stack-switching vs longjmp handling
   can conflict. *Mitigation:* build libpython with `-sSUPPORT_LONGJMP=wasm` (native
   wasm EH/longjmp), verify against a bpy import smoke before trusting it under JSPI.
3. **Single-thread vs Blender's job system.** CPython-emscripten is single-threaded, but
   Blender calls `PyGILState_Ensure` from worker threads (`bpy_interface.cc` GIL calls)
   for jobs/handlers. Startup is single-threaded and safe, but any Python-touching job
   under `-sPROXY_TO_PTHREAD` needs care. *Mitigation:* keep Python execution on the main
   thread for M2; revisit real-pthread CPython (experimental in newer Pyodide) only if a
   launch-tier feature demands off-main-thread bpy.

## Sources
- https://peps.python.org/pep-0776/ (Emscripten Tier 3, 3.14 only)
- https://docs.python.org/3.13/using/configure.html + Tools/wasm/README (3.13 build path, emcc>=3.1.19, "not officially supported")
- https://blog.pyodide.org/posts/0.28-release/ (Pyodide 0.28 = Py3.13 + emcc 4.0.9)
- https://deepwiki.com/pyodide/pyodide/4.2-build-process (libpython.a + libpyodide link, cpython patches)
- upstream pin: build_environment/cmake/versions.cmake:381-385; build_files/cmake/Modules/FindPythonLibsUnix.cmake:39,161; source/blender/python/intern/bpy_interface.cc:598
