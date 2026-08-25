<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web custom-cursor bridge — 2026-08-25

## Outcome

Commit `1e24fc3` closes the remaining honest custom-cursor failure in `GHOST_WindowWeb`.
Blender's area-swap, vertex-loop, mute/pick-area, numbered/time, and cursor-text paths call
`setCustomCursorShape()` with either straight RGBA pixels or legacy low-bit-first XBM bitmap/mask
rows. The web backend returned `GHOST_kFailure`, so those interactions fell back to the default
cursor even though CSS image cursors can preserve the image and hotspot.

The WM-worker method now validates a 1..128-pixel image and in-range hotspot, then synchronously
proxies the borrowed spans to the browser main thread before the caller can release them. The
main-thread bridge copies exact RGBA bytes or expands XBM source/mask bits to black/white/transparent
RGBA, encodes a local PNG data URL, and only then publishes `GHOST_kStandardCursorCustom` through
the existing atomic release generation. Failure leaves the prior cursor untouched; hide/show
retains the last custom image. `GHOST_kCapabilityCursorRGBA` is now truthful, while the unimplemented
cursor-generator capability remains masked.

## Fail-first and focused evidence

- A pinned Chromium 149 capability probe preserves a generated PNG cursor and its `1 1` hotspot in
  both assigned and computed CSS (`20260825T182733-1637364`). The new behavior contract rejects the
  predecessor at cursor-bridge schema 1 before custom evidence allocation
  (`20260825T183114-1640295`).
- The focused JavaScript model passes exact RGBA and XBM expansion, invalid dimension/heap-span
  rejection, custom hide/show restoration, all 46 standard mappings, and missing module/canvas/error
  recovery (`20260825T183225-1640670`). The source contract binds the main-thread proxy, borrowed
  span copy, 128-pixel ceiling, low-bit-first expansion, custom release generation, and exact
  RGBA-versus-generator capability mask; all 12 mutations reject (`20260825T183332-1641887`).
- The real WasmFS + `PROXY_TO_PTHREAD` GHOST harness decodes the browser-produced PNGs back to the
  expected 2x2 RGBA/XBM pixels and hotspots, rejects an invalid hotspot without generation drift,
  retains the custom cursor across hide/show, and restores the standard text cursor
  (`20260825T183533-1643579`). Existing focus, lifecycle, clipboard, and IME browser contracts remain
  green (`20260825T183549-1643805/1643806/1643811/1643821`); fresh Xvfb-headed pointer-lock and
  fullscreen contracts are green (`20260825T184349-1654285/1654292`).
- Final integrated native/wasm32 output remains byte-identical at 5,139 bytes, SHA-256
  `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`, with source SHA-256
  `b2b31d79627c59df6080a53e54e1b82c79fa1ccb6fd567a80b28605cc726c43d`
  (`20260825T184201-1651469`).

## Product and gate evidence

- The optimized product relinked and then ended exact locked no-work; OFF preflight is green
  (`20260825T183725-1646690`, `20260825T183821-1647938/1647937`). The artifacts are 675,313-byte
  JavaScript at `b466be26eb40`, 119,028,151-byte Wasm at `2a4bdc55d5b5`, and 167,143,248-byte data
  at `09e58a25849e`.
- The same product reaches the running WM loop at `/` on the explicitly nonreceipt fallback
  diagnostic, updates the cursor bridge schema, advances four ticks and one presentation within
  38 ms after trusted input, and records zero presentation-submission rejection,
  presentation-transaction rejection, or device loss (`20260825T183840-1648175`).
- Required M4 remains honestly red at the unchanged unsupported hardware binding
  (`20260825T184006-1649035`). Container-backed regression restores M0 to 6/6 green while M1–M8
  retain the existing strict manifest, split-product, browser, hardware, run-label, and release
  boundaries (`20260825T184022-1649988`).
- REUSE 6.2.0 covers all 2,569/2,569 files with no bad, deprecated, missing, or unused licenses
  (`20260825T184518-1656303`).

No adapter, device, profile, split product, live receipt, result promotion, dependency decision,
deferral, tolerance, golden, blacklist, or promise changed. The fallback run binds no receipt;
dzn, Windows Edge, and WSL restart were not attempted. The named blocker remains `no conformant
hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
