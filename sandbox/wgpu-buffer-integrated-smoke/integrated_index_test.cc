/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free parity contract for the point-restart cleanup delegated by
 * Blender's real IndexBuf::init() to the canonical WebGPU backend method. */

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "MEM_guardedalloc.h"

#include "GPU_index_buffer.hh"
#include "wgpu_index_buffer.hh"

#ifndef BW_WGPU_INDEX_STRIP_SOURCE
#  error "BW_WGPU_INDEX_STRIP_SOURCE must name the extracted shipping method"
#endif

namespace blender::gpu {

class IndexStripHarness : public IndexBuf {
 public:
  void upload_data() override {}
  void bind_as_ssbo(uint /*binding*/) override {}
  void read(uint32_t * /*data*/) const override {}
  void update_sub(uint /*start*/, uint /*len*/, const void * /*data*/) override {}

  uint32_t stored_length() const
  {
    return index_len_;
  }
  bool is_subrange() const
  {
    return is_subrange_;
  }
  const IndexBuf *source() const
  {
    return is_subrange_ ? src_ : nullptr;
  }
  const uint16_t *u16_data() const
  {
    return static_cast<const uint16_t *>(data_);
  }
  const uint32_t *u32_data() const
  {
    return static_cast<const uint32_t *>(data_);
  }

 private:
  void strip_restart_indices() override;
};

/* Execute the shipping method without retaining WGPUIndexBuffer's live-device
 * vtable. The build driver extracts this definition byte-for-byte. */
#define WGPUIndexBuffer IndexStripHarness
#include BW_WGPU_INDEX_STRIP_SOURCE
#undef WGPUIndexBuffer

namespace {

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    return false;
  }
  return true;
}

template<size_t Size>
uint32_t *owned_indices(const std::array<uint32_t, Size> &source)
{
  uint32_t *result = MEM_new_array_uninitialized<uint32_t>(Size, "index restart contract");
  std::memcpy(result, source.data(), sizeof(source));
  return result;
}

template<size_t Size>
bool equal_u16(const IndexStripHarness &buffer, const std::array<uint16_t, Size> &expected)
{
  return std::memcmp(buffer.u16_data(), expected.data(), sizeof(expected)) == 0;
}

template<size_t Size>
bool equal_u32(const IndexStripHarness &buffer, const std::array<uint32_t, Size> &expected)
{
  return std::memcmp(buffer.u32_data(), expected.data(), sizeof(expected)) == 0;
}

bool point_restart_contract()
{
  size_t removed = 0;
  size_t survivors = 0;

  {
    constexpr std::array<uint32_t, 6> input = {7, RESTART_INDEX, 9, 11, RESTART_INDEX, 13};
    constexpr std::array<uint16_t, 4> expected = {7, 9, 11, 13};
    IndexStripHarness buffer;
    buffer.init(input.size(), owned_indices(input), 7, 13, GPU_PRIM_POINTS, true);
    if (!require(buffer.stored_length() == expected.size(), "mixed restart count") ||
        !require(buffer.index_len_get() == expected.size(), "mixed drawable count") ||
        !require(!buffer.is_32bit(), "mixed restart compression") ||
        !require(equal_u16(buffer, expected), "mixed restart stable order"))
    {
      return false;
    }
    removed += input.size() - expected.size();
    survivors += expected.size();
  }

  {
    constexpr std::array<uint32_t, 4> input = {
        RESTART_INDEX, RESTART_INDEX, RESTART_INDEX, RESTART_INDEX};
    IndexStripHarness buffer;
    buffer.init(input.size(),
                owned_indices(input),
                UINT32_MAX,
                0,
                GPU_PRIM_POINTS,
                true);
    if (!require(buffer.stored_length() == 0, "all-restart storage is empty") ||
        !require(buffer.index_len_get() == 0, "all-restart draw is empty"))
    {
      return false;
    }
    removed += input.size();
  }

  {
    constexpr std::array<uint32_t, 5> input = {3, RESTART_INDEX, 70000, RESTART_INDEX, 42};
    constexpr std::array<uint32_t, 3> expected = {3, 70000, 42};
    IndexStripHarness buffer;
    buffer.init(input.size(), owned_indices(input), 3, 70000, GPU_PRIM_POINTS, true);
    if (!require(buffer.stored_length() == expected.size(), "wide restart count") ||
        !require(buffer.is_32bit(), "wide indices remain u32") ||
        !require(equal_u32(buffer, expected), "wide restart stable order"))
    {
      return false;
    }
    removed += input.size() - expected.size();
    survivors += expected.size();
  }

  {
    constexpr std::array<uint32_t, 3> input = {65536, RESTART_INDEX, 65538};
    constexpr std::array<uint16_t, 2> expected = {0, 2};
    IndexStripHarness buffer;
    buffer.init(input.size(), owned_indices(input), 65536, 65538, GPU_PRIM_POINTS, true);
    if (!require(buffer.stored_length() == expected.size(), "rebased restart count") ||
        !require(!buffer.is_32bit(), "rebased indices compress to u16") ||
        !require(buffer.index_base_get() == 65536, "rebased index base") ||
        !require(equal_u16(buffer, expected), "restart removal precedes squeezing"))
    {
      return false;
    }
    removed += input.size() - expected.size();
    survivors += expected.size();
  }

  if (!require(removed == 9, "restart removal census") ||
      !require(survivors == 9, "restart survivor census"))
  {
    return false;
  }
  std::printf(
      "CONTRACT index-point-restart PASS cases=4 removed=%zu survivors=%zu order=stable\n",
      removed,
      survivors);
  return true;
}

bool index_metadata_contract()
{
  constexpr std::array<uint32_t, 4> source = {65536, 65537, 65538, 65539};
  IndexStripHarness parent;
  parent.init(source.size(), owned_indices(source), 65536, 65539, GPU_PRIM_TRIS, false);
  IndexStripHarness child;
  child.init_subrange(&parent, 1, 2);
  constexpr std::array<uint32_t, 4> wide_source = {3, 70000, 42, 90000};
  IndexStripHarness wide_parent;
  wide_parent.init(
      wide_source.size(), owned_indices(wide_source), 3, 90000, GPU_PRIM_TRIS, false);
  IndexStripHarness wide_child;
  wide_child.init_subrange(&wide_parent, 3, 1);
  IndexStripHarness device_only;
  device_only.init_build_on_device(17);

  const webgpu::IndexBindingPlan child_binding = webgpu::index_binding_plan(child);
  const webgpu::IndexBindingPlan wide_binding = webgpu::index_binding_plan(wide_child);

  if (!require(!parent.is_32bit(), "parent compresses to u16") ||
      !require(parent.index_base_get() == 65536, "parent base") ||
      !require(child.is_subrange(), "subrange marker") ||
      !require(child.source() == &parent, "subrange parent identity") ||
      !require(child.index_start_get() == 1 && child.index_len_get() == 2,
               "subrange span") ||
      !require(child.index_base_get() == parent.index_base_get(), "subrange base inheritance") ||
      !require(!child.is_32bit() && child.size_get() == 4, "subrange u16 byte size") ||
      !require(child_binding.byte_offset == 2 && child_binding.base_vertex == 65536,
               "subrange u16 draw binding") ||
      !require(wide_child.is_32bit() && wide_child.index_start_get() == 3,
               "subrange u32 metadata") ||
      !require(wide_binding.byte_offset == 12 && wide_binding.base_vertex == 0,
               "subrange u32 draw binding") ||
      !require(device_only.is_32bit(), "device-built indices are u32") ||
      !require(device_only.index_start_get() == 0 && device_only.index_len_get() == 17,
               "device-built span") ||
      !require(device_only.size_get() == 68, "device-built byte size"))
  {
    return false;
  }

  std::puts(
      "CONTRACT index-metadata PASS subranges=2 bindings=u16@2+65536/u32@12+0 device-u32=17");
  return true;
}

}  // namespace

bool run_integrated_index_contracts()
{
  return point_restart_contract() && index_metadata_contract();
}

}  // namespace blender::gpu
