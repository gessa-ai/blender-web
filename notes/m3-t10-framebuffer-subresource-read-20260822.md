<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU framebuffer subresource readback - 2026-08-22

## Outcome

Patch 0181 makes WebGPU framebuffer reads select the framebuffer attachment's exact mip/layer and
return exactly the caller-requested leading channel count. Crop, Y-flip, source bytes, and
destination bytes are resolved atomically before allocating the temporary source or touching the
caller buffer.

## Diagnosis and implementation

`WGPUFrameBuffer::read` previously called `tex->read(0, ...)`, so an array or cube attachment
always returned layer zero. It also divided the whole texture-read size by width and height to
derive bytes per pixel. Layer count therefore inflated that value, and an RGBA texture read with
one requested channel copied four bytes into each one-byte destination pixel.

The public attachment contract carries both layer and mip in
`upstream/source/blender/gpu/GPU_framebuffer.hh:51`. The pinned Vulkan framebuffer reader selects
the attachment layer at `upstream/source/blender/gpu/vulkan/vk_framebuffer.cc:387`, while the
pinned OpenGL/native oracle returns exactly the requested `GL_RED`/`RG`/`RGB`/`RGBA` channel set.

The WebGPU texture now exposes an exact layer/depth-slice read entry at
`upstream/source/blender/gpu/webgpu/wgpu_texture.cc:2273`. The framebuffer resolves its attachment
before allocation and calls that entry at
`upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc:382` and `:433`. Shared helpers at
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:321` and `:386` validate every source and
destination product, crop and vertically flip, copy only leading requested channels, and extend
missing color/alpha channels with native-compatible zero/one values.

## Evidence

- The unchanged canonical source rejects the new wiring contract before build or evidence
  allocation (`20260822T114800-1390585`).
- The pinned 5.2.0 Linux oracle proves both layers of a two-layer RGBA texture, channel counts one
  through four, and R/RG expansion to zero color plus unit alpha
  (`20260822T115915-1406092`).
- The isolated postimage passes the native/wasm32 graph before composition
  (`20260822T115303-1399073`). Final root and descendant-CWD runs pass 17 contracts and 13 new
  framebuffer cases byte-identically at 1,563 bytes, SHA-256
  `7b1d37f3f8400ba25c3e0e5e24940dd2a3e1e7045f78b8073c23737b47a20dc6`, with source SHA-256
  `3af0e6c460b71ce5ae97b10d00d39b340601be417ccf343b19a026b1bcde0c99`
  (`20260822T115920-1406435`, `20260822T115934-1407158`).
- A wrong Dawn identity rejects before creating its requested evidence directory
  (`20260822T115617-1403629`).
- The canonical freezer retains 257 paths and 20,258 entries. The patch is 1,585,709 bytes at
  SHA-256 `417e94e6dee8e933bde4e71e06b158cd56def8e19c3cef0e53ec52076c1bdab6`;
  live/replay manifests are byte-identical at SHA-256
  `73cfb96d783a50f199aa10dc3ec06baa32e720d082a169dbb3d3209ca6483c35`
  (`20260822T115447-1401611`, `20260822T115525-1402124`).
- `blender_browser` recompiles the affected common-header dependents, framebuffer, and texture,
  links, and then reports exact locked-Ninja no-work
  (`20260822T115627-1403845`, `20260822T115709-1404223`). The OFF-mode product preflight is green
  (`20260822T115746-1405416`).
- REUSE 6.2.0 reports copyright and license information for all 2,072 files
  (`20260822T120351-1412026`).
- Required M3 remains red for the absent fresh strict candidate (`20260822T120213-1409244`).
  Container-backed regression keeps M0 at 6/6 green while M1-M8 retain their existing strict
  receipt, APPLY/product, browser, run-label, and hardware boundaries
  (`20260822T120220-1410156`).

## Boundary

The contract creates no WebGPU instance, adapter, device, texture, readback, pixel, browser
receipt, or result promotion. Live framebuffer readback proof remains owned by `M3-LINUX-REPLAY`,
still blocked by the named s7 software-adapter condition.
