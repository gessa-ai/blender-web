<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4/M8 split CAPTURE product — 2026-08-26

## Outcome

The current windowed product is now relinked in `BLENDER_WEB_WASM_SPLIT_MODE=CAPTURE`. This is the
truthful hardware-profile input that was missing from every host: it contains an instrumented Wasm,
the exact uninstrumented `.wasm.orig`, and a schema-1 PASS split-build manifest. It is not the
shipping APPLY product and has no deferred shard yet.

The Apple M4 Pro driver can now point `BLENDER_WEB_BIN` at
`build-wasm-windowed-opt/bin`, run the strict success and terminal-error captures against this exact
generation, and return the two profile receipts (or their strict union). Only then may this build
tree be reconfigured to APPLY. No software/fallback profile was generated.

## Artifact identity

- `blender_browser.js`: 706,164 bytes,
  SHA-256 `be557c7b7de3f43a899092c4d161ff9f22b150831a51e2b1f1bb3e85bf6ad146`.
- `blender_browser.wasm`: 120,495,248 instrumented bytes,
  SHA-256 `43db44951da36e45c1eea9fa00e01be2f09a823fce200c68d2ead2f69a3b030c`.
- `blender_browser.wasm.orig`: 119,142,174 bytes,
  SHA-256 `0f815b8dee5b0ec1461fb83993b7ed4909578d9c69711d0ebaef244273d29e00`.
- `blender_browser.data`: 167,143,248 bytes,
  SHA-256 `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`.
- `blender_browser.split-build.json`: 13,081 bytes,
  SHA-256 `54641236abe8e44151c3a79b770a56beca18b112197fa4611a0cf17154a60801`.

The profile is hash-bound to the `.wasm.orig` identity above. Any intervening relink invalidates it
and requires fresh hardware captures; generations must not be mixed.

## Evidence and boundary

- Locked CAPTURE relink: `20260826T043941-326770`; locked replay reports no work.
- Exact CAPTURE inventory preflight: `20260826T044352-330979`.
- Strict producer self-check: `20260826T044352-331006` (`positive=20`, `negative=23`, zero browser
  launches).
- Two-phase source contract: `20260826T044352-331025`.
- Exact-artifact headed fallback diagnostic: `20260826T044402-331371` reaches running `WM_main`,
  advances uncapped ticks and presentations after trusted input, and reports zero incomplete
  contract bindings, submission/transaction rejection, or device loss. This is explicitly
  diagnostic-nonreceipt evidence.
- Container-backed regression retains M0 at 6/6 GREEN. M1-M8 remain RED at their existing strict
  receipt, APPLY-artifact, browser, run-label, and release boundaries.

The configure experiment also found that the migration runbook's removed bundled-emSDK Python path
returned exit 127. The canonical command now uses this host's documented
`.host-tools/bin/python3.13`; no build behavior or acceptance rule changed.

The shared worktree still contains pre-existing uncommitted release residue. This CAPTURE generation
is suitable for hash-bound profiling, but a public release still requires committed-state and
built-state reconciliation before the final APPLY/public-bundle cut.
