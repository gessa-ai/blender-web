/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <cstdio>
#include <immintrin.h>

#define CCL_NAMESPACE_BEGIN namespace ccl {
#define CCL_NAMESPACE_END }
#define __KERNEL_SSE__
#define __KERNEL_SSE2__
#define __KERNEL_SSE3__
#define __KERNEL_SSSE3__
#define __KERNEL_SSE42__

#include "util/math_float4.h"

int main()
{
  const ccl::float4 a = ccl::make_float4(1.25f, -2.0f, 3.5f, 0.5f);
  const ccl::float4 b = ccl::make_float4(4.0f, 0.25f, -1.0f, 8.0f);
  const ccl::float4 lower = ccl::make_float4(-3.0f, -3.0f, -3.0f, -3.0f);
  const ccl::float4 upper = ccl::make_float4(7.0f, 7.0f, 7.0f, 7.0f);
  const ccl::float4 result = ccl::min(ccl::max(a * b + a, lower), upper);
  const int mask = _mm_movemask_ps(result);

  std::printf("CYCLES_WASM_SIMD_PROBE %.6f %.6f %.6f %.6f mask=%d\n",
              result.x,
              result.y,
              result.z,
              result.w,
              mask);

  return (result.x == 6.25f && result.y == -2.5f && result.z == 0.0f && result.w == 4.5f &&
          mask == 2) ?
             0 :
             1;
}
