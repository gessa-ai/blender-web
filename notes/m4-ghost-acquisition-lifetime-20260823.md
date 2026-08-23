<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST fallback acquisition lifetime — 2026-08-23

## Outcome

Implementation commit `8822ef2` closes the fallback adapter/device acquisition use-after-free.
Both spontaneous WebGPU request completions now retain one shared owner-lifetime gate instead of
capturing the raw `GHOST_ContextWGPUWeb`. Context destruction invalidates that gate before every
other callback boundary, so a delayed adapter result cannot start a device request and a delayed
device result cannot access owner state, complete initialization, or start surface setup.

## Diagnosis and implementation

The previous destructor invalidated only `callback_lifetime_`, which protects asynchronous
resource and present transactions. `RequestAdapter` and `RequestDevice` independently captured
`this`, never consulted that token, and could therefore run after the context had been deleted.
The earlier device-loss test covered a separate shared atomic callback and could not expose either
acquisition callback.

`OwnerCallbackLifetime` keeps the non-reference-counted owner behind a shared validity gate.
Browser completions capture only the gate and route all owner work through `deliver()`; the
destructor publishes `nullptr` first. The focused regression delays each completion past a
context-probe destructor, while a deliberately unsafe raw-owner control demonstrates that the
native AddressSanitizer seam detects the original heap use-after-free.

## Evidence

- The unchanged shipping source rejects before evidence allocation because destruction lacks the
  acquisition invalidation boundary (`20260823T194518-3227957`). Ambient Node v22.22.1 is also
  rejected in favor of pinned Node v22.16.0, and its requested evidence path remains absent
  (`20260823T195024-3234972`).
- Final root and descendant-CWD runs preserve the 36-contract integrated native/wasm32 output at
  4,421 byte-identical bytes, SHA-256 `6858f710cbf7`, and shipping-source SHA-256
  `80de21aa8bb6`. The separate native-ASan/wasm32 lifetime result is 157 byte-identical bytes,
  SHA-256 `64dcdc822b7b`, with four live/delayed cases and zero owner access, completion, or follow-on
  requests after invalidation (`20260823T194603-3228849`, `20260823T194829-3232161`). Accepted
  native and wasm stderr are empty; the unsafe native control reports the expected
  `AddressSanitizer: heap-use-after-free`.
- The standalone emdawnwebgpu context compiles (`20260823T194937-3234577`). The real
  `blender_browser` rebuild and exact locked no-work check pass (`20260823T194650-3231385`,
  `20260823T194903-3234184`). OFF preflight binds the 657,928-byte JavaScript, 118,752,492-byte
  primary Wasm, and 167,143,248-byte data product (`20260823T194932-3234501`).
- Canonical replay retains 257 paths and reports SHA-256 `f6c3e3897b13`
  (`20260823T194946-3234720`). Final REUSE 6.2.0 is green for all 2,232 tracked files,
  including this record (`20260823T195450-3240092`).
- Required M4 remains red at the unchanged unsupported browser binding. Container-backed
  regression at `2026-08-23T19:51:10Z` restores M0 to 6/6 green while M1-M8 retain their strict
  receipt, split-product, browser, run-label, hardware, and release boundaries.

## Boundary

This is lifetime, source-binding, compile/link, and AddressSanitizer proof. It creates no accepted
hardware adapter, browser surface/pixel receipt, profile, split product, or milestone receipt. No
result promotion, dependency decision, new deferral, tolerance, golden, blacklist, or promise
changed. This iteration did not retry dzn, attempt the staged Windows path, or restart WSL. Live
proof remains deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA
ships none; Mesa dzn rejected by Dawn).
