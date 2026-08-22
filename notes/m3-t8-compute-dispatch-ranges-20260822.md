<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T8 WebGPU compute dispatch ranges — 2026-08-22

## Outcome

Patch 0188 makes direct WebGPU compute dispatches validate all three signed workgroup counts
against Blender's published backend limits before conversion to WebGPU's unsigned API. The
indirect path now proves that its buffer contains one aligned 12-byte `[x,y,z]` command before
pipeline or compute-pass work. Invalid geometry is an atomic no-dispatch decision; valid zero
counts retain no-op behavior.

## Diagnosis and implementation

The backend interface carries direct workgroup counts as signed integers
(`upstream/source/blender/gpu/intern/gpu_backend.hh:58`; public API at
`upstream/source/blender/gpu/GPU_compute.hh:28`). The Python entry point also parses signed
integers but checks only whether they exceed the upper limits
(`upstream/source/blender/python/gpu/gpu_py_compute.cc:52` and `:75`). The previous WebGPU backend
cast those values directly to `uint32_t`, so negative counts became huge unsigned dispatches and
non-Python callers could delegate over-limit axes to Dawn after pipeline/pass work. Its indirect
path always addressed offset zero without proving that the physical buffer contained its complete
command.

Pinned Dawn validates every direct axis against `maxComputeWorkgroupsPerDimension`
(`build-dawn/dawn/src/dawn/tests/unittests/validation/ComputeValidationTests.cpp:111`) and rejects
an incomplete or misaligned indirect command
(`build-dawn/dawn/src/dawn/tests/unittests/validation/ComputeIndirectValidationTests.cpp:83`). The
canonical indirect command is three 32-bit words
(`build-dawn/dawn/src/dawn/common/Constants.h:76`).

`compute_dispatch_plan()` now resolves the signed direct inputs against all three published
limits and replaces its output only on success; `compute_indirect_dispatch_range()` proves
alignment and the fixed command span with subtraction-safe arithmetic
(`upstream/source/blender/gpu/webgpu/wgpu_common.hh:100`, `:109`, and `:137`).
`WGPUBackend::compute_dispatch()` consumes the plan before shader/pipeline work and
`compute_dispatch_indirect()` validates the physical allocation before creating its pipeline or
pass (`upstream/source/blender/gpu/webgpu/wgpu_backend.cc:177`, `:209`, and `:233`).

## Verification

- The unchanged canonical source rejects the new helper/wiring contract before allocating its
  requested evidence directory (`20260822T153707-1596301`).
- Root and descendant-working-directory runs compile the canonical implementation for native and
  wasm32 and pass ten byte-identical contracts. The new direct census accepts 6/15 cases and
  rejects 9/15 with unchanged output; the indirect census accepts 5/13 and rejects 8/13. The
  814-byte stdout has SHA-256
  `c1e09a9fa9096e91e422cb4023a2ebe063b3a2a90a74bef9787a56d327fc71e6`; shipping-source
  SHA-256 is `70b777263de6b2961d5a00e3a3c8934d7065157c54450139d04f09f2550a0526`
  (`20260822T153945-1598569`, `20260822T154207-1601000`).
- A wrong Node identity rejects before its requested evidence directory exists
  (`20260822T154224-1601519`).
- The canonical freezer retains 257 paths and 20,258 entries. Its 1,601,734-byte patch has SHA-256
  `16ff5a21fdeed3fa11c91e61763bd36306f355e5d32887c2f14d3f962fac90f4`; live and replay
  manifests are byte-identical at SHA-256
  `22c14a60f7f9f0612ea5a49258f03dfcdc0722d9d60f1d43d587bbb79c1758aa`
  (`20260822T153854-1597862`). Reverse application and canonical-only replay are also green
  (`20260822T153937-1598457`).
- `blender_browser` relinks through locked Ninja and then reports exact no-work
  (`20260822T154049-1599603`, `20260822T154134-1600737`). Its strict OFF-mode preflight passes
  with a 118,057,249-byte primary Wasm (`20260822T154238-1601852`).
- REUSE 6.2.0 reports copyright and license information for all 2,092 files
  (`20260822T154738-1606114`).
- Required M3 remains red for the absent fresh strict candidate. The final container-backed
  regression keeps M0 6/6 green while M1-M8 retain their existing strict-receipt, product,
  browser, run-label, and hardware boundaries (`2026-08-22T15:43:43Z`).

## Boundary

The contract creates no WebGPU instance, adapter, device, command encoder, compute pipeline,
compute pass, dispatch, browser receipt, or result promotion. It does not bind the software
Vulkan adapter. Live compute proof remains owned by `M3-LINUX-REPLAY`, still blocked by the named
s7 software-adapter condition.
