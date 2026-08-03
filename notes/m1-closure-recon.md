# M1 closure recon — synthesis (driver, 2026-08-03)

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

Five-agent read-only recon of the remaining tier-(a) surface (blenkernel, depsgraph,
blentranslation, animrig, bmesh link closure, host tools, intern/extern). Conclusions
only; every claim was cited path:line in the recon transcripts.

## The headline: M1's remainder is WIDE, not deep

**There is no minimal bmesh closure.** `bf_bmesh` PRIVATE-links blenkernel; blenkernel is
the whole-core hub (direct links: gpu, draw, nodes, render, sequencer, modifiers, imbuf,
rna, blenloader, animrig, asset_system, blenfont, functions, ikplugin, shader_fx,
simulation; depsgraph adds windowmanager → editors; bf_rna's LIB pulls ~18 bf_editor_*
modules). The bmesh_core_test archive closure ≈ 90% of the combined blender_test's ~200
archives. ~13 core archives are built today; **the gap is ~150+ archives** — porting the
entire non-Python/non-Cycles core. This resizes "port blenkernel+depsgraph" honestly:
those two are necessary, nowhere near sufficient.

**But every hazard scan came back clean.** blenkernel (320 TUs, SRC list 100% static —
zero config-gated sources), depsgraph (66), blentranslation (3 at INTERNATIONAL OFF —
a real identity-passthrough lib, msgfmt NOT needed), animrig (20): ZERO
fenv/mmap/dlopen/fork/socket/statfs/sysctl/LP64-sizeof-assert hits. blenkernel's 10
sizeof static_asserts are all RELATIVE (C++ class vs DNA mirror) — they are canaries for
patch 0002's alignment model, not Class-1 fixes. The intern/extern closure is equally
benign: atomic/profile/mikktspace are INTERFACE header-only; opensubdiv/libmv are stubs;
ghost builds the headless NULL backend (all X11/Wayland/Cocoa hazards compiled out);
curve_fit_nd/rangetree/memutil/sky/nanosvg scan clean. Zero find_package risk — the
full-tree configure already resolves every dep to real lib/wasm archives, no NOTFOUND.
The blenlib error classes (the hard part) do not recur in this surface. Expect a wide
mechanical grind, not another ABI hunt. Runtime alloca note: 6 dynamic-size alloca sites
in blenkernel → raise `-sSTACK_SIZE` on final binaries; not a compile issue.

## Decisions taken (driver)

1. **bmesh gate vehicle: standalone `bmesh_core_test` via `WITH_TESTS_SINGLE_BINARY OFF`**
   (cache/config flip in patches/blender_web.cmake, no upstream edit). At OFF,
   testing.cmake's `blender_add_test_suite_executable` path emits a genuine standalone
   executable inheriting PLATFORM_LINKFLAGS. Rejected: hand-link script (no closure
   savings, repro liability) and combined blender_test (strictly more objects — every
   other module's tests + creator glue). Note: BLI_test existed "for free" because blenlib
   uses the *executable* test variant even at SINGLE_BINARY=ON; bmesh uses the `_lib`
   variant — hence the flip.
2. **Wave order:** current worker finishes bf_blenkernel → bf_depsgraph →
   bf_blentranslation → bf_animrig; then wave 2 flips the flag and drives
   `ninja bmesh_core_test`, letting the dependency graph order the ~150-archive grind.

## Corrections to prior beliefs

- checkpoint-02 said bmesh needs animrig "transitively" — **false at this pin**: zero
  animrig references in bmesh/ (and zero BLT_/translation-macro usage either; its
  blentranslation link is interface-conservative). animrig IS still required — via
  blenkernel's direct link and bf_rna's LIB.
- "GPU/UI stubbed" is loose: the live configure is FULL-TREE with backends OFF (gpu
  compiles its frontend with no GL/Vulkan/Metal backend; epoxy patched out). The gpu/draw/
  editors/windowmanager archives are real compile targets in the closure.

## Host tools (from the audit; exact fixes)

- **makesrna:** wired both halves (patch 0003), NEVER executed — first `ninja
  bf_blenkernel` verifies it (add_dependencies forces bf_rna first;
  blenkernel/CMakeLists.txt:747; RNA_prototypes.hh consumed by 40 blenkernel TUs).
  ABI risk is LOW: makesrna itself runs as wasm32 under node and links the 0002-corrected
  bf_dna, so any offsets it computes are wasm32-native.
- **datatoc (H-5, rc-126):** missing node prefix — `${CMAKE_CROSSCOMPILING_EMULATOR}`
  before `"$<TARGET_FILE:datatoc>"` at build_files/cmake/macros.cmake:1118/:1142/:1184
  (Half-A) + `blender_web_host_tool(datatoc)` after datatoc/CMakeLists.txt:13 (Half-B —
  else PROXY_TO_PTHREAD/no-NODERAWFS breaks it after A). chmod is NOT the fix.
- **shader_tool:** identical two-half defect (macros.cmake:1179 +
  gpu/shader_tool/CMakeLists.txt:51); fires BEFORE datatoc in the gpu path (glsl_to_c).
- **makesdna_test:** latent unwired invocation (makesdna/tests/CMakeLists.txt:19) — trips
  only on full ninja.
- **msgfmt / datatoc_icon:** not needed (INTERNATIONAL OFF; datatoc_icon doesn't exist in
  5.2 — icons go through plain datatoc).
