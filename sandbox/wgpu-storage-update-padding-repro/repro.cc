/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

static volatile uint8_t observed;

__attribute__((noinline)) static void model_current_update(const void *payload,
                                                           const size_t logical_size)
{
  const size_t transfer_size = (logical_size + 3u) & ~size_t(3u);
  std::array<uint8_t, 4> dawn_copy = {};
  std::memcpy(dawn_copy.data(), payload, transfer_size);
  observed = dawn_copy[3];
}

int main()
{
  const auto *payload = new std::array<uint8_t, 3>{0x11, 0x22, 0x33};
  model_current_update(payload->data(), payload->size());
  delete payload;
  return 0;
}
