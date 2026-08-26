#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind launch-visible forced-off features to truthful deferral rows."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "ledger/deferred.json"
CONFIG = ROOT / "patches/blender_web.cmake"
NOTE = ROOT / "notes/m8-deferral-registry-completeness-20260826.md"
S7_NOTE = ROOT / "notes/s7-wsl2-hardware-blocker-20260822.md"

FEATURE_FLAGS = {
    "feature-off-ik-solvers": ("WITH_IK_SOLVER", "WITH_IK_ITASC"),
    "feature-off-bullet-physics": ("WITH_BULLET",),
    "feature-off-ocean-modifier": ("WITH_MOD_OCEANSIM", "WITH_FFTW3"),
    "feature-off-remesh-quadriflow": ("WITH_MOD_REMESH", "WITH_QUADRIFLOW"),
    "feature-off-exact-boolean": ("WITH_MANIFOLD", "WITH_GMP"),
    "feature-off-slim-uv": ("WITH_UV_SLIM",),
    "feature-off-video-ffmpeg": ("WITH_CODEC_FFMPEG",),
    "feature-off-audio": (
        "WITH_AUDASPACE",
        "WITH_CODEC_SNDFILE",
        "WITH_OPENAL",
        "WITH_JACK",
        "WITH_PULSEAUDIO",
        "WITH_PIPEWIRE",
        "WITH_SDL_AUDIO",
        "WITH_COREAUDIO",
        "WITH_WASAPI",
        "WITH_RUBBERBAND",
    ),
    "feature-off-fbx-io": ("WITH_IO_FBX",),
    "feature-off-alembic-io": ("WITH_ALEMBIC",),
    "feature-off-grease-pencil-vector-io": (
        "WITH_IO_GREASE_PENCIL",
        "WITH_HARU",
        "WITH_POTRACE",
    ),
    "feature-off-openimagedenoise": ("WITH_OPENIMAGEDENOISE",),
    "feature-off-freestyle": ("WITH_FREESTYLE",),
    "feature-off-motion-tracking": ("WITH_LIBMV",),
    "feature-off-openxr": ("WITH_XR_OPENXR",),
    "feature-off-jpeg2000-webp-dpx": (
        "WITH_IMAGE_OPENJPEG",
        "WITH_IMAGE_WEBP",
        "WITH_IMAGE_CINEON",
    ),
}

S7_ROWS = {
    "wsl2-hardware-webgpu-m3": "M3",
    "wsl2-hardware-webgpu-m4": "M4",
    "wsl2-hardware-webgpu-m5": "M5",
    "wsl2-hardware-webgpu-m6-gpu": "M6",
    "wsl2-hardware-webgpu-m7": "M7",
    "wsl2-hardware-webgpu-m8": "M8",
}
S7_BLOCKER = (
    "no conformant hardware Vulkan ICD in WSL2 "
    "(NVIDIA ships none; Mesa dzn rejected by Dawn)"
)
REQUIRED_FIELDS = ("blocker", "impact", "revisit", "evidence", "workaround")


def fail(message: str) -> None:
    raise SystemExit(f"M8_DEFERRAL_REGISTRY_FAIL {message}")


def cmake_values(source: str, flag: str) -> list[str]:
    pattern = rf"(?m)^\s*set\(\s*{re.escape(flag)}\s+(ON|OFF)\s+CACHE\s+BOOL\b"
    return re.findall(pattern, source)


def indexed_rows(document: Any, failures: list[str]) -> dict[str, dict[str, Any]]:
    rows = document.get("deferred") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        failures.append("missing-deferred-array")
        return {}

    by_id: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            failures.append(f"invalid-row={number}")
            continue
        row_id = row["id"]
        if row_id in by_id:
            failures.append(f"duplicate-id={row_id}")
            continue
        by_id[row_id] = row
    return by_id


def validate(
    document: Any,
    config: str,
    note: str,
    s7_note: str,
) -> list[str]:
    failures: list[str] = []
    by_id = indexed_rows(document, failures)

    for row_id, flags in FEATURE_FLAGS.items():
        row = by_id.get(row_id)
        if row is None:
            failures.append(f"missing-feature-row={row_id}")
            continue
        if row.get("status") != "deferred":
            failures.append(f"feature-status={row_id}")
        if row.get("milestone") != "M8 launch registry":
            failures.append(f"feature-milestone={row_id}")
        for field in REQUIRED_FIELDS:
            if not str(row.get(field, "")).strip():
                failures.append(f"feature-{field}={row_id}")
        if not str(row.get("blocker", "")).startswith("Chosen browser launch scope cut:"):
            failures.append(f"feature-blocker-class={row_id}")
        evidence = str(row.get("evidence", ""))
        if "patches/blender_web.cmake" not in evidence or NOTE.name not in evidence:
            failures.append(f"feature-evidence={row_id}")
        for flag in flags:
            values = cmake_values(config, flag)
            if values != ["OFF"]:
                failures.append(
                    f"forced-off={row_id}:{flag}:{','.join(values) if values else 'absent'}"
                )

    found_s7 = {row_id for row_id in by_id if row_id.startswith("wsl2-hardware-webgpu-")}
    if found_s7 != set(S7_ROWS):
        failures.append(f"s7-row-set={','.join(sorted(found_s7)) or 'none'}")
    for row_id, milestone in S7_ROWS.items():
        row = by_id.get(row_id)
        if row is None:
            failures.append(f"missing-s7-row={row_id}")
            continue
        if row.get("status") != "deferred" or row.get("milestone") != milestone:
            failures.append(f"s7-disposition={row_id}")
        if row.get("blocker") != S7_BLOCKER:
            failures.append(f"s7-blocker={row_id}")
        impact = str(row.get("impact", ""))
        revisit = str(row.get("revisit", ""))
        evidence = str(row.get("evidence", ""))
        for token in (
            "on this WSL2 host",
            "driver-operated conformant Apple M4 Pro",
            "project receipt",
        ):
            if token not in impact:
                failures.append(f"s7-impact={row_id}:{token}")
        if "driver-operated Apple M4 Pro" not in revisit:
            failures.append(f"s7-revisit={row_id}")
        if S7_NOTE.name not in evidence or NOTE.name not in evidence:
            failures.append(f"s7-evidence={row_id}")
        stale = (impact + "\n" + revisit).lower()
        for token in ("normal host reboot", "windows-side edge", "cannot be produced here"):
            if token in stale:
                failures.append(f"s7-stale={row_id}:{token}")

    for row_id in FEATURE_FLAGS:
        if f"`{row_id}`" not in note:
            failures.append(f"note-feature={row_id}")
    for token in (
        "project-scope truth correction",
        "driver-operated Apple M4 Pro",
        "strict CAPTURE split generation",
        "Windows-side Edge plan is closed",
        "retry this path or restart WSL/Windows",
        "binds no receipt, profile, or split product",
    ):
        if token not in s7_note:
            failures.append(f"s7-note-token={token}")
    if "A conformant path is staged for later through Windows-side Edge" in s7_note:
        failures.append("s7-note-stale-reboot-path")

    return failures


def replace_forced_off(config: str, flag: str) -> str:
    pattern = re.compile(
        rf"(?m)^(\s*set\(\s*{re.escape(flag)}\s+)OFF(\s+CACHE\s+BOOL\b)"
    )
    mutated, count = pattern.subn(r"\1ON\2", config)
    if count != 1:
        fail(f"selfcheck-mutation-source={flag}:{count}")
    return mutated


def require_rejected(
    name: str,
    document: Any,
    config: str,
    note: str,
    s7_note: str,
) -> None:
    if not validate(document, config, note, s7_note):
        fail(f"selfcheck-accepted={name}")


def run_selfcheck(document: Any, config: str, note: str, s7_note: str) -> int:
    negative = 0
    for row_id in FEATURE_FLAGS:
        mutated = deepcopy(document)
        mutated["deferred"] = [row for row in mutated["deferred"] if row.get("id") != row_id]
        require_rejected(f"row-{row_id}", mutated, config, note, s7_note)
        negative += 1

    for flag in sorted({flag for flags in FEATURE_FLAGS.values() for flag in flags}):
        require_rejected(
            f"flag-{flag}", document, replace_forced_off(config, flag), note, s7_note
        )
        negative += 1

    mutated = deepcopy(document)
    mutated["deferred"].append(deepcopy(mutated["deferred"][0]))
    require_rejected("duplicate-id", mutated, config, note, s7_note)
    negative += 1

    for row_id in S7_ROWS:
        mutated = deepcopy(document)
        rows = {row["id"]: row for row in mutated["deferred"]}
        rows[row_id]["impact"] = rows[row_id]["impact"].replace(
            "on this WSL2 host", "for the project"
        )
        require_rejected(f"s7-scope-{row_id}", mutated, config, note, s7_note)
        negative += 1

    mutated = deepcopy(document)
    rows = {row["id"]: row for row in mutated["deferred"]}
    rows["wsl2-hardware-webgpu-m4"]["revisit"] = (
        "After a normal host reboot enables Windows-side Edge."
    )
    require_rejected("s7-reboot", mutated, config, note, s7_note)
    negative += 1

    return negative


def main() -> None:
    try:
        document = json.loads(LEDGER.read_text(encoding="utf-8"))
        config = CONFIG.read_text(encoding="utf-8")
        note = NOTE.read_text(encoding="utf-8")
        s7_note = S7_NOTE.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as error:
        fail(f"input={error}")

    failures = validate(document, config, note, s7_note)
    if failures:
        fail(failures[0])
    negative = run_selfcheck(document, config, note, s7_note)
    flags = {flag for values in FEATURE_FLAGS.values() for flag in values}
    print(
        "M8_DEFERRAL_REGISTRY_PASS "
        f"features={len(FEATURE_FLAGS)} flags={len(flags)} s7={len(S7_ROWS)} "
        f"negative={negative}"
    )


if __name__ == "__main__":
    main()
