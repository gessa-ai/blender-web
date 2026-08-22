# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

import bpy
import gpu


WIDTH = 6
HEIGHT = 5
SCISSOR = (1, 1, 3, 2)
EXPECTED_SCISSOR = {
    (x, y)
    for y in range(SCISSOR[1], SCISSOR[1] + SCISSOR[3])
    for x in range(SCISSOR[0], SCISSOR[0] + SCISSOR[2])
}


def color_footprint(pixels, channel):
    return {
        (x, y)
        for y, row in enumerate(pixels)
        for x, pixel in enumerate(row)
        if pixel[channel] >= 250
    }


def depth_footprint(pixels, expected):
    return {
        (x, y)
        for y, row in enumerate(pixels)
        for x, value in enumerate(row)
        if abs(value - expected) <= 1.0e-6
    }


def run_single_layer_oracle():
    color = gpu.types.GPUTexture(size=(WIDTH, HEIGHT), format="RGBA8")
    depth = gpu.types.GPUTexture(size=(WIDTH, HEIGHT), format="DEPTH_COMPONENT32F")
    framebuffer = gpu.types.GPUFrameBuffer(depth_slot=depth, color_slots=[color])

    with framebuffer.bind():
        gpu.state.scissor_test_set(False)
        framebuffer.clear(color=(0.0, 0.0, 0.0, 1.0), depth=0.875)

        # A viewport alone does not bound framebuffer clears. The enabled scissor does.
        gpu.state.viewport_set(4, 4, 1, 1)
        gpu.state.scissor_set(*SCISSOR)
        gpu.state.scissor_test_set(True)
        framebuffer.clear(color=(1.0, 0.0, 0.0, 1.0), depth=0.25)

        colors = framebuffer.read_color(0, 0, WIDTH, HEIGHT, 4, 0, "UBYTE").to_list()
        depths = framebuffer.read_depth(0, 0, WIDTH, HEIGHT).to_list()
        red = color_footprint(colors, 0)
        shallow = depth_footprint(depths, 0.25)
        assert red == EXPECTED_SCISSOR, (red, EXPECTED_SCISSOR)
        assert shallow == EXPECTED_SCISSOR, (shallow, EXPECTED_SCISSOR)

        gpu.state.scissor_test_set(False)
        gpu.state.viewport_set(2, 2, 1, 1)
        framebuffer.clear(color=(0.0, 1.0, 0.0, 1.0), depth=0.625)
        colors = framebuffer.read_color(0, 0, WIDTH, HEIGHT, 4, 0, "UBYTE").to_list()
        depths = framebuffer.read_depth(0, 0, WIDTH, HEIGHT).to_list()
        green = color_footprint(colors, 1)
        medium = depth_footprint(depths, 0.625)

    expected_full = {(x, y) for y in range(HEIGHT) for x in range(WIDTH)}
    assert green == expected_full, (green, expected_full)
    assert medium == expected_full, (medium, expected_full)
    return red, shallow, green


def run_all_layer_oracle():
    layers = 3
    texture = gpu.types.GPUTexture(
        size=(WIDTH, HEIGHT),
        layers=layers,
        format="RGBA8",
        data=gpu.types.Buffer(
            "FLOAT", WIDTH * HEIGHT * layers * 4, [0.0, 0.0, 0.0, 1.0] * WIDTH * HEIGHT * layers
        ),
    )
    all_layers = gpu.types.GPUFrameBuffer(color_slots=[texture])
    with all_layers.bind():
        gpu.state.scissor_set(*SCISSOR)
        gpu.state.scissor_test_set(True)
        all_layers.clear(color=(1.0, 0.0, 0.0, 1.0))
        gpu.state.scissor_test_set(False)

    footprints = []
    for layer in range(layers):
        selected = gpu.types.GPUFrameBuffer(
            color_slots=[{"texture": texture, "layer": layer}]
        )
        with selected.bind():
            pixels = selected.read_color(0, 0, WIDTH, HEIGHT, 4, 0, "UBYTE").to_list()
        footprint = color_footprint(pixels, 0)
        assert footprint == EXPECTED_SCISSOR, (layer, footprint, EXPECTED_SCISSOR)
        footprints.append(footprint)
    return footprints


def run_oracle():
    gpu.init()
    red, shallow, full = run_single_layer_oracle()
    layers = run_all_layer_oracle()
    print(
        "ORACLE_FRAMEBUFFER_SCISSORED_CLEAR_PASS "
        f"rect={sorted(red)} depth={sorted(shallow)} full={len(full)} layers={len(layers)}"
    )


try:
    run_oracle()
finally:
    bpy.ops.wm.quit_blender()
