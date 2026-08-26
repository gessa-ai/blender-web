<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 modifier-side state — 2026-08-25

## Outcome

Commit `f41ebe0` replaces GHOST-web's four aggregate modifier booleans with the pinned
`GHOST_ModifierKeys` side-aware state. Keyboard `code` publishes an exact left/right Shift,
Control, Alt, or OS transition before aggregate DOM flags are reconciled. Mouse and wheel input
therefore preserve a known side or simultaneous pair; only input with no key history uses the
documented left-side fallback. Focus loss still clears the complete state before deactivation.

The unchanged implementation failed the first trusted CDP case: `ShiftRight` generated the exact
right-key event, while `getModifierKeys()` returned mask `1` (left) instead of mask `2` (right).
The final post-commit source contract rejects 19 storage, mapping, ordering, aggregate, harness,
and focus mutations (`ledger/buildlogs/20260826T012341-139444.log`). The real WasmFS +
`PROXY_TO_PTHREAD` browser harness passes all four modifier families, right-only, both-held,
opposite-side release, aggregate preservation/fallback, and right-side focus retirement under
trusted CDP input (`ledger/buildlogs/20260826T012341-139445.log`). Existing focus-state and
canvas-keyboard ownership checks remain green (`ledger/buildlogs/20260826T012341-139449.log`,
`ledger/buildlogs/20260826T012341-139455.log`).

## Integrated product

The device-free integrated native/wasm32 matrix remains byte-identical at 5,305 bytes,
SHA-256 `b744698a4eb15c063e7d286527ef512fea62570074ddb5c7a5bb8c549d71b6a3`; its shipping-source
digest now includes `GHOST_SystemWeb.hh` and is
`f10ed0c6c7445b16e078bf053b058ec9a39ec0907277dfabf09de6bf75c9f26a`
(`ledger/buildlogs/20260826T012129-136597.log`). Locked Ninja relinked the optimized product and
then ended exact no-work (`ledger/buildlogs/20260826T011622-131245.log`,
`ledger/buildlogs/20260826T012348-139870.log`). Strict OFF preflight binds 680,153-byte
JavaScript, 119,035,011-byte Wasm, and 167,143,248-byte data artifacts
(`ledger/buildlogs/20260826T012356-139946.log`); their SHA-256 values are respectively
`0d49c2d2937c`, `8ce14cc83646`, and `09e58a25849e`.

The canonical `/` windowed product reaches running Blender on the explicit fallback-software
diagnostic, advances 74 idle ticks and ten trusted-input ticks with one new presentation, and
reports zero stage-1/import/submission/transaction/device-loss failures
(`ledger/buildlogs/20260826T012356-139959.log`). This is diagnostic-nonreceipt evidence only.
Canonical replay and its 18-mutation receipt self-check remain green
(`ledger/buildlogs/20260826T012356-139947.log`,
`ledger/buildlogs/20260826T012356-139951.log`). Final REUSE 6.2.0 compliance covers all
2,603/2,603 files (`ledger/buildlogs/20260826T012607-141916.log`).

## Boundaries

Required M4 remains honestly red at the unchanged unsupported hardware binding. The
container-backed regression restores M0 6/6 while M1-M8 retain their existing strict receipt,
artifact, split-product, browser, hardware, run-label, and release boundaries at
`2026-08-26T01:19:04Z`. No adapter, profile, split product, hardware receipt, result promotion,
dependency, deferral, tolerance, golden, blacklist, or promise changed. Mesa dzn and Windows were
not attempted, WSL was not restarted, and s7 remains blocked by `no conformant hardware Vulkan
ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
