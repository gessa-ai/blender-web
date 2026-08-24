# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0

"""Author and round-trip the M7 omitted-type fidelity fixture inside Blender."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

import bpy


PIN = "fbe6228777e7"
MARKER = "m7-omitted-type-roundtrip-v1"

ROLE_SPECS = (
    {
        "role": "sequence_active",
        "target": "SEQUENCE_EDITOR",
        "active": True,
        "state": {
            "view_type": "PREVIEW",
            "display_mode": "WAVEFORM",
            "display_channel": 3,
            "preview_channels": "COLOR",
            "use_proxies": True,
            "show_overlays": False,
            "cursor_location": [13.25, 27.5],
        },
    },
    {
        "role": "sequence_inactive",
        "target": "SEQUENCE_EDITOR",
        "active": False,
        "state": {
            "view_type": "SEQUENCER_PREVIEW",
            "display_mode": "RGB_PARADE",
            "display_channel": 7,
            "preview_channels": "COLOR_ALPHA",
            "use_proxies": False,
            "show_overlays": True,
            "cursor_location": [-9.5, 41.75],
        },
    },
    {
        "role": "spreadsheet_active",
        "target": "SPREADSHEET",
        "active": True,
        "state": {
            "is_pinned": True,
            "show_internal_attributes": True,
            "use_filter": True,
            "show_only_selected": True,
            "geometry_item_type": "DOMAIN",
            "geometry_component_type": "MESH",
            "attribute_domain": "CORNER",
            "object_eval_state": "ORIGINAL",
        },
    },
    {
        "role": "spreadsheet_inactive",
        "target": "SPREADSHEET",
        "active": False,
        "state": {
            "is_pinned": False,
            "show_internal_attributes": False,
            "use_filter": True,
            "show_only_selected": False,
            "geometry_item_type": "DOMAIN",
            "geometry_component_type": "CURVE",
            "attribute_domain": "POINT",
            "object_eval_state": "EVALUATED",
        },
    },
    {
        "role": "clip_active",
        "target": "CLIP_EDITOR",
        "active": True,
        "state": {
            "mode": "MASK",
            "view": "GRAPH",
            "show_marker_pattern": False,
            "show_marker_search": True,
            "lock_selection": True,
            "lock_time_cursor": True,
            "show_track_path": True,
            "path_length": 17,
            "show_names": True,
            "show_grid": False,
            "cursor_location": [0.3125, 0.6875],
            "pivot_point": "CURSOR",
        },
    },
    {
        "role": "clip_inactive",
        "target": "CLIP_EDITOR",
        "active": False,
        "state": {
            "mode": "TRACKING",
            "view": "DOPESHEET",
            "show_marker_pattern": True,
            "show_marker_search": False,
            "lock_selection": False,
            "lock_time_cursor": False,
            "show_track_path": False,
            "path_length": 31,
            "show_names": False,
            "show_grid": True,
            "cursor_location": [0.8125, 0.1875],
            "pivot_point": "INDIVIDUAL_ORIGINS",
        },
    },
    {
        "role": "nla_active",
        "target": "NLA_EDITOR",
        "active": True,
        "state": {
            "show_seconds": True,
            "show_strip_curves": True,
            "show_local_markers": True,
            "show_markers": False,
            "use_realtime_update": False,
        },
    },
    {
        "role": "nla_inactive",
        "target": "NLA_EDITOR",
        "active": False,
        "state": {
            "show_seconds": False,
            "show_strip_curves": False,
            "show_local_markers": False,
            "show_markers": True,
            "use_realtime_update": True,
        },
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("author", "roundtrip"), required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
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


def set_state(space: Any, state: dict[str, Any]) -> None:
    for name, value in state.items():
        if not hasattr(space, name):
            raise AssertionError(f"{space.bl_rna.identifier} lacks required field {name}")
        setattr(space, name, value)
        actual = normalized(getattr(space, name))
        if actual != normalized(value):
            raise AssertionError(f"failed to set {space.type}.{name}: {actual!r} != {value!r}")


def author_fixture() -> None:
    bpy.context.scene["bw_m7_roundtrip_marker"] = MARKER
    tree = bpy.data.node_groups.get("BWRT_COMPOSITOR")
    if tree is not None:
        bpy.data.node_groups.remove(tree)
    tree = bpy.data.node_groups.new("BWRT_COMPOSITOR", "CompositorNodeTree")
    tree["bw_m7_roundtrip_marker"] = MARKER
    bpy.context.scene.compositing_node_group = tree
    bpy.context.scene.use_nodes = True

    source = tree.nodes.new("CompositorNodeRGB")
    source.name = "BWRT_SOURCE"
    source.label = "roundtrip-source"
    source.outputs[0].default_value = (0.11, 0.22, 0.33, 0.44)

    balance = tree.nodes.new("CompositorNodeColorBalance")
    balance.name = "BWRT_BALANCE"
    balance.label = "storage-sentinel"
    balance.input_whitepoint = (0.81, 0.93, 1.07)
    balance.output_whitepoint = (1.13, 0.97, 0.79)
    balance.inputs["Factor"].default_value = 0.625

    blur = tree.nodes.new("CompositorNodeBlur")
    blur.name = "BWRT_BLUR"
    blur.label = "linked-sink"
    blur.inputs["Size"].default_value = (7.0, 11.0)
    blur.inputs["Extend Bounds"].default_value = True
    blur.inputs["Separable"].default_value = False

    tree.links.new(source.outputs["Color"], balance.inputs["Image"])
    tree.links.new(balance.outputs["Image"], blur.inputs["Image"])

    screen = bpy.context.screen
    if screen is None or screen.name != "Layout":
        raise AssertionError("pinned factory startup did not open the Layout screen")
    areas = sorted(screen.areas, key=lambda area: (area.y, area.x, area.width, area.height))
    if len(areas) != 4:
        raise AssertionError(f"pinned Layout screen has {len(areas)} areas instead of four")

    active_specs = [spec for spec in ROLE_SPECS if spec["active"]]
    inactive_specs = [spec for spec in ROLE_SPECS if not spec["active"]]
    if [spec["target"] for spec in active_specs] != [spec["target"] for spec in inactive_specs]:
        raise AssertionError("active/inactive target contract is not paired")

    for area, spec in zip(areas, active_specs, strict=True):
        area.type = spec["target"]
        if area.spaces.active.type != spec["target"]:
            raise AssertionError(f"failed to instantiate active {spec['target']} SpaceLink")
        set_state(area.spaces.active, spec["state"])

    active_screen = screen.copy()
    active_screen.name = "BWRT_ACTIVE"
    active_screen.use_fake_user = True
    screen.name = "BWRT_INACTIVE"

    for spec in inactive_specs:
        area = role_area(screen, spec["target"], True)
        set_state(area.spaces.active, spec["state"])
        area.type = "VIEW_3D"
        if area.type != "VIEW_3D" or spec["target"] not in [item.type for item in area.spaces]:
            raise AssertionError(f"failed to retain inactive {spec['target']} SpaceLink")


def socket_state(socket: Any) -> dict[str, Any]:
    result = {
        "name": socket.name,
        "identifier": socket.identifier,
        "bl_idname": socket.bl_idname,
        "type": socket.type,
        "is_linked": bool(socket.is_linked),
    }
    if hasattr(socket, "default_value"):
        result["default_value"] = normalized(socket.default_value)
    return result


def compositor_state() -> dict[str, Any]:
    scene = bpy.context.scene
    tree = scene.compositing_node_group
    if tree is None:
        raise AssertionError("scene compositor node group is missing")
    nodes = []
    for node in sorted(tree.nodes, key=lambda item: item.name):
        item = {
            "name": node.name,
            "label": node.label,
            "bl_idname": node.bl_idname,
            "type": node.type,
            "inputs": [socket_state(socket) for socket in node.inputs],
            "outputs": [socket_state(socket) for socket in node.outputs],
        }
        if node.name == "BWRT_BALANCE":
            item["storage"] = {
                "input_whitepoint": normalized(node.input_whitepoint),
                "output_whitepoint": normalized(node.output_whitepoint),
            }
        nodes.append(item)
    links = sorted(
        (
            link.from_node.name,
            link.from_socket.identifier,
            link.to_node.name,
            link.to_socket.identifier,
        )
        for link in tree.links
    )
    return {
        "tree_name": tree.name,
        "tree_type": tree.bl_idname,
        "marker": tree.get("bw_m7_roundtrip_marker"),
        "nodes": nodes,
        "links": [list(link) for link in links],
    }


def role_area(screen: Any, target: str, active: bool) -> Any:
    matches = []
    for area in screen.areas:
        types = [space.type for space in area.spaces]
        if target in types and ((area.type == target) == active):
            matches.append(area)
    if len(matches) != 1:
        raise AssertionError(
            f"expected one {'active' if active else 'inactive'} {target} area in {screen.name}, "
            f"found {len(matches)}"
        )
    return matches[0]


def editor_state() -> list[dict[str, Any]]:
    result = []
    for spec in ROLE_SPECS:
        screen_name = "BWRT_ACTIVE" if spec["active"] else "BWRT_INACTIVE"
        screen = bpy.data.screens.get(screen_name)
        if screen is None:
            raise AssertionError(f"missing fixture screen {screen_name}")
        area = role_area(screen, spec["target"], spec["active"])
        initial_type = area.type
        initial_order = [space.type for space in area.spaces]
        if "EMPTY" in initial_order or initial_type == "EMPTY":
            raise AssertionError(f"{screen_name} contains SPACE_EMPTY")

        if not spec["active"]:
            area.type = spec["target"]
        space = area.spaces.active
        if space.type != spec["target"]:
            raise AssertionError(f"failed to reactivate {spec['target']} in {screen_name}")
        state = {name: normalized(getattr(space, name)) for name in spec["state"]}
        regions = [
            {"type": region.type, "alignment": region.alignment}
            for region in area.regions
        ]
        if not spec["active"]:
            area.type = initial_type
            if [item.type for item in area.spaces] != initial_order:
                raise AssertionError(f"reactivating {spec['target']} reordered {screen_name}")

        result.append(
            {
                "role": spec["role"],
                "screen": screen_name,
                "target": spec["target"],
                "active": spec["active"],
                "area_type": initial_type,
                "space_order": initial_order,
                "state": state,
                "regions": regions,
            }
        )
    return result


def snapshot() -> dict[str, Any]:
    build_hash = bpy.app.build_hash.decode() if isinstance(bpy.app.build_hash, bytes) else str(bpy.app.build_hash)
    return {
        "schema": 1,
        "pin": PIN,
        "runtime": {"version": list(bpy.app.version), "build_hash": build_hash},
        "scene_marker": bpy.context.scene.get("bw_m7_roundtrip_marker"),
        "compositor": compositor_state(),
        "editors": editor_state(),
    }


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def save(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
    if "FINISHED" not in result or not path.is_file() or path.stat().st_size == 0:
        raise AssertionError(f"failed to save fixture: {path} ({result})")


def open_file(path: Path) -> None:
    if not path.is_file():
        raise AssertionError(f"fixture source is missing: {path}")
    result = bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=True, use_scripts=False)
    if "FINISHED" not in result:
        raise AssertionError(f"failed to open fixture: {path} ({result})")


def main() -> None:
    args = parse_args()
    if args.mode == "author":
        author_fixture()
        before = snapshot()
        write_state(args.pre_state, before)
        save(args.output)
        open_file(args.output)
        after = snapshot()
        if before != after:
            raise AssertionError("native-authored fixture changed on its first save/reload")
        if args.post_state is not None:
            write_state(args.post_state, after)
        print("BW_M7_TYPE_FIXTURE_AUTHOR_OK", flush=True)
        return

    if args.source is None or args.post_state is None:
        raise AssertionError("roundtrip mode requires --source and --post-state")
    open_file(args.source)
    before = snapshot()
    write_state(args.pre_state, before)
    save(args.output)
    open_file(args.output)
    after = snapshot()
    write_state(args.post_state, after)
    if before != after:
        raise AssertionError("fixture state changed across load/save/reload")
    print("BW_M7_TYPE_FIXTURE_ROUNDTRIP_OK", flush=True)


if __name__ == "__main__":
    main()
