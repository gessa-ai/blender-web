<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-G widget-shadow defined RGB — 2026-08-26

## Outcome

Patch 0284 is a hardware-validation candidate for the white transient-widget shadows. It keeps
shadows enabled and preserves their geometry, alpha curve, UBO interface, target format, and blend
state. The only shader change constructs the complete fragment result as black RGB plus computed
alpha in one assignment. Implementation commit: `6145c46`.

This item remains open. The local fallback adapter is diagnostic-only and does not render usable
semantic pixels. The driver-operated Apple M4 Pro must verify that tooltip/flyout and Adjust Last
Operation shadows are black/translucent and that no white rounded bars or rings remain.

## Diagnostic before the fix

The accepted Apple capture screenshots show soft edges and the expected rounded shadow geometry,
but the affected pixels brighten the gray viewport instead of darkening it. The shader's alpha
path is therefore visibly active while its intended constant-black RGB is not.

`sandbox/p0-widget-shadow/capture_diagnostic.mjs` attaches to the actual WM worker before WebGPU
object creation and records the browser-side state. Against the exact pre-fix CAPTURE artifact it
proved:

- `gpu_shader_2D_widget_shadow` declares three push constants and no sampler, texture, or image;
- the draw binds the sole surviving group-0 entry, a 144-byte push-constant UBO;
- the target is RGBA8Unorm, with transparent-black clear history and load/store shadow passes;
- the render pipeline writes RGBA and uses source-alpha / one-minus-source-alpha color blending;
- final WGSL initializes `fragColor` with `vec4<f32>()` and then replaces only `.w`.

No hardware console warning names widget shadow, node socket, or area borders as an incomplete bind
group. `gpu_shader_2D_node_socket` and `gpu_shader_2D_area_borders` both source their complete RGB
from explicit colors; neither owns a shadow sampler. The filed missing-gradient-sampler hypothesis
is therefore falsified rather than papered over.

## Candidate and evidence

The postimage emits:

```glsl
fragColor = float4(0.0f, 0.0f, 0.0f, inner_alpha * shadow_alpha);
```

After the locked CAPTURE relink, live interception sees the corresponding single WGSL assignment
`vec4<f32>(0, 0, 0, inner_alpha * shadow_alpha)`, with the original pipeline descriptor and one
complete bind group. The window reaches `WM_main`, advances uncapped tick/present counters, and has
zero page errors. This proves the candidate is baked into the artifact; it is not pixel evidence.

Evidence:

- pre-fix diagnostic runs: `20260826T191810-1167480`, `20260826T192054-1169425`,
  `20260826T192321-1171150`, `20260826T192540-1172959`, and `20260826T192753-1174736`;
- source contract: `20260826T193411-1179152` (one positive, six rejected mutations);
- canonical freeze/replay: `20260826T193324-1178526` and `20260826T193432-1180102`,
  20,258 entries, SHA-256 `69c7ee3cd030be7743847e1604c93794ef6765f020f087413b206912efdc3ec6`;
- locked relink/no-work: `20260826T193456-1180339` and `20260826T193623-1181002`;
- post-fix exact-artifact live trace: `20260826T193629-1181078`;
- CAPTURE inventory, producer self-check, and two-phase source proof:
  `20260826T193858-1183027`, `20260826T193858-1183029`, and
  `20260826T193858-1183028`;
- pinned-container regression: `20260826T194003-1184440` restores M0 6/6 while M1–M8 retain
  their strict receipt/APPLY/product boundaries;
- repository-wide REUSE 6.2.0: `20260826T194024-1185327`;
- CAPTURE `.wasm.orig`: 119,142,918 bytes, SHA-256
  `5a9d0944007313bed75ac3deaf24d3c48e443a423c93918dbb561abb76d0d65b`.

The diagnostic forces SwiftShader and binds no receipt. An attempted full numbered-history replay
also exposed unrelated existing drift at series entry 15 (`0016-gpu-webgpu-texture-format-conversion.patch`,
`source/blender/gpu/CMakeLists.txt:482`); the authoritative squashed canonical replay and 0284's
own reverse-apply both pass.
