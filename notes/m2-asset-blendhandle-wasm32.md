<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M2b — blendhandle asset read on wasm32 ("No asset found"): patch 0031

Date: 2026-08-05. Owner: ABI specialist (patch-0014 family). Root cause of a4302cd's bug2.

## Root cause (the divergence full-readfile 0014 didn't cover)
`blo_bhead_id_asset_data_address()` (readfile.cc:800) reads the ID's `asset_data` field
RAW from the file block: `*reinterpret_cast<AssetMetaData**>(POINTER_OFFSET(bhead,
sizeof(*bhead)+fd->id_asset_data_offset))`, where `id_asset_data_offset` is the FILE's
SDNA offset (`DNA_struct_member_offset_by_name_with_alias(fd->filesdna,"ID","AssetMetaData",
"*asset_data")`). On wasm32 reading a 64-bit `.blend`, that field is an **8-byte** file
pointer, but the raw read takes only 4 bytes = the **low 32 bits UNSHIFTED**. The runtime
data map is keyed by the 64->32 **truncated** address (`old_ptr_from_uint64_ptr` /
`bhead->old`, i.e. `uint32_from_uint64_ptr`'s `>>3`) — which is exactly how the FULL read
path lowers this same field (`cast_pointer_64_to_32`, `>>3`). Unshifted-low-32 never
matches the `>>3` key -> `BLO_read_struct(&reader, AssetMetaData, r_asset_data)` ->
`newdataadr` returns NULL -> `AssetMetaData` unset -> `FILE_TYPE_ASSET` lost ->
`FLF_ASSETS_ONLY` filters everything -> "No asset found". The full path never hits this
because it reconstructs the ID struct (`read_struct`/`DNA_struct_reconstruct`), applying
the `>>3` consistently. The blendhandle partial reader
(`BLO_blendhandle_get_datablock_info` -> `blo_read_asset_data_block`) reads the field raw.

## Fix (patch 0031, single source of truth — no parallel model, no AssetMetaData special-case)
`#ifdef __EMSCRIPTEN__`, and only for 64-bit files (`!FD_FLAGS_FILE_POINTSIZE_IS_4`): read
the full 8-byte file pointer and apply the SAME `uint32_from_uint64_ptr` the reader uses
everywhere, so the resolved old-address matches the data-map key. Native and the 32-bit-file
case fall through to the original expression -> byte-identical.

## Verification (relinked wasm blender; caches cleared per run)
- **bl_brush (brush_asset_test.py, the "No asset found" suite): PASS** (Ran 4 tests; OK).
  0 "No asset found" across ALL three essentials suites now.
- **Regression exact**: corpus 9/9 ALL_PASS (byte-exact, DETERMINISM_PASS); versioning
  10/10 PASS (DIVERGENCE=0, LOAD_FAIL=0, 2 BE refused == oracle).
- **Detector 0018 unchanged**: bl_node_structure_type_inference still refuses with the
  ADR-004 message (old `same old address` abort = 0). [Note: 0018 had been DROPPED from the
  shared wave tree by a restore; re-applied the committed patch to verify — see report.]
- Native byte-identical (guarded); patch reversible == working delta.

## Residual essentials failures — SEPARATE divergences (NOT the asset family, NOT 0031)
Both pass on the native oracle; both fail wasm-only for non-asset reasons (No-asset-found=0):
- **object_edit** `test_auto_smooth_detection`: `AssertionError: 4 != 1` (len(ob.modifiers)).
  A modifier/geometry-nodes (auto-smooth "Smooth by Angle") divergence on wasm.
- **bl_sculpt_brushes**: `BLI_assert multires_reshape_util.cc:118 context_init_common(),
  'reshape_context->subdiv != nullptr'` -> Aborted. A multires-reshape / OpenSubdiv
  divergence (subdiv null — opensubdiv likely stubbed/absent on wasm).
Both also emit a benign `ModuleNotFoundError: No module named '_multiprocessing'` at
addon-register (bl_pkg remote-asset-library) — Python module gap, integration lane. These
need their own lanes (modifier/geo-nodes; multires/opensubdiv), out of scope for the 64->32
asset fix.

## Poisoned-cache trap + indexer note (task 3)
Stale asset-library index files at `~/Library/Caches/Blender/asset-library-indices/`
(macOS; `~/.cache/blender/...` on Linux) cache an EMPTY result from a failed read and mask
the fix on rerun. Cleared before every verification run above.
**Upstream-worthy (reported, NOT fixed — not a one-line guarded change):** the asset indexer
should INVALIDATE-ON-ERROR — do not persist an `.index.json` when the underlying blendhandle
read failed/returned no resolvable assets, so a transient read failure does not poison future
scans. It is not a single guarded line: it needs to distinguish "file genuinely has no
assets" from "read failed", i.e. thread a read-status out of
`filelist_readjob_list_lib`/`BLO_blendhandle_get_datablock_info` to the index writer. Flag
for an upstream PR / its own task.
