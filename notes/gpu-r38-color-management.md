<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 r38 (colour-management lane) - the cube "darkening" is NOT the view transform.
# Both web AND the native oracle apply the **Standard** view transform to the Solid
# workbench viewport; the deficit is in the workbench studio-light RESOLVE (scene-linear
# render ~0.4x too dark). The mission premise (AgX/OCIO) and r37's handoff are FALSIFIED.

Pin: Blender 5.2 `fbe6228777e7` (oracle Blender 5.2.0 is the SAME hash). Build:
`build-wasm-windowed-opt` (relinked clean 2026-08-08 ~13:03 after instrumentation reverted).
Rig: headed node-Playwright, bundled Chromium, `NODE_PATH=/Users/paws/plushly/game-platform/node_modules`,
port 8129, `?gate=1600x900`. Driver: `sandbox/gpu-r38/disc.mjs`. Instrumentation was
BW_DIAG-gated dumps in `intern/opencolorio` + `wgpu_shader_compiler.cc` (fragment_source,
LUT metadata, OCIO params, WGSL, construct outcome) - **reverted grep-clean** after diagnosis.

## The curve-fit verdict (the discriminator the driver asked for)

r38 measured cube faces at r37 centroids (`sandbox/gpu-r38/cube-face-measurements.txt`):

| face  | golden disp (R,G,B) | web disp (R,G,B) | gold lin | web lin | web/gold (LINEAR) |
|-------|---------------------|------------------|----------|---------|-------------------|
| top   | 142,143,145         | 89,90,91         | 0.2747   | 0.1022  | **0.372** |
| left  | 133,135,136         | 86,86,86         | 0.2427   | 0.0931  | **0.383** |
| front | 108,110,114         | 77,78,78         | 0.1573   | 0.0762  | **0.484** |

- **c^2 double-gamma (driver's lead hypothesis): FALSIFIED, twice.** Prediction
  `web = native^2` (display) = 78/58/48; actual 89/85/77 (magnitude wrong). And the
  DIRECTION is wrong: c^2 gives factor=c, so brighter pixels darken *less*; observed is
  the opposite - the brightest face (top, 0.372 linear) is darkened *most*, the dimmest
  (front, 0.484) least. Gamma double-application is not the mechanism.
- **Near-constant LINEAR scale ~0.38-0.48.** `web_linear/gold_linear` is roughly constant.
  A constant scene-linear scale looks "brightness-dependent" in display space *only*
  because of the shared sRGB OETF. This is the signature of a **scene-referred intensity
  deficit through the SAME transfer function**, not a tone-curve / view-transform divergence.
- Not a clean power law in display or linear space.

## Root cause (proven): both sides apply the STANDARD view transform; web's workbench render is ~0.4x too dark

1. **The Solid workbench viewport applies "Standard", not AgX - on BOTH web and the oracle.**
   `IMB_colormanagement_setup_glsl_draw_from_space` (viewport, `gpu_viewport.cc:458`) is fed
   `viewport->view_settings` from `draw_color_management.cc` `viewport_settings_apply`. For
   default EEVEE-engine + Solid shading, `drw_color_management_type_for_v3d` returns
   `ViewTransform`, whose branch calls `BKE_color_managed_view_settings_init(..., nullptr)`
   -> the **config default view transform** (`colortools.cc:2064`), *ignoring* the scene's
   AgX. The config default resolves via `display->get_default_view()` =
   `get_view_by_index(0)` = `getView(sRGB, 0)`.
2. **`getView(sRGB,0) = getDefaultView(sRGB) = 'Standard'`** on the oracle (real Blender 5.2,
   PyOpenColorIO on the exact config; `sandbox/gpu-r38/oracle-getdefaultview-proof.txt`). The
   repo's bundled `config.ocio` is **byte-identical** to the oracle's
   (sha256 `dfc50d92ccd75f522c1160f83b8415bf706d5070`), `active_views` starts with `Standard`,
   `default_view_transform: Standard`. So the oracle's Solid cube is Standard too.
3. **Runtime proof (web):** the viewport's OCIO shader construct is `view=Standard display=sRGB
   look= nluts=0`, and its generated GLSL is exactly the sRGB OETF (monCurveRev breakPnt
   0.00304 / slope 12.92 / gamma 0.4167) + a [0,1] clamp - no AgX log2, no 3D LUT
   (`sandbox/gpu-r38/ocio-viewport-glsl-STANDARD.txt`). 16/16 viewport composite binds report
   `view=Standard nluts=0 valid=1 exponent=1 scale=1`, even after cycling the scene view
   transform through Filmic/Raw/... (Solid ignores scene VT, deterministically).
4. **Therefore** the display encode is identical on both sides; `scene_linear = sRGB_decode(display)`,
   and **web's workbench scene-linear render is ~0.37-0.48x the oracle's** (see table). The
   gbuffer `base_color` is correct (`0.8,0.8,0.8` all faces, r37 disc), so the deficit is in
   the **workbench studio-light RESOLVE**, not the material and not colour management. The
   per-face pattern (brightest/most-camera-facing face darkened most, most-oblique least) is
   consistent with reduced diffuse + missing/weak specular, *not* a lost constant ambient.

OCIO is fully alive in wasm (falsified suspect #2): `libocio` is compiled, `config.ocio` +
AgX `.cube`/`.spi1d` LUTs are in `blender_browser.data`, `LibOCIOConfig` (create_from_environment)
is used, the fallback config is not. sRGB attachment double-decode (suspect #1) is also out:
display-space overlays match (r37) and the same encode serves the (correct) overlays.

## SEAM HAND-OFF (to the workbench-shading / gpu lane, r37's domain - NOT colour management)

The workbench **solid studio-light resolve** produces scene-linear ~0.4x the oracle. Look in
`source/blender/draw/engines/workbench` (the deferred composite/resolve that combines the
gbuffer with the studio-light UBO + studio-light/matcap textures) and its gpu/webgpu
execution (studio-light UBO layout/values, or a resolve-shader translation). r37 dumped the
CPU-side `solid_lights` (dir/diff/spec) as correct - the deficit is in the GPU-side
application (magnitude), with specular apparently the largest loss. This is r37's workbench
lane; r37's residual note (defect-1 "darkening" deferred "to a colour-management lane") was
based on inferring AgX from `scene.view_settings.view_transform` - that inference is wrong for
Solid mode.

## DO-NOT-RE-RUN (r38)

1. The Solid workbench viewport applies **Standard** on BOTH web and the oracle
   (`getView(sRGB,0)=getDefaultView(sRGB)='Standard'`, config byte-identical). Do NOT chase
   AgX / the OCIO 3D LUT / log2 encoding / OCIO->WGSL translation for this darkening - the
   Solid viewport never applies AgX.
2. OCIO is NOT stubbed/fallback in wasm. Do NOT re-investigate WITH_OPENCOLORIO / the
   fallback curves / a missing LUT datafile for this.
3. The OCIO viewport shader is Standard (sRGB OETF + clamp, `nluts=0`). No 3D LUT is bound
   in the Solid composite. Do NOT investigate PromoteRGBA / NonFiltering-sampler-strip /
   3D-LUT upload for THIS darkening (they were checked and are structurally sound anyway).
4. gbuffer `base_color` is correct (`0.8`). The darkening is NOT the base colour / material.
5. c^2 gamma-double-application is FALSIFIED (magnitude and direction). The darkening is a
   ~constant LINEAR scene-referred scale, i.e. a workbench render-intensity deficit.

## Evidence (`sandbox/gpu-r38/`)
`disc.mjs`; `ocio-viewport-glsl-STANDARD.txt` (viewport shader = sRGB OETF, not AgX);
`oracle-getdefaultview-proof.txt` (PyOpenColorIO: getDefaultView(sRGB)=Standard);
`cube-face-measurements.txt`; `r38-run{1,2}.all.log` (BW_DIAG console). No patch: the fix is
outside the colour-management fence (workbench resolve). Instrumentation reverted grep-clean;
`build-wasm-windowed-opt` relinked clean.
