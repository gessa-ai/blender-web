<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-1 failure recovery — 2026-08-26

## Outcome

Commit `0147a12` replaces the Stage-1 loader's permanent `started` latch with one shared
in-flight Promise and a bounded three-attempt transfer transaction. A failed manifest/data
transfer cannot reach WasmFS, every automatic attempt resets file/byte/timing/error accounting,
and successful recovery clears the prior error before installation. If all automatic attempts
fail, the visible state remains `error` with `retryable=true` and a later explicit
`window.__bwStage1Load()` call starts a fresh bounded operation without reloading the page.

Progress remains honest across recovery: transient failures publish `Retrying assets`, final
failure leaves `Assets unavailable - retry available` visible, and a recovered transfer ends at
`Assets ready`. Concurrent callers receive the exact same Promise and therefore cannot start
duplicate fetch/write transactions.

## Evidence

- The exact committed predecessor fails first because two concurrent calls do not share one
  in-flight Promise (`ledger/buildlogs/20260826T182218-1117992.log`).
- The final pinned-Node contract passes the public-shell 3-positive/6-negative matrix plus 11
  Stage-1 behavior cases and 12 mutations. It proves shared concurrency, HTTP 503 then success,
  interrupted stream then success, a three-attempt ceiling, explicit recovery after exhaustion,
  no writes from incomplete transfers, and visible retry progress
  (`ledger/buildlogs/20260826T181955-1113324.log`).
- Deterministic minification/provenance is green. The four minified critical shell programs move
  from 10,911 to 11,130 Brotli-q11/lgwin-24 bytes (+219); the conservative pre-APPLY projection
  remains about 32,459 bytes under 15 MB, but is not a launch receipt
  (`ledger/buildlogs/20260826T181955-1113325.log`).
- Staged assembly, transport, and CAPTURE producer self-checks are green
  (`ledger/buildlogs/20260826T182034-1113918.log`,
  `ledger/buildlogs/20260826T182034-1113926.log`, and
  `ledger/buildlogs/20260826T182034-1113922.log`). The M8 consumer self-check is green
  (`ledger/buildlogs/20260826T182034-1113932.log`).
- Both source-freeze contracts, the final hermetic contract, JavaScript syntax, and REUSE 6.2.0
  are green (`ledger/buildlogs/20260826T182057-1115125.log`,
  `ledger/buildlogs/20260826T182057-1115126.log`,
  `ledger/buildlogs/20260826T182057-1115129.log`,
  `ledger/buildlogs/20260826T182057-1115127.log`, and
  `ledger/buildlogs/20260826T182057-1115137.log`).
- Required M8 remains honestly red at the existing APPLY/receipt/tier boundaries
  (`ledger/buildlogs/20260826T182117-1116582.log`). Authoritative container-backed regression
  restores M0 to 6/6 green while M1-M8 retain their strict existing boundaries
  (`ledger/buildlogs/20260826T182147-1117107.log`).

## Boundary

This task does not repair the separately queued non-streaming fallback length/span defect or the
Stage-1 peak-memory duplication. It creates no public bundle, APPLY artifact, browser run,
hardware receipt, result promotion, promise, tolerance, golden, blacklist, dependency, or
deferral change.
