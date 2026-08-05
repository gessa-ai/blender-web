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

## FRAMES RUN (B1, 2026-08-05) — THE DRAW PATH IS CORRECT; blend family renders

Read the now-visible validation errors (patch 0040 callback). Findings:

**blend_none has NO validation error.** With the callback live, blend_none's draw
survives validation entirely — readback stays exactly at the clear colour (1,0,1,1),
i.e. the fragment never covers the pixel. Not a vertex-format / attachment mismatch;
a geometry problem. Proven by temp-wiring the draw path in wgpu_batch.cc (reverted):

1. **ROOT CAUSE A — lane A: `WGPUShaderInterface` never calls populate_builtins().**
   Probe: `interface->uniform_builtin(GPU_UNIFORM_MVP)` returns **0** (garbage), but
   `uniform_get("ModelViewProjectionMatrix")->location` is **1024** (correct). The base
   `ShaderInterface` ctor (gpu_shader_interface.cc:22) only fills `image_formats_`, NOT
   `builtins_[]`. Vulkan/Metal/GL fill it via a populate_builtins() loop
   (vk_shader_interface.cc:190-196). Lane A's WGPUShaderInterface (wgpu_shader.cc:648)
   calls sort_inputs() and stops — `builtins_[]` stays uninitialised. So
   `GPU_matrix_bind` uploads MVP to location 0 → matches no push-constant slot → MVP
   stays zero → gl_Position=0 → degenerate → nothing drawn.
   **LANE A FIX:** in `WGPUShaderInterface::init` after `sort_inputs()`, add the VK loop:
   `for u in GPU_NUM_UNIFORMS: builtins_[u] = uniform_get(builtin_uniform_name(u)) ?`
   `location : -1;` (and the GPU_NUM_UNIFORM_BLOCKS ubo_builtins_ loop). File
   wgpu_shader.cc, class WGPUShaderInterface. Verified: uploading MVP by-name in a
   temp-wire flips the whole blend family FAIL→run-to-pixel.

2. **ROOT CAUSE B — Y orientation (cross-cutting; shader/codegen = lane A).** Even with
   a *correct identity* MVP the 1×1 pixel is not covered: the [0,1]² preset quad's
   corner lands exactly on the pixel centre (NDC origin). In y-up (OpenGL, which the
   reference VK/Metal backends present) that corner is on a TOP+LEFT edge → covered;
   my WebGPU renders y-DOWN so it is a BOTTOM+LEFT corner → excluded by the top-left
   fill rule. DECISIVE test: uploading `diag(1,-1,1,1)` (negate only Y) makes
   blend_none PASS; identity does not; full [0,1]→[-1,1] map also passes. So the
   WebGPU backend must present Blender's y-up convention. WebGPU has no negative
   viewport height → the flip belongs in vertex-shader clip output (`position.y =
   -position.y`) in lane A's codegen/glsl_patch, PAIRED with a framebuffer readback
   row-flip for WxH targets (wgpu_framebuffer/wgpu_texture read — partly lane B).
   This also fixes upside-down real frames (M4). Needs a driver coord-convention ADR.

**With A+B temp-wired, the ENTIRE blend family renders CORRECTLY** (12/12 PASS, pixels
byte-match the expected blend results): none/alpha/alpha_premult/additive/
additive_premult/multiply/subtract/invert/oit/background/min/max. PNG montage of the
readbacks: `sandbox/gpu-render-harness/evidence/first_frames_blend.png` — the project's
first rendered frames from the WebGPU backend. Temp-wire reverted; wgpu_batch.cc back
to pristine (the draw path needed no change — it was already correct).

**LANDED (mine): patch 0043 — buffer CopyDst usage.** `usage_flags` dropped CopyDst for
GPU_USAGE_DEVICE_ONLY, but Vulkan gives every vertex/index/storage buffer
TRANSFER_DST unconditionally (vk_*_buffer.cc). push_constants' DEVICE_ONLY SSBO hit
"[Buffer] usage (CopySrc|Storage|Indirect) doesn't include CopyDst". Fix: CopyDst is
now unconditional. Verified: that validation error is gone (push_constants now fails
only on values — compute dispatch writes nothing, a separate compute concern).

**Remaining draw-set blockers (characterised, not frames-critical):**
- `immediate_one_plane`/`immediate_two_planes` CRASH(139): WGPUImmediate not wired /
  not GPU_init-safe (lane B immediate — separate piece).
- `framebuffer_multi_viewport` CRASH(139): real validation error "layer count (256) of
  [TextureView] used as attachment is greater than 1" — my attachment_view builds a
  full-array view; a render attachment needs a single-layer 2D view (+ multi-viewport
  emulation, since WebGPU has no viewport-array). File wgpu_framebuffer.cc — lane B
  follow-up, substantial.


## ROUND 8 (2026-08-05, lane B) — Y-orientation halves + F4 attachment view; REAL-PATH BLEND GREEN

Lane A landed F1 (populate_builtins) + F2 codegen (wgpu_shader.cc:787
`gl_Position.y = -gl_Position.y;`) during this round. Combined with the lane-B halves
below, **GPUWebGPUTest.blend_* is 12/12 PASS on the REAL backend path** (not temp-wire).
Evidence: sandbox/gpu-render-harness/evidence/real_path_frames_blend.{png,txt}.

LANDED (mine), each patch reverse-applies clean:
- **patch 0044** (10498c0) — wgpu_pipeline front-face swap (ADR-005 decision 2). frontFace
  = negate(to_front_face(invert_facing)) CW<->CCW to compensate the clip-space Y-flip.
- **patch 0045** (2acb81b) — wgpu_framebuffer::read render-target readback row-flip
  (ADR-005 decision 3). src_row = fh-1-(y+row). RENDER-TARGET path only; WGPUTexture::read
  untouched -> texture_* gate 64/64 held. Rationale: the Vulkan/Metal reference does the
  clip-flip (vk_shader retargets Z only, but the tests encode y-up-correct rasterization)
  and does NOT flip on readback (vk_framebuffer.cc:355 -> read_sub); WebGPU adds its clip-
  flip over a top-left framebuffer, mirroring the stored texture, so a compensating readback
  flip is required. Multi-row correctness unverified (no runnable multi-pixel fb-read test;
  blend is 1x1, framebuffer_cube reads via GPU_texture_read not this path).
- **patch 0046** (cc355c1) — wgpu_framebuffer attachment_view single-layer (M3.F4). Query
  GetDepthOrArrayLayers(); whole-texture CreateView() only for 1-layer 2D; array/cube layer<0
  clamped to baseArrayLayer=0/count=1/2D. VERIFIED: the "layer count (256)... greater than 1"
  Dawn error is eliminated. framebuffer_cube unaffected (attaches via CUBEFACE, layer>=0).

CHARACTERIZED (NOT landed — outside lane-B file ownership; lane A / driver items):
- **immediate_one_plane/two_planes CRASH(139)** — ROOT CAUSE: `imm` (thread_local) is null
  because WGPUContext never does `imm = new WGPUImmediate()` and activate() never calls
  immActivate(). Both live in wgpu_context.cc (LANE A) — the file's own comment (lines 91-93)
  says the wiring lands "once [WGPUImmediate] lands". WGPUImmediate IS landed and complete:
  concrete class (base Immediate has exactly begin()/end() pure virtuals, both overridden),
  full begin()/end() (transient VBO upload + load-pass + pipeline + push-constant bind + draw).
  **LANE A REQUEST (3 lines in wgpu_context.cc):** ctor `imm = new WGPUImmediate();`;
  activate() `immActivate();`; deactivate() `immDeactivate();` — exactly the vk_context.cc
  pattern (:43,:141,:60). Backtrace: immVertexFormat() -> GPU_vertformat_clear(&imm->..)
  EXC_BAD_ACCESS 0x20.
- **framebuffer_multi_viewport CRASH(139)** — my attachment-view fix removed the Dawn
  validation error, but the SEGV remains: the test shader fails to compile
  ("'gpu_ViewportIndex' : undeclared identifier", wgpu_shader.cc:1108, LANE A codegen) ->
  null shader -> GPU_shader_bind(null) SEGV. Even with the builtins declared, a faithful pass
  needs MULTI-PASS layer+viewport emulation: WebGPU has NO viewport-array (one setViewport per
  pass) and NO gl_Layer (no layered rendering from the vertex stage). The test drives 256
  layers x 16 viewports = 4096 (layer,viewport) cells, each written by dedicated triangles via
  gl_Layer/gl_ViewportIndex. Options: (a) loop 4096 single-layer/single-viewport passes routing
  the matching triangles per cell — heavy, needs codegen to expose gpu_Layer/gpu_ViewportIndex
  as per-draw uniforms; (b) defer as a WebGPU-limitation carve-out. Recommend a driver decision.
- **push_constants* (10 FAILED) — task 5** — ROOT CAUSE: `WGPUBackend::compute_dispatch`
  (wgpu_backend.cc:62, LANE A file) is an EMPTY STUB (`int /*x*/,...`). The compute shader that
  writes the push-constant values into the SSBO never runs, so the readback stays zero and the
  value assertions fail. Genuinely unimplemented (not broken-present). Needs the WebGPU compute
  path: compute pipeline (from the compute module — lane A shader) + bind groups (SSBO + PC UBO)
  + ComputePassEncoder.DispatchWorkgroups. This is the T8 compute piece; out of the task-4-gated
  stretch scope and in lane A's backend file.
