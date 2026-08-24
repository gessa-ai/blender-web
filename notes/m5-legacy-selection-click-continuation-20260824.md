<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 legacy selection click continuation

## Outcome

Commit `f781a02` and numbered patch 0254 route edit-mesh click selection through an owned raw
selection-buffer query session in the windowed wasm profile. Exact point-sample and nearest-point
queries kick once, return to the existing bounded View3D timer while pending, and replay only after
their producing context is restored. Native and non-session callers retain the synchronous path.

The settled query owns the evaluated object set, element ranges, maximum drawn-index length, and
selection mode that produced its IDs. Replay therefore cannot interpret a face ID through a later
edge or vertex map. Nearest replay also preserves the established spiral scan and exact Manhattan
distance. A separate replay-required latch covers the race where the request settles after the
query returned but before the outer operator guard runs; pending, failed, and ready-before-replay
states all leave edit-mesh selection unchanged.

The face, edge, and vertex click stages stop before any selection mutation until the exact query is
ready. Terminal failure, context drift, cancellation, and the 240-by-10-ms timer bound retire both
the raw request and its query session. Box, lasso, and circle selection are deliberately unchanged
and remain the next legacy-selection continuation family.

## Evidence

- The predecessor rejects before evidence allocation because the query-session entry point is
  absent: `ledger/buildlogs/20260824T165439-269178.log`.
- Final source verification rejects 21 independent mutations. Native and wasm32 pass six contracts
  with byte-identical 508-byte output at SHA-256
  `bbabb9773375aa0dacd6e3ad0da27fb8f1e1c9fec38e77d2266ec78652326340`; the four-file source
  receipt is SHA-256 `db9efd55b98d4d8536082f96168d281278a4aa5c1ec730a77e3937eed0f70ca6`:
  `ledger/buildlogs/20260824T171112-282764.log`.
- Numbered patch 0254 is SHA-256
  `b472d50753f61d8b650143e4cd5b905fd83a14c3da37bd8ac00fd668bab489d2` and round-trips all four
  exact pre/postimages in that receipt. Canonical freeze/replay passes with 20,258 entries, patch
  SHA-256 `f04d0daf4bab11886cc432b4413848e942f6d259447c6e77dc39ef435e2c2920`, and manifest SHA-256
  `9a601d5e01ab760b0b372e1bfa7d4cf844ce4de7d759f46d6a933452bf744303`:
  `ledger/buildlogs/20260824T171038-282028.log`.
- The actual native and wasm draw/edit-mesh/View3D libraries build successfully:
  `ledger/buildlogs/20260824T171017-281813.log` and
  `ledger/buildlogs/20260824T171027-281900.log`. The optimized browser product relinks, ends
  locked-Ninja no-work, and passes strict OFF preflight with 657,928-byte JavaScript at SHA-256
  `40d960578c014baff44a6db5d8ce3f9a83a10d86398b1c922e085e3cb8b09a98`, 118,931,977-byte Wasm
  at SHA-256 `b1b09c6fde17ae2b929f5d261a3b577ac090678c81c6ea5397306165fe0fe620`, and 167,143,248-byte
  data at SHA-256 `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`:
  `ledger/buildlogs/20260824T171130-283222.log`,
  `ledger/buildlogs/20260824T171247-284492.log`, and
  `ledger/buildlogs/20260824T171248-284521.log`.
- Required M5 remains honestly red only at the absent `blender_browser.deferred.wasm` complete
  product: `ledger/buildlogs/20260824T171330-284788.log`. Pinned-container regression keeps M0 at
  6/6 green while M1-M8 retain their existing strict receipt, product, browser, hardware, and
  release boundaries: `ledger/buildlogs/20260824T171343-284895.log`. REUSE 6.2.0 covers all 2,332
  feature-commit files: `ledger/buildlogs/20260824T171439-285994.log`.

## Remaining boundary

`gpu-sync-readback-windowed` still truthfully names four synchronous families: legacy selection
gestures, depth pick, depth cache, and WM window capture. Patch 0254 closes only edit-mesh click
selection at the source/device-free contract boundary; it does not constitute live GPU evidence.

This work creates no WebGPU adapter/device, browser profile, split product, live receipt, result
promotion, dependency decision, tolerance, golden, blacklist, or promise. Live C1 and aggregate
M5 acceptance remain separately deferred by the named blocker `no conformant hardware Vulkan ICD
in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`. No dzn, Windows interop, or WSL restart
path was attempted.
