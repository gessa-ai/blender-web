<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU indirect draw ranges — 2026-08-22

## Outcome

Patch 0187 makes WebGPU's emulated multi-draw path prove the complete indirect-command byte span
before it builds a pipeline or opens a render pass. Invalid signed inputs, alignment, command
geometry, arithmetic, or allocation bounds now produce one atomic no-draw decision. A zero stride
uses the API's documented tightly-packed rule instead of repeatedly addressing the first command.

## Diagnosis and implementation

`gpu::Batch` exposes signed `count`, `offset`, and `stride` inputs and points the public API at the
OpenGL multi-draw contract (`upstream/source/blender/gpu/GPU_batch.hh:94` and `:360`). The previous
WebGPU loop converted each computed offset to `uint64_t` as it issued the call. It therefore let a
negative value become a huge offset, treated zero stride as a repeated command, and delegated
alignment and final-command bounds to Dawn only after pipeline/pass work had started.

The pinned Dawn contract requires every indirect offset to be four-byte aligned and requires the
whole command to fit (`build-dawn/dawn/src/dawn/native/RenderEncoderBase.cpp:201` and `:260`). Its
canonical command sizes are four and five 32-bit words—16 bytes for array draws and 20 bytes for
indexed draws (`build-dawn/dawn/src/dawn/common/Constants.h:75`).

`indirect_draw_span()` now resolves those rules in one pure decision
(`upstream/source/blender/gpu/webgpu/wgpu_pipeline.cc:72`; declaration and immutable result shape
at `wgpu_pipeline.hh:115`). It reserves the fixed final command first, then uses division to prove
`(count - 1) * stride` cannot overflow or cross the allocation. Only a complete candidate replaces
the caller's output. `WGPUBatch::multi_draw_indirect()` invokes it before pipeline creation and
reuses the proven offset/stride for every call (`upstream/source/blender/gpu/webgpu/wgpu_batch.cc:632`
and `:703`).

## Verification

- The unchanged canonical source rejects the new helper/wiring contract before allocating its
  requested evidence directory (`20260822T150642-1572084`).
- Root and descendant-working-directory runs compile the canonical pipeline implementation for
  native and wasm32 and pass nine byte-identical contracts. The new 19-case contract has seven
  accepted and twelve rejected ranges, covering zero/tight and explicit strides, both command
  sizes, overlapping legal strides, nonpositive counts, negative inputs, misalignment, exact-fit
  and one-byte-short allocations, large-count arithmetic, and unchanged output on every rejection.
  The 647-byte stdout has SHA-256
  `d15d04df5ecf343d5c85503da64ddbd7136c30062990ee1f5c93e552d96dfdae`; shipping-source SHA-256
  is `4b68e1fdf325db8d3c4db3615cba552c400b851bb97af6673ae67af9995cb6f9`
  (`20260822T151206-1576131`, `20260822T151936-1583283`).
- A wrong Node identity rejects before its requested evidence directory exists
  (`20260822T151644-1580011`).
- The canonical freezer retains 257 paths and 20,258 entries. Its 1,599,381-byte patch has SHA-256
  `ae6cc793258976707513f3a1fce12306f58e1e98167ab02107b77ecce8b832f5`; live and replay
  manifests are byte-identical at SHA-256
  `7f01714887853e0d5bafa626778c1f6867c42bf6ca8654b9dc7a22f82b805023`
  (`20260822T151108-1574725`). Reverse application and canonical-only replay are also green
  (`20260822T152356-1586853`).
- `blender_browser` relinks through locked Ninja and then reports exact no-work
  (`20260822T151313-1577110`, `20260822T151422-1578427`). Its strict OFF-mode preflight passes
  with a 118,057,162-byte primary Wasm (`20260822T151627-1579918`).
- REUSE 6.2.0 reports copyright and license information for all 2,090 files
  (`20260822T152151-1585283`).
- Required M3 remains red for the absent fresh strict candidate. The final container-backed
  regression keeps M0 6/6 green while M1-M8 retain their existing strict-receipt, product,
  browser, run-label, and hardware boundaries (`2026-08-22T15:18:58Z`).

## Boundary

The contract creates no WebGPU instance, adapter, device, command encoder, render pass, draw,
pixel, browser receipt, or result promotion. It does not bind the software Vulkan adapter. Live
indirect-draw proof remains owned by `M3-LINUX-REPLAY`, still blocked by the named s7
software-adapter condition.
