<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 NumPy deferral — 2026-08-26

## Outcome

Commit `d8de1d2` moves the complete 520-file NumPy Python tree to Stage 1. The previous partition
already deferred 317 test files but kept 203 runtime files, leaving a partial-package boundary in
the first-pixel payload. The new boundary is simpler: every NumPy file has a zero-length Stage-0
placeholder, and the production Stage-1 loader restores the whole package before M7 operator/IO
coverage.

This is a staged load, not a feature cut. Two independent behavior experiments establish that
NumPy is outside the boot closure: the pinned native 5.2 LTS factory startup reports zero NumPy
modules, and the real windowed CAPTURE product reports zero after reaching a stable WM main loop.
The persistent eight enabled add-ons still register without importing it.

## Exact size result

Against the unchanged 167,143,248-byte CAPTURE data payload, the partition becomes:

| bucket | files | raw bytes |
|---|---:|---:|
| Stage 0 keep | 2,342 | 24,173,362 |
| Stage 1 defer | 1,099 | 141,182,163 |
| drop | 1 | 1,787,723 |

The additional 203 deferred NumPy files remove 4,065,222 raw bytes from Stage 0. With pinned Node
22.16.0 Brotli-q11, Stage-0 data falls from 5,123,738 to **4,432,412 bytes** and rewritten glue
falls from 86,578 to **85,524 bytes**. Using the unchanged 12,418,419-byte provisional split
primary, critical wire falls from 17,628,735 to **16,936,355 bytes**, a 692,380-byte reduction.
The result remains **1,936,355 bytes over** LAUNCH.md's 15 MB bar.

## Runtime and contract evidence

- Pinned native factory startup: `numpy` is absent from `sys.modules`
  (`ledger/buildlogs/20260826T103701-698101.log`).
- The fail-first packer fixture caught the new Stage-1 concatenation; the final 28-classification,
  five-positive, ten-negative contract is green
  (`ledger/buildlogs/20260826T103831-700079.log` and `20260826T104959-709172.log`).
- The real fallback-browser A/B uses the same CAPTURE Wasm for both cases. Monolith and candidate
  report Blender 5.2.0 LTS, the same eight enabled add-ons, the same four editor areas, and the
  same Camera/Cube/Light objects. Both advance after two trusted `N` inputs with zero page or
  serious console errors. NumPy's `__init__.py` is 25,226 bytes in the monolith and zero bytes in
  Stage 0. The production Stage-1 loader then restores 1,099/1,099 files and 141,182,163 bytes;
  NumPy imports 86 modules and `arange(4).sum()` returns 6
  (`ledger/buildlogs/20260826T104717-706929.log`).
- Exact current-product derivation, staged provenance self-check, assembler self-check, release
  freeze self-check, and REUSE 6.2.0 are green
  (`ledger/buildlogs/20260826T103947-700625.log`, `20260826T104959-709176.log`,
  `20260826T104959-709181.log`, `20260826T104959-709173.log`,
  `20260826T105043-710327.log`, and `20260826T105043-710328.log`).
- Exact q11 data and glue measurements are
  `ledger/buildlogs/20260826T104836-708597.log` and `20260826T104836-708598.log`.
- The refreshed committed-tree technical compliance producer is green, and M8 returns to exactly
  its 23 existing APPLY/browser/tier failures with no staging or compliance-staleness addition
  (`ledger/buildlogs/20260826T105237-713071.log` and `20260826T105242-713165.log`).

The browser A/B uses the fallback software adapter and therefore binds no semantic pixel or
hardware receipt. No build-tree artifact, Wasm, accepted profile, APPLY product, result promotion,
tolerance, golden, blacklist, dependency, deferral, or promise changed. CAPTURE `.wasm.orig`
remains SHA-256 `c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.
Accepted Apple profiles, the hash-bound APPLY relink, and semantic hardware pixels for the staged
product remain mandatory.
