<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 False Color LUT - 2026-08-26

## Outcome

Commit `a5ab84c` moves the non-default `AgX_False_Color.spi1d` LUT from Stage 0 to
Stage 1. The pinned native Blender 5.2 oracle selects display `sRGB`, view `AgX`, and
look `None` at factory startup; False Color is an on-demand view. The default
`config.ocio`, `AgX_Base_sRGB.cube`, and `Guard_Rail_Shaper_EOTF.spi1d` inputs remain
in Stage 0.

The exact CAPTURE data partition changes from 479 keep files / 13,120,310 bytes and
2,962 deferred files / 152,235,215 bytes to 478 keep files / 12,993,270 bytes and
2,963 deferred files / 152,362,255 bytes. This removes 127,040 decoded bytes from
the first-pixel payload.

## Browser and wire evidence

The real headed Chromium monolith/candidate A/B preserves version, add-ons, editor
areas, default objects, active keymap, default toolbar icons, `sRGB / AgX / None`
color state, and trusted viewport input. Before Stage 1 the False Color LUT is absent;
the production loader restores all 2,963 files / 152,362,255 bytes byte-exactly, after
which Blender accepts the live `False Color` view and redraws with zero OCIO, page,
bind-group, encode, submit, transaction, or device-loss errors.

Pinned Node 22.16.0 Brotli q11/lgwin-24 changes Stage-0 data/glue from
2,595,747 + 60,806 bytes to 2,595,052 + 60,820 bytes. The net complete critical-wire
reduction is 681 bytes: the provisional projection moves from 14,979,754 to
14,979,073 bytes, or 20,927 bytes below LAUNCH.md's 15,000,000-byte ceiling. The LUT
is numeric text and compresses extremely well, so the decoded reduction is much
larger than the wire reduction.

## Verification

- Native factory-startup state: `ledger/buildlogs/20260826T160557-987046.log`.
- Fail-first classification rejection and final 569-case packer contract:
  `ledger/buildlogs/20260826T160717-988322.log` and
  `ledger/buildlogs/20260826T160731-988455.log`.
- Exact candidate partition and real browser A/B:
  `ledger/buildlogs/20260826T160820-989607.log` and
  `ledger/buildlogs/20260826T160932-990073.log`.
- Exact pinned Brotli data/glue encodes:
  `ledger/buildlogs/20260826T161134-992113.log` and
  `ledger/buildlogs/20260826T161134-992112.log`.
- Canonical staged provenance, assembler, transport, release-freeze, and aggregate
  M8 self-checks: `ledger/buildlogs/20260826T161321-993681.log`,
  `20260826T161409-994136.log`, `20260826T161409-994138.log`,
  `20260826T161409-994137.log`, and `20260826T161416-995010.log`.
- Container-backed regression restores M0 6/6; strict M8 returns to exactly its 23
  existing APPLY/browser/tier failures after technical compliance refresh:
  `ledger/buildlogs/20260826T161501-995743.log`,
  `20260826T161518-997387.log`, and `20260826T161524-997506.log`.
- REUSE 6.2.0 is green: `ledger/buildlogs/20260826T161538-997688.log`.

The browser A/B uses the local fallback adapter and binds no hardware or semantic-pixel
receipt. The CAPTURE `.wasm.orig` remains 119,142,918 bytes at SHA-256
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`. No build-tree
artifact, accepted profile, APPLY product, public bundle, receipt, result promotion,
tolerance, golden, blacklist, dependency, deferral, or milestone promise changed.
