<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Canonical shader-compiler parity probe

This device-free probe compiles and runs the canonical in-tree WebGPU shader
compiler module twice: once natively and once as WebAssembly under the pinned
Node runtime. Unlike the standalone M3.T7.pre design harness, it consumes the
evolved shipping postimage directly, including the WGSL disk cache, Tint entry-
point reflection, sampler compaction, and current bind-group visibility policy.

Before allocating evidence, the driver requires the clean-pin canonical replay,
shaderc v2025.4's checksum-bound source, Dawn/Tint `36cf1fae`, emcc 6.0.5, and
Node 22.16.0. Both targets build only through `scripts/ninja-locked.sh`. The
native and Wasm executions must emit identical six-contract evidence and four
byte-identical cold-cache files; the second bind-map compilation must be a warm
cache hit with unchanged WGSL and reflection, and an appended cache byte must
invalidate the otherwise checksummed envelope without changing caller outputs.

Run the bounded logger from any checkout descendant:

```sh
harness/buildwrap.sh bash sandbox/wgpu-shader-integrated-smoke/build.sh
```

The probe never requests an adapter or device. It does not create or replace an
M3 receipt, and the strict Linux replay remains blocked by the named s7 hardware-
adapter condition.
