<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 local product entry point — 2026-08-25

## Outcome

Commit `3aef6f1` makes the canonical local COOP/COEP server's printed `/` URL load the intended
windowed native-app page. Before the change, `/` and `/index.html` both served the obsolete
headless M4.pre shell (SHA-256 prefix `34fda1ae2bf8daa6`) while `/windowed.html` served the actual
product page (`150707c66cd0784e`). That mismatch made the easiest documented launch path select a
different product topology than the hardware driver had verified explicitly.

`scripts/serve-web.sh` now selects `windowed.html` when the shell contains it and defaults its
binary root to `build-wasm-windowed-opt/bin`. The old page remains available at `/index.html` or
as the root through `BLENDER_WEB_ENTRY=index.html`; custom index-only harnesses preserve their
existing root. Python resolves and contains the selected entry before binding the server, so an
absolute path, traversal, or escaping symlink fails closed.

## Evidence

- The post-commit hermetic contract passes default-windowed, explicit-legacy, index-only custom,
  and escaping-entry cases while checking COOP/COEP/CORP/no-store headers
  (`20260825T122700-1270783`).
- The actual default server, with no `BLENDER_WEB_BIN`, `BLENDER_WEB_SHELL`, or
  `BLENDER_WEB_ENTRY` override, serves `/` byte-identically to `/windowed.html` and differently
  from `/index.html` against `build-wasm-windowed-opt/bin` (`20260825T122700-1270787`).
- The existing headed diagnostic, extended only to accept `/` as an explicit same-origin target,
  reaches `state=running` on fallback software with 76 idle ticks and a trusted-input tick/present
  round trip. It reports zero stage-1/import/device-loss/submission/transaction failures
  (`20260825T122706-1270942`).
- The locked `blender_browser` product graph is exact no-work (`20260825T122804-1271558`), and
  repository-local REUSE 6.2.0 is green (`20260825T122700-1270784`).

## Boundary

The headed run is labeled `diagnostic-nonreceipt` and uses Chromium's fallback software adapter.
It binds no adapter, profile, pixel, split product, result promotion, or M4 promise. The live
hardware blocker remains **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn
rejected by Dawn)**. Neither dzn nor Windows Edge was attempted, and WSL was not restarted.
