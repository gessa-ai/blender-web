<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T7 shader-rewrite integrated Linux reconciliation — 2026-08-21

## Outcome

The canonical in-tree WebGPU shader frontend now has a device-free native/wasm32 contract for
the source transformations that run after Blender's shader preprocessor. The unchanged source
oracle exposed one real defect: `rewrite_isnan_isinf()` treated longer identifiers such as
`myisnan(` and `myisinf(` as target builtins and injected eight unused helper overloads. Patch
0151 makes the fast-path detector require the builtin's identifier boundary, preserving unrelated
source and shader-cache inputs byte-for-byte.

The expanded contract covers eight frontend families and 179 cases. Its four new families prove
nested texel-buffer helper inlining, seven integer-sampler call rewrites plus two controls, all
sampled/storage operations in the physical 1D-array lowering (including eight atomic names), and
finite-builtin lowering with longer-identifier controls. It includes the shipping
`wgpu_shader.cc` translation unit directly; no helper implementation is copied into the test.

## Evidence

- The pre-fix native oracle stopped exactly at `finite-builtin rewrite matched longer
  identifiers` (`20260821T222422-666444`).
- Final root and descendant-CWD runs build through the locked native and Wasm graphs and emit the
  same 581 bytes, SHA-256 `89f686740b17`, against source digest `f4a352811c4f`, Dawn
  `36cf1fae`, emcc 6.0.5, and Node 22.16.0 (`20260821T223524-677846`,
  `20260821T223546-678506`). Wrong Dawn and Node identities allocate no evidence
  (`20260821T222832-670307`).
- The canonical freezer and replayer prove the same 257 paths and 20,258 manifest entries. The
  new 1,531,126-byte authority is SHA-256 `22621d7ee011`; the byte-identical live/replay manifest
  is SHA-256 `1d0c7f68521b` (`20260821T222714-668392`, `20260821T222806-669737`).
- The windowed product rebuilt only its affected edges, then ended exact locked-Ninja no-work;
  its developer OFF-mode preflight is green (`20260821T222920-671156`,
  `20260821T223003-671493`, `20260821T223012-671586`). Exact REUSE 6.2.0 is green at
  1,992/1,992 files (`20260821T223257-674963`).

## Boundary

This is deterministic shader-source translation coverage only. The contract creates no WebGPU
instance, adapter, device, shader module, pipeline, profile, or receipt. Required M3 remains red
for the absent complete strict candidate, and group-scoped regression keeps M0 6/6 green while
M1-M8 retain the existing strict-manifest, APPLY/artifact, browser, run-label, and s7 hardware
boundaries (`20260821T223040-672635`, `20260821T223056-672776`).
