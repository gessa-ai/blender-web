# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

import gpu


gpu.init()

width = 2
height = 2
layer_pixels = width * height
red = [1.0, 0.0, 0.0, 1.0]
green = [0.0, 1.0, 0.0, 1.0]
source = gpu.types.Buffer(
    "FLOAT",
    layer_pixels * 2 * 4,
    red * layer_pixels + green * layer_pixels,
)
texture = gpu.types.GPUTexture(
    size=(width, height), layers=2, format="RGBA8", data=source
)

for layer, expected in ((0, [255, 0, 0, 255]), (1, [0, 255, 0, 255])):
    framebuffer = gpu.types.GPUFrameBuffer(
        color_slots=[{"texture": texture, "layer": layer}]
    )
    with framebuffer.bind():
        for channels in range(1, 5):
            actual = framebuffer.read_color(
                0, 0, 1, 1, channels, 0, "UBYTE"
            ).to_list()
            assert actual == [[expected[:channels]]], (layer, channels, actual)
            print(
                "ORACLE_FRAMEBUFFER_LAYER_PASS "
                f"layer={layer} channels={channels} values={actual[0][0]}"
            )

for texture_format, pixel, expected in (
    ("R8", [0.25], [64, 0, 0, 255]),
    ("RG8", [0.25, 0.5], [64, 128, 0, 255]),
):
    source = gpu.types.Buffer("FLOAT", layer_pixels * len(pixel), pixel * layer_pixels)
    texture = gpu.types.GPUTexture(
        size=(width, height), format=texture_format, data=source
    )
    framebuffer = gpu.types.GPUFrameBuffer(color_slots=[texture])
    with framebuffer.bind():
        actual = framebuffer.read_color(0, 0, 1, 1, 4, 0, "UBYTE").to_list()
    assert actual == [[expected]], (texture_format, actual)
    print(
        "ORACLE_FRAMEBUFFER_CHANNEL_EXTEND_PASS "
        f"format={texture_format} values={actual[0][0]}"
    )
