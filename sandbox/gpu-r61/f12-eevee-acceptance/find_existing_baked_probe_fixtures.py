# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read-only scan for upstream blends recognized as pre-baked by EEVEE setup."""

import json
from pathlib import Path

import bpy


root = Path("/Users/paws/blender-web/upstream/tests/files/render")
matches = []
failures = []
for path in sorted(root.rglob("*.blend")):
    try:
        bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False)
        obj = bpy.data.objects.get("Volume_Probe_Baked")
        if obj is not None:
            matches.append(
                {
                    "path": str(path),
                    "object_type": obj.type,
                    "data_name": getattr(obj.data, "name", None),
                    "probe_type": getattr(obj.data, "type", None),
                    "bytes": path.stat().st_size,
                }
            )
    except Exception as error:
        failures.append({"path": str(path), "error": repr(error)})

print(
    "BW_EXISTING_BAKED_PROBE_SCAN "
    + json.dumps(
        {"files": len(list(root.rglob('*.blend'))), "matches": matches, "failures": failures},
        sort_keys=True,
    )
)
