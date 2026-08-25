<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web fullscreen state — 2026-08-25

## Outcome

Commit `6d71197` replaces `GHOST_WindowWeb::setState()`'s unconditional-success no-op with the
browser Fullscreen API. Fullscreen entry uses `emscripten_request_fullscreen_strategy()` with
stretch CSS, leaves the transferred canvas backing store worker-owned, and treats Emscripten's
deferred user-activation result as an accepted request. Normal and maximized map to the browser's
page-filling non-fullscreen state through `emscripten_exit_fullscreen()`. Browser-impossible
minimization and unknown states fail honestly.

The real GHOST event harness now uses the shipping WasmFS + `PROXY_TO_PTHREAD` topology. Its state
requests cross shared atomics and execute only on the WM worker; logging synchronously proxies to
the browser main thread. That exposed a stale device-free link dependency, so the present counter
now lives inline in `GHOST_WebDisplayState.hh` and remains shared by the system and WebGPU context
without requiring the WebGPU translation unit in a no-context harness.

## Focused evidence

- The predecessor fails at the absent state switch (`20260825T152201-1446090`). Final and exact
  `6d71197` source checks cover normal, maximized, minimized, and fullscreen plus seven mutations
  (`20260825T152231-1446322`, `20260825T154018-1468103`).
- The final real-GHOST Wasm harness builds in the product thread/filesystem topology
  (`20260825T153229-1458426`). A headed Chromium run enters fullscreen, rejects minimization
  without leaving it, exits through GHOST, and accepts the page-fill maximized mapping
  (`20260825T153302-1459195`).
- The broader Dawn-pinned native/wasm32 transaction suite remains byte-identical at 5,139 bytes,
  SHA-256 `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`;
  seven fullscreen mutations fail closed and the bound source SHA-256 is
  `aa82ec90bff83e12d67b73cff726d8d860ceddb5909882ed80280a633793f9f9`
  (`20260825T153352-1460743`).

## Product and gate evidence

- The optimized `blender_browser` relinks through locked Ninja and ends exact no-work
  (`20260825T153416-1462203`, `20260825T153503-1462579`). Strict OFF preflight passes at
  JavaScript 667,333 bytes/SHA-256 `810df547b2ce`, Wasm 119,017,029 bytes/`f25ee6dd521a`, and data
  167,143,248 bytes/`09e58a25849e` (`20260825T153520-1462818`).
- The same relinked product reaches `WM_main` under the headed fallback-only diagnostic, advances
  77 idle ticks, turns trusted input into four ticks and one presentation, and reports zero
  stage-1/import failures, destroyed-texture submission rejections, present transaction
  rejections, or device loss (`20260825T153535-1462943`).
- Canonical replay remains green for 303 paths/256 active patches at SHA-256 `26b584627afe`, and
  final REUSE 6.2.0 covers 2,547/2,547 files (`20260825T153750-1466138`,
  `20260825T154141-1469368`). Required M4 remains red at its unchanged unsupported hardware
  binding (`20260825T153630-1464447`); container-backed regression restores M0 6/6 green while
  M1-M8 retain their existing strict boundaries (`20260825T153716-1465138`).

The headed GPU run is diagnostic-nonreceipt evidence. It binds no adapter, profile, split product,
pixel receipt, result promotion, dependency decision, deferral, tolerance, golden, blacklist, or
promise. The blocker remains `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa
dzn rejected by Dawn)`; dzn and Windows were not attempted, and WSL was not restarted.
