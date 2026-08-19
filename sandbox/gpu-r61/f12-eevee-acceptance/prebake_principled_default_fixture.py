# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Create a native-baked copy of the pinned principled-default EEVEE fixture.

This deliberately executes the unmodified ``eevee_render_tests.py::setup``
definition.  The only post-setup scene mutation is naming the newly baked
volume probe ``Volume_Probe_Baked`` so a later invocation of the same upstream
setup recognizes the cache and does not try to bake a second volume.
"""

import hashlib
import json
from pathlib import Path

import bpy


ROOT = Path("/Users/paws/blender-web")
INPUT = ROOT / "upstream/tests/files/render/principled_bsdf/principled_bsdf_default.blend"
SETUP_SOURCE = ROOT / "upstream/tests/python/eevee_render_tests.py"
OUTPUT = (
    ROOT
    / "sandbox/gpu-r61/f12-eevee-acceptance/fixtures/"
    / "principled_bsdf_default_upstream_setup_native_baked.blend"
)
RECEIPT = OUTPUT.with_suffix(".receipt.json")
PINNED_BUILD_HASH = "fbe6228777e7"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_snapshot(obj):
    probe = obj.data
    result = {
        "object_name": obj.name,
        "object_type": obj.type,
        "data_name": probe.name,
        "probe_type": probe.type,
        "location": list(obj.location),
        "scale": list(obj.scale),
    }
    if probe.type == "SPHERE":
        result.update(
            {
                "falloff": probe.falloff,
                "clip_start": probe.clip_start,
                "influence_distance": probe.influence_distance,
            }
        )
    elif probe.type == "VOLUME":
        result.update(
            {
                "resolution": [probe.resolution_x, probe.resolution_y, probe.resolution_z],
                "bake_samples": probe.bake_samples,
                "capture_world": probe.capture_world,
                "surfel_density": probe.surfel_density,
                "dilation_threshold": probe.dilation_threshold,
            }
        )
    return result


assert Path(bpy.data.filepath).resolve() == INPUT.resolve(), bpy.data.filepath
build_hash = bpy.app.build_hash.decode("ascii")
assert build_hash.startswith(PINNED_BUILD_HASH), build_hash
assert bpy.context.mode == "OBJECT", bpy.context.mode
assert not [obj for obj in bpy.context.scene.objects if obj.type == "LIGHT_PROBE"]

source = SETUP_SOURCE.read_text(encoding="utf-8")
definition_source, separator, _runner = source.partition(
    "# When run from inside Blender, render and exit."
)
assert separator, "could not isolate eevee_render_tests.py setup definition"
namespace = {"__file__": str(SETUP_SOURCE), "__name__": "bw_pinned_eevee_setup"}
exec(compile(definition_source, str(SETUP_SOURCE), "exec"), namespace)
namespace["setup"]()

probes = [obj for obj in bpy.context.scene.objects if obj.type == "LIGHT_PROBE"]
spheres = [obj for obj in probes if obj.data.type == "SPHERE"]
volumes = [obj for obj in probes if obj.data.type == "VOLUME"]
assert len(spheres) == 1, [probe_snapshot(obj) for obj in probes]
assert len(volumes) == 1, [probe_snapshot(obj) for obj in probes]

volume = volumes[0]
volume.name = "Volume_Probe_Baked"
volume.data.name = "Volume_Probe_Baked"

# Embed immutable provenance so browser-side inspection can prove which source
# and setup generated the serialized cache without relying on the host path.
scene = bpy.context.scene
scene["BW_fixture_schema"] = "blender-web.eevee-native-prebake.v1"
scene["BW_fixture_input_sha256"] = sha256(INPUT)
scene["BW_fixture_setup_sha256"] = sha256(SETUP_SOURCE)
scene["BW_fixture_blender_build_hash"] = build_hash

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT), check_existing=False)

receipt = {
    "schema": "blender-web.eevee-native-prebake-receipt.v1",
    "input": {"path": str(INPUT), "sha256": sha256(INPUT)},
    "setup": {"path": str(SETUP_SOURCE), "sha256": sha256(SETUP_SOURCE)},
    "blender": {
        "version": bpy.app.version_string,
        "build_hash": build_hash,
    },
    "output": {"path": str(OUTPUT), "sha256": sha256(OUTPUT)},
    "active_object": bpy.context.view_layer.objects.active.name
    if bpy.context.view_layer.objects.active
    else None,
    "probes": [probe_snapshot(obj) for obj in probes],
    "recognition_identity": {
        "lookup": "bpy.data.objects.get('Volume_Probe_Baked')",
        "object_name": volume.name,
        "data_name": volume.data.name,
        "object_type": volume.type,
        "probe_type": volume.data.type,
    },
    "scene_provenance": {
        key: scene[key]
        for key in sorted(scene.keys())
        if key.startswith("BW_fixture_")
    },
}
RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("BW_PREBAKE_RECEIPT " + json.dumps(receipt, sort_keys=True))
