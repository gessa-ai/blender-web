# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# One-line Subsurf smoke: subdivide the factory default cube (8 verts, 6 quads) with a
# Catmull-Clark Subdivision Surface modifier at level 1 and report the evaluated vertex
# count. Catmull-Clark L1 of a cube = 8 corners + 12 edge points + 6 face points = 26.
# Runs identically on the wasm binary and the native pin oracle (oracle/bpy.sh); the two
# counts must match. Also probes that the native C++ mesh exporters are now present.
import bpy

for op in ("obj_export", "ply_export", "stl_export"):
    print("OP_PRESENT", op, hasattr(bpy.ops.wm, op))

obj = bpy.data.objects.get("Cube")
assert obj is not None, "factory-startup default Cube missing"
base_verts = len(obj.data.vertices)
mod = obj.modifiers.new("subsurf", "SUBSURF")
mod.levels = 1
mod.render_levels = 1
deps = bpy.context.evaluated_depsgraph_get()
eval_mesh = obj.evaluated_get(deps).to_mesh()
n = len(eval_mesh.vertices)
print("SUBSURF_SMOKE base_verts=%d level1_verts=%d" % (base_verts, n))
print("SUBSURF_SMOKE_OK" if n == 26 else "SUBSURF_SMOKE_UNEXPECTED")
