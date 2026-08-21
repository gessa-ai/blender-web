<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T6 readback-capacity Linux reconciliation

## Outcome

The canonical WebGPU readback registry's terminal exact-ticket limit now has a
device-free native/wasm32 parity contract. The seventh integrated-buffer
contract fills all 256 exact-record slots with real failed requests, requires a
257th request to fail closed, retires every other record, refills exactly the
128 released slots, restores the cap, and then proves complete retirement and
reuse. It also proves `forget_source()` leaves claimed exact records intact and
that terminal failures create no pending GPU work.

The contract compiles the shipping `wgpu_readback.cc` directly. It does not copy
registry logic into the test and creates no instance, adapter, device, buffer,
map callback, or receipt. The invalid handles deliberately exercise the same
terminal-record path used when an exact request fails validation before WebGPU
allocation.

## Evidence

- Root run: `ledger/buildlogs/20260821T232034-717758.log`.
- Descendant-CWD run: `ledger/buildlogs/20260821T232142-719475.log`.
- Both native Dawn and Node 22.16.0/wasm32 runs emit the same 529 bytes at
  SHA-256 `6ef46d4cb31d34585b194849033da545e3ded3c1c252e19f6fe8e5b9393078fb`.
- The 15 shipping source inputs remain bound at SHA-256
  `45d86d809161ffe78a2778a7a78f6514de79b41b804825316470e332cf9a5cfb`;
  native and Wasm fmt headers remain byte-identical at SHA-256
  `ccaf61c9b5937e0fa97737fb047121c5fca9db34de516b8edfc1d913583e3c8e`.
- Canonical clean-pin replay is green for 257 paths at SHA-256
  `22621d7ee011` (`20260821T232218-720086`), and the locked windowed product is
  exact no-work (`20260821T232215-720031`).
- Exact REUSE 6.2.0 is 2,004/2,004 green
  (`20260821T232440-722563`).

Required M3 remains honestly red for the absent fresh strict candidate
(`20260821T232249-720359`). Container-backed regression keeps M0 6/6 green and
M1-M8 red only on the existing strict-receipt, APPLY/artifact, browser,
run-label, and hardware boundaries (`20260821T232304-720445`). No product or
upstream/GPU implementation, receipt, result promotion, dependency decision,
deferral, tolerance, golden, blacklist, or promise changed; s7 remains live.
