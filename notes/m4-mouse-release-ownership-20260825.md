<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 mouse-release ownership — 2026-08-25

## Outcome

Commit `d964a5f` prevents a canvas-owned drag from leaving Blender's mouse button permanently held
when the pointer is released outside the canvas. Mouse-down remains canvas-scoped. Mouse-up is
captured at `window`, but reaches GHOST only when `GHOST_SystemWeb` still owns the matching button;
unrelated page releases remain unconsumed. Because Emscripten makes `targetX/Y` relative to the
listener target, the terminal event is translated from viewport `clientX/Y` back into canvas space.
Registration rollback and removal use the same window target.

## Focused and integrated evidence

- The predecessor real `PROXY_TO_PTHREAD` browser harness retained the left-button bit after a
  press on the canvas and release over the neighboring panel, timing out at the state-reset boundary.
  The final exact-commit browser case delivers `ButtonUp`, clears the bit while canvas focus remains,
  and suppresses a later unowned window release (`20260825T233639-23620`).
- The focused contract covers canvas press ownership, window capture/removal, held-button admission,
  and canvas-coordinate normalization; all 12 mutations reject (`20260825T233639-23619`). The
  existing lifecycle contract remains green across 32 registration/disposal mutations.
- The post-commit integrated native/wasm32 matrix remains byte-identical at 5,305 bytes,
  SHA-256 `98f9c1ca84af8eff87f9bac77d839cb7305f95b34a718c5fdc8b50476deae8a1`, with
  source SHA-256 `09d745dcddbe5bb3e31c2ab23059796f44629493a5fe0a7958e8fe7385a2ef05`
  (`20260825T233651-23888`). Focus, repeated window replacement, keyboard ownership, Pointer Lock,
  clipboard, IME, and custom-cursor real-worker browser cases also remain green.

## Product and gate evidence

- The optimized product relinked through `scripts/ninja-locked.sh` and then ended exact no-work
  (`20260825T233114-17477`, `20260825T233651-23889`). Strict OFF preflight binds 679,666-byte
  JavaScript, 119,032,936-byte Wasm, and 167,143,248-byte data at SHA-256
  `c762562596962d2a2655f3bf9d5cad30eb75d94eed5376a5a1aedb68a86f0709`,
  `b6390b543af980c0d8969db147245ebc92db322880a9cfdcc37b6c5cb918e312`, and
  `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`
  (`20260825T233717-25301`).
- The canonical `/` entry (which serves `platform_web/shell/windowed.html`) reaches running
  `WM_main`, advances 76 idle ticks and 9 trusted-input ticks with two new presents, and reports zero
  stage-1/import/submission/transaction/device-loss failures (`20260825T233300-19383`). Its forced
  fallback-software adapter makes this diagnostic-nonreceipt evidence only.
- Canonical replay and REUSE 6.2.0 are green (`20260825T233447-21754`,
  `20260825T234025-28419`; 2,594/2,594 files). Required M4 remains red at its unsupported hardware
  binding, and the container-backed regression restores M0 6/6 while M1-M8 preserve their strict
  receipt/product/browser/hardware/run-label/release boundaries at 23:33:59Z.

No adapter, profile, split product, live receipt, result promotion, dependency, deferral, tolerance,
golden, blacklist, or promise changed. dzn and Windows were not attempted, WSL was not restarted,
and s7 remains externally blocked by `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none;
Mesa dzn rejected by Dawn)`.
