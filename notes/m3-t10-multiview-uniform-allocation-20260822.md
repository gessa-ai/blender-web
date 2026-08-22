# M3.T10 multi-viewport uniform allocation — 2026-08-22

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0200 makes both `WGPUBatch` multi-viewport paths fail closed when their transient
`{layer, viewport}` uniform buffer cannot be created. Direct and indirect draws now return before
push-constant flushing, queue writes, command-encoder or render-pass allocation, bind-group work,
draws, or submission instead of forwarding a null buffer handle into WebGPU.

## Diagnosis and implementation

Both paths created the same 16-byte `Uniform | CopyDst` buffer and immediately used the result
without checking it. The new dependency-light `multi_viewport_uniform_buffer_create()` transaction
builds that exact descriptor, rejects a null candidate, and publishes the output only after
success. Both shipping paths guard the transaction before any later stateful work. This is the
Class-32 fallible transient-resource pattern recorded in `notes/porting-patterns.md`.

## Evidence

- The fail-first source guard rejected the unchanged source before evidence allocation
  (`20260822T205525-1889936`).
- Final root and descendant-directory native/wasm32 runs pass 15 byte-identical pipeline
  contracts. The new two-case transaction proves two exact descriptor creates, atomic output
  preservation on failure, and successful publication. Output is 1,379 bytes at SHA-256
  `cdb851e98806ebb9d3f532d0955145007cfa79fee56087a9698984b6640c08af`; shipping inputs are
  SHA-256 `c8df1186f6d4ecb726ee2c358a2390279205ca81b11a5a5d76f0104b0a0807a3`
  (`20260822T210355-1898887`, `20260822T210409-1900109`). Wrong Node 22.22.1 rejects before the
  isolated evidence path is allocated (`20260822T205959-1895209`).
- The source freezer retains 257 paths and 20,258 entries. Its 1,648,671-byte canonical patch is
  SHA-256 `53c0706e85852a3d801d6814853077e41f328d7b455fcffcaf28b7b871df6f8e`; live and replay
  manifests are byte-identical at SHA-256
  `79c1d14cda5f54a8b2ca1b605ec20b3ca95946ea12595b0c1d11eb32320a933f`
  (`20260822T205641-1891343`, `20260822T205726-1891874`). Patch-0200 reverse validation is green
  (`20260822T205839-1893680`).
- The optimized windowed product rebuilds 15 targets including `wgpu_batch.cc`, relinks
  `blender_browser`, and ends at exact locked-Ninja no-work (`20260822T205850-1893750`,
  `20260822T205933-1894945`). OFF-mode product preflight is green
  (`20260822T205953-1895134`), and pinned REUSE 6.2.0 reports 2,123/2,123 compliant files
  (`20260822T210227-1898176`).
- Required M3 remains red for the absent fresh strict candidate. Final container-backed regression
  at `2026-08-22T21:01:13Z` restores M0 to 6/6 green while M1-M8 retain their named strict-receipt,
  product, browser, run-label, and hardware boundaries.

## Boundary

This task creates no accepted WebGPU instance, adapter, device, buffer, queue write, command
encoder, render pass, draw, submission, pixel or browser receipt, result promotion, dependency
decision, deferral, tolerance, golden, blacklist, or milestone promise. The s7 software-adapter
stop condition remains live.
