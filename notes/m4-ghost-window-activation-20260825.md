<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web-window drawing-context activation — 2026-08-25

## Outcome

`GHOST_WindowWeb::activateDrawingContext()` now delegates through Blender's stock `GHOST_Window`
implementation, which invokes the owned `GHOST_ContextWGPUWeb` and returns its real device-aware
status. The retired bring-up stub returned `GHOST_kFailure` unconditionally even though window
activation is called throughout `wm_draw.cc` and `wm_window.cc`.

The change is `8942b4e`. It touches no upstream source, adapter classification, receipt, result,
deferral, tolerance, golden, blacklist, or promise.

## Evidence

- The predecessor fails the new source contract before evidence acceptance
  (`20260825T142150-1386316`). The final contract passes the production path and rejects three
  hard-coded/wrong-target mutations (`20260825T142200-1386403`).
- The complete integrated native/wasm32 GHOST/WebGPU matrix passes at 5,139 identical bytes,
  SHA-256 `94588fb0021d` (`20260825T142231-1386684`).
- Locked Ninja relinks the real product and then reports exact no-work
  (`20260825T142246-1388001`, `20260825T142332-1388381`). OFF preflight binds the 659,927-byte JS,
  119,016,617-byte Wasm, and 167,143,248-byte data artifacts (`20260825T142340-1388472`).
- The same artifact reaches sustained `WM_main` progress at `/`, and trusted input advances both
  ticks and presentation with zero stage-1/import/submission/transaction/device-loss failures
  (`20260825T142423-1389633`). This fallback-software run is diagnostic-nonreceipt.
- Final REUSE 6.2.0 is green (`20260825T142807-1393343`). Required M4 remains red at the unchanged
  unsupported hardware binding (`20260825T142520-1390431`); container-backed regression restores
  M0 6/6 green and retains the existing strict downstream boundaries
  (`20260825T142600-1390971`).

## Hardware boundary

No dzn or Windows path was attempted and WSL was not restarted. No adapter, browser profile,
split product, pixel receipt, or milestone receipt was created. The blocker remains **no conformant
hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**.
