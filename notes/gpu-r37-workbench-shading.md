<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 r37 (gpu-shading lane) - the workbench solid-shading FLIP is a signed-packed-normal
# format bug (patch 0119); the "darkening" is a SEPARATE view-transform residual; the
# blue spike is a window-direct overlay-origin residual. Two GPU defects triaged, one FIXED.

Pin: Blender 5.2 `fbe6228777e7`. Builds: `build-wasm-windowed-opt` (relinked with 0119
2026-08-08 ~15:40) + `build-native-gpu` (rebuilt with 0119). Rig: headed node-Playwright,
bundled Chromium, `NODE_PATH=/Users/paws/plushly/game-platform/node_modules`, port 8123,
`?gate=1600x900` (DPR 1), `?pyexpr=` with `os.write(2,…)` + BW_DIAG/BW_DIAG_ARM readback
(patch 0117). Drivers: `sandbox/gpu-r37/disc.mjs` (+ `r37-disc{1,2,3}.result.json`).

## DEFECT 1 - workbench solid shading. ROOT CAUSE FOUND + FIXED (patch 0119): signed
## packed normals (GPU_COMP_I10) were decoded UNSIGNED, sign-flipping negative components.

### Discriminator (no rebuild, existing 0117 readback on the pre-fix binary)
`disc.mjs` boot-armed BW_DIAG_ARM=3, read back the workbench prepass gbuffer
(`prepass_normal` RG16Float, `prepass_material`, `prepass_objectid`, `prepass_depth`) at
state (a), decoded the sphere-map normals, clustered the visible cube faces, and named each
by transforming to world via the bpy `region_data.view_matrix`. Default view, camera world
pos ≈ (+15, -6.7, +8.2) ⇒ visible faces MUST be **+X, +Z, -Y**.

Pre-fix gbuffer (r37-disc2):
| face (by count) | decoded view normal | world axis | mean depth |
|---|---|---|---|
| 2141 px | [0.4024,-0.408,0.8195]  | **+X** (correct) | 0.99944 |
| 1037 px | [-0.0008,0.8951,0.4459] | **+Z** (correct) | 0.99945 |
|  814 px | [0.9149,0.1799,**-0.3615**] | **+Y** (WRONG - should be -Y) | 0.99945 |

The three normals are perfectly orthonormal, all at the same near depth (all front faces),
but the leftmost face's normal is `+Y` (view-Z NEGATIVE = pointing away from camera) when
the visible face is `-Y`. It is a **pure sign flip of exactly that face**. +X and +Y and +Z
are all decoded exactly = the view-matrix columns. The only visible face with a NEGATIVE
object-space component (`-Y` = (0,-1,0)) is the one that's wrong; +X=(1,0,0) and +Z=(0,0,1)
are all-non-negative and correct. => the SIGN of negative components is being dropped.

### Root cause
`to_wgpu_vertex_format` (wgpu_pipeline.cc, pre-r37 line ~88) mapped `GPU_COMP_I10`
(Blender's SIGNED packed normal, 2_10_10_10_REV, `GPU_FETCH_INT_TO_FLOAT_UNIT`) to
`wgpu::VertexFormat::Unorm10_10_10_2` - the UNSIGNED normalized format. WebGPU/Dawn has NO
signed snorm 10-10-10-2 vertex format (only `Unorm10_10_10_2`; confirmed in
emdawnwebgpu `webgpu_cpp.h`). Unsigned decode of a signed component: -1.0 packs as signed
-511 (two's-complement bit pattern 513), decodes UNORM as 513/1023 ≈ +0.5 (POSITIVE). So
(0,-1,0) reads as (0,+0.5,0) → normalize → +Y. Positive components stay positive
(511/1023≈0.5 → +1 after normalize), so all-positive faces are unaffected. Vulkan uses the
native signed `VK_FORMAT_A2B10G10R10_SNORM_PACK32` (vk_common.cc:244), which is why the
native oracle shades correctly. This was PRE-DIAGNOSED and deferred as
`gpu-comp-i10-vertex-format` (ledger/deferred.json) - r37 confirmed it is THE cause of the
workbench shading flip and implemented the deferral's own suggested fix ("CPU pre-expand to
a supported signed format").

### Fix (patch 0119, wgpu_pipeline.cc + wgpu_vertex_buffer.cc)
Since WebGPU lacks signed 10-10-10-2, transcode at upload to `Snorm8x4` (same 4 bytes, so
stride/offset unchanged for both interleaved and deinterleaved layouts):
1. `to_wgpu_vertex_format`: normalized `GPU_COMP_I10` → `VF::Snorm8x4`.
2. `WGPUVertexBuffer::upload_data`: `transcode_i10_attrs` unpacks each 2_10_10_10 signed
   field (sign-extended 10-bit / 511) to four signed bytes in a scratch copy (never mutates
   `data_`; DYNAMIC/STREAM re-upload safe). 8-bit is exact for the axis normals (±1/0) and
   ample for workbench; higher precision would need a wider format + a stride rebuild.

### Verify
- **Native Dawn census (build-native-gpu, harness m3):** the deferred test
  `vertex_buffer_fetch_mode__GPU_COMP_I10__GPU_FETCH_INT_TO_FLOAT_UNIT` now **PASSES**.
  Census 148 PASS/8 FAIL/2 CRASH → **149 PASS / 7 FAIL / 2 CRASH**; static_shaders held
  956/973. NO regressions (newfail empty, no vanished expectations). The gate shows RED only
  as an "UN-DEFER-candidate" (harness `EXPECT_NONPASS` in run.sh:444 still lists the test as
  deferred - a harness/deferred.json reconciliation for the driver, harness/ is out of fence).
- **Web gbuffer (r37-disc3, post-fix):** the leftmost face now decodes to
  `[-0.9148,-0.1805,+0.3613]` = world **-Y**, view-Z now POSITIVE (toward camera). All three
  visible faces correct.
- **Parity (compare_fullscreen.sh VERBATIM 0.016/1, SELFTEST_PASS):** whole-window
  **163,469 px (11.4%) → 158,531 px (11%)**, mean 0.00873744 → **0.00824825**. Face
  brightness ORDERING now matches native (native top141>left122>front111; web-fixed
  top89>left85>front77) - the FLIP is gone (r34 web had left DARKEST). Evidence:
  `sandbox/gpu-r37/cube_native_vs_web_fixed.png`, `cube_native_web_diffx5_fixed.png`.

### DEFECT 1 residual (SEPARATE, NOT the direction bug, likely OUT of the gpu/webgpu fence)
After 0119 the cube is still uniformly darker than native (top 141→89, left 122→85, front
111→77; ~30-37% sRGB, ~2x linear, ratio GROWS with brightness). This is NOT a normal/light
direction issue (ordering matches native, +X/+Z normals always correct). Discriminated to
the **view-transform / colour-management path on the rendered image**:
- Bright DISPLAY-space overlays match native exactly (red X-axis 197 vs 198; viewport
  background 68 vs 69; green axis matches) at all brightness levels.
- Only VIEW-TRANSFORM-processed workbench geometry (the cube) is darkened, brightness-
  dependently (a tone-curve divergence, not a linear scale).
- Scene view transform = **AgX**, display = sRGB. => the web viewport applies the AgX view
  transform to the workbench render differently/darker than native. This is OCIO/colour-
  management (view transform LUT/shader or datafiles), NOT the GPU vertex/backend path r37
  owns. HANDOFF for a colour-management lane: compare the OCIO view-transform GPU shader /
  AgX LUT applied to the viewport render vs native; the overlays (display-space) are correct.

## DEFECT 2 - the "blue spike" (x~95, lower-left). CHARACTERIZED + NARROWED (not fixed).
A bright fusiform (spindle) vertical bar, brightest in the middle (~71-93/255), just inside
the viewport left edge (~x95, y~180-360), absent in native. Shape = a small overlay element
(sphere/gizmo) COLLAPSED horizontally by a degenerate/mis-origin transform. It is NOT the
scene light gizmo (projects upper-right) nor a normal-path artifact (persists post-0119). The
scissor/viewport is NOT set per overlay draw in the single-pass path (wgpu_batch.cc) - it is
geometry-driven - so naming the exact draw needs geometry-level (vertex-position) BW_DIAG,
a multi-cycle effort not spent this round (minor, ~3k px, pre-existing since r27, cosmetic).

STRONGEST HYPOTHESIS (aligns with the driver's r36 hand-off): the spike belongs to the SAME
**window-direct overlay viewport/origin/scissor family** as r36's DEFECT 2 (timeline
current-frame indicator DROPPED). r36 root-caused window-direct geometry
(`wmViewport(region->winrct)` → window backbuffer) as inconsistent with the 0115 blit
origin-flip: r36's element is dropped, this one lands mis-positioned/collapsed at the left.
SEAM for next round: window-direct overlay draw viewport/scissor origin consistency with the
0115 blit flip in `wgpu_framebuffer.cc` (+ possibly platform_web/ghost presentBackbuffer);
verify with the spike pixels + r36's timeline box. Triage r37-DEFECT2 + r36-DEFECT2 together.

## DO-NOT-RE-RUN (r37; r29-r36 lists still stand)
1. The workbench shading FLIP is the signed-I10-normal format bug. FIXED (0119). Do NOT
   re-investigate normal matrices / studiolight direction / std140 mat3 packing / UBO light
   layout - the normals were proven exact for +X/+Z and a pure sign-flip for -Y; the light
   DIRECTIONS are correct (post-fix face ordering matches native).
2. `GPU_COMP_I10` must NOT map to `Unorm10_10_10_2` (unsigned) - drops the sign of negative
   components. WebGPU has no snorm 10-10-10-2; use the Snorm8x4 upload transcode (0119) or a
   wider signed expand. Do not re-map to any unsigned 10-10-10-2 format.
3. The cube DARKENING is NOT a lighting-direction or normal or vertex-format bug. It is the
   view-transform (AgX/OCIO) applied to the render; display-space overlays (red axis 197,
   background 68) match native. Do NOT chase it in gpu/webgpu vertex/shading; it is a
   colour-management lane.
4. The blue spike is NOT normal-related (persists after 0119) and NOT the scene light gizmo.
   It is a window-direct overlay-origin collapse (0115/r36 family); do not look in the
   workbench prepass/composite for it.

## Evidence
`sandbox/gpu-r37/disc.mjs`; `r37-disc{1,2,3}.result.json`;
`cube_native_vs_web_fixed.png`, `cube_native_web_diffx5_fixed.png`, `left_edge_spike_fixed.png`
(+ .license CC0-1.0); patch `patches/0119-gpu-webgpu-i10-signed-normal-snorm8.patch`.
