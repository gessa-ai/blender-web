#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify the R9 aggregate rollback of the eight size-only registration cuts."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]

CUT_PATCHES = (
    "0248-web-windowed-sculpt-paint-registration-cut.patch",
    "0249-web-windowed-grease-pencil-registration-cut.patch",
    "0250-web-windowed-compositor-registration-cut.patch",
    "0251-web-windowed-vse-registration-cut.patch",
    "0252-web-windowed-spreadsheet-registration-cut.patch",
    "0253-web-windowed-clip-registration-cut.patch",
    "0254-web-windowed-nla-registration-cut.patch",
    "0255-web-windowed-physics-registration-cut.patch",
)

CUT_VERIFIERS = (
    "sandbox/m8-sculpt-paint-cut/verify.py",
    "sandbox/m8-grease-pencil-cut/verify.py",
    "sandbox/m8-compositor-cut/verify.py",
    "sandbox/m8-vse-cut/verify.py",
    "sandbox/m8-spreadsheet-cut/verify.py",
    "sandbox/m8-clip-cut/verify.py",
    "sandbox/m8-nla-cut/verify.py",
    "sandbox/m8-physics-cut/verify.py",
)

CUT_FLAGS = (
    "WITH_BLENDER_WEB_SCULPT_PAINT",
    "WITH_BLENDER_WEB_GREASE_PENCIL",
    "WITH_BLENDER_WEB_COMPOSITOR",
    "WITH_BLENDER_WEB_VSE",
    "WITH_BLENDER_WEB_SPREADSHEET",
    "WITH_BLENDER_WEB_CLIP",
    "WITH_BLENDER_WEB_NLA",
    "WITH_BLENDER_WEB_PHYSICS",
)

DEFERRAL_IDS = (
    "feature-off-sculpt-paint-windowed",
    "feature-off-grease-pencil-editing-windowed",
    "feature-off-compositor-execution-windowed",
    "feature-off-vse-editing-windowed",
    "feature-off-spreadsheet-editor-windowed",
    "feature-off-clip-editor-windowed",
    "feature-off-nla-editor-windowed",
    "feature-off-physics-editing-windowed",
)

SPACETYPE_CALLS = (
    "ED_spacetype_nla();",
    "vse::ED_spacetype_sequencer();",
    "ED_spacetype_clip();",
    "spreadsheet::register_spacetype();",
    "ED_operatortypes_gpencil_legacy();",
    "ED_operatortypes_grease_pencil();",
    "sculpt_paint::operatortypes_sculpt();",
    "ED_operatortypes_sculpt_curves();",
    "ED_operatortypes_paint();",
    "ED_operatortypes_physics();",
    "ED_operatormacros_clip();",
    "vse::ED_operatormacros_sequencer();",
    "ED_operatormacros_paint();",
    "ED_operatormacros_grease_pencil();",
    "ED_operatormacros_nla();",
    "ED_keymap_gpencil_legacy(keyconf);",
    "ED_keymap_grease_pencil(keyconf);",
    "ED_keymap_physics(keyconf);",
    "ED_keymap_paint(keyconf);",
    "sculpt_paint::keymap_sculpt(keyconf);",
)

NODE_CALL = "register_compositor_nodes();"

AFFECTED_UPSTREAM_PATHS = {
    "source/blender/editors/space_api/CMakeLists.txt",
    "source/blender/editors/space_api/spacetypes.cc",
    "source/blender/nodes/CMakeLists.txt",
    "source/blender/nodes/intern/node_register.cc",
}

HISTORY_NOTES = (
    "notes/m8-sculpt-paint-registration-cut-20260824.md",
    "notes/m8-grease-pencil-registration-cut-20260824.md",
    "notes/m8-compositor-registration-cut-20260824.md",
    "notes/m8-vse-registration-cut-20260824.md",
    "notes/m8-spreadsheet-registration-cut-20260824.md",
    "notes/m8-clip-registration-cut-20260824.md",
    "notes/m8-nla-registration-cut-20260824.md",
    "notes/m8-physics-registration-cut-20260824.md",
)

HISTORY_MARKER = "Historical rejected experiment."


class VerifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Inputs:
    config: str
    series: str
    ledger: str
    space_cmake: str
    spacetypes: str
    nodes_cmake: str
    node_register: str
    canonical_patch: str
    canonical_receipt: str
    present_patches: frozenset[str]
    present_verifiers: frozenset[str]
    history_notes: tuple[str, ...]
    rollback_note: str


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def gather() -> Inputs:
    return Inputs(
        config=read("patches/blender_web.cmake"),
        series=read("patches/series"),
        ledger=read("ledger/deferred.json"),
        space_cmake=read("upstream/source/blender/editors/space_api/CMakeLists.txt"),
        spacetypes=read("upstream/source/blender/editors/space_api/spacetypes.cc"),
        nodes_cmake=read("upstream/source/blender/nodes/CMakeLists.txt"),
        node_register=read("upstream/source/blender/nodes/intern/node_register.cc"),
        canonical_patch=read("patches/PREVIEW_SNAPSHOT.patch"),
        canonical_receipt=read("patches/PREVIEW_SNAPSHOT.sha256"),
        present_patches=frozenset(
            name for name in CUT_PATCHES if (ROOT / "patches" / name).exists()
        ),
        present_verifiers=frozenset(
            relative for relative in CUT_VERIFIERS if (ROOT / relative).exists()
        ),
        history_notes=tuple(read(relative) for relative in HISTORY_NOTES),
        rollback_note=read("notes/m8-registration-fidelity-restore-20260824.md"),
    )


def patch_paths(patch: str) -> set[str]:
    paths: set[str] = set()
    for line in patch.splitlines():
        match = re.fullmatch(r"diff --git a/(.+) b/(.+)", line)
        if match is None:
            continue
        if match.group(1) != match.group(2):
            raise VerifyError(f"canonical patch rename is outside this verifier: {line}")
        paths.add(match.group(1))
    return paths


def require_contiguous(text: str, calls: tuple[str, ...], label: str) -> None:
    normalized = tuple(line.strip() for line in text.splitlines())
    width = len(calls)
    if not any(normalized[index : index + width] == calls for index in range(len(normalized))):
        raise VerifyError(f"restored {label} registration sequence is not exact and contiguous")


def conditional_depths(text: str) -> dict[int, int]:
    depths: dict[int, int] = {}
    depth = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if re.match(r"#\s*(if|ifdef|ifndef)\b", stripped):
            depth += 1
        depths[line_number] = depth
        if re.match(r"#\s*endif\b", stripped):
            depth -= 1
            if depth < 0:
                raise VerifyError("unbalanced preprocessor structure")
    if depth != 0:
        raise VerifyError("unbalanced preprocessor structure")
    return depths


def require_unconditional_calls(text: str, calls: tuple[str, ...], label: str) -> None:
    lines = text.splitlines()
    depths = conditional_depths(text)
    for call in calls:
        matches = [index for index, line in enumerate(lines, start=1) if line.strip() == call]
        if len(matches) != 1:
            raise VerifyError(f"{label} call {call!r} occurs {len(matches)} times")
        if depths[matches[0]] != 0:
            raise VerifyError(f"{label} call {call!r} remains conditionally registered")


def validate(inputs: Inputs) -> None:
    if inputs.present_patches:
        raise VerifyError(f"retired cut patches remain present: {sorted(inputs.present_patches)}")
    if inputs.present_verifiers:
        raise VerifyError(
            f"non-composable per-cut verifiers remain present: {sorted(inputs.present_verifiers)}"
        )

    source_bundle = "\n".join(
        (
            inputs.config,
            inputs.space_cmake,
            inputs.spacetypes,
            inputs.nodes_cmake,
            inputs.node_register,
            inputs.canonical_patch,
        )
    )
    for flag in CUT_FLAGS:
        if flag in source_bundle:
            raise VerifyError(f"retired windowed feature flag remains live: {flag}")
    for patch_name in CUT_PATCHES:
        if patch_name in inputs.series:
            raise VerifyError(f"retired cut remains in active series: {patch_name}")

    try:
        deferred = json.loads(inputs.ledger)
    except json.JSONDecodeError as error:
        raise VerifyError(f"deferral registry is invalid JSON: {error}") from error
    rows = deferred.get("deferred")
    if not isinstance(rows, list):
        raise VerifyError("deferral registry lacks its deferred list")
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    for deferral_id in DEFERRAL_IDS:
        if deferral_id in ids:
            raise VerifyError(f"size-only feature deferral remains active: {deferral_id}")
    if len(ids) != len(set(ids)):
        raise VerifyError("deferral registry contains duplicate IDs")

    require_unconditional_calls(inputs.spacetypes, SPACETYPE_CALLS, "space_api")
    require_unconditional_calls(inputs.node_register, (NODE_CALL,), "node")
    require_contiguous(
        inputs.spacetypes,
        (
            "ED_spacetype_action();",
            "ED_spacetype_nla();",
            "ED_spacetype_script();",
            "ED_spacetype_text();",
            "vse::ED_spacetype_sequencer();",
            "ED_spacetype_console();",
            "ED_spacetype_userpref();",
            "ED_spacetype_clip();",
            "ED_spacetype_statusbar();",
            "ED_spacetype_topbar();",
            "spreadsheet::register_spacetype();",
        ),
        "editor-space",
    )
    require_contiguous(
        inputs.spacetypes,
        (
            "asset::operatortypes_asset();",
            "ED_operatortypes_gpencil_legacy();",
            "ED_operatortypes_grease_pencil();",
            "object::operatortypes_object();",
            "ED_operatortypes_lattice();",
            "ED_operatortypes_mesh();",
            "geometry::operatortypes_geometry();",
            "sculpt_paint::operatortypes_sculpt();",
            "ED_operatortypes_sculpt_curves();",
            "ED_operatortypes_uvedit();",
            "ED_operatortypes_paint();",
            "ED_operatortypes_physics();",
        ),
        "operator",
    )
    require_contiguous(
        inputs.spacetypes,
        (
            "ED_operatormacros_action();",
            "ED_operatormacros_clip();",
            "ED_operatormacros_curve();",
            "curves::operatormacros_curves();",
            "pointcloud::operatormacros_pointcloud();",
            "ED_operatormacros_mask();",
            "vse::ED_operatormacros_sequencer();",
            "ED_operatormacros_paint();",
            "ED_operatormacros_grease_pencil();",
            "ED_operatormacros_nla();",
        ),
        "macro",
    )
    require_contiguous(
        inputs.spacetypes,
        (
            "ED_keymap_animchannels(keyconf);",
            "ED_keymap_gpencil_legacy(keyconf);",
            "ED_keymap_grease_pencil(keyconf);",
            "object::keymap_object(keyconf);",
            "ED_keymap_lattice(keyconf);",
            "ED_keymap_mesh(keyconf);",
            "ED_keymap_uvedit(keyconf);",
            "ED_keymap_curve(keyconf);",
            "curves::keymap_curves(keyconf);",
            "pointcloud::keymap_pointcloud(keyconf);",
            "ED_keymap_armature(keyconf);",
            "ED_keymap_physics(keyconf);",
            "ED_keymap_metaball(keyconf);",
            "ED_keymap_paint(keyconf);",
            "ED_keymap_mask(keyconf);",
            "ED_keymap_marker(keyconf);",
            "sculpt_paint::keymap_sculpt(keyconf);",
        ),
        "keymap",
    )
    require_contiguous(
        inputs.node_register,
        (
            "register_node_type_group_output();",
            "",
            "register_compositor_nodes();",
            "register_shader_nodes();",
        ),
        "compositor-node",
    )

    expected_space_tail = 'blender_add_lib(bf_editor_space_api "${SRC}" "${INC}" "${INC_SYS}" "${LIB}")'
    if not inputs.space_cmake.rstrip().endswith(expected_space_tail):
        raise VerifyError("space_api CMake retains a post-library feature-cut tail")

    canonical_paths = patch_paths(inputs.canonical_patch)
    overlap = AFFECTED_UPSTREAM_PATHS & canonical_paths
    if overlap:
        raise VerifyError(f"canonical postimage still changes cut-only source paths: {sorted(overlap)}")

    receipt_fields = inputs.canonical_receipt.split()
    if len(receipt_fields) != 2 or receipt_fields[1] != "PREVIEW_SNAPSHOT.patch":
        raise VerifyError("canonical patch SHA-256 receipt is malformed")
    actual_digest = hashlib.sha256(inputs.canonical_patch.encode("utf-8")).hexdigest()
    if receipt_fields[0] != actual_digest:
        raise VerifyError("canonical patch SHA-256 receipt does not bind the current patch")

    for note in inputs.history_notes:
        if HISTORY_MARKER not in note:
            raise VerifyError("a cut note is not marked as rejected historical evidence")
    required_rollback_claims = (
        "1,254,866",
        "fidelity-first",
        "no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)",
    )
    normalized_rollback_note = " ".join(inputs.rollback_note.split())
    for claim in required_rollback_claims:
        if claim not in normalized_rollback_note:
            raise VerifyError(f"rollback note omits required claim: {claim}")


def expect_rejection(label: str, candidate: Inputs) -> str:
    try:
        validate(candidate)
    except VerifyError:
        return label
    raise VerifyError(f"mutation was incorrectly accepted: {label}")


def self_test(inputs: Inputs) -> tuple[str, ...]:
    mutated_ledger = json.loads(inputs.ledger)
    mutated_ledger["deferred"].append({"id": DEFERRAL_IDS[0]})
    first_note = inputs.history_notes[0].replace(HISTORY_MARKER, "active experiment", 1)
    return (
        expect_rejection(
            "missing-call",
            replace(inputs, spacetypes=inputs.spacetypes.replace(SPACETYPE_CALLS[0], "", 1)),
        ),
        expect_rejection(
            "conditional-call",
            replace(
                inputs,
                spacetypes=inputs.spacetypes.replace(
                    f"  {SPACETYPE_CALLS[0]}",
                    f"#if defined(SOME_OTHER_FEATURE)\n  {SPACETYPE_CALLS[0]}\n#endif",
                    1,
                ),
            ),
        ),
        expect_rejection("feature-flag", replace(inputs, config=inputs.config + CUT_FLAGS[0])),
        expect_rejection("active-patch", replace(inputs, series=inputs.series + CUT_PATCHES[0])),
        expect_rejection(
            "active-deferral",
            replace(inputs, ledger=json.dumps(mutated_ledger, sort_keys=True)),
        ),
        expect_rejection(
            "present-patch", replace(inputs, present_patches=frozenset({CUT_PATCHES[0]}))
        ),
        expect_rejection(
            "present-verifier",
            replace(inputs, present_verifiers=frozenset({CUT_VERIFIERS[0]})),
        ),
        expect_rejection(
            "unmarked-history",
            replace(inputs, history_notes=(first_note, *inputs.history_notes[1:])),
        ),
    )


def main() -> int:
    inputs = gather()
    validate(inputs)
    mutations = self_test(inputs)
    canonical_paths = patch_paths(inputs.canonical_patch)
    print(
        "AUDIT_R9_FIDELITY_RESTORE_PASS "
        f"calls={len(SPACETYPE_CALLS) + 1} retired_patches={len(CUT_PATCHES)} "
        f"retired_deferrals={len(DEFERRAL_IDS)} canonical_paths={len(canonical_paths)} "
        f"mutations={len(mutations)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerifyError) as error:
        print(f"AUDIT_R9_FIDELITY_RESTORE_FAIL {error}")
        raise SystemExit(1)
