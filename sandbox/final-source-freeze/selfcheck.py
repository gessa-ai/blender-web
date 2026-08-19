#!/usr/bin/env python3
"""Hermetic fixture self-check for freeze.py; never reads the Blender source tree."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import importlib.util


HERE = Path(__file__).resolve().parent
FREEZE = HERE / "freeze.py"
SPEC = importlib.util.spec_from_file_location("source_freeze", FREEZE)
assert SPEC and SPEC.loader
freeze_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze_module)


def command(args: list[str], *, cwd: Path | None = None, expect: int = 0) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != expect:
        raise AssertionError(
            f"unexpected exit {completed.returncode}, wanted {expect}: {' '.join(args)}\n"
            + completed.stdout.decode("utf-8", "replace")
            + completed.stderr.decode("utf-8", "replace")
        )
    return completed


def git(repo: Path, *args: str) -> bytes:
    return command(["git", "-C", os.fspath(repo), *args]).stdout


def write(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(repo: Path, pin: str, pin_file: Path, output: Path, expect: int = 0) -> subprocess.CompletedProcess[bytes]:
    return command(
        [
            sys.executable,
            os.fspath(FREEZE),
            "--source",
            os.fspath(repo),
            "--expected-pin",
            pin,
            "--pin-file",
            os.fspath(pin_file),
            "--output-dir",
            os.fspath(output),
        ],
        expect=expect,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="source-freeze-selfcheck-") as temp_name:
        root = Path(temp_name)
        repo = root / "fixture"
        repo.mkdir()
        git(repo, "init", "--quiet")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.invalid")

        write(repo / "modify.txt", b"before\n")
        write(repo / "delete.txt", b"remove me\n")
        write(repo / "mode.txt", b"mode change\n")
        write(repo / "binary.bin", b"\x00old\xffpayload\x00")
        git(repo, "add", "-A")
        git(repo, "commit", "--quiet", "-m", "fixture pin")
        pin = git(repo, "rev-parse", "HEAD").decode("ascii").strip()
        pin_file = root / "PIN"
        pin_file.write_text(f"{pin[:12]} fixture\n", encoding="utf-8")

        # A historical file outside both source and output must remain untouched.
        historical = root / "historical-patches" / "0001-old.patch"
        write(historical, b"historical patch: preserve exactly\n")
        historical_before = sha256(historical)

        write(repo / "modify.txt", b"after\n")
        (repo / "delete.txt").unlink()
        (repo / "mode.txt").chmod(0o755)
        write(repo / "binary.bin", b"\x00new\xfepayload\x00with more bytes\xff")
        write(repo / "new executable.sh", b"#!/bin/sh\nexit 0\n", 0o755)
        os.symlink("modify.txt", repo / "new-link")

        output = root / "freeze-output"
        invoke(repo, pin, pin_file, output)

        expected_files = {
            "canonical-source.patch",
            "live.manifest.jsonl",
            "replay.manifest.jsonl",
            "receipt.json",
        }
        assert {path.name for path in output.iterdir()} == expected_files
        assert sha256(historical) == historical_before
        patch = (output / "canonical-source.patch").read_bytes()
        assert b"GIT binary patch" in patch
        assert b"deleted file mode 100644" in patch
        assert b"new file mode 100755" in patch
        assert b"old mode 100644\nnew mode 100755" in patch
        assert b"new file mode 120000" in patch
        live_manifest = (output / "live.manifest.jsonl").read_bytes()
        assert live_manifest == (output / "replay.manifest.jsonl").read_bytes()
        records = [json.loads(line) for line in live_manifest.splitlines()]
        by_path = {record["path"]: record for record in records}
        assert "delete.txt" not in by_path
        assert by_path["mode.txt"]["mode"] == "100755"
        assert by_path["new%20executable.sh"]["mode"] == "100755"
        assert by_path["new-link"]["mode"] == "120000"
        assert by_path["binary.bin"]["size"] == len(b"\x00new\xfepayload\x00with more bytes\xff")
        receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
        assert receipt["verdict"] == "PASS"
        assert receipt["patch"]["sha256"] == sha256(output / "canonical-source.patch")
        assert receipt["live_manifest"]["sha256"] == sha256(output / "live.manifest.jsonl")
        assert receipt["checks"]["manifest_replay_byte_exact"] is True
        receipt_before = sha256(output / "receipt.json")

        # Existing output is never overwritten.
        overwrite = invoke(repo, pin, pin_file, output, expect=1)
        assert b"refusing to overwrite" in overwrite.stderr
        assert sha256(output / "receipt.json") == receipt_before

        # A different valid full commit is rejected as an unexpected source HEAD.
        fixture_tree = git(repo, "write-tree").decode("ascii").strip()
        wrong_pin = git(repo, "commit-tree", fixture_tree, "-p", pin, "-m", "other pin").decode(
            "ascii"
        ).strip()
        wrong_output = root / "wrong-pin-output"
        wrong = invoke(repo, wrong_pin, pin_file, wrong_output, expect=1)
        assert b"unexpected source HEAD" in wrong.stderr
        assert not wrong_output.exists()

        # Staged/index dirt is rejected; worktree dirt is the intended snapshot.
        git(repo, "add", "modify.txt")
        dirty_output = root / "dirty-index-output"
        dirty = invoke(repo, pin, pin_file, dirty_output, expect=1)
        assert b"index is dirty" in dirty.stderr
        assert not dirty_output.exists()

        # A gitlink's empty directory is an ordinary uninitialized submodule.
        # Git commands run inside it must not walk up and classify the enclosing
        # repository as the child worktree.
        subrepo = root / "submodule-fixture"
        subrepo.mkdir()
        git(subrepo, "init", "--quiet")
        git(subrepo, "config", "user.name", "Fixture")
        git(subrepo, "config", "user.email", "fixture@example.invalid")
        write(subrepo / "payload", b"submodule\n")
        git(subrepo, "add", "-A")
        git(subrepo, "commit", "--quiet", "-m", "submodule pin")
        submodule_oid = git(subrepo, "rev-parse", "HEAD").decode("ascii").strip()

        parent = root / "submodule-parent"
        parent.mkdir()
        git(parent, "init", "--quiet")
        git(parent, "config", "user.name", "Fixture")
        git(parent, "config", "user.email", "fixture@example.invalid")
        write(parent / "tracked", b"parent\n")
        git(parent, "add", "-A")
        command([
            "git", "-C", os.fspath(parent), "update-index", "--add", "--cacheinfo",
            f"160000,{submodule_oid},lib/empty",
        ])
        git(parent, "commit", "--quiet", "-m", "parent with gitlink")
        empty_child = parent / "lib/empty"
        empty_child.mkdir(parents=True)
        freeze_module.require_clean_initialized_submodules(parent)
        write(empty_child / "not-a-repository", b"reject\n")
        try:
            freeze_module.require_clean_initialized_submodules(parent)
        except freeze_module.FreezeError as error:
            assert "not its own Git worktree" in str(error)
        else:
            raise AssertionError("populated non-repository gitlink directory was accepted")

        print(
            json.dumps(
                {
                    "verdict": "PASS",
                    "fixture_pin": pin,
                    "patch_sha256": receipt["patch"]["sha256"],
                    "manifest_sha256": receipt["live_manifest"]["sha256"],
                    "manifest_entries": receipt["live_manifest"]["entries"],
                    "negative_checks": [
                        "overwrite", "unexpected_pin", "dirty_index",
                        "populated_nonrepository_submodule",
                    ],
                    "empty_uninitialized_submodule": True,
                    "historical_patch_preserved": True,
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
