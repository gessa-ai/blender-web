<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T9 WebGPU 1D sRGB clear encoding — 2026-08-22

## Outcome

Patch 0186 makes the raw-copy clear fallback for a non-renderable 1D sRGB texture preserve the
same linear clear-color semantics as the render-pass path. RGB is encoded through the sRGB output
transfer function before its `RGBA8UnormSrgb` bytes reach `Queue::WriteTexture`; alpha remains a
linear UNORM component.

## Diagnosis and experiment

`WGPUTexture::clear()` normally gives its linear color directly to a render-pass attachment.
WebGPU applies the attachment format's sRGB encoding when it stores RGB. A 1D WebGPU texture
cannot be a render attachment, so that dimension uses a repeated host texel and `WriteTexture`
instead. The copy stores bytes verbatim. The old fallback linearly quantized all four components,
causing a later sRGB sample to decode already-linear bytes.

The pinned native Blender experiment used `(0.25, 0.5, 0.75, 0.5)`. A linear RGBA8 clear read
back `[64, 128, 191, 128]`, while a 2D sRGB attachment clear read back the encoded
`[137, 188, 225, 128]`. The committed 1D oracle clears an sRGB texture and samples it into a linear
target; it returns `[64, 128, 192, 128]`, within the expected one-byte quantization envelope. The
container-backed run prints the exact pass marker in `20260822T145233-1560574`.

`srgb_clear_component_to_unorm8()` now rejects non-finite inputs to zero, clamps finite inputs,
applies the standard piecewise sRGB output transfer function, and rounds to one byte. The fallback
calls it only for RGB when the physical backing format is `RGBA8UnormSrgb`; the existing linear
path still owns alpha and every other format.

## Verification

- The unchanged source fails the new source-wiring contract before allocating its requested
  evidence directory (`20260822T144132-1548399`).
- The root and descendant builds compile the canonical conversion implementation for native and
  wasm32 and pass 21 byte-identical contracts. The 12 new cases bind clamping, the transfer
  threshold, representative encoded values, and non-finite policy. Evidence is 2,096 bytes at
  SHA-256 `319a426dd393a5c304805ef0392878bd660a894bc7caa27550c2253a09230965`,
  with source SHA-256
  `7fbc98e8f5ee9feeb9d4191dfc89c2e7a8369f541e9cefe032302117a6ace5ec`
  (`20260822T144509-1551410`, `20260822T144551-1553661`).
- Wrong Dawn and Node identities reject before their requested evidence directories exist
  (`20260822T144541-1553126`, `20260822T144541-1553327`).
- The canonical freezer retains 257 paths and 20,258 entries. The patch is 1,596,649 bytes at
  SHA-256 `30009e228d9c70fd49168ac239e736ab8d3fe1df3502b23abc317235ce16718e`;
  live/replay manifests are byte-identical at SHA-256
  `4c5fe58ad4c0f19040fa5ef52b4fa103b0fa8403f1a9f164434c03bc37a4a940`
  (`20260822T144416-1550748`, `20260822T144459-1551324`,
  `20260822T145335-1561251`).
- `blender_browser` rebuilds through locked Ninja and then reports exact no-work
  (`20260822T144641-1554787`, `20260822T144725-1555143`). The OFF-mode product preflight is green
  (`20260822T144725-1555172`).
- REUSE 6.2.0 reports copyright and license information for all 2,088 files
  (`20260822T145109-1559152`). Required M3 remains red for the absent strict candidate
  (`20260822T144751-1556253`); container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict-receipt, product, browser, run-label, and hardware boundaries
  (`20260822T144806-1556391`).

## Boundary

The device-free contract creates no WebGPU instance, adapter, device, texture, command, browser
receipt, or result promotion. The native experiment is a semantic oracle, not accepted WebGPU
evidence. Live 1D WebGPU clear execution remains owned by `M3-LINUX-REPLAY`, still blocked by the
named s7 software-adapter condition.
