<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 context-owned pipeline caches - 2026-08-25

## Outcome

Patch 0278 (`c5f5565`) moves the batch render-pipeline pool, immediate render-pipeline pool, and
indexed-triangle-fan compute-pipeline cache from process-static storage onto `WGPUContext`. A
replacement context/device therefore creates its own WebGPU handles instead of looking up handles
retained from an earlier device. The two render pools remain separate, preserving their previous
cache partition, and reverse member destruction releases all three caches before the queue and
device handles.

## Evidence

- The predecessor fails the source guard before compilation because all three caches are static
  (`20260825T130735-1310098`). The final root and descendant-CWD native/wasm32 runs pass 39
  byte-identical contracts at 4,976 bytes, SHA-256
  `e19bd09d2f4dd7da5e34b0a6530dd14347782ffe8903d15e9ef9e386baaeba3d`. The new eight-case
  contract first reproduces cross-device reuse from one shared cache, then proves independent
  batch, immediate, and indexed-fan creation for two sequential context owners
  (`20260825T132808-1332664`, `20260825T133118-1337181`).
- Numbered patch 0278 is 7,580 bytes at SHA-256
  `5b81744447da2fb79b2bcc2908be73a321d70bf70ba7672672466e2c0e280c29`; isolated indexed replay
  applies it to the previous canonical source and byte-matches all five resulting source files
  (`20260825T133056-1336200`). The refreshed freezer retains 303 paths and 20,258 live/replay
  entries at canonical SHA-256
  `888e0e2c8f0534faf72e15a020f6616f06afc60e06eac508c114735dea94e114`, with identical manifest
  SHA-256 `07ad279b97bb5330fbb816bc1350e03bd7f2f9b3a5f1fcd0e6657903fd542ea2`
  (`20260825T132715-1331985`, `20260825T132932-1335489`).
- The real `blender_browser` rebuild and exact locked-Ninja no-work pass
  (`20260825T132825-1334111`, `20260825T132917-1335400`). OFF preflight binds the 119,013,782-byte
  primary Wasm, 659,848-byte JavaScript, and 167,143,248-byte data artifact
  (`20260825T132943-1335614`). The same Wasm/JS identities are SHA-256
  `a2978358209191f613396fe3fd06aa9594e9bbd0be8a794464def946c5a0bb0f` and
  `0dc6d67b0e2b7ff866119218d8fe0b8ed341002702c9c0798fc2b58df198b429`; their headed software
  diagnostic sustains WM/input/presentation with zero preinit, submit, transaction, or device-loss
  failures (`20260825T131726-1322022`).
- REUSE 6.2.0 covers all 2,531 files (`20260825T133251-1338859`). Required M3 remains red for the
  absent fresh strict candidate; container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict receipt, product, browser, hardware, and release boundaries
  (`2026-08-25T13:24:26Z`).

## Boundary

The cache contract is device-free, and the headed run uses fallback software only; neither binds
an adapter, draw, pixel, profile, split product, or milestone receipt. Strict live proof remains
blocked by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by
Dawn)**. No result promotion, dependency, deferral, tolerance, golden, blacklist, or promise
changed; dzn and Windows were not retried, and WSL was not restarted.
