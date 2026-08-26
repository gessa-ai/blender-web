<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 StudioLight discovery - 2026-08-26

## Outcome

Commit `d2e890f` restores Blender's complete StudioLight registry in the staged product without
moving any deferred image payload back onto the first-pixel wire. The Stage-0 preload manifest now
retains exactly 35 zero-byte discovery names: 27 matcaps and eight world lights. Stage 1 overwrites
those entries with the original image bytes. All other deferred files remain absent until Stage 1.

The five external `.sl` studio presets remain real Stage-0 files. Blender starts on its internal
`Default` studio light, but `BKE_studiolight_init()` eagerly parses every discovered `.sl`; a
zero-byte `.sl` would therefore register invalid lighting rather than a lazy payload.

## Root cause and fail-first evidence

`9db6040` removed every deferred filename after proving that Emscripten's baked `FS_createPath`
calls already create the full directory tree. That optimization correctly prevented empty Python
sources from masking missing imports, but it also removed the names that
`BKE_studiolight_init()` enumerates exactly once during startup. Restoring the image bytes later
could not repair the already-built registry.

The pinned native oracle reports 41 entries: six `STUDIO`, 27 `MATCAP`, and eight `WORLD`; every
factory Layout/Modeling viewport uses the internal `Default` studio light
(`ledger/buildlogs/20260826T164839-1026058.log`). Against the pre-fix staged candidate, the real
browser A/B reported a different startup registry, both representative image names were absent,
and post-Stage-1 assignment of `forest.exr` failed because the enum contained no world entries
(`ledger/buildlogs/20260826T163650-1015623.log`).

## Verification and wire cost

- The final headed Chromium monolith/staged A/B preserves the exact 41-entry registry before
  Stage 1, proves representative matcap/world files are zero-byte discovery entries, restores all
  2,963 deferred files / 152,362,255 bytes, selects `forest.exr` and `basic_bright.exr`, accepts
  trusted viewport input, and reports zero serious console or page errors
  (`ledger/buildlogs/20260826T164211-1019987.log`).
- The fail-closed packer contract covers 571 classifications, five discovery decisions, seven
  positive cases, and twelve negative manifest cases; the exact CAPTURE derivation produces 35
  discovery entries in a 513-entry Stage-0 manifest
  (`ledger/buildlogs/20260826T164025-1018067.log` and
  `ledger/buildlogs/20260826T164038-1018162.log`).
- Pinned Node 22.16.0 Brotli q11/lgwin-24 leaves Stage-0 data unchanged at 2,595,052 bytes and
  changes rewritten glue from 60,820 to 61,038 bytes. The 218-byte fidelity cost moves the
  provisional complete critical wire from approximately 14,979,073 to **14,979,291 bytes**, still
  20,709 bytes below LAUNCH.md's 15,000,000-byte ceiling
  (`ledger/buildlogs/20260826T164335-1020942.log` and
  `ledger/buildlogs/20260826T164335-1020943.log`).
- Canonical provenance, assembler, transport, release-freeze, aggregate M8, JavaScript syntax, and
  REUSE checks are green (`ledger/buildlogs/20260826T164537-1023630.log`,
  `20260826T164505-1022315.log`, `20260826T164505-1022319.log`,
  `20260826T164505-1022327.log`, `20260826T164537-1023631.log`,
  `20260826T164505-1022350.log`, and `20260826T164807-1025707.log`).

This is a device-free fallback-adapter behavior contract and binds no hardware or semantic-pixel
receipt. The CAPTURE `.wasm.orig` remains 119,142,918 bytes at SHA-256
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`. No build artifact,
accepted profile, APPLY product, public bundle, receipt, result promotion, tolerance, golden,
blacklist, dependency, deferral, or milestone promise changed. Accepted Apple profiles, the
hash-bound APPLY relink, staged hardware pixels, and the <=8-second interaction receipt remain
mandatory.
