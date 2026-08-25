# M4 sustained WM liveness — 2026-08-25

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

The headed `/windowed.html` software diagnostic now proves continued browser event-loop and
presentation progress instead of accepting entry into `WM_main`. After a bounded wait for the
second real WM tick, it takes two bounded post-running samples, requires a positive tick delta,
sends trusted mouse input to the canvas, and requires both another tick and a new presentation.
Any device loss, page error, presentation failure, import failure, missing fallback status, or
non-diagnostic validation mode rejects the run.

This changes only the diagnostic and its contracts (`17f1265`), not the shipping product. The
result is labeled `diagnostic-nonreceipt`, requires Chromium to report its forced SwiftShader
adapter as fallback software, and cannot bind an M4, adapter, pixel, profile, or hardware receipt.

## Fail-first and diagnosis

The unchanged verifier falsely passed with only `ticks=1` and `device_lost=1`
(`20260825T095746-1120217`). Requiring real deltas then failed with `idleTickDelta=0`,
`inputPresentDelta=0`, and `deviceLost=1` (`20260825T100150-1123528`).

Controlled raw OffscreenCanvas probes isolated the loss to the Linux Chromium software-GPU test
posture: the original launch and an adapter-only override both lost the device, while adding
`--use-gpu-in-tests` kept configure, submission, error-scope settlement, and the device alive
(`20260825T101658-1139953`, `20260825T101659-1140276`,
`20260825T101707-1140622`). The temporary probe and all experimental product-source changes were
removed. The retained verifier explicitly combines `--use-webgpu-adapter=swiftshader` with
`--use-gpu-in-tests` and fails closed unless the product reports `fallback=true` plus
`validation=fallback-diagnostic`.

## Evidence

- Device-free classification passes one positive case and rejects 23 mutations
  (`20260825T102622-1151406`).
- The post-commit headed product run settled at its second tick in 19,533 ms, advanced 71 ticks
  across the idle samples, then advanced 76 ticks and one presentation after trusted input, with
  zero device loss (`20260825T102626-1151438`).
- The integrated native/wasm pipeline remains byte-identical at 4,813 bytes, SHA-256
  `f54305f5871b...`, and includes the classifier contract (`20260825T102700-1151926`).
- Canonical replay, final REUSE 3.3 (2,517/2,517), and the locked real-product no-work build are
  green (`20260825T102721-1153174`, `20260825T102911-1154770`,
  `20260825T102721-1153176`).
- Required M4 remains honestly red at the unchanged unsupported historical binding schema
  (`20260825T102518-1149042`). Container-backed regression restores M0 to 6/6 and retains M1-M8
  red at their existing strict receipt, product, run-label, and hardware boundaries
  (`20260825T102550-1149587`).

The hardware stop condition is unchanged: no conformant hardware Vulkan ICD exists in this WSL2
instance (NVIDIA ships none; Mesa dzn is rejected by Dawn). dzn and Windows were not attempted,
WSL was not restarted, and no receipt, result, dependency, deferral, tolerance, golden, blacklist,
or promise changed.
