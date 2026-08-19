/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-3.0-or-later */

#include <emscripten.h>

int main(void)
{
  EM_ASM({ Module.bwGrowthHarnessModuleLoaded = true; });
  return 0;
}
