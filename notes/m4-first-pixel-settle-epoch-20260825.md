<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 per-window first-pixel settle epoch — 2026-08-25

## Outcome

Commit `f08f451` completes the preserved first-pixel redraw change without synthetic focus or
mouse input. `GHOST_SystemWeb` now captures the monotonic present counter when each canvas window
is published and requests bounded `GHOST_kEventWindowUpdate` events until that window contributes
two submissions. The Emscripten-only `wm_window.cc` handler from patch 0148 turns those events into
screen invalidation, so the cleared surface can be followed by Blender's region composite.

The per-window baseline is required for lifecycle correctness. Comparing the process-global
counter directly with two made the first window work but caused every replacement created after
two prior submissions to retire settling immediately. The helper keeps the established 12-tick
cadence and 180-tick ceiling, treats counter wrap monotonically, and gives each replacement its own
epoch.

## Evidence

- The fail-first source contract rejects the preserved absolute-count implementation before the
  helper exists (`20260825T221056-1862856`). The final four-source contract passes and rejects all
  11 focused mutations (`20260825T221419-1865480`).
- Post-commit native/wasm32 behavior is byte-identical for 14 initial, interval, first/second
  submit, terminal, replacement, timeout, and counter-wrap cases. The complete integrated output
  remains 5,305 bytes at SHA-256 `98f9c1ca84af...`; shipping source SHA-256 is
  `bd29f5dd5e75...` (`20260825T222139-1874151`).
- The optimized `blender_browser` relinked through locked Ninja, then ended exact no-work
  (`20260825T221516-1867326`, `20260825T222154-1875425`). OFF preflight binds 679,421-byte
  JavaScript, 119,032,661-byte Wasm, and 167,143,248-byte data artifacts
  (`20260825T221616-1868299`).
- The intended `/windowed.html` product entry reaches running `WM_main` on the forced
  fallback-software diagnostic, advances 77 idle ticks, and turns trusted input into three ticks
  plus one presentation with zero stage-1/import/submission/transaction/device-loss failures
  (`20260825T221711-1869068`). This is diagnostic-nonreceipt evidence.
- The real WasmFS + `PROXY_TO_PTHREAD` worker harness retains detached disposal, callback rebinding,
  two repeated replacements, bounded hit testing, and current input delivery
  (`20260825T221832-1870008`).

## Gate boundary

Required M4 remains red at the unchanged unsupported hardware binding
(`20260825T221900-1871263`). Authoritative container-backed regression restores M0 to 6/6 green;
M1-M8 retain their strict receipt, split-product, browser/hardware, run-label, and release
boundaries (`20260825T221942-1871813`). Pre-record pinned REUSE 6.2.0 covers all 2,585 files
(`20260825T222014-1872775`).

`windowed.html` remains the intended native-app product entry point; `scripts/serve-web.sh` aliases
its local `/` route to that entry. No adapter, profile, split product, live receipt, result
promotion, dependency, deferral, tolerance, golden, blacklist, or promise changed. Dzn and Windows
were not attempted, WSL was not restarted, and s7 remains externally blocked by `no conformant
hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
