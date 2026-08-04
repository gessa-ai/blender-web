<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M3.T9.pre — WebGPU texture formats + data conversion (standalone-proven)

The other development-heavy M3 backend chunk, developed OUTSIDE the Blender tree
against the `sandbox/dawn-probe` baseline. Filenames mirror
`source/blender/gpu/webgpu/` so they drop in later.

## Files

- `wgpu_texture_format.{hh,cc}` + `wgpu_texture_format_list.h` — the format TABLE:
  every `blender::gpu::TextureFormat` (GPU_texture.hh:45-124) → `wgpu::TextureFormat`
  + capability flags {renderable, filterable, storage, blendable, multisample} +
  conversion class + device feature gate. Data provenance: the X-macro table in
  `upstream/source/blender/gpu/GPU_format.hh` (read-only). Modelled on the Vulkan
  backend's `vk_common.cc::to_vk_format`.
- `wgpu_data_conversion.{hh,cc}` — the RGB→RGBA promotion for the 13 three-channel
  formats WebGPU cannot represent (the dominant real conversion); other formats are
  Direct memcpy.
- `tests/wgpu_texture_format_test.cc` — LIVE Dawn/Metal harness: per-format
  creatability + caps discovery, upload/readback round-trip for copyable color
  formats (incl. promotions), representative render/depth clears, a BC block
  round-trip, and a device-free conversion unit test.

## Build & run

```sh
# Reuses the dawn-probe checkout (build-dawn/dawn); Dawn-only (no shaderc/Tint).
harness/buildwrap.sh bash sandbox/wgpu-texture-formats/build.sh
```

Exit 0 iff the conversion unit test passes, every feature-gate-satisfied format is
creatable, every copyable color format round-trips byte-exact, and the render/depth
clears verify. Build tree under `build-dawn/t9pre-build` (gitignored).

## Result

Full table + per-format live results + the unsupported/promoted lists:
`notes/gpu-t9pre-findings.md`.
