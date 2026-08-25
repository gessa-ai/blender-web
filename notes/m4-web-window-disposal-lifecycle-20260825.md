<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web window-disposal lifecycle — 2026-08-25

## Outcome

Commit `64a2578` closes a use-after-free boundary in the single-canvas GHOST system. The inherited
`GHOST_System::disposeWindow()` removed and deleted a valid window, but `GHOST_SystemWeb` retained
that address in `window_` and left its browser-main HTML5 listeners installed. Subsequent window
lookups, main-loop settling, or queued input could therefore target deleted storage, and a later
window could not become the active callback target.

The web override now drains any synchronously committed IME transitions while the old window is
still valid, nulls the active pointer, atomically retires the callback owner, removes all ten exact
canvas/window listeners, and clears tracked buttons/modifiers before delegating deletion to the
base. Callback thunks validate the live atomic owner before dereferencing their opaque user pointer,
so work already queued from the browser main thread drops safely after retirement. A replacement
window republishes the owner, re-registers once, and restarts bounded first-pixel settling.

## Fail-first and focused evidence

- The predecessor real WasmFS + `PROXY_TO_PTHREAD` harness returned lifecycle bitmask `3`: the
  window was active before disposal and base deletion succeeded, but both `activeWindow()` and
  `getWindowUnderCursor()` still returned its deleted address
  (`20260825T175915-1606325`). The independent contract separately rejected the missing web
  `disposeWindow` override before evidence acceptance (`20260825T180104-1607438`).
- The final browser harness observes disposal bitmask `15`, no key delivery while detached,
  replacement-publication bitmask `7`, and keyboard delivery after callback rebinding. It also
  rejects any callback-removal diagnostic (`20260825T181535-1625623`).
- The source contract binds detach-before-delete ordering, all ten exact listener identities,
  queued-callback owner gating, IME retirement, input clearing, rollback, and replacement settling;
  all 17 mutations reject (`20260825T181535-1625622`). The post-commit integrated native/wasm32
  run remains byte-identical at 5,139 bytes, SHA-256
  `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`, with source SHA-256
  `7dbaff7314ec7208696535750434567e2eb59caa50455a58b6c1c80ba6d48663`
  (`20260825T181617-1627634`).
- Existing focus, pointer-lock, clipboard, IME, and fullscreen browser contracts remain green
  (`20260825T181222-1622403/1622404/1622408/1622416`, `20260825T181227-1622909`). Canonical-only
  replay remains green (`20260825T181535-1625642`).

## Product and gate evidence

- The optimized product relinked and then ended exact no-work; OFF preflight is green
  (`20260825T181050-1620627`, `20260825T181535-1625624/1625632`). The artifacts are
  675,151-byte JavaScript at `c2686605eeb5`, 119,027,933-byte Wasm at `431112c3b1c9`, and
  167,143,248-byte data at `09e58a25849e`.
- The same product reaches the running WM loop on the explicitly nonreceipt fallback diagnostic,
  advances four ticks and one presentation within 36 ms after trusted input, and records zero
  present-submission rejection, present-transaction rejection, or device loss
  (`20260825T181149-1621927`).
- REUSE 6.2.0 covers all 2,567/2,567 files with no bad, deprecated, missing, or unused licenses
  (`20260825T181726-1629217`).
- Required M4 remains honestly red at the unchanged unsupported hardware binding
  (`20260825T181548-1625939`). Container-backed regression restores M0 to 6/6 green while M1–M8
  retain their existing strict receipt, split-product, browser, hardware, and release boundaries
  (`20260825T181554-1626012`).

No adapter, device, profile, split product, live receipt, result promotion, dependency decision,
deferral, tolerance, golden, blacklist, or promise changed. The fallback run binds no receipt; dzn,
Windows Edge, and WSL restart were not attempted. The named blocker remains `no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
