<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Canonical WebGPU render-pipeline mapping parity smoke

This device-free M3.T10 reconciliation compiles Blender's canonical in-tree
`wgpu_pipeline` postimage directly for native and wasm32 against Blender's real
primitive, index-format, component, and fetch enums. The shared test also covers
the two-case transient uniform-buffer allocation transaction shared by
multi-viewport emulation and cross-format color blits,
the fail-first/retry transactions shared by sampler/render-pipeline caches and the
per-shader compute-pipeline variant cache,
16 direct-draw decisions, 28 multi-viewport/scissor decisions, 32 bottom-origin
window-backbuffer decisions, 21 ordinary offscreen viewport/scissor decisions, and
19 exact indirect-draw span decisions. Direct draws
resolve Blender's four signed backend parameters before WebGPU work, reject negative
first values and non-positive normalized counts, and preserve the full positive `int`
domain. Indirect draws cover signed input rejection, four-byte alignment,
16-byte array commands, 20-byte indexed commands, tightly-packed zero stride,
overlapping-but-aligned explicit stride, allocation bounds, and arithmetic overflow.
Multi-viewport draws preserve the signed raster transform while intersecting the
unsigned WebGPU scissor with the framebuffer. Legal zero and fully clipped rectangles
produce a contained zero scissor so pending load actions can still be consumed; negative
extents and device-invalid boundaries remain atomically rejected in both the direct and
indirect EEVEE-shadow paths. Their shared 16-byte `{layer,
viewport}` uniform allocation must publish a handle only on success; both paths
must return before queue or pass work when creation fails.
The color-blit fallback additionally rejects a missing shader module before pipeline creation,
the missing uniform before `WriteBuffer`, a missing bind group before command-encoder/pass
work, and failed compute encoder/pass/command-buffer creation before dependent work or submission
work. The source-order checks bind all three guards to the shipping method while the shared
native/Wasm allocation contract proves failure leaves the caller's buffer handle unchanged.
The indexed triangle-fan expansion likewise rejects a missing shader module before compute-
pipeline creation and uses the same tested encoder/pass/finish transaction, so any failed command
handle stops before expansion work or queue submission. Exact source-order checks bind both guards
to the shipping fan method.
Framebuffer full clears likewise use that tested render-pass transaction for both multi-attachment
clears and single-color-attachment clears. A failed encoder or pass now stops the layer loop before
dependent work, while a failed finished command buffer stops before submission; exact method-body
checks reject any retained unchecked command operation.
Framebuffer blits likewise use the checked copy transaction for both the two-step stencil buffer
bridge and the raw texture-to-texture path. Encoder failure stops before either copy, and finished-
command-buffer failure stops before queue submission; exact method-body checks bind all three copy
operations to those two transactions.
Layered depth/stencil and renderable-color texture clears use one abortable encoder transaction.
Failure at the encoder, any per-layer view/pass, or the finished command buffer discards the whole
clear before submission, while the successful path retains one command buffer for every layer.
Native synchronous texture readback uses the same checked copy transaction before mapping its
staging buffer, so encoder or finished-buffer failure cannot reach mapping or queue submission.
Likewise, a null sampler or render-pipeline candidate must remain absent from its
cache so the same key can retry and publish a later valid handle. The source guard
binds that transaction to every context and process-wide pipeline cache site.
The same rule applies to each specialization-keyed compute pipeline: a transient null
creation result must not become a retained variant that suppresses every later retry.
Window-backbuffer rectangles preserve that same raster transform while converting
Blender's bottom-origin viewport and optional independent scissor with widened
arithmetic. Both rectangles must validate before a render pass is allocated; a legal
empty state remains encodable while the explicit scissor is clipped without narrowing
its signed frontend geometry.
Ordinary offscreen passes convert the same bottom-origin rectangles to WebGPU's top origin,
preserve signed viewport transforms, and clip an enabled scissor independently. Clip-space and
readback flips preserve orientation and row order but cannot relocate a partial rectangle.
The oracle's 6x5 viewport and viewport/scissor intersection are included verbatim.
It additionally covers 15 direct compute-dispatch decisions and 13 indirect
compute-dispatch ranges. Direct counts reject negative axes, non-positive published
limits, and values above those per-axis limits while preserving zero-count no-ops;
indirect commands require four-byte alignment and one complete 12-byte `[x,y,z]`
record without overflow. It covers all 11 primitive rows, all 33
primitive/index-format combinations, and all 96
combinations of eight vertex component types, four valid component lengths, and
three fetch modes. It also covers every one of the 32 shader input types in the
dummy-attribute plan and requires a zero-stride, vertex-stepped binding that remains
constant for arbitrary vertex and instance ranges. The strip contract requires
`Uint16`/`Uint32` only for indexed
line-strip, line-loop, and triangle-strip pipelines and keeps every non-strip
topology at `Undefined`, matching pinned Dawn validation. This also includes the
resolved normalized signed-I10 mapping to `Snorm8x4`. A cache-key contract builds
two real vertex formats whose distinct two-alias lists concatenate to the same raw
bytes and requires length-framed hashing to keep their shader-location layouts
separate.

Run only through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/wgpu-pipeline-integrated-smoke/build.sh
```

The triangle-fan row deliberately exercises the backend's fail-visible fallback:
both executions must emit the exact canonical `BLI_assert_unreachable` diagnostic
before returning `TriangleList`. Native and Wasm stdout and stderr must be
byte-identical.

The driver checksum-binds Dawn `36cf1fae` (including its stride-zero pipeline,
16/20-byte indirect draw-range, viewport/scissor, and direct/indirect compute validation), emcc 6.0.5,
Node 22.16.0, matching native/Wasm fmt headers, Blender's canonical clean-pin replay,
and 25 exact pipeline/batch/framebuffer/texture/vertex-format/enum/assert source inputs before
evidence allocation. It also
requires both shipping direct and indirect batch paths to call the tested strip-format
mapping. Both targets build only through `scripts/ninja-locked.sh` and finish
with exact no-work checks.

No WebGPU instance, adapter, device, render/compute pipeline, render/compute pass, draw, dispatch,
or pixel evidence is created. Live descriptor, dispatch, and pixel validation remain owned by
`M3-LINUX-REPLAY` and require an accepted hardware adapter.
