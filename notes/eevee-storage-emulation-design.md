<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# EEVEE-Next storage-texture blocker: engineering attack (design, lane r48)

Design-only lane. Per decision D-10 the `vertex-stage-rw-storage` deferral (which
currently fails ALL 30 EEVEE M6 render scenes) gets a real engineering attempt
before it settles. This note is the mechanism map, the recommended fix in
priority order, the native-Dawn probe evidence, the effort estimate, and the
verification plan, so the driver can dispatch an implementation lane. No shared
tree was patched. Pin: Blender 5.2 `fbe6228777e7`.

## TL;DR

The deferral as recorded (`var<storage, read_write>` in the vertex stage) is
**not** the real blocker for the 30 EEVEE scenes. The real blocker is a
**four-class storage-texture BindGroupLayout failure**, and the largest classes
are backend-fixable with a small, faithful change - the exact analog of a strip
that already ships and works for storage buffers, plus two device-creation knobs.
A native Dawn/Metal probe (`sandbox/eevee-storage-design/`, Apple M4 Pro) proves
the fix: with the change, 8/9 EEVEE storage formats that fail today are accepted,
and the one remainder is a single named residual. Image **atomics** (virtual
shadow map) are a genuinely separate, harder blocker that stays scoped to the
shadow scenes.

## 1. Ground truth: declared-vs-used visibility (design question 1)

**Answer: the vertex stage never uses the storage resource. Visibility is
over-declared shader-wide by Blender's create-info, and only the fragment stage
touches it.** Evidence:

- `eevee_surf_deferred.bsl.hh`: the g-buffer images `gbuf_closure_img`
  (`UNORM_10_10_10_2`), `gbuf_normal_img` (`UNORM_16_16`), `gbuf_header_img`
  (`UINT_32`) are declared `[[image(..., write, ...)]]` and are written ONLY via
  `imageStoreFast` inside the `[[fragment]] surf_deferred(...)` entry point
  (lines 51-54, 60/67/74, 89). The vertex stage is the geometry transform
  (`eevee_geom_*`); it does not reference the images.
- The web backend applies one shader-wide stage mask to every resource:
  `wgpu_shader.cc:2133-2135` sets `stages = STAGE_VERTEX | STAGE_FRAGMENT` for a
  graphics shader and hands it to every resource in `resource_to_desc`. So each
  writable storage image carries Vertex visibility even though no vertex code
  writes it. This is the same over-declaration the storage-buffer strip already
  documents (`wgpu_shader_interface_map.cc:217-231`).

**The verbatim Dawn rejection** (captured in real render sweeps,
`sandbox/gpu-r44/resolve_default.dump.txt:2919`, `sandbox/gpu-r44-r3/shadow_info.log`):

```
Storage texture binding with StorageTextureAccess::WriteOnly is used with a
visibility (ShaderStage::(Vertex|Fragment)) that contains ShaderStage::Vertex.
 - While validating entries[N] / [BindGroupLayoutDescriptor]
 - While calling [Device].CreateBindGroupLayout(...).
```

Dawn objects **specifically to Vertex being in the set**. Fragment-only is
accepted (proved below). So the fix for this class is **visibility narrowing**:
strip Vertex from writable storage-image entries, identical in spirit to the
storage-buffer strip that already ships.

## 2. The real blocker is four classes, not one (corrects the m6 characterization)

`notes/m6-gpu-suite-real-scores.md` lumped all 30 EEVEE failures under a single
"Storage texture WriteOnly used with Vertex/Fragment visibility" line. The real
Dawn output on a live render shows **four distinct BindGroupLayout failure
classes** (all at `CreateBindGroupLayout`, which invalidates the pipeline layout,
so the pipeline never builds and the render never runs):

| # | Class | Verbatim Dawn error | Fix |
|---|-------|---------------------|-----|
| C1 | **Writable storage texture visible to Vertex** | `...WriteOnly/ReadWrite is used with a visibility (Vertex\|Fragment) that contains ShaderStage::Vertex` | Visibility strip (backend, ~mirrors the SSBO strip) |
| C2 | **Format not storage-writable in core WebGPU** | `Texture format TextureFormat::RGB10A2Unorm / RG16Unorm / RG11B10Ufloat / RG16Float / R16Float / R16Sint / ... does not support storage texture access WriteOnly` (and `RGBA16Float / RGBA32Float ... ReadWrite`) | Request `TextureFormatsTier1` (+`Tier2` for read-write) at device creation |
| C3 | **>4 storage textures in one stage** | `The number of storage textures (5) in the Compute stage exceeds the maximum per-stage limit (4). This adapter supports a higher ... of 8, which can be specified in requiredLimits` | Set `requiredLimits.maxStorageTexturesPerShaderStage` at device creation |
| C4 | **>8 storage buffers in the Vertex stage** | `The number of storage buffers (11) in the Vertex stage exceeds the maximum per-stage limit (8)` | The C1-class strip removes the fragment-only RW SSBOs from Vertex, cutting the count; plus `requiredLimits.maxStorageBuffersPerShaderStage` |

Separately, a **fifth**, harder blocker that is NOT a BindGroupLayout error:

| C5 | **Image atomics** (`imageAtomicMin/Add`) | Tint compile: `unhandled SPIR-V OpImageTexelPointer` -> null module -> segfault (the registered `storage-texture-atomics` deferral) | SSBO-atomic emulation over a linear layout (shader restructure) |

C1-C4 are the dominant cause of the 30 render failures. C5 is confined to the
shadow / volume / surfel-GI passes (7 EEVEE shaders use image atomics:
`eevee_surf_shadow`, `eevee_shadow`, `eevee_surf_occupancy`,
`eevee_occupancy_convert`, `eevee_surf_volume`, `eevee_surfel_cluster`,
`eevee_surfel_list`). Of these, only the virtual-shadow-map path
(`eevee_surf_shadow.bsl.hh:46-120`, `imageAtomicMin/Add` on `UINT_32`
`uimage2DArrayAtomic` in the FRAGMENT stage) is on the M6 launch-tier critical
path (the shadow scenes); volume and surfel-GI are off the M6 surface-material
critical path.

## 3. Where the fix already exists and where it is missing

The storage-**buffer** version of C1 was already found and fixed. It lives in two
places and both strip Vertex from a read-write SSBO:

- `wgpu_shader_interface_map.cc:213-237` (`StorageBuffer` case): if
  `btype == Storage` (writable), `svis = vis & (Fragment | Compute)`.
- `wgpu_shader.cc:2354-2362` (`build_explicit_layout`, re-applied after the
  WGSL-visibility scan): `if (e.buffer.type == Storage) e.visibility &=
  (Fragment | Compute);`

The storage-**image** version is **absent in both places**:

- `wgpu_shader_interface_map.cc:239-241` (`StorageImage` case) passes the full
  `vis` (Vertex|Fragment) straight into `make_storage_image_entry` with no
  writable-access strip.
- `wgpu_shader.cc:2360` only tests `e.buffer.type == Storage`; a storage-image
  entry (`e.storageTexture.access`) is never stripped.

So C1 is a one-case omission: the writable-storage-image analog of an already
proven, already shipping strip.

## 4. Native Dawn probe evidence (design question 4)

`sandbox/eevee-storage-design/` (probe `probe_storage_bgl.cc`, build `build.sh`,
reusing the pinned Dawn checkout `build-dawn/dawn` via the `sandbox/dawn-probe`
precedent). Pure Dawn validation - no Blender, no Tint, no shaders. Two devices
(a CONTROL matching today's GHOST feature set, and a PROPOSED device with the
three device knobs), each run a `CreateBindGroupLayout` matrix over the EEVEE
storage formats x access x visibility. Full logs:
`sandbox/eevee-storage-design/probe-result.log`.

Adapter: **Apple M4 Pro, Metal**. `TextureFormatsTier1: YES`,
`TextureFormatsTier2: YES`, `Unorm16TextureFormats: YES`,
`maxStorageTexturesPerShaderStage: 8`, `maxStorageBuffersPerShaderStage: 10`.

| Test | CONTROL (today) | PROPOSED (+Tier1+Tier2+limits) |
|------|-----------------|--------------------------------|
| `UNORM_10_10_10_2` write, Fragment-only (gbuf_closure) | FAIL | **OK** |
| `UNORM_16_16` write, Fragment-only (gbuf_normal) | FAIL | **OK** |
| `UINT_32` write, Fragment-only (gbuf_header) | OK | OK |
| `SFLOAT_16` write, Fragment-only | FAIL | **OK** |
| `SFLOAT_16_16` write, Fragment-only | FAIL | **OK** |
| `UFLOAT_11_11_10` write, Fragment-only | FAIL | **OK** |
| any writable, **Vertex\|Fragment** | FAIL (x6) | FAIL (x6) - strip still required |
| `SFLOAT_32` read_write, Fragment-only (film depth) | OK | OK |
| `SFLOAT_16_16_16_16` read_write, Fragment-only (film combined) | FAIL | **OK** (Tier2) |
| `UNORM_16_16` read_write, Fragment-only (thickness_amend) | FAIL | **FAIL (residual)** |
| 5 / 8 storage textures in one stage | FAIL / FAIL | **OK / OK** |

**Summary: CONTROL accepts 2/9 Fragment-only; PROPOSED accepts 8/9 and still
rejects all 6 Vertex-visible writable entries** (confirming the strip is
necessary, not redundant with the features). The single residual is
`RG16Unorm` **read-write** (`deferred_thickness_amend`), which no tier grants
(Tier2's read-write set is r8/r16/rgba8/rgba16/rgba32 only; see Dawn
`src/dawn/native/Format.cpp:343-388`).

This cross-checks the Dawn format table directly: `TextureFormatsTier1` grants
`StorageWOnly` to exactly the EEVEE write formats that fail (RGB10A2Unorm,
RG16Unorm, R16Float, RG16Float, RG16Sint, R8Sint, RG11B10Ufloat, RGBA16Unorm),
and `TextureFormatsTier2` grants `StorageRW` to the film/deferred-combine
read-write formats (RGBA16Float, R32*, R16Float, RGBA8/16/32).

## 5. Recommended strategy, in priority order

### Phase A - device + backend triad (small, backend-only, faithful). Highest yield.

1. **C1 visibility strip (mirror the SSBO strip for writable storage images).**
   - `wgpu_shader_interface_map.cc` `StorageImage` case: if `image_access` is
     `WriteOnly` or `ReadWrite`, `svis = vis & (Fragment | Compute)` before
     `make_storage_image_entry`.
   - `wgpu_shader.cc:2360` `build_explicit_layout`: extend the strip to
     `e.storageTexture.access == WriteOnly || == ReadWrite`.
   - Faithful because the vertex stage provably never writes these images
     (section 1); a genuinely vertex-written storage image is inexpressible on
     WebGPU regardless and would then get a precise per-shader error, not this
     blanket layout collapse (same reasoning as the SSBO strip's comment).

2. **C2 format support: request `TextureFormatsTier1` and `TextureFormatsTier2`
   at device creation** (adapter-guarded, like the existing feature opt-ins).
   - `GHOST_ContextWGPU.cc:83-107` already opts into `Unorm16TextureFormats` /
     `RG11B10UfloatRenderable` / `ClipDistances` / `DualSourceBlending` when the
     adapter exposes them. Add `TextureFormatsTier1` and `TextureFormatsTier2`
     to that same adapter-guarded list.
   - The M4/browser device is created on the emdawnwebgpu path; the same
     adapter-guarded opt-in must be applied there (see Risk R1).

3. **C3/C4 limits: set `requiredLimits` at `RequestDevice`** to the adapter's
   supported ceiling for `maxStorageTexturesPerShaderStage` and
   `maxStorageBuffersPerShaderStage` (probe shows the M4 ceiling is 8 / 10 vs the
   default 4 / 8). `GHOST_ContextWGPU.cc` currently passes no `requiredLimits`.

   Phase A is ~3 files, on the order of 20-40 lines, all backend / GHOST, no
   shader-source edits. It removes classes C1, C2, C3, C4.

### Phase A' - the one residual read-write format (tiny, per-case).

`deferred_thickness_amend` binds `gbuf_normal_img` as `read_write UNORM_16_16`
(`RG16Unorm`), which is storage-writable but not storage-**read-write** on this
pin. Options, cheapest first: (a) if the pass only ever writes an amended normal,
demote the create-info qualifier to `write` (then Tier1 covers it - verify the
GLSL does not read-modify-write the image); (b) substitute an `R32Uint` storage
image with manual 16:16 pack/unpack (the atomics-emulation addressing helper can
be reused); (c) split into read pass + write pass. Same family may recur for any
read-write `RG11B10Ufloat` raytrace-denoise image - enumerate on the render
evidence, not speculatively.

### Phase B - image-atomics emulation for the virtual shadow map (harder, separable).

C5 blocks the shadow scenes (`eevee_surf_shadow` uses `imageAtomicMin/Add` on the
shadow atlas). WGSL has no storage-texture atomics; the known faithful workaround
(recorded in the `storage-texture-atomics` deferral) is to re-express the image
atomic as a **storage-buffer atomic over an equivalent linear layout**: bind the
shadow atlas backing as an SSBO, compute the linear texel address from
`(page, layer, x, y)`, and use `atomicMin`/`atomicAdd` on the SSBO. This is a
`GPU_WEBGPU`-guarded shader restructure (the approved 0089-class exception, same
class the driver already blessed for the fallthrough and uniformity families in
`fix_plan.md` M3.F12/F13), plus a backend path that binds the atlas texture's
storage as a buffer. Correctness-sensitive (the `atomicMin` is the shadow depth
test), so it needs its own lane with the shadow scenes as the acceptance set.
Blender's Metal backend does NOT need this (Metal has native texture atomics), so
there is no in-tree precedent to copy - it is net-new for WebGPU.

## 6. Expected scene yield per step (design questions 1 and 3)

The 30 M6 EEVEE scenes: 15 `principled_bsdf`, 7 `raycast`, 4 `shadow`,
2 `transparency`, 2 `colorspace`. Critical-path analysis (the opaque deferred
path - g-buffer surface + deferred eval/combine + film - is shared by all 30 and
uses NO atomics; the m6 evidence that principled scenes fail with the BGL error,
not a compile/atomic crash, confirms atomics are off their critical path):

- **Phase A alone** removes C1-C4 from the shared opaque path -> unblocks pipeline
  creation for the **26 non-shadow scenes** (principled + raycast + transparency +
  colorspace). Of those, the subsurface/refraction principled scenes
  (`subsurface`, `thin_subsurface`, `thin_glass`, `transmission`,
  `thinfilm_transmission`) and possibly the raytrace-denoise path additionally
  need **Phase A'** for the residual read-write format. Realistic Phase A + A'
  yield: **26/30 render (pipelines build; pixels then judged against goldens
  separately)**.
- **Phase B** adds the **4 shadow scenes** -> path to **30/30**.

Honest caveat (the implementation lane's FIRST measurement): whether the 26
non-shadow test scenes rasterize the atomic shadow surface at all depends on
their light setup (world/HDRI-lit scenes do not; a shadow-casting lamp would pull
the atomic path onto their critical path too). The m6 error counts support the
optimistic reading (principled = 30 BGL errors, shadow = 38: the +8 is the
shadow-specific pipelines), but this is the one thing to confirm empirically
before promising 26 from Phase A alone. Acceptance is defined so the number is
measured, not assumed (section 8).

## 7. Effort + risk (design question 5)

**Phase A: SMALL.** 3 files (`GHOST_ContextWGPU.cc`,
`wgpu_shader_interface_map.cc`, `wgpu_shader.cc`), ~20-40 lines, backend/GHOST
only, no shader edits. Census risk **LOW**: the C1 strip mirrors the proven SSBO
strip and only removes Vertex visibility from resources the vertex stage does not
use; features and limits are additive. The compute/storage tripwires
(`compute_direct/indirect`, `storage_buffer`, `shader_compute_*`,
`specialization_constants_compute`) must stay green - re-run `harness/run.sh
--scope m3` (RUN-only; do not rebuild `build-native-gpu` while another lane is
mid-census). The `maxStorageTexturesPerShaderStage` cap that `GCaps.max_images`
reads (`wgpu_context.cc:191`) rises with the requiredLimits, which is correct.

**Phase A': TINY**, 1 create-info qualifier or a small pack/unpack, per residual.

**Phase B: MODERATE-HIGH.** Shader restructure (`GPU_WEBGPU`-guarded) of the
shadow atlas atomics + a backend atlas-as-SSBO bind path; correctness-sensitive;
own lane.

### Risks

- **R1 (the load-bearing risk): the SHIPPING browser adapter must also expose
  `TextureFormatsTier1`/`Tier2`.** The probe proves native Dawn/Metal on this Mac
  exposes them, and the pinned emdawnwebgpu header declares the feature enums
  (`webgpu.h:429-430`), but Tier1/Tier2 are recent WebGPU features and the user's
  Chrome may gate them behind a flag or not expose them on every OS/driver. The
  implementation lane MUST log `adapter.features` in the actual M4 browser build
  and, if a tier is absent, fall back for C2 to format substitution (pack the
  incompatible-format g-buffer images into `R32Uint` storage with manual
  bit-packing, or route them through MRT color attachments the way
  `surf_deferred` already routes the first closure). This fallback is larger than
  the feature opt-in, so verify the browser capability first.
- **R2: read-write residuals beyond the one found.** Enumerate every `read_write`
  storage image whose format is outside Tier2's read-write set (RG16Unorm,
  RG11B10Ufloat, RGB10A2*) on the real render, and handle per-case (Phase A').
- **R3: Phase B correctness.** SSBO-atomic addressing of a layered/paged atlas
  must match the texture's memory layout exactly, or shadows corrupt silently.
  Gate on the shadow-scene goldens, not just "no GPU error".
- **R4: per-stage image count on the emitted WGSL.** With Vertex stripped, verify
  no single stage still exceeds the (now raised) limit after Tint's pruning;
  the probe shows 8 is accepted on this adapter, but a heavier scene could bind
  more - the requiredLimits should request the adapter ceiling, not a fixed 8.

## 8. Verification plan

Acceptance set and order for the implementation lane:

1. **Census hold:** `harness/run.sh --scope m3` stays 149/7/2 (or better), the
   compute/storage/specialization tripwires green. Confirms Phase A did not
   regress the backend. (RUN-only; serialize any rebuild via
   `scripts/ninja-locked.sh`.)
2. **Browser capability gate (R1):** log `adapter.features` +
   `maxStorageTexturesPerShaderStage` on the M4 browser build; decide feature
   opt-in vs format-substitution fallback before proceeding.
3. **Phase A acceptance:** render `principled_bsdf_default` (EEVEE) via the m6
   render rig (`sandbox/m6-measure/inject_render.mjs` or the render-result
   bridge). Success = pipelines build, 0 storage-texture BGL errors, a non-black
   capture. Then the rest of the 26 non-shadow scenes; count how many still error
   (measures the section-6 caveat directly).
4. **Phase A' acceptance:** the subsurface/refraction principled scenes render
   with 0 residual read-write-format errors.
5. **Phase B acceptance:** the 4 shadow scenes render; shadow pixels match the
   staged goldens within Blender's own pinned oiiotool thresholds
   (0.016 / failpercent 1), not merely "no GPU error".
6. **Registry reconciliation:** when Phase A + B land, update
   `ledger/deferred.json` `vertex-stage-rw-storage` and `storage-texture-atomics`
   (the former largely resolved by the C1 strip + tiers; the latter resolved for
   the shadow path by Phase B, or narrowed to volume/surfel-GI if those stay
   deferred).

## 9. Recommended lane structure

- **Lane 1 (Phase A + A', backend/GHOST):** the visibility strip + feature
  opt-in + requiredLimits + the one/two read-write residuals. Owns the
  `gpu/webgpu` + `intern/ghost` fence. Small, high yield, low risk. Gate on the
  census hold + the 26 non-shadow scenes.
- **Lane 2 (Phase B, shadow atomics):** the SSBO-atomic shadow-atlas emulation
  (`GPU_WEBGPU`-guarded shader restructure + backend atlas-as-SSBO bind). Own
  lane, shadow-scene goldens as acceptance. Sequence after Lane 1 (it needs the
  opaque path building to see shadows composited).

## Evidence index

- Probe: `sandbox/eevee-storage-design/probe_storage_bgl.cc`, `CMakeLists.txt`,
  `build.sh`; results `sandbox/eevee-storage-design/probe-result.log`
  (CONTROL 2/9, PROPOSED 8/9, 6/6 Vertex rejected); build log
  `probe-build-run.log`.
- Real render error captures (read-only, corroboration):
  `sandbox/gpu-r44/resolve_default.dump.txt` (all four classes verbatim),
  `sandbox/gpu-r44-r3/shadow_info.log`.
- Backend code: `wgpu_shader_interface_map.cc:213-241` (SSBO strip present,
  StorageImage strip absent), `wgpu_shader.cc:2133-2135` (shader-wide stage
  mask), `wgpu_shader.cc:2354-2362` (explicit-layout strip, buffer-only).
- GHOST device creation: `upstream/intern/ghost/intern/GHOST_ContextWGPU.cc:65-114`
  (feature opt-ins present; no requiredLimits; no Tier1/Tier2).
- EEVEE shaders: `eevee_surf_deferred.bsl.hh` (g-buffer, fragment-only writes),
  `eevee_surf_shadow.bsl.hh` (atomic shadow atlas), `eevee_defines.hh` (format
  aliases).
- Dawn format table (storage-cap grants): `build-dawn/dawn/src/dawn/native/Format.cpp:343-403`.
- Deferrals: `ledger/deferred.json` (`vertex-stage-rw-storage`,
  `storage-texture-atomics`); precedent `fix_plan.md` M3.F12/F13 (0089-class
  `GPU_WEBGPU` GLSL-restructure exception).
