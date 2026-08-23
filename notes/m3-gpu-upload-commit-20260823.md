<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU upload commit contract — 2026-08-23

## Outcome

Commit `c9cddfa` and patch 0242 close R7's premature upload-commit defect. Direct queue writes and
staged copy submissions now expose durable pending, accepted, and rejected transaction state.
Callback-owned queue entries retain the exact upload bytes through implementation-scope
completion; rejection preserves them for a clean scheduler epoch. Static VBO dirty/host data and
deferred UBO attached data are released only after acceptance, while buffer-texture, storage, and
push-constant callers replay retained work before subsequent use.

## Evidence

- The unchanged upload path fails the new source-bound contract before evidence allocation because
  it has no `BufferUpdateTransaction` (`20260823T184542-3171134`).
- Final root and descendant-CWD native/wasm32 runs pass 19 byte-identical integrated contracts,
  including 12 buffer-update cases and nine ordered payloads. Delayed direct completion remains
  pending, direct and staged validation/submission rejection retain caller-independent bytes, and
  a deferred UBO survives rejection before committing its cleanup on retry. Evidence is 1,686
  bytes at SHA-256
  `500ac8bcb9dd4f1512132024736b527c70546ce4117254acadf7055f4fe2fbb1`; exact shipping inputs are
  SHA-256 `ce194ab7853bd8c17e7c00fe7a796533cb4488d400576852e855ee0f876505b3`
  (`20260823T191004-3196486`, `20260823T190240-3189266`). The exact vertex frontend suite also
  remains byte-identical (`20260823T190828-3194451`).
- Pinned Dawn on llvmpipe returns a real non-null validation error for an invalid direct upload,
  leaves the transaction rejected with its sentinel retained, and accepts the valid-offset retry
  in a clean epoch (`20260823T190252-3189828`, `20260823T190259-3189827`). The transcript remains
  `SOFTWARE_CONTROL_NON_RECEIPT`.
- Numbered patch 0242 is 27,369 bytes at SHA-256
  `abd496b7c0e6c4735e288039f7dc28d4f80102641d783abd2ffff8dce3e09fde` and passes isolated
  reverse/forward exact-byte round trip. Canonical freeze/replay retains 257 paths and 20,258
  entries; its 1,752,897-byte patch is SHA-256
  `bfbcd7cbd0f83ed905b6300cf6c4a778c23e7033c3391e0a45dae3c50148d3db`, with byte-identical
  3,477,335-byte manifests at SHA-256
  `0acaa9db46c0a81a5fb3b43ed781d7c5a53abe335fd6413a7d9d9f30b8edd6ca`
  (`20260823T190819-3194349`).
- The real `blender_browser` target rebuilds and ends locked no-work
  (`20260823T190329-3190172`, `20260823T190845-3195171`). OFF preflight binds the 657,928-byte JS,
  118,744,752-byte Wasm, and 167,143,248-byte data product (`20260823T190431-3191602`).
- Final REUSE 6.2.0 is green for all 2,228 tracked files, including this record
  (`20260823T191553-3201642`).
- Required M3 remains red only for the absent fresh strict candidate
  (`20260823T191030-3197227`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict-receipt, product, browser, run-label, hardware, and release boundaries
  (`20260823T191216-3198654`). No gate result was promoted.

## Boundary

This is device-free CPU/source and compile/link proof. It creates no accepted hardware adapter,
browser/pixel receipt, profile, split product, result promotion, dependency decision, new
deferral, tolerance, golden, blacklist, or milestone promise. Live hardware proof remains deferred
by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn
rejected by Dawn). This iteration did not retry dzn, attempt the staged Windows path, or restart
WSL.
