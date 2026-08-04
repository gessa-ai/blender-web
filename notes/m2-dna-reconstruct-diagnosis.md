<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M2.5 DNA diagnostic — `master_collection` NULL is a RUNTIME reconstruct bug, NOT makesdna

Date: 2026-08-04. Owner: makesdna/patch-0002 worker (driver-directed diagnostic).
**VERDICT: STOP → driver.** The root cause is in the runtime `DNA_struct_reconstruct`
offset accumulation (`dna_genfile.cc`), not the makesdna tool / patch 0002. Per the
task rule ("if it's in DNA_struct_reconstruct … STOP — that fix needs a driver
decision"), no fix applied. Upstream left in the wave state (not touched by me;
diagnostic was read-only + a Python SDNA parser over the generated `dna.cc`).

## Root cause (mechanical, proven)

`create_reconstruct_steps_for_struct()` (dna_genfile.cc:1497-1508) computes each
target member's write offset as a **pure unpadded sum**:

    int new_member_offset = 0;
    for (new_member ...) {
      init_reconstruct_step_for_member(..., new_member_offset, ...);   // TARGET write offset
      new_member_offset += get_member_size_in_bytes(newsdna, new_member);  // NO alignment
    }

`get_member_size_in_bytes` (dna_genfile.cc:1479) returns `pointer_size*len` or
`types_size[type]*len` — **no inter-member padding**. This is the EXACT i386/unpadded
model patch 0002 fixed in the makesdna *tool*, here reproduced in the *runtime*
reconstruction path. On LP64 the DNA hand-padding makes unpadded == compiler, so it
has always worked; on **wasm32 (4-byte pointers, 8-aligned int64/double)** the
hand-padding no longer aligns and the unpadded sum drifts.

`types_alignment[]` exists (dna_genfile.cc:538) but is a coarse
`__STDCPP_DEFAULT_NEW_ALIGNMENT__` default (only refined for `mat4x4f`) and is used
**only** by `DNA_struct_alignment()` (1711) — NOT in the offset accumulation. So it
cannot be dropped in as a fix.

## Evidence — definitive test (generated `dna.cc` SDNA vs compiled `offsetof`)

Parsed the real wasm-generated SDNA (`build-wasm/.../dna.cc` `DNAstr`) and replicated
BOTH the runtime unpadded accumulation and a padded (compiler) model; validated the
padded model against `dna_verify.cc`'s `offsetof` asserts.

- **makesdna is correct.** `dna_verify.cc` (green) asserts `offsetof(Scene,
  view_layers)==5400`, `offsetof(Scene, master_collection)==5408`; my padded model
  reproduces **all 9357 dna_verify member offsets across 992 structs, 0 mismatch**.
  SDNA `Scene` TLEN=6672 (padded, correct).
- **Runtime unpadded diverges.** For `Scene` the unpadded sum gives
  `customdata_mask` 5012 (compiler 5016 — the patch-0002 canary; first divergence),
  and it propagates: `view_layers` 5396/5400, **`master_collection` 5404/5408**,
  `layer_properties` 5408/5412, … (17 of 51 Scene members shifted). At runtime the
  reconstruct writes `master_collection`'s value to `new_block+5404`; C++ reads
  `scene->master_collection` at the compiler offset 5408 — where the runtime wrote
  `layer_properties` (NULL in startup.blend) — so the field reads **NULL** →
  `BKE_layer_collection_sync` bails at `!scene->master_collection` → OUT_OF_SYNC
  never cleared → `layer_utils.cc:205` assert. Exactly the reported abort.

## Broad-risk sizing (not assumed — measured)

Full-struct alignment scan over **all 993 SDNA structs** (every member, not just the
9357 dna_verify-covered ones; model validated 0-mismatch against dna_verify):

**Exactly ONE struct diverges under wasm32: `Scene`.** Every other struct's hand
padding happens to align under both ABIs. So the blast radius is narrow — but fatal,
because `Scene` is reconstructed on every `.blend` open and `master_collection` is a
load-bearing live pointer. (Silent misreads of *other* structs are NOT happening —
that risk is now sized to zero for the current pin, not assumed away.)

## Why `dna_verify.cc` did not catch it (and is still trustworthy)

`dna_verify` asserts `compiler_offsetof(X) == makesdna_write_sdna_verify_offset(X)`.
Both sides are padded (patch 0002 fixed `write_sdna_verify`), so they agree and it
compiles green. `dna_verify` **never exercises** the runtime
`create_reconstruct_steps_for_struct` accumulation — that is an *independent*
unpadded computation in a different file. So the gap is not a missing member assert
(coverage is fine: the full-struct scan found no uncovered divergence beyond Scene) —
it is that the **runtime reconstruction path has no compile-time verification at
all**. `dna_verify` remains fully trustworthy for what it certifies (makesdna↔compiler
SDNA agreement).

## ListBaseT hypothesis — DISPROVEN

`view_layers` is recorded in the SDNA as plain **`ListBase`** (its base class;
`ListBaseT<T> : public ListBase` adds no data members). makesdna resolves the
template correctly (TLEN 8 on wasm32). `view_layers` is misplaced *only* because of
the accumulated upstream padding error that begins 388 bytes earlier at
`customdata_mask` — nothing template-specific.

## Fix direction (for the driver — NOT applied here)

Add wasm32 alignment to the target accumulation at dna_genfile.cc:1507 (round
`new_member_offset` up to each member's real wasm32 alignment before it is passed in,
and round the struct total up to the struct alignment), `#ifdef __EMSCRIPTEN__`, LP64
byte-identical (unpadded==padded there, so guarded-out is a no-op). Requirements that
make this a driver call, not a mechanical worker fix:
1. Needs a REAL per-type wasm32 alignment source. `types_alignment` is a coarse
   default — unusable. Either compute alignment recursively at SDNA load
   (pointer=4, int64/double=8, struct=max-of-members) or bake makesdna's `align_32`
   into the SDNA (an SDNA format addition).
2. Cross-ABI asymmetry: the OLD/file side (`elem_offset_impl`, pointer_size=8) is
   already correct under LP64 hand-padding, so ONLY the new/wasm32 side needs
   padding — but this must be verified for consistency (and for the wasm32-writing
   case if `.blend` *save* is ever exercised on wasm32).
3. It is a runtime behavior change on the entire `.blend` read path (every struct,
   every file), so it wants sign-off + a corpus regression, unlike a build-time tool
   fix.

Alternative the driver flagged earlier stands: the wasm64 escape hatch (GOAL:
"wasm32 first; wasm64 later") makes pointer_size 8 and the hand-padding aligns again,
sidestepping this whole class — a strategic option to weigh against the dna_genfile
fix.

## Receipts
- SDNA parsers: scratchpad `sdna_probe.py` (Scene table), `sdna_align.py`
  (all-993-struct alignment scan, model-validated 9357/9357 vs dna_verify).
- Generated inputs: `build-wasm/source/blender/makesdna/intern/{dna.cc,dna_verify.cc}`.
- Boot abort repro + instrumentation: notes/m2-python-boot.md §THE BLOCKER.
- upstream/ NOT modified (wave tree intact); no dna_genfile.cc / makesdna edit by me.
