<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-1 fallback integrity — 2026-08-26

## Outcome

Commit `288d233` makes the public Stage-1 loader validate the manifest and complete payload before
the first WasmFS write. `total_bytes` must be a non-negative safe integer, the file list must be an
array, and every `[start,end)` span must be integral, in bounds, contiguous, and collectively cover
the declared payload exactly. The non-streaming `arrayBuffer()` branch now requires its received
length to equal `total_bytes`; it no longer replaces honest progress accounting with an arbitrary
response length.

Short, long, gapped, out-of-bounds, and uncovered-tail inputs therefore remain retryable transfer
errors. None can enter the writing phase, call `FS.writeFile`, or publish `Assets ready`. The
streaming reader retains its existing incremental overflow and terminal underflow checks.

## Evidence

- The exact predecessor fails first: a three-byte fallback for a six-byte manifest writes clamped
  slices and reports `done` instead of `error`
  (`ledger/buildlogs/20260826T182712-1123134.log`).
- The final pinned-Node contract passes the public-shell 3-positive/6-negative matrix plus 16
  Stage-1 behavior cases and 16 mutations, including fallback-specific short/long payloads and
  malformed span bounds with zero writes
  (`ledger/buildlogs/20260826T182937-1125080.log`).
- Deterministic minification/provenance is green for the expanded contract. The four public shell
  programs measure 23,455 raw versus 11,270 minified Brotli-q11/lgwin-24 bytes; the 140-byte
  increase from the preceding recovery fix leaves the conservative pre-APPLY projection about
  32,319 bytes under 15 MB, but this is not a launch receipt
  (`ledger/buildlogs/20260826T183125-1127077.log`).
- Staged assembly, transport, CAPTURE producer, and M8 consumer self-checks are green
  (`ledger/buildlogs/20260826T183125-1127078.log`,
  `ledger/buildlogs/20260826T183125-1127086.log`,
  `ledger/buildlogs/20260826T183125-1127081.log`, and
  `ledger/buildlogs/20260826T183125-1127104.log`).
- Both source-freeze contracts, the final hermetic contract, JavaScript syntax, technical
  compliance, and REUSE 6.2.0 are green
  (`ledger/buildlogs/20260826T183206-1128136.log`,
  `ledger/buildlogs/20260826T183206-1128138.log`,
  `ledger/buildlogs/20260826T183206-1128137.log`,
  `ledger/buildlogs/20260826T183206-1128144.log`,
  `ledger/buildlogs/20260826T183339-1132253.log`, and
  `ledger/buildlogs/20260826T183559-1133775.log`).
- Required M8 remains honestly red at its existing 25 APPLY/receipt/tier boundaries
  (`ledger/buildlogs/20260826T183233-1129822.log`). Container-backed regression restores M0 to
  6/6 green while M1-M8 retain their strict boundaries
  (`ledger/buildlogs/20260826T183308-1130999.log`).

## Boundary

This task does not address the separately queued Stage-1 peak-memory duplication. It creates no
public bundle, APPLY artifact, browser run, hardware receipt, result promotion, promise,
tolerance, golden, blacklist, dependency, or deferral change.
