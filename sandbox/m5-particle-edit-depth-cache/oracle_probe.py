# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

import json

import bpy


operators = {
    "click": bpy.ops.view3d.select,
    "linked": bpy.ops.particle.select_linked_pick,
    "box": bpy.ops.view3d.select_box,
    "lasso": bpy.ops.view3d.select_lasso,
    "circle": bpy.ops.view3d.select_circle,
    "brush": bpy.ops.particle.brush_edit,
}

record = {}
for name, operator in operators.items():
    operator_rna = operator.get_rna_type()
    record[name] = {
        "idname": operator.idname(),
        "poll": operator.poll(),
        "properties": [
            {
                "identifier": prop.identifier,
                "type": prop.type,
                "array_length": getattr(prop, "array_length", 0),
                "is_readonly": prop.is_readonly,
            }
            for prop in operator_rna.properties
            if prop.identifier != "rna_type"
        ],
    }

print("M5_PARTICLE_EDIT_DEPTH_ORACLE " + json.dumps(record, sort_keys=True))
