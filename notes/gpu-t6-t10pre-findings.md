<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M3.T6.pre + T10.pre — buffers + state tables, standalone-proven (findings)

Uncommitted worker notes for orchestrator review. Pin: Blender 5.2 `fbe6228777e7`;
Dawn `chromium/7989 @ 36cf1fae`. Companion modules: `sandbox/wgpu-buffers/` and
`sandbox/wgpu-state-tables/`. The last two standalone-provable M3 backend chunks,
built OUTSIDE the tree against the dawn-probe baseline and validated on live
Dawn/Metal. `upstream/`, `patches/`, `build-native-gpu/` untouched (read-only recon).

---

# PART 1 — T6.pre buffers (`sandbox/wgpu-buffers/`)

`wgpu_buffer.{hh,cc}` — the common `GPUBuffer` wrapper; `tests/wgpu_buffer_test.cc`
— live harness. API: `usage_flags(kind, usage, readable)`, `Buffer::create` (via
`mappedAtCreation`), `Buffer::update_sub` (writeBuffer vs staging by size),
`Buffer::read` (MAP_READ staging + CopyBufferToBuffer), `to_wgpu_index_format`.

## Recon (Vulkan backend, cited)

- **GPUUsageType does NOT select memory type.** vk hardcodes one VMA config per
  buffer KIND regardless of STREAM/STATIC/DYNAMIC/DEVICE_ONLY
  (vk_vertex_buffer.cc:213-219, vk_index_buffer.cc:112-121, vk_storage_buffer.cc:80-93,
  vk_uniform_buffer.cc:39-49). GPUUsageType affects only (a) **host-copy retention**
  — DEVICE_ONLY keeps no shadow (vk_vertex_buffer.cc:117-137), STATIC frees it after
  upload (:195-197), STREAM/DYNAMIC keep it — and (b) STREAM storage buffers route
  through a streaming ring (vk_storage_buffer.cc:48-54). ⇒ our mapping: DEVICE_ONLY
  drops `CopyDst`; the rest add it. Memory placement is WebGPU's to decide.
- **Per-kind usage flags** (→ our `usage_flags`): vertex = VERTEX **| STORAGE**
  (subdiv/compute writes) | TRANSFER_SRC/DST (vk_vertex_buffer.cc:207); index = INDEX
  **| STORAGE** | TRANSFER (vk_index_buffer.cc:113); uniform = UNIFORM (+STORAGE in vk,
  omitted — WebGPU forbids Uniform+Storage on one buffer) (vk_uniform_buffer.cc:42);
  storage = STORAGE **| INDIRECT** | TRANSFER (vk_storage_buffer.cc:82).
- **Upload heuristic:** Blender has NO size threshold — it branches on
  `is_mapped()`. But its inline `vkCmdUpdateBuffer` fast-path (used by uniforms)
  asserts **size ≤ 65536 && size%4==0** (vk_buffer.cc:146); larger goes through a
  staging buffer. ⇒ our `kWriteBufferStagingThreshold = 65536`: `queue.writeBuffer`
  (the WebGPU analog of the inline update) for ≤64 KiB, a dedicated staging buffer +
  `CopyBufferToBuffer` above it. Faithful, not arbitrary.
- **Alignment:** copies require 4-byte offset/size (vk_buffer.cc:146); dynamic UBO/
  SSBO binds need `minUniformBufferOffsetAlignment` / `minStorageBufferOffsetAlignment`
  (vk_context.cc:33, vk_storage_buffer.cc:50). ⇒ constants `kCopyAlignment=4`,
  `kUniformOffsetAlignment=256`.
- **Indices:** Blender uses BOTH 16- and 32-bit (`GPU_INDEX_U16/U32`,
  GPU_index_buffer.hh:26-29); U16 buffers carry an `index_base_` (min-index subtracted,
  added back at draw, gpu_index_buffer.cc:334-348). ⇒ `to_wgpu_index_format(is_32bit)`
  → Uint32/Uint16; the base-index offset is a vertbuf-level concern for T6 integration.
- `VKIndexBuffer::update_sub` is `NOT_YET_IMPLEMENTED` upstream (vk_index_buffer.cc:101);
  our wrapper implements sub-update uniformly for all kinds.

## Live results (Apple M4 Pro, Metal) — 5/5 PASS

Every buffer kind create + upload + **byte-exact readback** + sub-range update:
Vertex(4 KiB), Index(4 KiB), Uniform(256 B), Storage(8 KiB) all OK. The **20 MiB**
storage buffer (> the 64 KiB threshold) exercised the staging + `CopyBufferToBuffer`
update path and its tail read back byte-exact. Harness exit 0.

---

# PART 2 — T10.pre state tables (`sandbox/wgpu-state-tables/`)

`wgpu_state_table.{hh,cc}` — the mapping; `tests/wgpu_state_table_test.cc` — live
harness that CREATES a render pipeline per state config (creation validates the
descriptor). API: `to_blend`, `to_depth`, `to_stencil`, `to_cull_mode`,
`to_front_face`, `to_color_write_mask`, `provoking_vertex_is_native`.

## The blend table (VERBATIM from `opengl/gl_state.cc:335-439`)

Blend equation `final = SRC*srcF + DST*dstF`. Transcribed from the GL backend
(the canonical source) and **verified byte-identical in the Vulkan
(`vk_graphics_pipeline.hh:603-724`) and Metal (`mtl_state.mm:394+`) backends**.
GL_* → `wgpu::BlendFactor`; equation → `wgpu::BlendOperation`.

| GPU_BLEND_* | color (src,dst) | alpha (src,dst) | op | note |
|---|---|---|---|---|
| NONE | — | — | — | blend disabled (no BlendState) |
| ALPHA | SrcAlpha, OneMinusSrcAlpha | One, OneMinusSrcAlpha | Add | |
| ALPHA_PREMULT | One, OneMinusSrcAlpha | One, OneMinusSrcAlpha | Add | |
| ADDITIVE | SrcAlpha, One | Zero, One | Add | |
| ADDITIVE_PREMULT | One, One | One, One | Add | |
| MULTIPLY | Dst, Zero | DstAlpha, Zero | Add | |
| SUBTRACT | One, One | One, One | **ReverseSubtract** | |
| INVERT | OneMinusDst, Zero | Zero, One | Add | SRC*(1-DST); NOT a logic op |
| MIN | One, One | One, One | **Min** | factors ignored |
| MAX | One, One | One, One | **Max** | factors ignored |
| OIT | One, One | Zero, OneMinusSrcAlpha | Add | needs OIT FB setup |
| BACKGROUND | OneMinusDstAlpha, SrcAlpha | Zero, SrcAlpha | Add | |
| CUSTOM | One, **Src1** | One, **Src1Alpha** | Add | **dual-source** (feature-gated) |
| ALPHA_UNDER_PREMUL | OneMinusDstAlpha, One | OneMinusDstAlpha, One | Add | |
| OVERLAY_MASK_FROM_ALPHA | Zero, OneMinusSrcAlpha | Zero, OneMinusSrcAlpha | Add | |
| TRANSPARENCY | One, SrcAlpha | Zero, SrcAlpha | Add | |

**Coverage: 16/16 GPUBlend arms map to WebGPU. Exactly 1 (CUSTOM) is feature-gated**
(dual-source blending: WebGPU `dual-source-blending` feature + a WGSL fragment
declaring `@location(0) @blend_src(0)` and `@blend_src(1)` outputs; vk gates it on
`dualSrcBlend` at vk_backend.cc:175). **0 arms are unmappable** — all factors/ops
(incl. ReverseSubtract, Min, Max, OneMinusDst, Src1) exist in WebGPU core/feature.

## Depth / stencil / cull / write-mask (all expressible)

- **GPUDepthTest** → `depthCompare` + `depthWriteEnabled` (gl_state.cc:184-206):
  NONE→{write off, Always}, ALWAYS→{on, Always}, LESS→Less, LESS_EQUAL→LessEqual,
  EQUAL→Equal, GREATER→Greater, GREATER_EQUAL→GreaterEqual.
- **GPUStencilTest×Op** → `wgpu::StencilFaceState` front/back (gl_state.cc:218-266).
  The shadow-volume counters map cleanly: COUNT_DEPTH_PASS → back `passOp=IncrementWrap`,
  front `passOp=DecrementWrap`; COUNT_DEPTH_FAIL → back `depthFailOp=DecrementWrap`,
  front `depthFailOp=IncrementWrap` (WebGPU has `increment-wrap`/`decrement-wrap`).
  Reference/read/write masks come from mutable state (`stencilReadMask`/`WriteMask`).
- **GPUFaceCullTest** → `cullMode` (None/Front/Back); winding `to_front_face(invert)`
  → CW/CCW (GL default CCW; gl_state.cc:290-303).
- **GPUWriteMask** → `wgpu::ColorWriteMask` (R/G/B/A); DEPTH/STENCIL write bits map to
  `depthWriteEnabled` / `stencilWriteMask` separately.

## The gaps (WebGPU has none of these) — recon + T10 plan

| gap | severity | finding + plan |
|---|---|---|
| **Wide lines** (`GPU_line_width`>1) | **SOLVED** | WebGPU (like Metal) has no wide lines. Blender already expands wide lines in a portable VERTEX shader — `gpu_shader_3D_polyline_vert.glsl` (offset math :172-175) driven by `viewportSize`/`lineWidth` push constants. Metal relies on the same (mtl never sets line width). ⇒ route wide lines through the polyline shader; ignore `GPU_line_width` for raster. |
| **Point size** (`gl_PointSize`) | **the one UNSOLVED raster gap** | 8 shaders write `gl_PointSize` directly; Metal keeps it via `[[point_size]]`, Vulkan via the builtin — WGSL has NO point-size builtin and points are 1px, with NO existing portable fallback. ⇒ each point shader needs a quad/instanced-expansion rewrite (like the polyline shader). Widespread call sites (editors/interface, mesh, graph). Flag for the render milestones. |
| **Logic-op XOR** (`GPU_logic_op_xor_set`) | LOW | WebGPU has no logic ops. Only 3 call sites, all XOR marquee/rubber-band overlays (ed_util_imbuf.cc:426,432; clip_draw.cc). Non-critical editor UI; emulate with an inverted-blend/shader path or defer. |
| **Polygon mode / smooth** | NON-ISSUE | Zero `glPolygonMode`/`VK_POLYGON_MODE_LINE`/Metal-fill-line hits tree-wide; wireframe is done via overlay/edge shaders. `GL_POLYGON_SMOOTH`/`LINE_SMOOTH` are legacy `TODO: remove`. Nothing depends on them. |
| **Provoking vertex** | MEDIUM (in-shader) | WebGPU flat interpolation samples the FIRST vertex; Blender defaults to LAST (~17 EEVEE create-infos, via DRW `DRW_STATE_FIRST_VERTEX_CONVENTION`). No pipeline knob. Metal is the precedent: `set_provoking_vert` is a no-op and flat-shaded paths bake the convention into vertex shaders (SSBO vertex-pulling; mtl_state.mm:384-391). ⇒ emulate in shader-codegen for flat-shaded passes. |

## CUSTOM dual-source — live

The harness requests `DualSourceBlending` if the adapter exposes it and, when
present, validates CUSTOM with a real dual-source fragment shader
(`enable dual_source_blending; @blend_src(0)/@blend_src(1)`) + the Src1/Src1Alpha
blend. If absent, CUSTOM is reported SKIP with its mapping still asserted.

## Live results (Apple M4 Pro, Metal) — 38/38 pipelines PASS

Every mapped state config created a valid Dawn render pipeline (pipeline creation
validates the whole descriptor): **16/16 blend arms** (all created — and CUSTOM
was validated LIVE because the M4 adapter exposes `DualSourceBlending`, so the
dual-source `@blend_src` shader + Src1/Src1Alpha blend composed into a real
pipeline), **7/7 depth compares**, **9/9 stencil test×op combos** (incl. the
shadow-volume increment/decrement-wrap counters on front/back faces), **6/6
cull×winding**. 0 skipped. Harness exit 0.

---

# What T6 / T10 integration still needs

**T6:** key the wrapper on the real `GPUUsageType` + buffer classes; honor
`minUniform/StorageBufferOffsetAlignment` for dynamic-offset binds; carry the U16
`index_base_` at the vertbuf/indexbuf layer; mirror `VKStreamingBuffer`'s aligned
host arena for STREAM storage buffers if profiling shows writeBuffer churn.

**T10:** feed `to_blend/to_depth/to_stencil/...` from `GPUState`/`GPUStateMutable`
(gpu_state_private.hh) in `wgpu_pipeline.cc`'s descriptor build; gate CUSTOM on the
`dual-source-blending` feature + emit the `@blend_src` shader variant; implement the
point-size shader-expansion (the one real raster gap) and the flat-shading provoking
emulation for the render milestones; wire logic-op XOR overlays to an alternative or
defer. Depth/stencil/cull/blend are pure descriptor fills — no gaps.

# Verdict

Both modules are BUILT and PROVEN on live Dawn/Metal. T6: the buffer wrapper
covers all four kinds with a faithful (64 KiB-cutoff) upload heuristic — 5/5 live,
byte-exact, incl. the 20 MiB staging path. T10: the ENTIRE Blender state model maps
mechanically to WebGPU — **16/16 blend arms, 7 depth, stencil (incl. shadow-volume
wrap counters), cull/winding** all create valid pipelines (38/38), with only
CUSTOM feature-gated (dual-source, validated live on M4). The only genuine gaps are
NON-descriptor and well-characterized: point-size expansion (the one unsolved
raster gap, needs shader rewrites), provoking-vertex (emulate in-shader per Metal),
and logic-op XOR (3 non-critical overlays). Both are now integration tasks.
Confidence HIGH.
