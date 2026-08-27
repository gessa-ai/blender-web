/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm parity contract for the canonical in-tree WebGPU
 * render-pipeline enum mappings. No instance, adapter, device, or pipeline is
 * created; live descriptor validation remains part of the hardware-gated M3
 * replay. */

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdio>
#include <functional>
#include <limits>
#include <memory>
#include <unordered_set>

#ifndef BW_WGPU_PIPELINE_SOURCE
#  error "BW_WGPU_PIPELINE_SOURCE must name the canonical wgpu_pipeline.cc"
#endif
#ifndef BW_GHOST_PRESENT_TRANSACTION_HEADER
#  error "BW_GHOST_PRESENT_TRANSACTION_HEADER must name the shipping GHOST transaction header"
#endif
#ifndef BW_GHOST_DISPLAY_STATE_HEADER
#  error "BW_GHOST_DISPLAY_STATE_HEADER must name the shipping web display-state header"
#endif

/* The dummy-binding helper intentionally has internal linkage. Including the
 * canonical translation unit keeps this contract on the shipping vertex plan. */
#include BW_WGPU_PIPELINE_SOURCE
#include BW_GHOST_PRESENT_TRANSACTION_HEADER
#include BW_GHOST_DISPLAY_STATE_HEADER

namespace bw = blender::gpu::webgpu;
namespace gw = ghost_web;

namespace {

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    return false;
  }
  return true;
}

class BufferHandleProbe {
 public:
  BufferHandleProbe() = default;
  explicit BufferHandleProbe(const int identity, const bool map_success = true)
      : identity_(identity), state_(std::make_shared<State>())
  {
    state_->map_success = map_success;
  }

  bool operator==(std::nullptr_t) const
  {
    return identity_ == 0;
  }

  int identity() const
  {
    return identity_;
  }

  void *GetMappedRange(const uint64_t offset, const size_t size)
  {
    state_->map_calls++;
    state_->mapped_offset = offset;
    state_->mapped_size = size;
    return state_->map_success ? state_->values.data() : nullptr;
  }

  void Unmap()
  {
    state_->unmap_calls++;
  }

  int map_calls() const
  {
    return state_ ? state_->map_calls : 0;
  }

  int unmap_calls() const
  {
    return state_ ? state_->unmap_calls : 0;
  }

  uint64_t mapped_offset() const
  {
    return state_ ? state_->mapped_offset : 0;
  }

  size_t mapped_size() const
  {
    return state_ ? state_->mapped_size : 0;
  }

  float value(const size_t index) const
  {
    return state_ ? state_->values.at(index) : 0.0f;
  }

 private:
  struct State {
    bool map_success = true;
    int map_calls = 0;
    int unmap_calls = 0;
    uint64_t mapped_offset = 0;
    size_t mapped_size = 0;
    std::array<float, 4> values = {};
  };

  int identity_ = 0;
  std::shared_ptr<State> state_;
};

class BufferDeviceProbe {
 public:
  explicit BufferDeviceProbe(const bool create_success, const bool map_success = true)
      : create_success_(create_success), map_success_(map_success)
  {
  }

  BufferHandleProbe CreateBuffer(const wgpu::BufferDescriptor *descriptor)
  {
    create_calls_++;
    descriptor_present_ = descriptor != nullptr;
    if (descriptor != nullptr) {
      size_ = descriptor->size;
      usage_ = descriptor->usage;
      mapped_at_creation_ = descriptor->mappedAtCreation;
    }
    last_handle_ = create_success_ ? BufferHandleProbe(29, map_success_) : BufferHandleProbe();
    return last_handle_;
  }

  size_t create_calls() const
  {
    return create_calls_;
  }

  bool descriptor_present() const
  {
    return descriptor_present_;
  }

  uint64_t size() const
  {
    return size_;
  }

  wgpu::BufferUsage usage() const
  {
    return usage_;
  }

  bool mapped_at_creation() const
  {
    return mapped_at_creation_;
  }

  const BufferHandleProbe &last_handle() const
  {
    return last_handle_;
  }

 private:
  bool create_success_ = false;
  bool map_success_ = true;
  bool descriptor_present_ = false;
  size_t create_calls_ = 0;
  uint64_t size_ = 0;
  wgpu::BufferUsage usage_ = wgpu::BufferUsage::None;
  bool mapped_at_creation_ = false;
  BufferHandleProbe last_handle_;
};

bool multiview_uniform_allocation_contract()
{
  constexpr wgpu::BufferUsage expected_usage =
      wgpu::BufferUsage::Uniform | wgpu::BufferUsage::CopyDst;

  BufferDeviceProbe failing_device(false);
  BufferHandleProbe failed_output(7);
  if (!require(!bw::multi_viewport_uniform_buffer_create(failing_device, failed_output),
               "failed multi-viewport allocation is rejected") ||
      !require(failed_output.identity() == 7,
               "failed multi-viewport allocation preserves output") ||
      !require(failing_device.create_calls() == 1 && failing_device.descriptor_present() &&
                   failing_device.size() == 16 && failing_device.usage() == expected_usage &&
                   !failing_device.mapped_at_creation(),
               "failed multi-viewport allocation uses the exact descriptor"))
  {
    return false;
  }

  BufferDeviceProbe successful_device(true);
  BufferHandleProbe successful_output(11);
  if (!require(bw::multi_viewport_uniform_buffer_create(successful_device, successful_output),
               "successful multi-viewport allocation is accepted") ||
      !require(successful_output.identity() == 29,
               "successful multi-viewport allocation publishes the candidate") ||
      !require(successful_device.create_calls() == 1 && successful_device.descriptor_present() &&
                   successful_device.size() == 16 &&
                   successful_device.usage() == expected_usage &&
                   !successful_device.mapped_at_creation(),
               "successful multi-viewport allocation uses the exact descriptor"))
  {
    return false;
  }

  std::puts(
      "CONTRACT multiview_uniform_allocation PASS cases=2 creates=2 failure=atomic bytes=16");
  return true;
}

bool dummy_vertex_buffer_creation_contract()
{
  constexpr wgpu::BufferUsage expected_usage =
      wgpu::BufferUsage::Vertex | wgpu::BufferUsage::CopyDst;

  BufferDeviceProbe create_failure(false);
  const BufferHandleProbe missing = bw::dummy_vertex_buffer_create(create_failure);
  if (!require(missing == nullptr, "failed dummy allocation is rejected") ||
      !require(create_failure.create_calls() == 1 && create_failure.descriptor_present() &&
                   create_failure.size() == 16 && create_failure.usage() == expected_usage &&
                   create_failure.mapped_at_creation(),
               "failed dummy allocation uses the exact mapped descriptor"))
  {
    return false;
  }

  BufferDeviceProbe map_failure(true, false);
  const BufferHandleProbe unmapped = bw::dummy_vertex_buffer_create(map_failure);
  if (!require(unmapped == nullptr, "missing dummy mapped range is rejected") ||
      !require(map_failure.last_handle().map_calls() == 1 &&
                   map_failure.last_handle().unmap_calls() == 0 &&
                   map_failure.last_handle().mapped_offset() == 0 &&
                   map_failure.last_handle().mapped_size() == 16,
               "failed dummy mapping stops before unmap and publication"))
  {
    return false;
  }

  BufferDeviceProbe success(true);
  const BufferHandleProbe initialized = bw::dummy_vertex_buffer_create(success);
  if (!require(initialized.identity() == 29, "valid dummy allocation is published") ||
      !require(initialized.map_calls() == 1 && initialized.unmap_calls() == 1 &&
                   initialized.mapped_offset() == 0 && initialized.mapped_size() == 16,
               "valid dummy allocation maps and unmaps exactly once") ||
      !require(initialized.value(0) == 0.0f && initialized.value(1) == 0.0f &&
                   initialized.value(2) == 0.0f && initialized.value(3) == 1.0f,
               "dummy allocation contains Blender's default vertex attribute"))
  {
    return false;
  }

  std::puts(
      "CONTRACT dummy_vertex_buffer_creation PASS cases=3 create_fail=closed map_fail=closed values=0,0,0,1");
  return true;
}

class CacheHandleProbe {
 public:
  CacheHandleProbe() = default;
  explicit CacheHandleProbe(const int identity) : identity_(identity) {}

  bool operator==(std::nullptr_t) const
  {
    return identity_ == 0;
  }

  int identity() const
  {
    return identity_;
  }

 private:
  int identity_ = 0;
};

bool transient_handle_publication_contract()
{
  CacheHandleProbe output(31);
  if (!require(!bw::transient_handle_publish_if_valid(CacheHandleProbe(), output),
               "null transient handle is rejected") ||
      !require(output.identity() == 31, "failed transient publication preserves output"))
  {
    return false;
  }

  if (!require(bw::transient_handle_publish_if_valid(CacheHandleProbe(73), output),
               "valid transient handle is accepted") ||
      !require(output.identity() == 73, "valid transient handle is published"))
  {
    return false;
  }

  std::puts(
      "CONTRACT transient_handle_publication PASS attempts=2 failure=atomic success=published");
  return true;
}

bool bind_group_completeness_contract()
{
  const std::vector<uint32_t> empty;
  const std::vector<uint32_t> complete_expected = {3, 12, 13, 257};
  const std::vector<uint32_t> complete_assembled = {257, 13, 3, 12};
  const std::vector<uint32_t> duplicate_assembled = {13, 3, 257, 12, 13};
  const std::vector<uint32_t> partial_assembled = {3, 12, 257};
  const std::vector<uint32_t> extra_assembled = {3, 12, 13, 42, 257};

  if (!require(bw::bind_group_binding_ids_complete(empty, empty),
               "genuinely empty bind-group layout is complete") ||
      !require(bw::bind_group_binding_ids_complete(complete_expected, complete_assembled),
               "complete bind-group IDs are order-independent") ||
      !require(bw::bind_group_binding_ids_complete(complete_expected, duplicate_assembled),
               "assembled bind-group IDs are compared as a unique set") ||
      !require(!bw::bind_group_binding_ids_complete(complete_expected, empty),
               "required-but-empty bind group is rejected") ||
      !require(!bw::bind_group_binding_ids_complete(complete_expected, partial_assembled),
               "partial bind group is rejected") ||
      !require(!bw::bind_group_binding_ids_complete(complete_expected, extra_assembled),
               "bind group with an undeclared extra binding is rejected"))
  {
    return false;
  }

  std::puts(
      "CONTRACT bind_group_completeness PASS cases=6 accepted=3 rejected=3 internal=2 unique=deduplicated");
  return true;
}

bool framebuffer_load_action_commit_contract()
{
  blender::GPULoadOp load_action = blender::GPU_LOADACTION_CLEAR;
  int attempts = 0;

  if (!require(
          !bw::framebuffer_load_action_commit_if_valid(
              [&]() {
                attempts++;
                return false;
              },
              blender::GPU_LOADACTION_LOAD,
              load_action),
          "failed layered load clear is rejected") ||
      !require(load_action == blender::GPU_LOADACTION_CLEAR,
               "failed layered load clear remains pending") ||
      !require(attempts == 1, "failed layered load clear attempts once"))
  {
    return false;
  }

  if (!require(
          bw::framebuffer_load_action_commit_if_valid(
              [&]() {
                attempts++;
                return true;
              },
              blender::GPU_LOADACTION_LOAD,
              load_action),
          "successful layered load clear is accepted") ||
      !require(load_action == blender::GPU_LOADACTION_LOAD,
               "successful layered load clear is committed") ||
      !require(attempts == 2, "layered load clear retry census"))
  {
    return false;
  }

  std::puts(
      "CONTRACT framebuffer_load_action_commit PASS cases=2 failure=pending retry=committed");
  return true;
}

bool framebuffer_load_action_transaction_contract()
{
  bw::FramebufferLoadActionTracker tracker;
  tracker.record(2u, true);
  tracker.record(5u, true);

  auto late_view = tracker.transaction();
  if (!require(late_view->stage(2u), "first clear attachment is staged") ||
      !require(tracker.requires_clear(2u) && tracker.requires_clear(5u),
               "staging preserves both logical clear actions"))
  {
    return false;
  }
  late_view->complete(false);
  if (!require(tracker.requires_clear(2u) && tracker.requires_clear(5u),
               "late attachment-view failure preserves every clear"))
  {
    return false;
  }

  auto late_bind = tracker.transaction();
  if (!require(late_bind->stage(2u) && late_bind->stage(5u),
               "retry stages both clear attachments"))
  {
    return false;
  }
  auto same_epoch = tracker.transaction();
  if (!require(!same_epoch->stage(2u) && !same_epoch->stage(5u),
               "later same-epoch passes load behind the staged clear"))
  {
    return false;
  }
  late_bind->complete(false);
  same_epoch->complete(false);
  if (!require(tracker.requires_clear(2u) && tracker.requires_clear(5u),
               "late bind failure releases both clear reservations"))
  {
    return false;
  }

  auto accepted = tracker.transaction();
  if (!require(accepted->stage(2u) && accepted->stage(5u),
               "clean retry restages both clear attachments"))
  {
    return false;
  }
  accepted->complete(true);
  if (!require(!tracker.requires_clear(2u) && !tracker.requires_clear(5u),
               "successful submission commits both clears to load"))
  {
    return false;
  }

  tracker.record(7u, true);
  auto superseded = tracker.transaction();
  if (!require(superseded->stage(7u), "old generation stages once")) {
    return false;
  }
  tracker.record(7u, true);
  auto replacement = tracker.transaction();
  if (!require(replacement->stage(7u), "replacement generation can stage independently")) {
    return false;
  }
  superseded->complete(true);
  if (!require(tracker.requires_clear(7u),
               "stale successful completion cannot consume a replacement clear"))
  {
    return false;
  }
  replacement->complete(true);
  if (!require(!tracker.requires_clear(7u), "matching replacement completion commits")) {
    return false;
  }

  std::puts(
      "CONTRACT framebuffer_load_action_transaction PASS cases=6 attachments=3 late_view=pending late_bind=pending same_epoch=load retry=committed generation=isolated");
  return true;
}

bool framebuffer_layered_clear_order_contract()
{
  struct OrderCase {
    bool clear_valid;
    bool draw_valid;
    bool replace_generation;
    const char *expected_order;
    bool expected_pending;
  };
  constexpr std::array<OrderCase, 4> cases = {{{true, true, false, "CD", false},
                                                {false, true, false, "CX", true},
                                                {true, false, false, "CD", true},
                                                {true, true, true, "CD", true}}};

  int clear_operations = 0;
  int draw_operations = 0;
  int canceled_draws = 0;
  int load_observations = 0;

  for (const OrderCase &test : cases) {
    bw::FramebufferLoadActionTracker tracker;
    tracker.record(4u, true);
    auto transaction = tracker.transaction();
    if (!require(transaction->stage(4u), "layered clear generation stages before scheduling")) {
      return false;
    }

    bw::FramebufferLoadActionCompletionGroup completions(transaction, 2u);
    std::function<void(bool)> clear_complete = completions.completion();
    std::function<void(bool)> draw_complete = completions.completion();

    auto load_observer = tracker.transaction();
    if (!require(!load_observer->stage(4u),
                 "dependent draw observes the staged all-layer clear as load"))
    {
      return false;
    }
    load_observations++;
    load_observer->complete(false);

    bw::OrderedQueueScheduler scheduler;
    bw::OrderedQueueScheduler::Ticket leading_ticket;
    if (test.replace_generation) {
      leading_ticket = scheduler.reserve();
    }
    std::string order;
    bool draw_saw_pending = false;
    scheduler.enqueue([&](std::function<void(bool)> done) {
      order += 'C';
      clear_operations++;
      clear_complete(test.clear_valid);
      /* One helper can report a synchronous failure and later release its retained callback.
       * The per-operation completion must be idempotent. */
      clear_complete(test.clear_valid);
      done(test.clear_valid);
    });
    scheduler.enqueue(
        [&](std::function<void(bool)> done) {
          order += 'D';
          draw_operations++;
          draw_saw_pending = tracker.requires_clear(4u);
          draw_complete(test.draw_valid);
          done(test.draw_valid);
        },
        [&]() {
          order += 'X';
          canceled_draws++;
          draw_complete(false);
        });

    std::shared_ptr<bw::FramebufferLoadActionTransaction> replacement;
    if (test.replace_generation) {
      tracker.record(4u, true);
      replacement = tracker.transaction();
      if (!require(replacement->stage(4u),
                   "replacement generation stages independently while old work waits"))
      {
        return false;
      }
      leading_ticket.resolve([](std::function<void(bool)> done) { done(true); });
    }

    if (!require(order == test.expected_order, "layered clear precedes dependent draw") ||
        !require(scheduler.pending_count() == 0, "layered clear scheduler drains") ||
        !require(draw_operations + canceled_draws == clear_operations,
                 "each layered clear has one dependent draw outcome") ||
        !require(order == "CX" || draw_saw_pending,
                 "executed draw retains the shared generation until validation") ||
        !require(tracker.requires_clear(4u) == test.expected_pending,
                 "layered clear commits only after both operations accept"))
    {
      return false;
    }

    if (replacement) {
      replacement->complete(true);
      if (!require(!tracker.requires_clear(4u),
                   "matching replacement completion commits its own generation"))
      {
        return false;
      }
    }
  }

  if (!require(clear_operations == 4 && draw_operations == 3 && canceled_draws == 1 &&
                   load_observations == 4,
               "layered clear ordering census"))
  {
    return false;
  }

  std::puts(
      "CONTRACT framebuffer_layered_clear_order PASS cases=4 clears=4 draws=3 canceled=1 loads=4 committed=1 rollback=2 generation=isolated");
  return true;
}

bool vertex_buffer_handle_resolution_contract()
{
  const std::array<int, 3> bindings = {11, 22, 33};

  std::vector<CacheHandleProbe> failed_output = {CacheHandleProbe(97)};
  int failed_resolves = 0;
  if (!require(
          !bw::vertex_buffer_handles_resolve_if_valid(
              bindings,
              [&](const int binding) {
                failed_resolves++;
                return binding == 22 ? CacheHandleProbe() : CacheHandleProbe(binding);
              },
              failed_output),
          "missing planned vertex buffer is rejected") ||
      !require(failed_resolves == 2, "planned vertex resolution fails fast") ||
      !require(failed_output.size() == 1 && failed_output[0].identity() == 97,
               "failed planned vertex resolution preserves output"))
  {
    return false;
  }

  std::vector<CacheHandleProbe> successful_output = {CacheHandleProbe(101)};
  int successful_resolves = 0;
  if (!require(
          bw::vertex_buffer_handles_resolve_if_valid(
              bindings,
              [&](const int binding) {
                successful_resolves++;
                return CacheHandleProbe(binding);
              },
              successful_output),
          "complete planned vertex buffers are accepted") ||
      !require(successful_resolves == 3 && successful_output.size() == 3,
               "complete planned vertex resolution census") ||
      !require(successful_output[0].identity() == 11 &&
                   successful_output[1].identity() == 22 &&
                   successful_output[2].identity() == 33,
               "complete planned vertex buffers publish in slot order"))
  {
    return false;
  }

  const std::array<int, 0> empty_bindings = {};
  std::vector<CacheHandleProbe> empty_output = {CacheHandleProbe(103)};
  if (!require(
          bw::vertex_buffer_handles_resolve_if_valid(
              empty_bindings,
              [](const int binding) { return CacheHandleProbe(binding); },
              empty_output),
          "procedural draw with no vertex buffers is accepted") ||
      !require(empty_output.empty(), "empty planned vertex resolution publishes empty output"))
  {
    return false;
  }

  std::puts(
      "CONTRACT vertex_buffer_handle_resolution PASS cases=3 resolved=5 failure=atomic order=stable");
  return true;
}

bool index_buffer_handle_resolution_contract()
{
  CacheHandleProbe missing_output(97);
  if (!require(
          !bw::index_buffer_handle_resolve_if_required(
              true, CacheHandleProbe(), missing_output),
          "missing required index buffer is rejected") ||
      !require(missing_output.identity() == 97,
               "failed required index resolution preserves output"))
  {
    return false;
  }

  CacheHandleProbe unindexed_output(101);
  if (!require(
          bw::index_buffer_handle_resolve_if_required(
              false, CacheHandleProbe(53), unindexed_output),
          "non-indexed draw is accepted") ||
      !require(unindexed_output == nullptr,
               "non-indexed resolution publishes an empty handle"))
  {
    return false;
  }

  CacheHandleProbe indexed_output(103);
  if (!require(
          bw::index_buffer_handle_resolve_if_required(
              true, CacheHandleProbe(59), indexed_output),
          "valid required index buffer is accepted") ||
      !require(indexed_output.identity() == 59,
               "valid required index buffer is published"))
  {
    return false;
  }

  std::puts(
      "CONTRACT index_buffer_handle_resolution PASS cases=3 required=2 failure=atomic optional=empty");
  return true;
}

struct ShaderModuleSetProbe {
  CacheHandleProbe vertex;
  CacheHandleProbe fragment;
  CacheHandleProbe compute;

  bool operator==(std::nullptr_t) const
  {
    return vertex == nullptr && fragment == nullptr && compute == nullptr;
  }

  bool operator!=(std::nullptr_t) const
  {
    return !(*this == nullptr);
  }
};

bool shader_module_set_cache_contract()
{
  bw::ScopedHandleCache<uint8_t, ShaderModuleSetProbe> cache;
  std::function<void(bool)> settle;
  int creates = 0;

  ShaderModuleSetProbe modules = cache.get_or_create_scoped(
      uint8_t(0),
      []() {},
      [&]() {
        creates++;
        return ShaderModuleSetProbe{
            CacheHandleProbe(11), CacheHandleProbe(13), CacheHandleProbe()};
      },
      [&](auto completion) { settle = std::move(completion); });
  if (!require(modules == nullptr && cache.pending(uint8_t(0)) && cache.size() == 0,
               "shader module set remains unpublished while validation is pending") ||
      !require(creates == 1 && bool(settle), "shader module set begins one scoped creation"))
  {
    return false;
  }

  settle(false);
  if (!require(!cache.pending(uint8_t(0)) && cache.size() == 0,
               "rejected non-null module set remains unpublished"))
  {
    return false;
  }

  modules = cache.get_or_create_scoped(
      uint8_t(0),
      []() {},
      [&]() {
        creates++;
        return ShaderModuleSetProbe{
            CacheHandleProbe(17), CacheHandleProbe(19), CacheHandleProbe()};
      },
      [](auto completion) { completion(true); });
  if (!require(modules.vertex.identity() == 17 && modules.fragment.identity() == 19 &&
                   modules.compute == nullptr && cache.size() == 1 && creates == 2,
               "clean shader module retry publishes the complete required set"))
  {
    return false;
  }

  const ShaderModuleSetProbe stable = cache.get_or_create_scoped(
      uint8_t(0),
      []() {},
      [&]() {
        creates++;
        return ShaderModuleSetProbe{
            CacheHandleProbe(23), CacheHandleProbe(29), CacheHandleProbe()};
      },
      [](auto completion) { completion(true); });
  if (!require(stable.vertex.identity() == 17 && stable.fragment.identity() == 19 && creates == 2,
               "accepted shader module set remains stable without recreation"))
  {
    return false;
  }

  std::puts("CONTRACT shader_module_set_cache PASS cases=4 creates=2 "
            "error_object=rejected retry=atomic stable=preserved");
  return true;
}

bool scoped_handle_cache_contract()
{
  bw::ScopedHandleCache<uint32_t, CacheHandleProbe> cache;
  std::function<void(bool)> settle;
  int scope_begins = 0;
  int scope_ends = 0;
  int creates = 0;

  CacheHandleProbe result = cache.get_or_create_scoped(
      7u,
      [&]() { scope_begins++; },
      [&]() {
        creates++;
        return CacheHandleProbe(41);
      },
      [&](auto completion) {
        scope_ends++;
        settle = std::move(completion);
      });
  if (!require(result == nullptr && cache.size() == 0 && cache.pending(7u),
               "scoped cache keeps candidate unpublished while validation is pending") ||
      !require(scope_begins == 1 && scope_ends == 1 && creates == 1 && bool(settle),
               "scoped cache begins and ends one creation scope"))
  {
    return false;
  }

  result = cache.get_or_create_scoped(
      7u,
      [&]() { scope_begins++; },
      [&]() {
        creates++;
        return CacheHandleProbe(43);
      },
      [&](auto completion) {
        scope_ends++;
        completion(true);
      });
  if (!require(result == nullptr && scope_begins == 1 && scope_ends == 1 && creates == 1,
               "scoped cache deduplicates a pending key"))
  {
    return false;
  }

  settle(false);
  if (!require(cache.size() == 0 && !cache.pending(7u),
               "non-null error object remains uncached after scope rejection"))
  {
    return false;
  }

  result = cache.get_or_create_scoped(
      7u,
      [&]() { scope_begins++; },
      [&]() {
        creates++;
        return CacheHandleProbe(73);
      },
      [&](auto completion) {
        scope_ends++;
        completion(true);
      });
  if (!require(result.identity() == 73 && cache.size() == 1 && !cache.pending(7u),
               "clean retry publishes the scoped cache candidate") ||
      !require(scope_begins == 2 && scope_ends == 2 && creates == 2,
               "scoped cache retry creation census"))
  {
    return false;
  }

  result = cache.get_or_create_scoped(
      7u,
      [&]() { scope_begins++; },
      [&]() {
        creates++;
        return CacheHandleProbe(79);
      },
      [&](auto completion) {
        scope_ends++;
        completion(true);
      });
  if (!require(result.identity() == 73 && scope_begins == 2 && scope_ends == 2 && creates == 2,
               "scoped cache hit preserves the accepted handle without recreation"))
  {
    return false;
  }

  std::puts("CONTRACT scoped_handle_cache PASS cases=5 creates=2 pending=deduplicated "
            "error_object=rejected retry=published");
  return true;
}

bool ordered_scoped_handle_cache_contract()
{
  bw::ScopedHandleCache<uint32_t, CacheHandleProbe> cache;
  bw::OrderedQueueScheduler scheduler;
  std::function<void(bool)> settle;
  int creates = 0;
  int dependent = 0;
  int canceled = 0;

  auto fetch = [&](const int identity) {
    return cache.get_or_create_ordered(
        9u,
        scheduler,
        []() {},
        [&]() {
          creates++;
          return CacheHandleProbe(identity);
        },
        [&](auto completion) { settle = std::move(completion); });
  };

  const CacheHandleProbe provisional = fetch(41);
  scheduler.enqueue(
      [&](auto done) {
        dependent++;
        done(true);
      },
      [&]() { canceled++; });
  const CacheHandleProbe same_epoch = fetch(43);
  if (!require(provisional.identity() == 41 && same_epoch.identity() == 41 && creates == 1,
               "ordered cache reuses its provisional handle within the reserving epoch") ||
      !require(cache.size() == 0 && cache.pending(9u) && scheduler.pending_count() == 2,
               "ordered cache keeps provisional work behind one validation gate"))
  {
    return false;
  }

  scheduler.begin_epoch();
  const CacheHandleProbe later_epoch = fetch(47);
  if (!require(later_epoch.identity() == 41 && creates == 1 && scheduler.pending_count() == 3,
               "ordered cache gates provisional reuse separately in a later epoch"))
  {
    return false;
  }
  settle(false);
  if (!require(cache.size() == 0 && !cache.pending(9u) && dependent == 0 && canceled == 1,
               "ordered cache rejection cancels dependent work and leaves a clean retry"))
  {
    return false;
  }

  scheduler.begin_epoch();
  const CacheHandleProbe retry = fetch(73);
  scheduler.enqueue([&](auto done) {
    dependent++;
    done(true);
  });
  settle(true);
  scheduler.begin_epoch();
  const CacheHandleProbe accepted = fetch(79);
  if (!require(retry.identity() == 73 && accepted.identity() == 73 && creates == 2,
               "ordered cache publishes a clean retry for later epochs") ||
      !require(cache.size() == 1 && !cache.pending(9u) && dependent == 1 && canceled == 1 &&
                   scheduler.pending_count() == 0,
               "ordered cache drains accepted and rejected dependencies exactly once"))
  {
    return false;
  }

  std::puts("CONTRACT ordered_scoped_handle_cache PASS cases=5 creates=2 "
            "same_epoch=provisional later_epoch=gated rejection=canceled retry=published");
  return true;
}

bool context_owned_pipeline_cache_contract()
{
  using Cache = bw::ScopedHandleCache<uint8_t, CacheHandleProbe>;
  const auto fetch = [](Cache &cache, const int identity, int &creates) {
    return cache.get_or_create_scoped(
        uint8_t(0),
        []() {},
        [&]() {
          creates++;
          return CacheHandleProbe(identity);
        },
        [](auto completion) { completion(true); });
  };

  /* Reproduce the old process-static ownership: a later device asks the same
   * logical pipeline key and receives the first device's retained handle. */
  Cache process_static;
  int process_creates = 0;
  const CacheHandleProbe first_device = fetch(process_static, 11, process_creates);
  const CacheHandleProbe stale_second_device = fetch(process_static, 13, process_creates);
  if (!require(first_device.identity() == 11 && stale_second_device.identity() == 11 &&
                   process_creates == 1,
               "process-static pipeline cache reproduces cross-device handle reuse"))
  {
    return false;
  }

  struct ContextCaches {
    Cache batch;
    Cache immediate;
    Cache indexed_fan;
  };
  std::array<int, 3> first_context = {};
  std::array<int, 3> second_context = {};
  int context_creates = 0;
  {
    ContextCaches caches;
    first_context = {fetch(caches.batch, 21, context_creates).identity(),
                     fetch(caches.immediate, 23, context_creates).identity(),
                     fetch(caches.indexed_fan, 25, context_creates).identity()};
  }
  {
    ContextCaches caches;
    second_context = {fetch(caches.batch, 31, context_creates).identity(),
                      fetch(caches.immediate, 33, context_creates).identity(),
                      fetch(caches.indexed_fan, 35, context_creates).identity()};
  }
  if (!require(first_context == std::array<int, 3>{21, 23, 25},
               "first context owns all pipeline caches") ||
      !require(second_context == std::array<int, 3>{31, 33, 35},
               "replacement context creates device-local pipelines") ||
      !require(context_creates == 6, "each context creates three independent pipelines"))
  {
    return false;
  }

  std::puts("CONTRACT context_owned_pipeline_cache PASS cases=8 caches=3 "
            "shared_reuse=stale context_reuse=isolated creates=6");
  return true;
}

bool context_backend_handle_registry_contract()
{
  struct Handles {
    int instance = 0;
    int device = 0;
    int queue = 0;

    bool operator==(const Handles &) const = default;
  };

  int first_owner = 0;
  int second_owner = 0;
  bw::LatestOwnerHandleRegistry<int, Handles> registry;
  const Handles empty = {};
  const Handles first = {11, 12, 13};
  const Handles first_republished = {21, 22, 23};
  const Handles second = {31, 32, 33};

  if (!require(registry.current() == empty && registry.size() == 0,
               "backend handle registry starts empty"))
  {
    return false;
  }

  registry.publish(&first_owner, first);
  registry.publish(&first_owner, first_republished);
  if (!require(registry.current() == first_republished && registry.size() == 1,
               "republishing one context atomically replaces its handle tuple"))
  {
    return false;
  }

  registry.publish(&second_owner, second);
  if (!require(registry.current() == second && registry.size() == 2,
               "latest live context supplies one coherent handle tuple"))
  {
    return false;
  }

  registry.forget(&first_owner);
  if (!require(registry.current() == second && registry.size() == 1,
               "destroying an older context preserves the current context handles"))
  {
    return false;
  }

  registry.publish(&first_owner, first);
  if (!require(registry.current() == first && registry.size() == 2,
               "republished context becomes the current handle owner"))
  {
    return false;
  }

  registry.forget(&first_owner);
  if (!require(registry.current() == second && registry.size() == 1,
               "destroying the current context restores the previous live owner"))
  {
    return false;
  }

  registry.forget(&second_owner);
  registry.forget(&second_owner);
  if (!require(registry.current() == empty && registry.size() == 0,
               "last and duplicate context destruction leave an empty registry"))
  {
    return false;
  }

  std::puts("CONTRACT context_backend_handle_registry PASS cases=7 owners=2 "
            "tuples=3 publication=atomic restoration=previous cleanup=idempotent");
  return true;
}

bool ordered_queue_scheduler_failure_drain_contract()
{
  constexpr size_t follower_count = 100000;
  constexpr size_t failed_epoch_count = 100000;

  bw::OrderedQueueScheduler scheduler;
  bw::OrderedQueueScheduler::Ticket failed_head = scheduler.reserve();
  size_t executed = 0;
  size_t canceled = 0;
  for (size_t index = 0; index < follower_count; index++) {
    scheduler.enqueue(
        [&](auto done) {
          executed++;
          done(true);
        },
        [&]() { canceled++; });
  }

  if (!require(scheduler.pending_count() == follower_count + 1,
               "scheduler stress followers wait behind the unresolved head"))
  {
    return false;
  }
  failed_head.resolve([](auto done) { done(false); });
  if (!require(executed == 0 && canceled == follower_count,
               "failed scheduler head cancels every same-epoch follower") ||
      !require(scheduler.pending_count() == 0,
               "failed scheduler stress queue drains completely"))
  {
    return false;
  }

  if (!require(scheduler.failed_epoch_count() == 1,
               "current failed epoch remains retained for later same-epoch reservations"))
  {
    return false;
  }
  scheduler.begin_epoch();
  if (!require(scheduler.failed_epoch_count() == 0,
               "unreferenced failed epoch is pruned when a new epoch begins"))
  {
    return false;
  }

  size_t failed_heads = 0;
  size_t retained_peak = 0;
  for (size_t index = 0; index < failed_epoch_count; index++) {
    scheduler.enqueue([&](auto done) {
      failed_heads++;
      done(false);
    });
    retained_peak = std::max(retained_peak, scheduler.failed_epoch_count());
    if (!require(scheduler.failed_epoch_count() == 1,
                 "only the current failed epoch remains reachable"))
    {
      return false;
    }
    scheduler.begin_epoch();
    if (!require(scheduler.failed_epoch_count() == 0,
                 "completed failed epochs do not accumulate"))
    {
      return false;
    }
  }

  size_t accepted_retry = 0;
  scheduler.enqueue([&](auto done) {
    accepted_retry++;
    done(true);
  });
  if (!require(failed_heads == failed_epoch_count && retained_peak == 1,
               "long failed-epoch sequence retains bounded state") ||
      !require(accepted_retry == 1 && scheduler.pending_count() == 0 &&
                   scheduler.failed_epoch_count() == 0,
               "clean epoch executes after repeated scheduler failures"))
  {
    return false;
  }

  std::puts(
      "CONTRACT ordered_queue_scheduler_failure_drain PASS followers=100000 executed=0 canceled=100000 failed_epochs=100000 retained_peak=1 retained_final=0 stack=bounded retry=accepted");
  return true;
}

bool resize_present_barrier_queue_contract()
{
  constexpr uint64_t episode = 17;
  struct FrameEpisodeCase {
    uint64_t frame_episode;
    uint64_t current_episode;
    bool expected;
  };
  constexpr std::array<FrameEpisodeCase, 3> frame_episode_cases = {{{episode, episode, true},
                                                                    {episode - 1, episode, false},
                                                                    {episode, episode + 1, false}}};
  for (const FrameEpisodeCase &test : frame_episode_cases) {
    if (!require(gw::redraw_present_frame_matches_episode(test.frame_episode,
                                                          test.current_episode) == test.expected,
                 "resize barrier binds only the drawable episode active at frame start"))
    {
      return false;
    }
  }

  bw::OrderedQueueScheduler scheduler;
  gw::RedrawPresentBarrier barrier;
  std::function<void(bool)> settle_prior_frame;
  std::array<int, 5> order = {};
  size_t order_size = 0;

  scheduler.enqueue([&](auto done) {
    order[order_size++] = 1;
    settle_prior_frame = std::move(done);
  });
  if (!require(barrier.schedule(episode),
               "resize queue barrier schedules for the committed episode"))
  {
    return false;
  }
  scheduler.enqueue(
      [&](auto done) {
        order[order_size++] = 2;
        barrier.arrive(episode, [&, done = std::move(done)](const bool valid) mutable {
          order[order_size++] = 4;
          done(valid);
        });
      },
      [&]() { barrier.cancel(episode); });
  scheduler.begin_epoch();
  scheduler.enqueue([&](auto done) {
    order[order_size++] = 5;
    done(true);
  });

  if (!require(order_size == 1 && order[0] == 1 && scheduler.pending_count() == 3,
               "prior frame validation holds the barrier and later frame work"))
  {
    return false;
  }
  settle_prior_frame(true);
  if (!require(order_size == 2 && order[1] == 2 && barrier.is_ready() &&
                   scheduler.pending_count() == 2,
               "the barrier arrives only after prior frame work drains") ||
      !require(barrier.filter_update(episode, true),
               "the arrived barrier admits one synchronous presentation update"))
  {
    return false;
  }

  /* Model the P0-H-safe GHOST boundary: acquire/copy/submit occurs synchronously before
   * complete() releases the backend queue into work encoded by the following frame. */
  order[order_size++] = 3;
  if (!require(barrier.complete(episode, true) && scheduler.pending_count() == 0,
               "synchronous present releases later frame work") ||
      !require(order_size == order.size() &&
                   order == std::array<int, 5>{1, 2, 3, 4, 5},
               "resize ordering is prior-frame, barrier, present, release, later-frame"))
  {
    return false;
  }

  /* A failed frame submission ahead of the barrier must run its cancel callback, clear the
   * barrier, and let a later epoch proceed. This is the resize form of a transient browser error
   * storm: recovery must not leave swapBufferRelease() suppressing presentation forever. */
  {
    constexpr uint64_t failed_frame_episode = episode + 1;
    bw::OrderedQueueScheduler failed_frame_scheduler;
    gw::RedrawPresentBarrier failed_frame_barrier;
    bw::OrderedQueueScheduler::Ticket failed_frame = failed_frame_scheduler.reserve();
    bool later_epoch_ran = false;
    if (!require(failed_frame_barrier.schedule(failed_frame_episode),
                 "failed-frame case schedules its resize barrier"))
    {
      return false;
    }
    failed_frame_scheduler.enqueue(
        [&](auto done) {
          failed_frame_barrier.arrive(
              failed_frame_episode,
              [done = std::move(done)](const bool valid) mutable { done(valid); });
        },
        [&]() { failed_frame_barrier.cancel(failed_frame_episode); });
    failed_frame_scheduler.begin_epoch();
    failed_frame_scheduler.enqueue([&](auto done) {
      later_epoch_ran = true;
      done(true);
    });
    failed_frame.resolve([](auto done) { done(false); });
    if (!require(!failed_frame_barrier.is_scheduled() && later_epoch_ran &&
                     failed_frame_scheduler.pending_count() == 0,
                 "failed prior frame cancels the barrier and drains the later epoch") ||
        !require(failed_frame_barrier.schedule(failed_frame_episode),
                 "canceled failed-frame barrier leaves the resize episode retryable") ||
        !require(failed_frame_barrier.cancel(failed_frame_episode),
                 "failed-frame retry barrier tears down cleanly"))
    {
      return false;
    }
  }

  /* If the synchronous surface copy itself fails, complete(false) must release the ordered
   * barrier entry, preserve later-epoch work, and allow this same resize episode to retry. */
  {
    constexpr uint64_t failed_present_episode = episode + 2;
    bw::OrderedQueueScheduler failed_present_scheduler;
    gw::RedrawPresentBarrier failed_present_barrier;
    std::function<void(bool)> settle_prior;
    bool later_epoch_ran = false;
    failed_present_scheduler.enqueue(
        [&](auto done) { settle_prior = std::move(done); });
    if (!require(failed_present_barrier.schedule(failed_present_episode),
                 "failed-present case schedules its resize barrier"))
    {
      return false;
    }
    failed_present_scheduler.enqueue(
        [&](auto done) {
          failed_present_barrier.arrive(
              failed_present_episode,
              [done = std::move(done)](const bool valid) mutable { done(valid); });
        },
        [&]() { failed_present_barrier.cancel(failed_present_episode); });
    failed_present_scheduler.begin_epoch();
    failed_present_scheduler.enqueue([&](auto done) {
      later_epoch_ran = true;
      done(true);
    });
    settle_prior(true);
    if (!require(failed_present_barrier.is_ready(),
                 "failed-present case reaches the synchronous GHOST boundary") ||
        !require(failed_present_barrier.complete(failed_present_episode, false) &&
                     later_epoch_ran && failed_present_scheduler.pending_count() == 0,
                 "failed synchronous present releases the later epoch") ||
        !require(failed_present_barrier.schedule(failed_present_episode),
                 "failed synchronous present leaves the resize episode retryable") ||
        !require(failed_present_barrier.cancel(failed_present_episode),
                 "failed-present retry barrier tears down cleanly"))
    {
      return false;
    }
  }

  /* A browser window drag can publish another coherent extent before the previous resize's
   * barrier reaches the queue head. The obsolete arrival must fail only its old epoch, while the
   * replacement frame and barrier continue to the synchronous-present boundary. */
  {
    constexpr uint64_t first_episode = episode + 3;
    constexpr uint64_t replacement_episode = episode + 4;
    bw::OrderedQueueScheduler superseded_scheduled_scheduler;
    gw::RedrawPresentBarrier superseded_scheduled_barrier;
    std::function<void(bool)> settle_first_frame;
    std::array<int, 7> order = {};
    size_t order_size = 0;
    bool first_barrier_valid = true;

    superseded_scheduled_scheduler.enqueue([&](auto done) {
      order[order_size++] = 1;
      settle_first_frame = std::move(done);
    });
    if (!require(superseded_scheduled_barrier.schedule(first_episode),
                 "queued supersession schedules the first resize barrier"))
    {
      return false;
    }
    superseded_scheduled_scheduler.enqueue(
        [&](auto done) {
          order[order_size++] = 2;
          superseded_scheduled_barrier.arrive(
              first_episode,
              [&, done = std::move(done)](const bool valid) mutable {
                order[order_size++] = 3;
                first_barrier_valid = valid;
                done(valid);
              });
        },
        [&]() { superseded_scheduled_barrier.cancel(first_episode); });
    superseded_scheduled_scheduler.begin_epoch();
    superseded_scheduled_scheduler.enqueue([&](auto done) {
      order[order_size++] = 4;
      done(true);
    });
    if (!require(superseded_scheduled_barrier.schedule(replacement_episode),
                 "queued supersession schedules the replacement resize barrier"))
    {
      return false;
    }
    superseded_scheduled_scheduler.enqueue(
        [&](auto done) {
          order[order_size++] = 5;
          superseded_scheduled_barrier.arrive(
              replacement_episode,
              [&, done = std::move(done)](const bool valid) mutable {
                order[order_size++] = 7;
                done(valid);
              });
        },
        [&]() { superseded_scheduled_barrier.cancel(replacement_episode); });

    if (!require(order_size == 1 &&
                     superseded_scheduled_barrier.scheduled_episode() == replacement_episode,
                 "replacement barrier supersedes an older queued arrival"))
    {
      return false;
    }
    settle_first_frame(true);
    if (!require(!first_barrier_valid && order_size == 5 &&
                     superseded_scheduled_barrier.is_ready() &&
                     superseded_scheduled_barrier.ready_episode() == replacement_episode &&
                     superseded_scheduled_scheduler.pending_count() == 1,
                 "obsolete arrival releases its epoch and replacement reaches ready"))
    {
      return false;
    }
    if (!require(superseded_scheduled_barrier.filter_update(replacement_episode, true),
                 "queued replacement admits one synchronous presentation update"))
    {
      return false;
    }
    order[order_size++] = 6;
    if (!require(superseded_scheduled_barrier.complete(replacement_episode, true) &&
                     superseded_scheduled_scheduler.pending_count() == 0 &&
                     superseded_scheduled_barrier.completed_episode() == replacement_episode,
                 "queued replacement present releases its barrier"))
    {
      return false;
    }
    if (!require(order_size == order.size() &&
                     order == std::array<int, 7>{1, 2, 3, 4, 5, 6, 7},
                 "queued supersession preserves old-fail, replacement-frame, present order"))
    {
      return false;
    }
  }

  /* A second resize can also arrive after the old barrier is ready but before GHOST consumes its
   * synthetic update. Superseding that live completion must release the queue exactly once and a
   * stale GHOST completion must not retire the replacement barrier. */
  {
    constexpr uint64_t first_episode = episode + 5;
    constexpr uint64_t replacement_episode = episode + 6;
    bw::OrderedQueueScheduler superseded_ready_scheduler;
    gw::RedrawPresentBarrier superseded_ready_barrier;
    size_t first_completion_calls = 0;
    bool first_completion_valid = true;
    bool replacement_frame_ran = false;

    if (!require(superseded_ready_barrier.schedule(first_episode),
                 "ready supersession schedules the first resize barrier"))
    {
      return false;
    }
    superseded_ready_scheduler.enqueue([&](auto done) {
      superseded_ready_barrier.arrive(
          first_episode,
          [&, done = std::move(done)](const bool valid) mutable {
            first_completion_calls++;
            first_completion_valid = valid;
            done(valid);
          });
    });
    if (!require(superseded_ready_barrier.is_ready() &&
                     superseded_ready_scheduler.pending_count() == 1,
                 "first resize barrier reaches ready before supersession"))
    {
      return false;
    }
    superseded_ready_scheduler.begin_epoch();
    superseded_ready_scheduler.enqueue([&](auto done) {
      replacement_frame_ran = true;
      done(true);
    });
    if (!require(superseded_ready_barrier.schedule(replacement_episode) &&
                     first_completion_calls == 1 && !first_completion_valid &&
                     replacement_frame_ran &&
                     superseded_ready_barrier.scheduled_episode() == replacement_episode &&
                     superseded_ready_scheduler.pending_count() == 0,
                 "ready supersession cancels the old completion and drains the replacement frame"))
    {
      return false;
    }
    superseded_ready_scheduler.enqueue([&](auto done) {
      superseded_ready_barrier.arrive(
          replacement_episode,
          [done = std::move(done)](const bool valid) mutable { done(valid); });
    });
    if (!require(superseded_ready_barrier.is_ready() &&
                     superseded_ready_scheduler.pending_count() == 1,
                 "ready supersession replacement reaches the presentation boundary"))
    {
      return false;
    }
    if (!require(!superseded_ready_barrier.complete(first_episode, true) &&
                     superseded_ready_barrier.ready_episode() == replacement_episode,
                 "stale GHOST completion cannot retire the replacement barrier"))
    {
      return false;
    }
    if (!require(superseded_ready_barrier.filter_update(replacement_episode, true),
                 "ready replacement admits one synchronous presentation update"))
    {
      return false;
    }
    if (!require(superseded_ready_barrier.complete(replacement_episode, true) &&
                     superseded_ready_scheduler.pending_count() == 0 &&
                     superseded_ready_barrier.completed_episode() == replacement_episode &&
                     first_completion_calls == 1,
                 "ready replacement completes once without reviving the superseded callback"))
    {
      return false;
    }
  }

  std::puts("CONTRACT resize_present_barrier_queue PASS cases=31 frame_binding=3 "
            "order=prior,barrier,present,release,later "
            "recovery=failed-frame,failed-present,retry "
            "supersession=queued,ready,stale-completion");
  return true;
}

bool transient_resource_gate_contract()
{
  struct ResourceCase {
    int identity;
    bool scope_valid;
    bool expected_valid;
  };
  constexpr std::array<ResourceCase, 3> cases = {{{0, true, false},
                                                   {41, false, false},
                                                   {73, true, true}}};

  bw::OrderedQueueScheduler scheduler;
  int scope_begins = 0;
  int scope_ends = 0;
  int completions = 0;
  int dependent_work = 0;
  int canceled_work = 0;

  for (size_t case_index = 0; case_index < cases.size(); case_index++) {
    const ResourceCase &test = cases[case_index];
    bw::OrderedQueueScheduler::Ticket leading_ticket;
    if (case_index == 2) {
      /* Exercise the inverse callback order: validation settles while an earlier queue entry
       * still owns the front, then the accepted gate releases only when its turn begins. */
      leading_ticket = scheduler.reserve();
    }
    std::function<void(bool)> settle;
    bool completed = false;
    bool result = true;
    const CacheHandleProbe candidate = bw::transient_resource_gate_scoped(
        scheduler,
        [&]() { scope_begins++; },
        [&]() { return CacheHandleProbe(test.identity); },
        [&](auto completion) {
          scope_ends++;
          settle = std::move(completion);
        },
        [&](const bool valid) {
          completions++;
          completed = true;
          result = valid;
        });
    scheduler.enqueue(
        [&](auto done) {
          dependent_work++;
          done(true);
        },
        [&]() { canceled_work++; });

    if (!require(candidate.identity() == test.identity,
                 "transient gate returns the provisional candidate") ||
        !require(!completed && dependent_work == 0,
                 "transient gate blocks dependent work while its scope is pending") ||
        !require(scheduler.pending_count() == (case_index == 2 ? 3 : 2) && bool(settle),
                 "transient gate reserves queue order before scope completion"))
    {
      return false;
    }

    settle(test.scope_valid);
    if (case_index == 2) {
      if (!require(!completed && dependent_work == 0,
                   "settled transient gate waits for its reserved queue position"))
      {
        return false;
      }
      leading_ticket.resolve([](auto done) { done(true); });
    }
    if (!require(completed && result == test.expected_valid,
                 "transient gate combines handle and scope validity") ||
        !require(dependent_work == int(test.expected_valid),
                 "only accepted transient resources release dependent work") ||
        !require(canceled_work == int(case_index + 1 - size_t(dependent_work)),
                 "rejected transient resources cancel same-epoch work") ||
        !require(scheduler.pending_count() == 0, "transient resource gate drains"))
    {
      return false;
    }
    scheduler.begin_epoch();
  }

  if (!require(scope_begins == 3 && scope_ends == 3 && completions == 3,
               "transient resource gate scope census") ||
      !require(dependent_work == 1 && canceled_work == 2,
               "clean retry epoch executes after two rejected resources"))
  {
    return false;
  }
  std::puts("CONTRACT transient_resource_gate PASS cases=3 settle_orders=2 "
            "error_object=blocked dependent=1 canceled=2 retry=accepted");
  return true;
}

bool compute_bind_group_scope_contract()
{
  enum class DispatchKind : uint8_t {
    Direct,
    Indirect,
  };

  int scope_begins = 0;
  int creations = 0;
  int accepted = 0;
  int published = 0;
  int canceled = 0;
  int uncaptured_errors = 0;

  for (const DispatchKind kind : {DispatchKind::Direct, DispatchKind::Indirect}) {
    bw::OrderedQueueScheduler scheduler;
    for (const bool valid_scope : {false, true}) {
      if (valid_scope) {
        scheduler.begin_epoch();
      }

      bool scope_active = false;
      bool completed = false;
      bool result = true;
      std::function<void(bool)> settle;
      const CacheHandleProbe candidate = bw::transient_resource_gate_scoped(
          scheduler,
          [&]() {
            scope_begins++;
            scope_active = true;
          },
          [&]() {
            creations++;
            if (!scope_active) {
              uncaptured_errors++;
            }
            /* Validation failures return a non-null WebGPU error object. */
            return CacheHandleProbe(kind == DispatchKind::Direct ? 101 : 202);
          },
          [&](auto completion) {
            scope_active = false;
            settle = std::move(completion);
          },
          [&](const bool valid) {
            completed = true;
            result = valid;
            accepted += int(valid);
          });
      scheduler.enqueue(
          [&](auto done) {
            published++;
            done(true);
          },
          [&]() { canceled++; });

      if (!require(candidate != nullptr, "compute bind-group probe must model an error object") ||
          !require(!completed && published == accepted,
                   "compute dispatch published before bind-group scope completion") ||
          !require(bool(settle), "compute bind-group scope did not retain completion"))
      {
        return false;
      }

      settle(valid_scope);
      if (!require(completed && result == valid_scope,
                   "compute bind-group scope result was not propagated") ||
          !require(published == accepted,
                   "compute dispatch publication did not follow accepted bind-group creation") ||
          !require(canceled == creations - accepted,
                   "rejected compute bind group did not cancel its dispatch") ||
          !require(scheduler.pending_count() == 0,
                   "compute bind-group dispatch transaction did not drain"))
      {
        return false;
      }
    }
  }

  if (!require(scope_begins == 4 && creations == 4 && accepted == 2 && published == 2 &&
                   canceled == 2 && uncaptured_errors == 0,
               "compute bind-group direct/indirect scope census"))
  {
    return false;
  }
  std::puts("CONTRACT compute_bind_group_scope PASS cases=4 dispatch_kinds=2 "
            "error_objects=2 uncaptured=0 published=2 canceled=2 retry=accepted");
  return true;
}

bool compute_pipeline_cache_publication_contract()
{
  bw::ScopedHandleCache<std::string, CacheHandleProbe> cache;
  const std::string stable_key("\x03\0\0\0", 4);
  const std::string retry_key("\x07\0\0\0\x0b\0\0\0", 8);
  int creates = 0;

  CacheHandleProbe pipeline = cache.get_or_create_scoped(
      stable_key,
      []() {},
      [&]() {
        creates++;
        return CacheHandleProbe(31);
      },
      [](auto completion) { completion(true); });
  if (!require(pipeline.identity() == 31 && cache.size() == 1 && creates == 1,
               "accepted compute pipeline baseline is published"))
  {
    return false;
  }

  pipeline = cache.get_or_create_scoped(
      retry_key,
      []() {},
      [&]() {
        creates++;
        return CacheHandleProbe(41);
      },
      [](auto completion) { completion(false); });
  if (!require(pipeline == nullptr && cache.size() == 1 && !cache.pending(retry_key) &&
                   cache.lookup(stable_key).identity() == 31 && creates == 2,
               "non-null compute pipeline error object is rejected without disturbing old keys"))
  {
    return false;
  }

  pipeline = cache.get_or_create_scoped(
      retry_key,
      []() {},
      [&]() {
        creates++;
        return CacheHandleProbe(73);
      },
      [](auto completion) { completion(true); });
  if (!require(pipeline.identity() == 73 && cache.size() == 2 && creates == 3,
               "clean compute pipeline retry publishes its specialization key"))
  {
    return false;
  }

  std::puts(
      "CONTRACT compute_pipeline_cache_publication PASS cases=3 error_object=rejected retry=published entries=2");
  return true;
}

bool primitive_topology_contract()
{
  using PT = wgpu::PrimitiveTopology;
  struct Expected {
    blender::GPUPrimType primitive;
    PT topology;
  };
  constexpr std::array<Expected, 11> expected = {{
      {blender::GPU_PRIM_POINTS, PT::PointList},
      {blender::GPU_PRIM_LINES, PT::LineList},
      {blender::GPU_PRIM_TRIS, PT::TriangleList},
      {blender::GPU_PRIM_LINE_STRIP, PT::LineStrip},
      {blender::GPU_PRIM_LINE_LOOP, PT::LineStrip},
      {blender::GPU_PRIM_TRI_STRIP, PT::TriangleStrip},
      {blender::GPU_PRIM_TRI_FAN, PT::TriangleList},
      {blender::GPU_PRIM_LINES_ADJ, PT::TriangleList},
      {blender::GPU_PRIM_TRIS_ADJ, PT::TriangleList},
      {blender::GPU_PRIM_LINE_STRIP_ADJ, PT::TriangleList},
      {blender::GPU_PRIM_NONE, PT::TriangleList},
  }};

  for (const Expected &row : expected) {
    if (!require(bw::to_wgpu_topology(row.primitive) == row.topology,
                 "primitive topology mapping"))
    {
      return false;
    }
  }
  std::puts("CONTRACT primitive_topology PASS cases=11");
  return true;
}

bool strip_index_format_contract()
{
  using IF = wgpu::IndexFormat;
  constexpr std::array primitives = {
      blender::GPU_PRIM_POINTS,
      blender::GPU_PRIM_LINES,
      blender::GPU_PRIM_TRIS,
      blender::GPU_PRIM_LINE_STRIP,
      blender::GPU_PRIM_LINE_LOOP,
      blender::GPU_PRIM_TRI_STRIP,
      blender::GPU_PRIM_TRI_FAN,
      blender::GPU_PRIM_LINES_ADJ,
      blender::GPU_PRIM_TRIS_ADJ,
      blender::GPU_PRIM_LINE_STRIP_ADJ,
      blender::GPU_PRIM_NONE,
  };
  constexpr std::array index_formats = {IF::Undefined, IF::Uint16, IF::Uint32};

  size_t cases = 0;
  size_t selected = 0;
  for (const blender::GPUPrimType primitive : primitives) {
    const bool is_strip = primitive == blender::GPU_PRIM_LINE_STRIP ||
                          primitive == blender::GPU_PRIM_LINE_LOOP ||
                          primitive == blender::GPU_PRIM_TRI_STRIP;
    for (const IF index_format : index_formats) {
      const IF expected = is_strip ? index_format : IF::Undefined;
      if (!require(bw::to_wgpu_strip_index_format(primitive, index_format) == expected,
                   "strip index-format mapping"))
      {
        return false;
      }
      cases++;
      selected += expected != IF::Undefined ? 1 : 0;
    }
  }
  if (!require(cases == 33, "strip index-format census") ||
      !require(selected == 6, "selected strip index-format census"))
  {
    return false;
  }
  std::puts("CONTRACT strip_index_format PASS cases=33 selected=6");
  return true;
}

bool indirect_draw_span_contract()
{
  struct Case {
    int count;
    intptr_t offset;
    intptr_t stride;
    bool indexed;
    uint64_t buffer_size;
    bool accepted;
    uint64_t first_offset;
    uint64_t command_stride;
    uint64_t command_size;
    uint64_t end_offset;
  };
  constexpr intptr_t aligned_intptr_max =
      std::numeric_limits<intptr_t>::max() & ~intptr_t(3);
  constexpr std::array<Case, 19> cases = {{
      {1, 0, 0, false, 16, true, 0, 16, 16, 16},
      {1, 4, 0, true, 24, true, 4, 20, 20, 24},
      {3, 8, 0, false, 56, true, 8, 16, 16, 56},
      {3, 4, 32, true, 88, true, 4, 32, 20, 88},
      {2, 4, 4, false, 24, true, 4, 4, 16, 24},
      {2, 0, 24, true, 44, true, 0, 24, 20, 44},
      {4, 16, 32, false, 128, true, 16, 32, 16, 128},
      {0, 0, 0, false, 16, false, 0, 0, 0, 0},
      {-1, 0, 0, false, 16, false, 0, 0, 0, 0},
      {1, -4, 0, false, 16, false, 0, 0, 0, 0},
      {2, 0, -4, false, 32, false, 0, 0, 0, 0},
      {1, 2, 0, false, 32, false, 0, 0, 0, 0},
      {2, 0, 2, false, 32, false, 0, 0, 0, 0},
      {1, 0, 0, false, 15, false, 0, 0, 0, 0},
      {1, 0, 0, true, 19, false, 0, 0, 0, 0},
      {1, 4, 0, false, 16, false, 0, 0, 0, 0},
      {2, 0, 0, false, 31, false, 0, 0, 0, 0},
      {2, 0, 24, true, 43, false, 0, 0, 0, 0},
      {std::numeric_limits<int>::max(),
       aligned_intptr_max,
       aligned_intptr_max,
       false,
       1024,
       false,
       0,
       0,
       0,
       0},
  }};

  size_t accepted = 0;
  size_t rejected = 0;
  uint64_t first_sum = 0;
  uint64_t stride_sum = 0;
  uint64_t end_sum = 0;
  for (const Case &test : cases) {
    bw::IndirectDrawSpan actual = {11, 12, 13, 14};
    const bw::IndirectDrawSpan sentinel = actual;
    const bool result = bw::indirect_draw_span(
        test.count, test.offset, test.stride, test.indexed, test.buffer_size, actual);
    if (!require(result == test.accepted, "indirect draw span decision")) {
      return false;
    }
    if (!result) {
      if (!require(actual.first_offset == sentinel.first_offset &&
                       actual.command_stride == sentinel.command_stride &&
                       actual.command_size == sentinel.command_size &&
                       actual.end_offset == sentinel.end_offset,
                   "rejected indirect draw span preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.first_offset == test.first_offset &&
                     actual.command_stride == test.command_stride &&
                     actual.command_size == test.command_size &&
                     actual.end_offset == test.end_offset,
                 "accepted indirect draw span geometry"))
    {
      return false;
    }
    accepted++;
    first_sum += actual.first_offset;
    stride_sum += actual.command_stride;
    end_sum += actual.end_offset;
  }

  if (!require(accepted == 7 && rejected == 12, "indirect draw span census") ||
      !require(first_sum == 36 && stride_sum == 144 && end_sum == 380,
               "indirect draw span aggregate"))
  {
    return false;
  }
  std::puts("CONTRACT indirect_draw_span PASS cases=19 accepted=7 rejected=12 "
            "first_sum=36 stride_sum=144 end_sum=380");
  return true;
}

bool direct_draw_plan_contract()
{
  struct Case {
    int vertex_first;
    int vertex_count;
    int instance_first;
    int instance_count;
    bool accepted;
  };
  constexpr int int_max = std::numeric_limits<int>::max();
  constexpr int int_min = std::numeric_limits<int>::min();
  constexpr std::array<Case, 16> cases = {{
      {0, 1, 0, 1, true},
      {3, 7, 11, 13, true},
      {int_max, 1, int_max, 1, true},
      {0, int_max, 0, int_max, true},
      {int_max, int_max, int_max, int_max, true},
      {-1, 1, 0, 1, false},
      {0, -1, 0, 1, false},
      {0, 1, -1, 1, false},
      {0, 1, 0, -1, false},
      {0, 0, 0, 1, false},
      {0, 1, 0, 0, false},
      {int_min, 1, 0, 1, false},
      {0, int_min, 0, 1, false},
      {0, 1, int_min, 1, false},
      {0, 1, 0, int_min, false},
      {-1, -1, -1, -1, false},
  }};

  size_t accepted = 0;
  size_t rejected = 0;
  uint64_t value_sum = 0;
  for (const Case &test : cases) {
    bw::DirectDrawPlan actual = {101, 102, 103, 104};
    const bw::DirectDrawPlan sentinel = actual;
    const bool result = bw::direct_draw_plan(test.vertex_first,
                                             test.vertex_count,
                                             test.instance_first,
                                             test.instance_count,
                                             actual);
    if (!require(result == test.accepted, "direct draw decision")) {
      return false;
    }
    if (!result) {
      if (!require(actual.vertex_first == sentinel.vertex_first &&
                       actual.vertex_count == sentinel.vertex_count &&
                       actual.instance_first == sentinel.instance_first &&
                       actual.instance_count == sentinel.instance_count,
                   "rejected direct draw preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.vertex_first == uint32_t(test.vertex_first) &&
                     actual.vertex_count == uint32_t(test.vertex_count) &&
                     actual.instance_first == uint32_t(test.instance_first) &&
                     actual.instance_count == uint32_t(test.instance_count),
                 "accepted direct draw geometry"))
    {
      return false;
    }
    accepted++;
    value_sum += uint64_t(actual.vertex_first) + actual.vertex_count + actual.instance_first +
                 actual.instance_count;
  }

  if (!require(accepted == 5 && rejected == 11, "direct draw census") ||
      !require(value_sum == 17179869214ull, "direct draw aggregate"))
  {
    return false;
  }
  std::puts(
      "CONTRACT direct_draw_plan PASS cases=16 accepted=5 rejected=11 value_sum=17179869214");
  return true;
}

bool viewport_scissor_plan_contract()
{
  struct Case {
    int x;
    int y;
    int width;
    int height;
    uint32_t target_width;
    uint32_t target_height;
    uint32_t max_viewport_dimension;
    bool accepted;
    uint32_t scissor_x;
    uint32_t scissor_y;
    uint32_t scissor_width;
    uint32_t scissor_height;
  };
  constexpr int int_max = std::numeric_limits<int>::max();
  constexpr int int_min = std::numeric_limits<int>::min();
  constexpr std::array<Case, 28> cases = {{
      {0, 0, 640, 480, 640, 480, 8192, true, 0, 0, 640, 480},
      {10, 20, 30, 40, 640, 480, 8192, true, 10, 20, 30, 40},
      {-10, 5, 20, 10, 640, 480, 8192, true, 0, 5, 10, 10},
      {5, -10, 10, 20, 640, 480, 8192, true, 5, 0, 10, 10},
      {630, 20, 20, 30, 640, 480, 8192, true, 630, 20, 10, 30},
      {20, 470, 30, 20, 640, 480, 8192, true, 20, 470, 30, 10},
      {-10, -20, 660, 520, 640, 480, 8192, true, 0, 0, 640, 480},
      {-10, -10, 20, 20, 640, 480, 8192, true, 0, 0, 10, 10},
      {639, 479, 1, 1, 640, 480, 8192, true, 639, 479, 1, 1},
      {-63, -63, 64, 64, 64, 64, 64, true, 0, 0, 1, 1},
      {63, 63, 64, 64, 64, 64, 64, true, 63, 63, 1, 1},
      {0, 0, 0, 1, 640, 480, 8192, true, 0, 0, 0, 0},
      {0, 0, 1, 0, 640, 480, 8192, true, 0, 0, 0, 0},
      {0, 0, -1, 1, 640, 480, 8192, false, 0, 0, 0, 0},
      {0, 0, 1, -1, 640, 480, 8192, false, 0, 0, 0, 0},
      {0, 0, 1, 1, 0, 480, 8192, false, 0, 0, 0, 0},
      {0, 0, 1, 1, 640, 0, 8192, false, 0, 0, 0, 0},
      {0, 0, 1, 1, 640, 480, 0, false, 0, 0, 0, 0},
      {0, 0, 1, 1, 65, 64, 64, false, 0, 0, 0, 0},
      {0, 0, 1, 1, 64, 65, 64, false, 0, 0, 0, 0},
      {0, 0, 65, 1, 64, 64, 64, false, 0, 0, 0, 0},
      {0, 0, 1, 65, 64, 64, 64, false, 0, 0, 0, 0},
      {-10, 0, 10, 1, 640, 480, 8192, true, 0, 0, 0, 0},
      {640, 0, 1, 1, 640, 480, 8192, true, 0, 0, 0, 0},
      {0, -10, 1, 10, 640, 480, 8192, true, 0, 0, 0, 0},
      {0, 480, 1, 1, 640, 480, 8192, true, 0, 0, 0, 0},
      {int_min, 0, 1, 1, 640, 480, 8192, false, 0, 0, 0, 0},
      {int_max, 0, int_max, 1, 640, 480, 8192, false, 0, 0, 0, 0},
  }};

  size_t accepted = 0;
  size_t rejected = 0;
  uint64_t scissor_area = 0;
  for (const Case &test : cases) {
    bw::ViewportScissorPlan actual = {101, 102, 103, 104, 105, 106, 107, 108};
    const bw::ViewportScissorPlan sentinel = actual;
    const bool result = bw::viewport_scissor_plan(test.x,
                                                  test.y,
                                                  test.width,
                                                  test.height,
                                                  test.target_width,
                                                  test.target_height,
                                                  test.max_viewport_dimension,
                                                  actual);
    if (!require(result == test.accepted, "viewport/scissor decision")) {
      return false;
    }
    if (!result) {
      if (!require(actual.viewport_x == sentinel.viewport_x &&
                       actual.viewport_y == sentinel.viewport_y &&
                       actual.viewport_width == sentinel.viewport_width &&
                       actual.viewport_height == sentinel.viewport_height &&
                       actual.scissor_x == sentinel.scissor_x &&
                       actual.scissor_y == sentinel.scissor_y &&
                       actual.scissor_width == sentinel.scissor_width &&
                       actual.scissor_height == sentinel.scissor_height,
                   "rejected viewport/scissor preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.viewport_x == test.x && actual.viewport_y == test.y &&
                     actual.viewport_width == uint32_t(test.width) &&
                     actual.viewport_height == uint32_t(test.height),
                 "accepted viewport preserves raster transform") ||
        !require(actual.scissor_x == test.scissor_x &&
                     actual.scissor_y == test.scissor_y &&
                     actual.scissor_width == test.scissor_width &&
                     actual.scissor_height == test.scissor_height,
                 "accepted scissor intersection"))
    {
      return false;
    }
    accepted++;
    scissor_area += uint64_t(actual.scissor_width) * actual.scissor_height;
  }

  if (!require(accepted == 17 && rejected == 11, "viewport/scissor census") ||
      !require(scissor_area == 616503, "viewport/scissor aggregate"))
  {
    return false;
  }
  std::puts(
      "CONTRACT viewport_scissor_plan PASS cases=28 accepted=17 rejected=11 area=616503");
  return true;
}

bool window_viewport_scissor_plan_contract()
{
  struct Case {
    int viewport_x;
    int viewport_y;
    int viewport_width;
    int viewport_height;
    bool scissor_enabled;
    int scissor_x;
    int scissor_y;
    int scissor_width;
    int scissor_height;
    int target_width;
    int target_height;
    uint32_t max_viewport_dimension;
    bool accepted;
    int expected_viewport_x;
    int expected_viewport_y;
    uint32_t expected_viewport_width;
    uint32_t expected_viewport_height;
    bool expected_scissor_enabled;
    uint32_t expected_scissor_x;
    uint32_t expected_scissor_y;
    uint32_t expected_scissor_width;
    uint32_t expected_scissor_height;
  };
  constexpr int int_max = std::numeric_limits<int>::max();
  constexpr int int_min = std::numeric_limits<int>::min();
  constexpr std::array<Case, 31> cases = {{
      {0, 0, 640, 480, false, 0, 0, 0, 0, 640, 480, 8192, true,
       0, 0, 640, 480, false, 0, 0, 0, 0},
      {10, 20, 30, 40, false, 0, 0, 0, 0, 640, 480, 8192, true,
       10, 420, 30, 40, false, 0, 0, 0, 0},
      {-10, 5, 20, 10, false, 0, 0, 0, 0, 640, 480, 8192, true,
       -10, 465, 20, 10, false, 0, 0, 0, 0},
      {5, -10, 10, 20, false, 0, 0, 0, 0, 640, 480, 8192, true,
       5, 470, 10, 20, false, 0, 0, 0, 0},
      {630, 20, 20, 30, false, 0, 0, 0, 0, 640, 480, 8192, true,
       630, 430, 20, 30, false, 0, 0, 0, 0},
      {20, 470, 30, 20, false, 0, 0, 0, 0, 640, 480, 8192, true,
       20, -10, 30, 20, false, 0, 0, 0, 0},
      {-10, -20, 660, 520, false, 0, 0, 0, 0, 640, 480, 8192, true,
       -10, -20, 660, 520, false, 0, 0, 0, 0},
      {0, 0, 640, 480, true, 10, 20, 30, 40, 640, 480, 8192, true,
       0, 0, 640, 480, true, 10, 420, 30, 40},
      {0, 0, 640, 480, true, -10, 5, 20, 10, 640, 480, 8192, true,
       0, 0, 640, 480, true, 0, 465, 10, 10},
      {0, 0, 640, 480, true, 5, -10, 10, 20, 640, 480, 8192, true,
       0, 0, 640, 480, true, 5, 470, 10, 10},
      {0, 0, 64, 64, true, -10, 0, int_max, 1, 64, 64, 64, true,
       0, 0, 64, 64, true, 0, 63, 64, 1},
      {-63, 0, 64, 64, false, 0, 0, 0, 0, 64, 64, 64, true,
       -63, 0, 64, 64, false, 0, 0, 0, 0},
      {63, 0, 64, 64, false, 0, 0, 0, 0, 64, 64, 64, true,
       63, 0, 64, 64, false, 0, 0, 0, 0},
      {0, 0, 640, 480, true, 20, 470, 30, 20, 640, 480, 8192, true,
       0, 0, 640, 480, true, 20, 0, 30, 10},
      {0, 0, 0, 1, false, 0, 0, 0, 0, 640, 480, 8192, true,
       0, 479, 0, 1, false, 0, 0, 0, 0},
      {0, 0, 1, 0, false, 0, 0, 0, 0, 640, 480, 8192, true,
       0, 480, 1, 0, false, 0, 0, 0, 0},
      {-10, 0, 10, 1, false, 0, 0, 0, 0, 640, 480, 8192, true,
       -10, 479, 10, 1, true, 0, 0, 0, 0},
      {640, 0, 1, 1, false, 0, 0, 0, 0, 640, 480, 8192, true,
       640, 479, 1, 1, true, 0, 0, 0, 0},
      {0, -10, 1, 10, false, 0, 0, 0, 0, 640, 480, 8192, true,
       0, 480, 1, 10, true, 0, 0, 0, 0},
      {0, 480, 1, 1, false, 0, 0, 0, 0, 640, 480, 8192, true,
       0, -1, 1, 1, true, 0, 0, 0, 0},
      {0, 0, 1, 1, false, 0, 0, 0, 0, 0, 480, 8192, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, 0, 1, 1, false, 0, 0, 0, 0, 640, 0, 8192, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, 0, 1, 1, false, 0, 0, 0, 0, 640, 480, 0, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, 0, 1, 1, false, 0, 0, 0, 0, 65, 64, 64, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, 0, 65, 1, false, 0, 0, 0, 0, 64, 64, 64, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, int_min, 1, 1, false, 0, 0, 0, 0, 640, 480, 8192, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, int_max, 1, 1, false, 0, 0, 0, 0, 640, 480, 8192, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {int_max, 0, int_max, 1, false, 0, 0, 0, 0, 640, 480, 8192, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {0, 0, 640, 480, true, 0, 0, 0, 1, 640, 480, 8192, true,
       0, 0, 640, 480, true, 0, 0, 0, 0},
      {0, 0, 640, 480, true, -10, 0, 10, 1, 640, 480, 8192, true,
       0, 0, 640, 480, true, 0, 0, 0, 0},
      {0, 0, 640, 480, true, 0, int_min, 1, 1, 640, 480, 8192, true,
       0, 0, 640, 480, true, 0, 0, 0, 0},
  }};

  size_t accepted = 0;
  size_t rejected = 0;
  int64_t viewport_sum = 0;
  uint64_t scissor_area = 0;
  const auto plans_equal = [](const bw::WindowViewportPlan &a,
                              const bw::WindowViewportPlan &b) {
    return a.viewport.viewport_x == b.viewport.viewport_x &&
           a.viewport.viewport_y == b.viewport.viewport_y &&
           a.viewport.viewport_width == b.viewport.viewport_width &&
           a.viewport.viewport_height == b.viewport.viewport_height &&
           a.viewport.scissor_x == b.viewport.scissor_x &&
           a.viewport.scissor_y == b.viewport.scissor_y &&
           a.viewport.scissor_width == b.viewport.scissor_width &&
           a.viewport.scissor_height == b.viewport.scissor_height &&
           a.scissor_enabled == b.scissor_enabled && a.scissor_x == b.scissor_x &&
           a.scissor_y == b.scissor_y && a.scissor_width == b.scissor_width &&
           a.scissor_height == b.scissor_height;
  };
  for (const Case &test : cases) {
    const int viewport[4] = {
        test.viewport_x, test.viewport_y, test.viewport_width, test.viewport_height};
    const int scissor[4] = {
        test.scissor_x, test.scissor_y, test.scissor_width, test.scissor_height};
    bw::WindowViewportPlan actual = {
        {101, 102, 103, 104, 105, 106, 107, 108}, true, 109, 110, 111, 112};
    const bw::WindowViewportPlan sentinel = actual;
    const bool result = bw::window_viewport_scissor_plan(viewport,
                                                         test.scissor_enabled ? scissor : nullptr,
                                                         test.target_width,
                                                         test.target_height,
                                                         test.max_viewport_dimension,
                                                         actual);
    if (!require(result == test.accepted, "window viewport/scissor decision")) {
      return false;
    }
    if (!result) {
      if (!require(plans_equal(actual, sentinel),
                   "rejected window viewport/scissor preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.viewport.viewport_x == test.expected_viewport_x &&
                     actual.viewport.viewport_y == test.expected_viewport_y &&
                     actual.viewport.viewport_width == test.expected_viewport_width &&
                     actual.viewport.viewport_height == test.expected_viewport_height,
                 "accepted window viewport preserves bottom-origin transform") ||
        !require(actual.scissor_enabled == test.expected_scissor_enabled &&
                     actual.scissor_x == test.expected_scissor_x &&
                     actual.scissor_y == test.expected_scissor_y &&
                     actual.scissor_width == test.expected_scissor_width &&
                     actual.scissor_height == test.expected_scissor_height,
                 "accepted window scissor intersection"))
    {
      return false;
    }
    accepted++;
    viewport_sum += int64_t(actual.viewport.viewport_x) + actual.viewport.viewport_y +
                    actual.viewport.viewport_width + actual.viewport.viewport_height;
    if (actual.scissor_enabled) {
      scissor_area += uint64_t(actual.scissor_width) * actual.scissor_height;
    }
  }

  bw::WindowViewportPlan null_actual = {
      {101, 102, 103, 104, 105, 106, 107, 108}, true, 109, 110, 111, 112};
  const bw::WindowViewportPlan null_sentinel = null_actual;
  if (!require(!bw::window_viewport_scissor_plan(nullptr, nullptr, 640, 480, 8192, null_actual),
               "null window viewport rejected") ||
      !require(plans_equal(null_actual, null_sentinel), "null window viewport preserves output") ||
      !require(accepted == 23 && rejected == 8, "window viewport/scissor census") ||
      !require(viewport_sum == 16208, "window viewport aggregate") ||
      !require(scissor_area == 1764, "window scissor aggregate"))
  {
    return false;
  }
  std::puts("CONTRACT window_viewport_scissor_plan PASS cases=32 accepted=23 rejected=9 "
            "viewport_sum=16208 scissor_area=1764");
  return true;
}

bool offscreen_viewport_scissor_plan_contract()
{
  struct Case {
    int viewport[4];
    bool scissor_enabled;
    int scissor[4];
    int target_width;
    int target_height;
    uint32_t max_viewport_dimension;
    bool accepted;
    int expected_viewport_x;
    int expected_viewport_y;
    uint32_t expected_viewport_width;
    uint32_t expected_viewport_height;
    bool expected_scissor_enabled;
    uint32_t expected_scissor_x;
    uint32_t expected_scissor_y;
    uint32_t expected_scissor_width;
    uint32_t expected_scissor_height;
  };
  constexpr int int_max = std::numeric_limits<int>::max();
  constexpr std::array<Case, 20> cases = {{
      {{0, 0, 6, 5}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       0, 0, 6, 5, false, 0, 0, 0, 0},
      {{1, 1, 3, 2}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       1, 2, 3, 2, false, 0, 0, 0, 0},
      {{-2, 1, 4, 3}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       -2, 1, 4, 3, false, 0, 0, 0, 0},
      {{4, 3, 4, 3}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       4, -1, 4, 3, false, 0, 0, 0, 0},
      {{1, 0, 4, 4}, true, {3, 2, 3, 3}, 6, 5, 8, true,
       1, 1, 4, 4, true, 3, 0, 3, 3},
      {{0, 0, 6, 5}, true, {-2, 1, 4, 3}, 6, 5, 8, true,
       0, 0, 6, 5, true, 0, 1, 2, 3},
      {{0, 0, 6, 5}, true, {4, 3, 4, 3}, 6, 5, 8, true,
       0, 0, 6, 5, true, 4, 0, 2, 2},
      {{-2, -2, 10, 9}, true, {0, 0, 6, 5}, 6, 5, 16, true,
       -2, -2, 10, 9, true, 0, 0, 6, 5},
      {{-63, -63, 64, 64}, false, {0, 0, 0, 0}, 64, 64, 64, true,
       -63, 63, 64, 64, false, 0, 0, 0, 0},
      {{63, 63, 64, 64}, false, {0, 0, 0, 0}, 64, 64, 64, true,
       63, -63, 64, 64, false, 0, 0, 0, 0},
      {{0, 0, 64, 64}, true, {-10, 0, int_max, 1}, 64, 64, 64, true,
       0, 0, 64, 64, true, 0, 63, 64, 1},
      {{0, 0, 6, 5}, false, {0, 0, 0, -1}, 6, 5, 8, true,
       0, 0, 6, 5, false, 0, 0, 0, 0},
      {{0, 0, 0, 1}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       0, 4, 0, 1, false, 0, 0, 0, 0},
      {{0, 0, 1, 0}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       0, 5, 1, 0, false, 0, 0, 0, 0},
      {{-10, 0, 10, 1}, false, {0, 0, 0, 0}, 6, 5, 8, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {{0, 5, 1, 1}, false, {0, 0, 0, 0}, 6, 5, 8, true,
       0, -1, 1, 1, true, 0, 0, 0, 0},
      {{0, 0, 1, 1}, false, {0, 0, 0, 0}, 0, 5, 8, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {{0, 0, 1, 1}, false, {0, 0, 0, 0}, 9, 5, 8, false,
       0, 0, 0, 0, false, 0, 0, 0, 0},
      {{0, 0, 6, 5}, true, {0, 0, 0, 1}, 6, 5, 8, true,
       0, 0, 6, 5, true, 0, 0, 0, 0},
      {{0, 0, 6, 5}, true, {-10, 0, 10, 1}, 6, 5, 8, true,
       0, 0, 6, 5, true, 0, 0, 0, 0},
  }};

  const auto plans_equal = [](const bw::FramebufferViewportPlan &a,
                              const bw::FramebufferViewportPlan &b) {
    return a.viewport.viewport_x == b.viewport.viewport_x &&
           a.viewport.viewport_y == b.viewport.viewport_y &&
           a.viewport.viewport_width == b.viewport.viewport_width &&
           a.viewport.viewport_height == b.viewport.viewport_height &&
           a.viewport.scissor_x == b.viewport.scissor_x &&
           a.viewport.scissor_y == b.viewport.scissor_y &&
           a.viewport.scissor_width == b.viewport.scissor_width &&
           a.viewport.scissor_height == b.viewport.scissor_height &&
           a.scissor_enabled == b.scissor_enabled && a.scissor_x == b.scissor_x &&
           a.scissor_y == b.scissor_y && a.scissor_width == b.scissor_width &&
           a.scissor_height == b.scissor_height;
  };

  size_t accepted = 0;
  size_t rejected = 0;
  size_t enabled_scissors = 0;
  uint64_t scissor_area = 0;
  for (size_t case_index = 0; case_index < cases.size(); case_index++) {
    const Case &test = cases[case_index];
    bw::FramebufferViewportPlan actual = {
        {101, 102, 103, 104, 105, 106, 107, 108}, true, 109, 110, 111, 112};
    const bw::FramebufferViewportPlan sentinel = actual;
    const bool result = bw::offscreen_viewport_scissor_plan(
        test.viewport,
        test.scissor_enabled ? test.scissor : nullptr,
        test.target_width,
        test.target_height,
        test.max_viewport_dimension,
        actual);
    if (!require(result == test.accepted, "offscreen viewport/scissor decision")) {
      std::fprintf(stderr, "offscreen case=%zu accepted=%d actual=%d\n", case_index,
                   int(test.accepted), int(result));
      return false;
    }
    if (!result) {
      if (!require(plans_equal(actual, sentinel),
                   "rejected offscreen viewport/scissor preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.viewport.viewport_x == test.expected_viewport_x &&
                     actual.viewport.viewport_y == test.expected_viewport_y &&
                     actual.viewport.viewport_width == test.expected_viewport_width &&
                     actual.viewport.viewport_height == test.expected_viewport_height,
                 "accepted offscreen viewport converts to WebGPU top origin") ||
        !require(actual.scissor_enabled == test.expected_scissor_enabled &&
                     actual.scissor_x == test.expected_scissor_x &&
                     actual.scissor_y == test.expected_scissor_y &&
                     actual.scissor_width == test.expected_scissor_width &&
                     actual.scissor_height == test.expected_scissor_height,
                 "accepted offscreen scissor clips independently"))
    {
      return false;
    }
    accepted++;
    if (actual.scissor_enabled) {
      enabled_scissors++;
      scissor_area += uint64_t(actual.scissor_width) * actual.scissor_height;
    }
  }

  bw::FramebufferViewportPlan null_actual = {
      {101, 102, 103, 104, 105, 106, 107, 108}, true, 109, 110, 111, 112};
  const bw::FramebufferViewportPlan null_sentinel = null_actual;
  if (!require(!bw::offscreen_viewport_scissor_plan(
                   nullptr, nullptr, 6, 5, 8, null_actual),
               "null offscreen viewport rejected") ||
      !require(plans_equal(null_actual, null_sentinel),
               "null offscreen viewport preserves output") ||
      !require(accepted == 17 && rejected == 3, "offscreen viewport/scissor census") ||
      !require(enabled_scissors == 8, "offscreen enabled-scissor census") ||
      !require(scissor_area == 113, "offscreen scissor aggregate"))
  {
    return false;
  }
  std::puts("CONTRACT offscreen_viewport_scissor_plan PASS cases=21 accepted=17 rejected=4 "
            "scissors=8 scissor_area=113");
  return true;
}

bool compute_dispatch_range_contract()
{
  struct DirectCase {
    int groups_x;
    int groups_y;
    int groups_z;
    int max_x;
    int max_y;
    int max_z;
    bool accepted;
    uint32_t expected_x;
    uint32_t expected_y;
    uint32_t expected_z;
  };
  constexpr std::array<DirectCase, 15> direct_cases = {{
      {1, 1, 1, 65535, 65535, 65535, true, 1, 1, 1},
      {0, 1, 1, 65535, 65535, 65535, true, 0, 1, 1},
      {1, 0, 1, 65535, 65535, 65535, true, 1, 0, 1},
      {1, 1, 0, 65535, 65535, 65535, true, 1, 1, 0},
      {7, 11, 13, 7, 11, 13, true, 7, 11, 13},
      {0, 0, 0, 1, 1, 1, true, 0, 0, 0},
      {-1, 1, 1, 65535, 65535, 65535, false, 0, 0, 0},
      {1, -1, 1, 65535, 65535, 65535, false, 0, 0, 0},
      {1, 1, -1, 65535, 65535, 65535, false, 0, 0, 0},
      {8, 11, 13, 7, 11, 13, false, 0, 0, 0},
      {7, 12, 13, 7, 11, 13, false, 0, 0, 0},
      {7, 11, 14, 7, 11, 13, false, 0, 0, 0},
      {1, 1, 1, 0, 1, 1, false, 0, 0, 0},
      {1, 1, 1, 1, 0, 1, false, 0, 0, 0},
      {1, 1, 1, 1, 1, 0, false, 0, 0, 0},
  }};

  size_t direct_accepted = 0;
  size_t direct_rejected = 0;
  uint64_t accepted_group_sum = 0;
  for (const DirectCase &test : direct_cases) {
    bw::ComputeDispatchPlan actual = {101, 102, 103};
    const bw::ComputeDispatchPlan sentinel = actual;
    const bool result = bw::compute_dispatch_plan(test.groups_x,
                                                  test.groups_y,
                                                  test.groups_z,
                                                  test.max_x,
                                                  test.max_y,
                                                  test.max_z,
                                                  actual);
    if (!require(result == test.accepted, "compute dispatch decision")) {
      return false;
    }
    if (!result) {
      if (!require(actual.groups_x == sentinel.groups_x &&
                       actual.groups_y == sentinel.groups_y &&
                       actual.groups_z == sentinel.groups_z,
                   "rejected compute dispatch preserves output"))
      {
        return false;
      }
      direct_rejected++;
      continue;
    }
    if (!require(actual.groups_x == test.expected_x && actual.groups_y == test.expected_y &&
                     actual.groups_z == test.expected_z,
                 "accepted compute dispatch geometry"))
    {
      return false;
    }
    direct_accepted++;
    accepted_group_sum += actual.groups_x + actual.groups_y + actual.groups_z;
  }

  struct IndirectCase {
    uint64_t offset;
    uint64_t capacity;
    bool accepted;
  };
  constexpr std::array<IndirectCase, 13> indirect_cases = {{
      {0, 12, true},
      {4, 16, true},
      {8, 20, true},
      {12, 24, true},
      {std::numeric_limits<uint64_t>::max() - 15,
       std::numeric_limits<uint64_t>::max(),
       true},
      {0, 0, false},
      {0, 11, false},
      {4, 15, false},
      {1, 32, false},
      {2, 32, false},
      {3, 32, false},
      {std::numeric_limits<uint64_t>::max() - 11,
       std::numeric_limits<uint64_t>::max(),
       false},
      {std::numeric_limits<uint64_t>::max() - 3,
       std::numeric_limits<uint64_t>::max(),
       false},
  }};
  size_t indirect_accepted = 0;
  size_t indirect_rejected = 0;
  for (const IndirectCase &test : indirect_cases) {
    const bool result = bw::compute_indirect_dispatch_range(test.offset, test.capacity);
    if (!require(result == test.accepted, "compute indirect dispatch range")) {
      return false;
    }
    result ? indirect_accepted++ : indirect_rejected++;
  }

  if (!require(direct_accepted == 6 && direct_rejected == 9,
               "direct compute dispatch census") ||
      !require(indirect_accepted == 5 && indirect_rejected == 8,
               "indirect compute dispatch census") ||
      !require(accepted_group_sum == 40, "accepted compute dispatch aggregate"))
  {
    return false;
  }
  std::puts("CONTRACT compute_dispatch_range PASS direct_cases=15 accepted=6 rejected=9 "
            "indirect_cases=13 accepted=5 rejected=8 group_sum=40");
  return true;
}

class CommandScopeFutureProbe {
 public:
  explicit CommandScopeFutureProbe(const size_t index = 0) : index_(index) {}
  size_t index() const
  {
    return index_;
  }

 private:
  size_t index_ = 0;
};

class CommandScopeProbe {
 public:
  using Callback = std::function<void(wgpu::PopErrorScopeStatus,
                                      wgpu::ErrorType,
                                      wgpu::StringView)>;

  void push(wgpu::ErrorFilter)
  {
    pushes_++;
  }

  template<typename CallbackT>
  CommandScopeFutureProbe pop(CallbackT callback)
  {
    const int group = pops_ / 3;
    const bool valid = group == 0 ? encode_valid_ : submit_valid_;
    records_.push_back({valid, false, Callback(std::move(callback))});
    pops_++;
    return CommandScopeFutureProbe(records_.size() - 1);
  }

  wgpu::WaitStatus wait(const CommandScopeFutureProbe future)
  {
    resolve(future.index());
    return wgpu::WaitStatus::Success;
  }

  void resolve_all()
  {
    while (true) {
      size_t unresolved = records_.size();
      for (size_t i = 0; i < records_.size(); i++) {
        if (!records_[i].resolved) {
          unresolved = i;
          break;
        }
      }
      if (unresolved == records_.size()) {
        return;
      }
      const size_t group_end = std::min(unresolved + 3, records_.size());
      for (size_t i = unresolved; i < group_end; i++) {
        resolve(i);
      }
    }
  }

  void set_results(const bool encode_valid, const bool submit_valid)
  {
    encode_valid_ = encode_valid;
    submit_valid_ = submit_valid;
  }

  int pushes() const
  {
    return pushes_;
  }
  int pops() const
  {
    return pops_;
  }

 private:
  struct Record {
    bool valid;
    bool resolved;
    Callback callback;
  };

  void resolve(const size_t index)
  {
    if (index >= records_.size() || records_[index].resolved) {
      return;
    }
    Record &record = records_[index];
    record.resolved = true;
    record.callback(wgpu::PopErrorScopeStatus::Success,
                    record.valid ? wgpu::ErrorType::NoError : wgpu::ErrorType::Validation,
                    wgpu::StringView{});
  }

  bool encode_valid_ = true;
  bool submit_valid_ = true;
  int pushes_ = 0;
  int pops_ = 0;
  std::vector<Record> records_;
};

class CommandScopeInstanceProbe {
 public:
  explicit CommandScopeInstanceProbe(CommandScopeProbe &scope) : scope_(&scope) {}

  wgpu::WaitStatus WaitAny(const CommandScopeFutureProbe future, uint64_t) const
  {
    return scope_->wait(future);
  }

 private:
  CommandScopeProbe *scope_ = nullptr;
};

struct ComputeCommandTrace {
  bool encoder_success = false;
  bool pass_success = false;
  bool command_success = false;
  int encoder_creates = 0;
  int pass_begins = 0;
  int pass_work = 0;
  int pass_ends = 0;
  int finishes = 0;
  int submits = 0;
};

class ComputeCommandBufferProbe {
 public:
  ComputeCommandBufferProbe() = default;
  explicit ComputeCommandBufferProbe(const bool valid) : valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

 private:
  bool valid_ = false;
};

class ComputePassProbe {
 public:
  ComputePassProbe() = default;
  ComputePassProbe(ComputeCommandTrace *trace, const bool valid) : trace_(trace), valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  void Work()
  {
    trace_->pass_work++;
  }

  void End()
  {
    trace_->pass_ends++;
  }

 private:
  ComputeCommandTrace *trace_ = nullptr;
  bool valid_ = false;
};

class ComputeCommandEncoderProbe {
 public:
  ComputeCommandEncoderProbe() = default;
  ComputeCommandEncoderProbe(ComputeCommandTrace *trace, const bool valid)
      : trace_(trace), valid_(valid)
  {
  }

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  ComputePassProbe BeginComputePass()
  {
    trace_->pass_begins++;
    return ComputePassProbe(trace_, trace_->pass_success);
  }

  ComputeCommandBufferProbe Finish()
  {
    trace_->finishes++;
    return ComputeCommandBufferProbe(trace_->command_success);
  }

 private:
  ComputeCommandTrace *trace_ = nullptr;
  bool valid_ = false;
};

class ComputeCommandDeviceProbe {
 public:
  ComputeCommandDeviceProbe(ComputeCommandTrace &trace, CommandScopeProbe &scope)
      : trace_(&trace), scope_(&scope)
  {
  }

  bool operator==(std::nullptr_t) const
  {
    return trace_ == nullptr;
  }

  void PushErrorScope(const wgpu::ErrorFilter filter) const
  {
    scope_->push(filter);
  }

  template<typename CallbackT>
  CommandScopeFutureProbe PopErrorScope(wgpu::CallbackMode, CallbackT callback) const
  {
    return scope_->pop(std::move(callback));
  }

  ComputeCommandEncoderProbe CreateCommandEncoder() const
  {
    trace_->encoder_creates++;
    return ComputeCommandEncoderProbe(trace_, trace_->encoder_success);
  }

 private:
  ComputeCommandTrace *trace_ = nullptr;
  CommandScopeProbe *scope_ = nullptr;
};

class ComputeCommandQueueProbe {
 public:
  explicit ComputeCommandQueueProbe(ComputeCommandTrace &trace) : trace_(&trace) {}

  bool operator==(std::nullptr_t) const
  {
    return trace_ == nullptr;
  }

  void Submit(const size_t count, const ComputeCommandBufferProbe *command_buffer) const
  {
    if (count == 1 && command_buffer != nullptr && !(*command_buffer == nullptr)) {
      trace_->submits++;
    }
  }

 private:
  ComputeCommandTrace *trace_ = nullptr;
};

bool compute_command_transaction_contract()
{
  struct FailureCase {
    bool encoder_success;
    bool pass_success;
    bool command_success;
    bool encode_scope_success;
    bool submit_scope_success;
    int expected_begins;
    int expected_work;
    int expected_ends;
    int expected_finishes;
  };
  constexpr std::array<FailureCase, 6> cases = {{{false, true, true, true, true, 0, 0, 0, 0},
                                                 {true, false, true, true, true, 1, 0, 0, 0},
                                                 {true, true, false, true, true, 1, 1, 1, 1},
                                                 {true, true, true, false, true, 1, 1, 1, 1},
                                                 {true, true, true, true, false, 1, 1, 1, 1},
                                                 {true, true, true, true, true, 1, 1, 1, 1}}};

  int accepted = 0;
  for (const FailureCase &test : cases) {
    ComputeCommandTrace trace;
    trace.encoder_success = test.encoder_success;
    trace.pass_success = test.pass_success;
    trace.command_success = test.command_success;
    CommandScopeProbe scope;
    scope.set_results(test.encode_scope_success, test.submit_scope_success);
    const CommandScopeInstanceProbe instance(scope);
    const ComputeCommandDeviceProbe device(trace, scope);
    const ComputeCommandQueueProbe queue(trace);
    bw::OrderedQueueScheduler scheduler;
    bool completed = false;
    bool result = false;

    bw::command_pass_encode_submit_scoped(
        instance,
        device,
        queue,
        scheduler,
        "",
        [](auto &encoder) { return encoder.BeginComputePass(); },
        [](auto &pass) { pass.Work(); },
        [&](const bool valid) {
          completed = true;
          result = valid;
        });
#ifdef __EMSCRIPTEN__
    if (!require(!completed && trace.submits == 0,
                 "compute command waits for browser error scopes"))
    {
      return false;
    }
    scope.resolve_all();
#endif
    const bool encoded = test.encoder_success && test.pass_success && test.command_success &&
                         test.encode_scope_success;
    const bool expect_success = encoded && test.submit_scope_success;
    if (!require(completed && result == expect_success, "compute command transaction result") ||
        !require(trace.encoder_creates == 1, "compute command encoder creation count") ||
        !require(trace.pass_begins == test.expected_begins, "compute pass begin count") ||
        !require(trace.pass_work == test.expected_work, "compute pass dependent work count") ||
        !require(trace.pass_ends == test.expected_ends, "compute pass end count") ||
        !require(trace.finishes == test.expected_finishes, "compute command finish count") ||
        !require(trace.submits == int(encoded), "compute command submit count") ||
        !require(scope.pushes() == (encoded ? 6 : 3), "compute command scope push count") ||
        !require(scope.pops() == (encoded ? 6 : 3), "compute command scope pop count") ||
        !require(scheduler.pending_count() == 0, "compute command scheduler drained"))
    {
      return false;
    }
    accepted += int(expect_success);
  }

  if (!require(accepted == 1, "compute command transaction success census")) {
    return false;
  }
  std::puts("CONTRACT compute_command_transaction PASS cases=6 accepted=1 "
            "error_objects=2 encoder_fail=closed pass_fail=closed command_fail=closed");
  return true;
}

struct BufferCommandTrace {
  bool encoder_success = true;
  bool encode_success = true;
  bool command_success = true;
  int encoder_creates = 0;
  int copies = 0;
  int finishes = 0;
  int submits = 0;
};

class BufferCommandBufferProbe {
 public:
  BufferCommandBufferProbe() = default;
  explicit BufferCommandBufferProbe(const bool valid) : valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

 private:
  bool valid_ = false;
};

class BufferCommandEncoderProbe {
 public:
  BufferCommandEncoderProbe() = default;
  BufferCommandEncoderProbe(BufferCommandTrace *trace, const bool valid)
      : trace_(trace), valid_(valid)
  {
  }

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  void CopyBufferToBuffer()
  {
    trace_->copies++;
  }

  BufferCommandBufferProbe Finish()
  {
    trace_->finishes++;
    return BufferCommandBufferProbe(trace_->command_success);
  }

 private:
  BufferCommandTrace *trace_ = nullptr;
  bool valid_ = false;
};

class BufferCommandDeviceProbe {
 public:
  BufferCommandDeviceProbe(BufferCommandTrace &trace, CommandScopeProbe &scope)
      : trace_(&trace), scope_(&scope)
  {
  }

  bool operator==(std::nullptr_t) const
  {
    return trace_ == nullptr;
  }

  void PushErrorScope(const wgpu::ErrorFilter filter) const
  {
    scope_->push(filter);
  }

  template<typename CallbackT>
  CommandScopeFutureProbe PopErrorScope(wgpu::CallbackMode, CallbackT callback) const
  {
    return scope_->pop(std::move(callback));
  }

  BufferCommandEncoderProbe CreateCommandEncoder() const
  {
    trace_->encoder_creates++;
    return BufferCommandEncoderProbe(trace_, trace_->encoder_success);
  }

 private:
  BufferCommandTrace *trace_ = nullptr;
  CommandScopeProbe *scope_ = nullptr;
};

class BufferCommandQueueProbe {
 public:
  explicit BufferCommandQueueProbe(BufferCommandTrace &trace) : trace_(&trace) {}

  bool operator==(std::nullptr_t) const
  {
    return trace_ == nullptr;
  }

  void Submit(const size_t count, const BufferCommandBufferProbe *command_buffer) const
  {
    if (count == 1 && command_buffer != nullptr && !(*command_buffer == nullptr)) {
      trace_->submits++;
    }
  }

 private:
  BufferCommandTrace *trace_ = nullptr;
};

bool buffer_command_transaction_contract()
{
  struct FailureCase {
    bool encoder_success;
    bool encode_success;
    bool command_success;
    bool encode_scope_success;
    bool submit_scope_success;
    int expected_copies;
    int expected_finishes;
  };
  constexpr std::array<FailureCase, 6> cases = {{{false, true, true, true, true, 0, 0},
                                                 {true, false, true, true, true, 1, 0},
                                                 {true, true, false, true, true, 1, 1},
                                                 {true, true, true, false, true, 1, 1},
                                                 {true, true, true, true, false, 1, 1},
                                                 {true, true, true, true, true, 1, 1}}};

  int accepted = 0;
  int ordered_followups = 0;
  int canceled_followups = 0;
  int retry_epochs = 0;
  for (const FailureCase &test : cases) {
    BufferCommandTrace trace;
    trace.encoder_success = test.encoder_success;
    trace.encode_success = test.encode_success;
    trace.command_success = test.command_success;
    CommandScopeProbe scope;
    scope.set_results(test.encode_scope_success, test.submit_scope_success);
    const CommandScopeInstanceProbe instance(scope);
    const BufferCommandDeviceProbe device(trace, scope);
    const BufferCommandQueueProbe queue(trace);
    bw::OrderedQueueScheduler scheduler;
    bool completed = false;
    bool result = false;

    bw::command_encode_submit_scoped(
        instance,
        device,
        queue,
        scheduler,
        "",
        [&](auto &encoder) {
          encoder.CopyBufferToBuffer();
          return trace.encode_success;
        },
        [&](const bool valid) {
          completed = true;
          result = valid;
        });
    scheduler.enqueue(
        [&](std::function<void(bool)> done) {
          ordered_followups++;
          done(true);
        },
        [&]() { canceled_followups++; });
#ifdef __EMSCRIPTEN__
    if (!require(!completed && ordered_followups + canceled_followups == int(&test - cases.data()),
                 "later queue work waits for browser validation"))
    {
      return false;
    }
    scope.resolve_all();
#endif
    const bool encoded = test.encoder_success && test.encode_success && test.command_success &&
                         test.encode_scope_success;
    const bool expect_success = encoded && test.submit_scope_success;
    if (!require(completed && result == expect_success, "buffer command transaction result") ||
        !require(trace.encoder_creates == 1, "buffer command encoder creation count") ||
        !require(trace.copies == test.expected_copies, "buffer command copy count") ||
        !require(trace.finishes == test.expected_finishes, "buffer command finish count") ||
        !require(trace.submits == int(encoded), "buffer command submit count") ||
        !require(scheduler.pending_count() == 0, "buffer command scheduler drained"))
    {
      return false;
    }
    scheduler.begin_epoch();
    scheduler.enqueue([&](std::function<void(bool)> done) {
      retry_epochs++;
      done(true);
    });
    accepted += int(expect_success);
  }

  if (!require(accepted == 1, "buffer command transaction success census") ||
      !require(ordered_followups == 1 && canceled_followups == 5,
               "failed epoch cancels later queue work") ||
      !require(retry_epochs == 6, "new epoch retries after failure"))
  {
    return false;
  }
  std::puts("CONTRACT buffer_command_transaction PASS cases=6 accepted=1 error_objects=2 "
            "ordered=1 canceled=5 retry_epochs=6");
  return true;
}

class GhostWindowProbe {
 public:
  explicit GhostWindowProbe(const bool valid) : valid_(valid) {}

  bool getValid() const
  {
    return valid_;
  }

 private:
  bool valid_ = false;
};

bool ghost_window_publication_transaction_contract()
{
  int initialize_calls = 0;
  const bool rejected_context = gw::drawing_context_initialize_if_valid(1, [&]() {
    initialize_calls++;
    return 0;
  });
  const bool accepted_context = gw::drawing_context_initialize_if_valid(1, [&]() {
    initialize_calls++;
    return 1;
  });
  if (!require(!rejected_context && accepted_context && initialize_calls == 2,
               "GHOST drawing-context validity follows exact status"))
  {
    return false;
  }

  GhostWindowProbe invalid_window(false);
  GhostWindowProbe valid_window(true);
  std::array<GhostWindowProbe *, 3> windows = {nullptr, &invalid_window, &valid_window};
  constexpr std::array<int, 3> expected_signatures = {0, 1, 2};
  int destroyed = 0;
  int published = 0;
  for (size_t i = 0; i < windows.size(); i++) {
    int signature = 0;
    GhostWindowProbe *const result = gw::window_publish_if_valid(
        windows[i],
        [&](GhostWindowProbe *window) {
          signature = signature * 10 + 1;
          destroyed++;
          if (window != &invalid_window) {
            signature = -1;
          }
        },
        [&](GhostWindowProbe *window) {
          signature = signature * 10 + 2;
          published++;
          if (window != &valid_window) {
            signature = -1;
          }
        });
    const bool expect_publication = i == 2;
    if (!require(result == (expect_publication ? &valid_window : nullptr),
                 "GHOST window publication result") ||
        !require(signature == expected_signatures[i],
                 "GHOST window publication side-effect order"))
    {
      return false;
    }
  }
  if (!require(destroyed == 1 && published == 1,
               "GHOST invalid window destroyed before valid publication"))
  {
    return false;
  }

  std::puts("CONTRACT ghost_window_publication_transaction PASS cases=5 context=2 "
            "windows=3 accepted=2 invalid=destroyed publication=atomic");
  return true;
}

bool ghost_callback_registration_transaction_contract()
{
  constexpr size_t listener_count = 16;
  size_t failure_rollbacks = 0;
  for (size_t failed_position = 0; failed_position < listener_count; failed_position++) {
    std::array<bool, listener_count> listeners = {};
    size_t attempted = 0;
    size_t rollback_prefix = listener_count + 1;
    bool published = false;
    const bool accepted = gw::sequential_registration_transaction<listener_count>(
        [&](const size_t index) {
          attempted++;
          if (index == failed_position) {
            return false;
          }
          listeners[index] = true;
          return true;
        },
        [&](const size_t registered_count) {
          rollback_prefix = registered_count;
          failure_rollbacks++;
          for (size_t index = 0; index < registered_count; index++) {
            listeners[index] = false;
          }
        },
        [&]() { published = true; });
    if (!require(!accepted && !published, "failed listener set stays unpublished") ||
        !require(attempted == failed_position + 1, "registration stops at first failure") ||
        !require(rollback_prefix == failed_position, "successful listener prefix rolls back") ||
        !require(std::none_of(listeners.begin(), listeners.end(), [](const bool active) {
                   return active;
                 }),
                 "failed listener set leaves no active prefix"))
    {
      return false;
    }
  }

  std::array<uint32_t, listener_count> replacement_listeners = {};
  uint32_t active_owner = 0;
  const auto register_owner = [&](const uint32_t candidate_owner, const size_t failure_position) {
    return gw::sequential_registration_transaction<listener_count>(
        [&](const size_t index) {
          if (index == failure_position) {
            return false;
          }
          replacement_listeners[index] = candidate_owner;
          return true;
        },
        [&](const size_t registered_count) {
          for (size_t index = 0; index < registered_count; index++) {
            replacement_listeners[index] = 0;
          }
        },
        [&]() { active_owner = candidate_owner; });
  };

  const bool initial_accepted = register_owner(1, listener_count);
  replacement_listeners.fill(0);
  active_owner = 0;
  constexpr size_t replacement_failure = 8;
  const bool replacement_rejected = register_owner(2, replacement_failure);
  const bool failed_replacement_clean =
      active_owner == 0 &&
      std::none_of(replacement_listeners.begin(), replacement_listeners.end(),
                   [](const uint32_t owner) { return owner != 0; });
  const bool retry_accepted = register_owner(3, listener_count);
  const bool retry_complete =
      active_owner == 3 &&
      std::all_of(replacement_listeners.begin(), replacement_listeners.end(),
                  [](const uint32_t owner) { return owner == 3; });
  if (!require(failure_rollbacks == listener_count, "every failed position rolls back") ||
      !require(initial_accepted, "initial complete listener set publishes") ||
      !require(!replacement_rejected && replacement_failure == 8 && failed_replacement_clean,
               "failed replacement rolls back before publication") ||
      !require(retry_accepted && retry_complete, "replacement retries after rollback"))
  {
    return false;
  }

  std::puts("CONTRACT ghost_callback_registration_transaction PASS cases=19 "
            "failed_positions=16 replacement=rollback-retry publication=atomic");
  return true;
}

bool ghost_surface_publication_status_contract()
{
  struct Case {
    gw::DrawingContextMode mode;
    bool device_ready;
    gw::PreinitializedPresentationStatus presentation_status;
    bool surface_valid;
    bool backbuffer_valid;
    uint32_t width;
    uint32_t height;
    bool expected;
  };
  constexpr std::array<Case, 13> cases = {{
      {gw::DrawingContextMode::DeviceOnly,
       false,
       gw::PreinitializedPresentationStatus::NotAttempted,
       false,
       false,
       0,
       0,
       false},
      {gw::DrawingContextMode::DeviceOnly,
       true,
       gw::PreinitializedPresentationStatus::NotAttempted,
       false,
       false,
       0,
       0,
       true},
      {gw::DrawingContextMode::PresentableWindow,
       false,
       gw::PreinitializedPresentationStatus::Ready,
       true,
       true,
       1280,
       720,
       false},
      {gw::DrawingContextMode::PresentableWindow,
       true,
       gw::PreinitializedPresentationStatus::NotAttempted,
       false,
       false,
       0,
       0,
       false},
      {gw::DrawingContextMode::PresentableWindow,
       true,
       gw::PreinitializedPresentationStatus::CanvasUnresolved,
       false,
       false,
       0,
       0,
       false},
      {gw::DrawingContextMode::PresentableWindow,
       true,
       gw::PreinitializedPresentationStatus::SurfaceCreationFailed,
       false,
       false,
       0,
       0,
       false},
      {gw::DrawingContextMode::PresentableWindow,
       true,
       gw::PreinitializedPresentationStatus::ConfigurationFailed,
       true,
       false,
       1280,
       720,
       false},
      {gw::DrawingContextMode::PresentableWindow,
       true,
       gw::PreinitializedPresentationStatus::BackbufferFailed,
       true,
       false,
       1280,
       720,
       false},
      {gw::DrawingContextMode::PresentableWindow,
       true,
       gw::PreinitializedPresentationStatus::Ready,
       false,
       true,
       1280,
       720,
       false},
      {gw::DrawingContextMode::PresentableWindow,
       true,
       gw::PreinitializedPresentationStatus::Ready,
       true,
       false,
       1280,
       720,
       false},
      {gw::DrawingContextMode::PresentableWindow,
       true,
       gw::PreinitializedPresentationStatus::Ready,
       true,
       true,
       0,
       720,
       false},
      {gw::DrawingContextMode::PresentableWindow,
       true,
       gw::PreinitializedPresentationStatus::Ready,
       true,
       true,
       1280,
       0,
       false},
      {gw::DrawingContextMode::PresentableWindow,
       true,
       gw::PreinitializedPresentationStatus::Ready,
       true,
       true,
       1280,
       720,
       true},
  }};

  size_t accepted = 0;
  for (const Case &test : cases) {
    const bool result = gw::drawing_context_status_is_ready(test.mode,
                                                            test.device_ready,
                                                            test.presentation_status,
                                                            test.surface_valid,
                                                            test.backbuffer_valid,
                                                            test.width,
                                                            test.height);
    if (!require(result == test.expected, "GHOST surface publication status")) {
      return false;
    }
    accepted += result ? 1 : 0;
  }
  if (!require(accepted == 2, "GHOST device-only/presentable acceptance census")) {
    return false;
  }
  std::puts("CONTRACT ghost_surface_publication_status PASS cases=13 accepted=2 "
            "canvas=required surface=required configuration=required backbuffer=required "
            "device_only=explicit");
  return true;
}

bool ghost_surface_acquisition_status_contract()
{
  struct Case {
    gw::SurfaceAcquireStatus status;
    bool texture_valid;
    gw::SurfaceAcquireAction expected;
  };
  constexpr std::array<Case, 12> cases = {{
      {gw::SurfaceAcquireStatus::SuccessOptimal, true, gw::SurfaceAcquireAction::Present},
      {gw::SurfaceAcquireStatus::SuccessSuboptimal,
       true,
       gw::SurfaceAcquireAction::PresentAndReconfigure},
      {gw::SurfaceAcquireStatus::Timeout, false, gw::SurfaceAcquireAction::Retry},
      {gw::SurfaceAcquireStatus::Outdated, false, gw::SurfaceAcquireAction::Reconfigure},
      {gw::SurfaceAcquireStatus::Lost, false, gw::SurfaceAcquireAction::Recreate},
      {gw::SurfaceAcquireStatus::Error, false, gw::SurfaceAcquireAction::Reconfigure},
      {gw::SurfaceAcquireStatus::SuccessOptimal, false, gw::SurfaceAcquireAction::Reconfigure},
      {gw::SurfaceAcquireStatus::SuccessSuboptimal,
       false,
       gw::SurfaceAcquireAction::Reconfigure},
      {gw::SurfaceAcquireStatus::Timeout, true, gw::SurfaceAcquireAction::Retry},
      {gw::SurfaceAcquireStatus::Outdated, true, gw::SurfaceAcquireAction::Reconfigure},
      {gw::SurfaceAcquireStatus::Lost, true, gw::SurfaceAcquireAction::Recreate},
      {gw::SurfaceAcquireStatus::Error, true, gw::SurfaceAcquireAction::Reconfigure},
  }};

  std::array<size_t, 5> action_counts = {};
  for (const Case &test : cases) {
    const gw::SurfaceAcquireAction action =
        gw::surface_acquire_action(test.status, test.texture_valid);
    if (!require(action == test.expected, "GHOST surface acquisition action")) {
      return false;
    }
    action_counts[size_t(action)]++;
  }
  if (!require(action_counts == std::array<size_t, 5>{1, 1, 2, 6, 2},
               "GHOST surface acquisition action census") ||
      !require(gw::surface_acquire_can_present(gw::SurfaceAcquireAction::Present) &&
                   gw::surface_acquire_can_present(
                       gw::SurfaceAcquireAction::PresentAndReconfigure) &&
                   !gw::surface_acquire_can_present(gw::SurfaceAcquireAction::Retry),
               "GHOST surface acquisition present boundary"))
  {
    return false;
  }

  std::puts("CONTRACT ghost_surface_acquisition_status PASS cases=12 optimal=1 suboptimal=1 "
            "retry=2 reconfigure=6 recreate=2 failure=propagated");
  return true;
}

bool ghost_device_loss_state_contract()
{
  struct Case {
    gw::DeviceState current;
    uint32_t bound_generation;
    uint32_t observed_generation;
    gw::ImportedDeviceLossStatus status;
    gw::DeviceState expected;
  };
  constexpr std::array<Case, 7> cases = {{
      {gw::DeviceState::Active,
       7,
       7,
       gw::ImportedDeviceLossStatus::Pending,
       gw::DeviceState::Active},
      {gw::DeviceState::Active,
       7,
       7,
       gw::ImportedDeviceLossStatus::Unknown,
       gw::DeviceState::Lost},
      {gw::DeviceState::Active,
       7,
       7,
       gw::ImportedDeviceLossStatus::Destroyed,
       gw::DeviceState::Lost},
      {gw::DeviceState::Active,
       7,
       8,
       gw::ImportedDeviceLossStatus::Pending,
       gw::DeviceState::Lost},
      {gw::DeviceState::Active,
       7,
       0,
       gw::ImportedDeviceLossStatus::Pending,
       gw::DeviceState::Lost},
      {gw::DeviceState::Active,
       0,
       0,
       gw::ImportedDeviceLossStatus::Pending,
       gw::DeviceState::Lost},
      {gw::DeviceState::Lost,
       7,
       7,
       gw::ImportedDeviceLossStatus::Pending,
       gw::DeviceState::Lost},
  }};

  size_t lost = 0;
  for (const Case &test : cases) {
    const gw::DeviceState result = gw::device_state_after_loss_signal(test.current,
                                                                      test.bound_generation,
                                                                      test.observed_generation,
                                                                      test.status);
    if (!require(result == test.expected, "GHOST device-loss transition")) {
      return false;
    }
    lost += result == gw::DeviceState::Lost ? 1 : 0;
  }

  if (!require(lost == 6, "GHOST device-loss transition census") ||
      !require(gw::device_state_allows_work(gw::DeviceState::Active),
               "GHOST active device permits work") ||
      !require(!gw::device_state_allows_work(gw::DeviceState::Lost),
               "GHOST lost device blocks work") ||
      !require(gw::surface_acquire_can_present(
                   gw::surface_acquire_action(gw::SurfaceAcquireStatus::SuccessOptimal, true)) &&
                   !gw::device_state_allows_work(gw::DeviceState::Lost),
               "GHOST device loss overrides apparently successful surface acquisition"))
  {
    return false;
  }

  std::weak_ptr<std::atomic<gw::DeviceState>> weak_state;
  std::function<void()> delayed_loss;
  {
    auto callback_state = std::make_shared<std::atomic<gw::DeviceState>>(gw::DeviceState::Active);
    weak_state = callback_state;
    delayed_loss = [callback_state]() { gw::device_state_mark_lost(*callback_state); };
  }
  if (!require(!weak_state.expired(), "GHOST loss callback retains only shared terminal state")) {
    return false;
  }
  delayed_loss();
  auto callback_state = weak_state.lock();
  if (!require(callback_state != nullptr &&
                   callback_state->load(std::memory_order_acquire) == gw::DeviceState::Lost,
               "GHOST delayed loss callback marks terminal state after owner lifetime"))
  {
    return false;
  }
  callback_state.reset();
  delayed_loss = nullptr;
  if (!require(weak_state.expired(), "GHOST loss callback releases shared state after delivery")) {
    return false;
  }

  std::puts("CONTRACT ghost_device_loss_state PASS cases=13 transitions=7 lost=6 work=3 "
            "generation=bound terminal=sticky callback=lifetime_safe");
  return true;
}

bool ghost_device_loss_inflight_cancel_contract()
{
  struct Trace {
    int configure = 0;
    int backbuffer_publications = 0;
    int pipeline_publications = 0;
    int submits = 0;
    int present_notes = 0;

    int total() const
    {
      return configure + backbuffer_publications + pipeline_publications + submits +
             present_notes;
    }
  };

  const auto exercise = [](const bool lose_before_completion) {
    auto state = std::make_shared<std::atomic<gw::DeviceState>>(gw::DeviceState::Active);
    Trace trace;
    std::array<std::function<void()>, 5> completions = {{
        [state, &trace]() {
          if (!gw::device_state_allows_callback_work(state)) {
            return;
          }
          trace.configure++;
        },
        [state, &trace]() {
          if (!gw::device_state_allows_callback_work(state)) {
            return;
          }
          trace.backbuffer_publications++;
        },
        [state, &trace]() {
          if (!gw::device_state_allows_callback_work(state)) {
            return;
          }
          trace.pipeline_publications++;
        },
        [state, &trace]() {
          if (!gw::device_state_allows_callback_work(state)) {
            return;
          }
          trace.submits++;
        },
        [state, &trace]() {
          if (!gw::device_state_allows_callback_work(state)) {
            return;
          }
          trace.present_notes++;
        },
    }};

    if (lose_before_completion) {
      gw::device_state_mark_lost(*state);
    }
    for (const std::function<void()> &complete : completions) {
      complete();
    }
    return trace;
  };

  const Trace active = exercise(false);
  const Trace lost = exercise(true);
  if (!require(active.configure == 1 && active.backbuffer_publications == 1 &&
                   active.pipeline_publications == 1 && active.submits == 1 &&
                   active.present_notes == 1,
               "GHOST active in-flight callbacks complete") ||
      !require(lost.total() == 0,
               "GHOST terminal loss cancels every in-flight callback before owner work"))
  {
    return false;
  }

  std::puts("CONTRACT ghost_device_loss_inflight_cancel PASS cases=10 active=5 lost=5 "
            "configure=0 publication=0 submit=0 present=0");
  return true;
}

class GhostHandleProbe {
 public:
  GhostHandleProbe() = default;
  explicit GhostHandleProbe(const int identity) : identity_(identity) {}

  bool operator==(std::nullptr_t) const
  {
    return identity_ == 0;
  }

  int identity() const
  {
    return identity_;
  }

 private:
  int identity_ = 0;
};

class GhostScopeProbe {
 public:
  void begin()
  {
    begins_++;
  }

  template<typename CompleteFn> void end(CompleteFn &&complete)
  {
    ends_++;
    completion_ = std::forward<CompleteFn>(complete);
  }

  bool pending() const
  {
    return bool(completion_);
  }

  void resolve(const bool valid)
  {
    std::function<void(bool)> completion = std::move(completion_);
    completion_ = nullptr;
    completion(valid);
  }

  int begins() const
  {
    return begins_;
  }

  int ends() const
  {
    return ends_;
  }

 private:
  int begins_ = 0;
  int ends_ = 0;
  std::function<void(bool)> completion_;
};

struct GhostFrameTrace {
  int failure_stage = 8;
  uint64_t signature = 0;
  bool dependencies_valid = true;
  int submits = 0;

  void step(const uint64_t value)
  {
    signature = signature * 10 + value;
  }
};

class GhostFramePassProbe {
 public:
  GhostFramePassProbe() = default;
  GhostFramePassProbe(GhostFrameTrace *trace, const bool valid) : trace_(trace), valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  void End()
  {
    trace_->step(7);
  }

 private:
  GhostFrameTrace *trace_ = nullptr;
  bool valid_ = false;
};

class GhostFrameEncoderProbe {
 public:
  GhostFrameEncoderProbe() = default;
  GhostFrameEncoderProbe(GhostFrameTrace *trace, const bool valid) : trace_(trace), valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  GhostHandleProbe Finish()
  {
    trace_->step(8);
    return trace_->failure_stage == 5 ? GhostHandleProbe() : GhostHandleProbe(35);
  }

 private:
  GhostFrameTrace *trace_ = nullptr;
  bool valid_ = false;
};

bool ghost_present_resource_transaction_contract()
{
  int accepted = 0;

  for (int texture_case = 0; texture_case < 3; texture_case++) {
    GhostScopeProbe scope;
    GhostHandleProbe texture(71);
    uint32_t texture_width = 17;
    uint32_t texture_height = 19;
    bool completed = false;
    bool result = false;
    gw::scoped_handle_create(
        [&]() { scope.begin(); },
        [&]() {
          return texture_case == 0 ? GhostHandleProbe() : GhostHandleProbe(72);
        },
        [&](auto completion) { scope.end(std::move(completion)); },
        [&](const bool valid, GhostHandleProbe candidate) {
          completed = true;
          result = valid;
          if (valid) {
            texture = std::move(candidate);
            texture_width = 1280;
            texture_height = 720;
          }
        });
    if (!require(scope.begins() == 1 && scope.ends() == 1 && scope.pending(),
                 "GHOST backbuffer scope is balanced and pending") ||
        !require(!completed && texture.identity() == 71 && texture_width == 17 &&
                     texture_height == 19,
                 "GHOST backbuffer is unpublished before scope completion"))
    {
      return false;
    }
    scope.resolve(texture_case == 2);
    const bool expect_success = texture_case == 2;
    if (!require(completed && result == expect_success,
                 "GHOST backbuffer scope controls publication") ||
        !require(expect_success ?
                     texture.identity() == 72 && texture_width == 1280 && texture_height == 720 :
                     texture.identity() == 71 && texture_width == 17 && texture_height == 19,
                 "GHOST backbuffer publication is atomic"))
    {
      return false;
    }
    accepted += int(expect_success);
  }

  for (int failure_stage = 0; failure_stage <= 5; failure_stage++) {
    GhostScopeProbe scope;
    uint64_t signature = 0;
    bool dependencies_valid = true;
    GhostHandleProbe bind_group_layout(81);
    GhostHandleProbe pipeline(82);
    bool completed = false;
    bool result = false;
    gw::present_pipeline_create_scoped(
        [&]() { scope.begin(); },
        [&]() {
          signature = signature * 10 + 1;
          return failure_stage == 0 ? GhostHandleProbe() : GhostHandleProbe(11);
        },
        [&]() {
          signature = signature * 10 + 2;
          return failure_stage == 1 ? GhostHandleProbe() : GhostHandleProbe(12);
        },
        [&](const GhostHandleProbe &candidate_layout) {
          signature = signature * 10 + 3;
          dependencies_valid &= candidate_layout.identity() == 12;
          return failure_stage == 2 ? GhostHandleProbe() : GhostHandleProbe(13);
        },
        [&](const GhostHandleProbe &module, const GhostHandleProbe &layout) {
          signature = signature * 10 + 4;
          dependencies_valid &= module.identity() == 11 && layout.identity() == 13;
          return failure_stage == 3 ? GhostHandleProbe() : GhostHandleProbe(14);
        },
        [&](auto completion) { scope.end(std::move(completion)); },
        [&](const bool valid, GhostHandleProbe candidate_layout, GhostHandleProbe candidate_pipeline) {
          completed = true;
          result = valid;
          if (valid) {
            bind_group_layout = std::move(candidate_layout);
            pipeline = std::move(candidate_pipeline);
          }
        });
    if (!require(scope.begins() == 1 && scope.ends() == 1 && scope.pending(),
                 "GHOST pipeline scope is balanced and pending") ||
        !require(!completed && bind_group_layout.identity() == 81 && pipeline.identity() == 82,
                 "GHOST pipeline is unpublished before scope completion"))
    {
      return false;
    }
    scope.resolve(failure_stage != 4);
    const bool expect_success = failure_stage == 5;
    const uint64_t expected_signature = failure_stage == 0 ? 1 :
                                        failure_stage == 1 ? 12 :
                                        failure_stage == 2 ? 123 : 1234;
    if (!require(completed && result == expect_success,
                 "GHOST pipeline transaction result") ||
        !require(signature == expected_signature, "GHOST pipeline transaction call order") ||
        !require(dependencies_valid, "GHOST pipeline transaction dependency handles") ||
        !require(expect_success ?
                     bind_group_layout.identity() == 12 && pipeline.identity() == 14 :
                     bind_group_layout.identity() == 81 && pipeline.identity() == 82,
                 "GHOST pipeline transaction atomic publication"))
    {
      return false;
    }
    accepted += int(expect_success);
  }

  constexpr std::array<uint64_t, 9> expected_before_scope = {
      1, 12, 123, 1234, 12345, 12345678, 123456789, 123456789, 123456789};
  for (int failure_stage = 0; failure_stage <= 8; failure_stage++) {
    GhostFrameTrace trace;
    trace.failure_stage = failure_stage;
    GhostScopeProbe encode_scope;
    GhostScopeProbe submit_scope;
    bool completed = false;
    bool result = false;
    gw::present_frame_encode_submit_scoped(
        [&]() { encode_scope.begin(); },
        [&]() {
          trace.step(1);
          return failure_stage == 0 ? GhostHandleProbe() : GhostHandleProbe(21);
        },
        [&]() {
          trace.step(2);
          return failure_stage == 1 ? GhostHandleProbe() : GhostHandleProbe(22);
        },
        [&](const GhostHandleProbe &source_view) {
          trace.step(3);
          trace.dependencies_valid &= source_view.identity() == 21;
          return failure_stage == 2 ? GhostHandleProbe() : GhostHandleProbe(23);
        },
        [&]() {
          trace.step(4);
          return GhostFrameEncoderProbe(&trace, failure_stage != 3);
        },
        [&](GhostFrameEncoderProbe &encoder, const GhostHandleProbe &target_view) {
          trace.step(5);
          trace.dependencies_valid &= !(encoder == nullptr) && target_view.identity() == 22;
          return GhostFramePassProbe(&trace, failure_stage != 4);
        },
        [&](GhostFramePassProbe &pass, const GhostHandleProbe &bind_group) {
          trace.step(6);
          trace.dependencies_valid &= !(pass == nullptr) && bind_group.identity() == 23;
        },
        [&](auto completion) { encode_scope.end(std::move(completion)); },
        [&]() { submit_scope.begin(); },
        [&](const GhostHandleProbe &command_buffer) {
          trace.step(9);
          trace.dependencies_valid &= command_buffer.identity() == 35;
          trace.submits++;
        },
        [&](auto completion) { submit_scope.end(std::move(completion)); },
        [&](const bool valid) {
          completed = true;
          result = valid;
        });
    const bool has_complete_command = failure_stage >= 6;
    if (!require(encode_scope.begins() == 1 && encode_scope.ends() == 1 &&
                     encode_scope.pending(),
                 "GHOST frame encode scope is balanced and pending") ||
        !require(submit_scope.pending() == has_complete_command,
                 "GHOST frame submit scope exists exactly for a complete command") ||
        !require(!completed && trace.submits == int(has_complete_command),
                 "GHOST complete surface command submits in the caller tick") ||
        !require(trace.signature == expected_before_scope[size_t(failure_stage)],
                 "GHOST frame pre-scope call order"))
    {
      return false;
    }

    if (has_complete_command) {
      const bool encode_valid = failure_stage != 6;
      const bool submit_valid = failure_stage != 7;
      if ((failure_stage & 1) == 0) {
        encode_scope.resolve(encode_valid);
        if (!require(!completed, "GHOST present joins the pending submit scope")) {
          return false;
        }
        submit_scope.resolve(submit_valid);
      }
      else {
        submit_scope.resolve(submit_valid);
        if (!require(!completed, "GHOST present joins the pending encode scope")) {
          return false;
        }
        encode_scope.resolve(encode_valid);
      }
    }
    else {
      encode_scope.resolve(false);
      if (!require(!submit_scope.pending(),
                   "GHOST invalid handle path does not open a submit scope"))
      {
        return false;
      }
    }

    const bool expect_success = failure_stage == 8;
    const uint64_t expected_signature = expected_before_scope[size_t(failure_stage)];
    if (!require(completed && result == expect_success, "GHOST frame transaction result") ||
        !require(trace.signature == expected_signature, "GHOST frame transaction call order") ||
        !require(trace.dependencies_valid, "GHOST frame transaction dependency handles") ||
        !require(trace.submits == int(has_complete_command),
                 "GHOST frame transaction submit count"))
    {
      return false;
    }
    accepted += int(expect_success);
  }

  if (!require(accepted == 3, "GHOST present transaction success census")) {
    return false;
  }
  std::puts("CONTRACT ghost_present_resource_transaction PASS cases=18 backbuffer=3 "
            "pipeline=6 frame=9 error_objects=3 publication=scoped submit=3 same_tick=3 "
            "dual_scope=3 committed=1");
  return true;
}

bool ghost_resize_coherence_contract()
{
  GhostHandleProbe backbuffer(71);
  uint32_t authoritative_width = 640;
  uint32_t authoritative_height = 480;
  uint32_t backbuffer_width = 640;
  uint32_t backbuffer_height = 480;
  uint32_t requested_width = 640;
  uint32_t requested_height = 480;
  bool configured = true;

  if (!require(!gw::surface_resize_candidate_needed(configured,
                                                     authoritative_width,
                                                     authoritative_height,
                                                     requested_width,
                                                     requested_height,
                                                     false,
                                                     backbuffer != nullptr,
                                                     backbuffer_width,
                                                     backbuffer_height),
               "GHOST coherent settled resize needs no candidate"))
  {
    return false;
  }

  requested_width = 1280;
  requested_height = 720;
  if (!require(gw::surface_resize_candidate_needed(configured,
                                                    authoritative_width,
                                                    authoritative_height,
                                                    requested_width,
                                                    requested_height,
                                                    false,
                                                    backbuffer != nullptr,
                                                    backbuffer_width,
                                                    backbuffer_height),
               "GHOST new resize needs a candidate") ||
      !require(!gw::surface_resize_candidate_needed(configured,
                                                     authoritative_width,
                                                     authoritative_height,
                                                     requested_width,
                                                     requested_height,
                                                     true,
                                                     backbuffer != nullptr,
                                                     backbuffer_width,
                                                     backbuffer_height),
               "GHOST pending resize suppresses duplicate candidates"))
  {
    return false;
  }

  int configure_calls = 0;
  uint32_t configured_width = 0;
  uint32_t configured_height = 0;
  bool configure_saw_old_publication = true;
  const auto configure = [&](const uint32_t width, const uint32_t height) {
    configure_calls++;
    configured_width = width;
    configured_height = height;
    configure_saw_old_publication &= backbuffer.identity() == 71 &&
                                     authoritative_width == 640 && authoritative_height == 480 &&
                                     backbuffer_width == 640 && backbuffer_height == 480;
  };

  auto result = gw::surface_resize_commit_if_current(false,
                                                      GhostHandleProbe(72),
                                                      1280,
                                                      720,
                                                      requested_width,
                                                      requested_height,
                                                      configure,
                                                      backbuffer,
                                                      backbuffer_width,
                                                      backbuffer_height,
                                                      authoritative_width,
                                                      authoritative_height,
                                                      configured);
  if (!require(result == gw::SurfaceResizeResult::Rejected && configure_calls == 0 &&
                   backbuffer.identity() == 71 && authoritative_width == 640 &&
                   authoritative_height == 480 && backbuffer_width == 640 &&
                   backbuffer_height == 480,
               "GHOST non-null error texture preserves coherent old state") ||
      !require(gw::surface_resize_candidate_needed(configured,
                                                    authoritative_width,
                                                    authoritative_height,
                                                    requested_width,
                                                    requested_height,
                                                    false,
                                                    backbuffer != nullptr,
                                                    backbuffer_width,
                                                    backbuffer_height),
               "GHOST rejected resize remains retryable without a new request") ||
      !require(gw::surface_resize_present_coherent(
                   true, 640, 480, true, 640, 480, 640, 480),
               "GHOST rejected resize preserves the old presentable state"))
  {
    return false;
  }

  result = gw::surface_resize_commit_if_current(true,
                                                GhostHandleProbe(),
                                                1280,
                                                720,
                                                requested_width,
                                                requested_height,
                                                configure,
                                                backbuffer,
                                                backbuffer_width,
                                                backbuffer_height,
                                                authoritative_width,
                                                authoritative_height,
                                                configured);
  if (!require(result == gw::SurfaceResizeResult::Rejected && configure_calls == 0 &&
                   backbuffer.identity() == 71 && authoritative_width == 640 &&
                   authoritative_height == 480,
               "GHOST null resize texture preserves coherent old state"))
  {
    return false;
  }

  result = gw::surface_resize_commit_if_current(true,
                                                GhostHandleProbe(73),
                                                800,
                                                600,
                                                requested_width,
                                                requested_height,
                                                configure,
                                                backbuffer,
                                                backbuffer_width,
                                                backbuffer_height,
                                                authoritative_width,
                                                authoritative_height,
                                                configured);
  if (!require(result == gw::SurfaceResizeResult::Superseded && configure_calls == 0 &&
                   backbuffer.identity() == 71 && authoritative_width == 640 &&
                   authoritative_height == 480,
               "GHOST superseded resize cannot publish stale extents") ||
      !require(gw::surface_resize_candidate_needed(configured,
                                                    authoritative_width,
                                                    authoritative_height,
                                                    requested_width,
                                                    requested_height,
                                                    false,
                                                    backbuffer != nullptr,
                                                    backbuffer_width,
                                                    backbuffer_height),
               "GHOST superseded resize keeps the newest request retryable"))
  {
    return false;
  }

  result = gw::surface_resize_commit_if_current(true,
                                                GhostHandleProbe(74),
                                                1280,
                                                720,
                                                requested_width,
                                                requested_height,
                                                configure,
                                                backbuffer,
                                                backbuffer_width,
                                                backbuffer_height,
                                                authoritative_width,
                                                authoritative_height,
                                                configured);
  if (!require(result == gw::SurfaceResizeResult::Committed && configure_calls == 1 &&
                   configured_width == 1280 && configured_height == 720 &&
                   configure_saw_old_publication && backbuffer.identity() == 74 &&
                   authoritative_width == 1280 && authoritative_height == 720 &&
                   backbuffer_width == 1280 && backbuffer_height == 720 && configured,
               "GHOST accepted resize configures then publishes one coherent state") ||
      !require(!gw::surface_resize_candidate_needed(configured,
                                                     authoritative_width,
                                                     authoritative_height,
                                                     requested_width,
                                                     requested_height,
                                                     false,
                                                     backbuffer != nullptr,
                                                     backbuffer_width,
                                                     backbuffer_height),
               "GHOST committed resize stops retrying"))
  {
    return false;
  }

  if (!require(gw::surface_resize_present_coherent(true, 1280, 720, true, 1280, 720, 1280, 720),
               "GHOST exact extents may present") ||
      !require(!gw::surface_resize_present_coherent(
                   false, 1280, 720, true, 1280, 720, 1280, 720),
               "GHOST unconfigured surface cannot present") ||
      !require(!gw::surface_resize_present_coherent(
                   true, 1280, 720, false, 1280, 720, 1280, 720),
               "GHOST missing backbuffer cannot present") ||
      !require(!gw::surface_resize_present_coherent(
                   true, 1280, 720, true, 640, 480, 1280, 720),
               "GHOST stale backbuffer cannot present") ||
      !require(!gw::surface_resize_present_coherent(
                   true, 1280, 720, true, 1280, 720, 640, 720),
               "GHOST mismatched surface width cannot present") ||
      !require(!gw::surface_resize_present_coherent(
                   true, 1280, 720, true, 1280, 720, 1280, 480),
               "GHOST mismatched surface height cannot present"))
  {
    return false;
  }

  std::puts("CONTRACT ghost_resize_coherence PASS cases=17 candidates=10 present=7 "
            "failure=preserved superseded=retried commit=atomic retry=no_event");
  return true;
}

wgpu::VertexFormat expected_32bit_format(const blender::GPUVertCompType component,
                                         const int component_len)
{
  using VF = wgpu::VertexFormat;
  if (component == blender::GPU_COMP_F32) {
    constexpr std::array<VF, 4> formats = {
        VF::Float32, VF::Float32x2, VF::Float32x3, VF::Float32x4};
    return formats[size_t(component_len - 1)];
  }
  if (component == blender::GPU_COMP_I32) {
    constexpr std::array<VF, 4> formats = {
        VF::Sint32, VF::Sint32x2, VF::Sint32x3, VF::Sint32x4};
    return formats[size_t(component_len - 1)];
  }
  constexpr std::array<VF, 4> formats = {
      VF::Uint32, VF::Uint32x2, VF::Uint32x3, VF::Uint32x4};
  return formats[size_t(component_len - 1)];
}

bool format_32bit_contract()
{
  constexpr std::array components = {
      blender::GPU_COMP_F32, blender::GPU_COMP_I32, blender::GPU_COMP_U32};
  constexpr std::array fetch_modes = {blender::GPU_FETCH_FLOAT,
                                      blender::GPU_FETCH_INT,
                                      blender::GPU_FETCH_INT_TO_FLOAT_UNIT};
  size_t cases = 0;
  for (const blender::GPUVertCompType component : components) {
    for (int component_len = 1; component_len <= 4; component_len++) {
      for (const blender::GPUVertFetchMode fetch : fetch_modes) {
        if (!require(bw::to_wgpu_vertex_format(component, component_len, fetch) ==
                         expected_32bit_format(component, component_len),
                     "32-bit vertex format mapping"))
        {
          return false;
        }
        cases++;
      }
    }
  }
  if (!require(cases == 36, "32-bit vertex format census")) {
    return false;
  }
  std::puts("CONTRACT format_32bit PASS cases=36");
  return true;
}

wgpu::VertexFormat expected_subword_format(const blender::GPUVertCompType component,
                                           const int component_len,
                                           const bool normalized)
{
  using VF = wgpu::VertexFormat;
  const bool pair = component_len <= 2;
  switch (component) {
    case blender::GPU_COMP_I8:
      return normalized ? (pair ? VF::Snorm8x2 : VF::Snorm8x4) :
                          (pair ? VF::Sint8x2 : VF::Sint8x4);
    case blender::GPU_COMP_U8:
      return normalized ? (pair ? VF::Unorm8x2 : VF::Unorm8x4) :
                          (pair ? VF::Uint8x2 : VF::Uint8x4);
    case blender::GPU_COMP_I16:
      return normalized ? (pair ? VF::Snorm16x2 : VF::Snorm16x4) :
                          (pair ? VF::Sint16x2 : VF::Sint16x4);
    case blender::GPU_COMP_U16:
      return normalized ? (pair ? VF::Unorm16x2 : VF::Unorm16x4) :
                          (pair ? VF::Uint16x2 : VF::Uint16x4);
    default:
      return VF::Float32x4;
  }
}

bool format_subword_contract()
{
  constexpr std::array components = {blender::GPU_COMP_I8,
                                     blender::GPU_COMP_U8,
                                     blender::GPU_COMP_I16,
                                     blender::GPU_COMP_U16};
  constexpr std::array fetch_modes = {blender::GPU_FETCH_FLOAT,
                                      blender::GPU_FETCH_INT,
                                      blender::GPU_FETCH_INT_TO_FLOAT_UNIT};
  size_t cases = 0;
  for (const blender::GPUVertCompType component : components) {
    for (int component_len = 1; component_len <= 4; component_len++) {
      for (const blender::GPUVertFetchMode fetch : fetch_modes) {
        const bool normalized = fetch == blender::GPU_FETCH_INT_TO_FLOAT_UNIT;
        if (!require(bw::to_wgpu_vertex_format(component, component_len, fetch) ==
                         expected_subword_format(component, component_len, normalized),
                     "subword vertex format mapping"))
        {
          return false;
        }
        cases++;
      }
    }
  }
  if (!require(cases == 48, "subword vertex format census")) {
    return false;
  }
  std::puts("CONTRACT format_subword PASS cases=48");
  return true;
}

bool format_i10_contract()
{
  constexpr std::array fetch_modes = {blender::GPU_FETCH_FLOAT,
                                      blender::GPU_FETCH_INT,
                                      blender::GPU_FETCH_INT_TO_FLOAT_UNIT};
  size_t cases = 0;
  size_t signed_cases = 0;
  for (int component_len = 1; component_len <= 4; component_len++) {
    for (const blender::GPUVertFetchMode fetch : fetch_modes) {
      const bool normalized = fetch == blender::GPU_FETCH_INT_TO_FLOAT_UNIT;
      const wgpu::VertexFormat expected = normalized ? wgpu::VertexFormat::Snorm8x4 :
                                                       wgpu::VertexFormat::Unorm10_10_10_2;
      if (!require(bw::to_wgpu_vertex_format(blender::GPU_COMP_I10, component_len, fetch) ==
                       expected,
                   "signed I10 vertex format mapping"))
      {
        return false;
      }
      cases++;
      signed_cases += normalized ? 1 : 0;
    }
  }
  if (!require(cases == 12, "I10 vertex format census") ||
      !require(signed_cases == 4, "normalized I10 census"))
  {
    return false;
  }
  std::puts("CONTRACT format_i10 PASS cases=12 normalized=4");
  return true;
}

bool dummy_vertex_contract()
{
  using T = blender::gpu::shader::Type;
  using VF = wgpu::VertexFormat;
  struct Expected {
    T type;
    VF format;
  };
  constexpr std::array<Expected, 32> expected = {{
      {T::float_t, VF::Float32},
      {T::float2_t, VF::Float32x2},
      {T::float3_t, VF::Float32x3},
      {T::float4_t, VF::Float32x4},
      {T::float3x3_t, VF::Float32x4},
      {T::float4x4_t, VF::Float32x4},
      {T::uint_t, VF::Uint32},
      {T::uint2_t, VF::Uint32x2},
      {T::uint3_t, VF::Uint32x3},
      {T::uint4_t, VF::Uint32x4},
      {T::int_t, VF::Sint32},
      {T::int2_t, VF::Sint32x2},
      {T::int3_t, VF::Sint32x3},
      {T::int4_t, VF::Sint32x4},
      {T::bool_t, VF::Uint32},
      {T::float3_10_10_10_2_t, VF::Float32x3},
      {T::uchar_t, VF::Uint32},
      {T::uchar2_t, VF::Uint32x2},
      {T::uchar3_t, VF::Uint32x3},
      {T::uchar4_t, VF::Uint32x4},
      {T::char_t, VF::Sint32},
      {T::char2_t, VF::Sint32x2},
      {T::char3_t, VF::Sint32x3},
      {T::char4_t, VF::Sint32x4},
      {T::ushort_t, VF::Uint32},
      {T::ushort2_t, VF::Uint32x2},
      {T::ushort3_t, VF::Uint32x3},
      {T::ushort4_t, VF::Uint32x4},
      {T::short_t, VF::Sint32},
      {T::short2_t, VF::Sint32x2},
      {T::short3_t, VF::Sint32x3},
      {T::short4_t, VF::Sint32x4},
  }};

  for (size_t index = 0; index < expected.size(); index++) {
    const uint32_t location = uint32_t(index % 16);
    const bw::VertexBinding binding =
        bw::dummy_vertex_binding(location, uint8_t(expected[index].type));
    if (!require(binding.vbo_index == -1 && binding.is_dummy,
                 "dummy source identity") ||
        !require(binding.buffer_offset == 0, "dummy buffer offset") ||
        !require(binding.array_stride == 0, "dummy zero stride") ||
        !require(binding.step_mode == wgpu::VertexStepMode::Vertex,
                 "dummy vertex step mode") ||
        !require(binding.attributes.size() == 1, "dummy attribute count") ||
        !require(binding.attributes[0].format == expected[index].format,
                 "dummy attribute format") ||
        !require(binding.attributes[0].offset == 0, "dummy attribute offset") ||
        !require(binding.attributes[0].shaderLocation == location,
                 "dummy shader location"))
    {
      return false;
    }
  }

  std::puts("CONTRACT dummy_vertex PASS cases=32 stride=0 step=vertex");
  return true;
}

bool shader_lifetime_cache_contract()
{
  /* Reproduce allocator address reuse without constructing a device-backed shader:
   * the render-pipeline hash must distinguish successive lifetimes at one address. */
  auto *reused_address =
      reinterpret_cast<blender::gpu::WGPUShader *>(uintptr_t{0x1000});
  constexpr uint64_t identity_count = 4096;
  const auto identity_hash = [](const bw::PipelineInfo &info) {
    uint64_t hash = 1469598103934665603ull;
    bw::hash_shader_identity(hash, info.shader, info.shader_cache_identity);
    return hash;
  };
  std::unordered_set<uint64_t> hashes;
  hashes.reserve(identity_count);
  for (uint64_t identity = 1; identity <= identity_count; identity++) {
    const bw::PipelineInfo info(reused_address, identity);
    hashes.insert(identity_hash(info));
  }

  const bw::PipelineInfo first(reused_address, 1);
  const bw::PipelineInfo same_lifetime(reused_address, 1);
  const bw::PipelineInfo replacement(reused_address, 2);
  if (!require(identity_hash(first) == identity_hash(same_lifetime),
               "same shader lifetime cache identity") ||
      !require(identity_hash(first) != identity_hash(replacement),
               "reused shader address cache separation") ||
      !require(hashes.size() == identity_count, "shader lifetime hash census"))
  {
    return false;
  }

  std::puts("CONTRACT shader_lifetime_cache PASS cases=4096 unique=4096");
  return true;
}

bool vertex_alias_cache_key_contract()
{
  /* Attribute aliases participate in shader-location matching. Distinct valid alias
   * sequences must therefore remain distinct in the render-pipeline cache key, even
   * when their bytes concatenate to the same undelimited string. */
  blender::GPUVertFormat split_after_first{};
  blender::GPU_vertformat_clear(&split_after_first);
  blender::GPU_vertformat_attr_add(
      &split_after_first, "a", blender::gpu::VertAttrType::SFLOAT_32);
  blender::GPU_vertformat_alias_add(&split_after_first, "bc");
  split_after_first.pack();

  blender::GPUVertFormat split_after_second{};
  blender::GPU_vertformat_clear(&split_after_second);
  blender::GPU_vertformat_attr_add(
      &split_after_second, "ab", blender::gpu::VertAttrType::SFLOAT_32);
  blender::GPU_vertformat_alias_add(&split_after_second, "c");
  split_after_second.pack();

  auto *shader = reinterpret_cast<blender::gpu::WGPUShader *>(uintptr_t{0x2000});
  bw::PipelineInfo first(shader, 1);
  first.vertex_formats[0] = &split_after_first;
  first.vertex_lens[0] = 1;
  first.vertex_formats_len = 1;
  bw::PipelineInfo second(shader, 1);
  second.vertex_formats[0] = &split_after_second;
  second.vertex_lens[0] = 1;
  second.vertex_formats_len = 1;

  const blender::GPUVertAttr &first_attr = split_after_first.attrs[0];
  const blender::GPUVertAttr &second_attr = split_after_second.attrs[0];
  const char *first_name = blender::GPU_vertformat_attr_name_get(
      &split_after_first, &first_attr, 0);
  const char *first_alias = blender::GPU_vertformat_attr_name_get(
      &split_after_first, &first_attr, 1);
  const char *second_name = blender::GPU_vertformat_attr_name_get(
      &split_after_second, &second_attr, 0);
  const char *second_alias = blender::GPU_vertformat_attr_name_get(
      &split_after_second, &second_attr, 1);
  if (!require(split_after_first.attrs[0].name_len == 2 &&
                   split_after_second.attrs[0].name_len == 2,
               "vertex alias-list census") ||
      !require(first_attr.type.format == second_attr.type.format &&
                   first_attr.offset == second_attr.offset &&
                   split_after_first.stride == split_after_second.stride,
               "vertex alias layouts otherwise match") ||
      !require(std::strcmp(first_name, "a") == 0 && std::strcmp(first_alias, "bc") == 0 &&
                   std::strcmp(second_name, "ab") == 0 && std::strcmp(second_alias, "c") == 0,
               "vertex alias collision inputs") ||
      !require(bw::pipeline_hash(first) != bw::pipeline_hash(second),
               "vertex alias-list cache separation"))
  {
    return false;
  }

  std::puts("CONTRACT vertex_alias_cache_key PASS cases=2 aliases=4 unique=2");
  return true;
}

}  // namespace

int main()
{
  if (!primitive_topology_contract() || !strip_index_format_contract() ||
      !multiview_uniform_allocation_contract() ||
      !dummy_vertex_buffer_creation_contract() ||
      !transient_handle_publication_contract() ||
      !bind_group_completeness_contract() ||
      !framebuffer_load_action_commit_contract() ||
      !framebuffer_load_action_transaction_contract() ||
      !framebuffer_layered_clear_order_contract() ||
      !vertex_buffer_handle_resolution_contract() ||
      !index_buffer_handle_resolution_contract() ||
      !shader_module_set_cache_contract() ||
      !scoped_handle_cache_contract() ||
      !ordered_scoped_handle_cache_contract() ||
      !context_owned_pipeline_cache_contract() ||
      !context_backend_handle_registry_contract() ||
      !ordered_queue_scheduler_failure_drain_contract() ||
      !resize_present_barrier_queue_contract() ||
      !transient_resource_gate_contract() ||
      !compute_bind_group_scope_contract() ||
      !compute_pipeline_cache_publication_contract() ||
      !indirect_draw_span_contract() || !direct_draw_plan_contract() ||
      !viewport_scissor_plan_contract() || !window_viewport_scissor_plan_contract() ||
      !offscreen_viewport_scissor_plan_contract() ||
      !compute_dispatch_range_contract() ||
      !compute_command_transaction_contract() ||
      !buffer_command_transaction_contract() ||
      !ghost_window_publication_transaction_contract() ||
      !ghost_callback_registration_transaction_contract() ||
      !ghost_surface_publication_status_contract() ||
      !ghost_surface_acquisition_status_contract() ||
      !ghost_device_loss_state_contract() ||
      !ghost_device_loss_inflight_cancel_contract() ||
      !ghost_present_resource_transaction_contract() ||
      !ghost_resize_coherence_contract() ||
      !format_32bit_contract() ||
      !format_subword_contract() || !format_i10_contract() || !dummy_vertex_contract() ||
      !shader_lifetime_cache_contract() || !vertex_alias_cache_key_contract())
  {
    return 1;
  }
  std::puts(
      "INTEGRATED_PIPELINE_PASS contracts=43 primitives=11 strip_cases=33 "
      "multiview_allocations=2 dummy_buffer_creations=3 indirect_spans=19 direct_draws=16 viewport_scissors=28 "
      "window_rects=32 offscreen_rects=21 compute_direct=15 "
      "compute_indirect=13 compute_command_cases=6 buffer_command_cases=6 "
      "scheduler_failure_followers=100000 scheduler_failed_epochs=100000 "
      "resize_present_barrier_cases=31 "
      "ghost_window_cases=5 ghost_callback_registration_cases=17 ghost_surface_cases=13 ghost_acquire_cases=12 ghost_device_loss_cases=13 ghost_loss_inflight_cases=10 ghost_present_cases=14 ghost_resize_cases=17 formats=96 i10=12 "
      "dummy=32 transient_publications=2 vertex_binding_resolutions=3 "
      "bind_group_completeness_cases=6 "
      "index_binding_resolutions=3 shader_module_set_cases=4 scoped_cache_cases=5 "
      "ordered_scoped_cache_cases=5 "
      "context_pipeline_caches=3 "
      "context_handle_registry_cases=7 "
      "transient_resource_gates=3 compute_bind_group_scope_cases=4 "
      "compute_cache_publications=3 load_action_commits=2 load_action_transactions=6 "
      "layered_clear_orders=4 "
      "shader_lifetimes=4096 alias_keys=2");
  return 0;
}
