<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 IME focus ownership — 2026-08-25

## Outcome

Commit `27b75ca` treats the canvas and Blender's enabled hidden IME textarea as one logical GHOST
focus domain. Canvas focus/blur and browser-window focus/blur now pass through one deduplicated
state transition before publishing `GHOST_kEventWindowActivate` or `GHOST_kEventWindowDeactivate`.
An internal composition begin/end handoff therefore preserves the manager's active canvas window,
while an ordinary page control or browser-window loss still produces exactly one deactivate and
reactivate pair.

Before the patch, the real WasmFS + `PROXY_TO_PTHREAD` harness measured the active element moving
to `bw-ime-input` while manager state fell to zero and logged `GHOST WindowDeactivate`; ending IME
restored the canvas and emitted `GHOST WindowActivate`. The final exact-commit browser run covers
internal handoffs, external-control focus, and window loss/recovery while the textarea owns
`activeElement` (`20260826T005939-114901`). The focused source contract rejects 17 mutations
(`20260826T005910-113463`), and the listener-lifecycle contract retains fail-at-every-position
rollback/removal coverage for all 14 callbacks.

The full integrated native/wasm32 run is byte-identical at 5,305 bytes, SHA-256
`b744698a4eb15c063e7d286527ef512fea62570074ddb5c7a5bb8c549d71b6a3`, with shipping-source
SHA-256 `c79b0a8d55dc51ee98307d7f895efe391eb6df965780ff46029ebaef35d36d8b`
(`20260826T005910-113489`). Neighboring keyboard, clipboard, focus-state, and window-lifecycle real
worker checks also remain green.

## Product and boundary

Locked Ninja rebuilt `GHOST_SystemWeb.cc` and relinked the optimized browser product, then ended
no-work both before and after the implementation commit (`20260826T004603-100690`,
`20260826T004644-101110`, `20260826T005920-114768`). OFF preflight binds the 680,153-byte
JavaScript, 119,034,557-byte Wasm, and 167,143,248-byte data artifact at SHA-256
`0d49c2d2937c`, `2caf01de6b46`, and `09e58a25849e` (`20260826T004658-101269`). The canonical `/`
windowed product reaches running Blender on the fallback-software diagnostic, advances 74 idle
ticks and nine trusted-input ticks with a new present, and reports zero stage-1, import,
present-submission, present-transaction, or device-loss failures (`20260826T004731-101607`). This
is diagnostic-nonreceipt evidence only.

The optional product-level `live_ime.mjs` producer was rejected as evidence: one headless attempt
timed out at its unrelated two-present prerequisite, and two headed attempts timed out at its
five-second F2 focus wait (`20260826T004809-102999`, `20260826T004901-103535`,
`20260826T005103-105743`). These runs reached no contradictory focus assertion; the exact
real-worker focus contract above is the binding behavior check.

Canonical receipt self-check/replay and REUSE 6.2.0 remain green
(`20260826T005640-110308`, `20260826T005640-110317`, `20260826T010234-117111`). Required M4 stays
red at the unchanged unsupported hardware binding (`20260826T005656-110535`), and the authoritative
container-backed regression restores M0 6/6 while M1-M8 retain their strict existing boundaries
(`20260826T005757-111319`). No adapter, profile, split product, hardware receipt, result promotion,
dependency, deferral, tolerance, golden, blacklist, or promise changed. Mesa dzn and Windows were
not attempted, WSL was not restarted, and s7 remains externally blocked by `no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
