/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_context.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 */

#include "wgpu_context.hh"

#include "BLI_assert.h"
#include "BLI_threads.h"
#include "BLI_utildefines.h"

#include "gpu_capabilities_private.hh"

#include "wgpu_framebuffer.hh"
#include "wgpu_immediate.hh"
#include "wgpu_shader.hh"
#include "wgpu_state_manager.hh"
#include "wgpu_storage_buffer.hh"
#include "wgpu_texture.hh"
#include "wgpu_uniform_buffer.hh"

#include "GPU_framebuffer.hh"
#include "GPU_texture.hh"

/* GHOST-private: the WITH_WEBGPU_BACKEND block in gpu/CMakeLists.txt adds
 * intern/ghost/intern to this TU's include path. Production should instead route
 * the handle through a GHOST_IContext virtual (mirroring getVulkanHandles) so
 * the gpu module never sees a GHOST-private header — noted in the T4 findings. */
#if defined(__EMSCRIPTEN__) && !defined(WITH_HEADLESS)
/* Windowed browser build: GHOST_WindowWeb::newDrawingContext /
 * GHOST_SystemWeb::createOffscreenContext hand back a GHOST_ContextWGPUWeb (the
 * emdawnwebgpu twin), NOT the native GHOST_ContextWGPU. The two classes have
 * DIFFERENT member layouts — the web class stores canvas_selector_/width_/height_
 * BEFORE its instance_/adapter_/device_/queue_ handles — so casting the web object
 * to the native type and calling getInstance() reads the std::string SSO bytes as
 * the instance pointer. That garbage handle is misaligned, and its first
 * wgpuInstanceAddRef traps with "operation does not support unaligned accesses"
 * (wasm32 i64 atomic RMW on RefCounted::mRefCount needs 8-byte alignment). Select
 * the correct GHOST context type here — the same seam the in-tab render harness
 * (sandbox/gpu-render-harness/wgpu_context_web.cc) already uses, which is exactly
 * why that main-thread profile never hit the trap. The guard is !WITH_HEADLESS
 * (NOT WITH_GHOST_WEB — that add_definitions is scoped to intern/ghost only and
 * never reaches bf_gpu): the windowed browser target is the sole non-headless
 * Emscripten WebGPU build and has platform_web/ghost on bf_gpu's include path,
 * whereas the M3 offscreen/conformance build (build-wasm-gpu, WITH_HEADLESS) and
 * any native build keep the native branch below unchanged. */
#  include "GHOST_ContextWGPUWeb.hh"
using WGPUGhostContext = GHOST_ContextWGPUWeb;
#else
#  include "GHOST_ContextWGPU.hh"
using WGPUGhostContext = GHOST_ContextWGPU;
#endif

#include <algorithm>
#include <climits>

namespace blender::gpu {

wgpu::Device WGPUContext::s_device = nullptr;
wgpu::Instance WGPUContext::s_instance = nullptr;
wgpu::Queue WGPUContext::s_queue = nullptr;

WGPUContext::WGPUContext(GHOST_IWindow *ghost_window, GHOST_IContext *ghost_context) : Context()
{
  ghost_window_ = ghost_window;
  ghost_context_ = ghost_context;

  /* The context was created by GHOST_SystemHeadless::createOffscreenContext for
   * GHOST_kDrawingContextTypeWebGPU, so it is a GHOST_ContextWGPU. Borrow its
   * already-initialized Dawn instance/adapter/device/queue (ownership stays with
   * GHOST). */
  WGPUGhostContext *wgpu_ghost = static_cast<WGPUGhostContext *>(ghost_context);
  instance_ = wgpu_ghost->getInstance();
  adapter_ = wgpu_ghost->getAdapter();
  device_ = wgpu_ghost->getDevice();
  queue_ = wgpu_ghost->getQueue();
#if defined(__EMSCRIPTEN__) && !defined(WITH_HEADLESS)
  /* GHOST_ContextWGPUWeb has no getAdapterName() (the browser exposes no adapter
   * name string); mirror the harness override's fixed label. */
  adapter_name_ = "emdawnwebgpu";
#else
  adapter_name_ = wgpu_ghost->getAdapterName();
#endif

  /* Publish the device/instance/queue backend-side so worker threads (async
   * shader compilation) can reach them without the thread-local active context —
   * GPU_context_active_get() is null on the compile worker. There is a single
   * Dawn device (one GHOST_ContextWGPU), so a static is correct. */
  s_device = device_;
  s_instance = instance_;
  s_queue = queue_;

  /* Fill the global capability table from the live device limits. Device-probed
   * (per the T9 findings recommendation), not hard-coded to the WebGPU spec
   * floors — the M4 Pro / Dawn adapter reports much higher limits. */
  capabilities_init();

  /* Per-context state manager (lane B's WGPUStateManager). The base Context dtor
   * owns its lifetime (Context::~Context deletes state_manager). */
  state_manager = new WGPUStateManager();

  /* Immediate-mode drawing context (lane B's WGPUImmediate). Every backend
   * constructs `imm` in its ctor (mirrors vk_context.cc:43); without it the
   * thread-local `imm` stays null and immBegin/immVertexFormat dereference a null
   * pointer (immediate_* SEGV). Base Context::~Context deletes it (gpu_context.cc:101),
   * but the dtor below deletes+nulls it early to mirror VKContext's lifecycle. */
  imm = new WGPUImmediate();

  /* Default offscreen frame-buffers (mirrors vk_context.cc:45-47). The bootstrap /
   * GPU_offscreen path dereferences active_fb, so it must be non-null — without
   * these the draw families crash in GPU_offscreen_create. Base Context owns them. */
  back_left = new WGPUFrameBuffer("back_left");
  front_left = new WGPUFrameBuffer("front_left");
  active_fb = back_left;
}

WGPUContext::~WGPUContext()
{
  /* Drop the back-buffer wrapper first: the base Texture dtor detaches it from
   * back_left/front_left (which are still alive here), releasing the surface
   * texture ref without destroying the surface's own texture. */
  if (surface_texture_ != nullptr) {
    delete surface_texture_;
    surface_texture_ = nullptr;
  }
  free_resources();
  /* Mirror VKContext::~VKContext():59-60 — delete `imm` here and null it so the
   * base Context dtor's `delete imm` (gpu_context.cc:101) is a safe no-op. */
  delete imm;
  imm = nullptr;
  /* Drop the backend-side device/instance/queue refs so the statics do not
   * outlive GHOST's teardown and release a dangling handle at process exit. */
  s_device = nullptr;
  s_instance = nullptr;
  s_queue = nullptr;
}

/* --- Activation --------------------------------------------------------- */
/* Mirror VKContext::activate/deactivate but without the render-graph (WebGPU's
 * implicit model needs none). immActivate/immDeactivate bind this context's `imm`
 * as the thread-local immediate-mode target, exactly as the Vulkan backend does
 * (vk_context.cc:141,147). */
void WGPUContext::activate()
{
  BLI_assert(is_active_ == false);
  is_active_ = true;
  sync_backbuffer();
  immActivate();
}

void WGPUContext::deactivate()
{
  immDeactivate();
  is_active_ = false;
}

void WGPUContext::capabilities_init()
{
  wgpu::Limits limits = {};
  /* ConvertibleStatus converts to bool == (status == Success). */
  if (device_ == nullptr || !device_.GetLimits(&limits)) {
    return;
  }

  /* Reset all capabilities from any previous context (mirrors vk_backend.cc:911). */
  GCaps = {};

  /* WebGPU has no geometry-shader stage and no shader stencil export. */
  GCaps.geometry_shader_support = false;
  GCaps.stencil_export_support = false;

  GCaps.max_texture_size = std::max(int(limits.maxTextureDimension1D),
                                    int(limits.maxTextureDimension2D));
  GCaps.max_texture_3d_size = int(std::min<uint64_t>(limits.maxTextureDimension3D, INT_MAX));
  GCaps.max_buffer_texture_size = uint32_t(std::min<uint64_t>(limits.maxBufferSize, UINT_MAX));
  GCaps.max_texture_layers = int(std::min<uint64_t>(limits.maxTextureArrayLayers, INT_MAX));
  GCaps.max_textures = int(std::min<uint64_t>(limits.maxSampledTexturesPerShaderStage, INT_MAX));
  GCaps.max_images = int(std::min<uint64_t>(limits.maxStorageTexturesPerShaderStage, INT_MAX));
  /* WebGPU exposes a single per-dimension workgroup-count cap (not per axis). */
  const int wg_count = int(std::min<uint64_t>(limits.maxComputeWorkgroupsPerDimension, INT_MAX));
  GCaps.max_work_group_count[0] = wg_count;
  GCaps.max_work_group_count[1] = wg_count;
  GCaps.max_work_group_count[2] = wg_count;
  GCaps.max_work_group_size[0] = int(std::min<uint64_t>(limits.maxComputeWorkgroupSizeX, INT_MAX));
  GCaps.max_work_group_size[1] = int(std::min<uint64_t>(limits.maxComputeWorkgroupSizeY, INT_MAX));
  GCaps.max_work_group_size[2] = int(std::min<uint64_t>(limits.maxComputeWorkgroupSizeZ, INT_MAX));
  GCaps.max_uniforms_vert = GCaps.max_uniforms_frag = int(
      std::min<uint64_t>(limits.maxUniformBuffersPerShaderStage, INT_MAX));
  /* No maxDrawIndirectCount / maxDrawIndexedIndexValue analogs in WebGPU; the
   * spec places no cap here, so use INT_MAX (as the VK path clamps to). */
  GCaps.max_batch_indices = INT_MAX;
  GCaps.max_batch_vertices = INT_MAX;
  GCaps.max_vertex_attribs = int(std::min<uint64_t>(limits.maxVertexAttributes, INT_MAX));
  /* maxInterStageShaderVariables counts vec4 slots; ×4 → float components. */
  GCaps.max_varying_floats = int(
      std::min<uint64_t>(uint64_t(limits.maxInterStageShaderVariables) * 4u, INT_MAX));
  GCaps.max_shader_storage_buffer_bindings = GCaps.max_compute_shader_storage_blocks = int(
      std::min<uint64_t>(limits.maxStorageBuffersPerShaderStage, INT_MAX));
  GCaps.max_uniform_buffer_size = size_t(limits.maxUniformBufferBindingSize);
  GCaps.max_storage_buffer_size = size_t(limits.maxStorageBufferBindingSize);
  GCaps.storage_buffer_alignment = limits.minStorageBufferOffsetAlignment;

  GCaps.max_parallel_compilations = BLI_system_thread_count();
  /* WebGPU exposes no device memory statistics — memory_statistics_get() → 0/0. */
  GCaps.mem_stats_support = false;
  /* No portable WebGPU device-extension enumeration; leave the extension table empty. */
  GCaps.extensions_len = 0;
  GCaps.extension_get = nullptr;

  /* Use the backend-agnostic frontend texture pool (texturepool_alloc returns
   * TexturePoolImpl), the same fallback the Vulkan backend selects. */
  GCaps.texture_pool_workaround = true;

#ifdef __EMSCRIPTEN__
  /* emdawnwebgpu WebGPU objects are per-thread JS handle-table entries — a wgpu::
   * Device/Buffer/Texture created on one worker is not usable from another. Blender's
   * existing "main context" workaround serialises all GPU resource creation onto the
   * main context/thread, which is exactly the guarantee WebGPU needs in the browser.
   * Off under native Dawn (a real cross-thread device), so this is Emscripten-only. */
  GCaps.use_main_context_workaround = true;
#endif
}

/* --- Sampler cache --------------------------------------------------------- */

static wgpu::AddressMode to_wgpu_address_mode(GPUSamplerExtendMode mode)
{
  switch (mode) {
    case GPU_SAMPLER_EXTEND_MODE_REPEAT:
      return wgpu::AddressMode::Repeat;
    case GPU_SAMPLER_EXTEND_MODE_MIRRORED_REPEAT:
      return wgpu::AddressMode::MirrorRepeat;
    case GPU_SAMPLER_EXTEND_MODE_EXTEND:
    case GPU_SAMPLER_EXTEND_MODE_CLAMP_TO_BORDER:
    default:
      /* WebGPU has no border-colour address mode; clamp-to-edge is the closest. */
      return wgpu::AddressMode::ClampToEdge;
  }
}

wgpu::Sampler WGPUContext::get_sampler(const GPUSamplerState &state)
{
  const uint32_t key = state.as_uint();
  auto it = sampler_cache_.find(key);
  if (it != sampler_cache_.end()) {
    return it->second;
  }

  /* Mirrors VKSampler::create (vk_sampler.cc). Defaults to point sampling; the
   * PARAMETERS / CUSTOM branches widen to linear / mipmap / compare. */
  wgpu::SamplerDescriptor d = {};
  d.addressModeU = to_wgpu_address_mode(state.extend_x);
  d.addressModeV = to_wgpu_address_mode(state.extend_yz);
  d.addressModeW = to_wgpu_address_mode(state.extend_yz);
  d.magFilter = wgpu::FilterMode::Nearest;
  d.minFilter = wgpu::FilterMode::Nearest;
  d.mipmapFilter = wgpu::MipmapFilterMode::Nearest;
  d.lodMinClamp = 0.0f;
  d.lodMaxClamp = 0.0f;
  d.maxAnisotropy = 1;

  if (state.type == GPU_SAMPLER_STATE_TYPE_CUSTOM) {
    if (state.custom_type == GPU_SAMPLER_CUSTOM_ICON) {
      d.magFilter = wgpu::FilterMode::Linear;
      d.minFilter = wgpu::FilterMode::Linear;
      d.mipmapFilter = wgpu::MipmapFilterMode::Nearest;
      d.lodMaxClamp = 1.0f;
    }
    else { /* GPU_SAMPLER_CUSTOM_COMPARE */
      d.magFilter = wgpu::FilterMode::Linear;
      d.minFilter = wgpu::FilterMode::Linear;
      d.compare = wgpu::CompareFunction::LessEqual;
    }
  }
  else { /* PARAMETERS (INTERNAL is treated as parameters here). */
    if (state.filtering & GPU_SAMPLER_FILTERING_LINEAR) {
      d.magFilter = wgpu::FilterMode::Linear;
      d.minFilter = wgpu::FilterMode::Linear;
    }
    if (state.filtering & GPU_SAMPLER_FILTERING_MIPMAP) {
      d.mipmapFilter = wgpu::MipmapFilterMode::Linear;
      d.lodMaxClamp = 1000.0f;
    }
  }

  wgpu::Sampler sampler = device_.CreateSampler(&d);
  sampler_cache_[key] = sampler;
  return sampler;
}

/* --- Dummy vertex buffer (unbound-attribute constant) ---------------------- */

wgpu::Buffer WGPUContext::dummy_vertex_buffer()
{
  if (dummy_vertex_buffer_ == nullptr) {
    wgpu::BufferDescriptor bd = {};
    /* Comfortable for the largest dummy stride (16 B) over a healthy instance count; an
     * Instance-stepped dummy on a non-instanced draw only ever reads element 0. WebGPU
     * zero-initialises buffer storage — exactly the constant an unbound attribute yields. */
    bd.size = 65536;
    bd.usage = wgpu::BufferUsage::Vertex | wgpu::BufferUsage::CopyDst;
    dummy_vertex_buffer_ = device_.CreateBuffer(&bd);
  }
  return dummy_vertex_buffer_;
}

/* --- Cross-format colour blit (render-pass fallback for blit_to) ----------- */

bool WGPUContext::blit_color_render(
    Texture *src, Texture *dst, uint32_t w, uint32_t h, uint32_t dst_x, uint32_t dst_y)
{
  if (src == nullptr || dst == nullptr || w == 0 || h == 0) {
    return false;
  }
  webgpu::WGPUTexture *wsrc = static_cast<webgpu::WGPUTexture *>(src);
  webgpu::WGPUTexture *wdst = static_cast<webgpu::WGPUTexture *>(dst);
  wgpu::TextureView src_view = wsrc->sampled_view();
  if (src_view == nullptr || wdst->texture() == nullptr) {
    return false;
  }
  const wgpu::TextureFormat dst_format = wdst->wgpu_format();

  /* Lazy: the shared fullscreen-triangle blit module. The region offscreen textures
   * this composites onto the window surface are stored bottom-up (the ADR-005 offscreen
   * clip-flip convention), while the window backbuffer is presented upright (M4.T14a), so
   * the blit samples with uv.y = y (NOT the straight-copy 1 - y): verified in-tab, the
   * straight copy renders the topbar/N-panel/properties strips upside-down, this sign
   * lands them upright to match the directly-drawn 3D viewport. */
  if (blit_module_ == nullptr) {
    static const char *kBlitWGSL =
        "struct VOut { @builtin(position) pos : vec4f, @location(0) uv : vec2f, };\n"
        "@vertex fn vs_main(@builtin(vertex_index) vid : u32) -> VOut {\n"
        "  var o : VOut;\n"
        "  let x = f32((vid << 1u) & 2u);\n"
        "  let y = f32(vid & 2u);\n"
        "  o.pos = vec4f(x * 2.0 - 1.0, y * 2.0 - 1.0, 0.0, 1.0);\n"
        "  o.uv = vec2f(x, y);\n"
        "  return o;\n"
        "}\n"
        "@group(0) @binding(0) var src_tex : texture_2d<f32>;\n"
        "@group(0) @binding(1) var src_smp : sampler;\n"
        "@fragment fn fs_main(i : VOut) -> @location(0) vec4f {\n"
        "  return textureSampleLevel(src_tex, src_smp, i.uv, 0.0);\n"
        "}\n";
    wgpu::ShaderSourceWGSL wgsl;
    wgsl.code = kBlitWGSL;
    wgpu::ShaderModuleDescriptor md;
    md.nextInChain = &wgsl;
    blit_module_ = device_.CreateShaderModule(&md);
  }
  if (blit_sampler_ == nullptr) {
    wgpu::SamplerDescriptor sd = {};
    sd.magFilter = wgpu::FilterMode::Nearest;
    sd.minFilter = wgpu::FilterMode::Nearest;
    sd.addressModeU = wgpu::AddressMode::ClampToEdge;
    sd.addressModeV = wgpu::AddressMode::ClampToEdge;
    blit_sampler_ = device_.CreateSampler(&sd);
  }

  /* Pipeline cached per destination format (auto layout — the module declares exactly
   * one sampled texture + one sampler in group 0). */
  const uint32_t fmt_key = uint32_t(dst_format);
  wgpu::RenderPipeline pipeline;
  auto found = blit_pipelines_.find(fmt_key);
  if (found != blit_pipelines_.end()) {
    pipeline = found->second;
  }
  else {
    wgpu::ColorTargetState target = {};
    target.format = dst_format;
    target.writeMask = wgpu::ColorWriteMask::All;
    wgpu::FragmentState fragment = {};
    fragment.module = blit_module_;
    fragment.entryPoint = "fs_main";
    fragment.targetCount = 1;
    fragment.targets = &target;
    wgpu::RenderPipelineDescriptor pd = {};
    pd.layout = nullptr;
    pd.vertex.module = blit_module_;
    pd.vertex.entryPoint = "vs_main";
    pd.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
    pd.fragment = &fragment;
    pipeline = device_.CreateRenderPipeline(&pd);
    blit_pipelines_[fmt_key] = pipeline;
  }
  if (pipeline == nullptr) {
    return false;
  }

  wgpu::BindGroupEntry entries[2] = {};
  entries[0].binding = 0;
  entries[0].textureView = src_view;
  entries[1].binding = 1;
  entries[1].sampler = blit_sampler_;
  wgpu::BindGroupDescriptor bgd = {};
  bgd.layout = pipeline.GetBindGroupLayout(0);
  bgd.entryCount = 2;
  bgd.entries = entries;
  wgpu::BindGroup bind_group = device_.CreateBindGroup(&bgd);

  wgpu::RenderPassColorAttachment ca = {};
  ca.view = wdst->texture().CreateView();
  ca.loadOp = wgpu::LoadOp::Load;
  ca.storeOp = wgpu::StoreOp::Store;
  wgpu::RenderPassDescriptor rp = {};
  rp.colorAttachmentCount = 1;
  rp.colorAttachments = &ca;

  wgpu::CommandEncoder enc = device_.CreateCommandEncoder();
  wgpu::RenderPassEncoder pass = enc.BeginRenderPass(&rp);
  pass.SetPipeline(pipeline);
  pass.SetViewport(float(dst_x), float(dst_y), float(w), float(h), 0.0f, 1.0f);
  pass.SetScissorRect(dst_x, dst_y, w, h);
  pass.SetBindGroup(0, bind_group);
  pass.Draw(3, 1, 0, 0);
  pass.End();
  wgpu::CommandBuffer cb = enc.Finish();
  queue_.Submit(1, &cb);
  return true;
}

wgpu::BindGroup WGPUContext::create_bind_group_checked(
    const wgpu::BindGroupLayout &layout, const std::vector<wgpu::BindGroupEntry> &entries)
{
  std::vector<wgpu::BindGroupEntry> valid;
  valid.reserve(entries.size());
  /* Duplicate-binding guard over the FULL binding range. The frontend can report two
   * resources for the same dense @binding on a workbench/overlay shader (a remap
   * coincidence between resource classes); Dawn then rejects the whole group with
   * "binding index N already used by a previous entry", dropping the draw. Keep the first
   * entry for each binding (the kind-specific guards in append_resource_bind_entries
   * already ensure it matches the layout kind) so the group stays valid and the pass
   * renders. NB: the sampler half of a combined texture lives at sampler_base (256) + n
   * and storage-image bindings sit higher still, so a fixed 64-entry window silently
   * missed them — the collision that dropped the workbench-solid + grid composite was at
   * binding 257 (a sampler). Track EVERY binding, not just the low dense range. */
  std::vector<uint32_t> seen_bindings;
  seen_bindings.reserve(entries.size());
  for (const wgpu::BindGroupEntry &e : entries) {
    /* An entry with no resource set is the null GPUBufferBinding that throws an
     * uncaught TypeError in createBindGroup and halts the render loop — drop it. */
    if (e.buffer == nullptr && e.textureView == nullptr && e.sampler == nullptr) {
      continue;
    }
    if (std::find(seen_bindings.begin(), seen_bindings.end(), e.binding) !=
        seen_bindings.end())
    {
      continue;
    }
    seen_bindings.push_back(e.binding);
    valid.push_back(e);
  }
  wgpu::BindGroupDescriptor bgd = {};
  bgd.layout = layout;
  bgd.entryCount = uint32_t(valid.size());
  bgd.entries = valid.data();
  return device_.CreateBindGroup(&bgd);
}

/* --- Draw/dispatch bind-group resource assembly ---------------------------- */

void WGPUContext::append_resource_bind_entries(WGPUShader *shader,
                                               std::vector<wgpu::BindGroupEntry> &entries)
{
  if (shader == nullptr) {
    return;
  }
  const webgpu::InterfaceMap &imap = shader->interface_map();
  /* Emit an entry only for a binding the shader's layout declares AND whose resource
   * kind matches: a resource left bound by a previous draw (stale texture/SSBO/UBO)
   * must not leak in, and a dense binding index reused across resource classes (e.g. a
   * UBO at the same index another shader used for a texture) must not be filled with
   * the wrong entry kind — both make CreateBindGroup reject the group. The kind is read
   * from the interface-map layout entry by comparing each sub-struct's discriminant to
   * a default entry (robust to WebGPU enum-naming: Undefined vs BindingNotUsed). */
  static const wgpu::BindGroupLayoutEntry kDefault = {};
  auto entry_of = [&](uint32_t binding) -> const wgpu::BindGroupLayoutEntry * {
    for (const wgpu::BindGroupLayoutEntry &e : imap.entries) {
      if (e.binding == binding) {
        return &e;
      }
    }
    return nullptr;
  };
  auto is_buffer_binding = [&](uint32_t b) {
    const wgpu::BindGroupLayoutEntry *e = entry_of(b);
    return e != nullptr && e->buffer.type != kDefault.buffer.type;
  };
  /* Buffer-KIND-specific guards. A dense binding is either a Uniform slot or a
   * Storage/ReadOnlyStorage slot -- never both -- so a UBO must never be placed on a
   * storage binding (Dawn: "Binding usage (Uniform) doesn't match expected usage
   * (Storage)") and a storage buffer must never land on a uniform binding. When two
   * resource classes remap onto the same dense index (the frontend reports colliding
   * bindings for a workbench/overlay shader), only the class matching the layout
   * entry's buffer.type is emitted -- this alone resolves both the UBO-on-Storage
   * usage error (console class 2) and the "binding index N already used" collision
   * (console class 3). */
  auto is_uniform_binding = [&](uint32_t b) {
    const wgpu::BindGroupLayoutEntry *e = entry_of(b);
    return e != nullptr && e->buffer.type == wgpu::BufferBindingType::Uniform;
  };
  auto is_storage_binding = [&](uint32_t b) {
    const wgpu::BindGroupLayoutEntry *e = entry_of(b);
    return e != nullptr && (e->buffer.type == wgpu::BufferBindingType::Storage ||
                            e->buffer.type == wgpu::BufferBindingType::ReadOnlyStorage);
  };
  (void)is_buffer_binding;
  auto is_texture_binding = [&](uint32_t b) {
    const wgpu::BindGroupLayoutEntry *e = entry_of(b);
    return e != nullptr && e->texture.sampleType != kDefault.texture.sampleType;
  };
  auto is_sampler_binding = [&](uint32_t b) {
    const wgpu::BindGroupLayoutEntry *e = entry_of(b);
    return e != nullptr && e->sampler.type != kDefault.sampler.type;
  };
  auto is_image_binding = [&](uint32_t b) {
    const wgpu::BindGroupLayoutEntry *e = entry_of(b);
    return e != nullptr && e->storageTexture.access != kDefault.storageTexture.access;
  };
  /* The caller adds the push-constant emulation UBO itself; a resource left bound at
   * that same dense binding by an earlier draw must not be re-added here (Dawn:
   * "binding index N already used"). */
  const bool has_pc = shader->has_push_constants();
  const uint32_t pc_binding = has_pc ? shader->push_constants_binding() : 0xffffffffu;
  auto is_pc = [&](uint32_t b) { return has_pc && b == pc_binding; };

  /* Bound uniform buffers (distinct from the push-constant emulation UBO, which the
   * caller adds explicitly). */
  for (const auto &item : bound_uniform_buffers_) {
    const uint32_t b = uint32_t(shader->remap_ubo_binding(item.first));
    if (is_pc(b) || !is_uniform_binding(b)) {
      continue;
    }
    WGPUUniformBuffer *ubo = item.second;
    if (ubo == nullptr) {
      continue;
    }
    const webgpu::Buffer &buf = ubo->buffer();
    if (!buf.valid()) {
      continue;
    }
    wgpu::BindGroupEntry e = {};
    e.binding = b;
    e.buffer = buf.handle();
    e.offset = 0;
    e.size = buf.size();
    entries.push_back(e);
  }

  /* Storage buffers (GPU_storagebuf_bind). */
  for (const auto &item : bound_storage_buffers_) {
    const uint32_t b = uint32_t(shader->remap_ssbo_binding(item.first));
    if (is_pc(b) || !is_storage_binding(b)) {
      continue;
    }
    WGPUStorageBuffer *ssbo = item.second;
    if (ssbo == nullptr) {
      continue;
    }
    const webgpu::Buffer &buf = ssbo->buffer();
    if (!buf.valid()) {
      continue;
    }
    wgpu::BindGroupEntry e = {};
    e.binding = b;
    e.buffer = buf.handle();
    e.offset = 0;
    e.size = buf.size();
    entries.push_back(e);
  }

  /* VBO / IBO bound as an SSBO, and buffer textures bound via bind_as_texture
   * (both recorded in the buffer-SSBO bind-space). */
  for (const auto &item : bound_buffer_ssbos_) {
    const uint32_t b = uint32_t(shader->remap_ssbo_binding(item.first));
    if (is_pc(b) || !is_storage_binding(b)) {
      continue;
    }
    const webgpu::Buffer *buf = item.second;
    if (buf == nullptr || !buf->valid()) {
      continue;
    }
    wgpu::BindGroupEntry e = {};
    e.binding = b;
    e.buffer = buf->handle();
    e.offset = 0;
    e.size = buf->size();
    entries.push_back(e);
  }

  WGPUStateManager *sm = static_cast<WGPUStateManager *>(state_manager);
  if (sm == nullptr) {
    return;
  }

  /* Storage images (GPU_texture_image_bind). */
  for (const auto &item : sm->bound_images()) {
    const uint32_t b = uint32_t(shader->remap_image_binding(item.first));
    if (!is_image_binding(b)) {
      continue;
    }
    webgpu::WGPUTexture *tex = static_cast<webgpu::WGPUTexture *>(item.second);
    if (tex == nullptr) {
      continue;
    }
    wgpu::TextureView view = tex->image_view();
    if (view == nullptr) {
      continue;
    }
    wgpu::BindGroupEntry e = {};
    e.binding = b;
    e.textureView = view;
    entries.push_back(e);
  }

  /* Sampled textures + their samplers (GPU_texture_bind). One combined sampler at
   * dense binding N splits into a texture half at N and a sampler half at
   * SAMPLER_BASE + N (notes/gpu-binding-map-spec.md §4.1). Buffer textures are a
   * storage-buffer entry, handled above — skip them here. */
  const uint32_t sampler_base = imap.sampler_base;
  for (const auto &item : sm->bound_textures()) {
    const uint32_t n = uint32_t(shader->remap_sampler_binding(item.first));
    webgpu::WGPUTexture *tex = static_cast<webgpu::WGPUTexture *>(item.second.texture);
    if (tex == nullptr || tex->is_buffer_texture()) {
      continue;
    }
    if (is_texture_binding(n)) {
      /* Bind the view at the dimension the shader declares (not the texture's native
       * type) so a DRW array-dummy on a texture_2d slot does not mismatch the layout. */
      const wgpu::BindGroupLayoutEntry *le = entry_of(n);
      wgpu::TextureView view = tex->sampled_view(
          le != nullptr ? le->texture.viewDimension : wgpu::TextureViewDimension::Undefined);
      if (view != nullptr) {
        wgpu::BindGroupEntry e = {};
        e.binding = n;
        e.textureView = view;
        entries.push_back(e);
      }
    }
    const uint32_t sb = sampler_base + n;
    if (is_sampler_binding(sb)) {
      wgpu::Sampler sampler = get_sampler(item.second.sampler);
      if (sampler != nullptr) {
        wgpu::BindGroupEntry e = {};
        e.binding = sb;
        e.sampler = sampler;
        entries.push_back(e);
      }
    }
  }

}

/* --- Window back-buffer sync (web windowed only) --------------------------- */

void WGPUContext::sync_backbuffer()
{
#if defined(__EMSCRIPTEN__) && !defined(WITH_HEADLESS)
  /* Only the window context has a GHOST window + a configured surface; offscreen
   * (GPU_offscreen) contexts and the M3 headless/native builds take no action. */
  if (ghost_window_ == nullptr || ghost_context_ == nullptr) {
    return;
  }
  WGPUGhostContext *wgpu_ghost = static_cast<WGPUGhostContext *>(ghost_context_);
  /* M4.T21 present seam: adopt the GHOST context's PERSISTENT offscreen back-buffer as
   * back_left/front_left, NOT the surface's per-frame GetCurrentTexture(). The transient
   * surface texture is destroyed by the browser on event-loop yield, so any draw/composite
   * command buffer that outlives the rAF tick submitted a destroyed texture ("Destroyed
   * texture … WebgpuSwapChainTexture used in a submit", 725x/boot). The offscreen has NO
   * per-frame lifetime, so that whole family is eliminated by construction; GHOST blits it
   * onto the real surface as the last op of each frame (presentBackbuffer in
   * swapBufferRelease). */
  wgpu::Texture backbuffer = wgpu_ghost->getBackbufferTexture();
  if (backbuffer == nullptr) {
    return; /* surface not configured yet (canvas unresolved / pre-first-configure) */
  }
  const int w = int(backbuffer.GetWidth());
  const int h = int(backbuffer.GetHeight());
  const wgpu::TextureFormat fmt = wgpu_ghost->getSurfaceFormat();

  const bool first = (surface_texture_ == nullptr);
  webgpu::WGPUTexture *back;
  if (first) {
    back = new webgpu::WGPUTexture("back_left_backbuffer");
    surface_texture_ = back;
  }
  else {
    back = static_cast<webgpu::WGPUTexture *>(surface_texture_);
  }
  /* Re-adopt each activate: the offscreen handle only changes on resize (GHOST recreates
   * it at the new extent), and re-adopting refreshes the wrapped texture + size in place
   * while the attachment keeps pointing at this same WGPUTexture wrapper. */
  back->adopt_external(backbuffer, fmt, w, h);

  if (first) {
    if (back_left != nullptr) {
      back_left->attachment_set(GPU_FB_COLOR_ATTACHMENT0, GPU_ATTACHMENT_TEXTURE(surface_texture_));
    }
    if (front_left != nullptr) {
      front_left->attachment_set(GPU_FB_COLOR_ATTACHMENT0,
                                 GPU_ATTACHMENT_TEXTURE(surface_texture_));
    }
  }
#endif
}

bool WGPUContext::is_window_backbuffer(const FrameBuffer *fb) const
{
  /* back_left/front_left get the surface's current texture in sync_backbuffer (web
   * windowed only). No surface -> no window backbuffer, so the native/headless gpu
   * build always reports false and keeps the ADR-005 offscreen convention untouched. */
  return surface_texture_ != nullptr && (fb == back_left || fb == front_left);
}

/* --- Frame machinery: no-ops until the render pipeline lands (T10/lane B). - */
void WGPUContext::begin_frame() {}
void WGPUContext::end_frame() {}
void WGPUContext::flush() {}
void WGPUContext::finish() {}

void WGPUContext::memory_statistics_get(int *r_total_mem, int *r_free_mem)
{
  *r_total_mem = 0;
  *r_free_mem = 0;
}

bool WGPUContext::debug_capture_begin(const char * /*title*/)
{
  return false;
}
void WGPUContext::debug_capture_end() {}
void *WGPUContext::debug_capture_scope_create(const char * /*name*/)
{
  return nullptr;
}
bool WGPUContext::debug_capture_scope_begin(void * /*scope*/)
{
  return false;
}
void WGPUContext::debug_capture_scope_end(void * /*scope*/) {}
void WGPUContext::debug_unbind_all_ubo() {}
void WGPUContext::debug_unbind_all_ssbo() {}

}  // namespace blender::gpu
