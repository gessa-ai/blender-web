<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M6 GPU render suites (workbench + EEVEE) - REAL scores via the r35 render-result bridge

Measured with the TICK-PUMPED RENDER-RESULT BRIDGE (patch 0125): the BW_DIAG-gated
hook in `WGPUTexture::read` kicks a tick-pumped async readback (AllowSpontaneous)
whose true device bytes land in `/tmp/bw_readback_<seq>.bin`, decoded + oiiotool-
compared to the staged goldens at Blender's own pinned thresholds. The bridge is
PROVEN on the workbench factory cube (real shaded pixels, 0 GPU errors); see the
self-test section. Each suite scene is booted as the STARTUP FILE (clean GPU context,
no live open_mainfile).

This CORRECTS the r34-truth-pass premise that "all 50 renders complete correctly and
readback is the sole M6 blocker": the readback path WORKS; the real blockers are
render-side (see clusters).

## workbench (20 scored)

| # | dir/test | verdict | mean_err | max_err | pct_over | gpuErr | cluster |
|---|----------|---------|----------|---------|----------|--------|---------|
| 1 | workbench/aa-disabled | RENDER-BLACK | - | - | - | 42 | render-bug:bindgroup-6v7 |
| 2 | workbench/aa-single-pass | RENDER-BLACK | - | - | - | 42 | render-bug:bindgroup-6v7 |
| 3 | workbench/dof | FAIL | 0.319203 | 0.9529411792755127 | 16384 pixels (100%) over 0.016 | 432 | render-bug:bindgroup-6v7 |
| 4 | workbench/in_front | FAIL | 0.32579 | 0.9529411792755127 | 16384 pixels (100%) over 0.016 | 336 | render-bug:bindgroup-6v7 |
| 5 | workbench/in_front_dof | FAIL | 0.339977 | 0.9529411792755127 | 16384 pixels (100%) over 0.016 | 432 | render-bug:bindgroup-6v7 |
| 6 | workbench/light_flat_attribute | FAIL | 0.250207 | 0.847058892250061 | 16384 pixels (100%) over 0.016 | 0 | pixel-delta |
| 7 | workbench/light_flat_custom | FAIL | 0.302472 | 0.8941177129745483 | 16384 pixels (100%) over 0.016 | 456 | render-bug:bindgroup-6v7 |
| 8 | workbench/light_flat_random | FAIL | 0.412044 | 0.9215686321258545 | 16384 pixels (100%) over 0.016 | 456 | render-bug:bindgroup-6v7 |
| 9 | workbench/light_matcap | FAIL | 0.300198 | 0.9019607901573181 | 16384 pixels (100%) over 0.016 | 24 | render-bug:bindgroup-6v10 |
| 10 | workbench/light_matcap_no_specular | FAIL | 0.286351 | 0.8588235974311829 | 16384 pixels (100%) over 0.016 | 24 | render-bug:bindgroup-6v10 |
| 11 | workbench/light_studio_material | FAIL | 0.239226 | 0.9215686321258545 | 16383 pixels (100%) over 0.016 | 42 | render-bug:bindgroup-1v4 |
| 12 | workbench/light_studio_object | FAIL | 0.260875 | 0.9490196108818054 | 16384 pixels (100%) over 0.016 | 456 | render-bug:bindgroup-6v7 |
| 13 | workbench/light_studio_object_no_specular | FAIL | 0.236708 | 0.7803922295570374 | 16384 pixels (100%) over 0.016 | 456 | render-bug:bindgroup-6v7 |
| 14 | workbench/x-ray | FAIL | 0.180053 | 0.5568628311157227 | 16381 pixels (100%) over 0.016 | 81 | render-bug:gpu-validation |
| 15 | workbench/x-ray_0 | FAIL | 0.216684 | 0.7960785031318665 | 16384 pixels (100%) over 0.016 | 81 | render-bug:gpu-validation |
| 16 | workbench/x-ray_1 | FAIL | 0.206159 | 0.9137255549430847 | 16380 pixels (100%) over 0.016 | 336 | render-bug:bindgroup-6v7 |
| 17 | workbench/x-ray_back_cull | FAIL | 0.186085 | 0.6078431606292725 | 16384 pixels (100%) over 0.016 | 81 | render-bug:gpu-validation |
| 18 | workbench/x-ray_in_front | FAIL | 0.191448 | 0.6078431606292725 | 16384 pixels (100%) over 0.016 | 82 | render-bug:gpu-validation |
| 19 | colorspace/acescg_blackbody | FAIL | 0.24158 | 0.4941176772117615 | 16384 pixels (100%) over 0.016 | 0 | pixel-delta |
| 20 | colorspace/rec2020_lights | FAIL | 0.233397 | 0.41960790753364563 | 16384 pixels (100%) over 0.016 | 37 | render-bug:gpu-validation |

**workbench aggregate:** FAIL=18, RENDER-BLACK=2

## eevee (30 scored)

| # | dir/test | verdict | mean_err | max_err | pct_over | gpuErr | cluster |
|---|----------|---------|----------|---------|----------|--------|---------|
| 1 | colorspace/acescg_blackbody | NO-CAPTURE | - | - | - | 30 | render-blocked:gpu-validation |
| 2 | colorspace/rec2020_lights | NO-CAPTURE | - | - | - | 67 | render-blocked:gpu-validation |
| 3 | transparency/transparency_blended | NO-CAPTURE | - | - | - | 32 | render-blocked:gpu-validation |
| 4 | transparency/transparency_dithered | NO-CAPTURE | - | - | - | 30 | render-blocked:gpu-validation |
| 5 | shadow/shadow_filter | NO-CAPTURE | - | - | - | 38 | render-blocked:gpu-validation |
| 6 | shadow/shadow_min_pool_size | NO-CAPTURE | - | - | - | 38 | render-blocked:gpu-validation |
| 7 | shadow/shadow_resolution | RENDER-CRASH | - | - | - | 38 | render-crash:gpu-validation |
| 8 | shadow/shadow_resolution_scale | NO-CAPTURE | - | - | - | 38 | render-blocked:gpu-validation |
| 9 | raycast/raycast_attribute | NO-CAPTURE | - | - | - | 30 | render-blocked:gpu-validation |
| 10 | raycast/raycast_bump | NO-CAPTURE | - | - | - | 30 | render-blocked:gpu-validation |
| 11 | raycast/raycast_direction_constant | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 12 | raycast/raycast_hit | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 13 | raycast/raycast_normal | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 14 | raycast/raycast_position | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 15 | raycast/raycast_visibility | RENDER-CRASH | - | - | - | 38 | render-crash:gpu-validation |
| 16 | principled_bsdf/principled_bsdf_coat | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 17 | principled_bsdf/principled_bsdf_coat_zero_weight | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 18 | principled_bsdf/principled_bsdf_default | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 19 | principled_bsdf/principled_bsdf_emission | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 20 | principled_bsdf/principled_bsdf_emission_alpha | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 21 | principled_bsdf/principled_bsdf_metallic | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 22 | principled_bsdf/principled_bsdf_sheen | RENDER-CRASH | - | - | - | 0 | render-crash |
| 23 | principled_bsdf/principled_bsdf_specular | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 24 | principled_bsdf/principled_bsdf_subsurface | RENDER-CRASH | - | - | - | 0 | render-crash |
| 25 | principled_bsdf/principled_bsdf_thin_glass | RENDER-CRASH | - | - | - | 34 | render-crash:gpu-validation |
| 26 | principled_bsdf/principled_bsdf_thin_subsurface | RENDER-CRASH | - | - | - | 38 | render-crash:gpu-validation |
| 27 | principled_bsdf/principled_bsdf_thinfilm_metallic | NO-CAPTURE | - | - | - | 30 | render-blocked:gpu-validation |
| 28 | principled_bsdf/principled_bsdf_thinfilm_reflection | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 29 | principled_bsdf/principled_bsdf_thinfilm_transmission | RENDER-CRASH | - | - | - | 30 | render-crash:gpu-validation |
| 30 | principled_bsdf/principled_bsdf_transmission | RENDER-CRASH | - | - | - | 42 | render-crash:gpu-validation |

**eevee aggregate:** NO-CAPTURE=10, RENDER-CRASH=20

## Aggregate (all scored)

| verdict | count |
|---------|-------|
| FAIL | 18 |
| NO-CAPTURE | 10 |
| RENDER-BLACK | 2 |
| RENDER-CRASH | 20 |

## Failure clusters

| cluster | count |
|---------|-------|
| render-crash:gpu-validation | 18 |
| render-bug:bindgroup-6v7 | 10 |
| render-blocked:gpu-validation | 10 |
| render-bug:gpu-validation | 5 |
| pixel-delta | 2 |
| render-bug:bindgroup-6v10 | 2 |
| render-crash | 2 |
| render-bug:bindgroup-1v4 | 1 |

### Cluster meanings
- **render-bug:bindgroup-6v7** - workbench render draw: WebGPU BindGroup has 6 entries
  but the layout expects 7 -> Invalid CommandBuffer -> Submit rejected -> black render.
  A backend bind-completion defect (class of patch 0116), scene/feature dependent
  (the factory default cube renders CLEAN, so it is not universal). REPORTED, not fixed.
- **render-bug:gpu-validation / device-lost** - EEVEE-Next pipeline creation fails:
  "Storage texture WriteOnly used with Vertex/Fragment visibility -> Invalid
  BindGroupLayout -> CreatePipeline". EEVEE-Next binds write-only storage textures in
  graphics stages, which WebGPU disallows (registered deferral: vertex-stage-rw-storage /
  storage-texture-atomics). The render never runs, so there is no final texture to read -
  NOT a readback blocker. REPORTED, not fixed.
- **pixel-delta** - the render produced CLEAN pixels (0 GPU errors) that exceed the
  golden threshold: a real shading/precision/feature delta, not a render crash.
- **PASS** - real pixels within Blender's own pinned oiiotool tolerance.

### Colour-management caveat
The decoder applies Blender's **Standard** view transform (linear->sRGB), verified on the
oracle for the vast majority of scenes. The `colorspace/acescg_blackbody` and
`colorspace/rec2020_lights` scenes use **ACES 2.0 / Rec.2020** display with a non-zero
exposure, which the pure-python decoder does NOT replicate. Any pixel-delta on those two
scenes is therefore CONFOUNDED by colour management and is not a pure render-accuracy
number; they are measured for completeness but flagged here.
