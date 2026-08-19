#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fail-closed structural checks for the reproducible M0 artifacts."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLENDER_COMMIT = "fbe6228777e7"
BLENDER_COMMIT_FULL = "fbe6228777e7d9afefcd61a413844e790ae75db7"
BLENDER_SHA256 = "96f6c181a30f4950607839dc84d42a354b250d8a0231b098b59b7bc69c351c48"
BLENDER_URL = (
    "https://download.blender.org/release/Blender5.2/"
    "blender-5.2.0-linux-x64.tar.xz"
)
UBUNTU_AMD64_DIGEST = (
    "sha256:019e8eb29a85e74d64925745884f2ec79aa27e3feab36353d24656f4d6b89467"
)
EMSDK_REPO_COMMIT = "1ab2e627b1a84567f5284d1baaa5f6be7ccf07de"
EMSCRIPTEN_RELEASE_COMMIT = "dbd755b5da399329c2576f6e3dfa7f419f5d8409"
EMCC_COMMIT = "1db513782be24469589d7cb8a1f1834e9a33f271"


def fail(message: str) -> None:
    print(f"M0_SELFCHECK_FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_text(path: Path, needles: list[str]) -> str:
    if not path.is_file():
        fail(f"missing {path.relative_to(ROOT)}")
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            fail(f"{path.relative_to(ROOT)} is missing exact text: {needle}")
    return text


pin_path = ROOT / "oracle/PIN"
pin = require_text(
    pin_path,
    [BLENDER_COMMIT, "blender-v5.2-release", "Blender 5.2 LTS"],
).splitlines()[0]
if not pin.startswith(f"{BLENDER_COMMIT} "):
    fail("oracle/PIN does not start with the exact Blender pin")

upstream_git = ROOT / "upstream/.git"
if upstream_git.exists():
    result = subprocess.run(
        ["git", "-C", str(ROOT / "upstream"), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != BLENDER_COMMIT_FULL:
        fail(f"upstream checkout drifted to {result.stdout.strip()}")

dockerfile = require_text(
    ROOT / "containers/oracle/Dockerfile",
    [
        f"FROM ubuntu:24.04@{UBUNTU_AMD64_DIGEST}",
        f"ARG BLENDER_COMMIT={BLENDER_COMMIT}",
        f"ARG BLENDER_URL={BLENDER_URL}",
        f"ARG BLENDER_SHA256={BLENDER_SHA256}",
        "ARG OIIO_TOOLS_VERSION=2.4.17.0+dfsg-1.1build4",
        '"openimageio-tools=${OIIO_TOOLS_VERSION}"',
        "sha256sum --check --strict -",
        'grep --fixed-strings --quiet "${BLENDER_COMMIT}"',
        "ENTRYPOINT [\"/opt/blender/blender\"]",
    ],
)
if "openimageio-tools " in dockerfile:
    fail("Dockerfile contains an unversioned openimageio-tools install")

require_text(
    ROOT / "scripts/oracle-container.sh",
    [
        'PLATFORM="linux/amd64"',
        'SOURCE_DATE_EPOCH="1783956011"',
        "--provenance=false",
        '--build-arg "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"',
        "--network none",
        'exec python3 "$ROOT/scripts/m0-selfcheck.py"',
        "M0_ORACLE_CONTAINER_OK",
    ],
)
require_text(
    ROOT / "scripts/ci/m0-basic.sh",
    [
        BLENDER_COMMIT_FULL,
        EMSDK_REPO_COMMIT,
        EMSCRIPTEN_RELEASE_COMMIT,
        EMCC_COMMIT,
        'ccache emcc -c "$tmpdir/hello.c"',
        '"$EMSDK_NODE" "$tmpdir/hello.js"',
        "cache_hits >= 1",
        "--use-port=emdawnwebgpu",
        "M0_BASIC_CI_OK",
    ],
)
require_text(
    ROOT / ".github/workflows/m0.yml",
    [
        "actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8",
        "actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830",
        "fsfe/reuse-action@676e2d560c9a403aa252096d99fcab3e1132b0f5",
        f"EMSDK_REPO_COMMIT: {EMSDK_REPO_COMMIT}",
        "EMSDK_VERSION: 6.0.5",
        "EM_CACHE:",
        "CCACHE_DIR:",
        "M0_VERIFY_UPSTREAM_FETCH=1 bash scripts/ci/m0-basic.sh",
    ],
)
require_text(
    ROOT / "sandbox/final-m0-m3/run_m0.py",
    [
        "reuse_evidence_selfcheck.py",
        "reuse-evidence-selfcheck.stdout",
        "REUSE evidence selfcheck failed",
    ],
)

for script in (
    ROOT / "scripts/oracle-container.sh",
    ROOT / "scripts/m0-oracle-receipt.py",
    ROOT / "scripts/ci/m0-basic.sh",
    ROOT / "sandbox/final-m0-m3/reuse_evidence_selfcheck.py",
):
    if not script.is_file():
        fail(f"missing {script.relative_to(ROOT)}")
    result = subprocess.run(
        (["python3", "-m", "py_compile", str(script)]
         if script.suffix == ".py" else ["bash", "-n", str(script)]),
        capture_output=True,
        text=True,
    )
    if result.returncode:
        fail(f"syntax {script.relative_to(ROOT)}: {result.stderr.strip()}")

if shutil.which("docker") is None:
    docker_detail = "docker CLI unavailable; static Dockerfile validation completed"
else:
    result = subprocess.run(
        ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    docker_detail = (
        "docker daemon available; run scripts/oracle-container.sh verify for execution"
        if result.returncode == 0
        else "docker daemon unavailable; static Dockerfile validation completed"
    )

print(f"M0_SELFCHECK_OK: {docker_detail}")
