/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#pragma once

/* Emscripten supplies SSE1-SSE4.2 compatibility intrinsics through this
 * architecture-neutral umbrella. Clang's x86intrin.h is not wasm-safe. */
#include <immintrin.h>

#define __KERNEL_SSE__
#define __KERNEL_SSE2__
#define __KERNEL_SSE3__
#define __KERNEL_SSSE3__
#define __KERNEL_SSE42__
