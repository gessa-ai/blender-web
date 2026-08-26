<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 IME non-composing key bridge — 2026-08-26

## Outcome

Commit `cc2a844` closes Audit R12's ordinary-key loss while Blender's hidden IME textarea owns DOM
focus. The shipping `WITH_INPUT_IME` callback transaction now registers key-down/up on both the
canvas and `#bw-ime-input`. An earlier listener on the textarea admits ordinary keys but calls
`stopImmediatePropagation()` for disabled/unowned input, active composition, `isComposing`,
`Process`, and key-code 229. Emscripten's C keyboard payload does not carry `isComposing`, so this
main-thread ordering prevents composition process keys from also entering GHOST as raw keys.

The shipping profile owns 16 callbacks and retires their exact targets in reverse order; the
non-IME profile remains 14. The existing process-lifetime registration epoch still rejects queued
callbacks from disposed/replaced windows.

## Evidence

- The fail-first real worker timed out with trusted textarea keys but zero GHOST delivery
  (`20260826T061526-420334`). The final focused case delivers 22 exact down/up transitions covering
  ASCII, ArrowLeft, Backspace, Enter, Escape, and Ctrl+C/X/V; active composition emits four IME
  events and zero raw keys, while an unrelated page control remains suppressed
  (`20260826T062340-428387`).
- The existing composition, keyboard-focus, and repeated window replacement browser cases remain
  green (`20260826T062340-428388`, `428392`, `428399`). The focused source contract rejects 17
  mutations (`20260826T062249-427028`), and the baked runtime contains the admission/suppression
  guard (`20260826T063110-440047`).
- The full native/wasm32 integration matrix covers all 16 listener failure positions plus
  replacement rollback/retry and remains green (`20260826T063024-437357`).
- The locked CAPTURE relink and no-work replay are green (`20260826T062439-430783`,
  `20260826T062759-434099`). The current 119,142,963-byte `.wasm.orig` is SHA-256
  `7f6d20fd94d76f8f97d419a0c587be3c7d71bfc812c163b3b25ac9614e23dc9c`; inventory, producer
  self-check, and two-phase source validation pass (`20260826T062806-434917`, `434918`, `434922`).
- In headed Chromium on the forced software adapter, the real Blender object-name editor receives
  trusted ASCII/navigation/Backspace/Ctrl+C/X/V/Enter/Escape, commits `BWKEY_012X`, preserves it
  across the canceled rename, and reads it back through Blender's Python Console and GHOST
  clipboard. The bridge admits 86 raw events with zero suppression outside composition and zero
  presentation/device errors (`20260826T062641-432870`). A preceding headless run reached the same
  text-state assertion but reported `Device was destroyed`; it is rejected rather than used as
  evidence (`20260826T062551-431775`).
- Pinned REUSE 6.2.0 is green (`20260826T063733-445105`). The authoritative container-backed
  regression restores M0 to 6/6; M1-M8 retain their strict receipt/APPLY/browser/pixel/release
  boundaries.

## Boundary

The product browser run is fallback-software diagnostic evidence only. It binds no adapter profile,
hardware receipt, pixel result, milestone promotion, tolerance, golden, blacklist, or promise.
P0-D and P0-E still require Apple semantic-pixel verification, the new CAPTURE generation still
requires exact Apple success plus terminal-error profiles before APPLY, and physical OS IME/dead-key
evidence remains separately blocked on a trusted human input session.
