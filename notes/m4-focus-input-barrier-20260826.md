<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 focus/input total-order barrier — 2026-08-26

## Outcome

Commit `4056b2a` closes the R12 focus/input ordering defect. Browser-main capture already preserved
an intervening focus loss, but the WM worker consumed it only from `processEvents()` after later
proxied key and pointer callbacks had queued GHOST input. Canvas blur/focus callbacks now consume
that capture-time loss before consulting the later live DOM. Focus and input therefore use the
existing Emscripten worker callback FIFO as one order: deactivate, reactivate, then later input.

The change does not manufacture focus transitions for Blender's canvas/IME handoffs. An ordinary
blur still emits one pair, held modifier/button state retires before deactivation, and stale
callback registrations remain rejected by their existing epoch gate.

## Focused evidence

- The audited predecessor produced `KeyDown, KeyUp, WindowDeactivate, WindowActivate`
  (`20260826T030555-241420`). The fail-first run in this iteration reproduced that exact inversion.
- The final real WasmFS + `PROXY_TO_PTHREAD` browser harness proves both immediate key and mouse
  sequences are `deactivate, activate, down, up`, while preserving held Control/left retirement and
  ordinary single-pair delivery (`20260826T064801-459504`).
- The source contract rejects 20 publication, callback-order, lifecycle, and live-evidence
  mutations (`20260826T065442-470009`). Focus reset, IME composition, ordinary IME keys, keyboard
  ownership, modifier sides, window replacement, and Pointer Lock all remain green
  (`20260826T064801-459505/459508/459524/459516/459540/459554`,
  `20260826T065003-464607`).

## Integrated product

The canonical native/wasm32 integration matrix remains byte-identical at 5,470 bytes,
SHA-256 `bb8b0bc829cd9b82c5ab372af4b35271be80eb7336135f9f597bda65acb555e6`
(`20260826T064942-463297`). The locked CAPTURE product relink and exact no-work replay are green
(`20260826T065018-464817`, `20260826T065133-465582`). Its new profile input is
`blender_browser.wasm.orig`, 119,143,435 bytes,
SHA-256 `7146e9a1e24c7d5882bf0dc13b3b27e5ab0c7971583f30141dfa2bf1b32925e4`.

Exact CAPTURE inventory, the 20-positive/23-negative producer self-check, and the two-phase source
contract are green (`20260826T065133-465583`, `20260826T065243-467320/467321`). The same artifact
reaches running `WM_main` under the fallback-software diagnostic, advances uncapped ticks and a
presentation after trusted input, and reports zero incomplete target bindings, present rejection,
or device loss (`20260826T065147-465803`). This remains diagnostic-nonreceipt evidence.

REUSE covers 2,632/2,632 files (`20260826T065940-474443`). Required M4 remains RED only at the
unsupported hardware binding (`20260826T065300-467427`); container-backed regression keeps M0 6/6
GREEN while M1-M8 retain their strict receipt/APPLY/browser/release boundaries
(`20260826T065337-467959`). No hardware profile, deferred shard, APPLY product, pixel receipt,
result promotion, tolerance, golden, blacklist, deferral, or promise changed.
