<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# SampledBuffer (texel/buffer-texture) emulation — design note (M3.F10, r13)

**Status: DESIGN ONLY. No code written this round. Driver decides next round.**

93 static shaders fail with `tint ReadIR: SPIR-V capability 'SampledBuffer' is not
supported`. All 93 trace to ONE GLSL construct: `texelFetch(samplerBuffer, int_index)`.
WGSL has no texel/texture-buffer type; Tint's SPIR-V reader hard-rejects the SampledBuffer
capability. The Tint source is not vendored (only build objects under `build-deps/tint/…`),
so there is no local Tint patch surface — emulation is mandatory, nothing to wait on.

## 1. Who uses it (family breakdown, 93 shaders)

Exactly the three geometry types whose per-point/per-curve data Blender streams through an
OpenGL/Vulkan *buffer texture*: **curves (hair), point cloud, grease pencil.** No mesh
shader is among the 93.

| Family | Count | Geometry |
|---|---|---|
| workbench | 48 | `workbench_prepass_curves_*` (24) + `workbench_prepass_ptcloud_*` (24) |
| overlay | 24 | depth/outline/sculpt-selection/viewer-attribute for curves, ptcloud, gpencil |
| eevee | 18 | `eevee_surface_{capture,deferred,depth,forward,hybrid,occupancy,shadow,volume,world}_{curves,pointcloud}` |
| other | 3 | `draw_curves_test`, `gpencil_geometry`, `gpu_buffer_texture_test` |

By geometry: curves ≈ 44, pointcloud ≈ 41, gpencil ≈ 7, pure-test ≈ 1 (2 of the 93 are
compile-census tests, not render paths).

Root-cause resource declarations (pulled into every failing shader via `ADDITIONAL_INFO`):
- `draw/intern/shaders/draw_object_infos_infos.hh:67-68` — `draw_curves`: `curves_pos_rad_buf`
  (samplerBuffer), `curves_indirection_buf` (isamplerBuffer)
- `…draw_object_infos_infos.hh:73` — `draw_pointcloud`: `ptcloud_pos_rad_tx` (samplerBuffer)
- `…draw_object_infos_infos.hh:85-86` — `draw_gpencil`: `gp_pos_tx`, `gp_col_tx`
- `overlay/…/overlay_sculpt_curves_infos.hh:28`, `overlay_viewer_attribute_infos.hh:57,95`

Enum: `ImageType::{Float,Uint,Int}Buffer` (= `samplerBuffer`/`usamplerBuffer`/`isamplerBuffer`),
`gpu/intern/gpu_shader_create_info.hh:529`. Usage: `texelFetch(sampler, int)` in
`draw_curves_lib.glsl:78,100,149,156,272`, `draw_pointcloud_lib.glsl:42,124,129-144`, and the
eevee attribute libs.

## 2. Vulkan semantics we must emulate

Vulkan uses a real texel-buffer descriptor — a `VkBufferView` over the VertBuf:
- `vulkan/vk_common.cc:813-816` — SAMPLER + `{Float,Int,Uint}Buffer` → `UNIFORM_TEXEL_BUFFER`
  (`:760-763` IMAGE → `STORAGE_TEXEL_BUFFER`).
- `vulkan/vk_texture.cc:639-647` — `VKTexture::init_internal(VertBuf*)` stores `source_buffer_`;
  view built lazily via `vkCreateBufferView`, `format = to_vk_format()` (the VertBuf's own format).
- Texel format IS the VertBuf format: `gpu_texture.cc:418-436`. `*_pos_rad` = 4×f32 (RGBA32F);
  `curves_indirection_buf` = R32I.

Semantics to reproduce: **indexed fetch of typed texels from a linear GPU buffer, texel format
defined by the source VertBuf, returning a (format-expanded) vec4.** For the launch-relevant
buffers those formats are 32-bit → **no packing/conversion on fetch.**

## 3. Option (a) — storage-buffer-backed fetch — **RECOMMENDED**

Rewrite `samplerBuffer` → read-only `std430` storage buffer at codegen; `texelFetch(buf,i)` →
`buf[i]`. Bind the VertBuf as a read-only storage buffer.

Existing scaffolding (why this is the cheap path):
- `webgpu/wgpu_texture.cc:700-710` — `init_internal(VertBuf*)` already stashes `source_buffer_`
  but never consumes it (stub; comment: "forwarded at bind-group assembly").
- `webgpu/wgpu_buffer.cc:27-29` — every VertBuf is ALREADY allocated `Vertex | Storage`, so
  binding one as read-only storage needs **no allocation change**.
- `wgpu_shader_interface_map.cc:102-111` has `make_buffer_entry(...)`; `:79-82` has a
  `TexDim::Buffer` enum with a "route to textureLoad-only" TODO.
- Blender itself already dual-purposes these VertBufs: `draw/intern/draw_curves.cc` binds the
  same evaluated pos_rad VertBuf as an **SSBO** in the eval path and as a buffer-texture in draw.

Feasibility:
- **(i) Codegen sees the Buffer type — YES.** `print_image_type` (`wgpu_shader.cc:204-250`)
  already special-cases `{Float,Int,Uint}Buffer`; the declaration point (`print_resource`,
  `:363-402`) is fully ours to change to `layout(binding=…,std430) readonly buffer {…}`.
- **(ii) Bind path — MEDIUM.** Route the (formerly-sampler) binding to a storage-buffer entry
  backed by `source_buffer_`; wire `WGPUTexture`/`WGPUVertexBuffer` to surface the handle. Tint
  fully supports readonly storage + array indexing.
- **(iii) Format — SMALL for launch formats.** RGBA32F → `array<vec4<f32>>`, R32I →
  `array<i32>`; no reconstruction. Only non-32-bit custom-data attribute formats need WGSL
  unpacking (material-attribute rendering, not first geometry).

**The one real complication:** the customdata attribute helpers take the buffer **as a GLSL
function parameter** (`get_customdata_*(int, const samplerBuffer cd_buf)`,
`draw_curves_lib.glsl:247-264`, pointcloud `:127-144`, eevee attribute libs). GLSL passes a
*sampler* as a param but not a buffer block, so a naive swap breaks these signatures. The
**position/indirection buffers are global** (fetched directly), so the first-pixels path is
unaffected; only the attribute helpers need a refactor. This splits option (a) into a **small
core (positions)** and a **medium tail (attributes)**.

**Verdict: feasible, MEDIUM.** Matches how Blender already treats these VertBufs (SSBO); no
re-allocation; launch-critical formats need zero conversion.

## 4. Option (b) — wrap as 2D texture + index math — not preferred

`texelFetch(buf,i)` → `textureLoad(tex2d, vec2(i%W, i/W), 0)`.
- Must be **2D not 1D**: `maxTextureDimension1D` = 8192; dense hair/point counts exceed it →
  carry `W` uniform + `i%W,i/W` ALU on the hot path.
- **Upload cost:** linear VertBuf data must be repacked into 2D rows on every geometry update
  (option (a) binds the buffer as-is).
- Needs a device texture per VertBuf that (a) avoids. Sampler2D *can* be passed as a GLSL param
  (so the function-param sub-issue is easier here — the only point in b's favor).
- **Verdict: MEDIUM-LARGE, strictly more per-frame cost than (a). Fallback only if a specific
  attribute format resists storage-buffer reconstruction.**

## 5. Option (c) — Dawn/Tint native — none

No WGSL texel-buffer type; Tint reader hard-rejects SampledBuffer; not vendored → no patch
surface; no `texture_1d` escape hatch (same 8192 limit + still a device texture). Nothing to
wait for.

## 6. Gate need vs defer

**None of the 93 is on the mesh first-pixels path** — all are curves/pointcloud/gpencil; mesh
workbench+EEVEE use SSBO/vertex attributes and are absent from the 93. M4/M5/M6 default-cube,
edit mode, modifiers, geometry-nodes-(mesh), animation need **zero** of these to render. The
static suite checks compile only, so all 93 are census-only, not render regressions.

Against GOAL launch tier:
- **Defer outright (not launch tier):** grease pencil (~7) + the 2 GPU compile tests.
- **Defer early:** point cloud (~41) — not explicitly in launch tier; can trail mesh.
- **Launch-relevant when hair/curves enter the viewport:** curves (~44) — workbench+EEVEE curves
  and edit/sculpt overlays; only their **position/indirection** buffers (global, no conversion)
  are needed for first curve pixels.

## Recommendation + cost

Pursue **option (a), staged**:
1. **Core (SMALL):** global position/indirection buffers (`curves_pos_rad_buf`,
   `curves_indirection_buf`, `ptcloud_pos_rad_tx`) → readonly storage buffers, RGBA32F/R32I,
   no conversion. Unblocks curves+pointcloud geometry in workbench/EEVEE/overlay; clears the
   bulk (~85) of the census.
2. **Tail (MEDIUM):** refactor the param-passed customdata attribute helpers off the
   sampler-as-parameter shape; add WGSL unpack only for non-32-bit attribute formats.

**Defer** grease pencil + the 2 GPU buffer-texture tests to a later milestone; **point cloud**
shares (a)'s machinery but sequences after curves. Do not invest in (b) unless a format resists
storage reconstruction; treat (c) as unavailable.

Estimated cost: core ≈ 1 focused unit (codegen + one bind-path wire, positions only, verified
against `draw_curves_test`/workbench_prepass_curves compile); tail ≈ 1–2 units (helper refactor
+ attribute formats). Full 93 clear is ~3 units; first curve pixels need only the core.

Key files: `wgpu_texture.cc:700-710`, `wgpu_vertex_buffer.cc:149-153`, `wgpu_buffer.cc:27-29`,
`wgpu_shader.cc:204-250 / 363-402`, `wgpu_shader_interface_map.cc:79-135`,
`vk_common.cc:760-816`, `vk_texture.cc:639-647`, `gpu_texture.cc:418-436`,
`draw_object_infos_infos.hh:64-90`, `draw_curves_lib.glsl`, `draw_pointcloud_lib.glsl`.
