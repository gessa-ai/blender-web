<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 critical Brotli window — 2026-08-26

> **Complete-wire correction:** the 14,963,658-byte figure below is the exact
> provisional primary/data/glue trio, not the complete pre-interaction payload. Commit
> `b1474cd` adds the previously omitted HTML and shell/worker controls to the receipt;
> the production-shaped complete projection is approximately 14,994,702 bytes. See
> `notes/m8-complete-critical-wire-20260826.md`.

## Outcome

Commit `99d7fd2` replaces the public bundle's ambient `brotli -q 11` invocation with a
repository-owned encoder pinned to Node 22.16.0, Brotli quality 11, and the standard maximum
16 MiB window (`lgwin=24`). Assembly, provenance, transport verification, staged-receipt creation,
M7/M8 verification, and both release freezes now bind the same codec contract.

This changes transport encoding only. The provisional split primary, Stage-0 file set, rewritten
glue input, and runtime feature surface are unchanged.

## Exact size result

The exact source-commit-bound recompression is
`ledger/buildlogs/20260826T143435-904295.log`:

| critical asset | prior q11 (`lgwin=22`) | q11 (`lgwin=24`) | change |
|---|---:|---:|---:|
| provisional primary Wasm | 12,418,419 | 12,292,157 | -126,262 |
| Stage-0 data | 2,595,374 | 2,594,698 | -676 |
| rewritten glue | 76,803 | 76,803 | 0 |
| **critical wire total** | **15,090,596** | **14,963,658** | **-126,938** |

The unchanged provisional payload moves from 90,596 bytes over LAUNCH.md's 15,000,000-byte gate
to **36,342 bytes under** it. `lgwin=24` is the ordinary Brotli format maximum, not the optional
large-window extension.

## Contract evidence

- The codec self-check pins Node, quality, window, and exact output hashes. Its >4 MiB
  distant-repeat fixture distinguishes `lgwin=24` from the old default, and its text fixture
  distinguishes quality 11 from quality 10. The final mutation check is
  `ledger/buildlogs/20260826T143041-898306.log`.
- Producer, provenance, transport, staged update, M7/M8, receipt, and release-freeze self-checks
  are green in `ledger/buildlogs/20260826T143130-899535.log`,
  `ledger/buildlogs/20260826T143247-901302.log`, and
  `ledger/buildlogs/20260826T143354-902319.log`.
- REUSE 6.2.0 is green in `ledger/buildlogs/20260826T143321-901571.log`.
- Required M8 remains honestly red at the existing 25 APPLY, staged-browser, product-receipt,
  tier, and release boundaries (`ledger/buildlogs/20260826T143614-904842.log`). Authoritative
  container-backed regression restores M0 to 6/6 green while M1-M8 retain their named strict
  boundaries (`ledger/buildlogs/20260826T143754-906510.log`).

## Boundary

The 14,963,658-byte result is an exact projection over the unchanged provisional split generated
from failed-receipt profiles. It is not an accepted profile, hash-bound APPLY product, assembled
public bundle, browser performance receipt, or launch promotion. The Apple rig must still return
accepted P0-F capture profiles and P0-E resize-recovery pixels; only then may the box relink APPLY,
assemble the public bundle, and measure the actual browser product. No build-tree artifact,
profile, APPLY product, public bundle, hardware receipt, result promotion, deferral, tolerance,
golden, blacklist, dependency, or promise changed.
