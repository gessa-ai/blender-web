<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4/M8 split CAPTURE product — 2026-08-26

## Outcome

The current windowed product is relinked in `BLENDER_WEB_WASM_SPLIT_MODE=CAPTURE`, including the
bounded P0-D redraw recovery from `c2b6182`. This is the
truthful hardware-profile input that was missing from every host: it contains an instrumented Wasm,
the exact uninstrumented `.wasm.orig`, and a schema-1 PASS split-build manifest. It is not the
shipping APPLY product and has no deferred shard yet.

The Apple M4 Pro driver can now point `BLENDER_WEB_BIN` at
`build-wasm-windowed-opt/bin`, run the strict success and terminal-error captures against this exact
generation, and return the two profile receipts (or their strict union). Only then may this build
tree be reconfigured to APPLY. No software/fallback profile was generated.

## Artifact identity

- `blender_browser.js`: 706,164 bytes,
  SHA-256 `306350a69822b37b0d5b3cc5dee87b89fe0d8c3b2bfe9fb6cd1a1ebcd2812550`.
- `blender_browser.wasm`: 120,495,911 instrumented bytes,
  SHA-256 `c91005cec29ee6017c775a517022ed058d0a8abaec192dbcc0f59a5c999b74ce`.
- `blender_browser.wasm.orig`: 119,142,827 bytes,
  SHA-256 `b0ecf56ee5dcfaf3e3ad46f93b9a533a60130d3a2828dfb08ca4336eacddc3e0`.
- `blender_browser.data`: 167,143,248 bytes,
  SHA-256 `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`.
- `blender_browser.split-build.json`: 13,080 bytes,
  SHA-256 `144d5e2277738b5a3ce76a8bfb924c126adb22b69a584dcc1faf71fa7a13c26b`.

The profile is hash-bound to the `.wasm.orig` identity above. Any intervening relink invalidates it
and requires fresh hardware captures; generations must not be mixed.

## Evidence and boundary

- Locked CAPTURE relink: `20260826T052332-370951`; locked replay
  `20260826T052436-372365` reports no work.
- Exact CAPTURE inventory preflight: `20260826T052444-372433`.
- Strict producer self-check: `20260826T052444-372434` (`positive=21`, `negative=23`, zero browser
  launches).
- Two-phase source contract: `20260826T052444-372438`.
- Exact-artifact headed fallback diagnostic: `20260826T052500-372577` reaches running `WM_main`,
  advances uncapped ticks and presentations after trusted input, and reports zero incomplete
  contract bindings, submission/transaction rejection, or device loss. This is explicitly
  diagnostic-nonreceipt evidence.
- Container-backed regression retains M0 at 6/6 GREEN. M1-M8 remain RED at their existing strict
  receipt, APPLY-artifact, browser, run-label, and release boundaries.
- Pinned REUSE 6.2.0 remains green at `20260826T052849-376040`.

The configure experiment also found that the migration runbook's removed bundled-emSDK Python path
returned exit 127. The canonical command now uses this host's documented
`.host-tools/bin/python3.13`; no build behavior or acceptance rule changed.

The shared worktree still contains pre-existing uncommitted release residue. This CAPTURE generation
is suitable for hash-bound profiling, but a public release still requires committed-state and
built-state reconciliation before the final APPLY/public-bundle cut.
