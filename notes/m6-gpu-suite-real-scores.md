<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M6 GPU render suites: final Phase A rescore

This is the clean 50-scene browser rescore at outer HEAD `ac03fa6e540136f539c8cf84994a8e623b6f28ec`.
Each blend booted as the startup file in a fresh headed Chromium context. The run used no
persisted captures and no `REUSE=1`; every scored row has a fresh manifest. Workbench
pixels came from patch 0125's tick-pumped device-byte bridge and were compared to the
pinned Blender goldens at 0.016 / 1 percent. EEVEE uses 4/255 / 0.08 percent, but this
run produced no EEVEE bridge pixels, so no EEVEE row receives a pixel PASS or FAIL.

Completeness: exactly 20 Workbench plus 30 EEVEE rows, zero duplicates, zero missing/LFS
inputs, zero RIG-FAIL, zero browser crash, and zero reused manifests. The native census
also holds at 149 PASS / 7 FAIL / 2 CRASH, with static shaders 956/973.

## Headline

- Workbench improves to **12 PASS / 8 FAIL**, with no load flakes or render crashes.
- EEVEE is **28 NO-CAPTURE / 2 RENDER-ERR**. All 30 rows have zero readback kicks and
  zero device-byte captures. Therefore Phase A's required non-black behavioral acceptance
  is not met, including `principled_bsdf_default`.
- Phase A did remove the old C1-C4 validation flood: no fresh manifest contains the old
  Vertex-visible writable-storage, WriteOnly-format, or per-stage-limit signatures.
- The measured EEVEE residue is: 20 rows return `OK BLENDER_EEVEE` with zero GPU errors
  but do not fire the readback diagnostic hook inside `WGPUTexture::read`: layer-view
  wrappers have no local `texture_` and return early. Seven rows first fail on RG11B10Ufloat ReadWrite;
  `principled_bsdf_transmission` instead hits a writable RGBA16Float storage alias between
  bindings 2 and 3 at mip 7; and sheen plus subsurface never emit a START marker within
  the bounded 200-second render-progress window.
- All four shadow rows stop first at the Phase A' RG11B10Ufloat ReadWrite BGL failure.
  This matrix does not reach and therefore does not measure the Phase B atomic path.

## Workbench (20 rows)

| # | Scene | Verdict | Mean error | Max error | Pixels over | GPU errors | Cluster |
|---|---|---|---:|---:|---:|---:|---|
| 1 | `workbench/aa-disabled` | FAIL | 0.00295075 | 0.2588235139846802 | 388 pixels (2.37%) over 0.016 | 0 | pixel-delta |
| 2 | `workbench/aa-single-pass` | FAIL | 0.00419036 | 0.45098042488098145 | 704 pixels (4.3%) over 0.016 | 0 | pixel-delta |
| 3 | `workbench/dof` | FAIL | 0.0169481 | 0.34117648005485535 | 4357 pixels (26.6%) over 0.016 | 96 | render-bug:gpu-validation |
| 4 | `workbench/in_front` | FAIL | 0.00232644 | 0.21568632125854492 | 642 pixels (3.92%) over 0.016 | 0 | pixel-delta |
| 5 | `workbench/in_front_dof` | FAIL | 0.0210335 | 0.34117648005485535 | 5508 pixels (33.6%) over 0.016 | 96 | render-bug:gpu-validation |
| 6 | `workbench/light_flat_attribute` | PASS | 0.000227625 | 0.003921627998352051 | 0 pixels (0%) over 0.016 | 0 | pixel-pass |
| 7 | `workbench/light_flat_custom` | PASS | 0.000694125 | 0.047058820724487305 | 27 pixels (0.165%) over 0.016 | 0 | pixel-pass |
| 8 | `workbench/light_flat_random` | PASS | 0.000848269 | 0.05098038911819458 | 50 pixels (0.305%) over 0.016 | 0 | pixel-pass |
| 9 | `workbench/light_matcap` | PASS | 0.000819946 | 0.0313725471496582 | 29 pixels (0.177%) over 0.016 | 0 | pixel-pass |
| 10 | `workbench/light_matcap_no_specular` | PASS | 0.000783963 | 0.023529410362243652 | 9 pixels (0.0549%) over 0.016 | 0 | pixel-pass |
| 11 | `workbench/light_studio_material` | PASS | 0.000785399 | 0.14901959896087646 | 40 pixels (0.244%) over 0.016 | 0 | pixel-pass |
| 12 | `workbench/light_studio_object` | PASS | 0.000832472 | 0.05098038911819458 | 46 pixels (0.281%) over 0.016 | 0 | pixel-pass |
| 13 | `workbench/light_studio_object_no_specular` | PASS | 0.000487723 | 0.0156862735748291 | 0 pixels (0%) over 0.016 | 0 | pixel-pass |
| 14 | `workbench/x-ray` | PASS | 0.000298155 | 0.00784313678741455 | 0 pixels (0%) over 0.016 | 0 | pixel-pass |
| 15 | `workbench/x-ray_0` | PASS | 0.000127895 | 0.003921627998352051 | 0 pixels (0%) over 0.016 | 0 | pixel-pass |
| 16 | `workbench/x-ray_1` | FAIL | 0.00833756 | 0.21176475286483765 | 2435 pixels (14.9%) over 0.016 | 0 | pixel-delta |
| 17 | `workbench/x-ray_back_cull` | PASS | 0.000279326 | 0.007843166589736938 | 0 pixels (0%) over 0.016 | 0 | pixel-pass |
| 18 | `workbench/x-ray_in_front` | PASS | 0.000281081 | 0.007843166589736938 | 0 pixels (0%) over 0.016 | 0 | pixel-pass |
| 19 | `colorspace/acescg_blackbody` | FAIL | 0.0192027 | 0.0627450942993164 | 8033 pixels (49%) over 0.016 | 0 | pixel-delta |
| 20 | `colorspace/rec2020_lights` | FAIL | 0.107421 | 0.1450980305671692 | 16384 pixels (100%) over 0.016 | 0 | pixel-delta |

**Aggregate:** FAIL=8, PASS=12

## Eevee (30 rows)

| # | Scene | Verdict | Mean error | Max error | Pixels over | GPU errors | Cluster |
|---|---|---|---:|---:|---:|---:|---|
| 1 | `colorspace/acescg_blackbody` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 2 | `colorspace/rec2020_lights` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 3 | `transparency/transparency_blended` | NO-CAPTURE | - | - | - | 2 | render-blocked:gpu-validation |
| 4 | `transparency/transparency_dithered` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 5 | `shadow/shadow_filter` | NO-CAPTURE | - | - | - | 2 | render-blocked:gpu-validation |
| 6 | `shadow/shadow_min_pool_size` | NO-CAPTURE | - | - | - | 2 | render-blocked:gpu-validation |
| 7 | `shadow/shadow_resolution` | NO-CAPTURE | - | - | - | 2 | render-blocked:gpu-validation |
| 8 | `shadow/shadow_resolution_scale` | NO-CAPTURE | - | - | - | 2 | render-blocked:gpu-validation |
| 9 | `raycast/raycast_attribute` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 10 | `raycast/raycast_bump` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 11 | `raycast/raycast_direction_constant` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 12 | `raycast/raycast_hit` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 13 | `raycast/raycast_normal` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 14 | `raycast/raycast_position` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 15 | `raycast/raycast_visibility` | NO-CAPTURE | - | - | - | 2 | render-blocked:gpu-validation |
| 16 | `principled_bsdf/principled_bsdf_coat` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 17 | `principled_bsdf/principled_bsdf_coat_zero_weight` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 18 | `principled_bsdf/principled_bsdf_default` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 19 | `principled_bsdf/principled_bsdf_emission` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 20 | `principled_bsdf/principled_bsdf_emission_alpha` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 21 | `principled_bsdf/principled_bsdf_metallic` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 22 | `principled_bsdf/principled_bsdf_sheen` | RENDER-ERR | - | - | - | 0 | render-start-timeout |
| 23 | `principled_bsdf/principled_bsdf_specular` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 24 | `principled_bsdf/principled_bsdf_subsurface` | RENDER-ERR | - | - | - | 0 | render-start-timeout |
| 25 | `principled_bsdf/principled_bsdf_thin_glass` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 26 | `principled_bsdf/principled_bsdf_thin_subsurface` | NO-CAPTURE | - | - | - | 2 | render-blocked:gpu-validation |
| 27 | `principled_bsdf/principled_bsdf_thinfilm_metallic` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 28 | `principled_bsdf/principled_bsdf_thinfilm_reflection` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 29 | `principled_bsdf/principled_bsdf_thinfilm_transmission` | NO-CAPTURE | - | - | - | 0 | no-capture |
| 30 | `principled_bsdf/principled_bsdf_transmission` | NO-CAPTURE | - | - | - | 2 | render-blocked:gpu-validation |

**Aggregate:** NO-CAPTURE=28, RENDER-ERR=2

## Workbench residuals

The two DoF scenes each emit 96 validation errors from three distinct root classes before
their invalid-command-buffer cascades:

1. Depth32FloatStencil8 offers UnfilterableFloat or Depth where the layout expects Float.
2. An RGBA16Float attachment view exposes mipLevelCount 3, while attachments require 1.
3. RG8Unorm is sampled and writable as a render attachment in the same synchronization scope.

The remaining clean Workbench pixel deltas are `aa-disabled`, `aa-single-pass`, `in_front`,
and `x-ray_1`. The `acescg_blackbody` and `rec2020_lights` rows remain intentionally
reported but color-management-confounded: the bridge decoder applies Standard sRGB, while
those scenes use ACES 2.0 / Rec.2020 with exposure. Under D-10 they are not evidence of a
backend pixel regression and cannot be accepted as faithful M6 parity until the real display
transform or caller-facing readback path is used.

## EEVEE outcome taxonomy

- `NO-CAPTURE / no-capture`: render returns OK with zero captured validation errors, but
  the readback diagnostic hook inside `WGPUTexture::read` does not fire because layer-view
  wrappers have no local `texture_` and return early, so no final device bytes were captured.
- `NO-CAPTURE / render-blocked:gpu-validation`: the render returns, but a measured validation
  blocker prevents a capturable final result. Seven are RG11B10Ufloat ReadWrite; one is the separate
  RGBA16Float writable-storage alias in `principled_bsdf_transmission`.
- `RENDER-ERR / render-start-timeout`: the bounded retry observes no fd2 START marker within
  200 seconds, so there is no proof the bpy timer entered `_bw_render`. The second bounded
  run confirms no START or terminal marker in that window, not an in-render loop hang.

## Evidence

- Raw matrix: `sandbox/gpu-r35/results.tsv`
- Per-scene manifests and decoded Workbench images: `sandbox/gpu-r35/caps/`
- fd2 control: `sandbox/gpu-m6-rescore-final/marker-control/`
- Native census: `sandbox/gpu-m6-rescore-final/native-census-summary.txt`
- Proof images and contact sheet: `sandbox/gpu-m6-rescore-final/proof/`
