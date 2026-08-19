#!/usr/bin/env python3
"""Hermetic self-check for the two-root technical release freeze."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import freeze_release


HERE = Path(__file__).resolve().parent
PROGRAM = HERE / "freeze_release.py"


def command(args: list[str], *, expect: int = 0) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != expect:
        raise AssertionError(
            f"unexpected exit {completed.returncode}, wanted {expect}: {' '.join(args)}\n"
            + completed.stdout.decode("utf-8", "replace")
            + completed.stderr.decode("utf-8", "replace")
        )
    return completed


def git(repo: Path, *args: str) -> bytes:
    return command(["git", "-C", os.fspath(repo), *args]).stdout


def write(path: Path, payload: bytes = b"fixture\n", mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(mode)


def initialize(repo: Path, message: str) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "--quiet")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", message)
    return git(repo, "rev-parse", "HEAD").decode("ascii").strip()


def invoke(
    project: Path,
    project_pin: str,
    upstream: Path,
    upstream_pin: str,
    pin_file: Path,
    output: Path,
    *,
    expect: int = 0,
) -> subprocess.CompletedProcess[bytes]:
    return command(
        [
            sys.executable,
            os.fspath(PROGRAM),
            "--project", os.fspath(project),
            "--project-pin", project_pin,
            "--upstream", os.fspath(upstream),
            "--upstream-pin", upstream_pin,
            "--upstream-pin-file", os.fspath(pin_file),
            "--output-dir", os.fspath(output),
        ],
        expect=expect,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="release-source-freeze-selfcheck-") as name:
        root = Path(name)
        project = root / "project"
        project.mkdir()
        write(project / ".gitignore", b"upstream/\n")
        for required in freeze_release.REQUIRED_PROJECT_PATHS:
            write(project / required, f"fixture: {required}\n".encode())
        project_pin = initialize(project, "project pin")
        write(project / "platform_web/shell/boot-windowed.js", b"changed project shell\n")
        write(project / "new-top-level-verifier.py", b"print('new')\n")

        upstream = project / "upstream"
        for required in freeze_release.REQUIRED_UPSTREAM_PATHS:
            write(upstream / required, f"fixture: {required}\n".encode())
        write(upstream / "source/pinned.cc", b"pinned\n")
        upstream_pin = initialize(upstream, "upstream pin")
        submodule_origin = root / "linux-x64-origin"
        write(submodule_origin / "payload", b"submodule fixture\n")
        submodule_pin = initialize(submodule_origin, "submodule pin")
        git(
            upstream, "update-index", "--add", "--cacheinfo",
            f"160000,{submodule_pin},lib/linux_x64",
        )
        git(upstream, "commit", "--quiet", "-m", "record empty submodule")
        upstream_pin = git(upstream, "rev-parse", "HEAD").decode("ascii").strip()
        (upstream / "lib/linux_x64").mkdir(parents=True)
        write(upstream / "source/pinned.cc", b"ported\n")
        write(upstream / "source/new_web_backend.cc", b"backend\n")
        pin_file = root / "UPSTREAM_PIN"
        pin_file.write_text(upstream_pin[:12] + " fixture\n", encoding="utf-8")

        output = root / "release-freeze"
        invoke(project, project_pin, upstream, upstream_pin, pin_file, output)
        assert {path.name for path in output.iterdir()} == {
            "project", "upstream", "receipt.json"
        }
        receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
        assert receipt["verdict"] == "PASS"
        assert receipt["coverage"]["required_paths_present"] == len(
            freeze_release.REQUIRED_PROJECT_PATHS
        )
        assert receipt["coverage"]["required_upstream_paths_present"] == len(
            freeze_release.REQUIRED_UPSTREAM_PATHS
        )
        assert receipt["coverage"]["volatile_generated_outputs"] == list(
            freeze_release.VOLATILE_GENERATED_OUTPUTS
        )
        assert set(freeze_release.VOLATILE_GENERATED_OUTPUTS) == {
            *(f"ledger/results/{scope}.json" for scope in
              ("m0", "m1", "m2b", "m3", "m4", "m5", "m6", "m7", "m8")),
            "reports/dashboard.md",
            "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png",
            "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png.license",
        }
        assert "sandbox/m8-staged-deploy/artifacts/unlisted.txt" not in (
            freeze_release.VOLATILE_GENERATED_OUTPUTS
        )
        assert all(receipt["checks"].values())
        assert receipt["final_paired_resnapshot"] == {
            "policy": "nested overlapping live resnapshots immediately before publication",
            "order": ["project", "upstream", "upstream", "project"],
            "checks_per_root": 2,
        }
        for component in ("project", "upstream"):
            component_dir = output / component
            assert (component_dir / "live.manifest.jsonl").read_bytes() == (
                component_dir / "replay.manifest.jsonl"
            ).read_bytes()
            assert receipt[component]["receipt_sha256"] == sha256(
                component_dir / "receipt.json"
            )

        before = sha256(output / "receipt.json")
        overwrite = invoke(
            project, project_pin, upstream, upstream_pin, pin_file, output, expect=1
        )
        assert b"refusing to overwrite" in overwrite.stderr
        assert sha256(output / "receipt.json") == before

        # The same gitlink path becomes invalid if populated without its own
        # Git worktree marker. This must fail before a component is published.
        write(upstream / "lib/linux_x64/not-a-repository", b"reject\n")
        bad_submodule_output = root / "populated-nonrepo-submodule"
        bad_submodule = invoke(
            project, project_pin, upstream, upstream_pin, pin_file,
            bad_submodule_output, expect=1,
        )
        assert b"not its own Git worktree" in bad_submodule.stderr
        assert not bad_submodule_output.exists()
        (upstream / "lib/linux_x64/not-a-repository").unlink()

        # Deterministically mutate the project in the old cross-root window:
        # immediately after its first final resnapshot, while upstream remains to
        # be checked. The nested final project pass must detect the mutation and
        # the failed composite output must be removed.
        original_resnapshot = freeze_release.resnapshot_matches
        project_passes = 0

        def mutate_after_first_project_pass(
            source: Path, pin: str, receipt_dir: Path
        ) -> None:
            nonlocal project_passes
            is_project = source.resolve() == project.resolve()
            if is_project:
                project_passes += 1
            original_resnapshot(source, pin, receipt_dir)
            if is_project and project_passes == 1:
                (project / "GOAL.md").write_bytes(
                    b"mutation in cross-root verification window\n"
                )

        freeze_release.resnapshot_matches = mutate_after_first_project_pass
        mutation_output = root / "mutation-window"
        try:
            try:
                freeze_release.freeze_release(
                    project,
                    project_pin,
                    upstream,
                    upstream_pin,
                    pin_file,
                    mutation_output,
                )
            except freeze_release.canonical.FreezeError as exc:
                assert "changed after its component freeze completed" in str(exc)
            else:
                raise AssertionError("cross-root mutation window was accepted")
        finally:
            freeze_release.resnapshot_matches = original_resnapshot
        assert project_passes == 2
        assert not mutation_output.exists()

        # Explicit upstream technical inputs are independently asserted; the
        # generic complete manifest must not hide a missing parity CMake path.
        upstream_required = upstream / freeze_release.REQUIRED_UPSTREAM_PATHS[-1]
        upstream_required_payload = upstream_required.read_bytes()
        upstream_required.unlink()
        missing_upstream_output = root / "missing-upstream-coverage"
        missing_upstream = invoke(
            project, project_pin, upstream, upstream_pin, pin_file,
            missing_upstream_output, expect=1,
        )
        assert b"upstream freeze omits required technical-release inputs" in missing_upstream.stderr
        assert not missing_upstream_output.exists()
        write(upstream_required, upstream_required_payload)

        # Browser fallback device creation is release-critical independently of
        # the worker path; deleting it must fail explicit project coverage.
        web_fallback = project / "platform_web/ghost/GHOST_ContextWGPUWeb.cc"
        web_fallback_payload = web_fallback.read_bytes()
        web_fallback.unlink()
        missing_web_fallback_output = root / "missing-web-fallback-coverage"
        missing_web_fallback = invoke(
            project, project_pin, upstream, upstream_pin, pin_file,
            missing_web_fallback_output, expect=1,
        )
        assert (
            b"top-level freeze omits required technical-release inputs: "
            b"platform_web/ghost/GHOST_ContextWGPUWeb.cc"
            in missing_web_fallback.stderr
        )
        assert not missing_web_fallback_output.exists()
        write(web_fallback, web_fallback_payload)

        # Deleting an asserted release input must fail even though the generic
        # component patch/replay itself remains internally valid.
        (project / "GOAL.md").unlink()
        missing_output = root / "missing-coverage"
        missing = invoke(
            project, project_pin, upstream, upstream_pin, pin_file, missing_output, expect=1
        )
        assert b"omits required technical-release inputs: GOAL.md" in missing.stderr
        assert not missing_output.exists()

        print(json.dumps({
            "verdict": "PASS",
            "project_patch_sha256": receipt["project"]["patch"]["sha256"],
            "upstream_patch_sha256": receipt["upstream"]["patch"]["sha256"],
            "required_paths": receipt["coverage"]["required_paths_present"],
            "required_upstream_paths": receipt["coverage"]["required_upstream_paths_present"],
            "negative_checks": [
                "overwrite", "populated_nonrepository_submodule",
                "cross_root_mutation_window", "missing_upstream_release_input",
                "missing_web_fallback_release_input", "missing_release_input"
            ],
            "empty_uninitialized_submodule": True,
            "cross_root_resnapshot_byte_exact": True,
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
