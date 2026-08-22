# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

import gpu


gpu.init()

width = 2
height = 2
layers = 3
texture = gpu.types.GPUTexture(
    size=(width, height),
    layers=layers,
    format="RGBA8",
    data=gpu.types.Buffer(
        "FLOAT",
        width * height * layers * 4,
        [1.0, 0.0, 0.0, 1.0] * (width * height * layers),
    ),
)

# A bare texture attachment selects all array layers, matching
# GPU_ATTACHMENT_TEXTURE and explicit load-action scope in the C++ API.
all_layers = gpu.types.GPUFrameBuffer(color_slots=[texture])
with all_layers.bind():
    all_layers.clear(color=(0.0, 1.0, 0.0, 1.0))

expected = [[[0, 255, 0, 255]] * width for _ in range(height)]
observed = []
for layer in range(layers):
    selected = gpu.types.GPUFrameBuffer(
        color_slots=[{"texture": texture, "layer": layer}]
    )
    with selected.bind():
        pixels = selected.read_color(0, 0, width, height, 4, 0, "UBYTE").to_list()
    assert pixels == expected, (layer, pixels)
    observed.append(pixels)

print(f"ORACLE_FRAMEBUFFER_ALL_LAYER_CLEAR_PASS layers={len(observed)}")
