#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build, execute, and receipt the exact M0 native-oracle container."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get(
    "BLENDER_ORACLE_IMAGE", "blender-web/oracle:5.2.0-fbe6228777e7"
)
PLATFORM = "linux/amd64"
BLENDER_VERSION = "5.2.0"
BLENDER_COMMIT = "fbe6228777e7d9afefcd61a413844e790ae75db7"
BLENDER_COMMIT_DISPLAY = BLENDER_COMMIT[:12]
OIIO_VERSION = "2.4.17.0"


def fail(message: str) -> "NoReturn":
    print(f"M0_ORACLE_RECEIPT_FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(command: list[str]) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        fail(
            f"command exited {result.returncode}: {' '.join(command)}\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout


def docker_run(image: str, entrypoint: str, *arguments: str) -> str:
    return run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            PLATFORM,
            "--network",
            "none",
            "--entrypoint",
            entrypoint,
            image,
            *arguments,
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", args.label):
        fail("label must be 1-128 safe filename characters")
    output = args.output.resolve()
    if output.exists():
        fail(f"refusing to overwrite {output}")

    run(["docker", "info"])
    verify = subprocess.run(
        [os.fspath(ROOT / "scripts/oracle-container.sh"), "verify"],
        check=False,
        capture_output=True,
        text=True,
    )
    if verify.returncode != 0:
        fail(
            f"oracle verification exited {verify.returncode}\n"
            f"{verify.stderr.strip()}"
        )
    for token in ("Blender 5.2.0 LTS", "M0_ORACLE_BPY_OK", OIIO_VERSION,
                  "M0_ORACLE_CONTAINER_OK"):
        if token not in verify.stdout:
            fail(f"oracle verification omitted {token!r}")

    repo_digests = json.loads(
        run(["docker", "image", "inspect", IMAGE, "--format", "{{json .RepoDigests}}"])
    )
    repository = IMAGE.split(":", 1)[0]
    matching = sorted(
        value.split("@", 1)[1]
        for value in repo_digests
        if value.startswith(repository + "@sha256:")
    )
    if len(matching) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", matching[0]):
        fail(f"expected one immutable repository digest for {repository}, got {matching}")
    image_digest = matching[0]
    immutable_image = f"{repository}@{image_digest}"

    blender_version = docker_run(immutable_image, "/opt/blender/blender", "--version")
    if f"Blender {BLENDER_VERSION} LTS" not in blender_version:
        fail("digest-specific Blender version mismatch")
    if f"build hash: {BLENDER_COMMIT_DISPLAY}" not in blender_version:
        fail("digest-specific Blender commit mismatch")

    bpy_probe = docker_run(
        immutable_image,
        "/opt/blender/blender",
        "--background",
        "--factory-startup",
        "--python-expr",
        "import bpy; assert sorted(bpy.data.objects.keys()) == "
        "['Camera', 'Cube', 'Light']; print('M0_ORACLE_BPY_OK')",
    )
    if "M0_ORACLE_BPY_OK" not in bpy_probe:
        fail("digest-specific bpy probe failed")

    oiio_version = docker_run(immutable_image, "/usr/bin/oiiotool", "--version").strip()
    if oiio_version != OIIO_VERSION:
        fail(f"digest-specific oiiotool mismatch: {oiio_version!r}")

    receipt = {
        "schema": 1,
        "verdict": "PASS",
        "run_label": args.label,
        "image_digest": image_digest,
        "blender_version": BLENDER_VERSION,
        "blender_commit": BLENDER_COMMIT,
        "oiiotool_version": OIIO_VERSION,
        "exit_code": 0,
    }
    payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        fail(f"refusing to overwrite {output}")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
