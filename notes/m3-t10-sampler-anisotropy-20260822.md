# M3.T10 WebGPU sampler anisotropy — 2026-08-22

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0164 preserves Blender's mip-gated 2x, 4x, 8x, and 16x anisotropic sampler
requests in the WebGPU descriptor. The former path always left
`maxAnisotropy = 1`, silently discarding every anisotropy level used by image and
compositor sampling. The descriptor now also satisfies pinned Dawn's requirement
that minification, magnification, and mip filters are all linear when anisotropy
is greater than one.

## Diagnosis and implementation

Blender's contract and exact sample decoder live in
`upstream/source/blender/gpu/GPU_texture.hh:308` and `:360`. The pinned Vulkan
oracle enables anisotropy only with mipmapping and carries the selected sample
count in `upstream/source/blender/gpu/vulkan/vk_sampler.cc:48`. The WebGPU path
handled the independent linear and mipmap bits at
`upstream/source/blender/gpu/webgpu/wgpu_context.cc:288` but never read the
anisotropy mask.

The unchanged exact-source probe failed at `anisotropy sample count` after the
three pre-anisotropy controls passed (`20260822T041008-983739`). Patch
`patches/0164-gpu-webgpu-sampler-anisotropy.patch` adds only the missing branch:
it remains gated by `GPU_SAMPLER_FILTERING_MIPMAP`, uses
`GPU_anisotropic_samples_get`, and makes all three filters linear as required by
pinned Dawn's sampler validator.

## Evidence

- Exact native/wasm32 descriptor execution is byte-identical at 381 bytes,
  SHA-256 `b45dfcd6b24164694fc717331794da98e760b84e6ebda715f85d0e5cf80c03df`.
  It covers four anisotropy levels, the no-mipmap gate, a nearest-filter request,
  both custom samplers, and all four address modes (`20260822T041300-987576`).
- The extractor binds the exact shipping body at SHA-256
  `cb26a0afc8ee86f869590c9856d4623d3305dd43792fc68bfecec08409e2ec89`;
  malformed source plus wrong Dawn, Node, and fmt identities allocate no evidence
  (`20260822T041354-988407`).
- The canonical clean-pin freezer retains 257 changed paths and 20,258 manifest
  entries. Patch SHA-256 is
  `68c9422ec2204a17348f6a0ab42f0fac3b5eeb012cba9c8eb5d5481b7f937e9d`;
  live/replay manifest SHA-256 is
  `434c9c0e2c0100b54bf19c12b424bf8c96720da958c1bfb9b3e666b10197c81b`
  (`20260822T041207-986126`).
- The real windowed Wasm product recompiles `wgpu_context.cc`, links, and then
  reports exact locked-Ninja no-work (`20260822T041407-988660`,
  `20260822T041447-989095`).
- Required M3 remains honestly red only because no fresh strict candidate was
  supplied (`20260822T041501-989180`). Container-backed regression restores M0
  6/6 green and retains the existing M1-M8 receipt/artifact/browser/hardware
  boundaries (`20260822T041532-990462`).

## Boundary

The contract creates no WebGPU instance, adapter, device, sampler, bind group,
command, browser receipt, or result promotion. Live sampler creation and pixel
proof remain owned by `M3-LINUX-REPLAY`, which is still blocked by the named s7
software-adapter condition.
