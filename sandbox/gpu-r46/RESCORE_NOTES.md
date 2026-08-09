<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# r46 20-scene rescore - reading results.tsv

Build: build-wasm-windowed-opt/bin/blender_browser.wasm (18:17, pure pre-i18n, built by round 3
from the exact WIP source; served on port 8128). Comparator: r35 score.py, verbatim m6 thresholds.

## Headline: the bindgroup-6v7 signature is 100% ELIMINATED
NO scene in results.tsv shows `bindgroup-6v7`. Every previously-6v7 scene (aa-*, dof, in_front*,
light_flat_custom/random, light_studio_object*, x-ray_1) now shows either a much smaller
`gpu-validation` residual or renders. Error-count collapse vs the committed r44r2 (0122) tsv:

  scene                          r44r2 (0122)            r46 (0124)
  aa-disabled                    RENDER-BLACK 42 6v7     RENDER-BLACK 3 gpu-validation
  aa-single-pass                 RENDER-BLACK 42 6v7     RENDER-BLACK 3 gpu-validation
  light_flat_custom              FAIL 456 6v7            FAIL 24 gpu-validation
  light_flat_random              FAIL 456 6v7            FAIL 24 gpu-validation
  light_studio_object            FAIL 456 6v7            FAIL 24 gpu-validation
  light_studio_object_no_specular FAIL 456 6v7           FAIL 24 gpu-validation
  in_front_dof                   FAIL 432 6v7            FAIL 120 gpu-validation
  x-ray_1                        FAIL 336 6v7            FAIL 24 gpu-validation

## RENDER-CRASH rows are boot-timeout FLAKES (gpuErr=0), not GPU regressions
This harness boots a full 101 MB Blender wasm per scene; under load several scenes hit the 200 s
bridge timeout -> RENDER-CRASH with gpuErr=0. They render on a clean re-run:
- light_matcap: reconfirmed clean = 0 GPU errors, renders (caps/workbench_workbench_light_matcap_reconfirm/).
  It is a real PASS (committed r44r2: PASS 0 gpuErr).
- light_studio_material: PASS on pixels in committed r44r2 (18 gpuErr, the 1v4 compute); its 1v4
  compute error occasionally breaks the render (crashed here with the bindgroup-1v4 sig).
- dof / in_front / x-ray_0 / x-ray_in_front: render on other runs (see the committed r44r2 tsv and
  the individual x-ray capture, 81 gpuErr color-compaction).

## True verdicts (flakes resolved from committed r44r2 + individual clean runs)
PASS = 4, UNCHANGED from r44r2: light_flat_attribute, light_matcap, light_matcap_no_specular,
light_studio_material. The 6v7 fix removes the bindgroup-count ERROR (a prerequisite) but does not
by itself flip the ex-6v7 scenes to PASS - they still fail pixels on the DISTINCT depth-Uint
residual (a Depth32FloatStencil8 texture on a Uint object_id sampler slot).

## Residual clusters (all DISTINCT; re-diagnosed from live Dawn messages)
- gpu-validation 81 (x-ray, x-ray_back_cull, x-ray_in_front, + x-ray_0) = color-target COMPACTION
  on NONE-gap TransparentDepthPass framebuffers (R16Uint object_id -> targets[0] vs float
  @location(0)). Out of the 6-file fence -> diagnosis-only.
- gpu-validation 24 (light_flat_custom/random, light_studio_object*, in_front, x-ray_1) = depth
  texture on a Uint object_id sampler slot (residual bind collision, 0122 namespace follow-up).
- gpu-validation 120 (in_front_dof, dof) = the same depth-Uint plus the DoF compute chain.
- bindgroup-1v4 (light_studio_material) = compute storage-image dispatch emits 1 of 4 entries.
- pixel-delta (acescg_blackbody) = a pre-existing colorspace pixel diff, 0 GPU errors (not GPU).
- rec2020_lights = x-ray-family color path (transparent), gpu-validation.

Full per-scene unique Dawn errors: caps/workbench_workbench_{x-ray,light_studio_object,
light_studio_material}/gpuerrors.uniq.txt.
