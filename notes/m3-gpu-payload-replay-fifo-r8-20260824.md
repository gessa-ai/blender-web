<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU pending-payload replay FIFO R8 — 2026-08-24

## Outcome

Implementation commit `703de76` and numbered patch 0246 close R8's concurrent retained-payload
replay defect. `PendingBufferPayloadQueue` now admits one replay drainer, which reserves every
available deque entry in frontend order and absorbs a concurrently retained tail before releasing
ownership. A per-entry drain generation prevents a synchronously rejected completion from being
selected repeatedly by the same drainer while preserving it for a later clean-epoch retry.

## Evidence

- With patch 0246 reversed in an isolated source copy, the forced E1/E2/E3 interleaving fails the
  one-drainer contract in both native and wasm32 (`20260824T020453-3585342`,
  `20260824T020525-3585875`). The canonical upstream postimage was not changed for this control.
- Root and descendant-CWD runs pass 20 byte-identical native/wasm32 contracts. The pending-payload
  slice executes 12 payloads across five cases, requires E1/E2/E3 reservation and execution order,
  and leaves E3 as the final overlapping bytes. Evidence is 1,818 bytes at SHA-256
  `5ef1682105d4562ba45eee10cf4f9779cbebd7791bf0258864b98e8248876092`; shipping inputs are
  SHA-256 `cca5209fca4d4aee323fb20105068f29a349ae22724948f0cf804cee9d43f09a`
  (`20260824T020911-3588423`, `20260824T020932-3590106`).
- Ambient Node 25.1.0 is rejected before its requested evidence path exists
  (`20260824T021138-3591744`).
- Numbered patch 0246 is 6,382 bytes at SHA-256
  `bb5481655653807b39972b7f567cdc96e60a316e2c8e8a4a2c282b20efd13d93` and passes isolated
  reverse/forward exact-byte round trip (`20260824T020849-3588222`). The canonical freezer and
  clean-pin replay retain 257 paths and 20,258 entries at patch SHA-256
  `2b7df81dec14e5f1ecea6d758e49f55fe91547531c460a1fada51ea2b843715d` and manifest SHA-256
  `4bb880f4cd0e56b6a7e517983de03e97697f1b1d8ba03c1852f738a31ec8ecda`
  (`20260824T020705-3587272`, `20260824T020854-3588300`).
- The real optimized `blender_browser` target rebuilds and ends locked no-work
  (`20260824T020958-3590786`, `20260824T021046-3591261`). OFF preflight binds a 657,928-byte
  JavaScript file, 118,765,535-byte Wasm, and 167,143,248-byte data file
  (`20260824T021110-3591476`). Final REUSE 6.2.0 is 2,248/2,248 GREEN
  (`20260824T021644-3596713`).
- Required M3 remains honestly red only at the absent fresh strict candidate
  (`20260824T021204-3593020`). Container-backed regression restores M0 6/6 green while M1-M8
  retain their existing strict-receipt, split-product, browser, run-label, hardware, and release
  boundaries (`20260824T021221-3593210`). No result was promoted.

## Boundary

This is device-free CPU/source and compile/link proof. It creates no accepted hardware adapter,
browser/pixel receipt, profile, split product, result promotion, dependency decision, new deferral,
tolerance, golden, blacklist, or milestone promise. Live proof remains deferred by the named
blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
This iteration did not retry dzn, attempt the staged Windows path, or restart WSL.
