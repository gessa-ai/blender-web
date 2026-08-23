<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 EEVEE access-aware storage formats — 2026-08-23

## Outcome

Patch 0211 (`2aab304`) makes WebGPU storage-format promotion access-aware. A write-only
`SFLOAT_16_16` image now remains native `RG16Float`, while an image carrying both read and write
qualifiers is promoted to `RGBA16Float`. The one rule feeds the GLSL layout declaration,
`WGPUShaderInterface::image_formats_`, and the bind-group resource descriptor.

This removes two opposite interface mismatches. EEVEE's write-only depth-of-field gather LUT and
occlusion images are allocated as `RG16Float` and must not be declared or bound as `RGBA16Float`.
Conversely, the read-write motion-vector image is physically promoted by `eevee_storage_format()`
and its shader-interface metadata must carry that same promoted format. The existing unconditional
RG11B10Ufloat and RG16Unorm promotions are unchanged.

## Evidence

The unchanged backend fails the expanded contract at the absent qualifier parameter
(`20260823T005842-2141590`). The final device-free contract crosses all 63 texture formats with
all eight qualifier bit patterns (504 helper cases, 18 expected promotions), binds the three
shipping interfaces, and produces byte-identical 825-byte native/Wasm output at SHA-256
`750461f9eec26ebb2fc51f4e2226398921c45d5f89c7a2f4ca9ad1b89bc5df42`. Root and descendant-CWD
runs plus malformed-source self-checks are green (`20260823T010400-2146615`,
`20260823T010445-2148442`, `20260823T010436-2148163`). The test does not construct the polymorphic
interface; exact source binding checks all three call sites, and the full product build compiles
the live interface implementation.

The canonical freezer and independent replay retain 257 paths and 20,258 manifest entries at
patch SHA-256 `2958b19d7975` and manifest SHA-256 `fe7d8d15f8ae` (`20260823T010110-2143643`,
`20260823T010156-2144540`). The real `blender_browser` target rebuilds and then reaches exact
locked-Ninja no-work (`20260823T010458-2148856`, `20260823T010540-2149245`). REUSE 6.2.0 is
2,150/2,150 green (`20260823T010626-2149665`).

## Boundary

This is device-free format/interface proof. It creates no WebGPU adapter, device, texture,
pipeline, browser capture, pixel comparison, or M6 receipt. M6 remains red on its existing safe
run-label boundary; container-backed regression at `2026-08-23T01:06:49Z` keeps M0 6/6 green and
M1-M8 otherwise red on their existing receipt, product, browser, run-label, and hardware
boundaries. The live EEVEE receipt remains deferred for the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
