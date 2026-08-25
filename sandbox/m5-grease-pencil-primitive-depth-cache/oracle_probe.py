# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

import json

import bpy


operator_names = [
    "primitive_line",
    "primitive_polyline",
    "primitive_arc",
    "primitive_curve",
    "primitive_box",
    "primitive_circle",
]

records = []
for name in operator_names:
    operator = getattr(bpy.ops.grease_pencil, name)
    operator_rna = operator.get_rna_type()
    records.append(
        {
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
    )

print("M5_GREASE_PENCIL_PRIMITIVE_ORACLE " + json.dumps(records, sort_keys=True))
