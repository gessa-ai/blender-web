# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0

"""Fail-closed semantic and parity verifier for the M7 omitted-type fixture."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable


PIN = "fbe6228777e7"
MARKER = "m7-omitted-type-roundtrip-v1"

EXPECTED_ROLES = {
    "sequence_active": ("SEQUENCE_EDITOR", True),
    "sequence_inactive": ("SEQUENCE_EDITOR", False),
    "spreadsheet_active": ("SPREADSHEET", True),
    "spreadsheet_inactive": ("SPREADSHEET", False),
    "clip_active": ("CLIP_EDITOR", True),
    "clip_inactive": ("CLIP_EDITOR", False),
    "nla_active": ("NLA_EDITOR", True),
    "nla_inactive": ("NLA_EDITOR", False),
}

EXPECTED_SPACE_STATE = {
    "sequence_active": {
        "view_type": "PREVIEW", "display_mode": "WAVEFORM", "display_channel": 3,
        "preview_channels": "COLOR", "use_proxies": True,
        "show_overlays": False, "cursor_location": [13.25, 27.5],
    },
    "sequence_inactive": {
        "view_type": "SEQUENCER_PREVIEW", "display_mode": "RGB_PARADE", "display_channel": 7,
        "preview_channels": "COLOR_ALPHA", "use_proxies": False, "show_overlays": True,
        "cursor_location": [-9.5, 41.75],
    },
    "spreadsheet_active": {
        "is_pinned": True, "show_internal_attributes": True, "use_filter": True,
        "show_only_selected": True, "geometry_item_type": "DOMAIN",
        "geometry_component_type": "MESH", "attribute_domain": "CORNER",
        "object_eval_state": "ORIGINAL",
    },
    "spreadsheet_inactive": {
        "is_pinned": False, "show_internal_attributes": False, "use_filter": True,
        "show_only_selected": False, "geometry_item_type": "DOMAIN",
        "geometry_component_type": "CURVE", "attribute_domain": "POINT",
        "object_eval_state": "EVALUATED",
    },
    "clip_active": {
        "mode": "MASK", "view": "GRAPH", "show_marker_pattern": False,
        "show_marker_search": True, "lock_selection": True, "lock_time_cursor": True,
        "show_track_path": True, "path_length": 17, "show_names": True, "show_grid": False,
        "cursor_location": [0.3125, 0.6875], "pivot_point": "CURSOR",
    },
    "clip_inactive": {
        "mode": "TRACKING", "view": "DOPESHEET", "show_marker_pattern": True,
        "show_marker_search": False, "lock_selection": False, "lock_time_cursor": False,
        "show_track_path": False, "path_length": 31, "show_names": False, "show_grid": True,
        "cursor_location": [0.8125, 0.1875], "pivot_point": "INDIVIDUAL_ORIGINS",
    },
    "nla_active": {
        "show_seconds": True, "show_strip_curves": True, "show_local_markers": True,
        "show_markers": False, "use_realtime_update": False,
    },
    "nla_inactive": {
        "show_seconds": False, "show_strip_curves": False, "show_local_markers": False,
        "show_markers": True, "use_realtime_update": True,
    },
}

REQUIRED_REGIONS = {
    "SEQUENCE_EDITOR": {"HEADER", "PREVIEW", "WINDOW"},
    "SPREADSHEET": {"HEADER", "FOOTER", "WINDOW"},
    "CLIP_EDITOR": {"HEADER", "PREVIEW", "WINDOW"},
    "NLA_EDITOR": {"HEADER", "CHANNELS", "WINDOW"},
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def by_name(items: list[dict[str, Any]], key: str = "name") -> dict[str, dict[str, Any]]:
    result = {item[key]: item for item in items}
    require(len(result) == len(items), f"duplicate {key} values")
    return result


def validate_contract(state: dict[str, Any]) -> None:
    require(state.get("schema") == 1, "state schema drift")
    require(state.get("pin") == PIN, "fixture pin drift")
    runtime = state.get("runtime", {})
    require(runtime.get("version") == [5, 2, 0], "runtime is not Blender 5.2.0")
    require(runtime.get("build_hash") in {PIN, "Unknown"}, "runtime build hash is not pinned/unknown")
    require(state.get("scene_marker") == MARKER, "scene marker lost")

    compositor = state.get("compositor", {})
    require(compositor.get("tree_name") == "BWRT_COMPOSITOR", "compositor tree identity lost")
    require(compositor.get("tree_type") == "CompositorNodeTree", "compositor tree type lost")
    require(compositor.get("marker") == MARKER, "compositor marker lost")
    nodes = by_name(compositor.get("nodes", []))
    require(set(nodes) == {"BWRT_SOURCE", "BWRT_BALANCE", "BWRT_BLUR"}, "node set changed")
    expected_node_types = {
        "BWRT_SOURCE": "CompositorNodeRGB",
        "BWRT_BALANCE": "CompositorNodeColorBalance",
        "BWRT_BLUR": "CompositorNodeBlur",
    }
    for name, bl_idname in expected_node_types.items():
        node = nodes[name]
        require(node.get("bl_idname") == bl_idname, f"{name} became undefined or changed type")
        require("Undefined" not in str(node.get("type")), f"{name} has an undefined legacy type")

    require(
        nodes["BWRT_BALANCE"].get("storage")
        == {
            "input_whitepoint": [0.885642, 1.016848, 1.16992],
            "output_whitepoint": [1.140232, 0.978781, 0.797148],
        },
        "storage-bearing Color Balance state changed",
    )
    source_outputs = by_name(nodes["BWRT_SOURCE"].get("outputs", []), "identifier")
    balance_inputs = by_name(nodes["BWRT_BALANCE"].get("inputs", []), "identifier")
    balance_outputs = by_name(nodes["BWRT_BALANCE"].get("outputs", []), "identifier")
    blur_inputs = by_name(nodes["BWRT_BLUR"].get("inputs", []), "identifier")
    require(source_outputs.get("Color", {}).get("default_value") == [0.11, 0.22, 0.33, 0.44],
            "source socket payload changed")
    require(balance_inputs.get("Fac", {}).get("default_value") == 0.625,
            "Color Balance factor socket changed")
    require(blur_inputs.get("Size", {}).get("default_value") == [7.0, 11.0],
            "Blur size socket changed")
    require(balance_outputs.get("Image", {}).get("is_linked") is True,
            "Color Balance output link state changed")
    expected_links = [
        ["BWRT_BALANCE", "Image", "BWRT_BLUR", "Image"],
        ["BWRT_SOURCE", "Color", "BWRT_BALANCE", "Image"],
    ]
    require(compositor.get("links") == expected_links, "compositor links changed")

    editors = by_name(state.get("editors", []), "role")
    require(set(editors) == set(EXPECTED_ROLES), "editor role set changed")
    for role, (target, active) in EXPECTED_ROLES.items():
        editor = editors[role]
        require(editor.get("target") == target, f"{role} target changed")
        require(editor.get("active") is active, f"{role} active/inactive contract changed")
        require(editor.get("area_type") == (target if active else "VIEW_3D"),
                f"{role} active area became SPACE_EMPTY or changed type")
        order = editor.get("space_order", [])
        require("EMPTY" not in order, f"{role} contains SPACE_EMPTY")
        require(target in order, f"{role} lost its target SpaceLink")
        require((order[0] == target) is active, f"{role} target SpaceLink ordering changed")
        require(editor.get("state") == EXPECTED_SPACE_STATE[role], f"{role} specific state changed")
        region_types = {region.get("type") for region in editor.get("regions", [])}
        require(REQUIRED_REGIONS[target] <= region_types, f"{role} lost required regions")


def mutate_node_undefined(state: dict[str, Any]) -> None:
    by_name(state["compositor"]["nodes"])["BWRT_BALANCE"]["bl_idname"] = "NodeUndefined"


def mutate_storage_loss(state: dict[str, Any]) -> None:
    by_name(state["compositor"]["nodes"])["BWRT_BALANCE"]["storage"]["input_whitepoint"] = [1, 1, 1]


def mutate_socket_loss(state: dict[str, Any]) -> None:
    by_name(state["compositor"]["nodes"])["BWRT_BLUR"]["inputs"] = []


def mutate_link_loss(state: dict[str, Any]) -> None:
    state["compositor"]["links"].pop()


def mutate_space_empty(state: dict[str, Any]) -> None:
    editor = by_name(state["editors"], "role")["sequence_active"]
    editor["area_type"] = "EMPTY"
    editor["space_order"][0] = "EMPTY"


def mutate_inactive_loss(state: dict[str, Any]) -> None:
    editor = by_name(state["editors"], "role")["clip_inactive"]
    editor["space_order"].remove("CLIP_EDITOR")


def mutate_region_loss(state: dict[str, Any]) -> None:
    by_name(state["editors"], "role")["nla_inactive"]["regions"] = []


def mutate_specific_state_loss(state: dict[str, Any]) -> None:
    by_name(state["editors"], "role")["spreadsheet_active"]["state"]["attribute_domain"] = "POINT"


MUTATIONS: dict[str, Callable[[dict[str, Any]], None]] = {
    "node-undefined": mutate_node_undefined,
    "node-storage-loss": mutate_storage_loss,
    "node-socket-loss": mutate_socket_loss,
    "node-link-loss": mutate_link_loss,
    "space-empty": mutate_space_empty,
    "inactive-spacelink-loss": mutate_inactive_loss,
    "region-loss": mutate_region_loss,
    "type-specific-state-loss": mutate_specific_state_loss,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parity_payload(state: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(state)
    payload["runtime"].pop("build_hash", None)
    return payload


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--state", type=Path, action="append", required=True)
    parser.add_argument("--blend", type=Path, action="append", required=True)
    parser.add_argument("--javascript", type=Path, required=True)
    parser.add_argument("--wasm", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    validate_contract(expected)
    require(expected["runtime"]["build_hash"] == PIN, "native author is not the pinned oracle")
    expected_payload = parity_payload(expected)
    matched = []
    for path in args.state:
        state = json.loads(path.read_text(encoding="utf-8"))
        validate_contract(state)
        expected_hash = "Unknown" if path.name.startswith("wasm-") else PIN
        require(state["runtime"]["build_hash"] == expected_hash,
                f"unexpected runtime identity in {path.name}")
        require(parity_payload(state) == expected_payload,
                f"native/Wasm state parity mismatch: {path.name}")
        matched.append({
            "name": path.name,
            "build_hash": state["runtime"]["build_hash"],
            "sha256": sha256(path),
        })

    mutation_results = []
    for name, mutation in MUTATIONS.items():
        candidate = copy.deepcopy(expected)
        mutation(candidate)
        try:
            validate_contract(candidate)
        except AssertionError:
            mutation_results.append(name)
        else:
            raise AssertionError(f"mutation was incorrectly accepted: {name}")

    blends = []
    for path in args.blend:
        require(path.is_file() and path.stat().st_size > 0, f"missing blend artifact: {path}")
        blends.append({"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})

    receipt = {
        "schema": 1,
        "contract": "M7 omitted-type load/save/reload parity",
        "pin": PIN,
        "hardware_independent": True,
        "gpu_or_browser_receipt": False,
        "stock_native_reads_wasm32_output": False,
        "open_boundary": "M7-WASM32-WRITE-CROSS-ABI",
        "state_sha256": canonical_sha256(expected_payload),
        "state_matches": matched,
        "mutation_controls": mutation_results,
        "blend_artifacts": blends,
        "runtime": {
            "javascript_sha256": sha256(args.javascript),
            "wasm_sha256": sha256(args.wasm),
        },
    }
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "M7_TYPE_ROUNDTRIP_OK "
        f"states={len(matched)} mutations={len(mutation_results)} "
        f"state_sha256={receipt['state_sha256'][:12]} "
        f"wasm_sha256={receipt['runtime']['wasm_sha256'][:12]} cross_native=OPEN"
    )


if __name__ == "__main__":
    main()
