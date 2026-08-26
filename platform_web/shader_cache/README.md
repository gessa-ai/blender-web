<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# First-boot WGSL cache seed

`first_boot.bwsp` contains the checksummed WebGPU translation-cache envelopes used by the
default factory-startup frame. It was extracted from the exact CAPTURE-generation Wasm named in
`first_boot.seed.json`; the extraction used Chromium's software adapter only to run deterministic
CPU shaderc/Tint translation and is explicitly not a hardware, pixel, or performance receipt.

At runtime, persistent OPFS entries take priority. A new origin falls back to this read-only pack.
Every lookup still requires the exact content key, shaderc/Tint policy salt, bounded stage lengths,
and payload checksum. Source, define, resource-map, or toolchain drift therefore misses safely and
runs the normal translator.

Regenerate the committed pack from an extracted entry directory with:

```sh
.host-tools/bin/python3.13 scripts/build-shader-cache-seed.py \
  --input-dir sandbox/m8-shader-cache-seed/artifacts/seed \
  --output platform_web/shader_cache/first_boot.bwsp \
  --manifest platform_web/shader_cache/first_boot.seed.json \
  --source-wasm-orig-sha256 <exact-capture-wasm-orig-sha256>
```

The generator rejects malformed, mixed-generation, symlinked, duplicate, unsorted, oversized, or
checksum-invalid entries and writes a deterministic pack plus source-identity manifest.
