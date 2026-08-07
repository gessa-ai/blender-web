<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# numpy release rebuild (-DNDEBUG) - the glTF-export abort fix

## Verdict (outcome first)

- **Root cause (from notes/m7-io-smoke.md): CONFIRMED + FIXED.** `lib/wasm`'s numpy
  2.3.4 was built with C assertions ENABLED, because `scripts/deps/numpy.sh` ran
  `meson setup` with meson's **default buildtype (=`debug`)** and never passed
  `-DNDEBUG`. `numpy/_core/src/multiarray/alloc.c:130` `assert(PyGILState_Check())`
  then false-fires under blender's `-sPROXY_TO_PTHREAD` profile and **aborts on the
  first array allocation** - a bare `numpy.zeros(5)` dies identically, and it took
  the glTF `export_scene.gltf` down.
- **Fix:** pass **`-Db_ndebug=true`** to `meson setup`. That adds `-DNDEBUG` to every
  translation unit unconditionally (independent of buildtype), so `assert()` compiles
  to nothing. One line; ZERO source patches; no other numpy behavior changes.
- **(a) `import numpy; numpy.zeros(5)` no longer aborts - PASS (decisive).**
  - STATIC proof: the `assert(PyGILState_Check())` is gone from the archive -
    `PyGILState_Check` assert-strings in `libnumpy.a` went **3 → 0**, and the
    `multiarray/alloc.c` `__FILE__` strings 2 → 1 (the surviving one is a non-assert
    reference). The abort was literally that compiled-in assert; with it removed the
    allocation proceeds unconditionally. Archive shrank 38.8M → 37.5M.
  - DYNAMIC integrity: a standalone libpython + `libnumpy.a` node embed (registers the
    13 numpy `PyInit_*` in a custom inittab, resolves numpy from the **harvested**
    `lib/wasm` tree) runs `numpy.zeros(5)` and `numpy.array([1,2,3]).sum()==6` clean -
    `NUMPY_GATE_OK`, exit 0. The release rebuild did not regress numpy.
- **(b) glTF export reaches a `.glb` / (c) parse_glb digest - GATED on the blender
  relink (driver-owned), in progress.** All existing `blender*.wasm` binaries still
  link the pre-fix `libnumpy.a`, so they still abort (documented below). The fixed
  `libnumpy.a` is already in `lib/wasm`; the in-flight `build-wasm-cycles` relink
  (and the windowed one) picks it up automatically at its link step. The smoke +
  comparator are turnkey the moment a fresh binary exists (see `sandbox/m7-io-smoke`).

## The change (scripts/deps/numpy.sh - file owner: this lane)

1. `meson setup … -Db_ndebug=true …` (the fix; commented at the call site + a RELEASE
   MODE block at the head of the script).
2. `NUMPY_FORCE_REBUILD=1` env override so the idempotent early-exit can be bypassed for
   the debug→release reharvest (2nd run without it is still ~0s / skip).
3. **Atomic harvest** (matching `scripts/deps/wheels.sh` discipline) - other lanes read
   `lib/wasm` during their links and `.data` repackaging, so nothing is written in place:
   - `libnumpy.a`: staged to a sibling `.libnumpy.a.incoming.$$`, then `mv -f` over the
     marker - a single `rename(2)`, atomic replace on the same fs.
   - `site-packages/numpy`: staged sibling tree, then two fast renames (rename-old-out,
     rename-new-in) - smaller absent-window than `rm -rf` + `mv`, never a partial tree.
   - self-check: greps the harvested archive for the alloc.c assert `__FILE__` string and
     warns if `-DNDEBUG` failed to apply.

Build: `NUMPY_FORCE_REBUILD=1 harness/buildwrap.sh bash scripts/deps/numpy.sh` →
`BUILD OK (141 s) … libnumpy.a (36M, 13 PyInit_*)`.

## Why the abort is only reproducible inside blender.js (not a minimal embed)

A `-sPROXY_TO_PTHREAD` standalone embed that initialises Python **and** runs the script on
the same proxied-main thread does NOT reproduce the abort - even with the OLD (assert-on)
archive it prints `NUMPY_GATE_OK`, because `PyGILState_Check()` returns true there. The
false-fire is specific to blender's own Python init + threading sequence. So the minimal
embed proves numpy *integrity*; the *abort fix* is proven statically (assert removed) and
end-to-end only in the full `blender.js` runtime.

Pre-relink gate reproduction (current `build-wasm-cycles/bin/blender.js`, OLD numpy linked):
the smoke boots, enables the glTF addon, reaches `INFO: Starting glTF 2.0 export`, then
`Aborted(Assertion failed: PyGILState_Check(), at: …/multiarray/alloc.c,130,_npy_alloc_cache)`
at `npy_alloc_cache_dim`. Note the swapped **pure-python** tree loaded fine - the abort is
in the statically-linked C-ext, confirming the fix must ride in `libnumpy.a` → the `.wasm`.

## The `.data` repackage - needs nothing special

The fix is entirely in the compiled C objects (`libnumpy.a`), which are **statically linked
into `blender*.wasm`**. The pure-python `site-packages/numpy` tree is byte-identical to the
debug build (NDEBUG touches no `.py`). So:
- the driver's **windowed relink** picks up the fix at its next **`.wasm` link** - no manual
  step, no inittab change (the 13 `PyInit_*` are unchanged);
- the **`.data` repackage** needs no special handling - the numpy `.py` payload is unchanged,
  and re-harvesting it is a content no-op done atomically.

## Verification harness (this lane's, sandbox/m7-numpy-release/)

- `embed_zeros.c` - the 13-module inittab + the exact `numpy.zeros(5)` repro, resolving numpy
  from the harvested `lib/wasm` tree.
- `link_run.sh <archive.a> <st|mt> <tag>` - links + runs the gate single-threaded or under the
  blender-matching threaded profile (`-pthread -sPROXY_TO_PTHREAD`; dlmalloc, since CPython 3.13
  vendors its own mimalloc inside `libpython3.13.a` and `-sMALLOC=mimalloc` would double-define).
- `libnumpy.a.OLD` - the pre-fix archive, kept for the static 3→0 comparison.
