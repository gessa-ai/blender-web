#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Create a deterministic release archive bound to exact tagged APPLY bytes.

The staged public assembler remains the only producer of hostable files.  This
tool reads that tree, proves it derives from a successful APPLY build, and wraps
it without changing a byte.  CAPTURE and OFF generations are deliberately not
packageable.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://github.com/gessa-ai/blender-web"
TAG_RE = re.compile(
    r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:dev|rc)(?:\.[0-9]+)?)?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PIN_RE = re.compile(
    r"^(?P<commit>[0-9a-f]{12}) (?P<branch>[^ ]+) \((?P<label>Blender [^)]+)\)\n$"
)


class ReleaseError(RuntimeError):
    """A release boundary is absent, ambiguous, or stale."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, int | str]:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise ReleaseError(f"release artifact is unreadable: {path}: {error}") from error
    if path.is_symlink() or not stat.S_ISREG(mode):
        raise ReleaseError(f"release artifact is not an exact regular file: {path}")
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def canonical_artifact_digest(artifacts: dict[str, dict[str, int | str]]) -> str:
    digest = hashlib.sha256()
    for name in sorted(artifacts):
        row = artifacts[name]
        digest.update(f"{name}\0{row['bytes']}\0{row['sha256']}\n".encode())
    return digest.hexdigest()


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repo, capture_output=True, text=True
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ReleaseError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.strip()


def resolve_tagged_source(repo: Path, tag: str) -> dict[str, int | str]:
    """Require one annotated semver tag at a completely clean current HEAD."""
    repo = repo.resolve(strict=True)
    if TAG_RE.fullmatch(tag) is None:
        raise ReleaseError(f"unsafe release tag: {tag!r}")
    ref = f"refs/tags/{tag}"
    if _git(repo, "cat-file", "-t", ref) != "tag":
        raise ReleaseError(f"release tag must be annotated: {tag}")
    tag_object = _git(repo, "rev-parse", "--verify", ref)
    commit = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    head = _git(repo, "rev-parse", "--verify", "HEAD")
    if commit != head:
        raise ReleaseError(f"release tag {tag} does not point to HEAD ({commit} != {head})")
    status_result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "-z"],
        cwd=repo,
        capture_output=True,
    )
    if status_result.returncode != 0:
        raise ReleaseError("cannot inspect release source worktree")
    if status_result.stdout:
        rows = [row for row in status_result.stdout.split(b"\0") if row]
        sample = ", ".join(
            row.decode("utf-8", errors="backslashreplace") for row in rows[:5]
        )
        raise ReleaseError(f"release source worktree is not clean: {sample}")
    tree = _git(repo, "rev-parse", "--verify", f"{commit}^{{tree}}")
    epoch_text = _git(repo, "show", "-s", "--format=%ct", commit)
    try:
        epoch = int(epoch_text)
    except ValueError as error:
        raise ReleaseError(f"invalid tagged commit epoch: {epoch_text!r}") from error
    if epoch < 0:
        raise ReleaseError("tagged commit epoch is negative")
    return {
        "tag": tag,
        "tag_object": tag_object,
        "commit": commit,
        "tree": tree,
        "commit_epoch": epoch,
    }


def _safe_bundle_name(name: str) -> bool:
    if not name or "\\" in name or "\0" in name or name.startswith("/"):
        return False
    path = PurePosixPath(name)
    return str(path) == name and all(part not in {"", ".", ".."} for part in path.parts)


def collect_exact_bundle(
    bundle: Path, expected_names: Iterable[str]
) -> tuple[dict[str, dict[str, int | str]], str]:
    """Reject every extra, missing, linked, escaping, or non-regular entry."""
    bundle = bundle.resolve(strict=True)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ReleaseError(f"bundle root is not an exact directory: {bundle}")
    names = tuple(expected_names)
    if len(names) != len(set(names)) or any(not _safe_bundle_name(name) for name in names):
        raise ReleaseError("expected bundle inventory is duplicate or unsafe")
    actual: set[str] = set()
    for path in bundle.rglob("*"):
        relative = path.relative_to(bundle).as_posix()
        mode = path.lstat().st_mode
        if path.is_symlink():
            raise ReleaseError(f"bundle contains a symlink: {relative}")
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ReleaseError(f"bundle contains an unsupported entry: {relative}")
        actual.add(relative)
    expected = set(names)
    if actual != expected:
        raise ReleaseError(
            "bundle tree mismatch: "
            f"missing={sorted(expected - actual)!r} extra={sorted(actual - expected)!r}"
        )
    artifacts = {name: identity(bundle / name) for name in names}
    return artifacts, canonical_artifact_digest(artifacts)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReleaseError(f"cannot load release verifier: {path}")
    module = importlib.util.module_from_spec(spec)
    old_path = list(sys.path)
    try:
        sys.path.insert(0, str(path.parent))
        spec.loader.exec_module(module)
    except Exception as error:
        raise ReleaseError(f"cannot load release verifier {path}: {error}") from error
    finally:
        sys.path[:] = old_path
    return module


def load_apply_contract(build_bin: Path) -> dict[str, Any]:
    """Reuse the M8 inventory authority and its stricter product preflight."""
    build_bin = build_bin.resolve(strict=True)
    verifier = _load_module(
        "bw_release_verify_m8", ROOT / "sandbox/m8-launch-gate/verify_m8.py"
    )
    try:
        contract = verifier.artifact_contract(build_bin)
    except Exception as error:
        raise ReleaseError(str(error)) from error
    preflight = _load_module(
        "bw_release_windowed_preflight", ROOT / "scripts/windowed-product-preflight.py"
    )
    try:
        preflight.validate(build_bin.parent, "apply")
    except Exception as error:
        raise ReleaseError(str(error)) from error
    return contract


def verify_stage_provenance(
    build_bin: Path, bundle: Path, contract: dict[str, Any]
) -> dict[str, object]:
    module = _load_module(
        "bw_release_stage_provenance",
        ROOT / "sandbox/m8-staged-deploy/stage_provenance.py",
    )
    proof, failures = module.verify_full(
        ROOT,
        build_bin,
        bundle,
        contract["shipped_wasm"],
        contract["public_split_manifest"],
    )
    if failures:
        raise ReleaseError("public bundle provenance failed: " + "; ".join(failures[:8]))
    proof_bytes = canonical_json(proof)
    return {
        "contract": "m8-stage-provenance-v1",
        "full_stage": True,
        "sha256": sha256_bytes(proof_bytes),
    }


def _tar_info(name: str, *, size: int, mode: int, epoch: int, directory: bool) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = mode
    info.mtime = epoch
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    if directory:
        info.type = tarfile.DIRTYPE
    return info


def write_release_archive(
    bundle: Path,
    names: Iterable[str],
    metadata: dict[str, object],
    output: Path,
    epoch: int,
    prefix: str,
) -> None:
    """Write normalized USTAR+gzip bytes without overwriting an existing file."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", prefix):
        raise ReleaseError(f"unsafe release archive prefix: {prefix!r}")
    output = output.resolve(strict=False)
    if output.exists() or output.is_symlink():
        raise ReleaseError(f"release archive already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    bundle = bundle.resolve(strict=True)
    names = tuple(names)
    metadata_bytes = canonical_json(metadata)
    entries: dict[str, tuple[str, Path | bytes | None]] = {prefix: ("dir", None)}
    for relative in (*names, "release.json"):
        if not _safe_bundle_name(relative):
            raise ReleaseError(f"unsafe archive member: {relative!r}")
        parts = PurePosixPath(relative).parts
        for depth in range(1, len(parts)):
            directory = f"{prefix}/{'/'.join(parts[:depth])}"
            entries[directory] = ("dir", None)
    entries[f"{prefix}/release.json"] = ("bytes", metadata_bytes)
    for relative in names:
        entries[f"{prefix}/{relative}"] = ("file", bundle / relative)
    created = False
    try:
        with output.open("xb") as raw:
            created = True
            with gzip.GzipFile(filename="", mode="wb", compresslevel=9, mtime=0, fileobj=raw) as zipped:
                with tarfile.open(fileobj=zipped, mode="w|", format=tarfile.USTAR_FORMAT) as archive:
                    for member_name in sorted(entries):
                        kind, payload = entries[member_name]
                        if kind == "dir":
                            archive.addfile(
                                _tar_info(member_name, size=0, mode=0o755, epoch=epoch, directory=True)
                            )
                        elif kind == "bytes":
                            assert isinstance(payload, bytes)
                            archive.addfile(
                                _tar_info(
                                    member_name,
                                    size=len(payload),
                                    mode=0o644,
                                    epoch=epoch,
                                    directory=False,
                                ),
                                io.BytesIO(payload),
                            )
                        else:
                            assert isinstance(payload, Path)
                            row = identity(payload)
                            with payload.open("rb") as stream:
                                archive.addfile(
                                    _tar_info(
                                        member_name,
                                        size=int(row["bytes"]),
                                        mode=0o644,
                                        epoch=epoch,
                                        directory=False,
                                    ),
                                    stream,
                                )
    except Exception:
        if created:
            try:
                output.unlink()
            except OSError:
                pass
        raise


def write_json_exclusive(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise ReleaseError(f"release receipt already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical_json(value))


def upstream_pin() -> dict[str, str]:
    data = (ROOT / "oracle/PIN").read_text(encoding="utf-8")
    match = PIN_RE.fullmatch(data)
    if match is None:
        raise ReleaseError("pinned upstream identity is malformed")
    return match.groupdict()


def sanitized_build_receipt(build_bin: Path, contract: dict[str, Any]) -> dict[str, object]:
    manifest = contract["manifest"]
    profile = manifest.get("profile_receipt")
    if not isinstance(profile, dict):
        raise ReleaseError("APPLY manifest profile receipt is absent")
    profile_receipt = {
        key: profile[key]
        for key in ("schema", "status", "bytes", "sha256", "captured_original")
        if key in profile
    }
    source_captures = profile.get("source_capture_receipts")
    if isinstance(source_captures, list):
        profile_receipt["source_capture_receipts"] = [
            {key: row[key] for key in ("bytes", "sha256") if key in row}
            for row in source_captures
            if isinstance(row, dict)
        ]
    inventory = [
        {
            key: row[key]
            for key in (
                "filename", "role", "bytes", "sha256", "shipped", "critical", "request_phase"
            )
        }
        for row in contract["inventory"]
    ]
    return {
        "mode": "apply",
        "contract": manifest["contract"],
        "split_manifest": identity(build_bin / "blender_browser.split-build.json"),
        "javascript": identity(build_bin / "blender_browser.js"),
        "data": identity(build_bin / "blender_browser.data"),
        "profile_receipt": profile_receipt,
        "wasm_inventory": inventory,
    }


def make_metadata(
    tag: str,
    source: dict[str, int | str],
    build: dict[str, object],
    artifacts: dict[str, dict[str, int | str]],
    bundle_digest: str,
    provenance: dict[str, object],
    prefix: str,
) -> dict[str, object]:
    if SHA256_RE.fullmatch(bundle_digest) is None:
        raise ReleaseError("bundle digest is invalid")
    return {
        "schema": 1,
        "contract": "blender-web.tagged-release.v1",
        "status": "PASS",
        "release": {
            "tag": tag,
            "archive_prefix": prefix,
            "source_url": SOURCE_URL,
            "source": source,
            "upstream": upstream_pin(),
        },
        "build": build,
        "bundle": {
            "artifact_count": len(artifacts),
            "bytes": sum(int(row["bytes"]) for row in artifacts.values()),
            "sha256": bundle_digest,
            "artifacts": artifacts,
        },
        "provenance": provenance,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument(
        "--build-bin", type=Path, default=ROOT / "build-wasm-windowed-opt/bin"
    )
    parser.add_argument(
        "--bundle", type=Path, default=ROOT / "sandbox/m8-staged-deploy/bundle-staged"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if not args.check_only and args.output is None:
        parser.error("--output is required unless --check-only is used")

    source = resolve_tagged_source(ROOT, args.tag)
    build_bin = args.build_bin.resolve(strict=True)
    bundle = args.bundle.resolve(strict=True)
    contract = load_apply_contract(build_bin)
    artifacts, bundle_digest = collect_exact_bundle(bundle, contract["bundle_files"])
    provenance = verify_stage_provenance(build_bin, bundle, contract)
    prefix = f"blender-web-{args.tag}"
    metadata = make_metadata(
        args.tag,
        source,
        sanitized_build_receipt(build_bin, contract),
        artifacts,
        bundle_digest,
        provenance,
        prefix,
    )
    if args.check_only:
        print(
            "BW_TAGGED_RELEASE_CHECK_PASS "
            f"tag={args.tag} commit={source['commit']} artifacts={len(artifacts)} "
            f"bundle_sha256={bundle_digest}"
        )
        return 0

    output = args.output.resolve(strict=False)
    receipt = (
        args.receipt.resolve(strict=False)
        if args.receipt is not None
        else output.with_name(output.name + ".json")
    )
    if output == receipt:
        raise ReleaseError("release archive and receipt paths must differ")
    if output == bundle or bundle in output.parents or receipt == bundle or bundle in receipt.parents:
        raise ReleaseError("release outputs must not be created inside the staged bundle")
    if receipt.exists() or receipt.is_symlink():
        raise ReleaseError(f"release receipt already exists: {receipt}")
    write_release_archive(
        bundle,
        contract["bundle_files"],
        metadata,
        output,
        int(source["commit_epoch"]),
        prefix,
    )
    archive = identity(output)
    sidecar = dict(metadata)
    sidecar["metadata_sha256"] = sha256_bytes(canonical_json(metadata))
    sidecar["archive"] = {"filename": output.name, **archive}
    try:
        write_json_exclusive(receipt, sidecar)
    except Exception:
        try:
            output.unlink()
        except OSError:
            pass
        raise
    print(
        "BW_TAGGED_RELEASE_PACKAGE_PASS "
        f"tag={args.tag} commit={source['commit']} artifacts={len(artifacts)} "
        f"archive_bytes={archive['bytes']} archive_sha256={archive['sha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseError as error:
        print(f"BW_TAGGED_RELEASE_FAIL {error}", file=sys.stderr)
        raise SystemExit(2) from error
