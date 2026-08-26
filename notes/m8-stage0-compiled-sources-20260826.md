<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 compiled-source deferral — 2026-08-26

## Outcome

Commit `4a43751` moves 833 redundant source-data files behind Stage 1: 790 icon SVGs, 37
cursor SVGs, the embedded font inputs, the compiled default-theme source, and three data/icon
generator scripts. Blender's build already converts the runtime-relevant bytes into C/object data;
the source copies remain available byte-exact after Stage 1 for inspection.

This is staged loading, not a feature cut. Runtime icon `.dat` files and the ordinary startup
payload remain in Stage 0. The optimized CAPTURE Wasm is unchanged at
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.

## Source boundary

- `upstream/source/blender/editors/datafiles/CMakeLists.txt:178` embeds `bfont.pfb` with
  `data_to_c_simple`.
- The same file at lines 1023 and 1055 embeds the icon and cursor SVG families.
- `upstream/source/blender/blenloader/CMakeLists.txt:18` compiles
  `userdef_default_theme.c` directly.
- The icon generator scripts describe their build-only role in
  `upstream/release/datafiles/blender_icons_geom.py` and
  `blender_icons_geom_update.py`.

## Exact size result

Against the unchanged 167,143,248-byte CAPTURE data payload, the partition becomes:

| bucket | files | raw bytes |
|---|---:|---:|
| Stage 0 keep | 1,509 | 22,597,563 |
| Stage 1 defer | 1,932 | 142,757,962 |
| drop | 1 | 1,787,723 |

The 833 newly deferred files remove 1,575,799 raw bytes. With pinned Node 22.16.0
Brotli-q11, Stage-0 data falls from 4,432,412 to **4,028,170 bytes** and rewritten glue falls
from 85,524 to **81,589 bytes**. With the unchanged 12,418,419-byte provisional split primary,
critical wire falls from 16,936,355 to **16,528,178 bytes**, a **408,177-byte reduction**.
The result remains **1,528,178 bytes over** LAUNCH.md's 15 MB bar.

## Verification

- Fail-first classification rejected the still-kept icon SVG
  (`ledger/buildlogs/20260826T110526-725158.log`). The final 37-classification, five-positive,
  ten-negative packer contract is green (`20260826T111126-729284.log`).
- The isolated candidate pack is 1,509/22,597,563 Stage 0 and
  1,932/142,757,962 Stage 1 (`20260826T110838-726996.log`).
- A real fallback-browser monolith/candidate A/B boots the same Blender version, eight enabled
  add-ons, four editor areas, and Camera/Cube/Light state; both advance under two trusted inputs.
  Eight representative source files are zero-length placeholders, the runtime icon remains
  byte-identical in Stage 0, and Stage 1 restores all 1,932 files / 142,757,962 bytes with exact
  representative SHA-256 values and zero page/serious-console errors
  (`20260826T110900-727187.log`).
- Exact q11 data/glue measurements are in `20260826T111017-728824.log`.
- Packer provenance, assembler source inventory, staged-consumer, release-freeze, compliance-tool,
  technical compliance, and REUSE 6.2.0 checks are green
  (`20260826T111126-729292.log`, `20260826T111126-729302.log`,
  `20260826T111126-729316.log`, `20260826T111150-729518.log`,
  `20260826T111150-729519.log`, `20260826T111201-730403.log`, and
  `20260826T111327-732495.log`).

The browser A/B uses the fallback software adapter and binds no semantic-pixel or hardware
receipt. No build-tree artifact, accepted profile, APPLY product, public bundle, result promotion,
tolerance, golden, blacklist, dependency, deferral, or promise changed. Accepted Apple profiles,
the hash-bound APPLY relink, and semantic hardware pixels for the staged product remain mandatory.
