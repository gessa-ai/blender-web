// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

#include <array>
#include <cstdint>
#include <cstdio>
#include <vector>

namespace wgpu {

enum class FeatureName : uint8_t {
  Unorm16TextureFormats,
  RG11B10UfloatRenderable,
  Float32Filterable,
  TextureComponentSwizzle,
  Depth32FloatStencil8,
  TextureFormatsTier1,
  TextureFormatsTier2,
  ClipDistances,
  DualSourceBlending,
};

}  // namespace wgpu

namespace {

constexpr std::array<wgpu::FeatureName, 9> kFeatureOrder = {
    wgpu::FeatureName::Unorm16TextureFormats,
    wgpu::FeatureName::RG11B10UfloatRenderable,
    wgpu::FeatureName::Float32Filterable,
    wgpu::FeatureName::TextureComponentSwizzle,
    wgpu::FeatureName::Depth32FloatStencil8,
    wgpu::FeatureName::TextureFormatsTier1,
    wgpu::FeatureName::TextureFormatsTier2,
    wgpu::FeatureName::ClipDistances,
    wgpu::FeatureName::DualSourceBlending,
};

struct Adapter {
  uint32_t mask = 0;

  bool HasFeature(const wgpu::FeatureName feature) const
  {
    return (mask & (uint32_t(1) << uint32_t(feature))) != 0;
  }
};

#include "ghost_wgpu_optional_features.inc"

bool verify_mask(const uint32_t mask)
{
  const std::vector<wgpu::FeatureName> actual = select_optional_features(Adapter{mask});
  size_t cursor = 0;
  for (const wgpu::FeatureName feature : kFeatureOrder) {
    const bool enabled = (mask & (uint32_t(1) << uint32_t(feature))) != 0;
    if (!enabled) {
      continue;
    }
    if (cursor >= actual.size() || actual[cursor] != feature) {
      return false;
    }
    cursor++;
  }
  return cursor == actual.size();
}

}  // namespace

int main()
{
  for (uint32_t mask = 0; mask < 512; mask++) {
    if (!verify_mask(mask)) {
      std::fprintf(stderr, "optional-feature contract failed at mask=%u\n", mask);
      return 1;
    }
  }
  std::puts(
      "T3 OPTIONAL FEATURE CONTRACT PASS features=9 masks=512 float32_index=2 swizzle_index=3");
  return 0;
}
