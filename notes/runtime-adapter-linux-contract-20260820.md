<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Shared browser runtime-adapter contract - 2026-08-20

## Outcome

The seven audited Linux browser producers now refuse to allocate a lane receipt unless the same
browser process exposes one exact accepted hardware WebGPU adapter. The shared JavaScript contract
in `sandbox/m8-launch-gate/runtime_evidence.mjs` opens a temporary secure `file:` document in the
producer's browser context, requests the high-performance adapter, closes the probe page, and
requires all of the following:

- exact `hardware-webgpu-adapter-v1` fields and exact vendor/architecture/device/description keys;
- browser-reported `isFallbackAdapter === false` rather than absent or inferred status;
- a nonempty unmasked detail identity; and
- no SwiftShader, llvmpipe, lavapipe, softpipe, WARP, CPU, or other named software-rasterizer token.

The record is stored as `runtime_adapter` by the USD and files producers, Chrome/Edge matrix,
30-second product bar, performance run, soak, and staged-runtime capture. M7's USD/files receipt
schemas advance to v3. The soak performs a hardware probe before allocating its persistent profile,
then requires the persistent browser context to report the byte-identical adapter before allocating
the result directory. Every other producer probes before its receipt directory/file is created.

`verify_m8.py` independently implements the exact-key, type, host-platform, fallback, masked-info,
CPU/software-token, and empty-match checks. The staged composer validates both source receipts;
M8 additionally requires the adapter to be identical across staged, performance, soak, product,
and Chrome-matrix lanes. `verify_m7.py` independently consumes the staged, files, and USD adapter
records. A valid APPLY artifact therefore cannot turn a later llvmpipe or SwiftShader execution
into a lane PASS.

This closes the audit's producer/consumer contract gap only. No hardware adapter was exposed on
ornith-lab, no browser/APPLY receipt was created, and no result, deferral, tolerance, golden, or
milestone promise was promoted. The s7 hardware-Vulkan/WebGPU blocker remains binding.

## Evidence

- Shared producer/contract self-check: seven allocation-order checks and 35 negative identity,
  adapter, and prior-row cases (`ledger/buildlogs/20260820T235208-2665073.log`).
- Independent M8 consumer: five-lane identity plus adapter equality, one accepted adapter, ten
  adapter mutations, and the existing Linux package verifier
  (`ledger/buildlogs/20260820T235208-2665074.log`).
- M7 aggregate producer/consumer self-check remains green
  (`ledger/buildlogs/20260820T235208-2665078.log`).
- All seven producer self-checks pass with exact Node 22.16.0 and Playwright 1.61.1
  (`ledger/buildlogs/20260820T235208-2665085.log`); all nine JavaScript and three Python sources
  parse cleanly (`ledger/buildlogs/20260820T235208-2665093.log`).
- The live bundled Chromium software path is rejected by the shared contract without allocating a
  receipt (`ledger/buildlogs/20260820T235244-2665681.log`).
- REUSE 6.2 covers all 1,937 files (`ledger/buildlogs/20260820T235208-2665101.log`).
- Required M7 and M8 scopes remain honestly red for absent staged/files/APPLY receipts
  (`ledger/buildlogs/20260820T235259-2665917.log`,
  `ledger/buildlogs/20260820T235303-2666003.log`).
- Container-backed regression restores M0 to 6/6 green and leaves M1-M8 red only on the recorded
  strict-receipt, artifact/APPLY, hardware, and run-label gates
  (`ledger/buildlogs/20260820T235308-2666059.log`).
