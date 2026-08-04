<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M1 wave-2 worker P5 — editor spaces / UI

**Result: 26/26 archives GREEN on wasm32, first build, ZERO source fixes.**

Partition P5 (`notes/m1-wave2-partition.md §P5`): interface, screen, util,
animation, asset, id_management, and the 20 `space_*` editors. 444 TU.

## Build

- Command: `harness/buildwrap.sh scripts/ninja-locked.sh -C build-wasm -k 0 <26 targets>`
- Log: `ledger/buildlogs/20260804T015555.log` — `BUILD OK (235 s)`, rc=0.
- Evidence: **444 `Building CXX object` lines** across the P5 editor dirs (exactly
  the partition-plan TU count) + **26 `Linking CXX static library` lines**, 0
  `error:` / 0 `FAILED:`. All 26 `libbf_editor_*.a` on disk, non-trivial
  (interface 4.17 MB, space_node 2.53 MB, space_spreadsheet 2.51 MB,
  space_view3d 1.83 MB … id_management 4.99 KB, space_api 10.2 KB).

## Fixes / patches

- **None.** Patch range 0180–0199 is UNUSED. `upstream/` pristine in all P5
  source dirs (`git -C upstream status` clean for interface/screen/util/
  animation/asset/id_management/space_*).
- No `#ifdef __EMSCRIPTEN__` guards required anywhere in P5.

## ED_*.hh (P4-owned shared headers)

- **No change needed.** P5 compiles clean against the `editors/include/ED_*.hh`
  as they stand in the applied series. No shared-header seam hit this lane.

## Blockers

- None.

## Interpretation

Confirms the recon prediction that the editor lanes are a "wide mechanical grind,
low per-lib risk." The ILP32 / libc-gap error classes (patterns 1–2 in
`notes/porting-patterns.md`) do not surface here: a pre-build `rg` over all P5
dirs found **0** `fenv.h`/`FE_DIVBYZERO`, **0** `statfs`, **0** `size_t(1)<<32`.
The two `static_assert(sizeof …)` sites in P5 (interface_draw.cc
`WaveformColorVertex==24`, sequencer_quads_batch.cc `ColorVertex==12`) are
pointer-free POD vertex formats — ABI-stable across wasm32, and indeed compiled
clean. All ILP32/DNA/RNA/libc corrections these higher-level TUs depend on were
already absorbed upstream of this lane by patches 0001–0008 (makesdna align,
blenlib libc gaps, blenkernel ILP32) and consumed transitively via BLI/BKE/DNA/
RNA headers.
