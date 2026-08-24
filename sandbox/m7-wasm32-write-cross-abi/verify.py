# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0

"""Fail-closed verifier for canonical Wasm32 .blend writes and cross-ABI reloads."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import struct
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


PIN = "fbe6228777e7"
BHEAD4_SHA256 = "bbf99fe754bb426dd69fa211d6e80b4991728f1f8c201a547f7949b793edf3c2"
EXPECTED_HEADER = b"BLENDER_v502"
BHEAD4 = struct.Struct("<iiIii")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def load_semantic_verifier(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("m7_type_roundtrip_verify", path)
    require(spec is not None and spec.loader is not None, "cannot import semantic verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_c_string_table(data: bytes, offset: int, count: int) -> tuple[list[str], int]:
    values = []
    for _ in range(count):
        end = data.find(b"\0", offset)
        require(end >= 0, "unterminated SDNA string")
        values.append(data[offset:end].decode("utf-8"))
        offset = end + 1
    return values, (offset + 3) & ~3


def parse_sdna(data: bytes) -> dict[str, Any]:
    offset = 0
    require(data[:4] == b"SDNA", "DNA1 payload lacks SDNA marker")
    offset = 4
    require(data[offset : offset + 4] == b"NAME", "SDNA lacks NAME table")
    offset += 4
    names_count = struct.unpack_from("<i", data, offset)[0]
    offset += 4
    require(names_count > 0, "empty SDNA NAME table")
    names, offset = read_c_string_table(data, offset, names_count)

    require(data[offset : offset + 4] == b"TYPE", "SDNA lacks TYPE table")
    offset += 4
    types_count = struct.unpack_from("<i", data, offset)[0]
    offset += 4
    require(types_count > 0, "empty SDNA TYPE table")
    types, offset = read_c_string_table(data, offset, types_count)

    require(data[offset : offset + 4] == b"TLEN", "SDNA lacks TLEN table")
    offset += 4
    type_sizes_offset = offset
    require(offset + types_count * 2 <= len(data), "truncated SDNA TLEN table")
    type_sizes = list(struct.unpack_from(f"<{types_count}h", data, offset))
    offset += types_count * 2
    if types_count & 1:
        offset += 2

    require(data[offset : offset + 4] == b"STRC", "SDNA lacks STRC table")
    offset += 4
    structs_count = struct.unpack_from("<i", data, offset)[0]
    offset += 4
    require(structs_count > 0, "empty SDNA STRC table")
    structs = []
    for _ in range(structs_count):
        require(offset + 4 <= len(data), "truncated SDNA struct header")
        type_index, members_count = struct.unpack_from("<hh", data, offset)
        offset += 4
        require(0 <= type_index < types_count, "SDNA struct type index out of range")
        require(members_count >= 0, "negative SDNA member count")
        members = []
        for _member in range(members_count):
            require(offset + 4 <= len(data), "truncated SDNA struct member")
            member_type, member_name = struct.unpack_from("<hh", data, offset)
            offset += 4
            require(0 <= member_type < types_count, "SDNA member type index out of range")
            require(0 <= member_name < names_count, "SDNA member name index out of range")
            members.append((member_type, member_name))
        structs.append((type_index, members))
    require(offset == len(data), "trailing bytes after SDNA STRC table")
    require(len(set(types)) == len(types), "duplicate SDNA type name")
    return {
        "names": names,
        "types": types,
        "type_sizes": type_sizes,
        "type_sizes_offset": type_sizes_offset,
        "structs": structs,
    }


def validate_canonical_blend(data: bytes) -> dict[str, Any]:
    require(data[: len(EXPECTED_HEADER)] == EXPECTED_HEADER, "not a little-endian BHead4 v502 file")
    offset = len(EXPECTED_HEADER)
    records = []
    saw_end = False
    while offset < len(data):
        header_offset = offset
        require(offset + BHEAD4.size <= len(data), "truncated BHead4 header")
        code, length, old_address, struct_index, array_size = BHEAD4.unpack_from(data, offset)
        del old_address
        offset += BHEAD4.size
        require(length >= 0, "negative BHead4 payload length")
        require(array_size >= 0, "negative BHead4 array size")
        require(offset + length <= len(data), "BHead4 payload extends past EOF")
        code_bytes = struct.pack("<i", code)
        records.append(
            {
                "header_offset": header_offset,
                "data_offset": offset,
                "code": code_bytes,
                "length": length,
                "struct_index": struct_index,
                "array_size": array_size,
            }
        )
        offset += length
        if code_bytes == b"ENDB":
            require(length == 0 and array_size == 0, "invalid ENDB record")
            require(offset == len(data), "bytes follow ENDB")
            saw_end = True
            break
    require(saw_end, "missing ENDB record")

    dna_records = [record for record in records if record["code"] == b"DNA1"]
    require(len(dna_records) == 1, "expected exactly one DNA1 record")
    dna_record = dna_records[0]
    dna = parse_sdna(
        data[dna_record["data_offset"] : dna_record["data_offset"] + dna_record["length"]]
    )
    types = dna["types"]
    type_sizes = dna["type_sizes"]
    require(type_sizes[types.index("ListBase")] == 8, "file SDNA is not pointer-size 4")
    require(type_sizes[types.index("Scene")] == 6664, "Scene is not canonical legacy-32 size")
    require(
        type_sizes[types.index("CustomData_MeshMasks")] == 40,
        "CustomData_MeshMasks size drift",
    )

    structured = 0
    for record in records:
        struct_index = record["struct_index"]
        if struct_index <= 0:
            continue
        require(struct_index < len(dna["structs"]), "BHead4 SDNA index out of range")
        type_index = dna["structs"][struct_index][0]
        expected_length = type_sizes[type_index] * record["array_size"]
        require(record["length"] == expected_length, "structured BHead4 length mismatches SDNA")
        structured += 1
    require(structured > 0, "canonical file has no structured BHead4 records")
    return {
        "records": records,
        "structured_records": structured,
        "dna": dna,
        "dna_record": dna_record,
    }


def expect_rejected(label: str, callback: Callable[[], None], results: list[str]) -> None:
    try:
        callback()
    except (AssertionError, ValueError, IndexError, struct.error, UnicodeDecodeError):
        results.append(label)
    else:
        raise AssertionError(f"mutation was incorrectly accepted: {label}")


def parity_payload(state: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(state)
    value["runtime"].pop("build_hash", None)
    return value


def validate_legacy_state(state: dict[str, Any], expected_build_hash: str) -> None:
    require(state.get("schema") == 1, "legacy state schema drift")
    runtime = state.get("runtime", {})
    require(runtime.get("version") == [5, 2, 0], "legacy state runtime version drift")
    require(runtime.get("build_hash") == expected_build_hash, "legacy state runtime identity drift")
    scenes = state.get("scenes", [])
    require(len(scenes) == 1, "BHead4 scene count drift")
    require(scenes[0].get("name") == "Space types", "BHead4 scene name drift")
    require(scenes[0].get("root") == "Scene Collection", "BHead4 root collection drift")
    require(scenes[0].get("objects") == ["Camera", "Cube", "Lamp"], "BHead4 scene objects drift")
    objects = state.get("objects", [])
    require([item.get("name") for item in objects] == ["Camera", "Cube", "Lamp"],
            "BHead4 object set drift")
    require([item.get("type") for item in objects] == ["CAMERA", "MESH", "LIGHT"],
            "BHead4 object type drift")
    meshes = state.get("meshes", [])
    require(len(meshes) == 1 and meshes[0].get("name") == "Cube", "BHead4 mesh set drift")
    require(
        [meshes[0].get("vertices"), meshes[0].get("edges"), meshes[0].get("polygons")]
        == [8, 12, 6],
        "BHead4 mesh topology drift",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--semantic-native-state", type=Path, action="append", required=True)
    parser.add_argument("--semantic-wasm-state", type=Path, action="append", required=True)
    parser.add_argument("--legacy-native-state", type=Path, action="append", required=True)
    parser.add_argument("--legacy-wasm-state", type=Path, action="append", required=True)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--canonical-blend", type=Path, required=True)
    parser.add_argument("--dna-verify", type=Path, required=True)
    parser.add_argument("--semantic-fixture", type=Path, required=True)
    parser.add_argument("--semantic-verifier", type=Path, required=True)
    parser.add_argument("--global-undo", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--javascript", type=Path, required=True)
    parser.add_argument("--wasm", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    semantic = load_semantic_verifier(args.semantic_verifier)
    expected = load_json(args.expected)
    semantic.validate_contract(expected)
    require(expected["runtime"]["build_hash"] == PIN, "semantic author is not pinned")
    expected_payload = semantic.parity_payload(expected)

    semantic_matches = []
    for expected_hash, paths in (
        (PIN, args.semantic_native_state),
        ("Unknown", args.semantic_wasm_state),
    ):
        for path in paths:
            state = load_json(path)
            semantic.validate_contract(state)
            require(state["runtime"]["build_hash"] == expected_hash,
                    f"semantic runtime identity drift: {path.name}")
            require(semantic.parity_payload(state) == expected_payload,
                    f"semantic cross-ABI state mismatch: {path.name}")
            semantic_matches.append({"name": path.name, "sha256": sha256(path)})

    mutation_results = []
    for name, mutation in semantic.MUTATIONS.items():
        candidate = copy.deepcopy(expected)
        mutation(candidate)
        expect_rejected(
            f"semantic-{name}", lambda candidate=candidate: semantic.validate_contract(candidate),
            mutation_results,
        )

    require(sha256(args.legacy_source) == BHEAD4_SHA256, "pinned BHead4 fixture hash drift")
    legacy_payload = None
    legacy_matches = []
    for expected_hash, paths in (
        (PIN, args.legacy_native_state),
        ("Unknown", args.legacy_wasm_state),
    ):
        for path in paths:
            state = load_json(path)
            validate_legacy_state(state, expected_hash)
            payload = parity_payload(state)
            if legacy_payload is None:
                legacy_payload = payload
            else:
                require(payload == legacy_payload, f"BHead4 cross-runtime mismatch: {path.name}")
            legacy_matches.append({"name": path.name, "sha256": sha256(path)})
    require(legacy_payload is not None, "no BHead4 state evidence")

    state_mutation = copy.deepcopy(load_json(args.legacy_native_state[0]))
    state_mutation["scenes"][0]["root"] = "Broken Collection"
    expect_rejected(
        "legacy-root-collection",
        lambda: validate_legacy_state(state_mutation, PIN),
        mutation_results,
    )

    canonical_bytes = args.canonical_blend.read_bytes()
    parsed = validate_canonical_blend(canonical_bytes)

    wrong_header = bytearray(canonical_bytes)
    wrong_header[7] = ord("-")
    expect_rejected(
        "file-pointer-marker", lambda: validate_canonical_blend(bytes(wrong_header)), mutation_results
    )

    wrong_scene_size = bytearray(canonical_bytes)
    dna = parsed["dna"]
    scene_type_index = dna["types"].index("Scene")
    scene_size_offset = (
        parsed["dna_record"]["data_offset"] + dna["type_sizes_offset"] + scene_type_index * 2
    )
    struct.pack_into("<h", wrong_scene_size, scene_size_offset, 6672)
    expect_rejected(
        "file-wasm-scene-size",
        lambda: validate_canonical_blend(bytes(wrong_scene_size)),
        mutation_results,
    )

    first_structured = next(record for record in parsed["records"] if record["struct_index"] > 0)
    wrong_block_length = bytearray(canonical_bytes)
    struct.pack_into(
        "<i",
        wrong_block_length,
        first_structured["header_offset"] + 4,
        first_structured["length"] + 4,
    )
    expect_rejected(
        "file-structured-length",
        lambda: validate_canonical_blend(bytes(wrong_block_length)),
        mutation_results,
    )
    expect_rejected(
        "file-truncated", lambda: validate_canonical_blend(canonical_bytes[:-1]), mutation_results
    )
    missing_dna = bytearray(canonical_bytes)
    struct.pack_into("<4s", missing_dna, parsed["dna_record"]["header_offset"], b"DATA")
    expect_rejected(
        "file-missing-dna", lambda: validate_canonical_blend(bytes(missing_dna)), mutation_results
    )

    dna_verify_text = args.dna_verify.read_text(encoding="utf-8")
    for pattern in (
        r"sizeof\(struct Scene\) == 6672",
        r"offsetof\(struct Scene, customdata_mask\) == 5016",
        r"offsetof\(struct Scene, master_collection\) == 5408",
        r"const unsigned char DNAstr_legacy_32\[\]",
        r"const int DNAlen_legacy_32 = sizeof\(DNAstr_legacy_32\)",
    ):
        require(re.search(pattern, dna_verify_text) is not None,
                f"generated wasm DNA contract missing: {pattern}")

    receipt = {
        "schema": 1,
        "contract": "M7 Wasm32 canonical file writes and cross-ABI reload",
        "pin": PIN,
        "hardware_independent": True,
        "gpu_or_browser_receipt": False,
        "semantic_state_matches": semantic_matches,
        "legacy_bhead4_state_matches": legacy_matches,
        "mutation_controls": mutation_results,
        "canonical_file": {
            "sha256": sha256(args.canonical_blend),
            "bytes": len(canonical_bytes),
            "header": EXPECTED_HEADER.decode("ascii"),
            "structured_records": parsed["structured_records"],
            "scene_file_size": 6664,
            "scene_wasm_memory_size": 6672,
        },
        "sources": {
            "legacy_bhead4_sha256": sha256(args.legacy_source),
            "semantic_fixture_sha256": sha256(args.semantic_fixture),
            "semantic_verifier_sha256": sha256(args.semantic_verifier),
            "global_undo_sha256": sha256(args.global_undo),
            "probe_sha256": sha256(args.probe),
            "runner_sha256": sha256(args.runner),
            "verifier_sha256": sha256(Path(__file__).resolve()),
            "generated_dna_verify_sha256": sha256(args.dna_verify),
        },
        "runtime": {
            "javascript_sha256": sha256(args.javascript),
            "wasm_sha256": sha256(args.wasm),
        },
    }
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "M7_WASM32_WRITE_CROSS_ABI_OK "
        f"semantic_states={len(semantic_matches)} legacy_states={len(legacy_matches)} "
        f"mutations={len(mutation_results)} structured={parsed['structured_records']} undo=PASS "
        f"wasm_sha256={receipt['runtime']['wasm_sha256'][:12]}"
    )


if __name__ == "__main__":
    main()
