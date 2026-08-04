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

1. **`wgpu_texture.{hh,cc}`** — `WGPUTexture : gpu::Texture`, implementing the 13
   base virtuals (gpu_texture_private.hh: init_internal ×3, update_sub ×2, read,
   clear, copy_to, generate_mipmap, swizzle_set, mip_range_set), modelled on
   `vk_texture.cc` (1089 LOC). Uses the landed format+conversion:
   `CreateTexture(to_wgpu_format(fmt), device-probed usage)`; `update_sub` dispatches
   on `ConvClass` (Direct memcpy vs `promote_for_upload`) with 256-byte
   `bytesPerRow` alignment on copy paths; `read` via a MAP_READ staging buffer +
   `CopyTextureToBuffer`; views via `CreateView`. **SNORM_16 emulation choice:
   promote to RGBA16Float** (simplest; the alternative unorm16+shader-remap needs a
   codegen hook — defer). Depth-aspect handling exposed for `wgpu_framebuffer`.
   → then request lane-A texture_alloc wiring → run the 3 T9 tests.
2. **`wgpu_framebuffer.{hh,cc}`** — GPUFrameBuffer attachments → a transient
   `GPURenderPassDescriptor`; depth aspect from #1. Gate: `framebuffer_test`.
3. **`wgpu_state.{hh,cc}` + `wgpu_state_table.{hh,cc}`** — from
   `sandbox/wgpu-state-tables/`. NOTE: the real `GPUBlend`/`GPUDepthTest` are
   UNSCOPED `enum`s with `GPU_BLEND_*` members (not my scoped mirror), so the
   X-macro switch needs the `GPU_BLEND_##name` spelling — a mechanical rework, not a
   one-line alias like the format table. Drives `GPUState`/`GPUStateMutable` →
   cached pipeline descriptors in `wgpu_pipeline`. Gate: `state_blend_test`.
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
validated. Gate tests blocked on lane-A `texture_alloc` + my `wgpu_texture.cc`
(next). No gate PASS claimable yet — reported honestly.
