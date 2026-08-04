<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M3.T9.pre — texture formats + data conversion, standalone-proven (findings)

Uncommitted worker notes for orchestrator review. Pin: Blender 5.2 `fbe6228777e7`;
Dawn `chromium/7989 @ 36cf1fae`. Companion: committed module
`sandbox/wgpu-texture-formats/`. The development-heavy `wgpu_data_conversion` /
format-table half of M3, built OUTSIDE the tree and validated on a live native
Dawn/Metal device. `upstream/`, `patches/`, `build-native-gpu/` untouched
(read-only recon of `GPU_texture.hh` + `GPU_format.hh`).

---

## 1. Deliverable — the module (drop-in filenames)

| file | role |
|---|---|
| `wgpu_texture_format.{hh,cc}` + `wgpu_texture_format_list.h` | the format TABLE: every `gpu::TextureFormat` → `wgpu::TextureFormat` + caps {renderable,filterable,storage,blendable,multisample} + ConvClass + FeatureGate, as an X-macro |
| `wgpu_data_conversion.{hh,cc}` | the RGB→RGBA promotion (the one real conversion) |
| `tests/wgpu_texture_format_test.cc` | live Dawn harness + a device-free conversion unit test |

API: `to_wgpu_format(TextureFormat)`, `format_info(fmt)` (record incl. caps),
`caps_of(wgpu::TextureFormat)` (spec classification), `format_table(&count)`;
`promotion_plan(fmt)`, `promote_for_upload(fmt, rgb, w, h)`,
`promote_rgb_to_rgba(...)`, `opaque_alpha_bytes(type, comp_bytes, out)`.

**Source of truth (recon, cited):** `upstream/source/blender/gpu/GPU_format.hh` is
an X-macro table carrying, per format, `{C-type, byte-size, channels, blender enum,
VkFormat, MTLPixelFormat, MTLVertexFormat, GL enum, shader enum}`. The enum set is
`GPU_TEXTURE_FORMAT_EXPAND` (`GPU_texture.hh:45-124`). The Vulkan model is
`vulkan/vk_common.cc::to_vk_format`. **Surprise #1:** GPU_format.hh's MTLPixelFormat
column (e.g. `UNORM_8_8_8 → RGBA8Unorm`, `SFLOAT_16_16_16_16 → RGBA16Float`) is a
near-perfect WebGPU column already — WebGPU's format names track Metal's — so the
mapping was largely pre-specified by upstream; T9's job was verifying it live and
finding the divergences.

## 2. Results — 63 formats, live on "Apple M4 Pro" (Metal), HARNESS PASS

- **Mapped: 63/63.** Every Blender texture format has a WebGPU target (direct, or a
  4-channel promotion). None is unmappable in principle.
- **Created live: 59/63.** The 4 exceptions are genuinely unsupported (below).
- **Round-trip byte-exact: 50/50 copyable color formats** (writeTexture →
  CopyTextureToBuffer → mapAsync → compare), **of which 12 are RGB→RGBA promotions**.
- **Conversion unit test: PASS**; **RGBA8Unorm render-clear+readback: PASS**;
  **Depth32Float depth-clear+readback (0.5): PASS**; **BC1 4×4 block round-trip: PASS**.
- Optional features present on M4 (all requested): `TextureCompressionBC`,
  `Depth32FloatStencil8`, `Float32Filterable`, `RG11B10UfloatRenderable`,
  `Unorm16TextureFormats`.

## 3. The format table (Blender → WebGPU)

Grouped; every row is in `wgpu_texture_format_list.h`. Conv: **D**=Direct memcpy,
**P**=PromoteRGBA (3→4 ch), **Dep**=Depth, **C**=Compressed. Live = result on M4.

| Blender family | WebGPU target(s) | conv | gate | live |
|---|---|:--:|---|---|
| `UNORM_8{,_8,_8_8,_8_8_8}` | R8/RG8/**RGBA8**/RGBA8 Unorm | D/D/P/D | — | created, RT-pass |
| `SNORM_8{…}` | R8/RG8/**RGBA8**/RGBA8 Snorm | D/D/P/D | — | created (not renderable), RT-pass |
| `UNORM_16{,_16,_16_16,_16_16_16}` | R16/RG16/**RGBA16**/RGBA16 Unorm | D/D/P/D | Unorm16TextureFormats | created, RT-pass |
| `SNORM_16{…}` | (R/RG/RGBA)16Snorm | D/D/P/D | **none exists** | **UNSUPPORTED** (§5) |
| `UINT_8/16/32 {…}` | R/RG/**RGBA**/RGBA (8/16/32)Uint | D/D/P/D | — | created, RT-pass |
| `SINT_8/16/32 {…}` | R/RG/**RGBA**/RGBA (8/16/32)Sint | D/D/P/D | — | created, RT-pass |
| `SFLOAT_16 {…}` | R16/RG16/**RGBA16**/RGBA16 Float | D/D/P/D | — | created, RT-pass |
| `SFLOAT_32 {…}` | R32/RG32/**RGBA32**/RGBA32 Float | D/D/P/D | Float32Filterable (filter only) | created, RT-pass |
| `UNORM_10_10_10_2` | RGB10A2Unorm | D | — | created, RT-pass |
| `UINT_10_10_10_2` | RGB10A2Uint | D | — | created, RT-pass |
| `UFLOAT_11_11_10` | RG11B10Ufloat | D | RG11B10UfloatRenderable (render only) | created, RT-pass |
| `UFLOAT_9_9_9_EXP_5` | RGB9E5Ufloat | D | — | created (**not renderable**), RT-pass |
| `UNORM_16_DEPTH` | Depth16Unorm | Dep | — | created, renderable |
| `SFLOAT_32_DEPTH` | Depth32Float | Dep | — | created, clear+readback pass |
| `SFLOAT_32_DEPTH_UINT_8` | Depth32FloatStencil8 | Dep | Depth32FloatStencil8 | created |
| `SRGBA_8_8_8{,_8}` | **RGBA8UnormSrgb** (both) | P/D | — | created, RT-pass |
| `SNORM_DXT1/3/5` | BC1/BC2/BC3 RGBAUnorm | C | TextureCompressionBC | created; BC1 block RT-pass |
| `SRGB_DXT1/3/5` | BC1/BC2/BC3 RGBAUnormSrgb | C | TextureCompressionBC | created |

The 13 **PromoteRGBA** formats (bold "RGBA" targets above): `{U,S}NORM_8_8_8`,
`{U,S}NORM_16_16_16`, `{U,S}INT_8_8_8/16_16_16/32_32_32`, `SFLOAT_16_16_16/32_32_32`,
`SRGBA_8_8_8`. 12 round-trip live (SNORM_16_16_16's target RGBA16Snorm is unsupported).

## 4. Data conversion — the RGB→RGBA promotion (`wgpu_data_conversion`)

WebGPU (like Metal) has **no 3-channel texture formats**. The only real pixel
conversion the table demands is widening the 13 three-channel formats to their
4-channel sibling on upload, appending an opaque alpha per element:

- comp size 1/2/4 bytes copied verbatim for R,G,B; alpha filled with the type's
  opaque value: UNORM→max (`0xFF…`), SNORM→max-positive (`0x7F…`), UINT/SINT→`1`,
  FLOAT16→`0x3C00`, FLOAT32→`0x3F800000` (little-endian).
- Everything else is a **byte-exact memcpy** — proven by the 50/50 round-trip
  (writeTexture then CopyTextureToBuffer returns the uploaded bytes verbatim for
  every uncompressed color format, incl. the packed RGB10A2/RG11B10/RGB9E5).

Row-alignment note: `queue.writeTexture` needs no `bytesPerRow` alignment, but
`CopyTextureToBuffer`/`CopyBufferToTexture` require `bytesPerRow` a multiple of 256
(`COPY_BYTES_PER_ROW_ALIGNMENT`). The harness aligns the readback stride and
compares the first `width*bpp` bytes per row. T9's upload path uses `writeTexture`
(no alignment); any staging-buffer copy path must apply the 256 alignment.

## 5. Genuinely unsupported (needs emulation) — SNORM_16 family

`SNORM_16, SNORM_16_16, SNORM_16_16_16, SNORM_16_16_16_16`.

**Finding (Surprise #2):** WebGPU/Dawn exposes 16-bit **UNORM** formats behind
`Unorm16TextureFormats`, but has **no 16-bit SNORM** support at this pin. The
`RGBA16Snorm`/`R16Snorm`/`RG16Snorm` enumerators EXIST in `webgpu_cpp.h`, but **no
FeatureName enables them** (the full Dawn feature list has `Unorm16TextureFormats`,
`Unorm16Filterable`, `Unorm16FormatsForExternalTexture` — nothing for snorm16).
Requesting the unorm16 feature does not make snorm16 creatable; `CreateTexture`
fails validation. Metal itself supports `MTLPixelFormatRGBA16Snorm`, so this is a
Dawn/WebGPU-surface gap, not a hardware one.

**T9 consequence — emulation options** (pick per usage):
1. **Store as `RGBA16Uint`/`Unorm` + shader remap** `snorm = value/32767.0` (exact
   for the [-1,1] range); the create-info's sampler already reads it as float. Cheap
   for read-only textures; needs a codegen hook on sample.
2. **Promote to `RGBA16Float`** (2-byte half per channel) — lossy at the ULP level
   for exact snorm values but ample for normal/data textures; simplest.
3. Defer to `ledger/deferred.json` with blocker "WebGPU: no 16-bit snorm texture
   format" if no shipping shader needs it (grep first: Blender uses snorm16 rarely —
   mostly normal/vector textures).

## 6. Capability cross-check — LIVE discovery vs spec table (Surprise #3)

The harness DISCOVERS renderable/storage/multisample by `CreateTexture` usage
probes; these are AUTHORITATIVE and refine the hand-written `caps_of` spec table:

- **Renderable=false (correct):** all SNORM 8-bit, `RGB9E5Ufloat`, all 6 BC — matches
  spec (snorm/shared-exponent/compressed are sampled-only).
- **Storage=true:** the RGBA8/RGBA16(u/s/int/float)/R32/RG32/RGBA32 families (a
  promoted 3-ch format inherits its RGBA target's storage capability).
- **Multisample DIVERGENCE:** Metal supports MSAA on **8- and 16-bit integer** color
  formats (`SINT_8…`, `UINT_16…` → M=1), but NOT on **32-bit-per-channel** formats
  (`SINT_32*`, `UINT_32*`, `RG32Float`, `RGB(A)32Float` → M=0). My conservative
  `caps_of` (integer ⇒ no MSAA) under-reported the 8/16-bit int case. **Lesson: the
  backend should trust device-probed caps, not a hardcoded spec table**, or adopt the
  harness-verified table (emitted per-format by this harness). `filterable`/`blendable`
  remain spec-only (pipeline-level; not creation-probeable) and are flagged as such.

## 7. Other findings

- **No ETC2/ASTC in Blender 5.2's GPU texture enum** — only BC/DXT (S3TC). So the
  WebGPU backend needs only `texture-compression-bc` (present on Apple Silicon);
  ETC/ASTC are a non-issue at the pin.
- **No 24-bit depth in the TextureFormat enum.** `UNORM_24_DEPTH{,_UINT_8}` exist in
  the broader `DataFormat` (GPU_format.hh:105-106) but are NOT in
  `GPU_TEXTURE_FORMAT_EXPAND`; the texture depth set is 16-unorm / 32-float /
  32-float-stencil8. So the classic "Depth24 vs Depth24Plus" ambiguity does not arise
  for textures — Blender maps cleanly to `Depth16Unorm`/`Depth32Float`/
  `Depth32FloatStencil8`. (`Depth24Plus`/`Depth24PlusStencil8` are available WebGPU
  fallbacks if a future format needs an implementation-defined ≥24-bit depth.)
- **`SNORM_10_10_10_2` is a vertex/data format, not a texture format** (it's in
  `GPU_DATA_FORMAT_EXPAND` but absent from the texture EXPAND) — excluded from the
  table. WebGPU has no `RGB10A2Snorm` anyway.

## 8. What T9 integration still needs

Design is done and proven; the rest is wiring `source/blender/gpu/webgpu/`:
1. Key the table on the real `gpu::TextureFormat` (drop the mirror enum; `#include
   "GPU_format.hh"` and reuse its X-macro directly — the WebGPU column can even be
   ADDED to GPU_format.hh as a patch, mirroring the existing vk/mtl columns).
2. `wgpu_texture.cc`: create textures via `to_wgpu_format`; on upload dispatch on
   `ConvClass` (Direct memcpy vs `promote_for_upload`); apply the 256 `bytesPerRow`
   alignment on any staging copy (writeTexture path needs none).
3. Emulate the SNORM_16 family (§5) or defer it.
4. Prefer **device-probed capabilities** over the spec `caps_of` (§6); or ship the
   harness-verified per-format cap table.
5. Depth readback/aspect handling for framebuffer blits (`wgpu_framebuffer`) —
   Depth32Float/Depth16Unorm are copyable (proven); Depth24Plus is not.

## 9. Verdict

The format table + data-conversion module are BUILT and PROVEN on live Dawn/Metal:
63/63 mapped, 59 created, 50/50 color round-trips byte-exact (12 promoted),
render/depth/compressed paths verified, conversion unit test green. The only
genuinely unsupported formats are the 4 SNORM-16 (a WebGPU surface gap, with three
concrete emulations specified). T9 is now an integration task. Confidence HIGH.
