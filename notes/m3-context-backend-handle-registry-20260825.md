<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 context backend-handle registry - 2026-08-25

## Outcome

Patch 0279 (`4b28c64`) replaces `WGPUContext`'s three independently mutable process-static
instance/device/queue fields with one locked latest-live-owner registry. Async shader compilation
now takes one coherent tuple. Destroying an older context cannot clear a newer context's handles,
and destroying the newest overlapping context restores the previous live owner instead of leaving
the compiler with null handles.

## Evidence

- The predecessor fails before evidence allocation because the required owner registry is absent
  (`20260825T134328-1347863`). Final native and wasm32 executions pass the same 40 contracts at
  5,139 bytes, SHA-256 `94588fb0021d`, including seven coherent publication, republish, both-order
  teardown, restoration, and idempotent-cleanup cases (`20260825T135009-1353795`).
- Numbered patch 0279 applies to the exact patch-0278 four-file postimage, reverse-applies to the
  live source, and reproduces all four final files byte-for-byte. The independent freezer and
  replayer retain 303 canonical paths and 20,258 source entries at patch SHA-256
  `26b584627afe` and manifest SHA-256 `78735cca4a15`
  (`20260825T134914-1353139`, `20260825T135505-1360328`).
- The real `blender_browser` relinks and then proves locked no-work
  (`20260825T135049-1356177`, `20260825T135141-1356666`). The resulting JavaScript, wasm, and data
  are 659,848, 119,016,606, and 167,143,248 bytes; the headed software-fallback diagnostic reaches
  sustained WM/input/presentation progress with zero rejected submission, transaction, or device
  loss (`20260825T135217-1357003`).
- REUSE 6.2.0 covers all 2,532 files (`20260825T135617-1361620`). Required M3 remains red only for
  the absent fresh strict candidate (`20260825T135250-1357487`); the authoritative container-backed
  regression restores M0 to 6/6 green while M1-M8 retain their existing strict receipt, product,
  browser, hardware, and release boundaries (`20260825T135320-1358731`).

## Boundary

The registry contract is device-free, and the headed run uses fallback software only. Neither
binds an adapter, draw, pixel, profile, split product, or milestone receipt. Strict live proof
remains blocked by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn
rejected by Dawn)**. No result promotion, dependency, deferral, tolerance, golden, blacklist, or
promise changed; dzn and Windows were not retried, and WSL was not restarted.
