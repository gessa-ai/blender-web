# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Import then re-export OBJ and GLB through Blender's real wasm operators."""

import os
import sys

import addon_utils
import bpy


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def mesh_summary(label):
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"{label}: expected 1 mesh, found {len(meshes)}")
    mesh = meshes[0].data
    summary = (len(mesh.vertices), len(mesh.edges), len(mesh.polygons), len(mesh.loops))
    print(f"{label}_MESH verts={summary[0]} edges={summary[1]} "
          f"polys={summary[2]} loops={summary[3]}")
    sys.stdout.flush()
    return summary


# OBJ: C++ import and export, not a parser-only proxy.
reset_scene()
bpy.ops.wm.obj_import(filepath=os.environ["M7_OBJ_IN"])
obj_summary = mesh_summary("OBJ_IMPORT")
if obj_summary != (8, 12, 6, 24):
    raise RuntimeError(f"OBJ topology changed: {obj_summary}")
bpy.ops.wm.obj_export(filepath=os.environ["M7_OBJ_RT"], export_selected_objects=False,
                      apply_modifiers=True)
print("OBJ_ROUNDTRIP_OK", os.environ["M7_OBJ_RT"], os.path.getsize(os.environ["M7_OBJ_RT"]))
sys.stdout.flush()


if not addon_utils.check("io_scene_gltf2")[1]:
    addon_utils.enable("io_scene_gltf2", default_set=True, persistent=True)

reset_scene()
bpy.ops.import_scene.gltf(filepath=os.environ["M7_GLB_IN"])
gltf_summary = mesh_summary("GLTF_IMPORT")
if gltf_summary[2:] != (12, 36):
    raise RuntimeError(f"glTF topology changed: {gltf_summary}")
bpy.ops.export_scene.gltf(filepath=os.environ["M7_GLB_RT"], export_format="GLB",
                          use_selection=False)
print("GLTF_ROUNDTRIP_OK", os.environ["M7_GLB_RT"], os.path.getsize(os.environ["M7_GLB_RT"]))
sys.stdout.flush()
