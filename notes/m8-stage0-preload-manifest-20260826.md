<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 preload-manifest reduction - 2026-08-26

## Outcome

Commit `9db6040` removes all deferred filenames from the critical Emscripten preload manifest.
Deferred files are now absent until Stage 1 rather than materialized as zero-byte files. The
original file-packager glue already contains 448 `FS_createPath` calls covering 449 directories;
the packer parses that exact source contract and fails closed unless all 335 deferred parent
directories are present before it omits any file. Stage 1 then creates the real files with the
already-verified `FS.writeFile` path.

This also fixes a correctness defect hidden by the old placeholders. The first absent-file browser
candidate produced a startup traceback because urllib3 reads
`contrib/emscripten/emscripten_fetch_worker.js` during `bl_pkg` registration. Its former empty
placeholder suppressed `FileNotFoundError` and allowed an empty worker program to be cached. The
3,655-byte worker is now explicitly retained in Stage 0. The final partition is 479 keep files /
13,120,310 bytes, 2,962 deferred files / 152,235,215 bytes, and one dropped wheel / 1,787,723
bytes.

## Wire result

Pinned Node 22.16.0 Brotli q11/lgwin-24 changes the current provisional Stage-0 data/glue pair
from 2,594,698 + 76,803 bytes to 2,595,747 + 60,806 bytes. Returning the live fetch worker costs
1,049 compressed data bytes; removing 2,962 redundant manifest entries saves 15,997 glue bytes.
The net critical-wire reduction is **14,948 bytes**.

Applied to the existing complete-wire shape, the provisional projection moves from approximately
14,994,702 bytes to **14,979,754 bytes**, or 20,246 bytes below LAUNCH.md's 15,000,000-byte
ceiling. This remains a projection, not a receipt: the accepted Apple profiles, hash-bound APPLY
product, exact public bundle, hardware pixels, and <=8 second interaction measurement do not yet
exist.

## Evidence

- The fail-first absent-file candidate names the masked urllib3 startup access
  (`ledger/buildlogs/20260826T153800-960009.log`).
- The corrected monolith/candidate browser A/B preserves startup, trusted viewport input, lazy
  imports, metadata, icons, and Console behavior; all 2,962 deferred files restore byte-exactly
  with zero serious/page errors (`ledger/buildlogs/20260826T154309-963947.log`).
- Independent format-add-on, compiled-source, support-script, encoding, and NumPy A/B contracts
  are green (`ledger/buildlogs/20260826T154542-966233.log`,
  `20260826T154542-966234.log`, `20260826T154647-967442.log`,
  `20260826T154647-967443.log`, and `20260826T154748-968687.log`).
- The exact CAPTURE derivation proves 449 pre-created directories, 335 deferred parents, and no
  missing parent; packer, provenance, assembler, M8 consumer, transport, release-freeze, syntax,
  and REUSE contracts are green (`ledger/buildlogs/20260826T154250-962995.log`,
  `20260826T155242-972914.log`, `20260826T155242-972916.log`,
  `20260826T155242-972915.log`, `20260826T155020-970824.log`,
  `20260826T155020-970831.log`, `20260826T155320-974154.log`,
  `20260826T155320-974152.log`, and `20260826T155932-980060.log`).
- Exact q11 outputs are 2,595,747 data bytes and 60,806 glue bytes
  (`ledger/buildlogs/20260826T154848-970232.log` and
  `ledger/buildlogs/20260826T154848-970233.log`).
- Container-backed regression restores M0 6/6 and retains the strict existing M1-M8 receipt/APPLY
  boundaries (`ledger/buildlogs/20260826T155423-975654.log`).
- The refreshed technical compliance audit is green, while the strict M8 gate remains red at its
  23 existing APPLY/browser/product/tier boundaries (`ledger/buildlogs/20260826T155944-980282.log`
  and `ledger/buildlogs/20260826T155954-980442.log`).

The browser A/B uses the local fallback adapter and binds no hardware or semantic-pixel receipt.
The CAPTURE Wasm remains 119,142,918 bytes at SHA-256
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`. No build-tree artifact,
profile, APPLY product, public bundle, result promotion, tolerance, golden, blacklist, dependency,
or milestone promise changed.
