<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M1 wave-2 P4 — editor-tools partition (result)

Lane P4 of the wave-2 bmesh_core_test closure: the editor-tools partition
(sculpt_paint / transform / mesh / object / armature / curves / curve / uvedit /
physics / grease_pencil / gpencil_legacy + tool libs). 22 archives, 430 TU.

## Result: 22/22 GREEN, zero fixes

All 22 P4 archives compiled to wasm32 on the **first pass**, in one locked ninja
run (`ledger/buildlogs/20260804T015541.log`, 521 s). Re-run reported
`BUILD OK (0 s)` — no work outstanding, so the build is genuinely complete, not a
phantom no-op. Toolchain confirmed emsdk Emscripten
(`build-wasm/CMakeCache.txt` → `CMAKE_TOOLCHAIN_FILE = .../Emscripten.cmake`,
`CMAKE_CROSSCOMPILING_EMULATOR = tools/emsdk/node`), the same tree that produced
the prior verified-wasm archives (bf_dna/bf_blenlib/bf_blenkernel).

| archive | bytes |
|---|---|
| bf_editor_sculpt_paint  | 16328956 |
| bf_editor_grease_pencil |  5951092 |
| bf_editor_mesh          |  2914006 |
| bf_editor_object        |  2553960 |
| bf_editor_curves        |  2179142 |
| bf_editor_transform     |  2159198 |
| bf_editor_armature      |  1063352 |
| bf_editor_pointcloud    |  1000842 |
| bf_editor_uvedit        |   963150 |
| bf_editor_geometry      |   555652 |
| bf_editor_curve         |   456080 |
| bf_editor_render        |   316344 |
| bf_editor_physics       |   273066 |
| bf_editor_mask          |   154740 |
| bf_editor_gizmo_library |   128758 |
| bf_editor_gpencil_legacy |   93126 |
| bf_editor_io            |    70904 |
| bf_editor_undo          |    61154 |
| bf_editor_metaball      |    58676 |
| bf_editor_lattice       |    55222 |
| bf_editor_scene         |    17478 |
| bf_editor_sound         |    11838 |

## Error-class table

| class | count |
|---|---|
| (any)  | 0 |

Zero errors of any class. The recon's prediction for the editor lanes — "wide
mechanical grind, zero fenv/mmap/dlopen/LP64 hits" — held exactly. The editors
consume blenkernel/bmesh/DNA/RNA through headers only; every ILP32 /
libc-gap / host-tool hazard was already resolved upstream of this lane by
patches 0002–0008 (DNA wasm32 alignment, blenlib ILP32 asserts, fenv/statfs,
host-tool codegen). Nothing in the editor-tools surface tripped a new class.

## Patches

**None.** Patch range 0160–0179 unused — no source fix was required in any P4
dir. `git -C upstream status` for all 22 P4 source dirs + `editors/include`
is empty; `upstream/` stays pristine across the P4 surface.

## Shared header (`editors/include/ED_*.hh`) changes

**None.** P4 is the wave's sole owner of `editors/include/ED_*.hh`, but no fix
there was needed for any P4 target, and P5 (already green, 26/26) requested none.
The shared-header seam stayed untouched.

## Verification

- `harness/buildwrap.sh scripts/ninja-locked.sh -C build-wasm <22 targets>` → BUILD OK 521 s.
- Idempotent re-run → BUILD OK 0 s (complete, up to date).
- All 22 `libbf_editor_*.a` present on disk with the sizes above.
- `git -C upstream status --short` over all P4 dirs + include: empty (pristine).
</content>
