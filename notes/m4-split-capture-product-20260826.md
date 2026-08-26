<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4/M8 split CAPTURE product — 2026-08-26

## Outcome

The current windowed product is relinked in `BLENDER_WEB_WASM_SPLIT_MODE=CAPTURE`, including the
bounded P0-D redraw recovery from `c2b6182`, the IME ordinary-key bridge from `cc2a844`, and the
focus/input total-order barrier from `4056b2a`. This is the
truthful hardware-profile input that was missing from every host: it contains an instrumented Wasm,
the exact uninstrumented `.wasm.orig`, and a schema-1 PASS split-build manifest. It is not the
shipping APPLY product and has no deferred shard yet.

The Apple M4 Pro driver can now point `BLENDER_WEB_BIN` at
`build-wasm-windowed-opt/bin`, run the strict success and terminal-error captures against this exact
generation, and return the two profile receipts (or their strict union). Only then may this build
tree be reconfigured to APPLY. No software/fallback profile was generated.

## Artifact identity

- `blender_browser.js`: 706,618 bytes,
  SHA-256 `6361c6e006ab920dc2058212e125468f386cbfe43c7616f52f8f678eef591784`.
- `blender_browser.wasm`: 120,496,530 instrumented bytes,
  SHA-256 `836ca3b7805909c47f3ee84ac7be38ac41ecd799cff5b0e3edbec6478fb9447c`.
- `blender_browser.wasm.orig`: 119,143,435 bytes,
  SHA-256 `7146e9a1e24c7d5882bf0dc13b3b27e5ab0c7971583f30141dfa2bf1b32925e4`.
- `blender_browser.data`: 167,143,248 bytes,
  SHA-256 `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`.
- `blender_browser.split-build.json`: 13,080 bytes,
  SHA-256 `0ebaa725dda13f06311c9631f0543dbcf9743671479aff0357bd430125a9f8d4`.

The profile is hash-bound to the `.wasm.orig` identity above. Any intervening relink invalidates it
and requires fresh hardware captures; generations must not be mixed.

## Evidence and boundary

- Locked CAPTURE relink: `20260826T065018-464817`; locked replay
  `20260826T065133-465582` reports no work.
- Exact CAPTURE inventory preflight: `20260826T065133-465583`.
- Strict producer self-check: `20260826T065243-467320` (`positive=20`, `negative=23`, zero browser
  launches).
- Two-phase source contract: `20260826T065243-467321`.
- Exact-artifact headed fallback diagnostic: `20260826T065147-465803` reaches running `WM_main`,
  advances uncapped ticks and a presentation after trusted input, and reports zero incomplete
  target bindings, presentation rejection, or device loss. This is explicitly
  diagnostic-nonreceipt evidence.
- Container-backed regression retains M0 at 6/6 GREEN. M1-M8 remain RED at their existing strict
  receipt, APPLY-artifact, browser, run-label, and release boundaries.
- Pinned REUSE 6.2.0 remains green at `20260826T065940-474443`.

The configure experiment also found that the migration runbook's removed bundled-emSDK Python path
returned exit 127. The canonical command now uses this host's documented
`.host-tools/bin/python3.13`; no build behavior or acceptance rule changed.

The shared worktree still contains pre-existing uncommitted release residue. This CAPTURE generation
is suitable for hash-bound profiling, but a public release still requires committed-state and
built-state reconciliation before the final APPLY/public-bundle cut.
