<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M1 wave-2 partition plan — bmesh_core_test closure

Read-only analysis of `build-wasm/build.ninja` (15 MB, generated) + filesystem.
No builds run. Fan-out target: after `bf_blenkernel` (wave-1) goes green, the
driver flips `WITH_TESTS_SINGLE_BINARY OFF` and drives `ninja bmesh_core_test`;
this plan pre-partitions the library closure so workers can start the moment
the flag flips.

## Closure sizing (authoritative, from the ninja link graph)

- The production closure was taken from the **`blender_test.js` executable link
  line** (`build-wasm/build.ninja:68865`), which enumerates every repo archive
  bf_bmesh transitively pulls: **107 production archives** (excluding gtest/gmock
  glog/gflags/testing_main + the per-module `*_tests.a`).
- Of those, **17 are already built** (all codegen + low-level leaves):
  `bf_rna, bf_dna, bf_blenlib, bf_gpu_shaders, bf_draw_shaders,
  bf_compositor_shaders, bf_imbuf_opencolorio_shaders,
  bf_nodes_{compositor,functions,geometry}_generated, bf_editor_datafiles,
  bf_intern_{guardedalloc,eigen,libc_compat,clog}, extern_{xxhash,wcwidth}`.
- **Work set = 90 unbuilt production archives, 2147 TU** (`.o` inputs counted
  from each archive's `CXX_STATIC_LIBRARY_LINKER` rule). Every one has a direct
  ninja **phony alias** = archive name minus `lib`/`.a` (verified all 90), so a
  worker addresses a lib as `ninja -C build-wasm <target>`.

## Key finding — the archives compile-INDEPENDENTLY

Object-compile rules carry **no order-only dep on any sibling `lib/*.a`**; they
depend only on `cmake_object_order_depends_target_bf_<self>`, which for both the
hub (`bf_blenkernel`) and a leaf consumer (`bf_editor_mesh`) chains to the SAME
already-built codegen targets (`bf_dna`, `bf_dna_defaults`, the four `*_shaders`,
`bf_editor_datafiles`, `bf_nodes_*_generated`, `bf_rna`). A `.cc` in editors
needs blenkernel's **source headers** (`upstream/.../BKE_*.hh`, always present)
and the **generated headers** (`RNA_prototypes.hh`, `dna_type_offsets.h` — both
confirmed on disk), **not** `libbf_blenkernel.a`. Inter-archive dependency is a
**link-time-only** concern, resolved by the driver's final `ninja
bmesh_core_test`. Therefore all 90 archives can compile fully in parallel;
partitions need only be **disjoint by source directory** (fix-edit isolation)
and **TU-balanced**.

## Serialization — what MUST precede the fan-out

**Nothing in the work set.** All codegen chokepoints are already built (RNA via
makesrna — forced first by `bf_blenkernel`'s add_dependencies,
`upstream/source/blender/blenkernel/CMakeLists.txt:747`; DNA; shader→C via the
now-native `shader_tool`/`datatoc` per ADR-002; node `*_generated`;
`editor_datafiles`). No work-set archive is a compile prerequisite of another.

Two **cross-partition hazards** to name (not pre-fan-out blockers, but they
break the disjointness guarantee if they fire):

1. **Any DNA/RNA-regenerating fix invalidates ALL partitions.** `dna_type_offsets.h`
   / `RNA_prototypes.hh` are order-only deps of every TU; a patch that touches a
   DNA struct or a makesrna input re-runs codegen and forces a full-tree
   recompile. Recon judged this unlikely on this surface (blenkernel's 10 sizeof
   static_asserts are **canaries for patch 0002's alignment model, not per-TU
   fixes**). If one is needed it goes through the driver and every worker
   re-syncs — do not apply it inside a partition lane.
2. **Shared patch series + shared `editors/include/`.** Workers share ONE applied
   patch series and ONE build tree. Disjoint source dirs ⇒ disjoint patch hunks,
   **but the numbered `patches/NNNN-*.patch` filename space is shared** — reserve
   a range per worker (P1 0100–0119, P2 0120–0139, P3 0140–0159, P4 0160–0179,
   P5 0180–0199) so files never collide and the driver linearizes at merge.
   Additionally, **all editors `#include "ED_*.hh"` from `editors/include/`**
   (spans P4+P5): a fix there is the one shared-header seam — first worker to
   need it owns the hunk, the other rebases. `upstream/` stays pristine (fixes in
   `patches/` only).

## Partition (5 workers, disjoint by source dir, TU-balanced)

| # | partition | libs | TU | risk | build order (dependency-first, advisory — surfaces shared-header breaks early) |
|---|---|---|---|---|---|
| **P1** | **gpu / draw / window / media** — *strongest worker* | 19 | **341** | **HIGH (novel)** | gpu → draw → windowmanager → intern_ghost → render → blenfont → imbuf → imbuf_opencolorio → imbuf_{movie,openimageio,openexr} → {intern_sky,opensubdiv,libmv,memutil,extern_rangetree,nanosvg,curve_fit_nd,ikplugin} |
| **P2** | **kernel hub** — blenkernel anchor | 10 | **453** | MED | blenkernel → depsgraph → animrig → blenloader_core → blenloader → functions → asset_system → simulation → shader_fx → blentranslation |
| **P3** | **mesh / nodes / media pipeline** | 13 | **479** | LOW-MED | bmesh → geometry → functions?(P2) → nodes → nodes_{geometry,texture,shader,composite,function} → modifiers → compositor → sequencer → io_common → io_csv |
| **P4** | **editor tools** (modeling/anim/paint) | 22 | **430** | LOW (wide) | sculpt_paint → transform → mesh → object → armature → curves → curve → uvedit → physics → grease_pencil → gpencil_legacy → {gizmo_library,mask,pointcloud,geometry,lattice,metaball,io,render,scene,sound,undo} |
| **P5** | **editor spaces / UI** | 26 | **444** | LOW (wide) | interface → screen → space_outliner → space_view3d → space_node → space_file → space_sequencer → asset → animation → space_clip → util → {space_text,spreadsheet,graph,nla,image,action,info,userpref,buttons,script,console,topbar,statusbar,api} → id_management |

TU total = 341+453+479+430+444 = **2147** (100% coverage, zero overlap; verified).

**Why P1 is the low-TU strong-worker lane:** it carries every *novel* surface —
`gpu` compiling its frontend with **all backends OFF** (the recon's single most
novel item; epoxy patched out, no GL/Vulkan/Metal), `draw` (draw-manager, couples
to gpu headers), `intern_ghost` (headless NULL backend, X11/Wayland/Cocoa
compiled out), and the `imbuf` codec seam (OIIO/OpenEXR/OCIO/freetype external-dep
integration). Cycles here go to fix investigation, not throughput — so it is
intentionally the lightest lane. The tiny stubs/leaves (opensubdiv, libmv,
rangetree, nanosvg, sky, memutil, curve_fit_nd, ikplugin — all scanned benign in
recon) ride along as zero-effort filler. **P2** owns the hub: its risk is the
patch-0002 alignment canaries (blenkernel sizeof asserts) + `blenloader`
(readfile, load-bearing for M1.12). **P3/P4/P5** are the wide mechanical grind the
recon predicted (zero fenv/mmap/dlopen/LP64 hits) — low per-lib risk, bounded
only by TU volume; editors split P4/P5 along the tool-vs-space seam to keep
`editors/include` collisions rare.

### Ninja target lists (paste into each worker's `harness/buildwrap.sh` invocation)

```
# P1  (ninja -C build-wasm ...)
bf_gpu bf_draw bf_windowmanager bf_intern_ghost bf_blenfont bf_render \
  bf_imbuf bf_imbuf_opencolorio bf_imbuf_movie bf_imbuf_openimageio bf_imbuf_openexr \
  bf_intern_sky bf_intern_opensubdiv bf_intern_libmv bf_intern_memutil \
  extern_rangetree extern_nanosvg extern_curve_fit_nd bf_ikplugin

# P2
bf_blenkernel bf_depsgraph bf_animrig bf_blentranslation bf_blenloader \
  bf_blenloader_core bf_functions bf_simulation bf_shader_fx bf_asset_system

# P3
bf_bmesh bf_modifiers bf_geometry bf_nodes bf_nodes_geometry bf_nodes_texture \
  bf_nodes_shader bf_nodes_composite bf_nodes_function bf_io_common bf_io_csv \
  bf_compositor bf_sequencer

# P4
bf_editor_sculpt_paint bf_editor_transform bf_editor_mesh bf_editor_object \
  bf_editor_armature bf_editor_curves bf_editor_curve bf_editor_uvedit \
  bf_editor_physics bf_editor_grease_pencil bf_editor_gpencil_legacy \
  bf_editor_lattice bf_editor_metaball bf_editor_geometry bf_editor_pointcloud \
  bf_editor_mask bf_editor_gizmo_library bf_editor_io bf_editor_render \
  bf_editor_scene bf_editor_sound bf_editor_undo

# P5
bf_editor_interface bf_editor_space_outliner bf_editor_space_view3d \
  bf_editor_space_node bf_editor_space_file bf_editor_space_sequencer \
  bf_editor_asset bf_editor_animation bf_editor_space_clip bf_editor_screen \
  bf_editor_space_text bf_editor_space_spreadsheet bf_editor_space_graph \
  bf_editor_util bf_editor_space_nla bf_editor_space_image bf_editor_space_action \
  bf_editor_space_info bf_editor_space_userpref bf_editor_space_buttons \
  bf_editor_space_script bf_editor_space_console bf_editor_space_topbar \
  bf_editor_space_statusbar bf_editor_space_api bf_editor_id_management
```

After all 90 are green the driver runs the single serialized step:
`ninja -C build-wasm bmesh_core_test` (post `WITH_TESTS_SINGLE_BINARY OFF`
reconfigure; standalone-exe path per `blender_add_test_suite_executable` in
`upstream/tests/CMakeLists.txt` testing helpers) — the closure link + the only
place `bf_bmesh`↔hub link order matters.

## Notes / caveats
- Balance is **risk-weighted, not equal-TU**: P1 is deliberately light (341)
  because its libs are the fix-magnets; the mechanical lanes sit at 430–479.
- `bf_functions` appears in the P3 advisory order only as an *include* source
  for nodes; the **archive is owned by P2** — do not build it from P3.
- These are archives only; the 24 `*_tests.a` / `*_test_util.a` and other
  modules' standalone test exes are **out of scope** for the bmesh gate.
- If wave-1 also lands `bf_depsgraph`/`bf_animrig`/`bf_blentranslation` green
  before fan-out (per recon wave order), drop them from P2 and rebalance P2's
  remainder (~277 TU) by pulling `bf_render`/`bf_blenfont` from P1.
