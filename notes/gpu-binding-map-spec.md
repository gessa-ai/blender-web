<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M3.T2 — WGSL binding-map SPEC (normative for `wgpu_shader_interface`, T7)

Pin: Blender 5.2 `fbe6228777e7`; Dawn `chromium/7989 @ 36cf1fae`. This is the
NORMATIVE mapping the WebGPU backend's `wgpu_shader_interface` must implement so
that Tint's WGSL output binds identically to the bind-group layout the backend
builds. Every claim is validated by the committed probe
`sandbox/dawn-probe/probe_bindmap.cc` (target `dawn_bindmap_probe`) on native
Dawn/Metal ("Apple M4 Pro"), exit 0. Companion: `notes/gpu-dawn-probe.md` (T1),
`notes/gpu-webgpu-architecture.md` §3 (R1).

---

## 0. TL;DR

- Blender emits a **single descriptor set (set 0)** with **dense 0-based
  sequential bindings**; combined `sampler2D`s share one binding with no split
  in the source (recon citations in §1).
- WGSL/WebGPU has no combined samplers. Tint's SPIR-V reader **always** splits
  them (SPIRV-Tools `SplitCombinedImageSamplerPass`), copying the combined
  binding onto BOTH the texture and sampler halves.
- **Default Tint is unusable for Blender.** With empty `sampler_mappings`, Tint
  runs `ResolveBindingConflictsPass`, which renumbers *every* resource after the
  first sampler — **per stage, independently** — so shared bindings diverge
  across stages and the numbers no longer match Blender's layout (§3, proven).
- **The fix (normative):** hand Tint an explicit `spirv::reader::Options::
  sampler_mappings` that sends each combined sampler's **sampler half** to a
  reserved binding, leaving the texture half and all other resources on their
  Blender bindings. This is deterministic and composes across stages (§4, §5).

## 1. Blender's Vulkan binding scheme (VERIFIED, cited)

Source of truth (read at the pin):
- Single set 0 for everything; pipeline layout has exactly one set layout
  (`vulkan/vk_shader.cc:680-686`); GLSL emits no `set=` qualifier.
- The emitted `layout(binding=N)` is a **dense 0-based sequential index**, NOT
  the create-info slot. The counter is assigned in
  `vk_shader_interface.cc:205,224,238,280` over
  [subpass inputs] → [pass, then batch, then geometry resources, in declaration
  order] → [push-constant fallback UBO last] (`:283-285`), stored at `:379` and
  emitted at `vk_shader.cc:362,404`. Runtime layout matches
  (`vk_descriptor_set_layouts.cc:69-72`).
- Combined samplers: `layout(binding=N) uniform sampler2D name;` — texture and
  sampler share the single binding N (`vk_shader.cc:362,375-378,253`).
- Push-constant fallback UBO: `layout(binding=<last>, std140) uniform constants`
  when push data exceeds `maxPushConstantsSize` (`vk_shader.cc:844-846`,
  `vk_push_constants.cc:88-89`); real `layout(push_constant)` otherwise (no
  descriptor binding, `vk_shader.cc:841-842`).
- `BIND_SPACE_IMAGE_OFFSET = 512` (`vk_state_manager.hh:33`) is an *internal
  GL-style lookup namespace* only — it is NOT present in the emitted shader.

Consequence: `binding == create-info slot` does NOT hold. The WebGPU backend
reuses Blender's create-info codegen + `shader_interface`, so the dense N values
come for free; this spec governs only what Tint does to them and how the
bind-group layout is built.

## 2. What Tint does to the SPIR-V (VERIFIED, cited)

`src/tint/lang/spirv/reader/parser/parser.cc`:
- `:124-128` `SplitCombinedImageSamplerPass` — **always** runs; per its header
  (`.../split_combined_image_sampler_pass.h:34`) it *copies the descriptor set
  and binding number* onto both the split image and split sampler. So right
  after the split, texture@ (0,N) and sampler@ (0,N) — same binding.
- `:130-136` `ResolveBindingConflictsPass` — runs **only if `sampler_mappings`
  is empty**. This is the auto-renumberer that causes the divergence in §3.
- `:4617-4624` when emitting a sampler var, Tint looks up
  `sampler_mappings[BindingPoint{group, binding}]` where `{group,binding}` is
  the sampler's binding **after the split = the original combined (0,N)**, and
  remaps it to the mapped value. Non-samplers are never remapped here.

**Therefore the `sampler_mappings` KEY is the combined sampler's ORIGINAL
(set, binding) = `{0, N}`** (Blender's binding), and the VALUE is the chosen WGSL
sampler location. Confirmed live in §4.

## 3. Default Tint FAILS — measured (Mode A)

Blender-shaped input (`shaders/bindmap.{vert,frag}`, dense set 0):
`0 globals(UBO, V+F) · 1 color_tex(sampler2D, F) · 2 normal_tex(sampler2D, F) ·
3 material(UBO, F) · 4 light_data(SSBO, F) · 5 constants(push-const UBO, V+F)`.

Default Tint (empty `sampler_mappings`) output — VERBATIM from the probe:

| resource | Blender | Mode-A vertex | Mode-A fragment |
|---|---:|---:|---:|
| globals (UBO) | 0 | 0 | 0 |
| color_tex texture | 1 | — | 1 |
| color_tex sampler | (split) | — | 2 |
| normal_tex texture | 2 | — | 3 |
| normal_tex sampler | (split) | — | 4 |
| material (UBO) | 3 | — | **5** |
| light_data (SSBO) | 4 | — | **6** |
| constants (UBO, shared) | 5 | **5** | **7** |

Two fatal problems:
1. **Cross-stage divergence.** `constants` is a *shared* binding, but Mode A
   leaves it at 5 in the vertex (no samplers → no conflict pass) and bumps it to
   7 in the fragment. One bind-group layout cannot satisfy both.
2. **Layout-type mismatch.** Mode A puts `normal_tex sampler` at binding 4, where
   Blender's layout has the `light_data` SSBO. Feeding the Mode-A modules to
   Blender's intended layout is **rejected** by Dawn (probe C1, verbatim):
   > Binding type in the shader (sampler) doesn't match the type in the layout
   > (buffer) … for @group(0) @binding(4) … validating fragment stage.

So default Tint is a silent-mis-bind / hard-reject generator. It must not be used.

## 4. The SPEC — reserved-range sampler mapping (Mode B, PROVEN)

### 4.1 Mapping, per resource class → (`@group`, `@binding`)

For a shader whose Blender set-0 dense bindings are `N`:

| create-info resource class | WGSL `@group` | WGSL `@binding` |
|---|:--:|---|
| UNIFORM_BUFFER (incl. push-const fallback UBO) | 0 | `N` (unchanged) |
| STORAGE_BUFFER (SSBO) | 0 | `N` (unchanged) |
| IMAGE (storage image, `imageLoad/Store`) | 0 | `N` (unchanged) |
| SAMPLER — **texture half** of the split | 0 | `N` (unchanged) |
| SAMPLER — **sampler half** of the split | 0 | `SAMPLER_BASE + N` |

`SAMPLER_BASE` is a reserved constant chosen so that
`max_resource_binding < SAMPLER_BASE` **and**
`SAMPLER_BASE + max_sampler_binding < maxBindingsPerBindGroup`.
WebGPU's `maxBindingsPerBindGroup = 1000` (Dawn `native/Limits.cpp:133`, same in
emdawnwebgpu), and Blender's set-0 resource count is bounded well under 128 by
the per-stage limits (`maxUniformBuffersPerShaderStage=12`,
`maxStorageBuffersPerShaderStage=8`, `maxSampledTexturesPerShaderStage=16`,
`maxSamplersPerShaderStage=16`). **The probe uses `SAMPLER_BASE = 256`.** T7 may
instead compute it dynamically as `round_up_pow2(max_resource_binding + 1)` and
MUST assert `SAMPLER_BASE + max_N < maxBindingsPerBindGroup`.

`@group` is always 0 — this mirrors Blender's single descriptor set and keeps the
backend to ONE bind group (simplest bind/rebuild path). Alternative if binding
pressure ever appears: place all split samplers in a dedicated `@group(1)`;
costs a second bind-group layout in the pipeline layout. Not needed at the pin.

### 4.2 Exact Tint options usage (normative)

```cpp
tint::spirv::reader::Options opts;
// Enumerate EVERY combined sampler in the shader interface; N is its Blender
// (dense, set-0) binding. Map the sampler half to the reserved range.
for (const CombinedSampler& s : interface.combined_samplers()) {
    opts.sampler_mappings[tint::BindingPoint{0u, s.binding}] =
        tint::BindingPoint{0u, SAMPLER_BASE + s.binding};
}
auto ir   = tint::spirv::reader::ReadIR(spirv_words, opts);      // Result<core::ir::Module>
auto prog = tint::wgsl::writer::ProgramFromIR(ir.Get(), {});     // Result<Program>
auto out  = tint::wgsl::writer::Generate(prog.Move(), {});       // Result<Output>; .wgsl
```

**HARD REQUIREMENT:** because a non-empty `sampler_mappings` DISABLES
`ResolveBindingConflictsPass` (parser.cc:130), T7 must map **every** combined
sampler. An unmapped one leaves its sampler colliding with its own texture at
binding `N` with no auto-fix → an invalid WGSL module. "Map all or none" — and
"none" is Mode A, which is rejected.

### 4.3 Measured Mode-B output (VERBATIM, the spec realised)

`sampler_mappings = { {0,1}->{0,257}, {0,2}->{0,258} }`:

| resource | @group/@binding (vertex) | @group/@binding (fragment) |
|---|---|---|
| globals (UBO) | (0,0) | (0,0) |
| color_tex texture | — | (0,1) |
| color_tex sampler | — | (0,257) |
| normal_tex texture | — | (0,2) |
| normal_tex sampler | — | (0,258) |
| material (UBO) | — | (0,3) |
| light_data (SSBO) | — | (0,4) |
| constants (UBO, shared) | (0,5) | (0,5) |

Every non-sampler keeps its Blender binding; shared bindings (0 and 5) AGREE
across stages; samplers sit in the disjoint reserved range.

### 4.4 Collision-freedom argument

Group 0 only. Let R = number of set-0 resources (dense bindings occupy
`[0, R) ⊂ [0, 128)`). (a) Texture halves and all non-samplers keep their unique
dense N ∈ [0,R) — unique because Blender assigns dense unique bindings. (b) Each
sampler half maps to `SAMPLER_BASE + N` with `SAMPLER_BASE ≥ 256 > R`, so the
sampler set is disjoint from the resource set; and N is unique per combined
sampler, so the mapped values are pairwise distinct. Hence all `@binding` in
group 0 are unique, and all `< maxBindingsPerBindGroup`. Cross-stage: the map is
a pure function of `(set, binding)` with no stage input, and Blender gives a
shared resource the SAME N in every stage, so its WGSL binding is identical
across stages ⇒ one bind-group layout is compatible with all stages. ∎

## 5. Bind-group-layout construction (Mode C, PASS)

`wgpu_shader_interface` builds ONE `BindGroupLayout` (group 0) with, per resource:

| resource class | `BindGroupLayoutEntry` | binding | visibility |
|---|---|---|---|
| UBO | `.buffer.type = Uniform` | N | union of using stages |
| SSBO (read-only) | `.buffer.type = ReadOnlyStorage` | N | using stages |
| SSBO (read-write) | `.buffer.type = Storage` | N | using stages |
| combined sampler — texture | `.texture{sampleType, viewDimension}` | N | using stages |
| combined sampler — sampler | `.sampler.type` (Filtering/NonFiltering/Comparison) | `SAMPLER_BASE + N` | using stages |
| storage image | `.storageTexture{access, format, viewDimension}` | N | using stages |

`visibility` is the OR of the `ShaderStage`s that reference the binding (Blender's
`ShaderCreateInfo` frequency/stage data gives this; shared bindings get
`Vertex|Fragment`). The probe builds exactly this layout and:
- `CreateBindGroupLayout` — OK
- `CreatePipelineLayout` (1 BGL) — OK
- `CreateRenderPipeline` with the Mode-B vertex+fragment modules — **OK** (the
  layouts compose across stages).
- Same pipeline with the Mode-A modules — **correctly REJECTED** (§3).

`sampleType`/`sampler.type` pairing (Float↔Filtering here) must be derived from
the create-info's image format/qualifier so filterable/comparison/multisampled
cases match; that is per-resource detail for T7, not a binding-number concern.

## 6. Open questions for T7

1. **Arrays of combined samplers** (`sampler2D tex[N]`). Blender uses sampler
   arrays (e.g. batching / material atlases). The SPIRV-Tools split pass claims
   to handle "arrays of them", but the `sampler_mappings` keying for an array
   element (one key per element? one for the base?) is UNVERIFIED. Probe this
   before T7 implements array samplers.
2. **`SAMPLER_BASE` policy**: fixed 256 vs dynamic `round_up_pow2(max_N+1)`.
   Fixed is simpler and provably safe at the pin; dynamic is tighter if a shader
   ever approaches the reserved base. Pick one in T7 and assert the bound.
3. **Sampler type inference**: mapping create-info sampler/image qualifiers to
   WGSL `SamplerBindingType` (Filtering vs NonFiltering vs Comparison) and
   `TextureSampleType` (Float vs UnfilterableFloat vs Sint/Uint vs Depth). Tint
   picks a WGSL texel type from SPIR-V; T7's BGL must agree. Enumerate Blender's
   sampler qualifiers (`GPUSamplerState`, depth/shadow samplers) against WGSL.
4. **Storage images** stay at N here, but WGSL storage-texture access/format
   limits (R5) may force format substitutions — separate from binding numbers.
5. **Push-constant fallback UBO** binding N is *dynamic* (assigned last by
   `shader_interface`). Since the backend reuses that same interface, the WGSL N
   and the BGL entry come from one source — but T7 must ensure the create-info
   codegen path is the SAME one that computed N (no divergence between the GLSL
   the backend feeds shaderc and the interface it reflects).

## 7. Verdict

The R1 hazard is fully specified and mechanically validated: default Tint is
rejected; the reserved-range `sampler_mappings` spec produces a deterministic,
cross-stage-consistent, collision-free binding map that composes into a real
render pipeline on native Dawn. T7 can implement §4-§5 directly. Confidence HIGH;
the only genuinely open item is array-of-sampler keying (§6.1).
