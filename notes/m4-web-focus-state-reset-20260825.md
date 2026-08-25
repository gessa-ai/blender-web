<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web focus-state reset — 2026-08-25

## Outcome

Commit `453d587` prevents browser focus loss from leaving Blender with a permanently held
modifier or mouse button. A tab switch, browser-window blur, or programmatic focus move is not
required to deliver matching DOM `keyup` or `mouseup` events. The old bridge queued only
`WindowDeactivate`, leaving `GHOST_SystemWeb`'s physical input state unchanged.

On blur, `GHOST_EventBridgeWeb::on_focus()` now snapshots `GHOST_Buttons`, clears all seven
tracked buttons and Ctrl/Shift/Alt/Meta, publishes `GHOST_kEventButtonUp` for every button that
was held, and only then queues `GHOST_kEventWindowDeactivate`. Blender already reconciles
modifiers by querying GHOST while handling deactivation; explicit button releases cover the
mouse-state path for which WM has no equivalent reconciliation. Refocus starts from clear state.

## Fail-first and focused evidence

- The real WasmFS + `PROXY_TO_PTHREAD` browser harness first reproduced the predecessor defect:
  holding Ctrl+left and moving focus without either release left `held=17 afterBlur=17`
  (`20260825T173809-1585546`).
- The rebuilt harness proves `held=ctrl+left blur=cleared refocus=clear worker=proxy-pthread`
  (`20260825T173931-1587082`). Existing fullscreen, pointer-lock, clipboard, and IME browser
  cases remain green; pointer-lock was rerun headless after the WSLg GPU process exited.
- The independent source contract requires release-before-deactivate ordering, all seven button
  masks, modifier clearing, and the null-window guard. All 10 deliberate mutations are rejected.
  The device-free integrated native/wasm graph remains byte-identical at 5,139 bytes, SHA-256
  `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`, with source SHA-256
  `93e45ebbb0363e823d88d0cdb658b8f2dc127cdc203cc67b280623df9742a186`
  (`20260825T174351-1591600`).
- Canonical-only replay remains green at pin `fbe6228777e7`: 257 patches, two retired patches,
  174 numbered touched paths, and canonical SHA-256
  `347d4aec2a1c`; this top-level platform/harness unit requires no canonical refresh.

## Product and gate evidence

- The optimized windowed product relinked through the locked build and then ended exact no-work
  (`20260825T174107-1587888`, `20260825T174409-1592891`). The resulting JavaScript is 674,706
  bytes at `6bcc0dc2264217c0f5091d053b7fd5dbe6e86a84f6a3bd5a726399f6588c5ed5`; Wasm is
  119,027,026 bytes at `d757ff4ff705f8d9614ef5dfb96973aaa706f696859e49c8354bfbdba573d8b3`;
  data is 167,143,248 bytes at
  `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`.
- A real-product fallback diagnostic reaches the running main loop, advances input and
  presentation after interaction, and records zero present submission rejections, transaction
  rejections, or device loss (`20260825T174243-1590735`). This also keeps the earlier P0 boot and
  same-turn presentation fixes exercised in the baked product.
- Required M4 remains honestly red at `unsupported binding schema or milestone`. The final
  container-backed regression at `2026-08-25T17:44:43Z` restores M0 6/6 green while M1–M8 retain
  their existing strict receipt, split-product, browser, hardware, and release boundaries.
- REUSE 6.2.0 covers all 2,564/2,564 files with no bad, deprecated, missing, or unused licenses
  (`20260825T175012-1598785`).

The live product run uses Chromium's fallback software adapter and is explicitly
diagnostic-nonreceipt evidence. It binds no adapter, profile, split product, live receipt, result
promotion, dependency decision, tolerance, golden, blacklist, or promise. The named blocker
remains `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by
Dawn)`; dzn, Windows Edge, and WSL restart were not attempted.
