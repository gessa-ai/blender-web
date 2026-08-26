<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-F Pointer Lock Promise rejection recovery — 2026-08-26

## Outcome

The first-script shell now consumes failures from the modern Promise-returning
`requestPointerLock()` call and routes them through GHOST's existing `pointerlockerror` lifecycle.
A rejected Wrap/Hide request therefore returns to inactive, unlocked absolute motion, emits at
most one page diagnostic, and does not become an unhandled rejection or Playwright `pageerror`.

This is implemented and device-free verified, not hardware-closed. The driver-operated Apple M4
Pro must rerun both CAPTURE scenarios and require `pageErrors.length === 0` before either profile
or receipt is accepted.

## Root cause and fix

`GHOST_WindowWeb::setWindowCursorGrab()` calls Emscripten's synchronous
`emscripten_request_pointerlock(..., true)` seam. In the pinned Emscripten 4.0.10 runtime,
`$requestPointerLock` calls `target.requestPointerLock()` and discards its return value. Current
Chromium returns a Promise, so `WrongDocumentError` during the trusted MMB orbit escaped as an
unhandled page error even though GHOST already registered `pointerlockerror` and correctly retires
Pending/Active state there.

`platform_web/shell/diagnostics-bootstrap.js` runs before the Emscripten product script. It now
wraps the single DOM canvas method, calls the native method synchronously in the same activation
stack, and immediately attaches a rejection handler when a Promise is returned. Failure dispatches
the existing document `pointerlockerror` event and logs one bounded warning. The bridge does not
cancel or hide unrelated `unhandledrejection` events.

The change is shell-only. Locked Ninja remains no-work and the CAPTURE generation keeps its exact
119,142,906-byte `.wasm.orig` SHA-256
`edd94c4208c4c5229b197db20779336fb85293a79eb2ad7dc1fc3a8058e89336`; the driver can rerun the
same Wasm generation with the corrected shell without rebuilding or mixing profile generations.

## Evidence

- Fail-first source contract rejects the previous shell at the absent Promise handler:
  `20260826T080247-548250`.
- Final focused source contract covers pending/active/error/loss/blur/disposal plus
  rejected-Promise recovery and rejects 28 mutations: `20260826T082021-564620`.
- The real WasmFS/PROXY_TO_PTHREAD GHOST harness rebuilds, and headless Chromium performs two
  deterministic `WrongDocumentError` rejections. Both requests retire to inactive state, exactly
  one bounded diagnostic is emitted, and zero page errors escape:
  `20260826T081443-559436` and `20260826T081628-560978`.
- The aggregate native/wasm32 WebGPU/GHOST matrix is green:
  `20260826T081426-558098`.
- The optimized CAPTURE target is exact locked no-work and preserves both `.wasm.orig` and baked
  JavaScript hashes: `20260826T081650-561248`.
- REUSE 6.2.0 is green: `20260826T081952-564099`.

The required M4 scope remains RED at its existing hardware receipt boundary
(`20260826T081741-562350`). Regression retains the existing M1–M8 receipt/APPLY/browser/release
boundaries (`20260826T081752-562465`). No hardware profile, receipt, APPLY product, result
promotion, dependency, deferral, tolerance, golden, blacklist, or promise was created or changed.

Implementation commit: `34bad47`.

## Hardware closure

On the Apple M4 Pro rig, rerun both sanctioned CAPTURE scenarios with trusted MMB orbit. Require:

- adapter verdict `accepted-hardware` and the existing semantic/controller/profile checks;
- `pageErrors.length === 0` in both receipts;
- the bounded Pointer Lock diagnostic may appear once, with orbit continuing unlocked;
- both receipts reach PASS before their profiles authorize the hash-bound APPLY relink.
