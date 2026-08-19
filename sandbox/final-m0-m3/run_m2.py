#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute the exact 75-suite M2 native/Wasm matrix into volatile evidence."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUTPUT_ROOT = HERE / "evidence"
TIERB = ROOT / "sandbox/tierb-prep"
SUITES = TIERB / "suites.tsv"
SKIP = {
    "script_pyapi_doc_gen", "script_load_addons", "script_load_modules",
    "script_disk_file_hash_service_test", "physics_ocean", "script_bundled_modules",
}
DEFERRALS = {
    "script_pyapi_mathutils": {"float32-ulp-mathutils"},
    "script_pyapi_bmesh": {"float32-ulp-mathutils"},
    "bl_constraints": {"float32-ulp-mathutils"},
    "bl_node_structure_type_inference": {"wasm32-64bit-blend-collision"},
    "bl_voxel_remesh": {"feature-off-openvdb"},
    "bl_voxel_remesh_compare": {"feature-off-openvdb"},
    "imbuf_py_api": {"feature-off-avif"},
}
DETECTOR_ACTIVE_ID = "wasm32-64bit-blend-collision"
DETECTOR_ACTIVE_SUITE = "bl_node_structure_type_inference"
DETECTOR_ACTIVE_STATUS = "detector-active"
DETECTOR_ACTIVE_MARKER = (
    "Cannot open this 64-bit .blend on 32-bit WebAssembly: block address 0xADDR "
    "collides with another block after truncation to 32 bits, so its data pointers "
    "cannot be resolved without corruption. This is a known wasm32 limitation "
    "(see ADR-004, wasm32-pointer-collision); a wasm64 build reads this file correctly."
)
_DETECTOR_RAW_HEAD, _DETECTOR_RAW_TAIL = DETECTOR_ACTIVE_MARKER.split("0xADDR")
DETECTOR_ACTIVE_RAW_RE = re.compile(
    re.escape(_DETECTOR_RAW_HEAD.encode()) + rb"0x[0-9A-Fa-f]+" +
    re.escape(_DETECTOR_RAW_TAIL.encode())
)
LABEL_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")
CANONICAL_NATIVE_ORACLE = ROOT / "oracle/bpy.sh"
CANONICAL_NODE = ROOT / "tools/emsdk/node/22.16.0_64bit/bin/node"
CANONICAL_RUNTIME_JS = ROOT / "build-wasm-m1-parity/bin/blender.js"
CANONICAL_NODE_VERSION = "v22.16.0"
ALLOCATOR_LINE = b"Switching to fully guarded memory allocator.\n"
WASM_BANNER_LINE = b"Blender 5.2.0 LTS\n"
NATIVE_BANNER_RE = re.compile(
    rb"Blender 5\.2\.0 LTS \(hash fbe6228777e7 built "
    rb"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\)\n"
)
WASM_LOCALE_RE = re.compile(
    rb"[0-9]{2}:[0-9]{2}\.[0-9]{3}  translation      \| WARNING "
    rb"'locale' data path for translations not found\n"
)
CYCLES_ADDON_SOURCE = ROOT / "upstream/intern/cycles/blender/addon"
BASE_SCRIPTS_SOURCE = ROOT / "upstream/scripts"
LOCALE_LANGUAGES_SOURCE = ROOT / "upstream/locale/languages"
PASS_DELTA_NOTE = ROOT / "notes/m2-tierb-prep.md"
NO_DENOISER_SUITE = "bl_rna_accessors"
NO_DENOISER_NORMALIZED_LINE = (
    b"<LOG_TIME>  bpy.rna          | WARNING current value '4' matches no enum in "
    b"'CyclesRenderSettings', '', 'denoiser'\n"
)
SCRATCH_ROOT_SUITE = "blendfile_io"
SCRATCH_ROOT_TOKEN = b"<SUITE_SCRATCH>"
SCRATCH_ROOT_OCCURRENCES = 6
SCRATCH_ROOT_POLICIES = {
    SCRATCH_ROOT_SUITE: SCRATCH_ROOT_OCCURRENCES,
    "bl_animation_action": 1,
    "blendfile_liblink": 33,
}
DETERMINISTIC_PYTHON_ENV = {
    "PYTHONHASHSEED": "0",
    "PYTHONUNBUFFERED": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}
KEYMAP_ORDER_SUITE = "script_load_keymap"
KEYMAP_FIRST_HEADER = b"Keymaps that are in 'bl_keymap_utils.keymap_hierarchy' but not blender\n"
KEYMAP_SECOND_HEADER = b"Keymaps that are in blender but not in 'bl_keymap_utils.keymap_hierarchy'\n"
KEYMAP_TAIL = [b"Comparing keymap space/region types...\n", b"done!\n", b"\n", b"Blender quit\n"]
PHYSICS_ORDER = {
    "physics_cloth": ("cloth_test.blend", (("ClothSimple", 15), ("ClothSpring", 10))),
    "physics_softbody": ("softbody_test.blend", (("SoftBodySimple", 45),)),
    "physics_dynamic_paint": (
        "dynamic_paint_test.blend", (("DynamicPaintSimple", 15),)
    ),
}
PASS_DELTA_DEFERRALS = {
    "bl_rna_paths": "os-shell-affordances",
    "bl_animation_action": "wasm32-animation-action-objectdata",
    "blendfile_library_overrides": "wasm32-library-override-idname-allocation",
}
PASS_DELTA_MARKERS = {
    "bl_rna_paths": "normalized-delta:v1:rna-paths:macos-menu-6_vs_wasm-sandbox-menu-8",
    "bl_animation_action": "normalized-delta:v1:animation-action:wasm-missing-objectdata-warning-pair",
    "blendfile_library_overrides": "normalized-delta:v3:library-overrides:six-idname-bijection-phase",
}
PASS_DELTA_LEDGER = {
    "os-shell-affordances": {
        "status": "deferred-by-goal", "milestone": "GOAL", "evidence": "GOAL.md:19",
    },
    "wasm32-animation-action-objectdata": {
        "status": "deferred", "milestone": "M2",
        "evidence": "notes/m2-tierb-prep.md §8",
    },
    "wasm32-library-override-idname-allocation": {
        "status": "deferred", "milestone": "M2",
        "evidence": "notes/m2-tierb-prep.md §8",
    },
}
RNA_MENU_CONTEXT = (
    b' at 0xADDR> from ["bpy.data.screens[\'Shading\']", '
    b'"bpy.data.screens[\'Shading\'].areas[4]", '
    b'"bpy.data.screens[\'Shading\'].areas[4].spaces[0]"]\n'
)
RNA_NATIVE_MENU = ("iCloud Drive", "Macintosh HD", "Desktop", "Documents", "Downloads", "Applications")
RNA_WASM_MENU = ("/", "Home", "Desktop", "Documents", "Downloads", "Videos", "Pictures", "Music")
ANIMATION_ASSIGNMENT_WARNING = (
    b"WARNING: ignoring assignment to target_id_type of Slot 'OBLegacy Slot' in "
    b"Action 'ACAction Without IDRoot'. A Slot's target_id_type can only be changed "
    b"when currently 'UNSPECIFIED'.\n"
)
ANIMATION_FCURVE_ERROR = (
    b"ERROR: F-Curve (datapath: 'location') doesn't belong to the same channel bag "
    b"as channel group 'group1'\n"
)
ANIMATION_REMAP_READ = (
    b'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'animation/remap_action.blend"\n'
)
ANIMATION_SECOND_REMAP_READ = b"." + ANIMATION_REMAP_READ
ANIMATION_SAVED = b'.Info: Saved as "liboverride-action-slot.blend"\n'
ANIMATION_OBJECTDATA_WARNING = (
    b"<LOG_TIME>  blend            | WARNING 1 local ObjectData are reported to be "
    b"missing, this should never happen\n"
)
ANIMATION_TEMP_READ = (
    b'<LOG_TIME>  blend            | Read blend: "<SUITE_SCRATCH>/'
    b'bl_animation_action/liboverride-action-slot.blend"\n'
)
ANIMATION_LAYERED_READ = (
    b'.<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'animation/layered_action_versioning_42.blend"\n'
)
ANIMATION_RELATIVE_LIBRARY = (
    b"//../../../../../../../../../upstream/tests/files/animation/"
    b"liboverride-action-slot-libfile.blend"
)
ANIMATION_INFO_LIBRARY = (
    b"Info: Read library: '<REPO>/upstream/tests/files/animation/"
    b"liboverride-action-slot-libfile.blend', '" + ANIMATION_RELATIVE_LIBRARY
    + b"', parent '<direct>'\n"
)
ANIMATION_MISSING_DATA = (
    b"Info: Cannot find object data of Library Suzanne lib "
    + ANIMATION_RELATIVE_LIBRARY + b"\n"
)


def library_override_line(collection: str, reference: str, local: str) -> bytes:
    return (
        f'<bpy_struct, Collection("{collection}") at 0xADDR> '.encode()
        + b"{'IDPOINTER_ITEM_USE_ID', 'IDPOINTER_MATCH_REFERENCE'} "
        + f'{reference} <bpy_struct, Object("{reference}") at 0xADDR> '.encode()
        + f'{local} <bpy_struct, Object("{local}") at 0xADDR>\n'.encode()
    )


LIBRARY_OVERRIDE_PHASE_BEFORE = (
    b"Info: Read library: '<TMP>', '<TMP>', parent '<direct>'\n"
)
LIBRARY_OVERRIDE_PHASE_AFTER = (
    b'<LOG_TIME>  blend            | Read blend: "<TMP>"\n'
)
LIBRARY_OVERRIDE_CONTROLLER = library_override_line(
    "LibController2", "LibController2", "LibController2"
)
LIBRARY_OVERRIDE_CONTROLLER_001 = library_override_line(
    "LibController2.001", "LibController2", "LibController2.001"
)
LIBRARY_OVERRIDE_CONTROLLER_002 = library_override_line(
    "LibController2.002", "LibController2", "LibController2.002"
)
LIBRARY_OVERRIDE_NATIVE_PHASE = [
    LIBRARY_OVERRIDE_CONTROLLER,
    library_override_line("LibCube", "LibCube.002", "LibCube.002"),
    library_override_line("LibCube", "LibCube.001", "LibCube.001"),
    LIBRARY_OVERRIDE_CONTROLLER_001,
    library_override_line("LibCube.001", "LibCube.002", "LibCube.004"),
    library_override_line("LibCube.001", "LibCube.001", "LibCube.003"),
    LIBRARY_OVERRIDE_CONTROLLER_002,
    library_override_line("LibCube.002", "LibCube.002", "LibCube.007"),
    library_override_line("LibCube.002", "LibCube.001", "LibCube.006"),
]
LIBRARY_OVERRIDE_WASM_PHASE = [
    LIBRARY_OVERRIDE_CONTROLLER,
    library_override_line("LibCube", "LibCube.002", "LibCube.007"),
    library_override_line("LibCube", "LibCube.001", "LibCube.006"),
    LIBRARY_OVERRIDE_CONTROLLER_001,
    library_override_line("LibCube.001", "LibCube.002", "LibCube.002"),
    library_override_line("LibCube.001", "LibCube.001", "LibCube.001"),
    LIBRARY_OVERRIDE_CONTROLLER_002,
    library_override_line("LibCube.002", "LibCube.002", "LibCube.004"),
    library_override_line("LibCube.002", "LibCube.001", "LibCube.003"),
]
LIBRARY_OVERRIDE_RECORD_RE = re.compile(
    rb'^<bpy_struct, Collection\("(?P<collection>LibCube(?:\.00[12])?)"\) at 0xADDR> '
    rb"\{'IDPOINTER_ITEM_USE_ID', 'IDPOINTER_MATCH_REFERENCE'\} "
    rb'(?P<reference>LibCube\.(?:001|002)) <bpy_struct, Object\("(?P=reference)"\) at 0xADDR> '
    rb'(?P<local>LibCube\.(?:001|002|003|004|006|007)) '
    rb'<bpy_struct, Object\("(?P=local)"\) at 0xADDR>\n$'
)
LIBRARY_OVERRIDE_PHASE_BEFORE_INDEX = 23
LIBRARY_OVERRIDE_LOCAL_PAIRS = {
    (b"LibCube.002", b"LibCube.001"),
    (b"LibCube.004", b"LibCube.003"),
    (b"LibCube.007", b"LibCube.006"),
}
LIBRARY_OVERRIDE_SET_CANONICAL = (
    b"{'IDPOINTER_ITEM_USE_ID', 'IDPOINTER_MATCH_REFERENCE'}"
)
LIBRARY_OVERRIDE_SET_REVERSED = (
    b"{'IDPOINTER_MATCH_REFERENCE', 'IDPOINTER_ITEM_USE_ID'}"
)
LIBRARY_OVERRIDE_SET_OCCURRENCES = 66


class RunError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise RunError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ref(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError:
        fail(f"reference escapes repository: {resolved}")
    if path.is_symlink() or not resolved.is_file():
        fail(f"reference is not a non-symlink file: {relative}")
    return {"path": relative.as_posix(), "bytes": resolved.stat().st_size, "sha256": sha256(resolved)}


def canonical_file(raw: Path, expected: Path, where: str) -> Path:
    lexical = raw if raw.is_absolute() else ROOT / raw
    lexical = Path(os.path.normpath(os.fspath(lexical)))
    try:
        resolved = lexical.resolve(strict=True)
        canonical = expected.resolve(strict=True)
    except OSError as error:
        fail(f"{where}: missing canonical file: {error}")
    current = Path(expected.anchor)
    symlinked = False
    for part in expected.parts[1:]:
        current /= part
        symlinked = symlinked or current.is_symlink()
    if (lexical != expected or raw.is_symlink() or symlinked or resolved != canonical
            or not canonical.is_file()):
        fail(f"{where}: path is not the exact non-symlink canonical file")
    return canonical


def write_json(path: Path, value: Any) -> Path:
    if path.exists() or path.is_symlink():
        fail(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return path


def capture(argv: list[str], stdout: Path, stderr: Path, *, env: dict[str, str] | None,
            cwd: Path, timeout: int) -> int:
    for path in (stdout, stderr):
        if path.exists() or path.is_symlink():
            fail(f"refusing to overwrite raw evidence: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    with stdout.open("xb") as out, stderr.open("xb") as err:
        try:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=out, stderr=err,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            fail(f"suite timed out after {timeout}s: {argv}")
    return result.returncode


def capture_combined(argv: list[str], output: Path, *, env: dict[str, str] | None,
                     cwd: Path, timeout: int) -> int:
    if output.exists() or output.is_symlink():
        fail(f"refusing to overwrite raw evidence: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        try:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            fail(f"suite timed out after {timeout}s: {argv}")
    return result.returncode


def strip_platform_envelope(payload: bytes, *, wasm: bool) -> bytes:
    """Remove only the pinned launcher's structurally located metadata.

    Python/C stdout buffering may move the adjacent allocator/banner pair
    relative to test output. Requiring exactly one adjacent, version-pinned
    pair avoids a broad line filter that could erase test messages.
    """
    lines = payload.splitlines(keepends=True)
    if wasm:
        pair_indexes = [
            index for index in range(len(lines) - 1)
            if lines[index] == ALLOCATOR_LINE and lines[index + 1] == WASM_BANNER_LINE
        ]
        if len(pair_indexes) != 1:
            fail("Wasm log lacks one exact adjacent allocator/banner envelope")
        pair_index = pair_indexes[0]
        del lines[pair_index:pair_index + 2]
        locale_indexes = [
            index for index, line in enumerate(lines) if WASM_LOCALE_RE.fullmatch(line)
        ]
        if locale_indexes:
            if locale_indexes != [pair_index]:
                fail("Wasm locale startup warning is duplicated or outside its envelope")
            lines.pop(pair_index)
    else:
        pair_indexes = [
            index for index in range(len(lines) - 1)
            if lines[index] == ALLOCATOR_LINE
            and NATIVE_BANNER_RE.fullmatch(lines[index + 1]) is not None
        ]
        if len(pair_indexes) != 1:
            fail("native log lacks one exact adjacent allocator/banner envelope")
        pair_index = pair_indexes[0]
        del lines[pair_index:pair_index + 2]
    return b"".join(lines)


def canonicalize_keymap_inventory(payload: bytes) -> bytes:
    """Sort only the two exact set-derived inventories emitted by this suite."""
    lines = payload.splitlines(keepends=True)
    if not lines or lines[0] != KEYMAP_FIRST_HEADER:
        fail("script_load_keymap lacks its exact first inventory header")
    try:
        second = lines.index(KEYMAP_SECOND_HEADER, 1)
    except ValueError:
        fail("script_load_keymap lacks its exact second inventory header")
    first_items = lines[1:second]
    second_end = second + 1 + 28
    second_items = lines[second + 1:second_end]
    if (len(first_items) != 159 or len(set(first_items)) != 159
            or any(re.fullmatch(rb"\t[ -~]+\n", line) is None for line in first_items)):
        fail("script_load_keymap first inventory grammar/cardinality differs")
    if (len(second_items) != 28 or len(set(second_items)) != 28
            or any(re.fullmatch(
                rb"    \('[^'\n]+', '[A-Z0-9_]+', '[A-Z0-9_]+', \[\]\),\n", line
            ) is None for line in second_items)):
        fail("script_load_keymap second inventory grammar/cardinality differs")
    if lines[second_end:] != KEYMAP_TAIL:
        fail("script_load_keymap output outside its inventories differs")
    return b"".join([
        KEYMAP_FIRST_HEADER, *sorted(first_items), KEYMAP_SECOND_HEADER,
        *sorted(second_items), *KEYMAP_TAIL,
    ])


def canonicalize_physics_records(payload: bytes, suite: str) -> bytes:
    """Reassemble one exact physics result multiset into semantic phase order."""
    blend_file, tests = PHYSICS_ORDER[suite]
    canonical = [
        f'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/physics/{blend_file}"\n'.encode(),
        b"\n",
    ]
    for name, frames in tests:
        canonical.append(f"START {name} test.\n".encode())
        canonical.extend(
            f"bake: frame {frame} :: {frames}\n".encode()
            for frame in range(1, frames + 1)
        )
        canonical.extend([
            f"PASSED {name} test successfully.\n".encode(),
            b"Results:\n", b"Mesh Comparison : Same\n",
            b"Mesh Validation : Valid\n", b"\n", b"\n",
        ])
    canonical.append(b"Blender quit\n")
    lines = payload.splitlines(keepends=True)
    if Counter(lines) != Counter(canonical):
        fail(f"{suite} result/bake grammar or cardinality differs")
    return b"".join(canonical)


def canonicalize_library_override_sets(payload: bytes) -> bytes:
    """Canonicalize one exact uniformly ordered two-token set inventory."""
    canonical = payload.count(LIBRARY_OVERRIDE_SET_CANONICAL)
    reversed_count = payload.count(LIBRARY_OVERRIDE_SET_REVERSED)
    if (canonical, reversed_count) not in {
        (LIBRARY_OVERRIDE_SET_OCCURRENCES, 0),
        (0, LIBRARY_OVERRIDE_SET_OCCURRENCES),
    }:
        fail("blendfile_library_overrides ID-pointer set order/cardinality differs")
    return payload.replace(
        LIBRARY_OVERRIDE_SET_REVERSED, LIBRARY_OVERRIDE_SET_CANONICAL
    )


def canonicalize_suite_records(payload: bytes, suite: str | None) -> bytes:
    if suite == KEYMAP_ORDER_SUITE:
        return canonicalize_keymap_inventory(payload)
    if suite in PHYSICS_ORDER:
        return canonicalize_physics_records(payload, suite)
    if suite == "blendfile_library_overrides":
        return canonicalize_library_override_sets(payload)
    return payload


def canonicalize_suite_scratch_root(
    payload: bytes, *, suite: str | None, scratch_root: Path | None
) -> bytes:
    """Canonicalize only exact runner-owned per-platform sandbox roots.

    The native and Wasm executions deliberately use separate scratch trees.
    Blender prints the blendfile_io root six times, the animation-action root
    once, and the liblink root 33 times. Treating these runner-owned paths as
    semantic output would create a guaranteed false delta; accepting a broad
    temporary-path rewrite could hide real test output.
    """
    expected_occurrences = SCRATCH_ROOT_POLICIES.get(suite)
    if expected_occurrences is None:
        return payload
    if scratch_root is None or not scratch_root.is_absolute():
        fail(f"{suite} lacks its exact absolute scratch root")
    if SCRATCH_ROOT_TOKEN in payload:
        fail(f"{suite} raw log contains the reserved scratch token")
    root_bytes = os.fsencode(os.fspath(scratch_root))
    root_pattern = re.compile(re.escape(root_bytes) + rb"(?=/)")
    if len(root_pattern.findall(payload)) != expected_occurrences:
        fail(
            f"{suite} scratch root occurrence count differs: "
            f"expected={expected_occurrences}"
        )
    return root_pattern.sub(SCRATCH_ROOT_TOKEN, payload)


def normalized_bytes(
    payload: bytes, *, wasm: bool, suite: str | None = None,
    scratch_root: Path | None = None,
) -> bytes:
    payload = canonicalize_suite_scratch_root(
        payload, suite=suite, scratch_root=scratch_root
    )
    payload = strip_platform_envelope(payload, wasm=wasm)
    commands = [["sed", "-f", str(TIERB / "normalize.sed")]]
    if wasm:
        commands.append(["perl", str(TIERB / "wasm-denoise.pl")])
    for argv in commands:
        result = subprocess.run(argv, input=payload, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False)
        if result.returncode != 0:
            fail(f"normalizer failed rc={result.returncode}: {argv}: {result.stderr[-500:]!r}")
        payload = result.stdout
    if wasm and suite == NO_DENOISER_SUITE:
        lines = payload.splitlines(keepends=True)
        indexes = [
            index for index, line in enumerate(lines)
            if line == NO_DENOISER_NORMALIZED_LINE
        ]
        if len(indexes) != 1:
            fail(
                f"{NO_DENOISER_SUITE} must carry exactly one compiled-out-denoiser warning"
            )
        lines.pop(indexes[0])
        payload = b"".join(lines)
    return canonicalize_suite_records(payload, suite)


def normalized(
    raw: Path, output: Path, *, wasm: bool, suite: str, scratch_root: Path
) -> None:
    payload = normalized_bytes(
        raw.read_bytes(), wasm=wasm, suite=suite, scratch_root=scratch_root
    )
    if output.exists() or output.is_symlink():
        fail(f"refusing to overwrite normalized evidence: {output}")
    output.write_bytes(payload)


def suite_rows() -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for number, raw in enumerate(SUITES.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fields = raw.split("\t")
        if len(fields) < 2 or len(fields) > 4:
            fail(f"suites.tsv:{number}: malformed row")
        fields += [""] * (4 - len(fields))
        name, script, args, mode = fields
        if name in SKIP:
            continue
        rows.append((name, script, args, mode or "normal"))
    if len(rows) != 75 or len({row[0] for row in rows}) != 75:
        fail("live suites.tsv does not select exactly 75 unique CORE suites")
    return rows


def expand(value: str, scratch: Path) -> str:
    return (value.replace("@OUT@", str(scratch))
            .replace("@SRC@", str(ROOT / "upstream/tests/files"))
            .replace("@PY@", str(ROOT / "upstream/tests/python")))


def suite_args(script: str, rawargs: str, mode: str, scratch: Path) -> list[str]:
    args = shlex.split(expand(rawargs, scratch))
    if mode == "blend":
        return [expand(script, scratch), *args]
    result = ["--python", str(ROOT / "upstream/tests/python" / script)]
    if args:
        result.extend(["--", *args])
    return result


def stage_tree(source_root: Path, destination_root: Path) -> list[tuple[Path, Path]]:
    if not source_root.is_dir() or source_root.is_symlink():
        fail(f"canonical runtime asset root is missing or symlinked: {source_root}")
    destination_root.mkdir(parents=True)
    staged: list[tuple[Path, Path]] = []
    for source in sorted(source_root.rglob("*")):
        relative = source.relative_to(source_root)
        if "__pycache__" in relative.parts or source.suffix == ".pyc":
            continue
        if source.is_symlink():
            fail(f"canonical runtime asset source contains a symlink: {source}")
        destination = destination_root / relative
        if source.is_dir():
            destination.mkdir(exist_ok=True)
        elif source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            staged.append((source, destination))
        else:
            fail(f"canonical runtime asset source has unsupported entry: {source}")
    if not staged:
        fail(f"canonical runtime asset source is empty: {source_root}")
    return staged


def compose_datafiles(
    root: Path,
) -> tuple[Path, list[tuple[Path, Path]], list[tuple[Path, Path]]]:
    datafiles = root / "datafiles"
    datafiles_staged = stage_tree(ROOT / "upstream/release/datafiles", datafiles)
    assets_staged = stage_tree(ROOT / "upstream/assets", datafiles / "assets")
    locale = datafiles / "locale"
    locale.mkdir()
    if not LOCALE_LANGUAGES_SOURCE.is_file() or LOCALE_LANGUAGES_SOURCE.is_symlink():
        fail("canonical locale languages index is missing or symlinked")
    shutil.copyfile(LOCALE_LANGUAGES_SOURCE, locale / "languages")
    return datafiles, datafiles_staged, assets_staged


def compose_scripts(
    root: Path,
) -> tuple[Path, list[tuple[Path, Path]], list[tuple[Path, Path]]]:
    """Stage the installed Cycles add-on mapping used by the browser build.

    Directory symlinks are not portable through the Node/NODERAWFS boundary, so
    reproduce the browser's complete scripts tree with an actual
    ``addons_core/cycles`` directory. Bind every source/destination pair in the
    receipt; generated Python caches are never staged.
    """
    if not CYCLES_ADDON_SOURCE.is_dir() or CYCLES_ADDON_SOURCE.is_symlink():
        fail("canonical Cycles add-on source is missing or symlinked")
    sources = sorted(CYCLES_ADDON_SOURCE.glob("*.py"))
    if len(sources) != 10 or any(path.is_symlink() or not path.is_file() for path in sources):
        fail("canonical Cycles add-on must contain exactly ten non-symlink Python sources")
    unexpected = sorted(
        path.relative_to(CYCLES_ADDON_SOURCE).as_posix()
        for path in CYCLES_ADDON_SOURCE.iterdir()
        if path.name != "__pycache__" and path not in sources
    )
    if unexpected:
        fail(f"unexpected Cycles add-on payloads: {unexpected}")
    if not BASE_SCRIPTS_SOURCE.is_dir() or BASE_SCRIPTS_SOURCE.is_symlink():
        fail("canonical Blender scripts source is missing or symlinked")
    scripts = root / "scripts"
    scripts.mkdir()
    base_staged: list[tuple[Path, Path]] = []
    for source in sorted(BASE_SCRIPTS_SOURCE.rglob("*")):
        relative = source.relative_to(BASE_SCRIPTS_SOURCE)
        if "__pycache__" in relative.parts or source.suffix == ".pyc":
            continue
        if source.is_symlink():
            fail(f"canonical Blender scripts source contains a symlink: {relative}")
        destination = scripts / relative
        if source.is_dir():
            destination.mkdir(exist_ok=True)
        elif source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            base_staged.append((source, destination))
        else:
            fail(f"canonical Blender scripts source has unsupported entry: {relative}")
    addon = scripts / "addons_core/cycles"
    if addon.exists() or addon.is_symlink():
        fail("canonical base scripts unexpectedly already contain Cycles")
    addon.mkdir(parents=True)
    cycles_staged: list[tuple[Path, Path]] = []
    for source in sources:
        destination = addon / source.name
        shutil.copyfile(source, destination)
        cycles_staged.append((source, destination))
    return scripts, base_staged, cycles_staged


def language_index_count(path: Path) -> int:
    count = 0
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        fields = raw.split(":")
        if (len(fields) != 4 or not fields[0].isdigit() or not fields[1]
                or not fields[2] or not fields[3].endswith("%")
                or not fields[3][:-1].isdigit()):
            fail(f"malformed locale languages row {number}")
        count += 1
    if count < 2:
        fail("locale languages index is unexpectedly empty")
    return count


def runtime_assets_manifest(
    output: Path, scripts: Path, base_staged: list[tuple[Path, Path]],
    cycles_staged: list[tuple[Path, Path]], datafiles: Path,
    datafiles_staged: list[tuple[Path, Path]], assets_staged: list[tuple[Path, Path]],
) -> Path:
    return write_json(output / "runtime-assets.json", {
        "schema": 1,
        "system_resources": ".",
        "system_scripts": scripts.relative_to(output.parent).as_posix(),
        "python_environment": DETERMINISTIC_PYTHON_ENV,
        "pass_delta_note": ref(PASS_DELTA_NOTE),
        "base_scripts": [
            {"source": ref(source), "staged": ref(destination)}
            for source, destination in base_staged
        ],
        "cycles_addon": [
            {"source": ref(source), "staged": ref(destination)}
            for source, destination in cycles_staged
        ],
        "datafiles": [
            {"source": ref(source), "staged": ref(destination)}
            for source, destination in datafiles_staged
        ],
        "assets": [
            {"source": ref(source), "staged": ref(destination)}
            for source, destination in assets_staged
        ],
        "locale_languages": {
            "source": ref(LOCALE_LANGUAGES_SOURCE),
            "staged": ref(datafiles / "locale/languages"),
        },
    })


def python_probe(
    node: Path, wasm_js: Path, datafiles: Path, resources: Path, output: Path
) -> tuple[str, bool, bool, int, Path, Path, Path]:
    probe = output / "python-probe.json"
    expression = (
        "import bpy,json,pathlib,sys;bpy.context.scene.render.engine='CYCLES';"
        f"pathlib.Path({str(probe)!r}).write_text(json.dumps({{'version':sys.version.split()[0],"
        "'import_bpy':bpy.app.version[:2]==(5,2),"
        "'cycles_engine':bpy.context.scene.render.engine=='CYCLES',"
        "'language_count':len(bpy.context.preferences.view.bl_rna.properties['language'].enum_items)}"
        ",sort_keys=True))"
    )
    env = os.environ.copy()
    env.update({
        "BLENDER_SYSTEM_RESOURCES": str(resources),
        "BLENDER_SYSTEM_PYTHON": str(ROOT / "lib/wasm"),
        "BLENDER_SYSTEM_DATAFILES": str(datafiles),
        **DETERMINISTIC_PYTHON_ENV,
    })
    stdout = output / "python-probe.stdout"
    stderr = output / "python-probe.stderr"
    rc = capture([str(node), str(wasm_js), "--background", "--factory-startup",
                  "--python-exit-code", "1", "--python-expr", expression],
                 stdout, stderr,
                 env=env, cwd=output, timeout=300)
    if rc != 0 or not probe.is_file():
        fail(f"Wasm Python/bpy probe failed rc={rc}")
    if (stdout.read_bytes() != b"Blender 5.2.0 LTS\n\nBlender quit\n"
            or stderr.read_bytes() != b""):
        fail("Wasm Python/bpy probe emitted unexpected stdout/stderr")
    value = json.loads(probe.read_text(encoding="utf-8"))
    if set(value) != {"version", "import_bpy", "cycles_engine", "language_count"}:
        fail("Wasm Python probe schema mismatch")
    return (
        value["version"], value["import_bpy"] is True,
        value["cycles_engine"] is True, value["language_count"], probe, stdout, stderr,
    )


def stdlib_manifest(output: Path) -> Path:
    base = ROOT / "lib/wasm/lib/python3.13"
    if not base.is_dir():
        fail(f"Python stdlib missing: {base}")
    manifest = output / "python-stdlib.manifest"
    with manifest.open("x", encoding="utf-8") as stream:
        for path in sorted(candidate for candidate in base.rglob("*") if candidate.is_file()):
            stream.write(f"{path.relative_to(ROOT).as_posix()}\t{path.stat().st_size}\t{sha256(path)}\n")
    return manifest


def require_cache_bool(path: Path, key: str, expected: str) -> None:
    rows = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(f"{key}:")
    ]
    if len(rows) != 1 or rows[0].split("=", 1) != [f"{key}:BOOL", expected]:
        fail(f"canonical runtime cache must set {key}:BOOL={expected}")


def active_deferral_rows(value: Any) -> dict[str, dict[str, Any]]:
    rows = value.get("deferred") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        fail("deferral registry lacks deferred array")
    found: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in found:
            fail(f"deferral registry has invalid/duplicate row: {number}")
        found[row["id"]] = row
    detector = found.get(DETECTOR_ACTIVE_ID)
    if detector is None or detector.get("status") != DETECTOR_ACTIVE_STATUS:
        fail(f"{DETECTOR_ACTIVE_ID} must retain exact {DETECTOR_ACTIVE_STATUS} status")
    if not isinstance(detector.get("evidence"), str) or not detector["evidence"]:
        fail(f"{DETECTOR_ACTIVE_ID} lacks exact evidence")
    for name, row in found.items():
        if row.get("status") == DETECTOR_ACTIVE_STATUS and name != DETECTOR_ACTIVE_ID:
            fail(f"unexpected {DETECTOR_ACTIVE_STATUS} deferral: {name}")
    return {
        name: row for name, row in found.items()
        if row.get("status") in {"deferred", "partial"}
        or (name == DETECTOR_ACTIVE_ID and row.get("status") == DETECTOR_ACTIVE_STATUS)
    }


def active_deferrals() -> dict[str, dict[str, Any]]:
    value = json.loads((ROOT / "ledger/deferred.json").read_text(encoding="utf-8"))
    return active_deferral_rows(value)


def deferral_registry_rows() -> dict[str, dict[str, Any]]:
    value = json.loads((ROOT / "ledger/deferred.json").read_text(encoding="utf-8"))
    active_deferral_rows(value)
    return {row["id"]: row for row in value["deferred"]}


def require_detector_marker(
    suite: str, deferral_ids: set[str], raw_output: bytes, normalized_output: bytes
) -> str | None:
    detector = DETECTOR_ACTIVE_ID in deferral_ids
    if not detector:
        return None
    if suite != DETECTOR_ACTIVE_SUITE:
        fail(f"{DETECTOR_ACTIVE_ID} is not valid for suite: {suite}")
    marker = DETECTOR_ACTIVE_MARKER.encode("utf-8")
    if marker not in normalized_output or DETECTOR_ACTIVE_RAW_RE.search(raw_output) is None:
        fail(f"{suite} lacks the exact canonical ADR-004 detector marker")
    return DETECTOR_ACTIVE_MARKER


def failure_deferral_records(
    suite: str, active: dict[str, dict[str, Any]], raw_output: bytes,
    normalized_output: bytes,
) -> tuple[list[str], list[dict[str, Any]]]:
    expected = DEFERRALS.get(suite, set())
    allowed = expected & set(active)
    if not expected or allowed != expected:
        fail(f"Wasm suite failed without exact active deferral: {suite}")
    marker = require_detector_marker(suite, allowed, raw_output, normalized_output)
    records: list[dict[str, Any]] = []
    for name in sorted(allowed):
        row = active[name]
        evidence = row.get("evidence")
        status = row.get("status")
        if not isinstance(evidence, str) or not evidence or not isinstance(status, str) or not status:
            fail(f"active deferral lacks status/evidence: {name}")
        records.append({
            "id": name, "status": status, "evidence": evidence,
            "marker": marker if name == DETECTOR_ACTIVE_ID else None,
        })
    return sorted(allowed), records


def rna_menu_lines(names: tuple[str, ...]) -> list[bytes]:
    return [
        b'<bpy_struct, FileBrowserFSMenuEntry("' + name.encode() + b'")'
        + RNA_MENU_CONTEXT
        for name in names
    ]


def replace_exact_block(payload: bytes, block: list[bytes], marker: bytes, where: str) -> bytes:
    lines = payload.splitlines(keepends=True)
    indexes = [
        index for index in range(len(lines) - len(block) + 1)
        if lines[index:index + len(block)] == block
    ]
    if len(indexes) != 1:
        fail(f"{where} lacks one exact contiguous platform delta block")
    index = indexes[0]
    return b"".join(lines[:index] + [marker] + lines[index + len(block):])


def animation_delta_projection(payload: bytes, *, wasm: bool) -> bytes:
    lines = payload.splitlines(keepends=True)
    group_error = (
        b"ERROR: one of the ID's for the groups to assign to is invalid "
        + (b"(ptr=0xADDR, val=0)\n" if wasm else b"(ptr=0xADDR, val=0x0)\n")
    )
    native_progress = [b"." * 23 + ANIMATION_REMAP_READ]
    wasm_progress = [
        b"." * 4 + ANIMATION_ASSIGNMENT_WARNING,
        b"." * 6 + group_error,
        ANIMATION_FCURVE_ERROR,
        b"." * 13 + ANIMATION_REMAP_READ,
    ]
    progress = wasm_progress if wasm else native_progress
    progress_marker = b"<ANIMATION_PROGRESS_AND_DIAGNOSTICS>\n"
    projected = replace_exact_block(
        b"".join(lines), progress, progress_marker, "bl_animation_action progress"
    )
    lines = projected.splitlines(keepends=True)
    phase_anchor = [
        progress_marker, ANIMATION_SECOND_REMAP_READ, ANIMATION_SAVED,
        ANIMATION_TEMP_READ,
    ]
    phase_indexes = [
        index for index in range(len(lines) - len(phase_anchor) + 1)
        if lines[index:index + len(phase_anchor)] == phase_anchor
    ]
    if phase_indexes != [lines.index(progress_marker)]:
        fail("bl_animation_action library phase moved relative to progress/remap")
    if wasm:
        indexes = [index for index, line in enumerate(lines) if line == ANIMATION_TEMP_READ]
        if len(indexes) != 1 or indexes[0] + 4 >= len(lines):
            fail("bl_animation_action lacks its exact temp-read delta context")
        index = indexes[0]
        if (lines[index + 1] != ANIMATION_OBJECTDATA_WARNING
                or lines[index + 2] != ANIMATION_INFO_LIBRARY
                or lines[index + 3] != ANIMATION_MISSING_DATA
                or lines[index + 4] != ANIMATION_LAYERED_READ):
            fail("bl_animation_action Wasm ObjectData delta sequence differs")
        lines[index:index + 5] = [
            ANIMATION_TEMP_READ, b"<ANIMATION_LIBRARY_READ>\n", ANIMATION_LAYERED_READ,
        ]
        if not lines or lines[-1] != b"OK\n":
            fail("bl_animation_action Wasm diagnostics moved outside the test sequence")
    else:
        post_ok = [
            b"OK\n", ANIMATION_ASSIGNMENT_WARNING, group_error, ANIMATION_FCURVE_ERROR,
        ]
        if lines[-4:] != post_ok:
            fail("bl_animation_action native post-OK diagnostics moved")
        lines[-4:] = [b"OK\n"]
        indexes = [index for index, line in enumerate(lines) if line == ANIMATION_TEMP_READ]
        if len(indexes) != 1 or indexes[0] + 2 >= len(lines):
            fail("bl_animation_action native library-read context differs")
        index = indexes[0]
        if (lines[index + 1] != ANIMATION_INFO_LIBRARY
                or lines[index + 2] != ANIMATION_LAYERED_READ):
            fail("bl_animation_action native library-read sequence differs")
        lines[index:index + 3] = [
            ANIMATION_TEMP_READ, b"<ANIMATION_LIBRARY_READ>\n", ANIMATION_LAYERED_READ,
        ]
    return b"".join(lines)


def library_override_delta_projection(payload: bytes, *, wasm: bool) -> bytes:
    del wasm
    lines = payload.splitlines(keepends=True)
    index = LIBRARY_OVERRIDE_PHASE_BEFORE_INDEX
    if (len(lines) <= index + 10 or lines[index] != LIBRARY_OVERRIDE_PHASE_BEFORE
            or lines[index + 10] != LIBRARY_OVERRIDE_PHASE_AFTER):
        fail("blendfile_library_overrides hierarchy phase moved")
    phase = lines[index + 1:index + 10]
    controllers = (
        LIBRARY_OVERRIDE_CONTROLLER,
        LIBRARY_OVERRIDE_CONTROLLER_001,
        LIBRARY_OVERRIDE_CONTROLLER_002,
    )
    collections = (b"LibCube", b"LibCube.001", b"LibCube.002")
    found_pairs: set[tuple[bytes, bytes]] = set()
    for number, (controller, collection) in enumerate(zip(controllers, collections)):
        offset = number * 3
        if phase[offset] != controller:
            fail("blendfile_library_overrides controller row/order differs")
        records = []
        for line in phase[offset + 1:offset + 3]:
            match = LIBRARY_OVERRIDE_RECORD_RE.fullmatch(line)
            if match is None or match.group("collection") != collection:
                fail("blendfile_library_overrides collection association differs")
            records.append((match.group("reference"), match.group("local")))
        if [reference for reference, _ in records] != [b"LibCube.002", b"LibCube.001"]:
            fail("blendfile_library_overrides reference row/order differs")
        pair = (records[0][1], records[1][1])
        if pair not in LIBRARY_OVERRIDE_LOCAL_PAIRS:
            fail("blendfile_library_overrides local suffix pair differs")
        found_pairs.add(pair)
    if found_pairs != LIBRARY_OVERRIDE_LOCAL_PAIRS:
        fail("blendfile_library_overrides local suffix pairs are not a bijection")
    lines[index + 1:index + 10] = [
        b"<LIBRARY_OVERRIDE_IDNAME_HIERARCHY_PHASE>\n"
    ]
    return b"".join(lines)


def pass_delta_records(
    suite: str, registry: dict[str, dict[str, Any]],
    native_output: bytes, wasm_output: bytes,
) -> tuple[list[str], list[dict[str, Any]]]:
    deferral_id = PASS_DELTA_DEFERRALS.get(suite)
    if deferral_id is None or deferral_id not in registry:
        fail(f"passing suite lacks exact normalized parity: {suite}")
    if suite == "bl_rna_paths":
        marker = b"<OS_FILE_BROWSER_MENU>\n"
        native_projection = replace_exact_block(
            native_output, rna_menu_lines(RNA_NATIVE_MENU), marker, suite
        )
        wasm_projection = replace_exact_block(
            wasm_output, rna_menu_lines(RNA_WASM_MENU), marker, suite
        )
    elif suite == "bl_animation_action":
        native_projection = animation_delta_projection(native_output, wasm=False)
        wasm_projection = animation_delta_projection(wasm_output, wasm=True)
    elif suite == "blendfile_library_overrides":
        native_projection = library_override_delta_projection(native_output, wasm=False)
        wasm_projection = library_override_delta_projection(wasm_output, wasm=True)
    else:
        fail(f"unimplemented pass-with-delta suite: {suite}")
    if native_projection != wasm_projection:
        fail(f"{suite} differs outside its exact pass-with-delta schema")
    row = registry[deferral_id]
    contract = PASS_DELTA_LEDGER[deferral_id]
    if any(row.get(key) != value for key, value in contract.items()):
        fail(f"pass-with-delta ledger contract differs: {deferral_id}")
    status, evidence = contract["status"], contract["evidence"]
    return [deferral_id], [{
        "id": deferral_id, "status": status, "evidence": evidence,
        "marker": PASS_DELTA_MARKERS[suite],
    }]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--freeze-receipt", type=Path, required=True)
    parser.add_argument("--native-blender", type=Path, required=True)
    parser.add_argument("--wasm-blender-js", type=Path, required=True)
    parser.add_argument("--node", type=Path,
                        default=ROOT / "tools/emsdk/node/22.16.0_64bit/bin/node")
    parser.add_argument("--suite-timeout", type=int, default=600)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if LABEL_RE.fullmatch(args.run_label) is None:
            fail("unsafe run label")
        output = OUTPUT_ROOT / args.run_label / "m2"
        if output.exists() or output.is_symlink():
            fail(f"refusing to overwrite M2 attempt: {output}")
        output.mkdir(parents=True)
        incomplete = output / "INCOMPLETE"
        incomplete.write_text("M2 raw execution in progress\n", encoding="utf-8")
        freeze = json.loads(args.freeze_receipt.read_text(encoding="utf-8"))
        if freeze.get("schema") != 1 or freeze.get("verdict") != "PASS":
            fail("source freeze is not schema-1 PASS")
        freeze_hash = sha256(args.freeze_receipt)
        native = canonical_file(
            args.native_blender, CANONICAL_NATIVE_ORACLE, "M2 native Blender oracle"
        )
        wasm_js = canonical_file(
            args.wasm_blender_js, CANONICAL_RUNTIME_JS, "M2 Blender JavaScript runtime"
        )
        wasm = canonical_file(
            wasm_js.with_suffix(".wasm"), CANONICAL_RUNTIME_JS.with_suffix(".wasm"),
            "M2 Blender Wasm runtime",
        )
        wasm_cache = canonical_file(
            ROOT / "build-wasm-m1-parity/CMakeCache.txt",
            ROOT / "build-wasm-m1-parity/CMakeCache.txt", "M2 Blender CMake cache",
        )
        require_cache_bool(wasm_cache, "WITH_OPENIMAGEDENOISE", "OFF")
        node = canonical_file(args.node, CANONICAL_NODE, "M2 Node runtime")
        node_version = subprocess.run(
            [str(node), "--version"], capture_output=True, text=True, check=True
        ).stdout.strip()
        if node_version != CANONICAL_NODE_VERSION:
            fail(f"M2 Node version must be exactly {CANONICAL_NODE_VERSION}")
        datafiles, datafiles_staged, assets_staged = compose_datafiles(output)
        scripts, base_scripts, cycles_sources = compose_scripts(output)
        runtime_assets = runtime_assets_manifest(
            output / "raw", scripts, base_scripts, cycles_sources, datafiles,
            datafiles_staged, assets_staged,
        )
        (version, bpy_ok, cycles_ok, language_count,
         python_probe_result, python_probe_stdout, python_probe_stderr) = python_probe(
            node, wasm_js, datafiles, output, output / "raw"
        )
        expected_language_count = language_index_count(LOCALE_LANGUAGES_SOURCE)
        if (version != "3.13.13" or not bpy_ok or not cycles_ok
                or language_count != expected_language_count):
            fail(
                "Wasm Python contract mismatch: "
                f"version={version} import_bpy={bpy_ok} cycles={cycles_ok} "
                f"languages={language_count}"
            )
        active = active_deferrals()
        registry = deferral_registry_rows()
        rows: dict[str, Any] = {}
        scratch = output / "scratch"
        scratch.mkdir()
        common_prefix = [
            "--console-crash-handler", "--debug-memory", "--python-exit-code", "1",
            "--python-expr",
            "import bpy,sys;"
            "sys.stdout.reconfigure(line_buffering=True,write_through=True);"
            "sys.stderr.reconfigure(line_buffering=True,write_through=True);"
            "bpy.context.preferences.filepaths.file_preview_type='NONE'",
        ]
        native_env = os.environ.copy()
        native_env.update(DETERMINISTIC_PYTHON_ENV)
        wasm_env = os.environ.copy()
        wasm_env.update({
            "BLENDER_SYSTEM_RESOURCES": str(output),
            "BLENDER_SYSTEM_PYTHON": str(ROOT / "lib/wasm"),
            "BLENDER_SYSTEM_DATAFILES": str(datafiles),
            **DETERMINISTIC_PYTHON_ENV,
        })
        for name, script, rawargs, mode in suite_rows():
            row_dir = output / "raw/suites" / name
            row_dir.mkdir(parents=True)
            native_scratch = scratch / name / "native"
            wasm_scratch = scratch / name / "wasm"
            native_scratch.mkdir(parents=True)
            wasm_scratch.mkdir()
            native_args = suite_args(script, rawargs, mode, native_scratch)
            wasm_args = suite_args(script, rawargs, mode, wasm_scratch)
            debug = [] if mode == "allow_error" else ["--debug-exit-on-error"]
            nraw, wraw = row_dir / "native.raw.log", row_dir / "wasm.raw.log"
            nrc = capture_combined(
                [str(native), *common_prefix[:2], *debug, *common_prefix[2:], *native_args],
                nraw, env=native_env, cwd=native_scratch, timeout=args.suite_timeout,
            )
            wrc = capture_combined(
                [str(node), str(wasm_js), "--background", "--factory-startup",
                 *common_prefix[:2], *debug, *common_prefix[2:], *wasm_args],
                wraw, env=wasm_env, cwd=wasm_scratch, timeout=args.suite_timeout,
            )
            native_log, wasm_log = row_dir / "native.normalized.txt", row_dir / "wasm.normalized.txt"
            normalized(
                nraw, native_log, wasm=False, suite=name,
                scratch_root=native_scratch,
            )
            normalized(
                wraw, wasm_log, wasm=True, suite=name,
                scratch_root=wasm_scratch,
            )
            if nrc != 0:
                fail(f"native oracle suite failed: {name} rc={nrc}")
            if wrc == 0:
                if native_log.read_bytes() == wasm_log.read_bytes():
                    result, declared, records = "PASS", [], []
                else:
                    declared, records = pass_delta_records(
                        name, registry, native_log.read_bytes(), wasm_log.read_bytes()
                    )
                    result = "PASS_WITH_DEFERRAL"
            else:
                declared, records = failure_deferral_records(
                    name, active, wraw.read_bytes(), wasm_log.read_bytes()
                )
                result = "DEFERRED"
            rows[name] = {
                "native_exit": nrc, "wasm_exit": wrc,
                "native_raw_log": ref(nraw), "wasm_raw_log": ref(wraw),
                "native_log": ref(native_log), "wasm_log": ref(wasm_log),
                "native_normalized_sha256": sha256(native_log),
                "wasm_normalized_sha256": sha256(wasm_log),
                "result": result, "deferral_ids": declared,
                "deferral_records": records,
            }
        stdlib = stdlib_manifest(output / "raw")
        policy = write_json(output / "raw/normalization-policy.json", {
            "schema": 1,
            "pipeline": {
                "native": [ref(HERE / "run_m2.py"), ref(TIERB / "normalize.sed")],
                "wasm": [ref(HERE / "run_m2.py"), ref(TIERB / "normalize.sed"),
                         ref(TIERB / "wasm-denoise.pl")],
            },
            "platform_envelope": {
                "native": "one exact adjacent allocator + pinned native banner",
                "wasm": "one exact adjacent allocator + pinned Wasm banner",
                "wasm_optional": [
                    "exact immediately-following locale startup warning",
                ],
            },
            "suite_envelope": {
                NO_DENOISER_SUITE: {
                    "platform": "wasm",
                    "exact_count": 1,
                    "exact_normalized_line": NO_DENOISER_NORMALIZED_LINE.decode().rstrip("\n"),
                    "required_cache_flag": "WITH_OPENIMAGEDENOISE:BOOL=OFF",
                },
            },
            "scratch_root": {
                "suites": dict(sorted(SCRATCH_ROOT_POLICIES.items())),
                "platforms": ["native", "wasm"],
                "replacement": SCRATCH_ROOT_TOKEN.decode(),
            },
            "exit_code_primary": True, "normalized_bytes_exact_for_pass": True,
            "exact_replay_by_verifier": True,
        })
        stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        receipt = write_json(output / "receipt.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "created_utc": stamp, "source_freeze_sha256": freeze_hash,
            "runtime": {"native_oracle": ref(native), "node": ref(node),
                        "javascript": ref(wasm_js), "wasm": ref(wasm),
                        "cmake_cache": ref(wasm_cache),
                        "node_version": node_version,
                        "python_stdlib_manifest": ref(stdlib), "python_version": version,
                        "python_probe_result": ref(python_probe_result),
                        "python_probe_stdout": ref(python_probe_stdout),
                        "python_probe_stderr": ref(python_probe_stderr),
                        "import_bpy": bpy_ok, "cycles_engine": cycles_ok,
                        "language_count": language_count,
                        "openimagedenoise": False,
                        "runtime_assets": ref(runtime_assets), "factory_startup": True},
            "suite_manifest": ref(SUITES), "normalization_policy": ref(policy),
            "deferral_registry": ref(ROOT / "ledger/deferred.json"),
            "total": 75, "rows": rows,
        })
        incomplete.unlink()
        print(f"FINAL_M2_RAW_PASS receipt={receipt.relative_to(ROOT)} sha256={sha256(receipt)}")
        return 0
    except (RunError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"FINAL_M2_RAW_FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
