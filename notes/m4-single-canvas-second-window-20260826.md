<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 single-canvas second-window rejection — 2026-08-26

## Outcome

Commit `bbe7d27` closes the R12 split-ownership defect. `GHOST_SystemWeb::createWindow()` now
rejects a simultaneous second live window before constructing a context. The original window
therefore remains the single callback, input, hit-test, presentation, and `GHOST_WindowManager`
owner. Disposing it still clears `window_`, so the existing replacement-window lifecycle remains
available. Multi-window support itself stays explicitly deferred.

## Evidence

- The fail-first real WasmFS + `PROXY_TO_PTHREAD` browser case returned bitmask 75: system and
  hit-test ownership stayed on the first window while the manager switched to the second
  (`20260826T070936-485808`).
- The final seven-bit case proves the second create returns null without changing system ownership,
  manager ownership, managed-window count, or hit testing, then retains disposal, two repeated
  replacements, stale-callback retirement, focus transitions, and current input
  (`20260826T071019-486713`).
- The source/harness contract rejects 38 mutations, including a disabled or late production guard,
  an action producer that accepts the second window, an unbounded manager-count check, and a false
  browser verdict (`20260826T071232-489138`).
- The native/wasm32 integration matrix remains byte-identical at 5,470 bytes, SHA-256
  `bb8b0bc829cd9b82c5ab372af4b35271be80eb7336135f9f597bda65acb555e6`
  (`20260826T071309-491004`).

## Product and boundary

The locked CAPTURE product relinks and ends no-work (`20260826T071355-492590`,
`20260826T071516-494163`). Its new hardware-profile input is the 119,143,448-byte
`blender_browser.wasm.orig`, SHA-256
`76aa5d619fb3f1becb66828e96d4fba68dffb621af2d4d3ccd70fd77c10e0fff`.
Inventory preflight, the 20-positive/23-negative producer self-check, and the two-phase source
contract are green (`20260826T071523-494225/494228/494279`).

The exact artifact reaches running `WM_main` on the local fallback adapter with idle and trusted
input tick/presentation progress, zero target bind-group incompleteness, zero presentation
rejection, and no device loss (`20260826T071557-494800`). This is diagnostic-nonreceipt evidence.
Pinned REUSE covers 2,633/2,633 files (`20260826T072020-500238`). Required M4 remains hardware-pixel
RED, while authoritative container-backed regression restores M0 6/6 GREEN and preserves the
existing M1-M8 receipt/APPLY/browser/release boundaries (`20260826T071659-495795`).
