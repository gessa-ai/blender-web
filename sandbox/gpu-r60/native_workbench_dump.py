# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

import array
import json
import os

import bpy

out_dir = "/Users/paws/blender-web/sandbox/gpu-r60/browser/native-oracle"
os.makedirs(out_dir, exist_ok=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x = 128
scene.render.resolution_y = 128
scene.render.resolution_percentage = 100
scene.render.filepath = "/private/tmp/0143-native-workbench-oracle"
scene.render.image_settings.file_format = "PNG"
scene.frame_set(1)
bpy.ops.render.render(write_still=True)

image = bpy.data.images["Render Result"]
pixels = array.array("f", image.pixels[:])
with open(os.path.join(out_dir, "udim_native_rgba32.bin"), "wb") as handle:
    pixels.tofile(handle)
with open(os.path.join(out_dir, "udim_native_manifest.json"), "w", encoding="utf-8") as handle:
    json.dump({
        "blender_version": bpy.app.version_string,
        "backend": bpy.context.preferences.system.gpu_backend,
        "width": image.size[0],
        "height": image.size[1],
        "channels": image.channels,
        "float_count": len(pixels),
        "source": bpy.data.filepath,
    }, handle, indent=2)
