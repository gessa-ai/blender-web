<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 Python runtime-source staging — 2026-08-26

## Outcome

Commit `6bc7cab` moves 203 explicitly measured browser-cold CPython and site-package source
files to Stage 1. This is staged loading, not a feature cut: the production loader restores every
source byte after first pixels. Unrecognized or newly added sources remain in Stage 0 by default.

The optimized CAPTURE Wasm is unchanged: `.wasm.orig` remains 119,142,918 bytes at
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.

## Measured closure and fail-closed boundary

An exact windowed CAPTURE census found 206 Python sources absent from the initial browser module
closure. The final boundary retains three sources that a complement-only classifier would have
incorrectly deferred:

- `encodings/utf_8_sig.py` remains in the previously established five-file startup codec closure.
- `ssl.py` remains because the enabled `bl_pkg` backup-restoration path imports Requests/urllib3
  and reads `ssl.OPENSSL_VERSION`.
- `urllib3/contrib/pyopenssl.py` remains because Requests may import it and call
  `inject_into_urllib3()` during that same valid startup path.

The fail-first classifier rejected `_pydecimal.py` as incorrectly kept
(`ledger/buildlogs/20260826T125713-822058.log`). The final contract checks every one of the 203
deferred sources plus active neighbors and passes 281 classifications, five positive packing
cases, and ten negative manifest cases (`ledger/buildlogs/20260826T131824-840940.log`).

## Exact size result

Against the unchanged 167,143,248-byte CAPTURE data payload, the partition becomes:

| bucket | files | raw bytes |
|---|---:|---:|
| Stage 0 keep | 761 | 14,545,261 |
| Stage 1 defer | 2,680 | 150,810,264 |
| drop | 1 | 1,787,723 |

Pinned Node 22.16.0 Brotli-q11 produces a 2,941,058-byte Stage-0 data stream and 78,104-byte
rewritten glue. With the unchanged 12,418,419-byte provisional split primary, projected critical
wire falls from 16,019,244 to **15,437,581 bytes**, a **581,663-byte reduction**. It remains
honestly **437,581 bytes over** LAUNCH.md's 15,000,000-byte bar.

Canonical packing is recorded in `ledger/buildlogs/20260826T131825-840967.log`; the exact q11
measurement is `ledger/buildlogs/20260826T132327-846840.log`.

## Runtime and release evidence

- The real monolith/candidate browser A/B preserves version, enabled add-ons, editor areas,
  default objects, active Cube/object-mode state, and trusted N-panel input before Stage 1.
  Six representative cold sources are zero-length placeholders while six active neighbors remain
  byte-identical. Stage 1 restores all 2,680 files / 150,810,264 bytes, then exercises Decimal,
  ElementTree, logging handlers, multiprocessing managers, IDNA UTS-46 data, and PyREPL source
  compilation with zero serious console errors or page errors
  (`ledger/buildlogs/20260826T131835-841401.log`).
- Canonical staged provenance, assembler, transport, release-freeze, M8 consumer, compliance-tool,
  JavaScript syntax, and REUSE checks are green
  (`ledger/buildlogs/20260826T132048-843040.log`,
  `ledger/buildlogs/20260826T132048-843075.log`,
  `ledger/buildlogs/20260826T132048-843089.log`,
  `ledger/buildlogs/20260826T132048-843098.log`,
  `ledger/buildlogs/20260826T132050-843891.log`,
  `ledger/buildlogs/20260826T132050-843948.log`,
  `ledger/buildlogs/20260826T132051-843961.log`, and
  `ledger/buildlogs/20260826T132125-845009.log`).

The browser A/B uses a fallback software adapter and binds no semantic-pixel or hardware receipt.
No build-tree artifact, accepted profile, APPLY product, public bundle, result promotion,
tolerance, golden, blacklist, dependency, deferral, or promise changed. Accepted Apple profiles,
the hash-bound APPLY relink, and semantic hardware pixels for the staged product remain mandatory.
