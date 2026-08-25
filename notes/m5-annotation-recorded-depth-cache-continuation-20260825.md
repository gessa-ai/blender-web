<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 recorded annotation depth-cache continuation — 2026-08-25

## Outcome

Commit `a9074d2` and patch 0267 remove the final synchronous depth override from
`GPENCIL_OT_annotate`. The recorded-stroke `exec` callback snapshots exactly the four RNA fields
that stock replay consumes (`mouse`, `pressure`, `time`, and `is_start`) into operator-owned
storage. An explicit cursor advances only after a point is applied, so a pending browser readback
cannot retain borrowed RNA iteration state or repeat a point.

Replay preserves Blender's boundary order. Before a new `is_start` point, it obtains the cache
needed to finish the preceding stroke, finishes that stroke, initializes the next one, and resumes
the same unconsumed point. The final stroke likewise obtains its required cache before cleanup.
Projected draw points and depth-aware eraser strokes use the existing owned full-viewport cache;
non-depth execution stays direct. A ready request completes on the original `exec` stack. Only a
genuinely pending request installs the bounded annotation modal timer, which swallows unrelated
events while the owned snapshot is authoritative and lets Escape cancel.

Context or matrix drift, backend failure, timeout, and external cancellation converge on the same
owned request, timer, cache, snapshot, and stroke cleanup. The interactive continuation from patch
0266 now uses the same truthfully named ownership mode, and all annotation
`ED_view3d_depth_override` call sites have a zero residual census.

## Source and contract evidence

- The pinned Blender oracle reports a background-only `poll=false`, default draw mode,
  `wait_for_input=true`, and the exact four consumed stroke fields. The 0266 predecessor fails the
  new source contract before evidence allocation because recorded owner state is absent
  (`20260825T020713-709023`).
- Focused post-commit receipt `20260825T022323-723190` passes 13 contracts and 31 cases
  byte-for-byte under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 606-byte output is
  `sha256:a38c84d33bd6d11a3e7ca4c3bc71f66debb1bee607a083b81b813eb129604d51`; the
  production postimage is
  `sha256:7efd0b77090662d87f727598e9ee46d18c91f31a48859ad9a7e1eef89c811c57`.
  Seventeen ownership, snapshot, cursor, cache, boundary, settlement, and cancellation mutations
  fail closed.
- Aggregate post-commit receipt `20260825T022342-723491` passes the complete owned-readback census
  with 40 fail-closed mutations and byte-identical 627-byte native/Wasm output at
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`.
- Exact native and wasm product-graph translation-unit compiles pass in
  `20260825T021116-711582`. Numbered patch 0267 reverses and reapplies its one-file postimage at
  `sha256:860d7a3feb0e7d505316d0c9511409b6290593d1f6ddad85f19a324f1b895e1f`.

## Integration evidence

- Clean-pin freeze `20260825T021500-714995` reproduces the 20,258-entry source manifest with zero
  ignored paths. `PREVIEW_SNAPSHOT.patch` is 2,150,490 bytes at
  `sha256:eb82d2713d71feb73da194e7b644527f3204b9caccb3051e5f6174ab9553f12f`; both
  manifests are
  `sha256:5c0827e8508cb2096a7d0774c6494538e51e8b861ba4875b250b93241d9c47c2`.
  Canonical-only replay binds 288 paths (`20260825T021737-717951`). The optional diagnostic
  numbered-history replay still stops at the previously documented patch-0016 history defect,
  before patch 0267; the focused reverse/forward proof is green.
- The immutable-upstream windowed graph compiles the translation unit from the frozen overlay,
  relinks `blender_browser`, and ends exact locked no-work (`20260825T021827-718475` and
  `20260825T021915-719635`). Strict OFF preflight `20260825T022152-721519` binds 657,928-byte
  JavaScript, 118,976,779-byte Wasm, and 167,143,248-byte data artifacts.
- Repository-wide REUSE 6.2.0 is green for 2,440/2,440 files
  (`20260825T022621-725548`).
- Required M5 remains honestly red only at the absent
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary
  (`20260825T022640-725740`). Pinned-container regression `20260825T022648-725885` restores M0
  6/6 green and leaves M1–M8 at their existing strict-receipt, APPLY, browser, product, run-label,
  and release boundaries.

Grease Pencil surface placement, object axis-target placement, particle edit, and WM window
capture remain explicit synchronous residuals. Live C1/M5 acceptance remains separately deferred
by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn
rejected by Dawn). This work creates no adapter, device, browser profile, split product, or live
receipt, and changes no result promotion, dependency decision, tolerance, golden, blacklist, or
milestone promise. dzn and Windows were not attempted, and WSL was not restarted.
