#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fail-first contract for deterministic, source-bound release archives."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[2]
PACKAGER = ROOT / "scripts/package-tagged-release.py"


def run(*arguments: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        list(arguments), cwd=cwd, env=env, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def load_packager():
    spec = importlib.util.spec_from_file_location("bw_package_tagged_release", PACKAGER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load tagged release packager: {PACKAGER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expect_error(function, text: str) -> None:
    try:
        function()
    except Exception as error:  # contract checks the packager's public failure text
        if text not in str(error):
            raise AssertionError(f"expected {text!r}, got {error!r}") from error
    else:
        raise AssertionError(f"expected failure containing {text!r}")


def commit(repo: Path, message: str, epoch: int) -> str:
    env = dict(os.environ)
    stamp = f"@{epoch} +0000"
    env.update({"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
    run("git", "add", "-A", cwd=repo, env=env)
    run("git", "commit", "-m", message, cwd=repo, env=env)
    return run("git", "rev-parse", "HEAD", cwd=repo)


def main() -> int:
    packager = load_packager()
    freeze_source = (
        ROOT / "sandbox/final-source-freeze/freeze_release.py"
    ).read_text(encoding="utf-8")
    assert freeze_source.count('"scripts/package-tagged-release.py",') == 1
    assert freeze_source.count('"sandbox/m8-tagged-release/verify.py",') == 1
    canonical = packager.verify_canonical_source()
    assert canonical["verdict"] == "PASS"
    assert canonical["upstream_commit"].startswith("fbe6228777e7")
    negatives = 0
    with tempfile.TemporaryDirectory(prefix="bw-tagged-release-contract-") as temporary:
        work = Path(temporary)
        repo = work / "repo"
        repo.mkdir()
        run("git", "init", "-q", cwd=repo)
        run("git", "config", "user.name", "Release Contract", cwd=repo)
        run("git", "config", "user.email", "release@example.invalid", cwd=repo)
        (repo / "source.txt").write_text("source-v1\n", encoding="utf-8")
        epoch = 1_787_778_796
        tagged_commit = commit(repo, "release source", epoch)
        tag_env = dict(os.environ)
        tag_env["GIT_COMMITTER_DATE"] = f"@{epoch} +0000"
        run("git", "tag", "-a", "v0.1.1", "-m", "v0.1.1", cwd=repo, env=tag_env)

        source = packager.resolve_tagged_source(repo, "v0.1.1")
        assert source["commit"] == tagged_commit
        assert source["commit_epoch"] == epoch
        assert source["tree"] == run("git", "rev-parse", "HEAD^{tree}", cwd=repo)
        assert len(source["tag_object"]) == 40

        expect_error(lambda: packager.resolve_tagged_source(repo, "release/latest"),
                     "unsafe release tag")
        negatives += 1
        run("git", "tag", "v0.1.2", cwd=repo)
        expect_error(lambda: packager.resolve_tagged_source(repo, "v0.1.2"),
                     "must be annotated")
        negatives += 1

        (repo / "source.txt").write_text("source-v2\n", encoding="utf-8")
        commit(repo, "post-tag drift", epoch + 1)
        expect_error(lambda: packager.resolve_tagged_source(repo, "v0.1.1"),
                     "does not point to HEAD")
        negatives += 1
        run("git", "reset", "--hard", tagged_commit, cwd=repo)

        (repo / "source.txt").write_text("dirty\n", encoding="utf-8")
        expect_error(lambda: packager.resolve_tagged_source(repo, "v0.1.1"),
                     "worktree is not clean")
        negatives += 1
        run("git", "reset", "--hard", "HEAD", cwd=repo)
        (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")
        expect_error(lambda: packager.resolve_tagged_source(repo, "v0.1.1"),
                     "worktree is not clean")
        negatives += 1
        (repo / "untracked.txt").unlink()

        bundle = work / "bundle"
        (bundle / "bin").mkdir(parents=True)
        (bundle / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
        (bundle / "bin/app.wasm").write_bytes(b"\0asm-release")
        names = ("index.html", "bin/app.wasm")
        identities, bundle_digest = packager.collect_exact_bundle(bundle, names)
        assert list(identities) == list(names)
        assert len(bundle_digest) == 64

        (bundle / "extra").write_text("no\n", encoding="utf-8")
        expect_error(lambda: packager.collect_exact_bundle(bundle, names),
                     "bundle tree mismatch")
        negatives += 1
        (bundle / "extra").unlink()
        (bundle / "bin/app.wasm").unlink()
        expect_error(lambda: packager.collect_exact_bundle(bundle, names),
                     "bundle tree mismatch")
        negatives += 1
        (bundle / "bin/app.wasm").write_bytes(b"\0asm-release")
        (bundle / "link").symlink_to("index.html")
        expect_error(lambda: packager.collect_exact_bundle(bundle, (*names, "link")),
                     "symlink")
        negatives += 1
        (bundle / "link").unlink()

        metadata = {
            "schema": 1,
            "contract": "blender-web.tagged-release.v1",
            "status": "PASS",
            "release": {"tag": "v0.1.1", "source": source},
            "bundle": {"artifacts": identities, "sha256": bundle_digest},
        }
        first = work / "first.tar.gz"
        second = work / "second.tar.gz"
        packager.write_release_archive(bundle, names, metadata, first, epoch, "blender-web-v0.1.1")
        packager.write_release_archive(bundle, names, metadata, second, epoch, "blender-web-v0.1.1")
        assert first.read_bytes() == second.read_bytes()
        assert sha256(first) == sha256(second)

        with gzip.open(first, "rb") as compressed:
            with tarfile.open(fileobj=compressed, mode="r:") as archive:
                members = archive.getmembers()
                member_names = [member.name for member in members]
                assert member_names == sorted(member_names)
                assert all(member.uid == 0 and member.gid == 0 for member in members)
                assert all(member.uname == "" and member.gname == "" for member in members)
                assert all(member.mtime == epoch for member in members)
                assert all(member.mode == (0o755 if member.isdir() else 0o644)
                           for member in members)
                embedded = archive.extractfile("blender-web-v0.1.1/release.json")
                assert embedded is not None
                assert json.loads(embedded.read()) == metadata

        existing = work / "existing.tar.gz"
        existing.write_bytes(b"preserve")
        expect_error(
            lambda: packager.write_release_archive(
                bundle, names, metadata, existing, epoch, "blender-web-v0.1.1"
            ),
            "already exists",
        )
        assert existing.read_bytes() == b"preserve"
        negatives += 1

        current_capture = ROOT / "build-wasm-windowed-opt/bin"
        expect_error(lambda: packager.load_apply_contract(current_capture),
                     "only a successful APPLY inventory may ship")
        negatives += 1

        def rejected_replay(*_arguments, **_keywords):
            return subprocess.CompletedProcess([], 1, "", "canonical mutation")

        expect_error(lambda: packager.verify_canonical_source(rejected_replay),
                     "canonical source replay failed")
        negatives += 1

    assert negatives == 11
    print(
        "BW_TAGGED_RELEASE_CONTRACT_PASS positive=tag+canonical+tree+archive+embedded-receipt+freeze "
        f"negative={negatives} deterministic=2 capture_rejected=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
