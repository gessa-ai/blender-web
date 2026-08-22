<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T8 WebGPU compute-pipeline cache publication — 2026-08-22

## Outcome

Patch 0205 keeps a failed specialization-keyed compute pipeline out of
`WGPUShader::compute_pipelines_`. A transient null result from `CreateComputePipeline` now fails
the current dispatch without retaining that key, so the next dispatch can create and publish a
valid variant.

## Diagnosis and implementation

`WGPUShader::compute_pipeline()` linearly searches its per-shader vector before creating a new
variant. The miss path previously appended `{key, pipeline}` unconditionally. If creation returned
null, every later request for the same specialization key found that retained entry and returned
null without calling Dawn again.

`cache_variant_if_valid()` in
`upstream/source/blender/gpu/webgpu/wgpu_common.hh` makes the sequence-cache publication a single
transaction. It rejects null without changing the vector and appends the key/handle pair only after
successful creation. The shipping compute-pipeline miss path now returns before publication when
that transaction fails.

## Verification

- The unchanged source fails before evidence allocation on the absent transaction helper
  (`20260822T223550-2007673`).
- Root and descendant native/wasm32 runs pass 17 device-free contracts, including a deterministic
  fail-first/unpublished then retry/published compute variant. Their 1,631-byte outputs are
  byte-identical at SHA-256 `83d1fb7d61b4`, with 21 shipping inputs at SHA-256
  `b77fe0084168` (`20260822T223830-2011056`, `20260822T224108-2014941`).
- The canonical freezer and independent replay retain 257 paths and 20,258 entries. The
  1,652,546-byte patch is SHA-256 `6b07a9846585`; both manifests are SHA-256
  `820b09d2ec27` (`20260822T223745-2010359`, `20260822T223824-2010952`). Patch 0205 also
  reverse-applies cleanly to the live postimage (`20260822T224352-2018276`).
- The real `blender_browser` rebuild compiles the affected GPU closure and links successfully,
  then ends exact locked no-work (`20260822T223853-2011980`, `20260822T223937-2013172`). OFF
  preflight binds the resulting 118,072,225-byte primary Wasm
  (`20260822T223951-2013310`).
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260822T224204-2016636`). Container-backed regression restores M0 to 6/6 while M1-M8 retain
  the existing strict-receipt/product/browser/run-label/hardware boundaries
  (`20260822T224208-2016720`).
- Exact REUSE 6.2.0 reports all 2,132 files compliant (`20260822T224250-2017678`).

## Boundary

No WebGPU instance, adapter, device, compute pipeline, pass, dispatch, pixel, or browser receipt is
claimed. Live retry and dispatch proof remain owned by `M3-LINUX-REPLAY` and blocked by s7's lack of
an accepted hardware Vulkan/WebGPU adapter. No result promotion, dependency decision, deferral,
tolerance, golden, blacklist, or milestone promise changed.
