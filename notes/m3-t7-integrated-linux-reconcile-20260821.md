<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T7 integrated compiler Linux reconciliation — 2026-08-21

## Outcome

The canonical in-tree WebGPU shader compiler module now has a checkout-relative, device-free
native/Wasm parity probe. It compiles the shipping `wgpu_shader_interface_map`,
`wgpu_shader_compiler`, and `wgpu_shader_cache` postimages directly rather than substituting the
earlier standalone T7.pre prototype. Before allocating evidence, the driver requires the exact
clean-pin canonical replay plus shaderc v2025.4, Dawn/Tint `36cf1fae`, emcc 6.0.5, and Node
22.16.0.

Five contracts cover the current evolved behavior:

- cold bind-map translation followed by an exact warm-cache hit, with identical WGSL and Tint
  entry-point reflection;
- float, comparison-depth, and integer texture reflection, including the distinction between a
  retained sampler resource and a texture actually used by `textureSample*`;
- compute SSBO read/write, read-only, and atomic translation;
- read-write storage visibility stripping, depth sample type, and binding-range failures;
- the 17-sampler policy, including one compacted sampler declaration and all 17 reflected texture
  bindings.

Root and descendant runs are green at `20260821T195313-519823` and
`20260821T195431-522229`. Native and Wasm emit identical 469-byte evidence
(`sha256:d2b5b09140a9`) and four byte-identical cache entries
(`manifest sha256:d53a808d5964`). The six integrated source/header inputs have combined identity
`sha256:964703a18a0f`; canonical replay binds 257 paths to squashed patch
`sha256:e03f140fe3f3`. Every involved target ends locked-Ninja no-work. The existing standalone
T7.pre and native/Wasm T1/T2 probes remain green (`20260821T195412-521045` and
`20260821T195419-521667`).

The fail-closed wrong-Dawn control rejects before evidence allocation
(`20260821T195451-522664`). Shell/diff checks pass (`20260821T195507-522787`), and exact REUSE
6.2.0 reports 1,955/1,955 files compliant (`20260821T195801-525592`).

## Boundary

This probe creates no Dawn adapter or device, validates no live pipeline, and allocates no M3
receipt. Required M3 remains red at `2026-08-21T19:56:05Z` for the absent fresh strict candidate.
Group-scoped regression at `2026-08-21T19:56:06Z` keeps M0 6/6 green and M1–M8 honestly red on
their existing strict-manifest, APPLY/artifact, browser, run-label, and hardware boundaries.
No product/upstream/GPU implementation, receipt, result flag, dependency record, deferral,
tolerance, golden, blacklist, or promise changes; s7 remains the named external blocker.
