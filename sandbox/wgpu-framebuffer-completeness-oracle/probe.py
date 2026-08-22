# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

import gpu


gpu.init()

wide = gpu.types.GPUTexture(
    size=(2, 2),
    layers=2,
    format="RGBA8",
    data=gpu.types.Buffer("FLOAT", 2 * 2 * 2 * 4, [1.0, 0.0, 0.0, 1.0] * 8),
)
narrow = gpu.types.GPUTexture(
    size=(2, 2),
    layers=1,
    format="RGBA8",
    data=gpu.types.Buffer("FLOAT", 2 * 2 * 4, [0.0, 1.0, 0.0, 1.0] * 4),
)

framebuffer = gpu.types.GPUFrameBuffer(color_slots=[wide, narrow])
with framebuffer.bind():
    framebuffer.clear(color=(0.0, 0.0, 1.0, 1.0))

def read_layer(texture, layer):
    reader = gpu.types.GPUFrameBuffer(
        color_slots=[{"texture": texture, "layer": layer}]
    )
    with reader.bind():
        return reader.read_color(0, 0, 1, 1, 4, 0, "UBYTE").to_list()[0][0]


wide_pixels = [read_layer(wide, 0), read_layer(wide, 1)]
narrow_pixels = [read_layer(narrow, 0)]
assert wide_pixels == [[0, 0, 255, 255], [0, 0, 255, 255]], wide_pixels
assert narrow_pixels == [[0, 0, 255, 255]], narrow_pixels
print(
    "ORACLE_FRAMEBUFFER_LAYERED_CLEAR_PASS "
    f"wide={wide_pixels} narrow={narrow_pixels}"
)
