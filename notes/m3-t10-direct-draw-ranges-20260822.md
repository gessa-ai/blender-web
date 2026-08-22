<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU direct-draw ranges — 2026-08-22

## Outcome

Patch 0189 resolves Blender's four signed direct-draw parameters before any WebGPU context,
geometry upload, pipeline, or render-pass work. Negative first values and non-positive normalized
counts now fail atomically instead of becoming large unsigned WebGPU arguments. Every valid fan,
indexed, non-indexed, single-pass, and layered draw consumes the same converted plan.

## Diagnosis and implementation

The backend surface carries all four direct-draw values as `int`
(`upstream/source/blender/gpu/GPU_batch.hh:92`). The frontend owns the special zero-count
semantics: it resolves zero vertex count from the batch, maps zero instance count to one, and
returns if either resolved count is still zero
(`upstream/source/blender/gpu/intern/gpu_batch.cc:426-457`). It does not reject negative values.
The Python batch bindings also parse both range APIs as signed integers without a lower-bound
check (`upstream/source/blender/python/gpu/gpu_py_batch.cc:422-445` and `:466-489`).

The previous WebGPU path converted those values independently at six encoder sites, after it had
already acquired a context, uploaded geometry, selected a pipeline, and begun a render pass.
Pinned Dawn's direct API accepts `uint32_t` arguments and performs draw-state and buffer-range
validation only after encoding begins
(`build-dawn/dawn/src/dawn/native/RenderEncoderBase.cpp:103-132`). Thus `-1` could become
`UINT32_MAX`, and a terminal parameter failure was not atomic.

`direct_draw_plan()` now accepts only nonnegative first values and positive counts, preserves the
complete positive `int` domain, and leaves its output unchanged on rejection
(`upstream/source/blender/gpu/webgpu/wgpu_common.hh:99-127`). `WGPUBatch::draw()` resolves it at
method entry (`upstream/source/blender/gpu/webgpu/wgpu_batch.cc:209-217`), and every direct encoder
call plus triangle-fan expansion consumes its fields (`:274-315`, `:458-485`, and `:533-563`).
Positive out-of-bounds geometry remains Dawn's responsibility, matching the public API's explicit
no-bounds-check contract (`upstream/source/blender/gpu/GPU_batch.hh:335-345`).

## Verification

- The unchanged canonical source rejects the absent helper before evidence allocation
  (`20260822T155818-1613831`).
- Root and descendant-working-directory native/wasm32 runs pass eleven byte-identical contracts.
  The direct-draw census accepts 5/16 cases, rejects 11/16 without changing output, and covers
  negative, zero, `INT_MIN`, and `INT_MAX` boundaries. Final stdout is 915 bytes with SHA-256
  `efce7f503baea70d00f4ab46a93bd6b1f2cdf933cdb5a40b7e2c81f793577511`; the 20-source binding
  has SHA-256 `62ce5c0a8d39268aae462fd9ccb1117f3d942c966ed2142f43309f6acc2a5619`
  (`20260822T160341-1618554`, `20260822T160917-1626095`).
- A Node 25 identity mutation fails before its requested evidence directory exists
  (`20260822T160529-1620674`).
- The canonical freezer retains 257 paths and 20,258 entries. Its 1,603,299-byte patch has
  SHA-256 `3614142754032eaef27f717644e2d0d9ac585c7ce117b794bb288f246a6c1d66`; the live/replay
  manifests are byte-identical at SHA-256
  `534301890e496f019ac54e69129be6297a81b4f76168586db1c0e93962c3371a`
  (`20260822T160215-1617188`). Canonical replay and reverse application are green
  (`20260822T160731-1624455`, `20260822T161441-1630151`).
- `blender_browser` rebuilds through locked Ninja and then ends exact no-work
  (`20260822T160408-1619941`, `20260822T160458-1620375`). The strict OFF-product preflight passes
  with a 118,057,133-byte primary Wasm (`20260822T160516-1620590`).
- REUSE 6.2.0 reports copyright and license information for all 2,094 files
  (`20260822T160949-1626717`).
- Required M3 remains red for the absent fresh strict candidate
  (`20260822T160618-1621868`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict-receipt, product, browser, run-label, and hardware boundaries
  (`20260822T160704-1623599`).

## Boundary

The contract creates no WebGPU instance, adapter, device, buffer, pipeline, render pass, draw,
pixel, browser receipt, or result promotion. It does not bind the software Vulkan adapter. Live
draw proof remains owned by `M3-LINUX-REPLAY`, still blocked by the named s7 hardware-adapter
condition.
