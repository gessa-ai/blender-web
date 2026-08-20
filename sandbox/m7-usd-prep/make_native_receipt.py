#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Publish an immutable, source-frozen native USD capability receipt."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tempfile


SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parents[2]
BUILD = ROOT / "build-native-gpu"
OUT_ROOT = ROOT / "sandbox/m7-usd-prep/native-capability"
PRODUCER = ROOT / "sandbox/m7-usd-prep/make_native_receipt.py"
SELECTOR_SCHEMA = "blender-web.m7-usd-selector.v1"
RECEIPT_SCHEMA = "blender-web.m7-usd-native-capability.v2"
LABEL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
OBJECTS = {
    "usd_reader_shape.cc":
        "source/blender/io/usd/CMakeFiles/bf_io_usd.dir/intern/usd_reader_shape.cc.o",
    "usd_hook.cc": "source/blender/io/usd/CMakeFiles/bf_io_usd.dir/intern/usd_hook.cc.o",
}
REQUIRED_DEFINITIONS = {"WITH_USD", "WITH_USD_IMAGING", "WITH_USD_PYTHON_HOOKS"}


class ReceiptError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def real_file(path: Path, label: str) -> dict[str, object]:
    try:
        info = path.lstat()
    except OSError as error:
        raise ReceiptError(f"{label} is absent: {path}: {error}") from error
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or path.resolve(strict=True) != path:
        raise ReceiptError(f"{label} is not a canonical regular file: {path}")
    return {"path": str(path), "bytes": info.st_size, "sha256": sha256(path)}


def relative_identity(path: Path, label: str) -> dict[str, object]:
    value = real_file(path, label)
    value["path"] = str(path.relative_to(ROOT))
    return value


def source_freeze_path(value: str | None) -> Path:
    if not isinstance(value, str) or not value:
        raise ReceiptError("--source-freeze (or BW_SOURCE_FREEZE) is required")
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return Path(os.path.abspath(path))


def receipt_directory(root: Path, label: str) -> Path:
    if LABEL.fullmatch(label) is None:
        raise ReceiptError("a safe immutable label is required")
    root = Path(os.path.abspath(root))
    if root.resolve() != root:
        raise ReceiptError(f"native USD receipt root is indirect: {root}")
    try:
        relative = root.relative_to(ROOT)
    except ValueError as error:
        raise ReceiptError(f"native USD receipt root is outside the repository: {root}") from error
    if relative == Path("."):
        raise ReceiptError("native USD receipt root cannot be the repository root")
    output = root / label
    if output.parent != root or output.name != label:
        raise ReceiptError(f"unsafe native USD receipt directory: {output}")
    return output


def git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    value = result.stdout.strip()
    if result.returncode != 0 or re.fullmatch(r"[0-9a-f]{40,64}", value) is None:
        raise ReceiptError(f"cannot resolve source pin: {path}")
    return value


def cache_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        match = re.fullmatch(r"([^#/:][^:]*):[^=]+=(.*)", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def ninja_block(source: str, output: str) -> str:
    marker = f"build {output}:"
    lines = source.splitlines()
    matches = [index for index, line in enumerate(lines) if line.startswith(marker)]
    if len(matches) != 1:
        raise ReceiptError(f"Ninja output edge is absent/ambiguous: {output}")
    start = matches[0]
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].startswith("build ")), len(lines))
    return "\n".join(lines[start:end]).rstrip() + "\n"


def definitions(block: str) -> set[str]:
    matches = re.findall(r"(?m)^  DEFINES = (.*)$", block)
    if len(matches) != 1:
        raise ReceiptError("capability object has no exact Ninja DEFINES binding")
    return {token[2:] for token in matches[0].split() if token.startswith("-D")}


def analyze(build: Path) -> dict[str, object]:
    if build != BUILD or build.is_symlink() or not build.is_dir() or build.resolve() != build:
        raise ReceiptError(f"native USD build must be the canonical directory: {BUILD}")
    cache_path = build / "CMakeCache.txt"
    ninja_path = build / "build.ninja"
    archive_path = build / "lib/libbf_io_usd.a"
    cache = cache_values(cache_path)
    expected_cache = {
        "CMAKE_BUILD_TYPE": "Release", "WITH_USD": "ON", "WITH_PYTHON": "ON",
        "WITH_HYDRA": "OFF", "WITH_MATERIALX": "OFF",
    }
    if {key: cache.get(key) for key in expected_cache} != expected_cache:
        raise ReceiptError("native USD CMake capability profile is not exact")
    graph = ninja_path.read_text(encoding="utf-8", errors="strict")
    object_receipts: dict[str, dict[str, object]] = {}
    rule_hashes: dict[str, str] = {}
    for source_name, object_name in OBJECTS.items():
        block = ninja_block(graph, object_name)
        source_path = ROOT / "upstream/source/blender/io/usd/intern" / source_name
        if str(source_path) not in block or not REQUIRED_DEFINITIONS.issubset(definitions(block)):
            raise ReceiptError(f"native USD real capability rule is incomplete: {source_name}")
        object_receipts[source_name] = relative_identity(build / object_name,
                                                         f"{source_name} object")
        rule_hashes[source_name] = hashlib.sha256(block.encode()).hexdigest()
    archive_block = ninja_block(graph, "lib/libbf_io_usd.a")
    if not all(name in archive_block for name in OBJECTS.values()) or \
            "usd_hook_stub" in archive_block:
        raise ReceiptError("native USD archive does not use the exact real capability objects")
    archive_members_result = subprocess.run(
        ["ar", "-t", str(archive_path)], capture_output=True, text=True)
    archive_members = archive_members_result.stdout.splitlines()
    required_members = {Path(value).name for value in OBJECTS.values()}
    if archive_members_result.returncode != 0 or \
            any(archive_members.count(name) != 1 for name in required_members) or \
            any("usd_hook_stub" in name for name in archive_members):
        raise ReceiptError("native USD archive member inventory is not exact")
    member_receipts: dict[str, dict[str, object]] = {}
    for source_name, object_name in OBJECTS.items():
        member_name = Path(object_name).name
        extracted = subprocess.run(
            ["ar", "-p", str(archive_path), member_name], capture_output=True)
        expected_object = build / object_name
        if extracted.returncode != 0 or extracted.stdout != expected_object.read_bytes():
            raise ReceiptError(f"native USD archive member bytes differ: {member_name}")
        member_receipts[source_name] = {
            "name": member_name, "bytes": len(extracted.stdout),
            "sha256": hashlib.sha256(extracted.stdout).hexdigest(),
        }
    return {
        "configuration": {
            "buildType": "Release", "withUsd": True, "withPython": True,
            "withHydra": False, "withMaterialx": False,
            "definitions": sorted(REQUIRED_DEFINITIONS),
        },
        "cache": relative_identity(cache_path, "native USD CMake cache"),
        "graph": relative_identity(ninja_path, "native USD Ninja graph"),
        "archive": relative_identity(archive_path, "native USD archive"),
        "archiveMembers": member_receipts,
        "capabilityObjects": object_receipts,
        "capabilityRuleSha256": rule_hashes,
        "archiveInputs": {
            "required": list(OBJECTS.values()), "stubObjectAbsent": True,
            "edgeSha256": hashlib.sha256(archive_block.encode()).hexdigest(),
        },
    }


def ensure_no_selector(root: Path, *, create: bool = False) -> None:
    receipt_directory(root, "validation")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    elif not root.exists():
        return
    if root.is_symlink() or root.resolve() != root:
        raise ReceiptError(f"USD receipt root is indirect: {root}")
    selectors = []
    for child in root.iterdir():
        if child.is_symlink():
            raise ReceiptError(f"indirect entry in USD receipt root: {child}")
        if child.is_dir() and (child / "selector.json").exists():
            selectors.append(child / "selector.json")
    if selectors:
        raise ReceiptError("an immutable native USD selector already exists: " +
                           ", ".join(map(str, selectors)))


def exclusive_json(path: Path, value: object) -> bytes:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise ReceiptError(f"short write publishing immutable JSON: {path}")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return payload


def producer_selfcheck() -> None:
    positive = 0
    negative = 0
    if SCRIPT_PATH != PRODUCER or not (ROOT / "GOAL.md").is_file():
        raise ReceiptError("repository root is not derived from the producer path")
    positive += 1
    if receipt_directory(OUT_ROOT, "selfcheck") != OUT_ROOT / "selfcheck":
        raise ReceiptError("safe native USD output path differs")
    positive += 1
    if source_freeze_path("sandbox/freeze.json") != ROOT / "sandbox/freeze.json":
        raise ReceiptError("relative source-freeze path is not repository-rooted")
    positive += 1
    fixture = """build obj/a.o: CXX /source/a.cc\n  DEFINES = -DWITH_USD -DWITH_USD_IMAGING -DWITH_USD_PYTHON_HOOKS\n\nbuild lib/a.a: LINK obj/a.o\n"""
    assert "WITH_USD_IMAGING" in definitions(ninja_block(fixture, "obj/a.o"))
    assert ninja_block(fixture, "lib/a.a").startswith("build lib/a.a:")
    positive += 2
    for mutated in (fixture.replace("-DWITH_USD_IMAGING ", ""),
                    fixture + "\nbuild obj/a.o: CXX /other/a.cc\n"):
        try:
            block = ninja_block(mutated, "obj/a.o")
            if not REQUIRED_DEFINITIONS.issubset(definitions(block)):
                raise ReceiptError("missing definition")
        except ReceiptError:
            negative += 1
    for root, label in ((ROOT, "root-child"), (OUT_ROOT, "../escape"),
                        (ROOT.parent / "outside", "escape")):
        try:
            receipt_directory(root, label)
        except ReceiptError:
            negative += 1
    try:
        source_freeze_path(None)
    except ReceiptError:
        negative += 1
    with tempfile.TemporaryDirectory(
            prefix=".m7-usd-native-selector-", dir=OUT_ROOT.parent) as temporary:
        root = Path(temporary).resolve()
        ensure_no_selector(root)
        label = root / "label"
        label.mkdir()
        exclusive_json(label / "receipt.json", {"verdict": "PASS"})
        exclusive_json(label / "selector.json", {"schema": SELECTOR_SCHEMA})
        try:
            ensure_no_selector(root)
        except ReceiptError:
            negative += 1
    if positive != 5 or negative != 7:
        raise ReceiptError(
            f"native USD producer self-check count differs: positive={positive} negative={negative}")
    print(f"M7_USD_NATIVE_RECEIPT_SELFCHECK_PASS positive={positive} negative={negative} "
          f"root={ROOT}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label", nargs="?")
    parser.add_argument("--source-freeze", default=os.environ.get("BW_SOURCE_FREEZE"))
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        producer_selfcheck()
        return 0
    if not isinstance(args.label, str) or LABEL.fullmatch(args.label) is None:
        parser.error("a safe immutable label is required")
    try:
        source_freeze = source_freeze_path(args.source_freeze)
        output = receipt_directory(OUT_ROOT, args.label)
    except ReceiptError as error:
        parser.error(str(error))
    ensure_no_selector(OUT_ROOT)
    facts = analyze(BUILD)
    freeze = real_file(source_freeze, "canonical source freeze")
    dry = subprocess.run(
        [str(ROOT / "scripts/ninja-locked.sh"), "-C", str(BUILD), "-n", "bf_io_usd"],
        cwd=ROOT, capture_output=True, text=True)
    dry_text = (dry.stdout + dry.stderr).strip()
    if dry.returncode != 0 or "ninja: no work to do." not in dry_text or \
            "Re-running CMake" in dry_text or re.search(r"\[[0-9]+/[0-9]+\]", dry_text):
        raise ReceiptError("locked native bf_io_usd graph is not at a no-work fixed point: " + dry_text)
    start = json.dumps(facts, sort_keys=True)
    if json.dumps(analyze(BUILD), sort_keys=True) != start or real_file(
            source_freeze, "canonical source freeze") != freeze:
        raise ReceiptError("native USD inputs changed during receipt composition")
    ninja_version = subprocess.run(
        ["ninja", "--version"], check=True, capture_output=True, text=True).stdout.strip()
    receipt = {
        "schema": RECEIPT_SCHEMA, "verdict": "PASS", "label": args.label,
        "createdUtc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "producer": relative_identity(PRODUCER, "native USD receipt producer"),
        "sourceFreeze": freeze,
        "source": {"projectHead": git_head(ROOT), "upstreamHead": git_head(ROOT / "upstream")},
        "target": "bf_io_usd", "buildDirectory": str(BUILD),
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "ninja": {"version": ninja_version, "lockedDryRun": "no work to do"},
        **facts,
    }
    ensure_no_selector(OUT_ROOT, create=True)
    try:
        output.mkdir()
    except FileExistsError as error:
        raise ReceiptError(f"native USD receipt label already exists: {output}") from error
    receipt_payload = exclusive_json(output / "receipt.json", receipt)
    selector = {
        "schema": SELECTOR_SCHEMA, "kind": "native", "label": args.label,
        "receipt": {"path": "receipt.json", "bytes": len(receipt_payload),
                    "sha256": hashlib.sha256(receipt_payload).hexdigest()},
    }
    exclusive_json(output / "selector.json", selector)
    print(f"M7_USD_NATIVE_RECEIPT_PASS {output / 'receipt.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
