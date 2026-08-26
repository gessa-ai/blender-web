<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Release loader redesign — 2026-08-26

## Outcome

Commit `1040ac7` replaces the marketing-heavy windowed boot overlay with the owner-specified
minimal release loader: a neutral `#17181b` background, one thin ring, one 2-pixel determinate
bar, a percent readout, and one small single-line legal footer. The footer links the public GPL
source at <https://github.com/gessa-ai/blender-web> and carries the standing Blender Foundation
non-affiliation and trademark disclaimer. The hidden `#bw-diag` contract, `?gate=` behavior, and
loader dismissal after first semantic pixels are unchanged.

The removed proof copy now lives in `README.md`; it is no longer painted over Blender during
startup. No external font request is introduced.

## Local font and public inventory

The loader uses a deterministic static subset of the repository-pinned Inter 4.001 source at
`upstream/release/datafiles/fonts/Inter.woff2`. `scripts/subset-loader-font.py` pins FontTools
4.59.2 and Python Brotli 1.1.0, instantiates optical size 14 / weight 400, retains the required
Latin repertoire, and renames the modified font to `BW Interface Sans` in accordance with the
OFL reserved-font-name condition.

The emitted `platform_web/shell/fonts/bw-interface-sans.woff2` is 9,500 bytes with SHA-256
`266290448afbfd4c6ce386bbad0b305b478ca2612f665d1b26e5efc4d17e8190`. Its deterministic
Brotli-q11 public transport is 9,504 bytes. The font and `LICENSES/OFL-1.1.txt` are wired through
the monolithic and staged assemblers, service-worker precache/inventory, MIME servers, manifest
identity/provenance consumers, exact-tree checks, third-party inventory, and REUSE metadata.

## Evidence

- The pre-change shell fails the new contract at the required neutral background:
  `ledger/buildlogs/20260826T194953-1192465.log`.
- Deterministic font regeneration is exact:
  `ledger/buildlogs/20260826T195844-1198415.log`.
- The final source and real-browser loader contracts pass:
  `ledger/buildlogs/20260826T200725-1206450.log` and
  `ledger/buildlogs/20260826T200725-1206451.log`. The browser proof checks computed layout,
  the locally loaded font, the exact source/disclaimer footer, hidden diagnostics, retired-copy
  absence, and zero external requests.
- Public disclaimer, deploy portability, staged provenance, technical receipt, and critical-wire
  self-checks pass in `ledger/buildlogs/20260826T200725-1206456.log`,
  `20260826T200725-1206464.log`, `20260826T200725-1206472.log`,
  `20260826T200725-1206492.log`, and `20260826T200725-1206510.log`.
- Staged and monolithic assembler self-checks pass in
  `ledger/buildlogs/20260826T200725-1206527.log` and
  `ledger/buildlogs/20260826T195844-1198428.log`.
- Full M8 technical compliance passes in
  `ledger/buildlogs/20260826T200506-1204886.log`; repository-wide REUSE 6.2.0 reports all
  2,684 files compliant in `ledger/buildlogs/20260826T200251-1202455.log`.
- The pinned-container regression restores M0 to 6/6 while preserving the existing M1-M8
  receipt/APPLY/product boundaries in `ledger/buildlogs/20260826T200445-1204020.log`.

## Boundary

This is a shell/public-bundle source change. It did not relink Blender, assemble or publish a
release bundle, change the CAPTURE generation, consume or promote an Apple profile, authorize
APPLY, bind a hardware receipt, or change a result/promise/tolerance/golden/blacklist/deferral.
Required M4 remains red locally because this host cannot bind hardware pixels. Required M8 remains
red at its existing accepted-profile, APPLY-product, browser-receipt, and tier-evidence boundaries.
The next release relink must include this loader together with the already committed resize,
pointer-lock, and P0-G candidates before the driver-operated Apple hardware gauntlet.
