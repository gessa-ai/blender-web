# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

import bpy
import gpu
from gpu_extras.batch import batch_for_shader


WIDTH = 6
HEIGHT = 5


def make_shader():
    info = gpu.types.GPUShaderCreateInfo()
    info.vertex_in(0, "VEC2", "position")
    info.fragment_out(0, "VEC4", "fragment_color")
    info.vertex_source(
        "void main() {"
        "  gl_Position = vec4(position, 0.0, 1.0);"
        "}"
    )
    info.fragment_source(
        "void main() {"
        "  fragment_color = vec4(1.0, 0.0, 0.0, 1.0);"
        "}"
    )
    return gpu.shader.create_from_info(info)


def red_pixels(viewport, scissor=None):
    shader = make_shader()
    batch = batch_for_shader(
        shader,
        "TRI_STRIP",
        {"position": ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0))},
    )
    offscreen = gpu.types.GPUOffScreen(WIDTH, HEIGHT)
    with offscreen.bind():
        framebuffer = gpu.state.active_framebuffer_get()
        gpu.state.viewport_set(0, 0, WIDTH, HEIGHT)
        gpu.state.scissor_test_set(False)
        framebuffer.clear(color=(0.0, 0.0, 0.0, 1.0))
        gpu.state.viewport_set(*viewport)
        if scissor is not None:
            gpu.state.scissor_set(*scissor)
            gpu.state.scissor_test_set(True)
        batch.draw(shader)
        gpu.state.scissor_test_set(False)
        pixels = offscreen.texture_color.read().to_list()
    offscreen.free()

    return {
        (x, y)
        for y, row in enumerate(pixels)
        for x, pixel in enumerate(row)
        if pixel[0] >= 250 and pixel[1] <= 5 and pixel[2] <= 5
    }


def run_oracle():
    gpu.init()

    viewport_only = red_pixels((1, 1, 3, 2))
    expected_viewport = {(x, y) for y in range(1, 3) for x in range(1, 4)}
    assert viewport_only == expected_viewport, (viewport_only, expected_viewport)

    viewport_scissor = red_pixels((1, 0, 4, 4), (3, 2, 3, 3))
    expected_intersection = {(x, y) for y in range(2, 4) for x in range(3, 5)}
    assert viewport_scissor == expected_intersection, (
        viewport_scissor,
        expected_intersection,
    )

    print(
        "ORACLE_OFFSCREEN_VIEWPORT_SCISSOR_PASS "
        f"viewport={sorted(viewport_only)} intersection={sorted(viewport_scissor)}"
    )


try:
    run_oracle()
finally:
    bpy.ops.wm.quit_blender()
