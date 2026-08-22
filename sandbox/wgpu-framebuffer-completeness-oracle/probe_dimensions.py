# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

import gpu


gpu.init()


def texture(size, color):
    pixel_count = size[0] * size[1]
    return gpu.types.GPUTexture(
        size=size,
        format="RGBA8",
        data=gpu.types.Buffer("FLOAT", pixel_count * 4, list(color) * pixel_count),
    )


wide = texture((2, 2), (1.0, 0.0, 0.0, 1.0))
narrow = texture((1, 1), (0.0, 1.0, 0.0, 1.0))
framebuffer = gpu.types.GPUFrameBuffer(color_slots=[wide, narrow])
with framebuffer.bind():
    framebuffer.clear(color=(0.0, 0.0, 1.0, 1.0))


def read(texture, width, height):
    reader = gpu.types.GPUFrameBuffer(color_slots=[texture])
    with reader.bind():
        return reader.read_color(0, 0, width, height, 4, 0, "UBYTE").to_list()


wide_pixels = read(wide, 2, 2)
narrow_pixels = read(narrow, 1, 1)
assert wide_pixels == [
    [[0, 0, 255, 255], [255, 0, 0, 255]],
    [[255, 0, 0, 255], [255, 0, 0, 255]],
], wide_pixels
assert narrow_pixels == [[[0, 0, 255, 255]]], narrow_pixels
print(
    "ORACLE_FRAMEBUFFER_INTERSECTION_PASS "
    f"wide={wide_pixels} narrow={narrow_pixels}"
)
