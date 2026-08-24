<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4 R8 GHOST inheritance documentation — 2026-08-24

## Outcome

`GHOST_ContextWGPUWeb.hh` now describes the class that ships: it derives from
`GHOST_Context`, synchronously imports the browser device and presentable bundle prepared on the
WM worker before `main()`, and retains `initAsync()` only as the callback-driven standalone proof
path. The description also names the shared callback/owner execution gate and its destruction
boundary.

The R8 focused runner treats that preamble as source compliance. It normalizes comment leaders,
binds the description to the actual subclass declaration, requires both initialization paths and
the owner-lifecycle boundary, and rejects the retired standalone-class and top-level-await claims.

## Evidence

- The unchanged header fails the new inheritance/lifecycle contract before evidence allocation
  (`20260824T035759-3694810`).
- The final pre-commit and exact post-commit focused runs pass the documentation binding, all eight
  shipping callback roles, the native-ASan/wasm32 lifecycle matrix, and both unsafe controls
  (`20260824T035926-3695380`, `20260824T040229-3698902`).
- Canonical integrated native/wasm32 parity remains 38 contracts and 4,813 bytes at SHA-256
  `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`, with shipping inputs
  SHA-256 `a1645be80b61251112b756a0b9633e7a5b2c2f68cafed3aa26256fbe672e0017`
  (`20260824T040351-3701552`).
- The real `blender_browser` rebuild completed, then the locked rebuild and dry run were exact
  no-work (`20260824T035942-3695605`, `20260824T040051-3696931`,
  `20260824T040055-3696961`). OFF preflight binds the 657,928-byte JavaScript,
  118,772,391-byte Wasm, and 167,143,248-byte data product (`20260824T040113-3697175`).
- Canonical replay retains 257 paths and 224 active patches at SHA-256 `b71513bc33c9`
  (`20260824T040146-3697799`). Final REUSE 6.2.0 is green for all 2,255 files
  (`20260824T040507-3703787`).
- Required M4 remains honestly red only at `browser_pixels` (`20260824T040242-3699395`). The
  documented container-backed recovery restores M0 to 6/6 green, and final regression leaves
  M1–M8 on their existing strict-receipt, split-product, browser, run-label, hardware, and release
  boundaries (`20260824T040303-3699868`, `20260824T040310-3700540`).

## Boundary

This is documentation and source-compliance hardening. It changes no GPU or GHOST runtime behavior
and creates no accepted adapter, device, browser, or pixel receipt. Mesa dzn and Windows were not
attempted, WSL was not restarted, and the live receipt remains blocked by no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
