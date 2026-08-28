#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Compose P0-I/J interaction evidence with the independent P0-E resize receipt."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Callable, Sequence

import analyze_diagnostic as interaction


ROOT = Path(__file__).resolve().parents[2]
INTERACTION_PRODUCER = ROOT / "sandbox/p0-interaction-stress/capture_diagnostic.mjs"
RESIZE_VERIFIER = ROOT / "sandbox/m4-resize-recovery/verify_hardware_resize_receipt.mjs"
DEFAULT_BIN_DIR = ROOT / "build-wasm-windowed-opt/bin"
PINNED_NODE = ROOT / "tools/emsdk/node/22.16.0_64bit/bin/node"
REQUIRED_RESIZE_ATTEMPTS = 10
SHA256_LENGTH = 64
PRODUCT_FILES = {
    "blender_browser.js",
    "blender_browser.wasm",
    "blender_browser.wasm.orig",
    "blender_browser.data",
    "blender_browser.split-build.json",
}
GENERATION_FIELDS = (
    "mode",
    "originalWasmSha256",
    "instrumentedWasmSha256",
    "javascriptSha256",
)
BROWSER_FIELDS = (
    "platform",
    "nodeVersion",
    "playwrightVersion",
    "pngjsVersion",
    "chromiumVersion",
)
RESIZE_PASS_PREFIX = "BW_P0E_HARDWARE_RESIZE_RECEIPT_PASS "
SAFE_STEP_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class GauntletError(RuntimeError):
    """One independent evidence leg or their shared binding is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GauntletError(message)


def is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular_file(path: Path, label: str) -> None:
    require(path.is_file() and not path.is_symlink(), f"{label} is not a direct regular file: {path}")


def load_json(path: Path, label: str) -> dict[str, Any]:
    require_regular_file(path, label)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GauntletError(f"could not read {label} {path}: {error}") from error
    require(isinstance(document, dict), f"{label} root is not an object: {path}")
    return document


def current_interaction_source() -> dict[str, str]:
    require_regular_file(INTERACTION_PRODUCER, "interaction producer")
    return {
        "path": INTERACTION_PRODUCER.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(INTERACTION_PRODUCER),
    }


def verify_interaction_inventory(document: dict[str, Any], diagnostic_path: Path) -> None:
    """Bind every interaction step record to its immutable screenshot bytes."""

    require(diagnostic_path.name == "diagnostic.json",
            "interaction evidence entry point is not diagnostic.json")
    run = document.get("run")
    require(isinstance(run, str) and SAFE_STEP_RE.fullmatch(run) is not None,
            "interaction evidence run label is invalid")
    require(diagnostic_path.parent.name == run,
            "interaction evidence directory differs from its immutable run label")
    steps = document.get("steps")
    require(isinstance(steps, list) and steps, "interaction screenshot census is absent")
    expected_names = {diagnostic_path.name}
    for step in steps:
        require(isinstance(step, dict), "interaction screenshot step is invalid")
        name = step.get("name")
        require(isinstance(name, str) and SAFE_STEP_RE.fullmatch(name) is not None,
                f"interaction screenshot name is unsafe: {name}")
        image_name = f"{name}.png"
        require(image_name not in expected_names, f"duplicate interaction screenshot: {image_name}")
        expected_names.add(image_name)
        image_path = diagnostic_path.parent / image_name
        require_regular_file(image_path, f"interaction screenshot {name}")
        image_bytes = image_path.read_bytes()
        require(image_bytes.startswith(PNG_SIGNATURE),
                f"interaction screenshot is not PNG: {image_name}")
        require(type(step.get("bytes")) is int and step["bytes"] == len(image_bytes),
                f"interaction screenshot byte size differs: {image_name}")
        require(is_sha256(step.get("sha256")) and step["sha256"] == hashlib.sha256(
            image_bytes).hexdigest(), f"interaction screenshot SHA-256 differs: {image_name}")

    actual_names = set()
    for path in diagnostic_path.parent.iterdir():
        require(path.is_file() and not path.is_symlink(),
                f"interaction evidence contains a non-regular entry: {path.name}")
        actual_names.add(path.name)
    require(actual_names == expected_names, "interaction evidence inventory differs")


def normalized_generation(value: object, label: str) -> dict[str, object]:
    require(isinstance(value, dict), f"{label} is absent")
    result = {field: value.get(field) for field in GENERATION_FIELDS}
    require(result["mode"] == "capture", f"{label} is not CAPTURE mode")
    for field in GENERATION_FIELDS[1:]:
        require(is_sha256(result[field]), f"{label} {field} is invalid")
    return result


def normalized_browser(value: object, label: str) -> dict[str, object]:
    require(isinstance(value, dict), f"{label} is absent")
    result = {field: value.get(field) for field in BROWSER_FIELDS}
    require(all(result[field] not in (None, "") for field in BROWSER_FIELDS),
            f"{label} identity is incomplete")
    return result


def validate_product_files(value: object, label: str) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == PRODUCT_FILES,
            f"{label} inventory differs")
    for name, identity in value.items():
        require(isinstance(identity, dict), f"{label} {name} identity is invalid")
        require(type(identity.get("bytes")) is int and identity["bytes"] > 0,
                f"{label} {name} byte size is invalid")
        require(is_sha256(identity.get("sha256")), f"{label} {name} SHA-256 is invalid")
    return value


def validate_cross_binding(
    documents: list[dict[str, Any]],
    resize_receipt: dict[str, Any],
    expected_wasm_orig_sha256: str,
) -> dict[str, int | str]:
    """Require both already-strict evidence families to describe one Apple product."""

    require(is_sha256(expected_wasm_orig_sha256), "expected wasm.orig SHA-256 is invalid")
    try:
        series = interaction.validate_hardware_series(documents)
    except interaction.DiagnosticError as error:
        raise GauntletError(f"interaction series rejected: {error}") from error

    expected_source = current_interaction_source()
    for index, document in enumerate(documents, 1):
        require(document.get("source") == expected_source,
                f"interaction run {index} producer source differs from this checkout")

    require(resize_receipt.get("schema") == "blender-web.p0e-hardware-resize.v1",
            "resize receipt schema differs")
    require(resize_receipt.get("status") == "PASS", "resize receipt is not PASS")
    require(resize_receipt.get("passed") == REQUIRED_RESIZE_ATTEMPTS,
            "resize receipt does not pass 10/10 attempts")
    resize_results = resize_receipt.get("results")
    require(isinstance(resize_results, list) and len(resize_results) == REQUIRED_RESIZE_ATTEMPTS,
            "resize receipt attempt census differs")

    baseline = documents[0]
    interaction_identity = baseline.get("productIdentity")
    resize_identity = resize_receipt.get("product")
    require(isinstance(interaction_identity, dict) and isinstance(resize_identity, dict),
            "cross-product identity is absent")
    require(interaction_identity.get("binDir") == resize_identity.get("binDir"),
            "interaction and resize product directories differ")

    interaction_files = validate_product_files(
        interaction_identity.get("files"), "interaction product",
    )
    resize_files = validate_product_files(resize_identity.get("files"), "resize product")
    require(interaction_files == resize_files,
            "interaction and resize product file identities differ")

    original_sha = interaction_files["blender_browser.wasm.orig"]["sha256"]
    require(original_sha == expected_wasm_orig_sha256,
            "interaction product differs from the requested wasm.orig generation")
    require(resize_files["blender_browser.wasm.orig"]["sha256"] == expected_wasm_orig_sha256,
            "resize product differs from the requested wasm.orig generation")

    interaction_generation = normalized_generation(
        interaction_identity.get("generation"), "interaction local generation",
    )
    resize_generation = normalized_generation(
        resize_identity.get("generation"), "resize local generation",
    )
    require(interaction_generation == resize_generation,
            "interaction and resize local split generations differ")
    interaction_served = normalized_generation(
        interaction_identity.get("servedGeneration"), "interaction served generation",
    )
    resize_served = normalized_generation(
        resize_identity.get("servedGeneration"), "resize served generation",
    )
    require(interaction_served == resize_served == interaction_generation,
            "local and served split generations are not identical across evidence")

    interaction_browser = normalized_browser(baseline.get("stack"), "interaction browser")
    resize_browser = normalized_browser(resize_receipt.get("browser"), "resize browser")
    require(interaction_browser == resize_browser,
            "interaction and resize browser stacks differ")
    require(interaction_browser["platform"] == "darwin",
            "composed hardware evidence is not from darwin")

    interaction_adapter = baseline.get("adapter")
    resize_adapter = resize_receipt.get("adapter")
    require(isinstance(interaction_adapter, dict) and isinstance(resize_adapter, dict),
            "cross-adapter identity is absent")
    require(interaction_adapter == resize_adapter,
            "interaction and resize adapter identities differ")

    interaction_runs = [document.get("run") for document in documents]
    require(resize_receipt.get("run") not in interaction_runs,
            "resize and interaction evidence labels are not independent")
    return {
        "interaction_runs": series["runs"],
        "interaction_steps": series["steps"],
        "interaction_states": series["states"],
        "interaction_presents": series["presents"],
        "resize_attempts": REQUIRED_RESIZE_ATTEMPTS,
        "wasm_orig_sha256": expected_wasm_orig_sha256,
    }


def resolve_node(value: str | None) -> Path:
    candidates: list[Path] = []
    if value:
        located = shutil.which(value)
        candidates.append(Path(located) if located else Path(value))
    else:
        candidates.append(PINNED_NODE)
        located = shutil.which("node")
        if located:
            candidates.append(Path(located))
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    raise GauntletError("pinned Node executable is absent; pass --node-bin")


def run_resize_verifier(
    node_bin: Path,
    evidence_dir: Path,
    bin_dir: Path,
    expected_wasm_orig_sha256: str,
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    command = [
        str(node_bin),
        str(RESIZE_VERIFIER),
        "--evidence",
        str(evidence_dir),
        "--bin-dir",
        str(bin_dir),
        "--expected-wasm-orig-sha256",
        expected_wasm_orig_sha256,
    ]
    result = runner(
        command,
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "resize verifier failed").strip().splitlines()
        detail = details[-1] if details else "resize verifier failed"
        raise GauntletError(f"independent resize consumer rejected: {detail}")
    lines = [line for line in result.stdout.splitlines() if line]
    require(len(lines) == 1 and lines[0].startswith(RESIZE_PASS_PREFIX),
            "independent resize consumer did not emit its exact PASS token")


def resize_fixture(document: dict[str, Any]) -> dict[str, Any]:
    identity = copy.deepcopy(document["productIdentity"])
    identity["servedGeneration"] = {
        "url": "/blender_browser.split-build.json",
        **identity["servedGeneration"],
    }
    return {
        "schema": "blender-web.p0e-hardware-resize.v1",
        "status": "PASS",
        "run": "apple-resize-r1",
        "startedAt": "2026-08-28T00:01:00.000Z",
        "source": {"path": "fixture", "bytes": 1, "sha256": "f" * 64},
        "product": identity,
        "browser": {
            **document["stack"],
            "moduleSource": "fixture",
        },
        "adapter": copy.deepcopy(document["adapter"]),
        "contract": {},
        "results": [{} for _ in range(REQUIRED_RESIZE_ATTEMPTS)],
        "completedAt": "2026-08-28T00:04:00.000Z",
        "passed": REQUIRED_RESIZE_ATTEMPTS,
    }


def self_check() -> int:
    first = interaction.hardware_document()
    second = copy.deepcopy(first)
    second["run"] = "apple-r2"
    second["capturedAt"] = "2026-08-28T00:00:02.000Z"
    source = current_interaction_source()
    first["source"] = copy.deepcopy(source)
    second["source"] = copy.deepcopy(source)
    documents = [first, second]
    receipt = resize_fixture(first)
    expected = first["productIdentity"]["files"]["blender_browser.wasm.orig"]["sha256"]
    validate_cross_binding(documents, receipt, expected)
    positive = 1
    negative = 0

    mutations: tuple[Callable[[list[dict[str, Any]], dict[str, Any], list[str]], None], ...] = (
        lambda docs, resize, expected_box: docs.pop(),
        lambda docs, resize, expected_box: docs[0]["source"].__setitem__("sha256", "0" * 64),
        lambda docs, resize, expected_box: resize.__setitem__("schema", "wrong"),
        lambda docs, resize, expected_box: resize.__setitem__("status", "FAIL"),
        lambda docs, resize, expected_box: resize.__setitem__("passed", 9),
        lambda docs, resize, expected_box: resize["results"].pop(),
        lambda docs, resize, expected_box: resize.__setitem__("run", docs[0]["run"]),
        lambda docs, resize, expected_box: resize["product"].__setitem__("binDir", "other/bin"),
        lambda docs, resize, expected_box: resize["product"]["files"][
            "blender_browser.data"].__setitem__("sha256", "0" * 64),
        lambda docs, resize, expected_box: resize["product"]["files"][
            "blender_browser.js"].__setitem__("bytes", 99),
        lambda docs, resize, expected_box: resize["product"]["generation"].__setitem__(
            "instrumentedWasmSha256", "0" * 64),
        lambda docs, resize, expected_box: resize["product"]["servedGeneration"].__setitem__(
            "javascriptSha256", "0" * 64),
        lambda docs, resize, expected_box: resize["browser"].__setitem__(
            "chromiumVersion", "149.0.0.0"),
        lambda docs, resize, expected_box: resize["browser"].__setitem__("platform", "linux"),
        lambda docs, resize, expected_box: resize["adapter"]["info"].__setitem__(
            "device", "Different Apple GPU"),
        lambda docs, resize, expected_box: resize["adapter"].__setitem__(
            "isFallbackAdapter", True),
        lambda docs, resize, expected_box: expected_box.__setitem__(0, "0" * 64),
    )
    for mutate in mutations:
        candidate_documents = copy.deepcopy(documents)
        candidate_receipt = copy.deepcopy(receipt)
        expected_box = [expected]
        mutate(candidate_documents, candidate_receipt, expected_box)
        try:
            validate_cross_binding(candidate_documents, candidate_receipt, expected_box[0])
        except GauntletError:
            negative += 1
        else:
            raise GauntletError("self-check mutation was accepted")

    captured: list[list[str]] = []

    def accepted_runner(command: Sequence[str], **_kwargs: Any) -> SimpleNamespace:
        captured.append(list(command))
        return SimpleNamespace(
            returncode=0,
            stdout=f"{RESIZE_PASS_PREFIX}attempts=10/10 wasm_orig_sha256={expected}\n",
            stderr="",
        )

    run_resize_verifier(PINNED_NODE, Path("resize"), Path("bin"), expected, accepted_runner)
    require(captured[0][-1] == expected and captured[0][1] == str(RESIZE_VERIFIER),
            "resize consumer command binding differs")
    positive += 1

    with tempfile.TemporaryDirectory(prefix="bw-p0ij-gauntlet-") as temporary:
        evidence_dir = Path(temporary) / "inventory-run"
        evidence_dir.mkdir()
        image_bytes = PNG_SIGNATURE + b"fixture"
        image_path = evidence_dir / "step.png"
        image_path.write_bytes(image_bytes)
        diagnostic_path = evidence_dir / "diagnostic.json"
        diagnostic_path.write_text("{}\n", encoding="utf-8")
        inventory_document = {
            "run": "inventory-run",
            "steps": [{
                "name": "step",
                "bytes": len(image_bytes),
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
            }],
        }
        verify_interaction_inventory(inventory_document, diagnostic_path)
        positive += 1
        for name, mutate in (
            ("screenshot identity", lambda: image_path.write_bytes(image_bytes + b"changed")),
            ("unexpected inventory", lambda: (evidence_dir / "unexpected.txt").write_text(
                "unexpected\n", encoding="utf-8")),
            ("unsafe screenshot", lambda: inventory_document["steps"][0].__setitem__(
                "name", "../step")),
            ("run directory", lambda: inventory_document.__setitem__("run", "other-run")),
        ):
            original_bytes = image_bytes
            original_name = inventory_document["steps"][0]["name"]
            original_run = inventory_document["run"]
            extra_path = evidence_dir / "unexpected.txt"
            mutate()
            try:
                verify_interaction_inventory(inventory_document, diagnostic_path)
            except GauntletError:
                negative += 1
            else:
                raise GauntletError(f"self-check false green: {name}")
            inventory_document["steps"][0]["name"] = original_name
            inventory_document["run"] = original_run
            image_path.write_bytes(original_bytes)
            extra_path.unlink(missing_ok=True)

    for name, result in (
        ("consumer rejection", SimpleNamespace(returncode=1, stdout="", stderr="rejected\n")),
        ("consumer token", SimpleNamespace(returncode=0, stdout="wrong pass\n", stderr="")),
    ):
        try:
            run_resize_verifier(
                PINNED_NODE,
                Path("resize"),
                Path("bin"),
                expected,
                lambda *_args, result=result, **_kwargs: result,
            )
        except GauntletError:
            negative += 1
        else:
            raise GauntletError(f"self-check false green: {name}")

    print(
        "P0IJ_HARDWARE_GAUNTLET_SELFCHECK_PASS "
        f"positive={positive} negative={negative} interaction_runs=2 resize_attempts=10"
    )
    return 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--interaction", action="append", default=[])
    parser.add_argument("--resize-evidence")
    parser.add_argument("--bin-dir", default=str(DEFAULT_BIN_DIR))
    parser.add_argument("--expected-wasm-orig-sha256")
    parser.add_argument("--node-bin")
    args = parser.parse_args(argv)
    if args.self_check:
        require(len(argv) == 1, "--self-check cannot be combined with live arguments")
        return args
    require(len(args.interaction) >= 2, "at least two --interaction receipts are required")
    require(args.resize_evidence is not None, "--resize-evidence is required")
    require(is_sha256(args.expected_wasm_orig_sha256),
            "--expected-wasm-orig-sha256 must be an exact lowercase SHA-256")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_check:
        return self_check()

    interaction_paths = [Path(value).expanduser().resolve() for value in args.interaction]
    require(len(set(interaction_paths)) == len(interaction_paths),
            "interaction evidence paths are not unique")
    documents = [
        load_json(path, f"interaction receipt {index}")
        for index, path in enumerate(interaction_paths, 1)
    ]
    for document, path in zip(documents, interaction_paths, strict=True):
        verify_interaction_inventory(document, path)
    resize_dir = Path(args.resize_evidence).expanduser().resolve()
    require(resize_dir.is_dir() and not resize_dir.is_symlink(),
            f"resize evidence is not a direct directory: {resize_dir}")
    bin_dir = Path(args.bin_dir).expanduser().resolve()
    require(bin_dir.is_dir() and not bin_dir.is_symlink(),
            f"product bin directory is invalid: {bin_dir}")
    node_bin = resolve_node(args.node_bin)

    run_resize_verifier(
        node_bin,
        resize_dir,
        bin_dir,
        args.expected_wasm_orig_sha256,
    )
    resize_receipt = load_json(resize_dir / "receipt.json", "resize receipt")
    result = validate_cross_binding(
        documents,
        resize_receipt,
        args.expected_wasm_orig_sha256,
    )
    print(
        "P0IJ_HARDWARE_GAUNTLET_PASS "
        f"interaction_runs={result['interaction_runs']} "
        f"interaction_steps={result['interaction_steps']} "
        f"interaction_states={result['interaction_states']} "
        f"interaction_presents={result['interaction_presents']} "
        f"resize_attempts={result['resize_attempts']}/10 "
        f"wasm_orig_sha256={result['wasm_orig_sha256']} exact_generation=1"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GauntletError, interaction.DiagnosticError) as error:
        print(f"P0IJ_HARDWARE_GAUNTLET_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
