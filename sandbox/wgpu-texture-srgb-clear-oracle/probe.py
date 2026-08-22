# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

import bpy
import gpu
from gpu_extras.batch import batch_for_shader


def run_oracle() -> None:
    gpu.init()

    source = gpu.types.GPUTexture(4, format="SRGB8_A8")
    source.clear(format="FLOAT", value=(0.25, 0.5, 0.75, 0.5))

    interface = gpu.types.GPUStageInterfaceInfo("srgb_clear_interface")
    interface.smooth("FLOAT", "coordinate")
    info = gpu.types.GPUShaderCreateInfo()
    info.sampler(0, "FLOAT_1D", "source_texture")
    info.vertex_in(0, "VEC2", "position")
    info.vertex_in(1, "FLOAT", "source_coordinate")
    info.vertex_out(interface)
    info.fragment_out(0, "VEC4", "fragment_color")
    info.vertex_source(
        "void main() {"
        "  coordinate = source_coordinate;"
        "  gl_Position = vec4(position, 0.0, 1.0);"
        "}"
    )
    info.fragment_source(
        "void main() {"
        "  fragment_color = texture(source_texture, coordinate);"
        "}"
    )
    shader = gpu.shader.create_from_info(info)
    batch = batch_for_shader(
        shader,
        "TRI_STRIP",
        {
            "position": ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)),
            "source_coordinate": (0.5, 0.5, 0.5, 0.5),
        },
    )

    offscreen = gpu.types.GPUOffScreen(1, 1)
    with offscreen.bind():
        gpu.state.viewport_set(0, 0, 1, 1)
        framebuffer = gpu.state.active_framebuffer_get()
        framebuffer.clear(color=(0.0, 0.0, 0.0, 0.0))
        shader.uniform_sampler("source_texture", source)
        batch.draw(shader)
        sampled = offscreen.texture_color.read().to_list()[0][0]

    expected = [64, 128, 191, 128]
    assert all(abs(actual - reference) <= 1 for actual, reference in zip(sampled, expected)), (
        sampled,
        expected,
    )
    print(f"ORACLE_TEXTURE_1D_SRGB_CLEAR_PASS sampled={sampled}")


try:
    run_oracle()
finally:
    bpy.ops.wm.quit_blender()
