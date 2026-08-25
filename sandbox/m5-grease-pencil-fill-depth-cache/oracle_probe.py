# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

import json

import bpy


operator = bpy.ops.grease_pencil.fill
operator_rna = operator.get_rna_type()
record = {
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
print("M5_GREASE_PENCIL_FILL_ORACLE " + json.dumps(record, sort_keys=True))
