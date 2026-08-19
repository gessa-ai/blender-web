#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compose and verify one immutable same-freeze technical-release receipt."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "sandbox/final-m0-m6/evidence"
LABEL_RE = re.compile(r"final-[a-z0-9][a-z0-9._-]{1,73}")
DEFERRED_RE = re.compile(r"blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm")
CC0 = "SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n"
VOLATILE_GENERATED_OUTPUTS = (
    "ledger/results/m0.json", "ledger/results/m1.json", "ledger/results/m2b.json",
    "ledger/results/m3.json", "ledger/results/m4.json", "ledger/results/m5.json",
    "ledger/results/m6.json", "ledger/results/m7.json", "ledger/results/m8.json",
    "reports/dashboard.md",
    "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png",
    "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png.license",
)
M8_TECHNICAL_INPUTS = {
    "staged_receipt": "sandbox/m8-launch-gate/artifacts/current-staged-receipt.json",
    "runtime_proof": "sandbox/m8-staged-deploy/artifacts/verify_staged.json",
    "performance_proof": "sandbox/m8-staged-deploy/artifacts/measure_staged-4g.json",
    "runtime_screenshot": "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png",
    "runtime_screenshot_license": "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png.license",
    "runtime_console": "sandbox/m8-staged-deploy/artifacts/verify_console.log",
    "browser_matrix": "sandbox/m8-launch-gate/artifacts/current-browser-matrix.json",
    "product": "sandbox/m8-launch-gate/artifacts/current-product-receipt.json",
    "soak": "sandbox/m8-launch-gate/artifacts/current-soak-result.json",
    "compliance": "sandbox/m8-launch-gate/artifacts/current-compliance-receipt.json",
}
M8_TECHNICAL_TREES = {
    "launch_artifacts": (
        "sandbox/m8-launch-gate/artifacts", ("current-m8-preflight.json",),
    ),
    "staged_artifacts": ("sandbox/m8-staged-deploy/artifacts", ()),
    "bundle": ("sandbox/m8-staged-deploy/bundle-staged", ()),
}
M7_TECHNICAL_INPUTS = {
    "files_receipt": "sandbox/m7-product-gate/verify_files.json",
    "bundle_identity": "sandbox/m7-product-gate/bundle-identity.json",
}


class ComposeError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ComposeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reject_symlinks(path: Path, where: str) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            fail(f"{where}: symlink path component is not accepted: {current}")


def repository_file(value: str | Path, where: str) -> Path:
    raw = os.fspath(value)
    lexical = Path(raw) if Path(raw).is_absolute() else ROOT / PurePosixPath(raw)
    reject_symlinks(lexical, where)
    try:
        path = lexical.resolve(strict=True)
    except OSError as error:
        fail(f"{where}: missing file: {error}")
    if ROOT not in path.parents or not path.is_file():
        fail(f"{where}: expected a regular file strictly inside the repository")
    return path


def repository_tree(relative: str, where: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        fail(f"{where}: unsafe repository-relative directory")
    lexical = ROOT / pure
    reject_symlinks(lexical, where)
    try:
        path = lexical.resolve(strict=True)
    except OSError as error:
        fail(f"{where}: missing directory: {error}")
    if path != lexical or not path.is_dir():
        fail(f"{where}: expected canonical non-symlink directory")
    return path


def external_file(value: str | Path, where: str) -> Path:
    lexical = Path(value)
    if not lexical.is_absolute():
        fail(f"{where}: expected an absolute path outside the repository")
    reject_symlinks(lexical, where)
    try:
        path = lexical.resolve(strict=True)
    except OSError as error:
        fail(f"{where}: missing file: {error}")
    if path != lexical or not path.is_file() or path == ROOT or ROOT in path.parents:
        fail(f"{where}: expected canonical regular file outside the repository")
    return path


def load_json(path: Path, where: str) -> Any:
    def strict(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                fail(f"{where}: duplicate JSON field: {key}")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"{where}: invalid JSON: {error}")


def file_ref(path: Path) -> dict[str, Any]:
    path = repository_file(path, "file reference")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def external_ref(path: Path) -> dict[str, Any]:
    path = external_file(path, "external file reference")
    return {"path": os.fspath(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def tree_ref(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    for item in sorted(path.rglob("*")):
        reject_symlinks(item, "evidence tree")
        if item.is_dir():
            continue
        if not item.is_file():
            fail(f"evidence tree contains non-file: {item}")
        digest.update(item.relative_to(path).as_posix().encode("utf-8") + b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
        count += 1
    if count == 0:
        fail(f"evidence tree is empty: {path.relative_to(ROOT)}")
    return {"path": path.relative_to(ROOT).as_posix(), "files": count, "sha256": digest.hexdigest()}


def projected_tree_ref(path: Path, excluded: tuple[str, ...] = ()) -> dict[str, Any]:
    path = repository_tree(path.relative_to(ROOT).as_posix(), "projected evidence tree")
    excluded_set = set(excluded)
    if len(excluded_set) != len(excluded):
        fail("projected evidence tree has duplicate exclusions")
    digest = hashlib.sha256()
    count = 0
    for item in sorted(path.rglob("*")):
        reject_symlinks(item, "projected evidence tree")
        relative = item.relative_to(path).as_posix()
        if relative in excluded_set:
            if not item.is_file():
                fail(f"projected evidence exclusion is not a file: {relative}")
            continue
        if item.is_dir():
            continue
        if not item.is_file():
            fail(f"projected evidence tree contains non-file: {item}")
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
        count += 1
    return {
        "path": path.relative_to(ROOT).as_posix(), "excluded": list(excluded),
        "files": count, "sha256": digest.hexdigest(),
    }


def _closure_tree_identity(path: Path, excluded: tuple[str, ...]) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    excluded_set = set(excluded)
    for item in sorted(path.rglob("*")):
        reject_symlinks(item, "publication closure tree")
        relative = item.relative_to(path).as_posix()
        if relative in excluded_set:
            if not item.is_file():
                fail(f"publication closure exclusion is not a file: {relative}")
            continue
        if item.is_dir():
            continue
        if not item.is_file():
            fail(f"publication closure tree contains non-file: {item}")
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
        count += 1
    return count, digest.hexdigest()


def recheck_verification_closure(verified: dict[str, Any], root: Path = ROOT) -> None:
    closure = verified.get("verification_closure")
    if not isinstance(closure, dict) or set(closure) != {"schema", "files", "trees"} \
            or closure.get("schema") != 1:
        fail("aggregate verifier returned no exact verification closure")
    files = closure.get("files")
    trees = closure.get("trees")
    if not isinstance(files, list) or not isinstance(trees, list):
        fail("aggregate verifier closure inventories are not lists")
    seen_files: set[tuple[str, str]] = set()
    for index, row in enumerate(files):
        if not isinstance(row, dict) or set(row) != {"kind", "path", "bytes", "sha256"}:
            fail(f"verification closure file row {index} is not exact")
        kind, name = row["kind"], row["path"]
        if not isinstance(name, str) or (kind, name) in seen_files:
            fail(f"verification closure file row {index} is duplicate/invalid")
        seen_files.add((kind, name))
        if kind == "repository":
            pure = PurePosixPath(name)
            if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
                fail(f"verification closure repository path is unsafe: {name!r}")
            path = root / pure
        elif kind == "external":
            path = Path(name)
            if not path.is_absolute():
                fail("verification closure external path is not absolute")
        else:
            fail(f"verification closure file kind is invalid: {kind!r}")
        reject_symlinks(path, "publication closure file")
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            fail(f"publication closure file disappeared: {error}")
        if resolved != path or not path.is_file() or (
            path.stat().st_size, sha256(path)
        ) != (row["bytes"], row["sha256"]):
            fail(f"publication closure file changed: {path}")
    seen_trees: set[str] = set()
    for index, row in enumerate(trees):
        if not isinstance(row, dict) or set(row) != {"path", "excluded", "files", "sha256"}:
            fail(f"verification closure tree row {index} is not exact")
        name = row["path"]
        excluded = row["excluded"]
        if (not isinstance(name, str) or name in seen_trees or not isinstance(excluded, list)
                or any(not isinstance(value, str) for value in excluded)):
            fail(f"verification closure tree row {index} is duplicate/invalid")
        seen_trees.add(name)
        pure = PurePosixPath(name)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            fail(f"verification closure tree path is unsafe: {name!r}")
        path = root / pure
        reject_symlinks(path, "publication closure tree")
        if path.resolve(strict=True) != path or not path.is_dir():
            fail(f"publication closure tree is missing/noncanonical: {path}")
        current = _closure_tree_identity(path, tuple(excluded))
        if current != (row["files"], row["sha256"]):
            fail(f"publication closure tree changed: {path}")


def require_bound_verification(
    verified: dict[str, Any], manifest_path: Path, run_label: str, root: Path = ROOT,
) -> None:
    if verified.get("verdict") != "PASS" or verified.get("run_label") != run_label:
        fail("aggregate verifier returned an unbound result")
    candidate = verified.get("candidate_manifest")
    if candidate != {"bytes": manifest_path.stat().st_size, "sha256": sha256(manifest_path)}:
        fail("aggregate verifier did not bind the exact candidate manifest bytes")
    recheck_verification_closure(verified, root)


def split_artifacts() -> tuple[dict[str, dict[str, Any]], str]:
    directory = ROOT / "build-wasm-windowed-opt/bin"
    manifest_path = repository_file(directory / "blender_browser.split-build.json", "split manifest")
    manifest = load_json(manifest_path, "split manifest")
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 \
            or manifest.get("mode") != "apply" or manifest.get("verdict") != "PASS":
        fail("split manifest is not schema-1 APPLY/PASS")
    rows = manifest.get("wasm_inventory")
    if not isinstance(rows, list) or len(rows) != 3:
        fail("split manifest must contain exactly three Wasm inventory rows")
    by_role = {row.get("role"): row for row in rows if isinstance(row, dict)}
    if set(by_role) != {"primary", "deferred", "original_build_only"}:
        fail("split inventory role set is not exact")
    deferred = by_role["deferred"].get("filename")
    if (not isinstance(deferred, str) or DEFERRED_RE.fullmatch(deferred) is None
            or deferred in {"blender_browser.wasm", "blender_browser.wasm.orig"}):
        fail("split inventory has an unsafe deferred filename")
    names = {row.get("filename") for row in rows}
    actual = {path.name for path in directory.glob("blender_browser*.wasm*") if path.is_file()}
    if names != actual:
        fail(f"split inventory/file set mismatch: expected={sorted(names)} actual={sorted(actual)}")
    artifacts = {
        "manifest": file_ref(manifest_path),
        "javascript": file_ref(directory / "blender_browser.js"),
        "preload": file_ref(directory / "blender_browser.data"),
        "primary": file_ref(directory / "blender_browser.wasm"),
        "deferred": file_ref(directory / deferred),
    }
    return artifacts, deferred


def compose(label: str, release: Path, m03_manifest: Path) -> dict[str, Any]:
    if LABEL_RE.fullmatch(label) is None:
        fail("--run-label must start with 'final-' and contain 8-80 safe lowercase characters")
    release = external_file(release, "source freeze")
    release_json = load_json(release, "source freeze")
    if not isinstance(release_json, dict) or release_json.get("verdict") != "PASS":
        fail("source freeze is not PASS")
    m03_manifest = repository_file(m03_manifest, "M0-M3 manifest")
    m03_json = load_json(m03_manifest, "M0-M3 manifest")
    if not isinstance(m03_json, dict) or m03_json.get("run_label") != label:
        fail("M0-M3 manifest does not use --run-label")

    artifacts, _deferred = split_artifacts()
    m5 = {}
    for kind in ("click", "canvas", "latency"):
        run = f"{label}.m5-{kind}"
        receipt = repository_file(
            ROOT / f"sandbox/m5-{kind if kind != 'canvas' else 'canvas-smoke'}/evidence/{run}/receipt.json"
            if kind != "click" else ROOT / f"sandbox/m5-click-pick/evidence/{run}/receipt.json",
            f"M5 {kind} receipt",
        )
        m5[kind] = {"run_label": run, "receipt_sha256": sha256(receipt)}

    m4_binding = repository_file(
        ROOT / f"sandbox/m4-d9-gate/evidence/{label}.m4.binding.json", "M4 binding"
    )
    workbench = repository_tree(
        f"sandbox/gpu-r61/workbench-preview/runs/{label}.m6-workbench", "M6 Workbench"
    )
    eevee = repository_tree(
        f"sandbox/gpu-r61/eevee-matrix-preview/runs/{label}.m6-eevee", "M6 EEVEE"
    )
    cycles_smoke = repository_file(
        ROOT / f"sandbox/gpu-r61/cycles-windowed/evidence/{label}.m6-cycles-smoke-manifest.json",
        "M6 Cycles smoke",
    )
    cycles_smoke_tree = repository_tree(
        "sandbox/gpu-r61/cycles-windowed/evidence", "M6 Cycles smoke evidence tree"
    )
    cycles_suite = repository_tree(
        f"sandbox/m6-prep/cycles-runs/{label}.m6-cycles-suite", "M6 Cycles suite"
    )
    created = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    generated_outputs = {
        relative: file_ref(ROOT / relative) for relative in VOLATILE_GENERATED_OUTPUTS
    }
    return {
        "schema": 1,
        "verdict": "PASS",
        "run_label": label,
        "created_utc": created,
        "source_freeze": {"receipt": external_ref(release)},
        "generated_outputs": generated_outputs,
        "m0_m3": {
            "manifest": file_ref(m03_manifest),
            "verifier": file_ref(ROOT / "sandbox/final-m0-m3/verify.py"),
        },
        "artifacts": artifacts,
        "m7_technical": {
            "verifier": file_ref(ROOT / "sandbox/m7-product-gate/verify_m7.py"),
            "evidence": {
                key: file_ref(ROOT / relative)
                for key, relative in M7_TECHNICAL_INPUTS.items()
            },
            "evidence_trees": {
                "fallback": tree_ref(
                    repository_tree(
                        f"sandbox/m7-product-gate/fallback-evidence/{label}",
                        "M7 fallback evidence",
                    )
                ),
                "usd_browser": tree_ref(
                    repository_tree(
                        f"sandbox/m7-usd-prep/browser-roundtrip/{label}",
                        "M7 browser USD evidence",
                    )
                ),
                "usd_native": tree_ref(
                    repository_tree(
                        f"sandbox/m7-usd-prep/native-capability/{label}",
                        "M7 native USD evidence",
                    )
                ),
            },
        },
        "m8_technical": {
            "verifier": file_ref(ROOT / "sandbox/m8-launch-gate/verify_m8.py"),
            "evidence": {
                key: file_ref(ROOT / relative)
                for key, relative in M8_TECHNICAL_INPUTS.items()
            },
            "evidence_trees": {
                key: projected_tree_ref(ROOT / relative, excluded)
                for key, (relative, excluded) in M8_TECHNICAL_TREES.items()
            },
            "result": generated_outputs["ledger/results/m8.json"],
            "dashboard": generated_outputs["reports/dashboard.md"],
        },
        "milestones": {
            "m4": {
                "verifier": file_ref(ROOT / "sandbox/m4-d9-gate/verify_current_binding.py"),
                "binding": file_ref(m4_binding),
            },
            "m5": {"verifier": file_ref(ROOT / "sandbox/m5-final/verify_m5.py"), **m5},
            "m6": {
                "verifier": file_ref(ROOT / "sandbox/m6-prep/verify_render_closeout.py"),
                "workbench": {"run_label": f"{label}.m6-workbench", "evidence": tree_ref(workbench)},
                "eevee": {"run_label": f"{label}.m6-eevee", "evidence": tree_ref(eevee)},
                "cycles_smoke": {
                    "run_label": f"{label}.m6-cycles-smoke",
                    "evidence": file_ref(cycles_smoke),
                    "evidence_tree": tree_ref(cycles_smoke_tree),
                },
                "cycles_suite": {"run_label": f"{label}.m6-cycles-suite", "evidence": tree_ref(cycles_suite)},
            },
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label")
    parser.add_argument("--source-freeze", type=Path)
    parser.add_argument("--m0-m3-manifest", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.selfcheck:
            if LABEL_RE.fullmatch("final-20260815-r1") is None or LABEL_RE.fullmatch("unsafe") is not None:
                fail("label self-check failed")
            print("FINAL_M0_M6_COMPOSE_SELFCHECK_PASS immutable=1 verify=1")
            return 0
        if not args.run_label or args.source_freeze is None or args.m0_m3_manifest is None:
            fail("--run-label, --source-freeze, and --m0-m3-manifest are required")
        output_dir = OUT_ROOT / args.run_label
        if output_dir.exists() or output_dir.is_symlink():
            fail(f"refusing to overwrite immutable output: {output_dir.relative_to(ROOT)}")
        manifest = compose(args.run_label, args.source_freeze, args.m0_m3_manifest)
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{args.run_label}.staging-", dir=OUT_ROOT))
        try:
            manifest_path = staging / "final-m0-m6.json"
            with manifest_path.open("x", encoding="utf-8") as stream:
                json.dump(manifest, stream, indent=2, sort_keys=True)
                stream.write("\n")
            (staging / "final-m0-m6.json.license").write_text(CC0, encoding="utf-8")
            command = [
                sys.executable, os.fspath(ROOT / "sandbox/final-m0-m6/verify.py"),
                "--root", os.fspath(ROOT), "--manifest", os.fspath(manifest_path),
            ]
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            if result.returncode != 0:
                fail(f"aggregate verifier rejected immutable candidate: {(result.stdout + result.stderr)[-4000:]}")
            verified = json.loads(result.stdout)
            require_bound_verification(verified, manifest_path, args.run_label)
            verified["publication"] = {
                "schema": 1,
                "selector": f"sandbox/final-m0-m6/evidence/{args.run_label}/final-m0-m6.json",
                "candidate_bytes": manifest_path.stat().st_size,
                "candidate_sha256": sha256(manifest_path),
                "atomic_directory_publish": True,
            }
            verification_path = staging / "verification.json"
            with verification_path.open("x", encoding="utf-8") as stream:
                json.dump(verified, stream, indent=2, sort_keys=True)
                stream.write("\n")
            (staging / "verification.json.license").write_text(CC0, encoding="utf-8")
            digest_path = staging / "verification.sha256"
            digest_path.write_text(
                f"{sha256(verification_path)}  verification.json\n", encoding="ascii"
            )
            # Close the verifier-return/publication race: recheck every file and
            # exact tree in the verifier's closure immediately before one atomic
            # directory rename, then reject any unlisted staging output.
            require_bound_verification(verified, manifest_path, args.run_label)
            expected_outputs = {
                "final-m0-m6.json", "final-m0-m6.json.license",
                "verification.json", "verification.json.license", "verification.sha256",
            }
            actual_outputs = {
                item.name for item in staging.iterdir() if item.is_file() or item.is_symlink()
            }
            if (actual_outputs != expected_outputs or any(
                    item.is_symlink() or not item.is_file() for item in staging.iterdir()
            )):
                fail("aggregate staging output tree/selector is not exact")
            staging.rename(output_dir)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        manifest_path = output_dir / "final-m0-m6.json"
        verification_path = output_dir / "verification.json"
        final_names = {
            item.name for item in output_dir.iterdir() if item.is_file() or item.is_symlink()
        }
        if final_names != expected_outputs or any(
                item.is_symlink() or not item.is_file() for item in output_dir.iterdir()
        ):
            fail("published aggregate output tree/selector changed during atomic rename")
        require_bound_verification(verified, manifest_path, args.run_label)
        if (output_dir / "verification.sha256").read_text(encoding="ascii") != (
            f"{sha256(verification_path)}  verification.json\n"
        ):
            fail("published aggregate verification digest is stale")
        print(
            f"FINAL_M0_M6_COMPOSE_PASS run={args.run_label} "
            f"manifest={manifest_path.relative_to(ROOT)} verification_sha256={sha256(verification_path)}"
        )
        return 0
    except (ComposeError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"final-m0-m6-compose: FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
