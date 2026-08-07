# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M7-io probe: report availability of the launch-tier IO export operators on the
# wasm build (OBJ native C++ path; glTF Python addon). Tagged one-line output.
import bpy, sys, addon_utils

def has_op(path):
    mod, _, op = path.partition(".")
    return hasattr(getattr(bpy.ops, mod, None), op)

print("BPY_OK", bpy.app.version_string, len(bpy.data.objects))
# OBJ (native C++ exporter, WITH_IO_WAVEFRONT_OBJ)
print("OP_wm_obj_export", has_op("wm.obj_export"))
print("OP_wm_obj_import", has_op("wm.obj_import"))
# USD (native, WITH_USD)
print("OP_wm_usd_export", has_op("wm.usd_export"))
# glTF (python addon io_scene_gltf2)
print("OP_export_scene_gltf", has_op("export_scene.gltf"))
# Is the gltf addon already registered under factory-startup?
mods = {m.__name__ for m in addon_utils.modules()}
print("ADDON_gltf_visible", "io_scene_gltf2" in mods)
print("ADDON_gltf_enabled", addon_utils.check("io_scene_gltf2")[1])
sys.stdout.flush()
