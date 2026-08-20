// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DNA_userdef_types.h"

static_assert(blender::USER_GPU_BACKEND_WEBGPU == (1 << 2));
static_assert(blender::USER_GPU_BACKEND_DEFAULT == blender::USER_GPU_BACKEND_OPENGL);
static_assert(blender::USER_GPU_BACKEND_DEFAULT != blender::USER_GPU_BACKEND_WEBGPU);

int main()
{
  return 0;
}
