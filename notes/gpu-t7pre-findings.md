<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M3.T7.pre — WebGPU shader-compiler module, standalone-proven (findings)

Uncommitted worker notes for orchestrator review. Pin: Blender 5.2 `fbe6228777e7`;
Dawn `chromium/7989 @ 36cf1fae`. Companion to the committed module
`sandbox/wgpu-shader-compiler/`. Implements the NORMATIVE spec
`notes/gpu-binding-map-spec.md` §4-§5 as a reusable C++ module, so T7 becomes an
integration task, not a development task.

Goal: develop the two hardest T7 components OUTSIDE the Blender tree — against the
already-working `sandbox/dawn-probe` harness — and PROVE them end-to-end on a live
native Dawn/Metal device. `upstream/`, `build-native-gpu/`, `patches/` untouched
(read-only recon of `gpu_shader_create_info.hh` only).

---

## 1. Deliverable — the module (drop-in filenames)

Named so they drop straight into `source/blender/gpu/webgpu/`:

| file | role | external deps |
|---|---|---|
| `wgpu_shader_interface_map.{hh,cc}` | PURE mapping: create-info resource list → sampler_mappings + one group-0 BGL (spec §4-§5), incl. Sampler/Texture binding-type inference | webgpu_cpp.h only |
| `wgpu_shader_compiler.{hh,cc}` | the chain: shaderc(GLSL→SPIR-V 1.3) → Tint(ReadIR w/ sampler_mappings → ProgramFromIR → Generate) → WGSL + BGL | + shaderc, Tint |
| `tests/wgpu_shader_compiler_test.cc` | end-to-end harness: compile realistic shaders, build BGLs, create LIVE Dawn pipelines | + Dawn device |
| `tests/test_shaders.hh` | GLSL 450 corpus (bindmap ported from T2 + types + compute + array probe) | — |
| `CMakeLists.txt`, `build.sh` | extend the dawn-probe baseline (same Dawn checkout + link recipe) + libshaderc | — |

### API summary

```cpp
// wgpu_shader_interface_map.hh — pure, no device needed.
struct ResourceDesc { ResourceKind kind; uint32_t binding; uint32_t stages;
                      TexelClass texel; TexDim dim; bool filtering; uint32_t array_size;
                      bool storage_readonly; StorageTextureAccess/Format ...; };
InterfaceMap build_interface_map(const std::vector<ResourceDesc>&, uint32_t sampler_base = 0);
//   -> { sampler_base, sampler_mappings[{0,N}->{0,BASE+N}], entries[BindGroupLayoutEntry] }

// wgpu_shader_compiler.hh — the chain.
struct ShaderStageSources { std::string vertex, fragment, compute, name; };
CompileResult compile_shader(const ShaderStageSources&, const std::vector<ResourceDesc>&,
                             const CompileOptions& = {});
//   -> { ok, {vertex,fragment,compute}_wgsl, InterfaceMap interface, error }
```

The compiler couples the interface map's `sampler_mappings` to the Tint call and
returns the matching BGL, so the emitted WGSL binds identically to the layout the
backend builds — the entire point of the normative spec, now enforced in one call.

`build_interface_map` uses the **fixed SAMPLER_BASE = 256** policy (spec
open-question-2) and ASSERTS both invariants at runtime
(`max_resource_binding < SAMPLER_BASE` and
`SAMPLER_BASE + max_sampler_binding < maxBindingsPerBindGroup = 1000`), failing
loudly rather than mis-binding.

## 2. shaderc: use Blender's OWN precompiled lib (KEY build finding)

The module compiles GLSL→SPIR-V IN-PROCESS via `shaderc::Compiler::CompileGlslToSpv`
with `SetTargetEnvironment(shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_1)`
— exactly as `upstream/.../vulkan/vk_shader_compiler.cc:211` does, EXCEPT the env is
`vulkan_1_1` (SPIR-V 1.3), NOT Blender's `vulkan_1_2` (SPIR-V 1.5). This is the HARD
constraint from T1 (`notes/gpu-dawn-probe.md` §4a): Tint's IR SPIR-V reader hardcodes
`SPV_ENV_VULKAN_1_1` and rejects 1.5. **T7's `wgpu_shader_compiler.cc` must set
`shaderc_env_version_vulkan_1_1`.**

shaderc source: **Blender's own precompiled `lib/macos_arm64/shaderc/`** (fetched
out-of-tree at the pin by T3), so the standalone module links the SAME shaderc the
in-tree backend will (`bf::dependencies::optional::shaderc`). No new dependency,
no host `brew install` (host had none). This replaces dawn-probe's offline
`glslangValidator` step — the whole chain now runs inside the test binary.

### shaderc↔Tint SPIRV-Tools coexistence (a real T7 hazard — flagged)

Both `libshaderc` (bundles glslang + SPIRV-Tools) and Tint's `tint_lang_spirv_reader`
(consumes Dawn's own SPIRV-Tools for `SplitCombinedImageSamplerPass`) carry
SPIRV-Tools symbols. On one link line the STATIC `libshaderc_combined.a` +
static Tint SPIRV-Tools risk duplicate-symbol errors. The module links
`libshaderc_shared.dylib`, whose bundled glslang/SPIRV-Tools symbols are PRIVATE,
so they cannot clash with Tint's. **T7 integration must reproduce this**: the
WebGPU backend links BOTH shaderc and Tint in one binary (the Vulkan backend links
only shaderc, so it never hit this) — use the shaderc shared lib, or otherwise
ensure a single SPIRV-Tools on the link line.

## 3. Cases proven end-to-end — 4/4 gated PASS

Live on **"Apple M4 Pro", Metal, headless**. Every gated case: GLSL → module →
WGSL + BGL → **live Dawn pipeline created** (exit 0).

| case | shape | pipeline | result |
|---|---|---|---|
| `bindmap` | T2 pair: Globals UBO(V+F) · 2 combined sampler2D(F) · Material UBO · LightData SSBO-ro · Constants push-const UBO(V+F) | render | **PASS** |
| `types` | Globals UBO · sampler2D(float) · sampler2DShadow(compare) · usampler2D(texelFetch) | render | **PASS** |
| `compute_ssbo_atomic` | Params UBO · Histogram SSBO(rw)+atomicAdd · InputVals SSBO-ro | compute | **PASS** |
| `negative_control` | default-Tint (empty sampler_mappings) modules vs the spec layout | render | **PASS** (rejected) |

Observed WGSL confirms the spec exactly:
- `bindmap` frag: `color_tex_image texture_2d<f32> @binding(1)` +
  `color_tex_sampler sampler @binding(257)`; `normal_tex` @2/@258; `material` @3;
  `light_data` @4; shared `globals` @0 and `constants` @5 — identical across stages
  (spec §4.3 realised, now generated by the module in one `compile_shader` call).
- `compute` WGSL: `hist : Histogram_atomic`, `var<storage, read_write>` — Tint
  auto-wrapped the atomically-accessed SSBO member as `atomic<u32>` (R6 clears);
  `inp` is `var<storage, read>`. Compute pipeline created.
- `negative_control`: default Tint renumbered the fragment to
  `color sampler@2, normal tex@3, normal sampler@4, material@5, light@6, constants@7`
  (T2 Mode A reproduced). Against the spec layout a sampler sits on a texture/UBO
  binding → **Dawn REJECTS**. Rejection is the PASS — the module's mapping is
  load-bearing, not cosmetic.

## 4. Qualifier → WGSL BindingType table (open-question-3) — COMPLETE

Enumerated from upstream `ImageType` (`gpu_shader_create_info.hh:517-555`, read-only)
against WGSL. Implemented in `infer_sample_type` / `infer_sampler_type` /
`infer_view_dimension`; the divergent arms (Float/Depth+Comparison/Uint) are
LIVE-validated by the `types` case against a real pipeline.

| Blender `ImageType` family | GLSL | Tint WGSL texture | BGL `TextureSampleType` | BGL `SamplerBindingType` |
|---|---|---|---|---|
| `Float{n}` (filtering) | `sampler{n}` | `texture_{n}<f32>` | `Float` | `Filtering` |
| `Float{n}` (no LINEAR) | `sampler{n}` | `texture_{n}<f32>` | `UnfilterableFloat` | `NonFiltering` |
| `Uint{n}` | `usampler{n}` | `texture_{n}<u32>` | `Uint` | `NonFiltering`¹ |
| `Int{n}` | `isampler{n}` | `texture_{n}<i32>` | `Sint` | `NonFiltering`¹ |
| `Depth{n}` | `sampler{n}Depth` | `texture_depth_{n}` | `Depth` | `NonFiltering` |
| `Shadow{n}` | `sampler{n}Shadow` | `texture_depth_{n}` | `Depth` | `Comparison` |
| `AtomicUint/Int{n}` | `usampler{n}Atomic` | storage `texture_storage` r32uint/r32sint | (storage image, not sampler) | — |

Dimensionality (`TexDim → TextureViewDimension`): 1D→e1D, 2D→e2D, 2DArray→e2DArray,
3D→e3D, Cube→Cube, CubeArray→CubeArray. `Buffer` textures and `1DArray` have no
direct WGSL sampled-texture form → route to `textureLoad`-only handling (flagged).

¹ Integer textures are unfilterable; in WGSL only `textureLoad` (no sampler) is
valid on them. MEASURED (the `types` case's `usampler2D` used via `texelFetch`):
Tint STILL emits the split sampler half (`id_tex_sampler : sampler @binding(259)`) —
it does NOT drop it even though the sampler is unused. So the BGL MUST declare that
sampler entry, and it MUST be `NonFiltering` (a `Filtering` sampler on a uint-texel
path is rejected). The pipeline validated with `NonFiltering`. This also confirms the
spec's "map EVERY combined sampler" rule holds for integer/`texelFetch` samplers.

The `filtering` bit comes from Blender's `GPUSamplerState`
(`GPU_SAMPLER_FILTERING_LINEAR`, `GPU_texture.hh:294`); it is NOT in SPIR-V/Tint, so
it is a BGL-only choice the interface map makes. **Completeness:** every `ImageType`
texel family + every dimension is mapped; the only unmapped-on-purpose forms are
`Buffer`/`1DArray` sampled textures (no WGSL equivalent — need textureLoad or a
storage path) and multisampled samplers (Blender declares MS textures via a separate
path; `.texture.multisampled` is wired but defaulted false here).

## 5. Sampler-array verdict (open-question-1) — BROKEN AT TINT (not a keying problem)

`sampler2D tex[4]` at binding 0, run three ways through the split
(`tests/wgpu_shader_compiler_test.cc::run_sampler_array_probe`):

| variant | sampler_mappings | result |
|---|---|---|
| per-element keys {0,0..3}→{0,256..259} | 4 keys | `tint ReadIR` FAILS |
| single base key {0,0}→{0,256} | 1 key | `tint ReadIR` FAILS |
| empty (default Tint) | 0 keys | `tint ReadIR` FAILS |

All three fail IDENTICALLY and EARLY, with:

> `tint ReadIR: arrays of handle types are not supported`

**VERDICT: the keying question is MOOT.** Tint's IR SPIR-V reader *parser* rejects
an array-of-sampled-image variable before any split / `sampler_mappings` logic runs:
`src/tint/lang/spirv/reader/parser/parser.cc:200`
(`return Failure("arrays of handle types are not supported")`) — the same parser
that hardcodes `SPV_ENV_VULKAN_1_1` at :95 (T1). So `sampler2D tex[N]` cannot be
translated at this Dawn/Tint pin AT ALL. There is no binding_array output, no
unrolled output — nothing reaches WGSL.

**T7 consequence (actionable).** Blender DOES use sampler arrays (material atlases,
batching). Because the block is at the SPIR-V-reader parser, the only viable T7
paths are:
1. **Unroll at GLSL codegen (recommended).** Emit N *scalar* combined samplers
   `tex_0 … tex_{N-1}` at consecutive dense bindings instead of `tex[N]`, and index
   them via a generated `switch`/selector in the shader body. Then each is a scalar
   handle Tint accepts, and the interface map's per-element expansion (already
   implemented — it produces exactly bindings `[N, N+size)` + samplers
   `[BASE+N, BASE+N+size)` with one `sampler_mappings` key per element) is the
   correct layout with no changes. This is the standard WGSL-target workaround.
2. **Upstream Tint fix** for arrays of handle types in the SPIR-V reader (file a
   Tint issue; track against the M4 emdawnwebgpu pin — the browser Dawn/Tint may
   differ). Not available at `36cf1fae`.
3. Bindless (`binding_array`) is NOT reachable here — it would require the reader to
   accept the array in the first place.

The interface-map code is already array-ready (per-element keys + BGL entries),
so when option 1's unrolled GLSL is fed in, no map change is needed; the block is
purely the front of the chain (SPIR-V reader), not the mapping.

## 6. What T7 integration still needs

The two HARD components (the compiler chain + the interface/binding map) are DONE
and proven. Remaining for T7 (`source/blender/gpu/webgpu/`) is wiring, not design:

1. **Feed real create-info reflection.** Replace the hand-built `ResourceDesc`
   lists with Blender's `ShaderCreateInfo` resource walk (the dense-N assignment
   already lives in the reused `shader_interface`; §spec-5.5). The `ResourceDesc`
   struct mirrors what create-info provides 1:1 — the adapter is a short loop.
2. **GLSL comes from the create-info codegen**, not literals: reuse the Vulkan
   backend's `resources_declare` / interface builders through `run_preprocessor()`
   (arch §3a). The compiler API already takes GLSL strings per stage.
3. **shaderc env = vulkan_1_1** (SPIR-V 1.3), not Blender's 1.2 (§2). Enumerate any
   shader needing a >1.3 capability before flipping (M3 compute corpus expected clean).
4. **Link both shaderc + Tint** with a single SPIRV-Tools (§2 coexistence).
5. **BGL → wgpu_bind_group + wgpu_pipeline**: the module returns
   `wgpu::BindGroupLayoutEntry[]`; T7's `wgpu_bind_group.cc` caches the layout and
   `wgpu_pipeline.cc` composes the pipeline layout (this harness does both inline as
   the proof).
6. **Multisampled / storage-image / Buffer-texture** sampler qualifiers (§4 notes)
   and array samplers (§5 verdict) per their findings.
7. **WGSL disk cache** (arch §3b, OPFS at M4) — orthogonal; not in this module.

## 7. Verdict

The two HARD T7 components are BUILT and PROVEN standalone, outside the Blender
tree, on a live native Dawn/Metal device: `wgpu_shader_compiler` (in-process
shaderc GLSL→SPIR-V 1.3 → Tint → WGSL) and `wgpu_shader_interface_map` (the
normative reserved-range binding map + BGL + sampler/texture-type inference).
4/4 gated cases create real pipelines; the negative control is correctly rejected;
the sampler-qualifier matrix (Float/Comparison/Uint) validates live. T7 is now an
INTEGRATION task (feed real create-info reflection + codegen GLSL; wire the returned
BGL into `wgpu_bind_group`/`wgpu_pipeline`), not a development task. Two concrete
carry-forward hazards are characterised with fixes: (a) shaderc↔Tint SPIRV-Tools
coexistence (use the shaderc shared lib), and (b) sampler arrays are unreadable by
Tint at this pin (parser.cc:200) → unroll to scalar samplers at GLSL codegen.
Confidence HIGH.
