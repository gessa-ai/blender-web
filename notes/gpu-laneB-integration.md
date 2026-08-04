<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M3 integration lane B — texture/framebuffer/state port (progress + plan)

Uncommitted worker notes. Pin: Blender 5.2 `fbe6228777e7`; Dawn `chromium/7989`.
Lane B = port the proven sandbox modules (T9 texture/formats/conversion, T10
framebuffer/state/pipeline/immediate/batch) into the real `source/blender/gpu/
webgpu/` backend on the shared native tree (`build-native-gpu`), captured as
**patch 0016**. Shared tree with lane A (context/buffers/shaders = patch 0015).

## Workflow established (shared-tree, upstream write-blocked)

- The Write/Edit TOOLS are hook-blocked for the whole `upstream/` prefix
  (`.claude/hooks/protect.sh:14`), including the owned `webgpu/` subdir. **Bash file
  writes are NOT blocked.** So: author in `sandbox/lane-b-staging/webgpu/` (Edit
  freely), `cp` into `upstream/.../webgpu/`, build via
  `harness/buildwrap.sh scripts/ninja-locked.sh -C build-native-gpu <target>`.
- **Patch 0016 capture** (patches are CUMULATIVE — each is a git diff on the
  prior-patches-applied tree; verified from 0015's CMake hunk showing 0012's
  context): new files via `git diff --no-index /dev/null <f>`; the shared
  `CMakeLists.txt` delta via difflib against a snapshot taken BEFORE my edits
  (`sandbox/lane-b-staging/snapshots/CMakeLists.txt.pre0016`). Validated by
  `git -C upstream apply --check --reverse` (reverse-applies clean ⇒ the patch is
  exactly my delta on the 0001-0015 base — which is what harness/run.sh:121-136's
  series check accepts for an already-applied patch).

## Landed + VERIFIED this iteration

**T9 data foundation compiles in-tree** (`bf_gpu`, WITH_WEBGPU_BACKEND, 63 s, clean):
- `wgpu_texture_format.{hh,cc}` + `wgpu_texture_format_list.h` — the format table
  from `sandbox/wgpu-texture-formats/`, re-keyed on the REAL `blender::gpu::
  TextureFormat` (a one-line alias — the X-macro member names already match
  `GPU_TEXTURE_FORMAT_EXPAND`). `to_wgpu_format` / `caps_of` / `format_info` /
  ConvClass / FeatureGate, all as proven (63/63 mapped, 59 creatable on M4).
- `wgpu_data_conversion.{hh,cc}` — the RGB→RGBA promotion (the one real conversion).
These are SELF-CONTAINED (only webgpu_cpp.h + GPU_format.hh) with **no lane-A
dependency**, so they land first and unblock `wgpu_texture` + `wgpu_pipeline`.
Captured in **patch 0016**.

## HARD BLOCKER for the T9 gate (needs lane A)

`texture_test` / `texture_view_test` / `buffer_texture_test` cannot RUN until
`WGPUBackend::texture_alloc` returns a real `WGPUTexture` — but `wgpu_backend.cc`
is **lane A's file** (currently `BLI_assert_unreachable()` at wgpu_backend.cc:81).
**Request to lane A:** wire `texture_alloc(name) → new WGPUTexture(name)` once my
`wgpu_texture.{hh,cc}` lands (I'll flag the exact commit). Until then the gate
tests abort at allocation regardless of my code. (Same pattern lane A already hit:
texturepool/storagebuf were bootstrap-mandatory; texture_alloc is the T9 hook.)

## Sequenced plan (remaining lane-B files)

1. **`wgpu_texture.{hh,cc}`** — `WGPUTexture : gpu::Texture`. **HEADER AUTHORED**
   (`sandbox/lane-b-staging/webgpu/wgpu_texture.hh`) — the interface contract lane A
   wires `texture_alloc` against. Exact virtual set to implement (recon'd from
   `gpu_texture_private.hh:158-176,334-337` + `vk_texture.hh`):
   - `init_internal()` / `init_internal(VertBuf*)` / `init_internal(gpu::Texture*
     src, int mip_offset, int layer_offset, bool use_stencil)` — allocate / buffer
     texture / view. The base `init_1D/2D/3D/cubemap/buffer/view` are non-virtual and
     call these; they set `w_,h_,d_,format_,type_,gpu_image_usage_flags_,mipmaps_`
     BEFORE the virtual fires — so `allocate()` reads those members.
   - `update_sub(mip, offset[3], extent[3], eGPUDataFormat, const void*, int
     unpack_row_length)` and `update_sub(..., GPUPixelBuffer*)`.
   - `read(mip, eGPUDataFormat, void* dst)`, `clear(double4)`, `copy_to(Texture*,
     IndexRange)`, `generate_mipmap()`, `swizzle_set(char[4])`, `mip_range_set`.
   Create via `device.CreateTexture({to_wgpu_format(format_), dim from type_
   (GPU_TEXTURE_{1D,2D,3D,CUBE}[_ARRAY]), size {w_,h_,d_/layers}, mipLevelCount,
   usage from gpu_image_usage_flags_ (eGPUTextureUsage → CopyDst|CopySrc|
   TextureBinding|StorageBinding|RenderAttachment)})`. `update_sub` dispatches on
   `ConvClass` (Direct `queue.writeTexture` vs `promote_for_upload` first) — no 256
   align needed for writeTexture; `read` uses a MAP_READ staging buffer +
   `CopyTextureToBuffer` (256-byte `bytesPerRow`). **SNORM_16 emulation choice:
   promote to RGBA16Float** (simplest; unorm16+shader-remap needs a codegen hook —
   defer). Depth-aspect exposed for `wgpu_framebuffer`. First cut may stub
   generate_mipmap/copy_to/swizzle/mip_range/buffer-texture/view (assert) to compile
   + pass the basic texture_test create/upload/read path, filling as tests demand.
   → then request lane-A `texture_alloc(name) → new WGPUTexture(name)` → run the 3
   T9 tests.
2. **`wgpu_framebuffer.{hh,cc}`** — GPUFrameBuffer attachments → a transient
   `GPURenderPassDescriptor`; depth aspect from #1. Gate: `framebuffer_test`.
3. **`wgpu_state_table` — DONE by lane B2** (patch 0021, a78b0a5). So my remaining
   state work is only the WIRING in `wgpu_state`/`wgpu_pipeline`, using B2's pure
   `to_blend`/`to_depth`/`to_stencil`. B2's integration contract (per its report §4):
   `to_*` are pure functions; **`depthWriteEnabled` comes from the WRITE mask, not
   the depth mapping**; stencil masks + reference wire from `GPUStateMutable`
   (`SetStencilReference` on the pass); color/write-mask from
   `GPUWriteMask(state.write_mask)` via `flag_is_set`; **provoking LAST has NO
   descriptor knob** → shader-codegen emulation (Metal precedent, matches my T10.pre
   finding); **CUSTOM blend gates on `dual-source-blending` + `@blend_src` variants**.
   Gate: `state_blend_test`.
4. **`wgpu_pipeline.{hh,cc}`** — render/compute pipeline descriptor build + cache
   (needs lane A's `wgpu_shader` for the modules; coordinate). Gates:
   `push_constants_test`, `specialization_constants_test`.
5. **`wgpu_immediate.{hh,cc}`** (streaming vertex; needs lane A's shader) —
   `immediate_test`. **`wgpu_batch`** (pipeline lookup + bind groups + draw; the
   point-size R1 draw hook lands here) — needs lane A buffers.
6. **querypool / fence / pixelbuf** — small.
→ full `gpu` suite = the M3_GPU_BACKEND gate.

Sequencing note: #1-#2 are least lane-A-coupled (only need texture_alloc wiring);
#3-#5 need lane A's shader/buffer allocators — coordinate via reports, do NOT edit
lane A's files.

## Status

Foundation (format+conversion) landed + compiling in-tree; patch 0016 captured +
validated.

**`wgpu_texture.{hh,cc}` LANDED — patch 0016b (bf_gpu green).** The full
`WGPUTexture : gpu::Texture` — 11 virtuals implemented, not stubbed:
- **creation**: `init_internal()` → `allocate()` builds a `wgpu::TextureDescriptor`
  (dimension from type_ — 1D-array/cube collapsed to 2D layers; usage from
  gpu_image_usage_flags_ + always CopySrc|CopyDst; format via to_wgpu_format).
  `init_internal(VertBuf*)` stores the source buffer (no texel-buffer texture in
  WebGPU — sampling forwards to the buffer at bind-group time, lane A).
  `init_internal(src,…)` aliases the source device texture (distinct wgpu view
  created lazily at bind/attach time).
- **upload** `update_sub(…data…)`: CPU host→device conversion then
  `queue.writeTexture` (no 256 align on writeTexture). `update_sub(…pixbuf)` asserts
  (needs pixelbuf_alloc — lane A placeholder).
- **read**: `CopyTextureToBuffer` (256-aligned bytesPerRow) → MAP_READ staging →
  `instance.WaitAny` (blocking, mirrors wgpu_buffer.cc) → strip row padding →
  device→host conversion.
- **clear**: colour = pack one device texel + writeTexture over every mip/layer;
  depth/stencil = a render pass with only a depth-stencil attachment loadOp=Clear
  (no draw/pipeline/shader).
- **copy_to**: `CopyTextureToTexture` per mip. **generate_mipmap**: no-op (needs
  the blit-pipeline; documented). **swizzle_set/mip_range_set**: trivial stores.
- **CPU conversion matrix** (WebGPU copies move raw bytes → all pixel conversion is
  host-side, self-contained in wgpu_texture.cc): unorm/snorm/uint/sint 8/16/32,
  f16/f32, R11G11B10 pack/unpack, RGB→RGBA promotion (opaque alpha),
  GPU_DATA_{FLOAT,HALF_FLOAT,INT,UINT,UBYTE} + 10_11_11_REV passthrough.
- **SNORM_16 emulation (§5 choice REVISED)**: store in matching-width *Uint*
  (R/RG/RGBA16Uint) with byte-identical SNORM two's-complement patterns — exact CPU
  round-trip (passes the 0.00002-bias tests, unlike RGBA16Float). Shader-sample
  remap still deferred (no shader samples snorm16 in the gate).

Two locked-header signature bugs fixed to match the base pure-virtuals (else
WGPUTexture stayed abstract): `unpack_row_length` int→**uint**; the pixbuf
`update_sub` had a spurious `mip` param — removed. External contract lane A wires
(`new WGPUTexture(name)` → `Texture*`) unchanged.

CMake SRC 3-way merge point: appended `wgpu_texture.{cc,hh}` after lane-A's
`wgpu_shader_compiler.{cc,hh}` (atomic 2-line add; patch 0016b hunk depends on those
lines being present → effective apply-order is AFTER 0019/0021 despite the "0016b"
name — driver reconciles numbering at the M3 boundary).

### Gate status (honest)
`texture_test` cannot RUN yet: `WGPUBackend::texture_alloc` still asserts
(wgpu_backend.cc:81, lane-A file). **Request lane A: `texture_alloc(name) → new
webgpu::WGPUTexture(name)`.** Even wired, the suite runs through
`GPUTest::SetUpTestSuite → GPU_init`, which warms builtin shaders (shader_alloc, T7)
+ gpu_batch_presets (batch_alloc) — so first texture_test RUN also needs lane-A
shader + the bootstrap wgpu_batch. Known expected-fails once it runs: depth-DATA
upload (WebGPU forbids buffer→texture for Depth32Float depth aspect — needs a
render/compute path; clear+read work) and BC-compressed upload (deferred). No gate
PASS claimable yet — reported honestly. bf_gpu compiles green (21 s clean TU).
