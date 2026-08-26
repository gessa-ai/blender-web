<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 provisional split shape — 2026-08-26

## Outcome

The failed Apple M4 Pro success and terminal-error profiles were used only for an isolated,
non-shipping size experiment, as permitted by the hardware handoff. They do not authorize APPLY
and bind no receipt. Binaryen first rejected their real checksum against the current CAPTURE
generation. A copy of the merged profile then received the statically derived checksum of the
current 12-byte-newer `.wasm.orig`; only that temporary copy was used to measure split shape.

The provisional union has 20,444 hot defined functions out of 136,751. `wasm-split` plus the
production 48-function controller keep set produced:

| artifact | raw bytes | Brotli q11 bytes |
|---|---:|---:|
| current unsplit `.wasm.orig` | 119,142,918 | 24,212,144 |
| provisional primary Wasm | 50,578,979 | 12,292,157 |
| provisional deferred Wasm | 73,684,956 | 12,666,873 |
| current staged data, stage 0 | 28,518,942 | 5,534,442 |
| current CAPTURE glue | 707,146 | 90,811 |

The projected critical wire payload is therefore **17,917,410 bytes**, still **2,917,410 bytes
over the 15 MB launch bar**. Profile-guided splitting roughly halves the Wasm wire cost, but it is
not sufficient by itself; after accepted profiles arrive, the next launch-size task must remove at
least another 2.92 MB from primary Wasm, stage-0 data, and/or glue without cutting launch-visible
features.

## Validation and boundaries

- The unmodified provisional union was rejected by Binaryen with `checksum in profile does not
  match module checksum`; this is the expected production guard
  (`ledger/buildlogs/20260826T091617-620869.log`).
- The shape-only split completed in 14 seconds
  (`ledger/buildlogs/20260826T091916-622915.log`).
- The generated primary contains 20,516 defined functions; the deferred module contains 116,302.
  The production `binary-index-callgraph-streamed-wat-closure-v1` proof inspected all 48 reachable
  controller functions and returned PASS (`ledger/buildlogs/20260826T092145-625206.log`).
- Brotli q11 measurements are in `ledger/buildlogs/20260826T091952-623524.log`,
  `20260826T091952-623533.log`, `20260826T091952-623552.log`,
  `20260826T092511-627924.log`, and `20260826T092601-628226.log`.
- Current staged classification is 2,539 keep files / 28,518,942 bytes, 902 deferred files /
  136,836,583 bytes, and one dropped file / 1,787,723 bytes
  (`ledger/buildlogs/20260826T092452-627777.log`).

No build-tree file changed. No browser was launched, no software adapter produced a profile, and no
profile, APPLY artifact, hardware receipt, result flag, tolerance, golden, blacklist, deferral, or
promise was created or promoted. The current CAPTURE identity remains
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`; accepted success and
terminal-error Apple receipts remain mandatory.
