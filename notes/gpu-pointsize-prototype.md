<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M3.pointsize.pre — gl_PointSize → instanced-quad expansion (prototype + recipe)

Uncommitted worker notes for orchestrator review. Pin: Blender 5.2 `fbe6228777e7`;
Dawn `chromium/7989 @ 36cf1fae`. Companion module: `sandbox/wgpu-pointsize/`.
Closes the ONE unsolved raster gap from T10.pre. The program's first
RENDERED-CONTENT verification. `upstream/`, `patches/`, `build-native-gpu/`
untouched (read-only recon).

---

## 1. The gap + the affected shaders

WebGPU points are always 1px and WGSL has **no point-size builtin** and **no
`gl_PointCoord`**. Metal keeps `[[point_size]]`, Vulkan the `PointSize` builtin —
WGSL has neither. Every `GPU_PRIM_POINTS` shader that writes `gl_PointSize` must be
rewritten to draw an instanced quad per point.

The 8 `gl_PointSize` writers in `gpu/shaders/` (rg, read-only) — the core set:
1. `gpu_shader_2D_point_uniform_size_aa_vert.glsl`
2. `gpu_shader_3D_point_uniform_size_aa_vert.glsl` ← **prototyped (representative)**
3. `gpu_shader_2D_point_uniform_size_outline_aa_vert.glsl`
4. `gpu_shader_2D_point_varying_size_varying_color_vert.glsl` (per-vertex `size` attr)
5. `gpu_shader_3D_point_varying_size_varying_color_vert.glsl` (per-vertex `size` attr)
6. `gpu_shader_3D_point_flat_color_vert.glsl`
7. `gpu_shader_keyframe_shape_vert.glsl` (dopesheet keyframes)
8. `gpu_shader_cxx_global.hh` (the C++ `gl_PointSize` decl — not a shader)

Plus ~15 in `draw/engines/overlay/shaders/` (loose verts, particles, edit-mode
dots) that follow the same two shapes: **uniform size** (from a push-constant) or
**varying size** (per-vertex attribute), with a `gl_PointCoord`-based circular/AA
fragment. The prototype covers the uniform+AA shape; the varying-size delta is one
line (§4).

## 2. Representative recon (read at the pin)

`gpu_shader_3D_point_uniform_size_aa` (vert) + `..._2D_..._aa` (frag):
- **VERT:** `gl_Position = MVP*vec4(pos,1); gl_PointSize = size;` where `size` is a
  push-constant (uniform). Then it computes concentric AA radii **in gl_PointCoord
  units**: `radii[0]=0.5*size; radii[1]=radius-1; radii /= size;` (flat varying).
- **FRAG:** `dist = length(gl_PointCoord - vec2(0.5)); a = mix(color.a, 0,
  smoothstep(radii[1], radii[0], dist)); if (a==0) discard;` — a filled circle with
  a 1px AA ring.
- Geometry: `GPU_PRIM_POINTS`, one vertex per point.

## 3. The mechanical rewrite recipe

Four localized changes; the AA/radii/fragment math is UNCHANGED.

| # | change | from | to |
|---|---|---|---|
| R1 | **primitive** | `GPU_PRIM_POINTS`, draw N verts | `GPU_PRIM_TRIS` triangle-strip, **draw 4 verts × N instances**; `pos` becomes a **per-instance** attribute (step mode Instance) |
| R2 | **corner** | (implicit point sprite) | `vec2 corner = corners[gl_VertexIndex];` with `corners = {(-0.5,-0.5),(0.5,-0.5),(-0.5,0.5),(0.5,0.5)}` |
| R3 | **size → offset** | `gl_PointSize = size;` | `vec4 c = MVP*vec4(pos,1); gl_Position = c + vec4((corner*size/viewport)*2.0*c.w, 0, 0);` (pixels→NDC ×2, ×w for perspective) |
| R4 | **gl_PointCoord** | `gl_PointCoord` in frag | interpolated `v_uv = corner + 0.5;` (vertex out → frag in) |

New uniform needed: **`viewport` (pixels)** — already a common push-constant in
Blender's overlay/polyline shaders (`sizeViewport`), so usually free. The `size`
source is identical (uniform, or the per-vertex attribute for the varying variants —
R3 just reads the attribute instead of the uniform; nothing else changes).

`gl_VertexIndex` after Tint = `@builtin(vertex_index)` (0..3 per instance);
`gl_PointCoord` has no WGSL analog, hence R4. The rewrite compiles cleanly through
the T7 chain (shaderc→Tint→WGSL) — no combined samplers, one UBO binding.

## 4. Live render-readback (Apple M4 Pro, Metal) — PASS

The rewrite compiled through the T7 chain (shaderc→Tint→WGSL, 1 UBO binding), a
pipeline was built, and a 3-point grid (pixel centers x=16,32,48) was RENDERED
offscreen into a 64×64 target at sizes 1/5/9 px. Readback of row 32 (cols 8..56,
`#`=lit, `.`=dark) — the actual rendered pixels:

```
  size= 1px row32: ........#...............#...............#........
  size= 5px row32: ......#####...........#####...........#####......
  size= 9px row32: ....#########.......#########.......#########....
```

The point diameter tracks `size` exactly (1→1px, 5→5px, 9→9px wide), the three
points stay separate with dark gaps, and the circle is symmetric about each center.
Per-size assertions ALL PASS: 3 centers lit, 2 gaps (x=24,40) dark, an inner-radius
pixel lit (size 5: +1px; size 9: +3px), an outer-radius pixel dark (size 1: +3px;
size 5: +5px; size 9: +6px). Harness exit 0. This is the program's first
rendered-content verification, and it confirms the size→clip-offset math (R3) is
pixel-accurate.

## 5. Placement recommendation — CODEGEN, not per-shader patches

**Recommendation: implement R1-R4 at the create-info / shader-codegen level, once,
NOT as 8+ hand-edited shaders.** Rationale:
- R1 (points→instanced-quad) is a **draw-time + create-info** change (primitive
  type + a synthetic per-instance binding + `Draw(4, N)`), parallel to how the
  Vulkan/Metal backends already special-case point drawing. It belongs in the
  WebGPU backend's batch/draw path (`wgpu_batch`) keyed on `GPU_PRIM_POINTS`, not in
  GLSL.
- R2/R3/R4 are a fixed GLSL **prologue + a `gl_PointCoord`→varying substitution**
  that the BSL/`shader_tool` preprocessor can inject when a create-info is tagged
  `point-expansion` (the same place the preprocessor already rewrites builtins).
  This mirrors the existing wide-line solution: Blender did NOT patch every
  line-drawing shader — it routes them through one `gpu_shader_3D_polyline` vertex
  expansion. Points should get the symmetric treatment.
- The upstream shaders keep writing `gl_PointSize`/`gl_PointCoord` (unchanged for
  GL/Metal/Vulkan); the WebGPU codegen path substitutes. Zero upstream shader edits
  → no divergence, no per-shader maintenance.

So the T-level work is: (a) `wgpu_batch` point-draw expansion (draw call + synthetic
binding), (b) a preprocessor pass emitting the R2-R4 prologue for point create-infos,
(c) the `viewport` push-constant wired for shaders that lack it. The 8 (+~15 overlay)
shaders then convert **rote / automatically**.

## 6. Verdict

The one unsolved raster gap is CLOSED in prototype: the gl_PointSize→instanced-quad
rewrite is mechanically specified (R1-R4), compiles through the real T7 shader
chain, and renders pixel-accurate point coverage at 1/5/9 px on live Dawn/Metal.
The recipe is rote and the recommended placement is codegen-level (a `wgpu_batch`
point-draw expansion + a preprocessor prologue), mirroring Blender's existing
wide-line solution — so the ~23 affected shaders convert with zero per-shader edits.
This completes the M3 backend pre-work program: every development-heavy chunk
(shader chain, binding map, formats+conversion, buffers, state tables) plus this
last raster gap is now standalone-proven on real hardware. Confidence HIGH.
