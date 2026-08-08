<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 28b TAKE 3 (gpu-backend worker) — UI region interaction (defect 2): the menu/context/toolbar backgrounds were the un-uploaded-IBO class; ALREADY FIXED by patch 0114. Load-store (0110) consume semantics verified sound.

Same rig as notes/gpu-r28-solid-composite.md. This note settles defect 2 (context menus /
toolbar backgrounds / region blanking under interaction) and the load-store question the
lane was dispatched to re-examine.

## The A/B evidence PRE-DATES 0114 — it captured the broken state, not a load-store fault

The banked A/B PNGs (`platform_web/shell/evidence/m4-r28b-baseline-*` vs
`m4-r28b-ab-alwaysload-*`) are timestamped **Aug 7 17:53**, BEFORE patch 0114
(`cb5524f`, 18:39) landed. In them the File-menu dropdown + right-click context menu render
their TEXT/icons but have NO panel background — the grid + cube outline show straight
through the menu. Critically, the baseline (one-shot consume) and always-LOAD variants are
NEAR BYTE-IDENTICAL for every interaction (file sizes within tens of bytes), i.e. toggling
the load-store consume changed nothing — the defect was NOT the 0110 consume semantics. It
was "something else," exactly as the driver's dispatch suspected.

## Root cause of the transparent menu backgrounds = the same un-uploaded IBO 0114 fixed

A Blender menu/context-menu backdrop is a non-instanced INDEXED roundbox batch
(`GPU_SHADER_2D_WIDGET_BASE`, the `UI_draw_roundbox` filled shape); glyph text is a separate
(non-indexed / textured-quad) path. Pre-0114, `WGPUBatch::draw` skipped `DrawIndexed` for any
batch whose IBO had not been force-uploaded (the exact class 0114 fixed for the nav-gizmo /
instanced widgets) — so the filled panel vanished while the text drew: precisely the
"transparent menu background" the A/B PNGs show. 0114 (`elem->upload_data()` before bind in
both draw paths) uploads the IBO, so the filled roundbox draws.

## VERDICT (verified live on the current HEAD opt build, patch 0114/0115 in)

Scripted-interaction boot (`?gate=1280x720`, 60s settle, then click File @ top-left,
right-click viewport center; captures `opt-02-file-menu.png` / `opt-03-context-menu.png`):

- **File-menu dropdown: SOLID dark panel** — New/Open/Save/… on an opaque background with a
  drop shadow, item icons, and separators. PASS.
- **Right-click context menu: SOLID dark panel** — Object header + Shade Smooth/Flat/… with a
  hover highlight, on an opaque background. PASS.
- Chrome UPRIGHT (File/Edit at TOP, Timeline at BOTTOM, nav-gizmo ball, native panel order) —
  patch 0115. PASS.

So defect 2 needs NO new code; it was resolved by the landed 0114. This round adds no
load-store change.

## Load-store (patch 0110) one-shot consume — verified SOUND for the shared depth

The workbench gbuffer depth is SHARED with the overlay framebuffers (`[bw-r28c-fb]`:
`Opaque.Gbuffer`, `overlay_line_fb`, `&dfbl->overlay_fb` all carry the same depth ptr). This
is the exact place a mis-timed one-shot CLEAR could wipe once-drawn content. The ordered
depth trace (`[bw-r28c-seq]`, begin_load_pass + submit_clear interleaved) shows the consume
is correct:

    #SC1 &dfbl->default_fb  D=CLEAR cv=1.0     (clears shared depth)
    #SC4 Clear Main         D=CLEAR cv=1.0     (clears shared depth again, frame start)
    #1   Opaque.Gbuffer     D=load  cv=1.0     (prepass loads the cleared 1.0, writes geometry)
    #SC5 overlay_line_fb    D=load  (color-only submit_clear, depthbit=0 — depth untouched)
    #3.. overlay_line_fb    D=load             (overlays depth-test against the shared depth)

No pass wrongly re-CLEARs the shared depth after the prepass; color-only clears keep
`depthbit=0`. So 0110's consume + the ctor LOAD default hold for the shared-depth case — the
missing workbench solid is NOT a load-store regression (it is Bug B, the opaque-group prepass
producing no geometry; notes/gpu-r28-solid-composite.md).

## Follow-ups
1. Interactive verification here is capture-based on the opt tree; the driver's parity rig
   (`sandbox/m4-fullscreen-parity`) is the golden-diff path once Bug B lands and the viewport
   region collapses.
2. No load-store change this round — do NOT re-open 0110 for the solid-cube symptom.
