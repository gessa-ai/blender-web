/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <emscripten/emscripten.h>

EMSCRIPTEN_KEEPALIVE int split_contract_probe(void)
{
  return 42;
}

int main(void)
{
  return split_contract_probe() == 42 ? 0 : 1;
}
