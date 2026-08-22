<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T9 WebGPU odd-dimension mipmap kernel — 2026-08-22

## Outcome

Patch 0191 makes the normalized/float render fallback in `WGPUTexture::generate_mipmap()` use
Blender's pinned separable 1/2/3-tap reduction. Odd source axes now include their final texel
instead of silently dropping it. The integer fallback is unchanged because the pinned native
shader has no corresponding integer specialization.

## Diagnosis and implementation

The former WGSL always averaged the four texels at `2 * destination + {0,1}^2` and clamped each
coordinate to the source bounds. For a width-five source and width-two destination, those
footprints cover source texels 0-1 and 2-3; texel 4 is never addressed, so the clamp is inert. A
five-value ramp `[0,10,20,30,40]` therefore reduced to `[5,25]`.

The native mipmap shader at
`source/blender/gpu/shaders/gpu_shader_2D_update_mipmaps.bsl.hh:142-145,276-335` selects one tap
for size one, two equal taps for even sizes, and three weighted taps for odd sizes. For an odd
axis with `N` destination pixels, destination coordinate `x` uses weights
`(N-x)/(2N+1), N/(2N+1), (x+1)/(2N+1)`. The same ramp therefore produces `[8,32]`, including the
final source texel.

`mipmap_axis_plan()` exposes that scalar contract without a device. The complete float/normalized
WGSL lives in `mipmap_float_shader_source()`, and the shipping texture path consumes that exact
string. The integer path retains its existing 2x2 behavior. The Python GPU oracle exposes
`GPUTexture.clear`, `read`, and `mipmap_mode`, but its constructor fixes one mip level, so it cannot
exercise generation; the pinned native shader is the behavioral authority for this unit.

## Verification

- The pre-fix five-to-two experiment reproduced `[5,25]` versus native `[8,32]`. The unchanged
  canonical source then rejected the missing kernel helper/wiring before build or evidence
  allocation (`20260822T171048-1682248`).
- Final root and descendant-working-directory native/wasm32 runs pass 22 byte-identical contracts
  (`20260822T172138-1693717`, `20260822T171758-1690832`). The new contract covers eleven
  size/coordinate plans, three atomic rejections, the exact ramp, and the production shader
  identity `cc8680d08265ba8a`; pinned Dawn/Tint `36cf1fae` parses the same WGSL on the native leg.
  Stdout is 2,182 bytes at SHA-256
  `ad875121ec0c50128abe35671b4193c717b64f18283b1d52f8ff00243dd87180`, and the bound source set
  is SHA-256 `0597bf2082cfd6d1736b5068176d51ed4056243fb65bdc2d7ff4dfa59256a70d`.
- A wrong Node identity fails before its requested evidence directory exists
  (`20260822T171410-1685844`).
- The canonical freezer retains 257 paths and 20,258 entries. Its 1,611,271-byte patch has
  SHA-256 `f96a3b883108bf382479b5d392d2d8d42db493d766b091620d841af0214f5cde`; live and replay
  manifests are byte-identical at SHA-256
  `f647b717e08b0aef66d1a32580ed7295d072aa0d8abe89750b39aae324ad7893`
  (`20260822T171138-1682727`). Canonical-only replay and cumulative/incremental reverse checks are
  green (`20260822T172125-1693602`). The
  diagnostic numbered-history audit still stops at its named pre-existing patch-0016 conflict.
- `blender_browser` rebuilds through locked Ninja and then ends exact no-work
  (`20260822T172037-1693160`, `20260822T172125-1693601`). The strict OFF-product preflight passes
  with a 118,059,493-byte primary Wasm (`20260822T171354-1685729`).
- REUSE 6.2.0 reports copyright and license information for all 2,098 files
  (`20260822T171850-1691577`). Required M3 remains red for the absent fresh strict candidate. The
  final container-backed regression at `2026-08-22T17:17:38Z` keeps M0 6/6 green while M1-M8
  retain their existing strict-receipt, product, browser, run-label, and hardware boundaries.

## Boundary

The contract creates no WebGPU instance, adapter, device, texture, pipeline, render pass, sample,
pixel, browser receipt, or result promotion. It does not bind the software Vulkan adapter. Live
mipmap sampling remains owned by `M3-LINUX-REPLAY`, still blocked by the named s7 hardware-adapter
condition.
