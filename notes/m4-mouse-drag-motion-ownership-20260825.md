<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 mouse drag-motion ownership — 2026-08-25

## Outcome

Commit `303847a` completes the pointer-ownership lifecycle begun by the outside-release fix.
Mouse-move is now captured at `window`, but an outside-canvas point reaches GHOST only while the
canvas interaction still owns at least one tracked button or Pointer Lock is active. Ordinary page
motion remains unconsumed. Window-targeted motion and release share canvas-relative coordinates
derived locally on the WM worker from one coherent DOM rectangle snapshot refreshed at listener
registration and resize; there is no per-motion main-thread proxy and no dependency on Emscripten's
unpopulated deprecated `canvasX/Y` fields.

## Fail-first and focused evidence

- The predecessor real WasmFS + `PROXY_TO_PTHREAD` harness delivered the in-canvas
  `CursorMove x=468 y=160` and `ButtonDown`, then produced no cursor event after the trusted pointer
  moved over the neighboring panel. The existing window-captured release still arrived, isolating
  the defect to continuous motion rather than button or focus ownership.
- The exact-commit browser case now observes a canvas-relative position beyond the right edge,
  delivers the matching release with canvas focus unchanged, and suppresses later unowned
  window-level motion and release (`ledger/buildlogs/20260826T000459-54738.log`).
- Window disposal/replacement, focus-state retirement, Pointer Lock outcome/relative motion, and
  canvas keyboard ownership remain green in the real worker topology
  (`20260826T000508-54911`/`54912`/`54916`/`54923`).
- The focused source contract rejects 22 registration, removal, owned-state, coordinate,
  rectangle-snapshot, resize, and live-evidence mutations. The integrated listener lifecycle still
  rejects 32 mutations, and native/wasm32 output remains byte-identical at 5,305 bytes, SHA-256
  `98f9c1ca84af8eff87f9bac77d839cb7305f95b34a718c5fdc8b50476deae8a1`, with source SHA-256
  `89bdc4183535605194bdbb17a0dbcf8080896b593f930b0edb8c360ed2844169`
  (`ledger/buildlogs/20260826T000516-55454.log`).

## Product and gate evidence

- The optimized windowed product relinked through locked Ninja and then ended exact no-work
  (`20260826T000147-51914`, `20260826T000529-56770`). Strict OFF preflight binds 679,767-byte
  JavaScript, 119,033,947-byte Wasm, and 167,143,248-byte data at SHA-256
  `c64e2c9b008e6988a72a9c05e870617d0a99e305e8a64f20ab269a898f270d6a`,
  `d492b786a7d9c3e5386521b95d9d15fdbd854706e929eca4a8663a4c02281ee0`, and
  `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`
  (`ledger/buildlogs/20260826T000237-52450.log`).
- The canonical `/` entry reaches running Blender on the forced fallback-software diagnostic,
  advances 78 idle ticks and 10 trusted-input ticks with two new presents, and reports zero
  stage-1/import/submission/transaction/device-loss failures
  (`ledger/buildlogs/20260826T000250-52565.log`). This is diagnostic-nonreceipt evidence only.
- Canonical clean-pin replay remains green across 303 paths and 257 active patches
  (`ledger/buildlogs/20260826T000322-53094.log`). The authoritative container-backed regression
  restores M0 6/6 while required M4 remains red at the unsupported hardware binding and M1-M8
  retain their strict existing receipt/product/browser/hardware/run-label/release boundaries
  (`ledger/buildlogs/20260825T235854-47088.log`).

`platform_web/shell/windowed.html`, served at `/` by `scripts/serve-web.sh`, remains the intended
native-app product entry. No adapter, profile, split product, hardware receipt, result promotion,
dependency, deferral, tolerance, golden, blacklist, or promise changed. Mesa dzn and Windows were
not attempted, WSL was not restarted, and s7 remains externally blocked by
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
