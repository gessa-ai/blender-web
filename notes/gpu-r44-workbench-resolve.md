<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 r44 (workbench-resolve lane) - the Solid-cube "darkening" is a push-constant ARRAY
# std140 stride bug that silently corrupts the workbench TAA accumulation weights. It is
# NOT in the studio-light resolve (that shader + all its inputs are provably correct).
# FIXED: patch 0123.

Pin: Blender 5.2 `fbe6228777e7`. Builds: `build-native-gpu` (census, rebuilt with 0123
2026-08-08 ~15:30) + `build-wasm-windowed-opt` (rebuilt with 0123 ~15:32). Rig: headed
node-Playwright, bundled Chromium, `NODE_PATH=/Users/paws/plushly/game-platform/node_modules`,
port 8128, `?gate=1600x900` (DPR 1), `?pyexpr=` with BW_DIAG boot-arm gbuffer readback
(patch 0117). Driver: `sandbox/gpu-r44/disc.mjs`.

## ROOT CAUSE (proven): WGPUShader::push_constant_set copies push-constant ARRAYS tightly
## packed; the shader block is std140 (16-byte element stride). The workbench TAA weights
## `float samplesWeights[9]` are read [w0,w4,w8,0,0,0,0,0,0] -> value-dependent darkening.

`wgpu_shader.cc` `WGPUShader::push_constant_set(location, comp_len, array_size, data)`
did `n = comp_len*array_size*4; memcpy(dst + slot.offset, data, min(n, slot.size))` - one
CONTIGUOUS blob. But:
- The block is std140: `layout(binding=1, std140) uniform constants { float samplesWeights[9]; }`
  (dumped from the generated GLSL). In std140 an array element's stride is rounded UP to 16.
- `std140_align_size` already reserves `slot.size = 16*9 = 144` for `float[9]`, and Tint emits
  `samplesWeights : array<tint_padded_array_element, 9u>` reading each float at stride 16
  (dumped WGSL, `sandbox/gpu-r44/taa.wgsl`). The SHADER side is correct.
- The frontend hands `push_constant("samplesWeights", weights_, 9)` = 9 floats TIGHTLY packed
  (36 bytes). The contiguous copy lands them at bytes 0,4,8,...,32; the shader reads at
  0,16,32,...,128. So `samplesWeights[0]=w0`, `[1]=w4`, `[2]=w8`, `[3..8]=0`.

The workbench TAA accumulation (`workbench_effect_taa_frag.glsl`) does, per sample,
`frag_color += log2(color+1) * samplesWeights[i]` over the 3x3 neighbourhood (i=0..8),
then the SMAA resolve normalises by `taa_accumulated_weight` = the FULL blackman-harris
weight sum (computed CPU-side, always correct). With 6 of 9 weights zero and the CENTER
weight (w4, the largest) misapplied to the (-1,0) tap, the accumulated weight is only
`w0+w4+w8` (~0.4 of the sum) while the divide uses the full sum. In log2 space this is
`web = (gold+1)^k - 1` with `k = (w0+w4+w8)/sum ~ 0.4`, i.e. a value-dependent scale that
hits the bright cube (~0.28 linear -> ~0.10) hardest and the dim world background least -
exactly r38's "near-constant ~0.4 linear, brightest face darkened most" signature. EVERY
TAA-resolved viewport pixel is affected; UI chrome (not TAA'd) is not, which is why r38 saw
the chrome "background" match while the 3D render darkened.

vk_* reference: Vulkan uses a std140 push-constant BUFFER (`VKPushConstants::Layout`,
BUFFER storage, `vk_shader_interface.cc:69`) that lays out and writes array elements at the
std140 16-byte stride. The web backend diverged only in the UPLOAD copy.

## FIX (patch 0123, wgpu_shader.cc push_constant_set only)
Write each array element at its std140 stride `dst_stride = (comp_len*4 + 15) & ~15`
(matches `std140_align_size`): when `array_size > 1 && dst_stride != src_stride`, copy
element-by-element (`src+e*src_stride -> dst+slot.offset+e*dst_stride`). vec4[]/mat4[]
(stride==src), single vectors and scalars fall through to the original fast contiguous copy,
so nothing else changes. No fudge factor - the upload now matches the std140 layout the
shader (and slot.size) already assume. This is GENERAL: it also corrects any latent
float[]/int[]/vec2[]/vec3[] push-constant array in other shaders.

## Falsified branches (all PROVEN correct on the web/GPU side this round - do not re-chase)
1. **The studio-light resolve shader is a FAITHFUL translation.** Dumped the resolve
   fragment WGSL (`sandbox/gpu-r44/resolve_default.wgsl`): fast_rcp constant (0x7eef370b),
   brdf_approx, blinn_specular, wrapped_lighting, the 4-light specular+diffuse sums, and the
   final combine ALL match the reference. Not the math.
2. **The WorldData UBO LAYOUT is correct.** The Tint-emitted WGSL struct matches std140 byte
   for byte (all vec2/vec4 pack identically; SolidLightData array stride 48; ambient@256,
   use_specular@324). Not a UBO struct-layout mismatch.
3. **The WorldData UBO VALUES reaching the GPU are correct.** Dumped the 352-byte upload
   bytes (BW_DIAG_WORLD, reverted): all 4 lights (dir/spec/diffwrap) match r37's CPU dump,
   `use_specular=1`, `ambient=(0,0,0)`. Not a value-upload bug.
4. **ViewMatrices layout correct -> incident vector I / NV correct.** ViewMatrices is 4x
   mat4 (viewmat/viewinv/winmat/wininv), zero std140-vs-WGSL divergence; wininv rides the
   same correctly-uploaded UBO as the correct winmat (geometry renders in place). Not I/NV.
5. **gbuffer material correct.** base_color=0.8, metallic=0, roughness~0.68 (native ~0.61,
   negligible), decoded from `material_tx.a` per face (`disc.mjs`). Not the material.
6. **normals correct** (r37 0119; re-confirmed n_view per face). Not normals.
7. Specular is NEGLIGIBLE at the measured centroids (CPU model: `resolve_full` ~= `resolve_
   nospec` ~= gold). r38's "specular loss" framing is wrong; the loss is on the DIFFUSE-
   dominated output, applied downstream of the resolve (the TAA weights).
8. OIT/transparent resolve is a NO-OP for the opaque cube (TransparentPass empty). Not OIT.

## DO-NOT-RE-RUN (r44; r37/r38 lists still stand)
1. The resolve shader (get_world_lighting) and its inputs (base_color, roughness/metallic,
   normals, incident vector, WorldData UBO layout AND values) are ALL proven correct on the
   web GPU side. Do NOT re-audit the studio-light resolve math or the World UBO for THIS
   darkening. The bug is in the push-constant UPLOAD, downstream in the TAA accumulation.
2. Push-constant scalar/single-vector/vec4[]/mat4[] uploads are correct; only sub-16-byte
   ARRAY element strides (float[]/int[]/vec2[]/vec3[]) were wrong. Fixed generally by 0123.
3. The viewport "darkening" was never colour management (r38) nor a lighting-direction/normal/
   vertex-format bug (r37). It is the TAA weight corruption.

## Verification
- **Face measurement (`disc.mjs`, identity render->window map confirmed by y-flip hitting
  background):** web/gold LINEAR ratios (G channel) top(+X) **0.372->1.015**, left(-Y)
  **0.383->1.014**, front(+Z) **0.484->1.050**. All ~1.0.
- **Whole-window parity (compare_fullscreen.sh VERBATIM 0.016/1, SELFTEST_PASS):**
  whole-window **2.19% -> 1.1%**; per-region **viewport 2.10% -> 0.48% (PASS)** - the
  darkening region collapsed to the AA floor. Residual whole-window is chrome only (topbar
  1.64%, toolbar 4.01%, statusbar 5.93% = text/glyph AA, other lanes).
- **Census (build-native-gpu, `run.sh --scope m3`):** **149 PASS / 7 FAIL / 2 CRASH /158**
  + **static_shaders 956/973**. The single gate RED is the KNOWN spurious I10 un-defer
  candidate (`vertex_buffer_fetch_mode__GPU_COMP_I10__GPU_FETCH_INT_TO_FLOAT_UNIT`,
  human-owed since 0119). No other regression - the shared shader text was untouched, only
  the backend upload changed.

## Evidence (`sandbox/gpu-r44/`)
`disc.mjs` (+ `r44-after.result.json`, `r44-after.all.log`); `resolve_default.wgsl`/`.glsl`
(faithful resolve); `taa.wgsl`/`.glsl` (samplesWeights std140 stride); `after_1600x900.png`
(+ `.license`) web capture; `after_composite_native_web_heatmap.png` (+ `.license`);
`census-m3.log`. Patch `patches/0123-gpu-webgpu-push-constant-array-std140-stride.patch`.
Instrumentation (BW_DIAG_RESOLVE WGSL dump in wgpu_shader.cc; BW_DIAG_WORLD UBO byte dump in
wgpu_uniform_buffer.cc; resolve_color capture in wgpu_diag_readback.cc) was reverted
grep-clean after diagnosis.
