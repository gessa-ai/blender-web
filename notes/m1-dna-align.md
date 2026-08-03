<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M1 — makesdna wasm32 struct-alignment fix

Date: 2026-08-03. Owner: makesdna worker.
Patch: `patches/0002-makesdna-wasm32-align.patch`
(source: `upstream/source/blender/makesdna/intern/makesdna.cc` @ fbe6228777e7).

TL;DR: **makesdna laid DNA structs out with an i386-style ABI (8-byte scalars
aligned to 4 whenever pointers are 4 bytes). wasm32 has 4-byte pointers but keeps
int64_t/double 8-aligned. The patch makes the wasm makesdna round each member up
to its real wasm32 alignment. `offsetof(Scene, customdata_mask)` goes 5012 → 5016
and every offsetof()/sizeof() static_assert in `dna_verify.cc` now compiles.**
The change is fully guarded by `#ifdef __EMSCRIPTEN__`, so the native host tool
that bakes shipping DNA is byte-for-byte unchanged (proven below).

## The ABI difference

makesdna carries three parallel layouts per struct: `size_native` (the host
compiler running makesdna), `size_32`, `size_64`. The offsets it emits into
`dna_verify.cc` and the `sizeof` it emits both come from **`size_native`**.

Crucially, `size_native` is a plain running **sum of member sizes** — makesdna
inserts **no padding of its own**. It only *checks* alignment; it relies on DNA
structs being hand-padded so the sum already lands every member on its natural
boundary for the ABI it thinks it is on. The model it assumes when `sizeof(void*)`
is 4 is i386/ILP32:

- `member_size_native()` uses `sizeof(void*)` for pointers → 4 on the wasm tool.
- The 8-byte-scalar-before-a-struct alignment check
  (`makesdna.cc`, the `if (sizeof(void *) == 8 && (size_native % 8))` guard) only
  fires on 64-bit. On a 4-byte-pointer host it is **skipped entirely**, i.e.
  makesdna assumes 8-byte scalars need only 4-byte alignment.

That is exactly i386's System V ABI (`__alignof(int64_t) == 4`). But **wasm32 is a
third ABI the model never anticipated**: pointers are 4 bytes (like i386) while
`int64_t` / `double` / any struct containing them stay **8-aligned** (like LP64).

### Concrete failure (the load-bearing example)

`Scene.customdata_mask` has type `CustomData_MeshMasks { uint64_t vmask; uint64_t emask; … }`
(alignment 8, a struct member — so makesdna's `sizeof(void*)==8`-only struct check
never runs on the wasm tool).

- Because makesdna runs as a wasm32 tool, its `size_native` reaches
  `customdata_mask` at **5012** (≡ 4 mod 8) — the DNA hand-padding was tuned for
  8-byte pointers (LP64), so with wasm32's 4-byte pointers the running offset lands
  4 bytes short of an 8-boundary.
- Clang's real wasm32 layout inserts 4 bytes of padding and places it at **5016**.
- `dna_verify.cc` emitted `BLI_STATIC_ASSERT(offsetof(struct Scene,
  customdata_mask) == 5012, …)` → **static assertion fails** against the compiler's
  5016. That is the tier-(a) blocker from `notes/m1-integrate.md`.

## The fix

On the wasm build only, round the running offset **up to each member's true
wasm32 alignment** before adding the member — exactly what the C++ compiler does.

Key insight: makesdna's own `align_32` field already encodes the wasm32 alignment
model member-for-member — pointers 4 (set in the pointer branch), int64_t/double 8
(`add_builtin` sets `align_32 = size`), structs = recursive max of their members.
So `align_32` (folded with any `alignas` override) **is** the correct per-member
wasm32 alignment to round to. Two small helpers do this:

- `member_align_native()` → 4 for pointers, else `max(align_32, alignas-override)`.
- `dna_align_up(offset, align)` → rounds up to a power-of-two boundary.

Rounding is applied in the three places offsets accumulate, all `#ifdef __EMSCRIPTEN__`:

1. Pointer branch — round to 4 before adding the pointer.
2. Scalar/struct branch — round to the member's natural alignment before adding it.
3. Struct tail — round the total `size_native` up to the struct's own alignment
   (`max_align_32`), mirroring how the compiler rounds `sizeof` up.

And the same rounding in `write_sdna_verify()`, which recomputes offsets
independently for the emitted `offsetof` asserts.

## Proof (this session, all builds via `harness/buildwrap.sh`)

Method (per `notes/m1-integrate.md`): relink makesdna objects without
`-sPROXY_TO_PTHREAD`, add `-sNODERAWFS -sEXIT_RUNTIME`, run under
`tools/emsdk/node`, then compile `dna_verify.cc` with the `bf_dna` flags.

| Build | `offsetof(Scene, customdata_mask)` | `dna_verify.cc` compile |
|---|---|---|
| **Unpatched** makesdna | `== 5012` | **FAILS** — `static assertion failed … __builtin_offsetof(blender::Scene, customdata_mask) == 5012` (real offset 5016) |
| **Patched** makesdna | `== 5016` | **compiles clean** (all offsetof/sizeof asserts pass) |

Both makesdna binaries were built from the same objects, differing only in the one
`makesdna.cc` translation unit, and run against the same DNA headers. The patched
tool regenerated all five DNA files (`dna.cc` 577 KB, `dna_verify.cc` 1.06 MB, …).

## Native-build safety (correctness check)

Every added line is inside `#ifdef __EMSCRIPTEN__ … #endif`. Verified this session:

- Native clang does **not** define `__EMSCRIPTEN__`; emcc **does**
  (`clang++ -dM -E` → 0 matches; `emcc -dM -E` → match). `__EMSCRIPTEN__` is an
  Emscripten-only builtin.
- Mechanically stripping the `__EMSCRIPTEN__` blocks from the patched file yields a
  file **identical** to pristine upstream (diff empty apart from two incidental
  blank lines left by the stripper — no code delta).

Therefore the **native** makesdna host tool — the one that bakes the DNA shipped in
`.blend` files — sees the guarded code as absent and produces byte-for-byte
identical DNA. `.blend` compatibility is not affected. The correction exists only
in the wasm-compiled tool, where it must, because only wasm32 has this ABI.

## Follow-up (out of scope here, flagged for the driver)

`source/blender/blenloader` / `dna_genfile.cc` reconstruct member offsets from SDNA
at runtime when reading foreign `.blend` files. Direct C++ field access on wasm uses
the compiler's (now-matching) layout, which the verify asserts guard. If the runtime
SDNA reconstruction path uses the same unpadded summation, cross-endian/cross-ABI
`.blend` *reading* on wasm may need the analogous alignment logic — verify once
`.blend` load is exercised on wasm (M1 corpus / M2).
