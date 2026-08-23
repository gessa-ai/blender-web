<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 batch command transaction - 2026-08-23

## Outcome

Patch 0214 (`036e976`) makes all four batch-render submission paths fail closed at their
remaining command-handle boundaries. Direct and indirect draws now reject a null command encoder
before ordinary or multi-viewport render-pass creation, and reject a null finished command buffer
before queue submission. Existing pipeline, framebuffer load, bind-group, geometry, draw, and
successful submission behavior is unchanged.

## Evidence

- The unchanged source fails the exact source contract at the first missing multi-viewport encoder
  guard, before its evidence directory is allocated (`20260823T015655-2202523`).
- Final root and descendant-CWD native/wasm32 runs pass all 18 integrated contracts with
  byte-identical 1,773-byte output, SHA-256
  `0f980496bd0627a8e3fedce03260f1cf560d84c9356d889d5945cea95fa029f7`, while the exact source
  digest is `40da7cba2e5856038049969467e3ac9d42c7f237e96e85ab415e1df30d2f800e`
  (`20260823T015945-2205589`, `20260823T020013-2206406`). The source-order check uniquely binds
  encoder creation, guard, pass creation, finish, guard, and submission in each of the four paths.
- Ambient Node 25 is rejected before evidence allocation (`20260823T020044-2207234`).
- The canonical freeze/replay retains 257 paths and 20,258 entries. Its 1,657,277-byte patch is
  SHA-256 `05927f8996a7846cdfdf8f736a6560bddba211ee9056cef2186389ad3caaf0ff`; live and replay
  manifests are byte-identical at SHA-256
  `5fb28897e4401cdeb2533f15f425a230ade9aa9809182f69b5b204607a726e38`
  (`20260823T015835-2204060`, `20260823T015932-2205450`). Numbered patch 0214 is 2,806 bytes,
  SHA-256 `6393d274da84034c0d7cae9488e5bcef5dcf51898e9c7f6347ad72f46d352c53`, and reverse-applies
  cleanly.
- The real `blender_browser` build recompiles `wgpu_batch.cc`, relinks `libbf_gpu.a` and the
  browser, then reaches exact locked-Ninja no-work (`20260823T020105-2207830`,
  `20260823T020150-2208226`). OFF preflight binds the resulting 118,072,869-byte primary Wasm
  (`20260823T020200-2208316`).
- REUSE 6.2.0 covers 2,157/2,157 files. Required M3 remains red only for the absent fresh strict
  candidate (`20260823T020214-2209199`); final container-backed regression restores M0 6/6 green
  while M1-M8 retain their existing strict-receipt, APPLY/product, browser, run-label, hardware,
  and independent M8 size/latency boundaries (`20260823T020335-2209883`).

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, adapter, device, pass,
batch draw, submission, pixel, or browser receipt. Live proof remains blocked by **no conformant
hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result promotion,
dependency decision, deferral, tolerance, golden, blacklist, or milestone promise changed.
