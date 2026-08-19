#!/usr/bin/env python3
"""Create and independently replay a canonical source-freeze Git patch.

The source repository's real index and object database are never mutated.  A
temporary index whose object writes are redirected to a temporary object store
captures tracked changes and non-ignored untracked files from the worktree.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable
from urllib.parse import quote_from_bytes


class FreezeError(RuntimeError):
    """A fail-closed validation error."""


def run_git(
    repo: Path,
    args: Iterable[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    command = ["git", "-C", os.fspath(repo), *args]
    completed = subprocess.run(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise FreezeError(
            f"command failed ({completed.returncode}): {' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return completed


def git_stdout(
    repo: Path, args: Iterable[str], *, env: dict[str, str] | None = None
) -> bytes:
    return run_git(repo, args, env=env).stdout


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ignored_path_list(source: Path) -> bytes:
    raw = git_stdout(
        source, ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"]
    )
    paths = sorted(path for path in raw.split(b"\0") if path)
    return b"\0".join(paths) + (b"\0" if paths else b"")


def require_exact_pin(source: Path, expected_pin: str, pin_file: Path | None) -> str:
    if not re.fullmatch(r"[0-9a-f]{40,64}", expected_pin):
        raise FreezeError("--expected-pin must be a full lowercase Git object ID")

    resolved = git_stdout(
        source, ["rev-parse", "--verify", f"{expected_pin}^{{commit}}"]
    ).decode("ascii").strip()
    if resolved != expected_pin:
        raise FreezeError(
            f"expected pin did not resolve exactly: expected {expected_pin}, got {resolved}"
        )

    head = git_stdout(source, ["rev-parse", "HEAD"]).decode("ascii").strip()
    if head != expected_pin:
        raise FreezeError(f"unexpected source HEAD: expected {expected_pin}, got {head}")

    if pin_file is not None:
        if not pin_file.is_file():
            raise FreezeError(f"pin file is missing or not a file: {pin_file}")
        tokens = pin_file.read_text(encoding="utf-8").split()
        if not tokens or not re.fullmatch(r"[0-9a-f]{7,64}", tokens[0]):
            raise FreezeError(f"pin file has no valid leading Git object ID: {pin_file}")
        recorded = tokens[0]
        if not expected_pin.startswith(recorded):
            raise FreezeError(
                f"pin-file mismatch: {recorded} is not a prefix of {expected_pin}"
            )
    return head


def require_pristine_real_index(source: Path, pin: str) -> None:
    unmerged = git_stdout(source, ["ls-files", "--unmerged", "-z"])
    if unmerged:
        raise FreezeError("source index contains unmerged entries")

    index_diff = run_git(source, ["diff", "--cached", "--quiet", pin, "--"], check=False)
    if index_diff.returncode == 1:
        raise FreezeError(
            "source index is dirty; commit/unstage it so the real index exactly matches the pin"
        )
    if index_diff.returncode != 0:
        detail = index_diff.stderr.decode("utf-8", "replace").strip()
        raise FreezeError(f"could not validate source index: {detail}")

    # `git diff --cached` can have version-dependent treatment of intent-to-add
    # entries.  Compare every stage-zero path/mode/object directly as well.
    pinned_tree_raw = git_stdout(source, ["ls-tree", "-r", "-z", "--full-tree", pin])
    pinned_entries: list[tuple[bytes, str, str]] = []
    for item in pinned_tree_raw.split(b"\0"):
        if not item:
            continue
        try:
            header, path = item.split(b"\t", 1)
            mode_b, object_type, oid_b = header.split(b" ", 2)
        except ValueError as exc:
            raise FreezeError("could not parse a pinned tree entry") from exc
        if object_type not in {b"blob", b"commit"}:
            raise FreezeError(f"unexpected pinned tree object type: {object_type!r}")
        pinned_entries.append((path, mode_b.decode("ascii"), oid_b.decode("ascii")))
    pinned_entries.sort(key=lambda item: item[0])
    if index_entries(source) != pinned_entries:
        raise FreezeError(
            "source index path/mode/object entries do not exactly match the pinned tree"
        )

    git_dir_raw = git_stdout(source, ["rev-parse", "--absolute-git-dir"])
    git_dir = Path(os.fsdecode(git_dir_raw.strip())).resolve()
    in_progress = [
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "REBASE_HEAD",
        "BISECT_LOG",
        "index.lock",
        "rebase-apply",
        "rebase-merge",
    ]
    present = [name for name in in_progress if (git_dir / name).exists()]
    if present:
        raise FreezeError("source repository operation is in progress: " + ", ".join(present))

    sparse = run_git(source, ["config", "--bool", "core.sparseCheckout"], check=False)
    if sparse.returncode == 0 and sparse.stdout.strip() == b"true":
        raise FreezeError("sparse checkouts are not accepted for a canonical source freeze")
    if sparse.returncode not in (0, 1):
        raise FreezeError("could not determine sparse-checkout state")


def index_entries(
    repo: Path, *, env: dict[str, str] | None = None
) -> list[tuple[bytes, str, str]]:
    raw = git_stdout(repo, ["ls-files", "--stage", "-z"], env=env)
    entries: list[tuple[bytes, str, str]] = []
    seen: set[bytes] = set()
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            header, path = item.split(b"\t", 1)
            mode_b, oid_b, stage_b = header.split(b" ", 2)
        except ValueError as exc:
            raise FreezeError("could not parse a Git index entry") from exc
        if stage_b != b"0":
            raise FreezeError("index contains a non-stage-zero entry")
        if path in seen:
            raise FreezeError("index contains a duplicate path")
        seen.add(path)
        try:
            mode = mode_b.decode("ascii")
            oid = oid_b.decode("ascii")
        except UnicodeDecodeError as exc:
            raise FreezeError("index metadata was not ASCII") from exc
        if mode not in {"100644", "100755", "120000", "160000"}:
            raise FreezeError(f"unsupported Git mode {mode} at {quote_from_bytes(path)}")
        entries.append((path, mode, oid))
    entries.sort(key=lambda item: item[0])
    return entries


def require_clean_initialized_submodules(source: Path) -> None:
    """Refuse unrepresentable edits inside any initialized submodule."""

    visited: set[Path] = set()

    def inspect(repo: Path) -> None:
        resolved_repo = repo.resolve()
        if resolved_repo in visited:
            raise FreezeError(f"recursive submodule worktree detected: {repo}")
        visited.add(resolved_repo)
        for path_b, mode, _oid in index_entries(repo):
            if mode != "160000":
                continue
            relative = Path(os.fsdecode(path_b))
            child = (repo / relative).resolve()
            try:
                child.relative_to(resolved_repo)
            except ValueError as exc:
                raise FreezeError(f"submodule path escapes its repository: {relative}") from exc
            if not child.exists():
                continue
            if child.is_dir() and not any(child.iterdir()):
                # An uninitialized submodule is normally an empty directory.
                # Check this before invoking Git: `git -C empty rev-parse` walks
                # upward and would otherwise mistake the enclosing repository
                # for the submodule worktree.
                continue
            marker = child / ".git"
            probe = run_git(child, ["rev-parse", "--show-toplevel"], check=False)
            if probe.returncode != 0:
                # Close a narrow concurrent initialization/removal window.
                if child.is_dir() and not any(child.iterdir()):
                    continue
                raise FreezeError(f"submodule path is populated but is not a Git worktree: {child}")
            try:
                probed_top = Path(os.fsdecode(probe.stdout.strip())).resolve(strict=True)
            except (OSError, UnicodeError) as exc:
                raise FreezeError(f"submodule returned an invalid worktree root: {child}") from exc
            if probed_top != child or not marker.exists():
                # A successful probe whose top-level is the enclosing repository
                # is not evidence that this gitlink is initialized.
                if child.is_dir() and not any(child.iterdir()):
                    continue
                raise FreezeError(f"submodule path is populated but is not its own Git worktree: {child}")
            dirty = git_stdout(
                child,
                ["status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"],
            )
            if dirty:
                raise FreezeError(
                    f"initialized submodule is dirty and cannot be captured by a superproject patch: {child}"
                )
            inspect(child)

    inspect(source)


def synthetic_index_environment(source: Path, temp_root: Path) -> dict[str, str]:
    object_dir = temp_root / "objects"
    object_dir.mkdir()
    (object_dir / "info").mkdir()
    (object_dir / "pack").mkdir()
    source_objects_raw = git_stdout(source, ["rev-parse", "--git-path", "objects"])
    source_objects = Path(os.fsdecode(source_objects_raw.strip()))
    if not source_objects.is_absolute():
        source_objects = source / source_objects
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = os.fspath(temp_root / "index")
    env["GIT_OBJECT_DIRECTORY"] = os.fspath(object_dir)
    env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = os.fspath(source_objects.resolve())
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


DIFF_ARGS = [
    "diff",
    "--cached",
    "--binary",
    "--full-index",
    "--no-ext-diff",
    "--no-textconv",
    "--no-renames",
    "--src-prefix=a/",
    "--dst-prefix=b/",
]


def make_snapshot(source: Path, pin: str, temp_root: Path) -> tuple[dict[str, str], bytes]:
    env = synthetic_index_environment(source, temp_root)
    run_git(source, ["read-tree", pin], env=env)
    # This updates only the temporary index and temporary object directory.
    run_git(source, ["add", "-A", "--", "."], env=env)
    if git_stdout(source, ["ls-files", "--unmerged", "-z"], env=env):
        raise FreezeError("synthetic snapshot index contains unmerged entries")
    patch = git_stdout(source, [*DIFF_ARGS, pin, "--", "."], env=env)
    if not patch:
        raise FreezeError("source snapshot has no changes relative to the pin")
    return env, patch


def manifest_bytes(
    repo: Path, *, env: dict[str, str] | None = None
) -> tuple[bytes, int]:
    entries = index_entries(repo, env=env)
    process = subprocess.Popen(
        ["git", "-C", os.fspath(repo), "cat-file", "--batch"],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        process.kill()
        raise FreezeError("could not open git cat-file pipes")

    object_cache: dict[str, tuple[int, str]] = {}
    lines: list[bytes] = []
    try:
        for path, mode, oid in entries:
            if mode == "160000":
                # A gitlink has no blob in the superproject.  Its exact payload is
                # the target object ID, encoded without a trailing newline.
                payload = oid.encode("ascii")
                size = len(payload)
                digest = sha256_bytes(payload)
            else:
                cached = object_cache.get(oid)
                if cached is None:
                    process.stdin.write(oid.encode("ascii") + b"\n")
                    process.stdin.flush()
                    header = process.stdout.readline()
                    fields = header.rstrip(b"\n").split(b" ")
                    if len(fields) != 3 or fields[1] != b"blob":
                        raise FreezeError(f"expected blob object for {oid}, got {header!r}")
                    try:
                        size = int(fields[2])
                    except ValueError as exc:
                        raise FreezeError(f"invalid Git object size for {oid}") from exc
                    payload = process.stdout.read(size)
                    separator = process.stdout.read(1)
                    if len(payload) != size or separator != b"\n":
                        raise FreezeError(f"short git cat-file response for {oid}")
                    digest = sha256_bytes(payload)
                    object_cache[oid] = (size, digest)
                else:
                    size, digest = cached

            record = {
                "mode": mode,
                "path": quote_from_bytes(path, safe="/-._~"),
                "sha256": digest,
                "size": size,
            }
            lines.append(
                json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii")
                + b"\n"
            )
    finally:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
    return_code = process.wait()
    stderr = process.stderr.read().decode("utf-8", "replace").strip()
    if return_code != 0:
        raise FreezeError(f"git cat-file failed ({return_code}): {stderr}")
    return b"".join(lines), len(entries)


def replay_and_verify(
    source: Path,
    pin: str,
    patch_path: Path,
    live_manifest: bytes,
    temp_root: Path,
) -> bytes:
    replay = temp_root / "replay"
    replay_env = os.environ.copy()
    # Keep the replay hermetic and canonical-index based.  In particular, a
    # repository with LFS attributes must not download/smudge large payloads.
    replay_env["GIT_LFS_SKIP_SMUDGE"] = "1"
    run_git(
        temp_root,
        ["clone", "--shared", "--no-checkout", "--quiet", os.fspath(source), os.fspath(replay)],
        env=replay_env,
    )
    run_git(replay, ["checkout", "--detach", "--quiet", pin], env=replay_env)
    replay_head = git_stdout(replay, ["rev-parse", "HEAD"], env=replay_env).decode(
        "ascii"
    ).strip()
    if replay_head != pin:
        raise FreezeError(f"replay clone checked out unexpected HEAD: {replay_head}")
    if git_stdout(
        replay,
        ["status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"],
        env=replay_env,
    ):
        raise FreezeError("isolated replay clone was dirty before applying the patch")

    run_git(
        replay,
        ["apply", "--check", "--index", "--binary", os.fspath(patch_path)],
        env=replay_env,
    )
    run_git(
        replay,
        ["apply", "--index", "--binary", os.fspath(patch_path)],
        env=replay_env,
    )
    unstaged = run_git(replay, ["diff", "--quiet", "--"], env=replay_env, check=False)
    if unstaged.returncode != 0:
        raise FreezeError("replay produced unstaged worktree differences")
    if git_stdout(
        replay,
        ["ls-files", "--others", "--exclude-standard", "-z"],
        env=replay_env,
    ):
        raise FreezeError("replay produced untracked paths")

    replay_patch = git_stdout(replay, [*DIFF_ARGS, pin, "--", "."], env=replay_env)
    original_patch = patch_path.read_bytes()
    if replay_patch != original_patch:
        raise FreezeError("replay did not regenerate the canonical patch byte-for-byte")

    replay_manifest, _entry_count = manifest_bytes(replay, env=replay_env)
    if replay_manifest != live_manifest:
        raise FreezeError("replay manifest differs byte-for-byte from the live manifest")
    return replay_manifest


def write_exclusive(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def freeze(
    source: Path,
    expected_pin: str,
    output_dir: Path,
    pin_file: Path | None = None,
) -> dict[str, object]:
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise FreezeError(f"source is not a directory: {source}")
    top = Path(os.fsdecode(git_stdout(source, ["rev-parse", "--show-toplevel"]).strip())).resolve()
    if top != source:
        raise FreezeError(f"--source must be the repository root: {top}")

    output_dir = output_dir.absolute()
    try:
        output_dir.resolve().relative_to(source)
    except ValueError:
        pass
    else:
        raise FreezeError("--output-dir must be outside the source repository")
    if output_dir.exists() or output_dir.is_symlink():
        raise FreezeError(f"refusing to overwrite existing output path: {output_dir}")
    if not output_dir.parent.is_dir():
        raise FreezeError(f"output parent does not exist: {output_dir.parent}")

    pin = require_exact_pin(source, expected_pin, pin_file)
    require_pristine_real_index(source, pin)
    require_clean_initialized_submodules(source)
    pin_file_digest = sha256_file(pin_file) if pin_file is not None else None
    initial_ignored_paths = ignored_path_list(source)

    # mkdir is the no-overwrite reservation.  A crash leaves INCOMPLETE behind,
    # and a subsequent run refuses to overwrite it.
    os.mkdir(output_dir, 0o755)
    incomplete = output_dir / "INCOMPLETE"
    write_exclusive(incomplete, b"canonical source freeze did not complete\n")
    try:
        with tempfile.TemporaryDirectory(prefix="source-freeze-") as temp_name:
            temp_root = Path(temp_name)
            snapshot_root = temp_root / "snapshot"
            snapshot_root.mkdir()
            snapshot_env, patch = make_snapshot(source, pin, snapshot_root)
            live_manifest, entry_count = manifest_bytes(source, env=snapshot_env)

            patch_path = output_dir / "canonical-source.patch"
            live_manifest_path = output_dir / "live.manifest.jsonl"
            write_exclusive(patch_path, patch)
            write_exclusive(live_manifest_path, live_manifest)

            replay_manifest = replay_and_verify(
                source, pin, patch_path, live_manifest, temp_root
            )
            replay_manifest_path = output_dir / "replay.manifest.jsonl"
            write_exclusive(replay_manifest_path, replay_manifest)

            # Prove that the live source and all exclusion inputs remained stable
            # while the isolated replay was running.
            require_exact_pin(source, expected_pin, pin_file)
            require_pristine_real_index(source, pin)
            require_clean_initialized_submodules(source)
            if pin_file is not None and sha256_file(pin_file) != pin_file_digest:
                raise FreezeError("recorded pin file changed during source freeze")
            final_ignored_paths = ignored_path_list(source)
            if final_ignored_paths != initial_ignored_paths:
                raise FreezeError("ignored worktree path set changed during source freeze")
            resnapshot_root = temp_root / "resnapshot"
            resnapshot_root.mkdir()
            resnapshot_env, resnapshot_patch = make_snapshot(source, pin, resnapshot_root)
            resnapshot_manifest, resnapshot_entries = manifest_bytes(
                source, env=resnapshot_env
            )
            if resnapshot_patch != patch:
                raise FreezeError("live patch changed while replay verification was running")
            if resnapshot_manifest != live_manifest or resnapshot_entries != entry_count:
                raise FreezeError("live manifest changed while replay verification was running")

            ignored_count = initial_ignored_paths.count(b"\0")
            ignored_digest = sha256_bytes(initial_ignored_paths)

            git_version = subprocess.run(
                ["git", "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.decode("utf-8", "replace").strip()
            receipt: dict[str, object] = {
                "schema": 1,
                "verdict": "PASS",
                "created_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source": os.fspath(source),
                "expected_pin": pin,
                "recorded_pin_file": (
                    {
                        "path": os.fspath(pin_file.resolve()),
                        "sha256": pin_file_digest,
                    }
                    if pin_file is not None
                    else None
                ),
                "git_version": git_version,
                "patch": {
                    "path": patch_path.name,
                    "bytes": len(patch),
                    "sha256": sha256_bytes(patch),
                },
                "live_manifest": {
                    "path": live_manifest_path.name,
                    "entries": entry_count,
                    "bytes": len(live_manifest),
                    "sha256": sha256_bytes(live_manifest),
                },
                "replay_manifest": {
                    "path": replay_manifest_path.name,
                    "entries": entry_count,
                    "bytes": len(replay_manifest),
                    "sha256": sha256_bytes(replay_manifest),
                },
                "ignored_worktree_paths": {
                    "policy": "excluded by the repository's standard Git ignore rules",
                    "count": ignored_count,
                    "nul_list_sha256": ignored_digest,
                },
                "checks": {
                    "source_head_exact_pin": True,
                    "source_real_index_pristine": True,
                    "source_repository_operation_idle": True,
                    "initialized_submodules_clean": True,
                    "replay_started_pristine": True,
                    "patch_regenerated_byte_exact": True,
                    "manifest_replay_byte_exact": True,
                    "live_resnapshot_byte_exact": True,
                    "pin_and_ignore_inputs_stable": True,
                    "outputs_created_without_overwrite": True,
                },
            }
            receipt_bytes = (
                json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8") + b"\n"
            )
            write_exclusive(output_dir / "receipt.json", receipt_bytes)
            incomplete.unlink()
            return receipt
    except BaseException:
        # This directory was reserved by this process only after proving it did
        # not exist.  Never remove a pre-existing or user-selected path.
        shutil.rmtree(output_dir)
        raise


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="live source Git root")
    parser.add_argument(
        "--expected-pin", required=True, help="full lowercase Git commit object ID"
    )
    parser.add_argument(
        "--pin-file",
        type=Path,
        help="optional recorded-pin file; its first token must prefix --expected-pin",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="new, non-existing output directory outside --source",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        receipt = freeze(
            arguments.source,
            arguments.expected_pin,
            arguments.output_dir,
            arguments.pin_file,
        )
    except (FreezeError, OSError, subprocess.SubprocessError) as exc:
        print(f"source-freeze: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
