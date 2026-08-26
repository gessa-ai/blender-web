<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 focus-transition ordering — 2026-08-25

> **R12 audit correction:** `aae9c9a` preserves and retires the focus-loss boundary, but it does
> not totally order that boundary before later input already enqueued by proxied callbacks. A
> same-task blur/refocus followed immediately by key input dispatches KeyDown/KeyUp before
> WindowDeactivate/WindowActivate. The device-free corrective task and repro are recorded in
> `reports/audit-20260825-r12.md`; this note's receipts remain valid only for boundary retention.

## Outcome

Commit `aae9c9a` preserves a browser focus-domain loss even when the DOM main thread completes
`canvas -> page control -> canvas` before Emscripten delivers the first proxied callback to the
WM worker. The predecessor queried the later `document.activeElement`, suppressed the queued
canvas blur, and retained held Control plus left mouse state (`17`) without publishing a window
deactivation.

The browser-main capture bridge now publishes a monotonic loss generation from the DOM `blur`
event. At the start of `processEvents`, the WM worker consumes a changed generation, retires held
input through one ordinary deactivation, and only then queries the live DOM to decide whether to
reactivate. A proxied blur that handles an ordinary loss first acknowledges the generation, so a
later poll cannot emit a duplicate transition pair. Explicit exception-safe IME handoff markers
keep canvas/hidden-textarea moves inside Blender's existing logical focus domain. Bridge binding
fails closed if its Wasm publisher is absent and participates in listener rollback and teardown.

The final fail-closed source contract rejects all 17 publication, ordering, acknowledgement,
handoff, lifecycle, and live-evidence mutations
(`ledger/buildlogs/20260826T022458-201272.log`). Three consecutive real WasmFS +
`PROXY_TO_PTHREAD` runs retire held Control/left mouse under same-task blur/refocus and preserve
exactly one deactivate/activate pair for an ordinary transition; the final exact-code run is
`ledger/buildlogs/20260826T022506-201432.log`. IME focus-domain and Pointer Lock terminal behavior
remain green (`ledger/buildlogs/20260826T022507-201551.log`,
`ledger/buildlogs/20260826T022508-201271.log`), as do focus reset, canvas keyboard ownership,
window replacement, and left/right modifier state
(`ledger/buildlogs/20260826T022523-201869.log`,
`ledger/buildlogs/20260826T022524-202006.log`,
`ledger/buildlogs/20260826T022524-202121.log`,
`ledger/buildlogs/20260826T022525-201868.log`).

## Integrated product

The focused contract is part of the canonical device-free integration battery. Native and wasm32
remain byte-identical at 5,305 bytes, SHA-256
`b744698a4eb15c063e7d286527ef512fea62570074ddb5c7a5bb8c549d71b6a3`, with shipping-source
SHA-256 `302c73b7051a90c26ae0c456d5f6e8932ab2f278de7c8b39dcfde55f8d552204`
(`ledger/buildlogs/20260826T022530-202395.log`). This top-level GHOST-web change requires no
canonical patch-series refresh; the reusable late-proxy pattern is recorded as Class 109 in
`notes/porting-patterns.md`.

Locked Ninja relinked the optimized `blender_browser` product and then ended exact no-work
(`ledger/buildlogs/20260826T022545-203684.log`,
`ledger/buildlogs/20260826T022628-204118.log`). Strict OFF preflight binds the 682,793-byte
JavaScript, 119,035,487-byte Wasm, and 167,143,248-byte data artifacts
(`ledger/buildlogs/20260826T022629-204141.log`), whose SHA-256 values are respectively
`3e0d67e1eea1`, `371e85a25c95`, and `09e58a25849e`
(`ledger/buildlogs/20260826T022629-204111.log`).

The intended canonical `/` route continues to serve `platform_web/shell/windowed.html`. The exact
relinked product reaches running Blender under the forced fallback-software diagnostic, advances
77 idle ticks and four trusted-input ticks with one new presentation, and reports zero stage-1,
import, present-submission, present-transaction, or device-loss failures
(`ledger/buildlogs/20260826T022637-204160.log`). This exercises the previously committed P0 boot
and same-turn presentation repairs in the baked product rather than accepting a one-frame paint.
Pinned REUSE 6.2.0 covers all 2,608/2,608 files with no bad, deprecated, missing, unused, or
invalid licenses (`ledger/buildlogs/20260826T023053-208363.log`).

## Boundaries

Required M4 remains honestly red at the unchanged unsupported hardware binding
(`ledger/buildlogs/20260826T022843-206063.log`). The final pinned-container regression restores M0
6/6 green while M1-M8 retain their existing strict receipt, split-product, browser, hardware,
run-label, and release boundaries (`ledger/buildlogs/20260826T022843-206062.log`).

The live product run is diagnostic-nonreceipt evidence. No adapter, profile, split product,
hardware receipt, result promotion, dependency, deferral, tolerance, golden, blacklist, or promise
changed. Mesa dzn and Windows Edge were not attempted, WSL was not restarted, and s7 remains
blocked by `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by
Dawn)`.
