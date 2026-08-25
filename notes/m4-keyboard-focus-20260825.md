<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 canvas keyboard-focus ownership — 2026-08-25

## Outcome

Commit `55db332` makes DOM focus the ownership boundary for raw Blender keyboard input. GHOST-web
now registers and removes key-down/up listeners on its focusable canvas. The browser window remains
the target only for the genuinely global resize listener. A page control or the hidden text input
used for IME composition can therefore receive its own keystrokes without also injecting raw key
events into Blender.

The per-registration epoch/token and all-or-nothing listener transaction remain unchanged. Moving
the listener does not weaken delayed-callback retirement, and removal uses the exact canvas target
paired with registration.

## Fail-first experiment

The preimage real WasmFS + `PROXY_TO_PTHREAD` harness first delivered a focused `a`, moved focus to
the ordinary `#clear` button, then pressed `b`. With `document.activeElement.id == "clear"`, the
GHOST log still contained both `KeyDown key=0x042 utf8='b'` and `KeyUp key=0x042`. This isolated the
defect from key translation and focus-state retirement: `WindowDeactivate` had already arrived,
but the Emscripten key listener was attached to `window` and continued accepting later events.

## Evidence

- The exact-commit source contract rejects eight registration, removal, live-focus, and stale-
  registration mutations (`ledger/buildlogs/20260825T225154-1907024.log`).
- The standalone real GHOST harness rebuilds under the shipping worker topology
  (`ledger/buildlogs/20260825T225119-1906236.log`). Focused delivery plus blurred suppression,
  existing focus retirement, two delayed registration epochs across repeated replacement, and IME
  composition all pass (`20260825T225139-1906451`/`1906452`/`1906456`/`1906463`).
- The integrated native/wasm32 matrix remains byte-identical at 5,305 bytes, SHA-256
  `98f9c1ca84af`, with shipping-source SHA-256 `73573478966d`; it includes both the new eight-
  mutation contract and the existing 32-mutation listener-lifecycle contract
  (`ledger/buildlogs/20260825T225158-1907076.log`).
- The optimized product rebuilt the exact GHOST translation unit and relinked, then finished
  locked no-work (`20260825T224422-1898088`/`20260825T225211-1908385`). OFF preflight binds
  679,421-byte JavaScript, 119,032,661-byte Wasm, and 167,143,248-byte data
  (`20260825T225306-1909874`), with SHA-256 prefixes
  `3543d05636de`/`8df838f451a1`/`09e58a25849e`.
- The canonical `/` product entry reaches running Blender 5.2 LTS on the forced fallback adapter,
  advances 77 idle ticks and three ticks plus one present after trusted input, and reports zero
  stage-1/import/submission/transaction/device-loss failures
  (`ledger/buildlogs/20260825T225221-1908517.log`). This is diagnostic-nonreceipt evidence.
- Canonical clean-pin replay retains 257 active patches and 303 paths at SHA-256 prefix
  `347d4aec2a1c` (`ledger/buildlogs/20260825T225309-1909920.log`).
- REUSE 6.2.0 covers all 2,590 files with zero bad, missing, deprecated, or unused licenses
  (`ledger/buildlogs/20260825T225501-1910674.log`). Required M4 remains red at the unsupported
  hardware binding; authoritative container-backed regression restores M0 6/6 green while M1-M8
  retain their existing strict boundaries (`ledger/buildlogs/20260825T225519-1911646.log`).

## Boundaries

`platform_web/shell/windowed.html`, served as `/` by `scripts/serve-web.sh`, remains the intended
windowed native-app entry point. This change binds no WebGPU adapter, profile, split product, pixel
receipt, result promotion, dependency, deferral, tolerance, golden, blacklist, or promise. The live
adapter is fallback software and carries no receipt. Required M4 remains hardware-bound by
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`; Mesa
dzn and Windows were not attempted, and WSL was not restarted.
