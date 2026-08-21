/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm contract for the canonical in-tree WebGPU
 * conservative occlusion-query fallback. */

#include <array>
#include <cstdint>
#include <cstdio>

/* Include the base first so the test-only access override cannot affect any
 * standard-library or blenlib dependency included by the WebGPU header. */
#include "gpu_query.hh"
#define private public
#include "wgpu_query.hh"
#undef private

namespace {

using blender::MutableSpan;
using blender::gpu::GPU_QUERY_OCCLUSION;
using blender::gpu::WGPUQueryPool;

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    return false;
  }
  return true;
}

bool initial_state_contract()
{
  WGPUQueryPool pool;
  pool.init(GPU_QUERY_OCCLUSION);
  MutableSpan<uint32_t> empty;
  pool.get_occlusion_result(empty);

  if (!require(pool.initialized_, "query pool initialized") ||
      !require(pool.query_issued_ == 0, "new query pool issued count") ||
      !require(!pool.query_active_, "new query pool inactive"))
  {
    return false;
  }

  std::printf("CONTRACT initial-state PASS initialized=1 issued=0 active=0\n");
  return true;
}

bool lifecycle_contract()
{
  WGPUQueryPool pool;
  pool.init(GPU_QUERY_OCCLUSION);
  for (uint32_t i = 0; i < 5; i++) {
    pool.begin_query();
    if (!require(pool.query_active_, "begin marks query active") ||
        !require(pool.query_issued_ == i + 1, "begin increments issued count"))
    {
      return false;
    }
    pool.end_query();
    if (!require(!pool.query_active_, "end marks query inactive")) {
      return false;
    }
  }

  std::array<uint32_t, 5> results = {11u, 13u, 17u, 19u, 23u};
  pool.get_occlusion_result(MutableSpan<uint32_t>(results));
  for (const uint32_t result : results) {
    if (!require(result == 0u, "conservative query result is zero")) {
      return false;
    }
  }

  std::printf("CONTRACT lifecycle PASS queries=5 zero_hits=5\n");
  return true;
}

bool guarded_transition_contract()
{
  WGPUQueryPool pool;
  pool.init(GPU_QUERY_OCCLUSION);

  pool.begin_query();
  pool.begin_query();
  if (!require(pool.query_active_, "duplicate begin leaves query active") ||
      !require(pool.query_issued_ == 1, "duplicate begin does not issue another query"))
  {
    return false;
  }

  pool.end_query();
  pool.end_query();
  if (!require(!pool.query_active_, "duplicate end leaves query inactive") ||
      !require(pool.query_issued_ == 1, "duplicate end does not change issued count"))
  {
    return false;
  }

  pool.begin_query();
  pool.end_query();
  std::array<uint32_t, 2> results = {29u, 31u};
  pool.get_occlusion_result(MutableSpan<uint32_t>(results));
  if (!require(pool.query_issued_ == 2, "guarded sequence issues two queries") ||
      !require(results[0] == 0u && results[1] == 0u,
               "guarded sequence reports conservative zero hits"))
  {
    return false;
  }

  std::printf(
      "CONTRACT guarded-transitions PASS duplicate_begin=ignored duplicate_end=ignored queries=2\n");
  return true;
}

}  // namespace

int main()
{
  if (!initial_state_contract() || !lifecycle_contract() || !guarded_transition_contract()) {
    return 1;
  }
  std::printf("INTEGRATED_QUERY_PASS contracts=3 queries=7 zero_hits=7\n");
  return 0;
}
