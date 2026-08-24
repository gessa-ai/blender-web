# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0

"""Load and optionally round-trip the pinned BHead4 fixture inside Blender."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import bpy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("snapshot", "roundtrip"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pre-state", type=Path, required=True)
    parser.add_argument("--post-state", type=Path)
    argv = list(__import__("sys").argv)
    return parser.parse_args(argv[argv.index("--") + 1 :] if "--" in argv else [])


def normalized(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AssertionError(f"non-finite fixture value: {value!r}")
        rounded = round(value, 6)
        return 0.0 if rounded == 0 else rounded
    try:
        return [normalized(item) for item in value]
    except TypeError:
        pass
    raise AssertionError(f"unsupported fixture value: {type(value).__name__}")


def snapshot() -> dict[str, Any]:
    build_hash = (
        bpy.app.build_hash.decode()
        if isinstance(bpy.app.build_hash, bytes)
        else str(bpy.app.build_hash)
    )
    return {
        "schema": 1,
        "runtime": {"version": list(bpy.app.version), "build_hash": build_hash},
        "scenes": [
            {
                "name": scene.name,
                "root": scene.collection.name,
                "frame": [scene.frame_start, scene.frame_end, scene.frame_current],
                "objects": sorted(obj.name for obj in scene.objects),
            }
            for scene in sorted(bpy.data.scenes, key=lambda item: item.name)
        ],
        "objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "data": obj.data.name if obj.data is not None else None,
                "location": normalized(obj.location),
                "rotation": normalized(obj.rotation_euler),
                "scale": normalized(obj.scale),
            }
            for obj in sorted(bpy.data.objects, key=lambda item: item.name)
        ],
        "meshes": [
            {
                "name": mesh.name,
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
            }
            for mesh in sorted(bpy.data.meshes, key=lambda item: item.name)
        ],
    }


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def open_file(path: Path) -> None:
    if not path.is_file():
        raise AssertionError(f"missing source file: {path}")
    result = bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
    if "FINISHED" not in result:
        raise AssertionError(f"failed to open fixture: {path} ({result})")


def main() -> None:
    args = parse_args()
    open_file(args.source)
    before = snapshot()
    write_state(args.pre_state, before)

    if args.mode == "roundtrip":
        if args.output is None or args.post_state is None:
            raise AssertionError("roundtrip requires --output and --post-state")
        result = bpy.ops.wm.save_as_mainfile(filepath=str(args.output), compress=False)
        if "FINISHED" not in result or not args.output.is_file():
            raise AssertionError(f"failed to save fixture: {args.output} ({result})")
        open_file(args.output)
        after = snapshot()
        write_state(args.post_state, after)
        if before != after:
            raise AssertionError("BHead4 state changed across the Wasm save/reload")

    print(f"BW_M7_BHEAD4_{args.mode.upper()}_OK", flush=True)


if __name__ == "__main__":
    main()
