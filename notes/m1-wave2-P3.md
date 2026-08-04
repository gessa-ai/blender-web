<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M1 wave-2 worker P3 — mesh / nodes / compositor / sequencer / io

Partition P3 of `notes/m1-wave2-partition.md`: bmesh, geometry, nodes (+node
subdir libs), modifiers, compositor, sequencer, io_common, io_csv.

## Result: 13/13 GREEN — 479/479 TU, ZERO source fixes

Every target compiled to a green wasm32 archive with **no `#ifdef __EMSCRIPTEN__`
guards and no patches** (confirmed: `git -C upstream diff` over all eight P3
source dirs is empty). Single `ninja -k 0` run over all 13 targets, 199 s,
479 TUs, 0 errors / 0 FAILED. buildlog `20260804T015849`.

This confirms the recon's prediction for the mechanical lanes (§partition
"P3/P4/P5 are the wide mechanical grind... zero fenv/mmap/dlopen/LP64 hits").
All wasm32 portability work these libs depend on was already absorbed upstream of
P3 by patch series 0001–0008 (platform_wasm `-funsigned-char`/`-fno-strict-aliasing`,
makesdna wasm32 alignment, blenlib sizeof/libc-gap fixes, native host-tool codegen,
blenkernel ILP32 widen). With those in place the mesh/nodes/compositor/sequencer/io
source is byte-identical-portable.

## Archives (build-wasm/lib/)

| archive | bytes |
|---|---|
| libbf_bmesh.a | 3,551,016 |
| libbf_geometry.a | 7,836,438 |
| libbf_nodes.a | 6,547,650 |
| libbf_nodes_geometry.a | 21,039,092 |
| libbf_nodes_texture.a | 205,946 |
| libbf_nodes_shader.a | 3,726,644 |
| libbf_nodes_composite.a | 4,955,414 |
| libbf_nodes_function.a | 5,070,934 |
| libbf_modifiers.a | 6,187,790 |
| libbf_compositor.a | 4,387,326 |
| libbf_sequencer.a | 1,713,600 |
| libbf_io_common.a | 343,174 |
| libbf_io_csv.a | 150,696 |

## Error-class table

| class | count | notes |
|---|---|---|
| Class 1 (ILP32 sizeof/shift) | 0 | none surfaced in P3 source |
| Class 2 (libc gaps: fenv/statfs/char) | 0 | already handled by platform_wasm flags |
| Class 3 (host codegen tools) | 0 | node_*_generated + shaders prebuilt by wave-1/driver |
| other | 0 | — |

## Blockers

None. Partition fully green.

## Patches created

None — zero source fixes required. Reserved range 0140–0159 left unused.

## Notes / caveats
- `bf_functions` is NOT in P3 (P2-owned per partition §caveats); it appears only
  as an include source for nodes and was already green from wave-1.
- All four generated node archives (`bf_nodes_{compositor,functions,geometry}_generated`)
  and `bf_compositor_shaders` were already on disk from the driver's codegen step
  before P3 started; P3 only compiled the hand-written TUs.
