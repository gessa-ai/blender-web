<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# NumPy 2.3.4 for the wasm CPython 3.13 — build shape, recon, verification

Status (2026-08-05): **BUILT + IMPORT GATE GREEN.** numpy 2.3.4 cross-compiles for
wasm32-emscripten (emcc 6.0.5, JS-EH) with **ZERO source patches** and links **statically**
into a libpython embed; `import numpy; numpy.array([1,2,3]).sum()` prints `6` under emsdk node.
Artifact harvested to `lib/wasm`. The blender relink that puts it into `blender.js` is a
**driver follow-up** (this lane produces + harvests + verifies the artifact, like `python.sh`).

Recipe: `scripts/deps/numpy.sh` (idempotent). Own build tree: `build-deps/numpy/`.

## Build shape chosen: (a) static, baked into the inittab

The task posed three shapes. Decision, with evidence:

- **(a) static archive registered in a custom inittab — CHOSEN.** numpy's C extensions compile
  to objects with meson; we combine the 13 production modules' objects + numpy's internal static
  libs into ONE `libnumpy.a`, and register their 13 `PyInit_*` in Blender's Python inittab
  (`bpy_interface.cc` `bpy_internal_modules`). Posture-clean: no dynamic linking (GOAL), one
  archive like `libpython3.13.a`. **Verified working** (import gate, below).
- **(b) .so side-modules — REJECTED.** Conflicts with the mono-wasm posture (GOAL: no dynamic
  linking; `-sMAIN_MODULE/SIDE_MODULE` is the experimental-with-pthreads path ADR-001 avoids).
- **(c) Pyodide's approach — NOT our posture.** Pyodide builds numpy as dlopen'd `.so` +
  dynamic linking. We reuse Pyodide's *build knowledge* (meson options, cross file) but NOT its
  linking model.

## Recon

### Version (Blender 5.2 pin)
`versions.cmake:498` — **NUMPY_VERSION 2.3.4**, MD5 `8717ed1828a8a390c454c6636e91c46a`,
**BSD-3-Clause** (GPL-compatible). Upstream builds it via `pip install --no-build-isolation .`
(meson-python), `numpy.cmake:37`.

### Pyodide patch triage (toolchain-necessary vs Pyodide-FFI — ADR-001 discipline)
**Current Pyodide carries ZERO numpy source patches.** Since the numpy meson migration
(Pyodide 0.27 / numpy 2.x) the recipe is meson OPTIONS + an emscripten CROSS FILE, nothing
edited — upstream numpy 2.3.4's meson build is emscripten-aware and has absorbed the old
toolchain fixes. The last real patch set (numpy 1.22.3, distutils era) was **6 patches, ALL
bucket (a) toolchain-necessary, NONE Pyodide-FFI**: math feature-detection for wasm strict
linking, `random_float_fill`/f2py return-type fixes for wasm strict function-pointer signatures,
fenv-flag fallback, and two cross-compile size/detection fixes. All are **obsolete for 2.3.4**
(they patched `setup.py`/distutils machinery that no longer exists, and their intent is encoded
upstream). Net: **we inherit zero patches.** This matched the outcome exactly — meson setup +
compile succeeded with an unmodified 2.3.4 source tree.

### meson-vs-setup.py cross build
numpy has been **meson-only since 1.26** (no `setup.py`). Cross build essentials that MUST be
supplied (a plain `meson setup` cannot auto-detect them for wasm):
1. **numpy vendors its own meson** at `vendored-meson/meson/meson.py` (1.5.2) carrying the
   numpy-specific **`features`** CPU module. A stock system meson fails
   `meson_cpu/x86/meson.build:2 import('features')` → *"Module features does not exist"*. Drive
   the build with the vendored meson.
2. **Cross python for introspection.** meson reads the *running* python's `sysconfig` for the
   Python include dir (scheme-derived → the native `base_prefix`, i.e. 64-bit host headers).
   Compiling wasm32 against 64-bit `pyconfig.h` fails `LONG_BIT`/`SIZEOF_VOID_P`. Fix = the
   crossenv trick: a native CPython 3.13 that REPORTS the wasm target sysconfig via
   `_PYTHON_SYSCONFIGDATA_NAME` (a patched `_sysconfigdata` with `INCLUDEPY`→`lib/wasm`) + a
   `sitecustomize` overriding `sysconfig.get_paths()['include']`. Injected into BOTH the cross
   file's `[binaries] python` AND the meson-running process (its internal `python3` dep drives
   the cython sanity check).
3. **`longdouble_format = 'IEEE_QUAD_LE'`** in the cross file. Emscripten `long double` is
   128-bit IEEE quad (`sizeof==16`, verified); numpy detects this by *running* a probe
   (`_core/meson.build:439`) — impossible cross → supply as a property (matches Pyodide).
4. meson options for a minimal wasm build: `-Dallow-noblas=true` (bundled f2c lapack-lite, no
   external BLAS/LAPACK — already the 2.3.x default), `-Ddisable-optimization=true` (no CPU
   dispatch/SIMD; wasm has no numpy SIMD target anyway), `-Ddisable-threading=true` (matches the
   single-threaded libpython), `-Ddisable-highway/-svml/-intel-sort=true` (x86-only).

## The 13 production C-extension modules (inittab)

`import numpy` eagerly imports `_core`, `linalg`, `fft`, `random`, so ALL 13 `PyInit_*` must be
registered (only `_multiarray_umath` is needed for `.sum()` itself, but the eager subpackage
imports pull the rest). The 6 test/`_simd` extensions are excluded.

| dotted import name (inittab key) | init function |
|---|---|
| `numpy._core._multiarray_umath` | `PyInit__multiarray_umath` |
| `numpy.linalg._umath_linalg` | `PyInit__umath_linalg` |
| `numpy.linalg.lapack_lite` | `PyInit_lapack_lite` |
| `numpy.fft._pocketfft_umath` | `PyInit__pocketfft_umath` |
| `numpy.random.mtrand` | `PyInit_mtrand` |
| `numpy.random._common` | `PyInit__common` |
| `numpy.random.bit_generator` | `PyInit_bit_generator` |
| `numpy.random._bounded_integers` | `PyInit__bounded_integers` |
| `numpy.random._generator` | `PyInit__generator` |
| `numpy.random._mt19937` | `PyInit__mt19937` |
| `numpy.random._philox` | `PyInit__philox` |
| `numpy.random._pcg64` | `PyInit__pcg64` |
| `numpy.random._sfc64` | `PyInit__sfc64` |

Dotted-name inittab entries work: CPython's `is_builtin` scans `PyImport_Inittab` by exact name
string, and `BuiltinImporter` is on `sys.meta_path` for submodule imports too.

## Static-embedding seams fixed (the non-Pyodide part)

1. **f2c lapack-lite duplicate symbols.** With `allow-noblas`, numpy compiles the bundled f2c
   LAPACK into BOTH `lapack_lite` and `_umath_linalg`. Separate `.so`s hide it; ONE static link
   sees duplicate strong symbols (`xerbla_`, `s*_`, …). Fix: dedup module objects by basename
   (the shared f2c sources are identical) → one copy in `libnumpy.a`.
2. **numpy's internal static libs.** `_multiarray_umath` links `libnpymath.a`, `libunique_hash.a`,
   `lib_multiarray_umath_mtargets.a`, `libargfunc.dispatch.h_baseline.a`, and the baseline
   `libloops_*.dispatch.h_baseline.a`; random links `libnpyrandom.a`. All merged into `libnumpy.a`
   via `emar -M` `ADDLIB` (once each).
3. **1 benign wasm function-signature warning** — `random_multinomial` is declared with
   different signatures (i64 vs i32 for one param) in `_generator.pyx.c` vs
   `src/distributions/distributions.c` (an LP32/`long`-vs-`int64` inconsistency wasm's strict
   typing surfaces). NON-fatal, not on the gate path; would only affect
   `np.random.multinomial(large n)`. TODO: verify/patch if a suite exercises it (same class as
   Pyodide's old 0002/0006 patches).

## Verification — the import gate (GREEN)

Standalone libpython embed (`build-deps/numpy/embed_test.c`): a `main()` that registers the 13
inittab entries, `Py_InitializeFromConfig`, runs the gate. Links `libnumpy.a` + `libpython3.13.a`
+ `--use-port=zlib` (libpython's own zlibmodule; the real blender link resolves zlib from
lib/wasm) + the `patches/node-fstat-shim.js` `--pre-js` (M2.5 seam #7, NODERAWFS-only). Under
emsdk node:
```
NUMPY 2.3.4
SUM 6
NUMPY_GATE_OK        (exit 0)
```
This is the correct methodology given the contended `build-wasm` tree: it proves the ARCHIVE +
inittab shape against the identical libpython WITHOUT relinking `blender.js` (cf. the M2.0b
libpython embed probe that validated libpython before WITH_PYTHON flipped).

## Harvest (in `lib/wasm`)

- `lib/wasm/lib/libnumpy.a` — combined static archive (~37 MB, 13 `PyInit_*`).
- `lib/wasm/lib/python3.13/site-packages/numpy/` — pure-python tree (520 `.py`, incl. the 3
  meson-generated `__init__.py`/`__config__.py`/`random/__init__.py`). `site` auto-adds
  site-packages (blender disables python isolation, `bpy_interface.cc:379`).

## Integration follow-up (DRIVER — the contended build-wasm relink; REPORT not do)

1. Link `lib/wasm/lib/libnumpy.a` into the `blender` target (append to the python link, same
   place as `libpython3.13.a`).
2. Add the 13 inittab entries (table above) to `bpy_interface.cc` `bpy_internal_modules` (a
   patch), so the static modules resolve under their dotted names.
3. Confirm `site-packages` is on `sys.path` at boot (it is, via `site` — isolation off).
4. Re-run the gate on the real `blender.js`, then flip `NUMPY_HARVESTED=1` in the `scope_m2b`
   harness (notes/m2-tierb-prep.md §scope-final) → promotes the 8 numpy-pending tier-b suites
   (`script_load_addons/modules`, `script_pyapi_prop_array`, `bl_sculpt_*`, `bl_*_paint_brushes`)
   to must-pass; update the `optional-python-modules` deferral in `ledger/deferred.json`.
