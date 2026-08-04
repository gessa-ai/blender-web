<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M2b — bhead "same old address" collision on wasm32: DIAGNOSIS + STOP → driver

Date: 2026-08-04. Owner: ABI specialist (patch-0014 family).
**VERDICT: STOP → driver.** Root cause is definitively identified and proven from the
real file, but the correct fix exceeds the documented class of a targeted,
`#ifdef __EMSCRIPTEN__`-guarded ABI fix, and the naive "uint64 map keys" fix the
callout proposed is INSUFFICIENT (it converts a loud abort into SILENT pointer
corruption). No patch applied; upstream untouched by this task (read-only + a static
Python `.blend` parser).

## The failure
Suite `bl_node_structure_type_inference` on wasm aborts reading
`upstream/tests/files/node_group/structure_type_inference.blend`:
`readfile.cc:2789 read_data_into_datamap → CLOG_ERROR "Invalid, or multiple bhead with
same old address value (0xefec4e70)"` → `Aborted()`. Native passes.

## Root cause — PROVEN from the file (not inferred)
`BHead::old` is `const void *` (4 bytes on wasm32). Reading a 64-bit `.blend`, the
8-byte file block address is narrowed to 32 bits by `uint32_from_uint64_ptr()`
(BLO_core_bhead.hh:124): `ptr >>= 3; return uint32_t(ptr)` — used by
`old_ptr_from_uint64_ptr()` (blo_core_bhead.cc:22-30, only when `sizeof(void*)!=8`).
The same `>>3` narrowing is duplicated in `cast_pointer_64_to_32()`
(dna_genfile.cc:929: `new_data[a] = old_data[a] >> 3`) for pointer FIELDS.
The `>>3` assumes 8-byte pointer alignment (low 3 bits zero).

Static parse of the file (scratchpad/blend_bhead.py — header `BLENDER17-01v0500` =
LargeBHead8, 32-byte records) finds the exact colliding pair in one Mesh (`ME`) ID's
DATA run:

| block | full 64-bit old | len | (old>>3)&0xFFFFFFFF |
|---|---|---|---|
| A | `0x00007fff7f627380` | 6 | `0xefec4e70` |
| B | `0x00007fff7f627386` | 6 | `0xefec4e70` |

A and B are **distinct** 6-byte blocks **6 bytes apart** (sub-8-byte-aligned, packed
tighter than 8). They differ only in bits 1-2, which `>>3` **discards** → identical
32-bit key → `oldnewmap_insert` sees a duplicate → abort. Native keeps the full
64-bit address (`if constexpr (sizeof(void*)==8) return ptr`), so A≠B → passes.

## Blast radius — measured, not assumed
Data-dependent, and a SILENT corruption risk on files that don't happen to abort.
Static `>>3`-collision scan (scratchpad/scan_collide.py) over the M1.12 corpus:

| file | DATA blocks | >>3 collisions |
|---|---|---|
| animation / armature / collections_instancing / curves_text | 1021-1167 | 0 |
| materials_nodes / modifiers / stress_mixed | 1099-1477 | 0 |
| mesh_dense | 11306 | 0 |
| **structure_type_inference** | 3949 | **1** |

So the corpus 9/9 passed by luck of the writer's address layout (their small DATA
blocks are 8-aligned or spaced >8 apart); this file has two sub-8-aligned adjacent
6-byte blocks. ANY 64-bit `.blend` with sub-8-aligned small DATA blocks colliding
under `>>3` (or, more rarely, genuine bits-35+ collisions on huge files) will
mis-read — aborting if the collision hits a DATA-map key (as here), or SILENTLY
mis-resolving a pointer otherwise.

## Why "uint64 map keys" alone is INSUFFICIENT (the key finding)
The datamap is `Map<const void*, NewAddress>` (readfile.cc:266), keyed by
`bhead->old`; lookups go through `newdataadr(fd, adr)` (readfile.cc:1458 →
`oldnewmap_lookup_and_inc`), where `adr` is a POINTER FIELD read from the
reconstructed struct (e.g. readfile.cc:1921 `newdataadr(fd, lb->first)`). On wasm32
that field is **4 bytes**, already narrowed by `cast_pointer_64_to_32` (`>>3`).
So BOTH the key AND the lookup value are truncated the same way. Widening ONLY the
map key to `uint64_t` would make the 4-byte truncated field lookups (`0xefec4e70`)
fail to match the full 64-bit keys (`0x…7380`/`0x…7386`) → pointers resolve to NULL →
**silent corruption, worse than the abort.** A correct fix must preserve 64-bit
uniqueness on BOTH sides; the 4-byte field cannot carry a 64-bit value.

## Fix options (driver decision — none is a targeted guarded ABI fix)
1. **Pointer interning (surrogate) — the only wasm32 in-place fix.** Assign each
   distinct 64-bit old address a dense unique 32-bit id via a per-FileData
   `Map<uint64_t,uint32_t>`, applied CONSISTENTLY to `bhead->old` (blo_core_bhead) and
   every pointer field (`cast_pointer_64_to_32`, dna_genfile). Collision-free up to
   2^32 distinct addresses. COST/RISK: `cast_pointer_64_to_32` lives in the GENERIC
   `dna_genfile` module with no `FileData`; the interner must be threaded through
   `DNA_struct_reconstruct` (a layering violation coupling DNA↔readfile) or held in
   thread_local global state with a save/restore stack for NESTED library reads. A
   wrong implementation silently corrupts. This exceeds the documented class.
2. **wasm64 — the clean structural fix.** With `sizeof(void*)==8`, `old_ptr_from_
   uint64_ptr` keeps the full 64-bit address and `cast_pointer_64_to_32` is never used
   (64→64 is a plain copy) — the collision cannot occur, exactly like native. GOAL
   already anticipates "wasm32 first; wasm64 later behind a flag"; this bug is a strong
   argument to bring a wasm64 build option forward for `.blend`-heavy workflows.
3. **Do NOT** change `>>3` to low-32 or another shift: still collides (pigeonhole),
   just on a different address distribution — not robust, and the callout forbade
   special-casing.

RECOMMENDATION: wasm64 for correctness (option 2); if a wasm32 fix is mandated,
option 1 needs an ADR (interner ownership, nested-read stack, DNA-module coupling) —
it is not a 0014-style guarded one-file change.

## Verification gate (for whichever fix lands)
- `bl_node_structure_type_inference` suite reads without abort AND round-trips
  correctly (state-dump parity, since silent mis-read is the real risk).
- Corpus 9/9 still exact.
- Re-run all readfile-touching m2b suites (blendfile_*, node_*).
- scratchpad/scan_collide.py over a broad `.blend` set shows 0 residual collisions
  under the chosen scheme.

## Receipts
- Evidence: sandbox/tierb-prep/wasm-bl_node_structure_type_inference.txt.
- Static proof: scratchpad/blend_bhead.py (the A/B pair), scratchpad/scan_collide.py
  (corpus 0-collision, file 1-collision).
- Code: BLO_core_bhead.hh:124 (uint32_from_uint64_ptr), blo_core_bhead.cc:22-30,
  dna_genfile.cc:929 (cast_pointer_64_to_32), readfile.cc:266/1458/1921/2786-2792.
- upstream untouched by this task (only prior patch-0014 dna_genfile change persists).
