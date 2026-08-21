<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# Device-free shader-chain parity smoke

This probe compiles two source files twice: once natively against the exact cached
shaderc v2025.4 source and Dawn's pinned Tint target graph, and once to WebAssembly
against the harvested shaderc/Tint archive manifests. The T1 case translates a
minimal GLSL vertex shader through SPIR-V 1.3 to WGSL. The T2 case translates a
Blender-shaped vertex/fragment pair under both default Tint and the complete
reserved-range sampler map. It fails unless every resource matches the normative
binding census in `notes/gpu-binding-map-spec.md`. Success also requires
byte-identical native/Wasm WGSL for both cases.

The probe is deliberately device-free. It verifies the CPU translation portion
of M3.T1 and the mapping portion of M3.T2 on hosts where the separate Dawn
validation probe correctly stops at `PROBE_BLOCKED` because no hardware adapter
is available. It does not validate a pipeline or create or replace an M3 receipt.

Run it through the bounded build logger:

```sh
harness/buildwrap.sh bash sandbox/wgpu-shader-wasm-smoke/build.sh
```

Both native and WebAssembly targets build only through
`scripts/ninja-locked.sh`. The driver requires Dawn
`36cf1fae0cd8a81a4fb4580751648b80b2e6255c`, emcc 6.0.5, and the bundled Node
22.16.0 before allocating its ignored build outputs.
