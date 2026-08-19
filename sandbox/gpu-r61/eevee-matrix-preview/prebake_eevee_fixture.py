# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pinned official-Blender worker for one EEVEE prebaked fixture.

The worker executes the unmodified upstream ``eevee_render_tests.py::setup``
definition. After the bake returns, it only adds fixture provenance, gives the
new volume probe the upstream recognition identity ``Volume_Probe_Baked``, and
saves a new file. All paths and hashes come from the guarded serial launcher.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path("/Users/paws/blender-web")
RENDER_ROOT = ROOT / "upstream/tests/files/render"
SETUP_SOURCE = ROOT / "upstream/tests/python/eevee_render_tests.py"
INPUT_CONTRACT = ROOT / "sandbox/gpu-r61/eevee-matrix-preview/eevee-input-contract.tsv"
PIN_FILE = ROOT / "oracle/PIN"
PINNED_BUILD_HASH = "fbe6228777e7"
PINNED_SETUP_SHA256 = "18a5e10c897df2180f97021657162bc1544b1b8d29fa18c6b98f705f20435af2"
SETUP_SEPARATOR = "# When run from inside Blender, render and exit."
ENV_PREFIX = "BW_EEVEE_PREBAKE_"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def required_env(name: str) -> str:
    key = ENV_PREFIX + name
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"required environment variable is absent: {key}")
    return value


def within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def setup_definition() -> tuple[str, str]:
    source = SETUP_SOURCE.read_text(encoding="utf-8")
    definition, separator, _runner = source.partition(SETUP_SEPARATOR)
    if not separator:
        raise RuntimeError("could not isolate pinned EEVEE setup definition")
    return source, definition


def selfcheck() -> None:
    assert PIN_FILE.read_text(encoding="utf-8").split()[0] == PINNED_BUILD_HASH
    assert sha256(SETUP_SOURCE) == PINNED_SETUP_SHA256
    assert INPUT_CONTRACT.is_file()
    source, definition = setup_definition()
    ast.parse(source, filename=str(SETUP_SOURCE))
    ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=__file__)
    required = [
        "def setup():",
        'scene.get("EEVEE_skip_probes_setup", False)',
        "eevee.gi_cubemap_resolution = '256'",
        "bpy.ops.object.lightprobe_add(type='SPHERE', location=(0.0, 0.1, 1.0))",
        "cubemap.scale = (5.0, 5.0, 2.0)",
        "cubemap.data.falloff = 0.0",
        "cubemap.data.clip_start = 0.8",
        "cubemap.data.influence_distance = 1.2",
        "bpy.ops.object.lightprobe_add(type='VOLUME', location=(0.0, 0.0, 2.0))",
        "grid.scale = (8.0, 4.5, 4.5)",
        "grid.data.resolution_x = 32",
        "grid.data.resolution_y = 16",
        "grid.data.resolution_z = 8",
        "grid.data.bake_samples = 128",
        "grid.data.capture_world = True",
        "grid.data.surfel_density = 100",
        "grid.data.dilation_threshold = 1.0",
        "bpy.ops.object.lightprobe_cache_bake(subset='ACTIVE')",
    ]
    assert all(item in definition for item in required)
    print(
        "SELF_CHECK_PASS worker=eevee-native-prebake "
        f"pin={PINNED_BUILD_HASH} setup_sha256={PINNED_SETUP_SHA256} bakes=0"
    )


def probe_snapshot(obj) -> dict:
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


def render_sampling_snapshot(bpy) -> dict:
    scene = bpy.context.scene
    view_layer_samples = bpy.context.view_layer.samples
    scene_samples = scene.eevee.taa_render_samples
    effective = view_layer_samples if view_layer_samples > 0 else scene_samples
    return {
        "scene": scene.name,
        "scene_count": len(bpy.data.scenes),
        "view_layer": bpy.context.view_layer.name,
        "view_layer_samples": view_layer_samples,
        "scene_taa_render_samples": scene_samples,
        "effective": effective,
        "view_transform": scene.view_settings.view_transform,
    }


def write_receipt_exclusive(path: Path, receipt: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")


def common_configuration(bpy) -> dict:
    mode = required_env("MODE")
    if mode not in {"bake", "verify-skip"}:
        raise RuntimeError(f"unsupported prebake mode: {mode}")
    input_path = Path(required_env("INPUT")).resolve()
    receipt_path = Path(required_env("RECEIPT")).resolve()
    run_root = Path(required_env("RUN_ROOT")).resolve()
    row_key = required_env("ROW_KEY")
    expected_input_sha256 = required_env("INPUT_SHA256")
    expected_blender_sha256 = required_env("BLENDER_SHA256")
    expected_samples = int(required_env("EXPECTED_SAMPLES"))
    if expected_samples < 1:
        raise RuntimeError(f"expected samples must be positive, found {expected_samples}")
    expected_view_transform = required_env("EXPECTED_VIEW_TRANSFORM")
    expected_skip_raw = required_env("SKIP_PROBES")
    if expected_skip_raw not in {"true", "false"}:
        raise RuntimeError(f"invalid probe-skip contract value: {expected_skip_raw}")
    expected_skip_probes = expected_skip_raw == "true"
    expected_contract_sha256 = required_env("INPUT_CONTRACT_SHA256")
    blender_path = Path(required_env("BLENDER_PATH")).resolve()
    if not within(input_path, RENDER_ROOT):
        raise RuntimeError(f"input is outside pinned render corpus: {input_path}")
    if not within(receipt_path, run_root):
        raise RuntimeError(f"receipt is outside guarded run root: {receipt_path}")
    if receipt_path.exists():
        raise RuntimeError(f"refusing to overwrite receipt: {receipt_path}")
    if Path(bpy.data.filepath).resolve() != input_path:
        raise RuntimeError(f"loaded blend mismatch: {bpy.data.filepath} != {input_path}")
    if sha256(input_path) != expected_input_sha256:
        raise RuntimeError(f"input hash mismatch for {row_key}")
    if sha256(SETUP_SOURCE) != PINNED_SETUP_SHA256:
        raise RuntimeError("pinned EEVEE setup source hash mismatch")
    if sha256(INPUT_CONTRACT) != expected_contract_sha256:
        raise RuntimeError("pinned EEVEE input contract hash mismatch")
    actual_binary = Path(bpy.app.binary_path).resolve()
    if actual_binary != blender_path:
        raise RuntimeError(f"Blender binary path mismatch: {actual_binary} != {blender_path}")
    if sha256(actual_binary) != expected_blender_sha256:
        raise RuntimeError("official Blender binary hash mismatch")
    build_hash = bpy.app.build_hash.decode("ascii")
    if not build_hash.startswith(PINNED_BUILD_HASH):
        raise RuntimeError(f"official Blender build hash mismatch: {build_hash}")
    if bpy.context.mode != "OBJECT":
        raise RuntimeError(f"fixture must load in OBJECT mode, found {bpy.context.mode}")
    if len(bpy.data.scenes) != 1:
        raise RuntimeError(f"fixture input must contain exactly one scene, found {len(bpy.data.scenes)}")
    sampling = render_sampling_snapshot(bpy)
    if sampling["effective"] != expected_samples:
        raise RuntimeError(
            f"effective render samples mismatch: {sampling['effective']} != {expected_samples}"
        )
    if sampling["view_transform"] != expected_view_transform:
        raise RuntimeError(
            f"view transform mismatch: {sampling['view_transform']} != {expected_view_transform}"
        )
    actual_skip_probes = bool(bpy.context.scene.get("EEVEE_skip_probes_setup", False))
    if actual_skip_probes != expected_skip_probes:
        raise RuntimeError(
            f"probe-skip contract mismatch: {actual_skip_probes} != {expected_skip_probes}"
        )
    if bpy.data.objects.get("Volume_Probe_Baked") is not None:
        raise RuntimeError("pinned manifest input unexpectedly contains Volume_Probe_Baked")
    return {
        "mode": mode,
        "input_path": input_path,
        "input_sha256": expected_input_sha256,
        "receipt_path": receipt_path,
        "run_root": run_root,
        "row_key": row_key,
        "blender_path": blender_path,
        "blender_sha256": expected_blender_sha256,
        "build_hash": build_hash,
        "expected_samples": expected_samples,
        "expected_view_transform": expected_view_transform,
        "expected_skip_probes": expected_skip_probes,
        "input_contract_sha256": expected_contract_sha256,
        "render_sampling": sampling,
    }


def exclusion_receipt(bpy, config: dict) -> dict:
    scene_flags = [
        {
            "scene": scene.name,
            "EEVEE_skip_probes_setup": bool(scene.get("EEVEE_skip_probes_setup", False)),
        }
        for scene in bpy.data.scenes
    ]
    if not scene_flags or not all(item["EEVEE_skip_probes_setup"] for item in scene_flags):
        raise RuntimeError(f"excluded row is not a probe-skip scene: {scene_flags}")
    return {
        "schema": "blender-web.eevee-native-prebake-exclusion.v1",
        "row": config["row_key"],
        "reason": "upstream scene property EEVEE_skip_probes_setup=true",
        "input": {"path": str(config["input_path"]), "sha256": config["input_sha256"]},
        "setup": {"path": str(SETUP_SOURCE), "sha256": PINNED_SETUP_SHA256},
        "input_contract": {
            "path": str(INPUT_CONTRACT),
            "sha256": config["input_contract_sha256"],
        },
        "worker": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__))},
        "blender": {
            "path": str(config["blender_path"]),
            "sha256": config["blender_sha256"],
            "version": bpy.app.version_string,
            "build_hash": config["build_hash"],
        },
        "scene_flags": scene_flags,
        "render_sampling": config["render_sampling"],
        "bake_executed": False,
        "output_fixture": None,
    }


def bake_receipt(bpy, config: dict) -> dict:
    output_path = Path(required_env("OUTPUT")).resolve()
    if not within(output_path, config["run_root"]):
        raise RuntimeError(f"output is outside guarded run root: {output_path}")
    if output_path.exists():
        raise RuntimeError(f"refusing to overwrite fixture: {output_path}")
    scene_flags = [
        {
            "scene": scene.name,
            "EEVEE_skip_probes_setup": bool(scene.get("EEVEE_skip_probes_setup", False)),
        }
        for scene in bpy.data.scenes
    ]
    if not scene_flags or any(item["EEVEE_skip_probes_setup"] for item in scene_flags):
        raise RuntimeError(f"bake row contains a probe-skip scene: {scene_flags}")

    before_probe_pointers = {
        obj.as_pointer() for obj in bpy.data.objects if obj.type == "LIGHT_PROBE"
    }
    _source, definition_source = setup_definition()
    namespace = {"__file__": str(SETUP_SOURCE), "__name__": "bw_pinned_eevee_setup"}
    exec(compile(definition_source, str(SETUP_SOURCE), "exec"), namespace)
    namespace["setup"]()

    new_probes = [
        obj
        for obj in bpy.data.objects
        if obj.type == "LIGHT_PROBE" and obj.as_pointer() not in before_probe_pointers
    ]
    spheres = [obj for obj in new_probes if obj.data.type == "SPHERE"]
    volumes = [obj for obj in new_probes if obj.data.type == "VOLUME"]
    if len(spheres) != 1 or len(volumes) != 1:
        raise RuntimeError(
            "upstream setup did not create exactly one sphere and one volume: "
            + json.dumps([probe_snapshot(obj) for obj in new_probes], sort_keys=True)
        )
    volume = volumes[0]
    volume.name = "Volume_Probe_Baked"
    volume.data.name = "Volume_Probe_Baked"

    scene = bpy.context.scene
    scene["BW_fixture_schema"] = "blender-web.eevee-native-prebake.v2"
    scene["BW_fixture_row"] = config["row_key"]
    scene["BW_fixture_input_sha256"] = config["input_sha256"]
    scene["BW_fixture_setup_sha256"] = PINNED_SETUP_SHA256
    scene["BW_fixture_blender_build_hash"] = config["build_hash"]
    scene["BW_fixture_input_contract_sha256"] = config["input_contract_sha256"]
    scene["BW_fixture_effective_render_samples"] = config["expected_samples"]
    scene["BW_fixture_view_transform"] = config["expected_view_transform"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path), check_existing=False)
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"saved fixture is absent or empty: {output_path}")
    all_probes = [obj for obj in bpy.data.objects if obj.type == "LIGHT_PROBE"]
    return {
        "schema": "blender-web.eevee-native-prebake-receipt.v2",
        "row": config["row_key"],
        "input": {"path": str(config["input_path"]), "sha256": config["input_sha256"]},
        "setup": {"path": str(SETUP_SOURCE), "sha256": PINNED_SETUP_SHA256},
        "input_contract": {
            "path": str(INPUT_CONTRACT),
            "sha256": config["input_contract_sha256"],
        },
        "worker": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__))},
        "blender": {
            "path": str(config["blender_path"]),
            "sha256": config["blender_sha256"],
            "version": bpy.app.version_string,
            "build_hash": config["build_hash"],
        },
        "output": {
            "path": str(output_path),
            "sha256": sha256(output_path),
            "bytes": output_path.stat().st_size,
        },
        "scene_flags": scene_flags,
        "render_sampling": config["render_sampling"],
        "upstream_setup_returned": True,
        "new_probes": [probe_snapshot(obj) for obj in new_probes],
        "all_probes": [probe_snapshot(obj) for obj in all_probes],
        "recognition_identity": {
            "lookup": "bpy.data.objects.get('Volume_Probe_Baked')",
            "object_name": volume.name,
            "data_name": volume.data.name,
            "object_type": volume.type,
            "probe_type": volume.data.type,
        },
        "active_object": bpy.context.view_layer.objects.active.name
        if bpy.context.view_layer.objects.active
        else None,
        "scene_provenance": {
            key: scene[key] for key in sorted(scene.keys()) if key.startswith("BW_fixture_")
        },
    }


def main() -> None:
    import bpy

    config = common_configuration(bpy)
    receipt = (
        exclusion_receipt(bpy, config)
        if config["mode"] == "verify-skip"
        else bake_receipt(bpy, config)
    )
    write_receipt_exclusive(config["receipt_path"], receipt)
    print("BW_EEVEE_PREBAKE_RECEIPT " + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    if sys.argv[1:] == ["--selfcheck"]:
        selfcheck()
    else:
        main()
