<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web window title main-thread handoff — 2026-08-25

## Outcome

Commit `93df837` makes `GHOST_WindowWeb::setTitle()` update the real browser document. The GHOST
window runs on the `PROXY_TO_PTHREAD` WM worker, where `document` is absent, so the former `EM_JS`
helper silently did nothing. The replacement uses Emscripten's synchronous main-thread proxy,
preserving `GHOST_WindowWeb::getTitle()` and copying UTF-8 while `title_.c_str()` is still valid.
Title changes are rare, so the synchronous call avoids an unsafe asynchronous pointer lifetime
without creating a frame-loop cost.

## Contract coverage

The pinned Emscripten 6.0.5 repro runs `main()` on the proxied worker and proves Unicode and empty
titles execute on the main runtime thread (`20260825T151121-1435724`). The production source
contract requires the synchronous proxy, DOM guard, UTF-8 conversion, owned string input, and
matching getter; five mutations fail closed (`20260825T151121-1435729`). The broader native/wasm32
integration remains byte-identical at 5,139 bytes, SHA-256
`94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`, with production-source
SHA-256 `c7d9cfb2a520` (`20260825T151121-1435725`).

## Product evidence

- The optimized `blender_browser` relinked through locked Ninja and then ended exact no-work
  (`20260825T150419-1427831`, `20260825T151141-1437097`). The baked JavaScript contains exactly
  one title assignment. Strict OFF preflight passes (`20260825T151157-1437262`) and binds
  660,302-byte JavaScript at SHA-256 `3c1ae67dc851`, 119,016,816-byte Wasm at
  `ec01d89bb1ec`, and 167,143,248-byte data at `09e58a25849e`.
- The headed COOP/COEP fallback diagnostic against `/windowed.html` reaches `state=running`,
  advances 75 idle ticks, turns trusted input into three more ticks and one presentation, and
  observes the real title `(Unsaved) - Blender 5.2.0 LTS`. It reports zero stage-1/import failures,
  destroyed-texture submission rejections, transaction rejections, or device loss
  (`20260825T151203-1437336`).
- Canonical replay remains green for 303 paths/256 active patches at SHA-256 `26b584627afe`
  (`20260825T150825-1432772`), and final REUSE 6.2.0 covers 2,544/2,544 files
  (`20260825T151442-1439355`). Container-backed regression keeps M0 6/6 green while M1–M8 retain
  their existing strict receipt, split-product, browser, hardware, and release boundaries
  (`20260825T150758-1431800`). Required M4 remains honestly red at its unchanged unsupported
  hardware binding (`ledger/results/m4.json`, 2026-08-25T15:08:02Z).

The headed run is diagnostic-nonreceipt evidence and binds no adapter, profile, split product,
pixel receipt, result promotion, dependency decision, deferral, tolerance, golden, blacklist, or
promise. The named blocker remains `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none;
Mesa dzn rejected by Dawn)`; dzn and Windows were not attempted, and WSL was not restarted.
