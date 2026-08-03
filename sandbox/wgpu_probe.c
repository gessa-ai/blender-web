/* SPDX-FileCopyrightText: 2026 blender-web contributors */
/* SPDX-License-Identifier: GPL-3.0-or-later */
/* emdawnwebgpu port resolution probe: include the webgpu header and
   reference a core type so the port's include path must resolve. */
#include <webgpu/webgpu.h>

int wgpu_probe(void) {
  return (int)sizeof(WGPUDevice);
}
