<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 file-format implementation deferral — 2026-08-26

## Outcome

Commit `515630b` keeps the measured registration/UI closure for Blender's five enabled
file-format add-ons in Stage 0 and moves their 140 lazy import/export implementation modules to
Stage 1. The boundary covers BVH, SVG, UV Layout, FBX, and glTF. This is staged loading, not a
feature cut: the add-ons remain registered at boot, and the production Stage-1 loader restores
their exact source before the M7 operator lane runs.

The optimized CAPTURE Wasm is unchanged: `.wasm.orig` remains 119,142,918 bytes at
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.

## Measured boot closure

The pinned native Blender 5.2 factory startup and the current real windowed CAPTURE product agree
on eight boot files across these add-ons: each top-level `__init__.py`, glTF's
`blender/__init__.py`, and glTF's two registration-time UI/material helpers. The windowed census
waited ten seconds after WM startup and still loaded none of the 140 deferred implementations.

- Native closure: `ledger/buildlogs/20260826T112823-744625.log`.
- Windowed ten-second closure: `ledger/buildlogs/20260826T112750-744124.log`.
- The fail-first classifier caught `io_anim_bvh/import_bvh.py` incorrectly remaining in Stage 0:
  `ledger/buildlogs/20260826T113051-746480.log`.
- The final 51-classification packer contract is green:
  `ledger/buildlogs/20260826T113314-747993.log`.

## Exact size result

Against the unchanged 167,143,248-byte CAPTURE data payload, the partition becomes:

| bucket | files | raw bytes |
|---|---:|---:|
| Stage 0 keep | 1,369 | 20,673,511 |
| Stage 1 defer | 2,072 | 144,682,014 |
| drop | 1 | 1,787,723 |

The new boundary removes 1,924,052 raw bytes from Stage 0. With pinned Node 22.16.0 Brotli-q11,
Stage-0 data falls from 4,028,170 to **3,748,720 bytes** and rewritten glue falls from 81,589 to
**80,933 bytes**. With the unchanged 12,418,419-byte provisional split primary, projected
critical wire falls from 16,528,178 to **16,248,072 bytes**, a **280,106-byte reduction**. It
remains honestly **1,248,072 bytes over** LAUNCH.md's 15,000,000-byte bar.

Canonical packing is recorded in `ledger/buildlogs/20260826T113806-751626.log`; exact q11 sizes
are in `ledger/buildlogs/20260826T113957-753480.log`.

## Runtime and release evidence

- A real fallback-browser monolith/candidate A/B preserves Blender version, eight enabled add-ons,
  four editor areas, Camera/Cube/Light, WM progress, and trusted input. The candidate proves seven
  representative zero-length implementation placeholders while all eight boot files remain
  byte-identical. Stage 1 restores 2,072 files / 144,682,014 bytes, imports all seven
  implementations byte-exactly, and completes real glTF export plus import with zero page or
  serious-console errors (`ledger/buildlogs/20260826T113821-751705.log`).
- Canonical provenance, its adversarial self-check, the staged assembler, release freeze, M8
  self-check, compliance-tool self-check, and REUSE 6.2.0 are green
  (`ledger/buildlogs/20260826T113957-753485.log`,
  `ledger/buildlogs/20260826T113957-753481.log`,
  `ledger/buildlogs/20260826T113957-753493.log`,
  `ledger/buildlogs/20260826T114227-755570.log`,
  `ledger/buildlogs/20260826T114227-755563.log`,
  `ledger/buildlogs/20260826T114227-755564.log`, and
  `ledger/buildlogs/20260826T114227-755562.log`).
- An isolated provisional split probe also proved Binaryen's baseline and `--strip-debug` primary
  and secondary outputs are byte-identical, so custom/name metadata is not a remaining size lever
  (`ledger/buildlogs/20260826T112318-740457.log` and
  `ledger/buildlogs/20260826T112349-740676.log`).

The browser A/B uses a fallback software adapter and binds no semantic-pixel or hardware receipt.
No build-tree artifact, accepted profile, APPLY product, public bundle, result promotion,
tolerance, golden, blacklist, dependency, deferral, or promise changed. Accepted Apple profiles,
the hash-bound APPLY relink, and semantic hardware pixels for the staged product remain mandatory.
