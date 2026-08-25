<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 Python window-screenshot browser deferral — 2026-08-25

## Outcome

Commit `ea8dc3c` and patch 0275 close the last synchronous WM-capture source residual without
misrepresenting Blender's Python API. Native builds retain the stock `Window.screenshot()` method:
argument parsing, background-mode error, crop and alpha handling, and the immediate owned
`memoryview` return are unchanged. In the browser build the same method parses its arguments, then
raises an actionable `RuntimeError` before `WM_window_pixels_read`; the message points file-capture
callers to the already-asynchronous `bpy.ops.screen.screenshot()` continuation.

This is an explicit API deferral, not an asynchronous memoryview, a future disguised as the stock
return, or a blocking event-loop pump. Under ADR-006, the WM worker cannot wait for WebGPU mapping:
blocking the worker also blocks the `AllowSpontaneous` completion, and JSPI/Asyncify are disabled.

## Source and contract evidence

- The pinned Linux oracle preserves the public `screenshot(*, region=None, use_alpha=False)` method
  and its `memoryview` return documentation (`20260825T084043-1051102`).
- Final post-commit focused receipt `20260825T084031-1050819` passes the exact two-source policy,
  12 fail-closed mutations, isolated patch reverse/reapply, and the real native and windowed-wasm
  `bpy_rna_wm.cc` translation units. The source digest is
  `sha256:7466902b913503e1d462f86b02a4655764549d1f63d93130d157c0314efe8865`; patch 0275 is
  `sha256:f8c5deca973aea49fb516db78ab1f36ceeaaf98e4806e58585c8fbf67d72f1c5`.
  Undefined-symbol inspection finds `WM_window_pixels_read` in the native object and not in the
  wasm object; string inspection finds the browser error only in the wasm object.
- Aggregate receipt `20260825T084031-1050820` remains byte-identical across native and wasm32 at
  627 bytes / `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`.
  Its 50-source verifier rejects 48 mutations, reports zero remaining browser-sync caller families,
  and records `python_window_screenshot_memoryview` separately as deferred rather than converted.

## Integration evidence

- Canonical clean-pin replay passes with 303 paths and 252 active numbered identities at snapshot
  `sha256:4e65ce97d39543239ee062be3decaf51ac2e3917e3042a18c430a8410d7d847d`
  (`20260825T084138-1051608`).
- The real `blender_browser` rebuild completes and ends locked no-work
  (`20260825T083512-1045181` / `20260825T083634-1046710`). OFF preflight binds 658,702-byte
  JavaScript, 118,997,490-byte wasm, and 167,143,248-byte data artifacts
  (`20260825T083634-1046711`).
- The six-tier hardware deferral contract retains the exact named WSL2 blocker
  (`20260825T084138-1051607`). REUSE 6.2.0 is green for 2,512/2,512 tracked files
  (`20260825T084138-1051606`).
- Required M5 remains honestly red only at the absent
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary
  (`20260825T083808-1048140`). Container-backed regression restores M0 6/6 green while M1–M8 retain
  their existing strict receipt, browser, split-product, run-label, hardware, and release boundaries
  (`20260825T083824-1048326`).

`ledger/deferred.json` now marks the source family as closed with one explicit browser API deferral.
Revisit the immediate-memoryview contract only if ADR-006 deliberately changes or Blender gains an
upstream-compatible asynchronous pixel-view API. Live C1/M5 acceptance still has the separate named
blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
No adapter, browser profile, split product, live receipt, result promotion, dependency decision,
tolerance, golden, blacklist, or promise changed. dzn and Windows were not attempted, and WSL was
not restarted.
