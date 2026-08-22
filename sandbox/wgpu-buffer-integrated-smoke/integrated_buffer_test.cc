/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm parity contract for the canonical in-tree WebGPU
 * buffer wrapper, pixel-upload buffer, and readback registry. No instance,
 * adapter, or device is created; live buffer copies remain part of the
 * hardware-gated M3 replay. */

#include <array>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <utility>

#include "wgpu_buffer.hh"
#include "wgpu_pixel_buffer.hh"
#include "wgpu_readback.hh"

namespace bw = blender::gpu::webgpu;
namespace readback = blender::gpu::webgpu::readback;

namespace blender::gpu {
bool run_integrated_index_contracts();
}

namespace blender::gpu::webgpu {
bool run_integrated_buffer_update_contracts();
}

namespace {

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    return false;
  }
  return true;
}

uint64_t usage_bits(const wgpu::BufferUsage usage)
{
  return static_cast<uint64_t>(usage);
}

wgpu::BufferUsage expected_base_usage(const bw::BufferKind kind)
{
  switch (kind) {
    case bw::BufferKind::Vertex:
      return wgpu::BufferUsage::Vertex | wgpu::BufferUsage::Storage;
    case bw::BufferKind::Index:
      return wgpu::BufferUsage::Index | wgpu::BufferUsage::Storage;
    case bw::BufferKind::Uniform:
      return wgpu::BufferUsage::Uniform | wgpu::BufferUsage::Storage;
    case bw::BufferKind::Storage:
      return wgpu::BufferUsage::Storage | wgpu::BufferUsage::Indirect;
  }
  return wgpu::BufferUsage::None;
}

bool common_contract()
{
  struct AlignCase {
    size_t value;
    size_t alignment;
    size_t expected;
  };
  constexpr std::array<AlignCase, 8> align_cases = {{{0, 4, 0},
                                                      {1, 4, 4},
                                                      {4, 4, 4},
                                                      {5, 4, 8},
                                                      {255, 256, 256},
                                                      {256, 256, 256},
                                                      {257, 256, 512},
                                                      {65535, 4, 65536}}};

  if (!require(bw::kCopyAlignment == 4, "copy alignment") ||
      !require(bw::kUniformOffsetAlignment == 256, "uniform offset alignment") ||
      !require(bw::kWriteBufferStagingThreshold == 65536, "staging threshold"))
  {
    return false;
  }
  for (const AlignCase &test : align_cases) {
    if (!require(bw::align_up(test.value, test.alignment) == test.expected, "align_up case")) {
      return false;
    }
  }
  if (!require(bw::to_wgpu_index_format(false) == wgpu::IndexFormat::Uint16,
               "16-bit index format") ||
      !require(bw::to_wgpu_index_format(true) == wgpu::IndexFormat::Uint32,
               "32-bit index format"))
  {
    return false;
  }

  std::printf("CONTRACT common PASS align_cases=%zu threshold=%zu\n",
              align_cases.size(),
              bw::kWriteBufferStagingThreshold);
  return true;
}

bool checked_arithmetic_contract()
{
  constexpr size_t size_max = std::numeric_limits<size_t>::max();
  size_t aligned = 0;
  size_t rejected_sentinel = 37;

  if (!require(bw::checked_align_up(0, 4, aligned) && aligned == 0,
               "checked zero alignment") ||
      !require(bw::checked_align_up(1, 4, aligned) && aligned == 4,
               "checked ordinary alignment") ||
      !require(bw::checked_align_up(size_max - 3, 4, aligned) && aligned == size_max - 3,
               "checked maximum representable alignment") ||
      !require(bw::checked_align_up(size_max, 1, aligned) && aligned == size_max,
               "checked unit alignment") ||
      !require(!bw::checked_align_up(size_max - 2, 4, rejected_sentinel) &&
                   rejected_sentinel == 37,
               "alignment overflow is rejected without output mutation") ||
      !require(!bw::checked_align_up(8, 0, rejected_sentinel) && rejected_sentinel == 37,
               "zero alignment is rejected") ||
      !require(!bw::checked_align_up(8, 3, rejected_sentinel) && rejected_sentinel == 37,
               "non-power-of-two alignment is rejected") ||
      !require(bw::range_fits(0, 0, 0), "empty range fits empty allocation") ||
      !require(bw::range_fits(12, 4, 16), "exact-end range fits") ||
      !require(!bw::range_fits(12, 5, 16), "past-end range is rejected") ||
      !require(!bw::range_fits(size_max - 3, 8, 16), "wrapped range is rejected"))
  {
    return false;
  }

  std::printf("CONTRACT checked-arithmetic PASS align_cases=7 range_cases=4\n");
  return true;
}

bool allocation_limit_contract()
{
  struct AllocationCase {
    size_t requested;
    uint64_t limit;
    size_t expected;
    bool accepted;
  };
  constexpr size_t size_max = std::numeric_limits<size_t>::max();
  constexpr std::array<AllocationCase, 10> cases = {{{0, 4, 4, true},
                                                      {1, 4, 4, true},
                                                      {4, 4, 4, true},
                                                      {5, 8, 8, true},
                                                      {5, 7, 0, false},
                                                      {8, 7, 0, false},
                                                      {8, 0, 0, false},
                                                      {size_max - 3,
                                                       uint64_t(size_max),
                                                       size_max - 3,
                                                       true},
                                                      {size_max - 2,
                                                       uint64_t(size_max),
                                                       0,
                                                       false},
                                                      {size_max,
                                                       uint64_t(size_max),
                                                       0,
                                                       false}}};

  size_t accepted = 0;
  for (const AllocationCase &test : cases) {
    size_t allocation = 37;
    const bool actual = bw::buffer_allocation_size(test.requested, test.limit, allocation);
    if (!require(actual == test.accepted, "buffer allocation limit decision") ||
        !require(actual ? allocation == test.expected : allocation == 37,
                 "rejected allocation preserves output"))
    {
      return false;
    }
    accepted += actual;
  }

  std::printf("CONTRACT allocation-limit PASS cases=%zu accepted=%zu rejected=%zu\n",
              cases.size(),
              accepted,
              cases.size() - accepted);
  return accepted == 5;
}

bool update_payload_contract()
{
  struct UpdateCase {
    size_t logical_size;
    size_t allocation_size;
    bool accepted;
  };
  constexpr size_t size_max = std::numeric_limits<size_t>::max();
  constexpr std::array<UpdateCase, 9> cases = {{{0, 4, false},
                                                {1, 4, true},
                                                {2, 4, true},
                                                {3, 4, true},
                                                {4, 4, true},
                                                {5, 8, true},
                                                {5, 7, false},
                                                {8, 8, true},
                                                {size_max, size_max, false}}};
  const std::array<uint8_t, 8> source = {0x11, 0x22, 0x33, 0x44,
                                          0x55, 0x66, 0x77, 0x88};

  size_t aligned = 0;
  size_t padded = 0;
  size_t rejected = 0;
  size_t checked_bytes = 0;
  for (const UpdateCase &test : cases) {
    bw::BufferUpdatePayload payload;
    payload.transfer_size = 37;
    payload.padded = {0xa5};
    const bool actual = bw::buffer_update_payload(
        source.data(), test.logical_size, test.allocation_size, payload);
    if (!require(actual == test.accepted, "buffer update payload decision")) {
      return false;
    }
    if (!actual) {
      if (!require(payload.transfer_size == 37 && payload.padded.size() == 1 &&
                       payload.padded[0] == 0xa5,
                   "rejected update preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }

    const size_t expected_size = bw::align_up(test.logical_size, bw::kCopyAlignment);
    const auto *transfer = static_cast<const uint8_t *>(payload.data(source.data()));
    if (!require(payload.transfer_size == expected_size, "update transfer size") ||
        !require((payload.padded.empty() && transfer == source.data()) ||
                     (!payload.padded.empty() && transfer == payload.padded.data()),
                 "update transfer storage"))
    {
      return false;
    }
    for (size_t index = 0; index < expected_size; index++) {
      const uint8_t expected = index < test.logical_size ? source[index] : 0;
      if (!require(transfer[index] == expected, "update payload byte")) {
        return false;
      }
      checked_bytes++;
    }
    if (expected_size == test.logical_size) {
      aligned++;
    }
    else {
      padded++;
    }
  }

  bw::BufferUpdatePayload null_payload;
  if (!require(!bw::buffer_update_payload(nullptr, 3, 4, null_payload),
               "null update source is rejected"))
  {
    return false;
  }
  rejected++;

  std::printf(
      "CONTRACT update-payload PASS cases=10 aligned=%zu padded=%zu rejected=%zu bytes=%zu\n",
      aligned,
      padded,
      rejected,
      checked_bytes);
  return aligned == 2 && padded == 4 && rejected == 4 && checked_bytes == 32;
}

bool copy_range_contract()
{
  struct CopyCase {
    size_t source_offset;
    size_t destination_offset;
    size_t size;
    size_t source_capacity;
    size_t destination_capacity;
    bool expected;
  };
  constexpr size_t size_max = std::numeric_limits<size_t>::max();
  constexpr std::array<CopyCase, 9> cases = {{{0, 0, 4, 4, 4, true},
                                              {4, 8, 8, 12, 16, true},
                                              {0, 0, 0, 4, 4, false},
                                              {2, 0, 4, 8, 8, false},
                                              {0, 2, 4, 8, 8, false},
                                              {0, 0, 2, 8, 8, false},
                                              {8, 0, 8, 12, 16, false},
                                              {0, 12, 8, 16, 16, false},
                                              {size_max - 3, 0, 8, size_max, 16, false}}};

  size_t accepted = 0;
  for (const CopyCase &test : cases) {
    const bool actual = bw::buffer_copy_range_valid(test.source_offset,
                                                    test.destination_offset,
                                                    test.size,
                                                    test.source_capacity,
                                                    test.destination_capacity);
    if (!require(actual == test.expected, "buffer copy range decision")) {
      return false;
    }
    accepted += actual;
  }

  std::printf("CONTRACT copy-range PASS cases=%zu accepted=%zu rejected=%zu\n",
              cases.size(),
              accepted,
              cases.size() - accepted);
  return accepted == 2;
}

bool usage_contract()
{
  constexpr std::array<bw::BufferKind, 4> kinds = {bw::BufferKind::Vertex,
                                                    bw::BufferKind::Index,
                                                    bw::BufferKind::Uniform,
                                                    bw::BufferKind::Storage};
  constexpr std::array<bw::UsageType, 4> usages = {bw::UsageType::Stream,
                                                   bw::UsageType::Static,
                                                   bw::UsageType::Dynamic,
                                                   bw::UsageType::DeviceOnly};
  size_t cases = 0;
  for (const bw::BufferKind kind : kinds) {
    for (const bw::UsageType usage : usages) {
      for (const bool readable : {false, true}) {
        wgpu::BufferUsage expected = expected_base_usage(kind) | wgpu::BufferUsage::CopyDst;
        if (readable) {
          expected |= wgpu::BufferUsage::CopySrc;
        }
        if (!require(usage_bits(bw::usage_flags(kind, usage, readable)) == usage_bits(expected),
                     "exact usage mask"))
        {
          return false;
        }
        cases++;
      }
    }
  }

  const wgpu::BufferUsage uniform =
      bw::usage_flags(bw::BufferKind::Uniform, bw::UsageType::Dynamic, false);
  const wgpu::BufferUsage device_only =
      bw::usage_flags(bw::BufferKind::Storage, bw::UsageType::DeviceOnly, false);
  if (!require((uniform & wgpu::BufferUsage::Storage) != wgpu::BufferUsage::None,
               "uniform buffers retain storage usage") ||
      !require((device_only & wgpu::BufferUsage::CopyDst) != wgpu::BufferUsage::None,
               "device-only buffers retain CopyDst"))
  {
    return false;
  }

  std::printf("CONTRACT usage PASS cases=%zu uniform_storage=1 device_copydst=1\n", cases);
  return cases == 32;
}

bool invalid_buffer_contract()
{
  bw::Buffer buffer;
  wgpu::Device device;
  wgpu::Queue queue;
  wgpu::Instance instance;
  const std::array<uint8_t, 4> bytes = {1, 2, 3, 4};

  if (!require(!buffer.valid(), "default buffer is invalid") ||
      !require(buffer.size() == 0, "default buffer size") ||
      !require(buffer.kind() == bw::BufferKind::Vertex, "default buffer kind") ||
      !require(!buffer.update_sub(device, queue, 0, bytes.data(), bytes.size()),
               "invalid buffer rejects update") ||
      !require(!buffer.update_sub(device, queue, 0, nullptr, bytes.size()),
               "null update rejected") ||
      !require(buffer.read(instance, device, queue, 0, bytes.size()).empty(),
               "invalid buffer read is empty"))
  {
    return false;
  }

  std::printf("CONTRACT invalid-buffer PASS update=reject read=empty\n");
  return true;
}

bool move_lifetime_contract()
{
  bw::Buffer first;
  bw::Buffer second(std::move(first));
  bw::Buffer third;
  third = std::move(second);
  third = std::move(third);

  if (!require(!first.valid() && first.size() == 0, "moved-from constructor source") ||
      !require(!second.valid() && second.size() == 0, "moved-from assignment source") ||
      !require(!third.valid() && third.size() == 0, "moved empty destination") ||
      !require(third.kind() == bw::BufferKind::Vertex, "moved buffer kind"))
  {
    return false;
  }

  std::printf("CONTRACT move-lifetime PASS constructor=1 assignment=1 self=1\n");
  return true;
}

bool pixel_buffer_contract()
{
  constexpr std::array<size_t, 7> sizes = {0, 1, 4, 255, 256, 257, 4096};
  uint64_t digest = 1469598103934665603ull;
  size_t bytes_checked = 0;
  size_t remaps = 0;

  for (const size_t size : sizes) {
    blender::gpu::WGPUPixelBuffer buffer(size);
    const blender::GPUPixelBufferNativeHandle native_handle = buffer.get_native_handle();
    if (!require(buffer.get_size() == size, "pixel buffer size") ||
        !require(native_handle.handle == 0 && native_handle.size == 0,
                 "pixel buffer native handle is empty"))
    {
      return false;
    }

    auto *mapped = static_cast<uint8_t *>(buffer.map());
    if (!require(size == 0 || mapped != nullptr, "non-empty pixel buffer maps") ||
        !require(buffer.map() == nullptr, "pixel buffer rejects a second map") ||
        !require(buffer.data_for_upload(size) == nullptr,
                 "mapped pixel buffer rejects upload"))
    {
      return false;
    }

    for (size_t i = 0; i < size; i++) {
      mapped[i] = uint8_t((i * 29u + size * 17u + 11u) & 0xffu);
    }
    buffer.unmap();

    const auto *upload = static_cast<const uint8_t *>(buffer.data_for_upload(size));
    if (!require(size == 0 || upload == mapped, "upload view preserves mapped storage") ||
        !require(buffer.data_for_upload(size + 1) == nullptr,
                 "oversized pixel upload is rejected"))
    {
      return false;
    }
    for (size_t i = 0; i < size; i++) {
      const uint8_t expected = uint8_t((i * 29u + size * 17u + 11u) & 0xffu);
      if (!require(upload[i] == expected, "pixel upload preserves every byte")) {
        return false;
      }
      digest ^= upload[i];
      digest *= 1099511628211ull;
      bytes_checked++;
    }

    auto *remapped = static_cast<uint8_t *>(buffer.map());
    if (!require(size == 0 || remapped == mapped, "pixel buffer remap is stable")) {
      return false;
    }
    buffer.unmap();
    remaps++;
  }

  std::printf("CONTRACT pixel-buffer PASS cases=%zu bytes=%zu remaps=%zu digest=%016llx\n",
              sizes.size(),
              bytes_checked,
              remaps,
              static_cast<unsigned long long>(digest));
  return bytes_checked == 4869 && remaps == sizes.size();
}

bool invalid_readback_contract()
{
  int source_identity = 0;
  readback::SourceKey key;
  key.kind = readback::SourceKind::Buffer;
  key.obj = &source_identity;
  key.sub = 4;
  key.span = 4;

  wgpu::Device device;
  wgpu::Queue queue;
  wgpu::Buffer handle;
  const readback::Ticket cache_ticket = readback::kick_buffer(
      device, queue, handle, key, 0, 4, 4, readback::RequestMode::Cache);
  const readback::Ticket exact_ticket = readback::kick_buffer(
      device, queue, handle, key, 0, 4, 4, readback::RequestMode::Exact);
  std::array<uint8_t, 4> destination = {};

  if (!require(cache_ticket == readback::kInvalidTicket, "invalid cache kick") ||
      !require(exact_ticket != readback::kInvalidTicket, "invalid exact kick ticket") ||
      !require(readback::ticket_status(exact_ticket) == readback::TicketStatus::Failed,
               "invalid exact kick status") ||
      !require(readback::ticket_error(exact_ticket) == readback::TicketError::InvalidArgument,
               "invalid exact kick error") ||
      !require(readback::ticket_size(exact_ticket) == 0, "invalid exact kick size") ||
      !require(!readback::is_ready(exact_ticket), "invalid exact kick readiness") ||
      !require(readback::consume_ticket(exact_ticket, destination.data(), destination.size()) == 0,
               "failed ticket cannot be consumed") ||
      !require(!readback::cancel_ticket(exact_ticket), "failed ticket cannot be canceled") ||
      !require(!readback::take_settled(key, destination.data(), destination.size()),
               "unknown source has no settled payload") ||
      !require(readback::pending_count() == 0, "invalid kicks allocate no pending work"))
  {
    return false;
  }

  readback::free_ticket(exact_ticket);
  readback::forget_source(readback::SourceKind::Buffer, &source_identity);
  readback::pump();
  if (!require(readback::ticket_status(exact_ticket) == readback::TicketStatus::Invalid,
               "freed exact ticket is invalid") ||
      !require(readback::pending_count() == 0, "registry remains idle"))
  {
    return false;
  }

  std::printf("CONTRACT invalid-readback PASS cache=reject exact=failed pending=0\n");
  return true;
}

bool failed_ticket_capacity_contract()
{
  constexpr size_t exact_record_capacity = 256;
  constexpr size_t retired_records = exact_record_capacity / 2;
  std::array<readback::Ticket, exact_record_capacity> tickets = {};
  std::array<readback::Ticket, retired_records> replacements = {};
  int source_identity = 0;
  wgpu::Device device;
  wgpu::Queue queue;
  wgpu::Buffer handle;

  for (size_t i = 0; i < tickets.size(); i++) {
    readback::SourceKey key;
    key.kind = readback::SourceKind::Buffer;
    key.obj = &source_identity;
    key.sub = i;
    key.span = 4;
    tickets[i] = readback::kick_buffer(
        device, queue, handle, key, 0, 4, 4, readback::RequestMode::Exact);
    if (!require(tickets[i] != readback::kInvalidTicket, "exact failed-ticket capacity") ||
        !require(readback::ticket_status(tickets[i]) == readback::TicketStatus::Failed,
                 "exact capacity ticket status") ||
        !require(readback::ticket_error(tickets[i]) == readback::TicketError::InvalidArgument,
                 "exact capacity ticket error") ||
        !require(readback::ticket_size(tickets[i]) == 0, "exact capacity ticket size"))
    {
      return false;
    }
  }

  readback::SourceKey overflow_key;
  overflow_key.kind = readback::SourceKind::Buffer;
  overflow_key.obj = &source_identity;
  overflow_key.sub = exact_record_capacity;
  overflow_key.span = 4;
  if (!require(readback::kick_buffer(device,
                                     queue,
                                     handle,
                                     overflow_key,
                                     0,
                                     4,
                                     4,
                                     readback::RequestMode::Exact) ==
                   readback::kInvalidTicket,
               "exact failed-ticket cap is fail-closed") ||
      !require(readback::pending_count() == 0, "failed tickets allocate no pending work"))
  {
    return false;
  }

  readback::forget_source(readback::SourceKind::Buffer, &source_identity);
  for (const readback::Ticket ticket : tickets) {
    if (!require(readback::ticket_status(ticket) == readback::TicketStatus::Failed,
                 "forget_source preserves exact failed tickets"))
    {
      return false;
    }
  }

  for (size_t i = 0; i < tickets.size(); i += 2) {
    readback::free_ticket(tickets[i]);
    if (!require(readback::ticket_status(tickets[i]) == readback::TicketStatus::Invalid,
                 "freed exact ticket retires immediately"))
    {
      return false;
    }
  }

  for (size_t i = 0; i < replacements.size(); i++) {
    readback::SourceKey key = overflow_key;
    key.sub += 1 + i;
    replacements[i] = readback::kick_buffer(
        device, queue, handle, key, 0, 4, 4, readback::RequestMode::Exact);
    if (!require(replacements[i] != readback::kInvalidTicket,
                 "retired exact record capacity is reusable") ||
        !require(readback::ticket_status(replacements[i]) == readback::TicketStatus::Failed,
                 "replacement ticket status"))
    {
      return false;
    }
  }
  if (!require(readback::kick_buffer(device,
                                     queue,
                                     handle,
                                     overflow_key,
                                     0,
                                     4,
                                     4,
                                     readback::RequestMode::Exact) ==
                   readback::kInvalidTicket,
               "replacement tickets restore exact cap"))
  {
    return false;
  }

  for (size_t i = 1; i < tickets.size(); i += 2) {
    readback::free_ticket(tickets[i]);
  }
  for (const readback::Ticket ticket : replacements) {
    readback::free_ticket(ticket);
  }

  const readback::Ticket final_ticket = readback::kick_buffer(
      device, queue, handle, overflow_key, 0, 4, 4, readback::RequestMode::Exact);
  if (!require(final_ticket != readback::kInvalidTicket, "fully retired registry is reusable") ||
      !require(!readback::cancel_ticket(final_ticket), "failed exact ticket cannot be canceled") ||
      !require(readback::pending_count() == 0, "capacity exercise leaves no pending work"))
  {
    return false;
  }
  readback::free_ticket(final_ticket);
  if (!require(readback::ticket_status(final_ticket) == readback::TicketStatus::Invalid,
               "final exact ticket retires"))
  {
    return false;
  }

  std::printf("CONTRACT failed-ticket-capacity PASS cap=%zu retired=%zu replacements=%zu\n",
              exact_record_capacity,
              retired_records,
              replacements.size());
  return true;
}

}  // namespace

int main()
{
  if (!common_contract() || !checked_arithmetic_contract() || !allocation_limit_contract() ||
      !update_payload_contract() || !copy_range_contract() || !usage_contract() ||
      !invalid_buffer_contract() ||
      !move_lifetime_contract() || !pixel_buffer_contract() || !invalid_readback_contract() ||
      !failed_ticket_capacity_contract() ||
      !blender::gpu::webgpu::run_integrated_buffer_update_contracts() ||
      !blender::gpu::run_integrated_index_contracts())
  {
    return 1;
  }
  std::printf(
      "INTEGRATED_BUFFER_PASS contracts=15 usage_cases=32 pixel_cases=7 exact_cap=256 "
      "buffer_update_cases=9 index_cases=4 index_upload_cases=6\n");
  return 0;
}
