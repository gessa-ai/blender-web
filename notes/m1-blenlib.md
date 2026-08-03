<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M1 — bf_dna green + bf_blenlib compiles to wasm

Date: 2026-08-03. Owner: build-deps worker.
Patches added: `patches/0004-blenlib-wasm-libc-gaps.patch`,
`patches/0005-blenlib-wasm32-sizeof-assert.patch`.
Builds all via `harness/buildwrap.sh` (Ninja generator; fresh configure 49 s).

TL;DR: **With the full patch series (0001–0005) applied, `libbf_dna.a` and
`libbf_blenlib.a` both build clean for wasm32.** bf_dna's `dna_verify.cc`
static-asserts now pass (`offsetof(Scene, customdata_mask) == 5016`, the wasm32
value baked by patch 0002). bf_blenlib had exactly **5 failing translation units
out of 139** (134 compiled untouched); all 5 fell into **three error classes**,
all now fixed. No missing-POSIX-API avalanche, no SIMD/intrinsic/endianness
failures surfaced — blenlib-proper is far cleaner on wasm than the M1 estimate.

## bf_dna (task step 1) — GREEN

`cmake --build build-wasm --target bf_dna` → makesdna links to `bin/makesdna.js`,
runs under node (patch 0003), regenerates all 5 DNA files, and `bf_dna` compiles
`dna_verify.cc` (step 28/29) + links `lib/libbf_dna.a` (29/29). The generated
assert reads `offsetof(struct Scene, customdata_mask) == 5016` (was 5012 pre-0002)
and every offsetof/sizeof static_assert passes. The wasm32-alignment fix is
confirmed correct end-to-end, not just in the isolated relink from the prior round.

## bf_blenlib error classes (task step 2) — ranked, all FIXED

Collected with `ninja -k 0` (keep-going) so every TU's failure surfaced in one
pass, not first-error-only. 14 `error:` lines across 5 files → 3 classes:

### Class 1 — wasm32 ILP32 pointer-size assumption (3 TUs) — FIXED (patch 0005)
`BLI_resource_scope.hh:144  static_assert(sizeof(ResourceScope) == 16)` fails
`8 == 16`. `ResourceScope` = a `ChunkedList` head pointer + a `LinearAllocator<>&`
reference = 2 pointers = 16 B under LP64, **8 B under wasm32** (4-byte pointers).
Hit by every TU that includes the header (`index_mask.cc`,
`index_mask_expression.cc`, `resource_scope.cc`). The assert is a regression guard
(catches accidental `NonCopyable` double-inheritance bloat), not a layout
requirement, so the fix keeps it — asserting the correct wasm32 size under
`#ifdef __EMSCRIPTEN__`, LP64 value otherwise. **This is a recurring class**:
hardcoded `sizeof(...) == <LP64 constant>` asserts will reappear across DNA-heavy
and container code; the pattern is "guard the assert by ABI, don't delete it."

### Class 2 — missing libc `<fenv.h>` FP-exception flags (1 TU, 9 errors) — FIXED (patch 0004)
`expr_pylike_eval.cc` uses `fetestexcept(FE_DIVBYZERO | FE_INVALID)` to detect
div-by-zero / NaN after evaluating an expression. wasm has **no floating-point
exception status register**, so Emscripten's `bits/fenv.h` defines
`FE_ALL_EXCEPT 0` and omits `FE_DIVBYZERO` / `FE_INVALID` entirely (verified in
`tools/emsdk/.../sysroot/include/bits/fenv.h`); `fetestexcept()` always returns 0.
Fix defines the two missing macros to `0` under `#ifdef __EMSCRIPTEN__` so it
compiles. **Behavioral caveat (honest deferral, not silent):** the post-eval FP
error check is a **no-op on wasm** — driver expressions that divide by zero or
produce NaN return `EXPR_PYLIKE_SUCCESS` instead of `_DIV_BY_ZERO`/`_MATH_ERROR`.
This is a hardware limitation of wasm, not fixable via flags; a source-level
explicit div/NaN check would be needed for parity. Flag for
`ledger/deferred.json` if the driver-network tier-(b/c) suite exercises it.
(`feclearexcept(FE_ALL_EXCEPT)` at line 176 compiles fine — `FE_ALL_EXCEPT` is 0.)

### Class 3 — missing POSIX filesystem struct `statfs` (1 TU, 2 errors) — FIXED (patch 0004)
`storage.cc` `BLI_dir_free_space()` selects `struct statfs` + `statfs()` because
Emscripten is neither `__linux__` (no `<sys/vfs.h>`) nor a BSD/Apple target, so
`statfs` is an incomplete type. Emscripten **does** implement POSIX `statvfs()`.
Fix adds an `#ifdef __EMSCRIPTEN__` block that includes `<sys/statvfs.h>` and
defines `USE_STATFS_STATVFS`, routing to the existing statvfs code path (same one
NetBSD/OpenBSD/Haiku use). Fully functional, no behavioral loss.

## Native-build safety
All three fixes are inside `#ifdef __EMSCRIPTEN__` (class 3 adds a new guarded
include block; class 1 wraps the existing assert with an `#else` keeping the
LP64 value; class 2 only `#define`s under the guard, and `#ifndef`-guards each
macro). Native clang never defines `__EMSCRIPTEN__`, so the host build is
byte-unchanged.

## What remains (blenlib)
- `bf_blenlib.a` **exists** (4.15 MB, 139 members) — the M1.9 wall is cleared.
- Not yet done: the `blenlib_test` / `BLI_*` gtest targets (the actual tier-(a)
  gate) — needs the gtest/gflags/glog extern link + a node wasm test-runner
  (task 4 in `notes/m1-integrate.md`). bf_blenlib compiling is the prerequisite,
  now met.
- Watch for more Class-1 `sizeof == <LP64>` asserts and Class-2 libc gaps when
  blenkernel/depsgraph come online.

## Receipts
- Configure: `ledger/buildlogs/20260803T143232.log` (OK 49 s).
- bf_dna: `ledger/buildlogs/20260803T143328.log` (OK, 29/29, dna_verify offset 5016).
- bf_blenlib (pre-fix, -k 0, all classes): `ledger/buildlogs/20260803T143358.log`
  (5 FAILED TUs, 14 errors).
- bf_blenlib (post-fix): `ledger/buildlogs/20260803T143640.log` (OK, 6/6, links
  `lib/libbf_blenlib.a`).
- upstream/ restored pristine (`git -C upstream status --porcelain` empty);
  full series 0001–0005 re-applies `--check` clean.
