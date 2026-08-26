#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed M7 verifier with an explicit public-preview subset mode.

The default is the strict GOAL.md promise and therefore stays red while USD,
the launch budget, or the cross-browser fallback matrix is incomplete.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import plistlib
import platform
import shutil
import subprocess
import tempfile
import re
import stat
import sys
import zlib
from urllib.parse import unquote

import jsonschema

import fallback_contract as fallback_contract

ROOT = pathlib.Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "sandbox/m8-staged-deploy/bundle-staged"
STAGED_RECEIPT = ROOT / "sandbox/m8-staged-deploy/artifacts/verify_staged.json"
FILES_RECEIPT = ROOT / "sandbox/m7-product-gate/verify_files.json"
STRICT_STAGED_RECEIPT = ROOT / "sandbox/m8-launch-gate/artifacts/current-staged-receipt.json"
USD_BROWSER_ROOT = ROOT / "sandbox/m7-usd-prep/browser-roundtrip"
USD_NATIVE_ROOT = ROOT / "sandbox/m7-usd-prep/native-capability"
FALLBACK_SCHEMA = ROOT / "sandbox/m7-product-gate/fallback_receipt.schema.json"
FALLBACK_EVIDENCE = ROOT / "sandbox/m7-product-gate/fallback-evidence"
FALLBACK_PRODUCER = ROOT / "sandbox/m7-product-gate/capture_fallback.py"
FALLBACK_INPUT = ROOT / "sandbox/m4-goldens/default_cube.blend"
BUNDLE_IDENTITY = ROOT / "sandbox/m7-product-gate/bundle-identity.json"
USD_DRIVER = ROOT / "sandbox/m7-usd-prep/verify_browser_usd.mjs"
USD_NATIVE_PRODUCER = ROOT / "sandbox/m7-usd-prep/make_native_receipt.py"
USD_SELECTOR_SCHEMA = "blender-web.m7-usd-selector.v1"
CRITICAL_WIRE_LIMIT = 15_000_000
FALLBACK_FROZEN_PATHS = {
    "platform_web/shell/windowed.html",
    "platform_web/shell/diagnostics-bootstrap.js",
    "platform_web/shell/boot-windowed.js",
    "platform_web/shell/file-bridge.js",
    "platform_web/shell/wgpu-preinit-worker.js",
    "sandbox/m7-product-gate/fallback_contract.py",
    "sandbox/m7-product-gate/capture_fallback.py",
    "sandbox/m7-usd-prep/verify_browser_usd.mjs",
    "sandbox/m7-usd-prep/make_native_receipt.py",
    "sandbox/m7-product-gate/fallback_receipt.schema.json",
    "sandbox/m7-product-gate/verify_m7.py",
    "sandbox/m8-launch-gate/verify_m8.py",
    "sandbox/m8-launch-gate/bundle_identity.mjs",
    "sandbox/m8-launch-gate/runtime_evidence.mjs",
    "sandbox/m8-staged-deploy/make_staged_bundle.sh",
    "sandbox/m8-staged-deploy/brotli_q11.mjs",
    "sandbox/m8-staged-deploy/public_shell_minify.mjs",
    "sandbox/m8-staged-deploy/serve_measure.py",
    "sandbox/m8-staged-deploy/transport_contract.py",
}
VOLATILE_GENERATED_OUTPUTS = {
    "ledger/results/m0.json", "ledger/results/m1.json", "ledger/results/m2b.json",
    "ledger/results/m3.json", "ledger/results/m4.json", "ledger/results/m5.json",
    "ledger/results/m6.json", "ledger/results/m7.json", "ledger/results/m8.json",
    "reports/dashboard.md",
}
sys.path.insert(0, str(ROOT / "sandbox/m8-launch-gate"))
import verify_m8  # noqa: E402
sys.path.insert(0, str(ROOT / "sandbox/final-source-freeze"))
import freeze_release  # noqa: E402


def strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load(path: pathlib.Path, failures: list[str]) -> dict:
    try:
        display = path.relative_to(ROOT)
    except ValueError:
        display = path
    try:
        value = json.loads(path.read_text(), object_pairs_hook=strict_json_object)
    except Exception as error:
        failures.append(f"missing/unreadable {display}: {error}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"not a JSON object: {display}")
        return {}
    if not value:
        failures.append(f"empty JSON object is not a receipt/schema: {display}")
        return {}
    return value


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def strict_exit_code(failures: list[str], subset: bool) -> int:
    return 0 if subset or not failures else 1


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file_receipt(item: object, expected: pathlib.Path, context: str,
                        failures: list[str]) -> bool:
    if not isinstance(item, dict):
        failures.append(f"{context}: file receipt missing")
        return False
    actual_path = pathlib.Path(str(item.get("path", item.get("hostPath", ""))))
    expected = expected.absolute()
    if not actual_path.is_absolute() or os.path.normpath(str(actual_path)) != str(actual_path):
        failures.append(f"{context}: invalid receipt path")
        return False
    require(actual_path == expected, f"{context}: path mismatch", failures)
    current = pathlib.Path(actual_path.anchor)
    try:
        for part in actual_path.parts[1:-1]:
            current /= part
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or current.is_symlink():
                raise ValueError(f"indirect/non-directory parent: {current}")
        info = actual_path.lstat()
        if not stat.S_ISREG(info.st_mode) or actual_path.is_symlink():
            raise ValueError("terminal path is not a real regular file")
    except (OSError, ValueError) as error:
        failures.append(f"{context}: unsafe/missing file {expected}: {error}")
        return False
    require(item.get("bytes") == info.st_size,
            f"{context}: byte length mismatch", failures)
    require(item.get("sha256") == sha256(actual_path), f"{context}: SHA-256 mismatch", failures)
    return (actual_path == expected and item.get("bytes") == info.st_size
            and item.get("sha256") == sha256(actual_path))


def verify_relative_file_receipt(item: object, expected: pathlib.Path, context: str,
                                 failures: list[str]) -> bool:
    expected = expected.absolute()
    try:
        relative = str(expected.relative_to(ROOT))
    except ValueError:
        failures.append(f"{context}: expected path is outside the source root")
        return False
    if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
        failures.append(f"{context}: relative file receipt is not exact")
        return False
    absolute_item = {**item, "path": str(ROOT / str(item.get("path", "")))}
    require(item.get("path") == relative, f"{context}: relative path mismatch", failures)
    return verify_file_receipt(absolute_item, expected, context, failures)


def selected_usd_receipt(root: pathlib.Path, kind: str,
                         failures: list[str]) -> tuple[pathlib.Path | None, dict]:
    """Resolve exactly one immutable, direct-child USD selector without aliases."""
    try:
        info = root.lstat()
        if root.is_symlink() or not stat.S_ISDIR(info.st_mode) or root.resolve() != root:
            raise ValueError("root is not a canonical real directory")
        selectors: list[pathlib.Path] = []
        for child in root.iterdir():
            child_info = child.lstat()
            if child.is_symlink():
                raise ValueError(f"indirect entry in selector root: {child.name}")
            if stat.S_ISDIR(child_info.st_mode):
                candidate = child / "selector.json"
                if candidate.exists() or candidate.is_symlink():
                    selectors.append(candidate)
        if len(selectors) != 1:
            raise ValueError(f"expected exactly one immutable selector, found {len(selectors)}")
        selector_path = selectors[0]
        label_root = selector_path.parent
        selector_info = selector_path.lstat()
        if selector_path.is_symlink() or not stat.S_ISREG(selector_info.st_mode) or \
                label_root.is_symlink() or label_root.resolve() != label_root:
            raise ValueError("selector or label directory is indirect")
        label = label_root.name
        if re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", label) is None:
            raise ValueError("selector label is unsafe")
        if {entry.name for entry in label_root.iterdir()} != {"receipt.json", "selector.json"}:
            raise ValueError("selected label directory tree is not exact")
        selector = load(selector_path, failures)
        if set(selector) != {"schema", "kind", "label", "receipt"} or \
                selector.get("schema") != USD_SELECTOR_SCHEMA or \
                selector.get("kind") != kind or selector.get("label") != label:
            raise ValueError("selector schema/kind/label is not exact")
        receipt_item = selector.get("receipt")
        if not isinstance(receipt_item, dict) or set(receipt_item) != {
                "path", "bytes", "sha256"} or receipt_item.get("path") != "receipt.json":
            raise ValueError("selector receipt identity is not exact")
        receipt_path = label_root / "receipt.json"
        receipt_info = receipt_path.lstat()
        if receipt_path.is_symlink() or not stat.S_ISREG(receipt_info.st_mode) or \
                receipt_item.get("bytes") != receipt_info.st_size or \
                receipt_item.get("sha256") != sha256(receipt_path):
            raise ValueError("selected receipt bytes differ from selector")
        receipt = load(receipt_path, failures)
        if receipt.get("label") != label:
            raise ValueError("selected receipt label differs")
        return receipt_path, receipt
    except (OSError, ValueError) as error:
        failures.append(f"USD {kind} immutable selector invalid: {error}")
        return None, {}


def verify_bundle_binding(binding: object, context: str, failures: list[str]) -> None:
    try:
        bundle_files = tuple(verify_m8.bundle_files())
        verify_m8.validate_public_split_manifest()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        failures.append(f"{context}: exact split/bundle contract invalid: {error}")
        return
    if not isinstance(binding, dict) or set(binding) != set(bundle_files):
        failures.append(f"{context}: bundle artifact set is not exact")
        return
    for relative in bundle_files:
        item = binding.get(relative)
        path = BUNDLE / relative
        if not isinstance(item, dict):
            failures.append(f"{context}/{relative}: file receipt missing")
            continue
        require(path.is_file(), f"{context}/{relative}: bundle file missing", failures)
        if not path.is_file():
            continue
        require(item.get("bytes") == path.stat().st_size,
                f"{context}/{relative}: byte length mismatch", failures)
        require(item.get("sha256") == sha256(path),
                f"{context}/{relative}: SHA-256 mismatch", failures)
        if item.get("path") is not None:
                require(pathlib.Path(str(item["path"])).resolve() == path.resolve(),
                    f"{context}/{relative}: path mismatch", failures)


def parse_time(value: object, context: str, failures: list[str]) -> dt.datetime | None:
    if not isinstance(value, str):
        failures.append(f"{context}: timestamp missing")
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        failures.append(f"{context}: invalid timestamp")
        return None
    if parsed.tzinfo is None:
        failures.append(f"{context}: timestamp has no timezone")
        return None
    return parsed.astimezone(dt.timezone.utc)


def verify_fallback_freeze(receipt: dict, failures: list[str]) -> None:
    source = receipt.get("sourceFreeze")
    if not isinstance(source, dict):
        failures.append("fallback source-freeze receipt is missing")
        return
    freeze_path = pathlib.Path(str(source.get("path", "")))
    if freeze_path != fallback_contract.CANONICAL_FREEZE_RECEIPT or freeze_path.is_symlink():
        failures.append(f"fallback source freeze must be exact canonical receipt: "
                        f"{fallback_contract.CANONICAL_FREEZE_RECEIPT}")
        return
    verify_file_receipt(source, fallback_contract.CANONICAL_FREEZE_RECEIPT,
                        "fallback source freeze", failures)
    freeze, rows, freeze_errors = fallback_contract.validate_canonical_source_freeze(
        ROOT, freeze_path, freeze_release.REQUIRED_PROJECT_PATHS,
        freeze_release.REQUIRED_UPSTREAM_PATHS, freeze_release.VOLATILE_GENERATED_OUTPUTS)
    failures.extend(f"fallback {error}" for error in freeze_errors)
    require(FALLBACK_FROZEN_PATHS.issubset(rows),
            "fallback canonical source freeze omits critical producer paths", failures)
    created = parse_time(receipt.get("createdUtc"), "fallback receipt createdUtc", failures)
    frozen = parse_time(freeze.get("created_utc"), "fallback source freeze created_utc", failures)
    if created is not None and frozen is not None:
        require(created >= frozen, "fallback receipt predates its source freeze", failures)


def verify_webdriver_transcript(path: pathlib.Path, family: str, browser: dict,
                                failures: list[str]) -> None:
    try:
        rows = [json.loads(line, object_pairs_hook=strict_json_object)
                for line in path.read_text().splitlines()]
    except (OSError, ValueError, json.JSONDecodeError):
        failures.append(f"{family} WebDriver transcript is unreadable")
        return
    session = browser.get("session", {})
    if not isinstance(session, dict):
        failures.append(f"{family} session receipt is missing")
        return
    failures.extend(fallback_contract.validate_transcript_rows(
        rows, family, str(session.get("navigationUrl", "")),
        str(session.get("requestedCapabilitiesSha256", ""))))
    responses: dict[str, list[object]] = {}
    requests: dict[str, list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("operation"), str):
            continue
        operation = row["operation"]
        payload = row.get("payload", {})
        if row.get("direction") == "response" and isinstance(payload, dict):
            body = payload.get("body", {})
            value = body.get("value", body) if isinstance(body, dict) else body
            responses.setdefault(operation, []).append(value)
        elif row.get("direction") == "request" and isinstance(payload, dict):
            requests.setdefault(operation, []).append(payload)
    session_values = responses.get("session.create", [])
    session_requests = requests.get("session.create", [])
    actual_capabilities = session_requests[0].get("body", {}).get(
        "capabilities", {}).get("alwaysMatch") if len(session_requests) == 1 else None
    family_root = pathlib.Path(str(browser.get("input", {}).get("path", ""))).resolve().parent
    download_dir = family_root / "downloads"
    if family == "firefox":
        expected_capabilities = {"browserName": "firefox", "moz:firefoxOptions": {
            "binary": "/Applications/Firefox.app/Contents/MacOS/firefox", "prefs": {
                "browser.download.folderList": 2, "browser.download.dir": str(download_dir),
                "browser.download.useDownloadDir": True,
                "browser.download.manager.showWhenStarting": False,
                "browser.helperApps.neverAsk.saveToDisk":
                    "application/x-blender,application/octet-stream", "pdfjs.disabled": True}}}
    else:
        expected_capabilities = {"browserName": "safari"}
    require(actual_capabilities == expected_capabilities
            and fallback_contract.json_sha256(expected_capabilities) ==
                session.get("requestedCapabilitiesSha256"),
            f"{family} exact requested capabilities/download isolation mismatch", failures)
    observed = session_values[0].get("capabilities", {}) if len(session_values) == 1 \
        and isinstance(session_values[0], dict) else {}
    require(str(observed.get("browserName", "")) == session.get("observedBrowserName")
            and str(observed.get("browserVersion", "")) == session.get("observedBrowserVersion")
            and str(observed.get("platformName", "")) == session.get("observedPlatform"),
            f"{family} transcript capabilities response differs from receipt", failures)
    session_id = session_values[0].get("sessionId") if len(session_values) == 1 \
        and isinstance(session_values[0], dict) else None
    require(isinstance(session_id, str)
            and hashlib.sha256(session_id.encode()).hexdigest() == session.get("sessionIdSha256"),
            f"{family} transcript session identity differs from receipt", failures)
    bundle_values = responses.get("bundle.probe", [])
    loaded_artifacts = browser.get("requests", {}).get("browserLoadedArtifacts")
    expected_bundle_specs = [{"name": row.get("name"), "bytes": row.get("bytes"),
                              "sha256": row.get("sha256")}
                             for row in loaded_artifacts] \
        if isinstance(loaded_artifacts, list) and all(isinstance(row, dict)
                                                      for row in loaded_artifacts) else None
    bundle_requests = requests.get("bundle.probe", [])
    require(len(bundle_values) == 1 and isinstance(bundle_values[0], dict)
            and bundle_values[0].get("ok") is True
            and bundle_values[0].get("artifacts") == loaded_artifacts
            and len(bundle_requests) == 1
            and bundle_requests[0].get("body", {}).get("args") == [expected_bundle_specs],
            f"{family} transcript browser-loaded bundle ledger differs from receipt", failures)
    environment_values = responses.get("environment.probe", [])
    environment = environment_values[0] if len(environment_values) == 1 else {}
    require(isinstance(environment, dict) and environment == {
        "secure": True, "coi": True, "sab": True, "opfs": True, "fsa": False,
        "observerSchema": 1, "observerPreload": True},
        f"{family} transcript environment proof is incomplete", failures)
    product_values = responses.get("product.probe", [])
    renderer = browser.get("renderer", {})
    def semantic(value: object) -> dict[str, object]:
        return {key: value.get(key) for key in (
            "active", "objectCount", "objects", "meshVertices", "mode", "renderEngine")} \
            if isinstance(value, dict) else {}
    require(len(product_values) == 2 and all(isinstance(value, dict)
            and all(value.get(key) is True for key in ("ok", "workerDevice", "presented", "backend"))
            for value in product_values)
            and semantic(product_values[0].get("scene")) == renderer.get("initialScene")
            and semantic(product_values[1].get("scene")) == renderer.get("reloadScene"),
            f"{family} transcript Blender product proof differs from receipt", failures)
    nonce_name = browser.get("storage", {}).get("nonceName")
    exact_script_args = {
        "boot.wait": [[], []],
        "environment.probe": [[]],
        "product.probe": [[], []],
        "store.before": [[]],
        "open.install": [[nonce_name]],
        "store.after_open": [[]],
        "store.before_download_reopen": [[]],
        "download.reopen.install": [[browser.get("download", {}).get("suggestedName")]],
        "store.after_download_reopen": [[]],
        "download.install": [[browser.get("download", {}).get("suggestedName")]],
        "store.reload": [[nonce_name]],
        "diagnostics.final": [[]],
    }
    for operation, expected_args in exact_script_args.items():
        actual_args = [row.get("body", {}).get("args") for row in requests.get(operation, [])]
        require(actual_args == expected_args,
                f"{family} transcript script arguments mismatch: {operation}", failures)
    for operation in ("open.wait", "download.wait", "download.reopen.wait"):
        require(bool(requests.get(operation)) and all(
            row.get("body", {}).get("args") == [] for row in requests.get(operation, [])),
            f"{family} transcript polling arguments mismatch: {operation}", failures)
    before_values = responses.get("store.before", [])
    require(len(before_values) == 1 and isinstance(before_values[0], dict)
            and before_values[0].get("ok") is True
            and nonce_name not in before_values[0].get("items", []),
            f"{family} transcript does not prove clean nonce OPFS state", failures)
    open_values = responses.get("open.wait", [])
    input_bytes = browser.get("input", {}).get("bytes")
    require(bool(open_values) and isinstance(open_values[-1], dict)
            and open_values[-1].get("error") is None
            and open_values[-1].get("result", {}).get("name") == nonce_name
            and open_values[-1].get("result", {}).get("size") == input_bytes,
            f"{family} transcript input open is not nonce/byte bound", failures)
    download_values = responses.get("download.wait", [])
    download = browser.get("download", {})
    require(bool(download_values) and isinstance(download_values[-1], dict)
            and download_values[-1].get("error") is None
            and download_values[-1].get("via") == "download"
            and download_values[-1].get("ack", {}).get("name") == download.get("suggestedName")
            and download_values[-1].get("ack", {}).get("size") == download.get("ackBytes"),
            f"{family} transcript does not prove a real download request", failures)
    before_reopen_values = responses.get("store.before_download_reopen", [])
    require(len(before_reopen_values) == 1 and isinstance(before_reopen_values[0], dict)
            and before_reopen_values[0].get("ok") is True
            and before_reopen_values[0].get("items", []).count(nonce_name) == 1
            and download.get("suggestedName") not in before_reopen_values[0].get("items", []),
            f"{family} transcript does not prove clean downloaded-file reopen nonce", failures)
    download_reopen_values = responses.get("download.reopen.wait", [])
    semantic_reopen = download.get("semanticReopen", {})
    require(bool(download_reopen_values) and isinstance(download_reopen_values[-1], dict)
            and download_reopen_values[-1].get("error") is None
            and download_reopen_values[-1].get("result", {}).get("name") ==
                download.get("suggestedName")
            and download_reopen_values[-1].get("result", {}).get("size") ==
                download.get("artifact", {}).get("bytes"),
            f"{family} transcript does not authoritatively reopen downloaded bytes", failures)
    after_reopen_values = responses.get("store.after_download_reopen", [])
    require(len(after_reopen_values) == 1 and isinstance(after_reopen_values[0], dict)
            and after_reopen_values[0].get("ok") is True
            and after_reopen_values[0].get("list", {}).get("items", []).count(nonce_name) == 1
            and after_reopen_values[0].get("list", {}).get("items", []).count(
                download.get("suggestedName")) == 1
            and semantic(after_reopen_values[0].get("scene")) == semantic_reopen.get("scene"),
            f"{family} downloaded-file reopened scene/list differs from receipt", failures)
    reload_values = responses.get("store.reload", [])
    require(len(reload_values) == 1 and isinstance(reload_values[0], dict)
            and reload_values[0].get("ok") is True and reload_values[0].get("count") == 1
            and reload_values[0].get("opened", {}).get("name") == nonce_name
            and reload_values[0].get("opened", {}).get("size") == input_bytes,
            f"{family} transcript OPFS reload is incomplete", failures)
    diagnostic_values = responses.get("diagnostics.final", [])
    require(len(diagnostic_values) == 1 and diagnostic_values[0] == {
        "observerSchema": 1, "observerPreload": True, "page": [], "external": [], "gpu": [],
        "productWorkerDevice": True, "productPresented": True},
        f"{family} transcript diagnostics are not exact and clean", failures)
    input_path = browser.get("input", {}).get("path")
    file_sets = requests.get("file.input.set", [])
    require(len(file_sets) == 1 and file_sets[0].get("body", {}).get("text") == input_path,
            f"{family} transcript file chooser is not bound to receipt input", failures)
    reopen_file_sets = requests.get("download.reopen.file.set", [])
    require(len(reopen_file_sets) == 1
            and reopen_file_sets[0].get("body", {}).get("text") ==
                download.get("artifact", {}).get("path"),
            f"{family} downloaded-file chooser is not bound to exact evidence artifact", failures)


def verify_usd_pair_label(browser: dict, native: dict, expected: str | None,
                          failures: list[str]) -> None:
    browser_label = browser.get("label")
    native_label = native.get("label")
    require(isinstance(browser_label, str) and browser_label == native_label,
            "USD browser/native selectors do not use the same release label", failures)
    if expected is not None:
        require(browser_label == expected,
                "USD selector label differs from the final release label", failures)


def verify_usd_receipts(failures: list[str], expected_release_label: str | None = None) -> None:
    browser_path, browser = selected_usd_receipt(USD_BROWSER_ROOT, "browser", failures)
    native_path, native = selected_usd_receipt(USD_NATIVE_ROOT, "native", failures)
    if not browser or not native:
        return
    verify_usd_pair_label(browser, native, expected_release_label, failures)
    browser_keys = {
        "schema", "verdict", "label", "createdUtc", "driver", "sourceFreeze",
        "browser_version", "runtime_adapter", "artifacts", "browser_loaded_artifacts", "url",
        "cross_origin_isolated", "result", "page_errors", "page_crashes",
        "external_requests", "http_errors", "gpu_errors", "console_tail",
    }
    require(set(browser) == browser_keys and browser.get("schema") ==
            "blender-web.m7-usd-browser.v3",
            "USD browser receipt schema/keys are not exact", failures)
    require(browser.get("verdict") == "PASS", "USD browser receipt is not PASS", failures)
    verify_m8.check_runtime_adapter(browser.get("runtime_adapter"), "USD browser", failures)
    verify_relative_file_receipt(browser.get("driver"), USD_DRIVER,
                                 "USD browser driver", failures)
    verify_fallback_freeze(browser, failures)
    expected_artifacts = {
        "js": ROOT / "build-wasm-windowed-opt/bin/blender_browser.js",
        "wasm": ROOT / "build-wasm-windowed-opt/bin/blender_browser.wasm",
        "data": ROOT / "build-wasm-windowed-opt/bin/blender_browser.data",
    }
    browser_artifacts = browser.get("artifacts", {})
    require(isinstance(browser_artifacts, dict) and set(browser_artifacts) == set(expected_artifacts),
            "USD browser artifact set is not exact", failures)
    for key, path in expected_artifacts.items():
        verify_relative_file_receipt(browser_artifacts.get(key), path,
                                     f"USD browser artifact {key}", failures)
    loaded = browser.get("browser_loaded_artifacts")
    require(isinstance(loaded, dict) and set(loaded) == set(expected_artifacts),
            "USD browser-loaded artifact set is not exact", failures)
    if isinstance(loaded, dict) and isinstance(browser_artifacts, dict):
        for key in expected_artifacts:
            item = loaded.get(key)
            host = browser_artifacts.get(key)
            require(isinstance(item, dict) and set(item) == {"status", "bytes", "sha256"}
                    and item.get("status") == 200 and isinstance(host, dict)
                    and item.get("bytes") == host.get("bytes")
                    and item.get("sha256") == host.get("sha256"),
                    f"USD browser-loaded artifact differs from host bytes: {key}", failures)
    result = browser.get("result", {})
    require(browser.get("cross_origin_isolated") is True,
            "USD browser was not cross-origin isolated", failures)
    require(browser.get("page_errors") == [] and browser.get("page_crashes") == []
            and browser.get("external_requests") == [] and browser.get("http_errors") == []
            and browser.get("gpu_errors") == [],
            "USD browser receipt recorded runtime errors", failures)
    require(isinstance(result, dict) and result.get("ok") is True
            and result.get("build_option_usd") is True
            and result.get("export") == ["FINISHED"] and result.get("import") == ["FINISHED"]
            and result.get("magic") == "#usda" and result.get("mesh_count") == 1
            and result.get("coords") == [[0, 0, 0], [0, 3, 0], [2, 0, 0]]
            and result.get("polygon_sizes") == [3] and result.get("bytes", 0) > 100,
            "USD real browser operator round-trip is incomplete", failures)
    require(isinstance(browser.get("console_tail"), list)
            and all(isinstance(value, str) for value in browser["console_tail"]),
            "USD browser console tail is invalid", failures)

    native_keys = {
        "schema", "verdict", "label", "createdUtc", "producer", "sourceFreeze",
        "source", "target", "buildDirectory", "platform", "ninja", "configuration",
        "cache", "graph", "archive", "capabilityObjects", "archiveMembers",
        "capabilityRuleSha256", "archiveInputs",
    }
    require(set(native) == native_keys and native.get("schema") ==
            "blender-web.m7-usd-native-capability.v2",
            "USD native receipt schema/keys are not exact", failures)
    require(native.get("verdict") == "PASS", "USD native receipt is not PASS", failures)
    verify_relative_file_receipt(native.get("producer"), USD_NATIVE_PRODUCER,
                                 "USD native producer", failures)
    verify_fallback_freeze(native, failures)
    expected_pin = subprocess.run(
        ["git", "-C", str(ROOT / "upstream"), "rev-parse", "HEAD"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    expected_head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    require(native.get("source") == {"projectHead": expected_head, "upstreamHead": expected_pin},
            "USD native receipt source pins are stale", failures)
    require(native.get("target") == "bf_io_usd",
            "USD native receipt target is not bf_io_usd", failures)
    require(native.get("buildDirectory") == str(ROOT / "build-native-gpu"),
            "USD native build directory is not canonical", failures)
    require(native.get("platform") == {"system": platform.system(), "machine": platform.machine()},
            "USD native platform identity is stale", failures)
    expected_config = {
        "buildType": "Release", "withUsd": True, "withPython": True,
        "withHydra": False, "withMaterialx": False,
        "definitions": ["WITH_USD", "WITH_USD_IMAGING", "WITH_USD_PYTHON_HOOKS"],
    }
    require(native.get("configuration") == expected_config,
            "USD native default capability profile is incomplete", failures)
    usd_tools = str(ROOT / "sandbox/m7-usd-prep")
    if usd_tools not in sys.path:
        sys.path.insert(0, usd_tools)
    try:
        import make_native_receipt
        current_facts = make_native_receipt.analyze(ROOT / "build-native-gpu")
        for key in ("cache", "graph", "archive", "capabilityObjects", "archiveMembers",
                    "capabilityRuleSha256", "archiveInputs", "configuration"):
            require(native.get(key) == current_facts.get(key),
                    f"USD native receipt is stale: {key}", failures)
    except Exception as error:
        failures.append(f"USD native producer revalidation failed: {error}")
    ninja_version = subprocess.run(
        ["ninja", "--version"], capture_output=True, text=True).stdout.strip()
    require(native.get("ninja") == {"version": ninja_version, "lockedDryRun": "no work to do"},
            "USD native Ninja identity/no-work claim is stale", failures)
    dry = subprocess.run(
        [str(ROOT / "scripts/ninja-locked.sh"), "-C", str(ROOT / "build-native-gpu"),
         "-n", "bf_io_usd"], cwd=ROOT, capture_output=True, text=True)
    dry_text = (dry.stdout + dry.stderr).strip()
    require(dry.returncode == 0 and "ninja: no work to do." in dry_text
            and "Re-running CMake" not in dry_text
            and re.search(r"\[[0-9]+/[0-9]+\]", dry_text) is None,
            "USD native locked graph is not at a no-work fixed point", failures)
    require(browser_path is not None and native_path is not None,
            "USD selected receipt paths are absent", failures)


def verify_fallback_receipt(failures: list[str]) -> None:
    schema = load(FALLBACK_SCHEMA, failures)
    if not schema:
        return
    current = pathlib.Path(FALLBACK_EVIDENCE.anchor)
    try:
        for part in FALLBACK_EVIDENCE.parts[1:]:
            current /= part
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or current.is_symlink():
                raise ValueError(f"indirect/non-directory path component: {current}")
        if FALLBACK_EVIDENCE.resolve() != FALLBACK_EVIDENCE:
            raise ValueError("fallback evidence root does not resolve to itself")
        label_entries = sorted(FALLBACK_EVIDENCE.iterdir())
    except (OSError, ValueError) as error:
        failures.append(f"fallback evidence root is not canonical: {error}")
        return
    require(len(label_entries) == 1,
            f"fallback evidence must contain exactly one label directory, found {len(label_entries)}",
            failures)
    if len(label_entries) != 1:
        return
    label_root = label_entries[0]
    try:
        label_info = label_root.lstat()
    except OSError as error:
        failures.append(f"fallback label directory is unreadable: {error}")
        return
    if label_root.is_symlink() or not stat.S_ISDIR(label_info.st_mode) or \
            label_root.resolve() != label_root or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]*", label_root.name):
        failures.append("fallback label is not a canonical real label directory")
        return
    selectors = [label_root / "selector.json"] if (label_root / "selector.json").is_file() else []
    require(len(selectors) == 1,
            f"fallback evidence must publish exactly one immutable per-label selector, found {len(selectors)}",
            failures)
    if len(selectors) != 1:
        return
    selector_path = selectors[0]
    if selector_path.is_symlink():
        failures.append("fallback selector must not be a symlink")
        return
    selector = load(selector_path, failures)
    if set(selector) != {"schema", "label", "path", "bytes", "sha256"} or \
            selector.get("schema") != fallback_contract.SELECTOR_SCHEMA:
        failures.append("fallback selector schema/keys are not exact")
        return
    label = selector.get("label")
    evidence_root = selector_path.parent
    require(isinstance(label, str) and evidence_root == FALLBACK_EVIDENCE / str(label),
            "fallback selector label/directory mismatch", failures)
    receipt_path = pathlib.Path(str(selector.get("path", "")))
    require(receipt_path.is_absolute() and os.path.normpath(str(receipt_path)) == str(receipt_path),
            "fallback selector receipt path is not canonical absolute", failures)
    require(receipt_path == evidence_root / "receipt.json",
            "fallback selector does not bind its own immutable receipt", failures)
    verify_file_receipt(selector, receipt_path, "fallback selector", failures)
    if failures:
        return
    receipt = load(receipt_path, failures)
    if not receipt:
        return
    require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
            "fallback receipt schema is not Draft 2020-12", failures)
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER).validate(receipt)
    except jsonschema.exceptions.SchemaError as error:
        failures.append(f"fallback receipt schema is invalid: {error.message}")
        return
    except jsonschema.exceptions.ValidationError as error:
        failures.append(
            f"fallback receipt does not satisfy exact schema at {list(error.path)}: {error.message}")
        return
    require(receipt.get("schema") == fallback_contract.SCHEMA and receipt.get("label") == label,
            "fallback receipt schema/label differs from selector", failures)
    require(pathlib.Path(str(receipt.get("evidenceRoot", ""))) == evidence_root,
            "fallback evidenceRoot is not its selector directory", failures)
    require(not (evidence_root / "INCOMPLETE").exists() and not (evidence_root / "FAILED.txt").exists(),
            "fallback evidence retains INCOMPLETE or FAILED sentinel", failures)
    expected_top = {"receipt.json", "selector.json", "firefox", "safari"}
    require({entry.name for entry in evidence_root.iterdir()} == expected_top,
            "fallback evidence root has missing/extra entries", failures)

    def snapshot_tree() -> dict[str, tuple[int, str]]:
        result: dict[str, tuple[int, str]] = {}
        for path in sorted(evidence_root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"symlink in immutable fallback evidence: {path}")
            info = path.lstat()
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise ValueError(f"non-file/directory in immutable fallback evidence: {path}")
            if path.is_file():
                result[path.relative_to(evidence_root).as_posix()] = (path.stat().st_size, sha256(path))
        return result

    try:
        initial_snapshot = snapshot_tree()
    except (OSError, ValueError) as error:
        failures.append(str(error))
        return
    verify_file_receipt(receipt.get("producer"), FALLBACK_PRODUCER, "fallback producer", failures)
    verify_fallback_freeze(receipt, failures)
    verify_bundle_binding(receipt.get("bundleArtifacts"), "fallback", failures)
    bundle = receipt.get("bundleArtifacts", {})
    bundle_digest = hashlib.sha256("".join(
        f"{name}\0{bundle[name]['bytes']}\0{bundle[name]['sha256']}\n" for name in sorted(bundle)
    ).encode()).hexdigest() if isinstance(bundle, dict) and bundle else ""
    server = receipt.get("server", {})
    base_url = server.get("baseUrl") if isinstance(server, dict) else None
    require(isinstance(base_url, str) and server.get("servedBundleSha256") == bundle_digest,
            "fallback server bundle digest is not bound to receipt artifacts", failures)
    server_artifacts = server.get("artifacts", {}) if isinstance(server, dict) else {}
    require(isinstance(server_artifacts, dict) and set(server_artifacts) == set(bundle),
            "fallback server artifact ledger is not exact", failures)
    if isinstance(server_artifacts, dict) and isinstance(bundle, dict) and isinstance(base_url, str):
        for name in sorted(bundle):
            observed = server_artifacts.get(name, {})
            expected = bundle[name]
            require(isinstance(observed, dict)
                    and observed.get("url") == base_url + "/" + name
                    and observed.get("status") == 200
                    and observed.get("bytes") == expected.get("bytes")
                    and observed.get("sha256") == expected.get("sha256")
                    and observed.get("bundleSha256") == bundle_digest,
                    f"fallback server ledger mismatch: {name}", failures)
    nonce = receipt.get("nonce")
    rows = receipt.get("browsers")
    if not isinstance(rows, list) or len(rows) != 2:
        failures.append("fallback receipt must contain exactly Firefox and Safari")
        return
    require([row.get("family") for row in rows if isinstance(row, dict)] == ["firefox", "safari"],
            "fallback browser rows must be ordered Firefox then Safari", failures)
    for family, row in zip(("firefox", "safari"), rows, strict=True):
        if not isinstance(row, dict):
            failures.append(f"{family} fallback row is not an object")
            continue
        family_root = evidence_root / family
        storage = row.get("storage", {})
        download = row.get("download", {})
        input_name = f"fallback-{label}-{nonce}.blend"
        save_name = f"fallback-save-{label}-{nonce}.blend"
        expected_family = {input_name, "webdriver-transcript.jsonl", "webdriver-service.log",
                           "initial-canvas.png", "interaction-canvas.png", "downloads"}
        require(family_root.is_dir() and {entry.name for entry in family_root.iterdir()} == expected_family,
                f"{family} evidence directory has missing/extra entries", failures)
        downloads = family_root / "downloads"
        require(downloads.is_dir() and {entry.name for entry in downloads.iterdir()} == {save_name},
                f"{family} isolated download directory is not exact", failures)
        require(storage.get("nonceName") == input_name and download.get("suggestedName") == save_name,
                f"{family} nonce-bound storage/download names mismatch", failures)
        binary = row.get("binary", {})
        canonical_binary = {
            "firefox": pathlib.Path("/Applications/Firefox.app/Contents/MacOS/firefox"),
            "safari": pathlib.Path("/Applications/Safari.app/Contents/MacOS/Safari"),
        }[family]
        verify_file_receipt(binary, canonical_binary, f"{family} binary", failures)
        app = {
            "firefox": pathlib.Path("/Applications/Firefox.app"),
            "safari": pathlib.Path("/Applications/Safari.app"),
        }[family]
        try:
            app_info = app.lstat()
            app_safe = stat.S_ISDIR(app_info.st_mode) and not app.is_symlink() and app.resolve() == app
        except OSError:
            app_safe = False
        require(app_safe, f"{family} app path is missing/indirect", failures)
        if app_safe:
            try:
                with (app / "Contents/Info.plist").open("rb") as handle:
                    info = plistlib.load(handle)
            except (OSError, plistlib.InvalidFileException) as error:
                failures.append(f"{family} app identity unreadable: {error}")
                info = {}
        else:
            info = {}
        expected_signing = {
            "firefox": {"identifier": "org.mozilla.firefox", "team": "43AQ936H96"},
            "safari": {"identifier": "com.apple.Safari", "team": "not set"},
        }[family]
        signing = row.get("signing", {})
        app_verify = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) if app_safe else None
        app_detail = subprocess.run(["codesign", "-dv", "--verbose=2", str(app)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) if app_safe else None
        require(info.get("CFBundleShortVersionString") == row.get("version")
                and info.get("CFBundleName") == row.get("product")
                and signing == {**expected_signing, "valid": True}
                and app_verify is not None and app_detail is not None
                and app_verify.returncode == 0 and app_detail.returncode == 0
                and f"Identifier={expected_signing['identifier']}" in app_detail.stdout
                and f"TeamIdentifier={expected_signing['team']}" in app_detail.stdout,
                f"{family} current signed app identity/version mismatch", failures)
        driver = row.get("automationDriver", {})
        artifact = driver.get("artifact", {}) if isinstance(driver, dict) else {}
        driver_path = pathlib.Path(str(artifact.get("path", "")))
        driver_safe = verify_file_receipt(
            artifact, driver_path, f"{family} automation driver", failures)
        driver_verify = subprocess.run(["codesign", "--verify", "--strict", str(driver_path)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) if driver_safe else None
        driver_detail = subprocess.run(["codesign", "-dv", "--verbose=2", str(driver_path)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) if driver_safe else None
        version_probe = subprocess.run([str(driver_path), "--version"], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT) if driver_safe else None
        current_version = version_probe.stdout.splitlines()[0].strip() \
            if version_probe is not None and version_probe.stdout.splitlines() else ""
        expected_driver_signing = {
            "firefox": {"identifier": fallback_contract.GECKODRIVER_IDENTIFIER,
                        "team": fallback_contract.GECKODRIVER_TEAM, "valid": True},
            "safari": {"identifier": "com.apple.safaridriver", "team": "not set", "valid": True},
        }[family]
        require(driver_verify is not None and driver_detail is not None and version_probe is not None
                and driver_verify.returncode == 0 and driver_detail.returncode == 0
                and version_probe.returncode == 0 and driver.get("version") == current_version
                and driver.get("signing") == expected_driver_signing
                and f"Identifier={expected_driver_signing['identifier']}" in driver_detail.stdout
                and f"TeamIdentifier={expected_driver_signing['team']}" in driver_detail.stdout,
                f"{family} signed/version-bound driver identity mismatch", failures)
        command = driver.get("launchCommand")
        require(driver.get("launchCommandSha256") == fallback_contract.json_sha256(command),
                f"{family} driver launch command hash mismatch", failures)
        if family == "firefox":
            require(driver_path.name == "geckodriver"
                    and fallback_contract.geckodriver_release_matches(
                        str(artifact.get("sha256", "")), current_version)
                    and isinstance(command, list) and len(command) == 5 and command[:4] ==
                        [str(driver_path), "--log", "trace", "--port"] and str(command[4]).isdigit(),
                    "Firefox driver is not the exact frozen official geckodriver launch", failures)
        else:
            require(driver_path == fallback_contract.SAFARIDRIVER
                    and current_version.startswith(f"Included with Safari {row.get('version')} ")
                    and isinstance(command, list) and len(command) == 3
                    and command[:2] == [str(driver_path), "--port"] and str(command[2]).isdigit(),
                    "Safari driver is not the canonical version-matched launch", failures)
        service_log = driver.get("serviceLog", {}) if isinstance(driver, dict) else {}
        verify_file_receipt(service_log, family_root / "webdriver-service.log",
                            f"{family} WebDriver service log", failures)
        if (family_root / "webdriver-service.log").is_file():
            fatal = re.findall(r"(?im)^.*\b(?:panic|fatal|uncaught)\b.*$",
                               (family_root / "webdriver-service.log").read_text(errors="replace"))
            require(not fatal, f"{family} WebDriver service log contains fatal errors", failures)
        session = row.get("session", {})
        require(session.get("observedBrowserVersion") == row.get("version")
                and family in str(session.get("observedBrowserName", "")).lower()
                and session.get("navigationUrl") == base_url + "/index.html?m7fallback=" + str(nonce),
                f"{family} session product/version/navigation binding mismatch", failures)
        input_item = row.get("input", {})
        verify_file_receipt(input_item, family_root / input_name, f"{family} input", failures)
        if FALLBACK_INPUT.is_file() and (family_root / input_name).is_file():
            require(input_item.get("bytes") == FALLBACK_INPUT.stat().st_size
                    and input_item.get("sha256") == sha256(FALLBACK_INPUT),
                    f"{family} input is not the exact source fixture", failures)
        artifact_item = download.get("artifact", {}) if isinstance(download, dict) else {}
        verify_file_receipt(artifact_item, downloads / save_name, f"{family} real download", failures)
        expected_browser_download = (downloads / save_name) if family == "firefox" else \
            (pathlib.Path.home() / "Downloads" / save_name).resolve()
        require(pathlib.Path(str(download.get("browserDownloadPath", ""))).resolve() ==
                expected_browser_download.resolve()
                and download.get("movedIntoEvidence") is (family == "safari"),
                f"{family} browser download source/recovery receipt mismatch", failures)
        if family == "safari":
            require(not expected_browser_download.exists(),
                    "Safari nonce download was not recoverably moved into immutable evidence", failures)
        if (downloads / save_name).is_file():
            data = (downloads / save_name).read_bytes()
            require(len(data) == download.get("ackBytes") and len(data) > 1000
                    and data[:4] == bytes.fromhex("28b52ffd"),
                    f"{family} real download bytes/magic mismatch", failures)
        renderer = row.get("renderer", {})
        semantic_reopen = download.get("semanticReopen", {}) \
            if isinstance(download, dict) else {}
        require(isinstance(semantic_reopen, dict)
                and semantic_reopen.get("nonceName") == save_name
                and semantic_reopen.get("absentBefore") is True
                and semantic_reopen.get("singleEntryAfter") is True
                and semantic_reopen.get("openBytes") == artifact_item.get("bytes")
                and semantic_reopen.get("scene") == renderer.get("initialScene"),
                f"{family} downloaded .blend lacks exact authoritative semantic reopen", failures)
        screenshot_records = (("initial", "initialScreenshot", "initialPixels", "initial-canvas.png"),
                              ("interaction", "interactionScreenshot", "interactionPixels", "interaction-canvas.png"))
        sampled: list[list[int]] = []
        for description, receipt_key, proof_key, filename in screenshot_records:
            item = renderer.get(receipt_key, {}) if isinstance(renderer, dict) else {}
            screenshot_path = family_root / filename
            verify_file_receipt(item, screenshot_path, f"{family} {description} screenshot", failures)
            if screenshot_path.is_file():
                try:
                    proof, values = fallback_contract.png_pixel_proof(screenshot_path.read_bytes())
                except (OSError, ValueError, zlib.error) as error:
                    failures.append(f"{family} {description} screenshot invalid: {error}")
                else:
                    require(proof == renderer.get(proof_key),
                            f"{family} {description} pixel proof differs from PNG", failures)
                    sampled.append(values)
        if len(sampled) == 2:
            require(fallback_contract.mean_absolute_difference(*sampled) ==
                    renderer.get("interactionMeanAbsoluteDifference")
                    and renderer.get("interactionMeanAbsoluteDifference", 0) > 0.5,
                    f"{family} product interaction pixel discriminator mismatch", failures)
        loaded = row.get("requests", {}).get("browserLoadedArtifacts", [])
        expected_loaded = []
        if isinstance(bundle, dict) and isinstance(base_url, str):
            for name in sorted(bundle):
                item = bundle[name]
                expected_loaded.append({"name": name, "url": base_url + "/" + name,
                    "status": 200, "bytes": item["bytes"], "sha256": item["sha256"],
                    "headerBytes": str(item["bytes"]), "headerSha256": item["sha256"],
                    "bundleSha256": bundle_digest})
        require(loaded == expected_loaded,
                f"{family} browser-loaded exact artifact ledger mismatch", failures)
        transcript = row.get("webdriverTranscript", {})
        transcript_path = family_root / "webdriver-transcript.jsonl"
        verify_file_receipt(transcript, transcript_path, f"{family} WebDriver transcript", failures)
        if transcript_path.is_file():
            verify_webdriver_transcript(transcript_path, family, row, failures)
    # Reject mid-verification mutation of evidence, source, or current staged bytes.
    try:
        require(snapshot_tree() == initial_snapshot,
                "fallback immutable evidence changed during verification", failures)
    except (OSError, ValueError) as error:
        failures.append(str(error))
    verify_fallback_freeze(receipt, failures)
    verify_bundle_binding(receipt.get("bundleArtifacts"), "fallback final recheck", failures)


def run_io_roundtrip(failures: list[str]) -> None:
    binary = ROOT / "build-wasm-cycles/bin/blender.js"
    wasm = ROOT / "build-wasm-cycles/bin/blender.wasm"
    for path in (binary, wasm):
        require(path.is_file(), f"missing wasm IO runner: {path.relative_to(ROOT)}", failures)
    if failures:
        return
    temp = pathlib.Path(tempfile.mkdtemp(prefix="bw-m7-io-"))
    try:
        env = os.environ.copy()
        env.update({
            "BLENDER_SYSTEM_RESOURCES": str(ROOT / "upstream"),
            "BLENDER_SYSTEM_PYTHON": str(ROOT / "lib/wasm"),
            "BLENDER_SYSTEM_SCRIPTS": str(ROOT / "upstream/scripts"),
            "BLENDER_SYSTEM_DATAFILES": str(ROOT / "upstream/release/datafiles"),
            "M7_OBJ": str(temp / "cube.obj"),
            "M7_GLB": str(temp / "cube.glb"),
        })
        commands = [
            ["node", str(binary), "--background", "--factory-startup", "--python",
             str(ROOT / "sandbox/m7-io-smoke/export_scene.py")],
        ]
        env.update({
            "M7_OBJ_IN": str(temp / "cube.obj"),
            "M7_GLB_IN": str(temp / "cube.glb"),
            "M7_OBJ_RT": str(temp / "cube-rt.obj"),
            "M7_GLB_RT": str(temp / "cube-rt.glb"),
        })
        commands.extend([
            ["node", str(binary), "--background", "--factory-startup", "--python",
             str(ROOT / "sandbox/m7-io-smoke/roundtrip_scene.py")],
            ["python3", str(ROOT / "sandbox/m7-io-smoke/parse_obj.py"),
             str(temp / "cube.obj"), str(temp / "cube-rt.obj")],
            ["python3", str(ROOT / "sandbox/m7-io-smoke/parse_glb.py"),
             str(temp / "cube.glb"), str(temp / "cube-rt.glb")],
        ])
        transcript = []
        for command in commands:
            result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            transcript.append(result.stdout)
            if result.returncode != 0:
                failures.append("OBJ/glTF wasm round-trip failed: " + result.stdout[-800:].replace("\n", " "))
                return
        joined = "\n".join(transcript)
        for marker in (
            "OBJ_IMPORT_MESH verts=8 edges=12 polys=6 loops=24",
            "GLTF_IMPORT_MESH verts=24 edges=30 polys=12 loops=36",
            "OBJ_COMPARE", "GLB_COMPARE",
            "Draco is unavailable", "MeshOptimizer is unavailable",
        ):
            require(marker in joined, f"wasm IO transcript missing: {marker}", failures)
        require(joined.count("-> PASS") == 2, "OBJ/glTF semantic comparators did not both PASS", failures)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", action="store_true",
                        help="verify the public-preview M7 subset, not the full GOAL.md promise")
    parser.add_argument("--selfcheck", action="store_true",
                        help="validate the fail-closed receipt contracts without running product binaries")
    parser.add_argument("--release-label",
                        help="bind M7 evidence to the final aggregate run label (also reads FINAL_RUN_LABEL)")
    args = parser.parse_args()
    if args.selfcheck:
        schema = load(FALLBACK_SCHEMA, [])
        producer_check = subprocess.run(
            [sys.executable, str(FALLBACK_PRODUCER), "--selfcheck"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        native_producer_check = subprocess.run(
            [sys.executable, str(USD_NATIVE_PRODUCER), "--selfcheck"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        browser_properties = schema.get("$defs", {}).get("browser", {}).get("properties", {})
        capabilities = {"browserName": "firefox"}
        capabilities_sha = fallback_contract.json_sha256(capabilities)
        navigation_url = "http://127.0.0.1:1/index.html?m7fallback=" + "a" * 32
        session_id = "selfcheck-session"
        rows: list[dict] = []
        sequence = 0
        async_scripts = {"bundle.probe", "product.probe", "store.before",
                         "store.after_open", "store.before_download_reopen",
                         "store.after_download_reopen", "store.reload"}
        def pair(operation: str, method: str, path: str, body: object,
                 value: object = True) -> None:
            nonlocal sequence
            sequence += 1
            rows.append({"sequence": sequence, "direction": "request", "operation": operation,
                         "payload": {"method": method, "path": path, "body": body}})
            sequence += 1
            rows.append({"sequence": sequence, "direction": "response", "operation": operation,
                         "payload": {"status": 200, "body": {"value": value}}})
        prefix = f"/session/{session_id}"
        for operation in fallback_contract.EXPECTED_PHASES:
            if operation == "webdriver.status":
                pair(operation, "GET", "/status", None, {"ready": True})
            elif operation == "session.create":
                pair(operation, "POST", "/session", {"capabilities": {"alwaysMatch": capabilities}},
                     {"sessionId": session_id, "capabilities": {"browserName": "firefox",
                                                                  "browserVersion": "1",
                                                                  "platformName": "mac"}})
            elif operation == "session.timeouts":
                pair(operation, "POST", prefix + "/timeouts",
                     {"script": 240000, "pageLoad": 240000, "implicit": 0})
            elif operation == "navigation.open":
                pair(operation, "POST", prefix + "/url", {"url": navigation_url})
            elif operation == "navigation.refresh":
                pair(operation, "POST", prefix + "/refresh", {})
            elif operation == "session.delete":
                pair(operation, "DELETE", prefix, None)
            elif operation in fallback_contract.SCRIPT_BY_OPERATION:
                endpoint = "/execute/async" if operation in async_scripts else "/execute/sync"
                pair(operation, "POST", prefix + endpoint,
                     {"script": fallback_contract.SCRIPT_BY_OPERATION[operation], "args": []})
            elif operation == "canvas.screenshot.initial":
                pair(operation, "POST", prefix + "/element",
                     {"using": "css selector", "value": "#canvas"}, {"element-6066-11e4-a52e-4f735466cecf": "e"})
                pair(operation, "GET", prefix + "/element/e/screenshot", None, "png")
            elif operation == "canvas.screenshot.interaction":
                pair(operation, "GET", prefix + "/element/e/screenshot", None, "png")
            elif operation.endswith(".find"):
                selector = {"open.button.find": "#bw_fallback_capture_open",
                            "file.input.find": "input[type=file]",
                            "download.button.find": "#bw_fallback_capture_save",
                            "download.reopen.button.find": "#bw_fallback_capture_open",
                            "download.reopen.file.find": "input[type=file]"}[operation]
                pair(operation, "POST", prefix + "/element", {"using": "css selector", "value": selector},
                     {"element-6066-11e4-a52e-4f735466cecf": "e"})
            elif operation.endswith(".click"):
                pair(operation, "POST", prefix + "/element/e/click", {})
            elif operation == "file.input.set":
                pair(operation, "POST", prefix + "/element/e/value", {"text": "/fixture", "value": list("/fixture")})
            elif operation == "download.reopen.file.set":
                pair(operation, "POST", prefix + "/element/e/value",
                     {"text": "/download", "value": list("/download")})
            elif operation == "canvas.orbit":
                actions = json.loads(json.dumps(fallback_contract.ORBIT_ACTIONS))
                actions["actions"][0]["actions"][0]["origin"]["element-6066-11e4-a52e-4f735466cecf"] = "e"
                pair(operation, "POST", prefix + "/actions", actions)
            else:
                raise AssertionError(operation)
        transcript_negatives: list[str] = []
        assert fallback_contract.validate_transcript_rows(
            rows, "firefox", navigation_url, capabilities_sha) == []
        def rejects(name: str, mutated: list[dict]) -> None:
            if fallback_contract.validate_transcript_rows(
                    mutated, "firefox", navigation_url, capabilities_sha):
                transcript_negatives.append(name)
            else:
                raise AssertionError(f"false-green transcript fixture passed: {name}")
        rejects("four_request_fabrication", rows[:8])
        mutated = json.loads(json.dumps(rows)); mutated[9]["sequence"] = 999
        rejects("sequence_gap", mutated)
        mutated = json.loads(json.dumps(rows));
        script_row = next(row for row in mutated if row["direction"] == "request"
                          and row["operation"] == "environment.probe")
        script_row["payload"]["body"]["script"] += "//tamper"
        rejects("script_alias", mutated)
        mutated = json.loads(json.dumps(rows));
        session_row = next(row for row in mutated if row["direction"] == "request"
                           and row["operation"] == "session.create")
        session_row["payload"]["body"]["capabilities"]["alwaysMatch"]["browserName"] = "alias"
        rejects("capability_rebind", mutated)
        mutated = json.loads(json.dumps(rows)); mutated[-1]["payload"]["status"] = 500
        rejects("failed_response", mutated)
        mutated = json.loads(json.dumps(rows))
        find_row = next(row for row in mutated if row["direction"] == "request"
                        and row["operation"] == "open.button.find")
        find_row["payload"]["body"]["value"] = "#alias"
        rejects("selector_alias", mutated)
        mutated = json.loads(json.dumps(rows))
        find_response = next(row for row in mutated if row["direction"] == "response"
                             and row["operation"] == "open.button.find")
        find_response["payload"]["body"]["value"][fallback_contract.ELEMENT_KEY] = "other"
        rejects("element_id_rebind", mutated)
        mutated = json.loads(json.dumps(rows))
        orbit_row = next(row for row in mutated if row["direction"] == "request"
                         and row["operation"] == "canvas.orbit")
        orbit_row["payload"]["body"]["actions"][0]["actions"][2]["x"] = 79
        rejects("orbit_alias", mutated)
        mutated = json.loads(json.dumps(rows))
        interaction_row = next(row for row in mutated if row["direction"] == "request"
                               and row["operation"] == "canvas.screenshot.interaction")
        interaction_row["payload"]["path"] = prefix + "/element/other/screenshot"
        rejects("screenshot_rebind", mutated)
        mutated = json.loads(json.dumps(rows))
        product_offset = next(index for index, row in enumerate(mutated)
                              if row["direction"] == "request" and row["operation"] == "product.probe")
        mutated[product_offset:product_offset] = json.loads(json.dumps(
            mutated[product_offset:product_offset + 2]))
        for index, row in enumerate(mutated, 1):
            row["sequence"] = index
        rejects("unauthorized_repeat", mutated)
        boundary_negatives: list[str] = []
        original_evidence, original_schema = FALLBACK_EVIDENCE, FALLBACK_SCHEMA
        with tempfile.TemporaryDirectory(prefix="m7-fallback-boundary-") as temporary:
            fixture = pathlib.Path(temporary).resolve()
            schema_path = fixture / "schema.json"
            schema_path.write_text('{"fixture":true}\n', encoding="utf-8")
            evidence = fixture / "fallback-evidence"
            label_root = evidence / "fixture-label"
            label_root.mkdir(parents=True)
            receipt_path = label_root / "receipt.json"
            receipt_path.write_text("{}\n", encoding="utf-8")
            receipt_bytes = receipt_path.read_bytes()
            selector = {"schema": fallback_contract.SELECTOR_SCHEMA,
                        "label": label_root.name, "path": str(receipt_path),
                        "bytes": len(receipt_bytes),
                        "sha256": hashlib.sha256(receipt_bytes).hexdigest()}
            (label_root / "selector.json").write_text(
                json.dumps(selector), encoding="utf-8")
            try:
                globals()["FALLBACK_EVIDENCE"] = evidence
                globals()["FALLBACK_SCHEMA"] = schema_path
                actual_failures: list[str] = []
                verify_fallback_receipt(actual_failures)
                assert any("empty JSON object" in failure for failure in actual_failures)
                boundary_negatives.append("empty_receipt")

                schema_path.write_text("{}\n", encoding="utf-8")
                actual_failures = []
                verify_fallback_receipt(actual_failures)
                assert any("empty JSON object" in failure for failure in actual_failures)
                boundary_negatives.append("empty_schema")
                schema_path.write_text('{"fixture":true}\n', encoding="utf-8")

                forged_freeze = fixture / "forged-freeze.json"
                forged_freeze.write_text('{"verdict":"PASS"}\n', encoding="utf-8")
                actual_failures = []
                verify_fallback_freeze({
                    "sourceFreeze": {
                        "path": str(forged_freeze),
                        "bytes": forged_freeze.stat().st_size,
                        "sha256": sha256(forged_freeze),
                    },
                    "createdUtc": "2026-08-15T00:00:00Z",
                }, actual_failures)
                assert any("exact canonical receipt" in failure
                           for failure in actual_failures)
                boundary_negatives.append("external_forged_freeze")

                frozen_root = fixture / "frozen-source"
                frozen_root.mkdir()
                frozen_file = frozen_root / "tracked.bin"
                frozen_file.write_bytes(b"frozen bytes")
                frozen_manifest = fixture / "frozen.manifest.jsonl"
                frozen_manifest.write_text(json.dumps({
                    "mode": "100644", "path": "tracked.bin",
                    "sha256": hashlib.sha256(b"frozen bytes").hexdigest(),
                    "size": len(b"frozen bytes"),
                }) + "\n", encoding="utf-8")
                outside_frozen = fixture / "outside-frozen.bin"
                outside_frozen.write_bytes(b"frozen bytes")
                frozen_file.unlink()
                frozen_file.symlink_to(outside_frozen)
                manifest_failures: list[str] = []
                fallback_contract._validate_manifest_current(
                    frozen_root, frozen_manifest, set(), manifest_failures)
                assert any("regular-file type/mode mismatch" in failure
                           for failure in manifest_failures)
                boundary_negatives.append("frozen_regular_to_symlink")

                outside_label = fixture / "outside-label"
                label_root.rename(outside_label)
                label_root.symlink_to(outside_label, target_is_directory=True)
                actual_failures = []
                verify_fallback_receipt(actual_failures)
                assert any("canonical real label directory" in failure
                           for failure in actual_failures)
                boundary_negatives.append("symlink_label")

                real_parent = fixture / "real-parent"
                real_evidence = real_parent / "fallback-evidence"
                real_evidence.mkdir(parents=True)
                alias_parent = fixture / "alias-parent"
                alias_parent.symlink_to(real_parent, target_is_directory=True)
                globals()["FALLBACK_EVIDENCE"] = alias_parent / "fallback-evidence"
                actual_failures = []
                verify_fallback_receipt(actual_failures)
                assert any("evidence root is not canonical" in failure
                           for failure in actual_failures)
                boundary_negatives.append("symlink_parent")

                regular = fixture / "regular.bin"
                regular.write_bytes(b"fixture")
                leaf_alias = fixture / "leaf-alias.bin"
                leaf_alias.symlink_to(regular)
                item = {"path": str(leaf_alias), "bytes": 7,
                        "sha256": hashlib.sha256(b"fixture").hexdigest()}
                actual_failures = []
                verify_file_receipt(item, leaf_alias, "fixture leaf", actual_failures)
                assert actual_failures
                boundary_negatives.append("symlink_file")

                real_files = fixture / "real-files"
                real_files.mkdir()
                (real_files / "payload.bin").write_bytes(b"fixture")
                alias_files = fixture / "alias-files"
                alias_files.symlink_to(real_files, target_is_directory=True)
                indirect = alias_files / "payload.bin"
                item = {"path": str(indirect), "bytes": 7,
                        "sha256": hashlib.sha256(b"fixture").hexdigest()}
                actual_failures = []
                verify_file_receipt(item, indirect, "fixture parent", actual_failures)
                assert actual_failures
                boundary_negatives.append("symlink_file_parent")
            finally:
                globals()["FALLBACK_EVIDENCE"] = original_evidence
                globals()["FALLBACK_SCHEMA"] = original_schema
        garbage_rows = json.loads(json.dumps(rows))
        garbage_response = next(row for row in garbage_rows if row["direction"] == "response"
                                and row["operation"] == "download.reopen.wait")
        garbage_response["payload"]["body"]["value"] = {
            "error": "invalid or corrupt .blend", "result": None}
        with tempfile.TemporaryDirectory(prefix="m7-garbage-download-") as temporary:
            transcript_path = pathlib.Path(temporary) / "webdriver.jsonl"
            transcript_path.write_text("".join(json.dumps(row) + "\n" for row in garbage_rows),
                                       encoding="utf-8")
            garbage_browser = {
                "session": {"navigationUrl": navigation_url,
                            "requestedCapabilitiesSha256": capabilities_sha},
                "input": {"path": "/fixture/input.blend", "bytes": 2000},
                "storage": {"nonceName": "fallback-fixture-" + "a" * 32 + ".blend"},
                "download": {"suggestedName": "fallback-save-fixture-" + "a" * 32 + ".blend",
                             "artifact": {"path": "/download", "bytes": 2000},
                             "semanticReopen": {"scene": {}}},
                "requests": {"browserLoadedArtifacts": []}, "renderer": {},
            }
            actual_failures = []
            verify_webdriver_transcript(
                transcript_path, "firefox", garbage_browser, actual_failures)
            assert any("authoritatively reopen downloaded bytes" in failure
                       for failure in actual_failures)
            boundary_negatives.append("garbage_download")
        usd_selector_negatives: list[str] = []
        with tempfile.TemporaryDirectory(prefix="m7-usd-selector-selfcheck-") as temporary:
            fixture_root = pathlib.Path(temporary).resolve()

            def make_selector_root(name: str) -> tuple[pathlib.Path, pathlib.Path]:
                root = fixture_root / name
                (root / "historical").mkdir(parents=True)
                (root / "historical/receipt.json").write_text(
                    '{"label":"historical"}\n', encoding="utf-8")
                selected = root / "fresh"
                selected.mkdir()
                receipt = selected / "receipt.json"
                receipt.write_text('{"label":"fresh"}\n', encoding="utf-8")
                payload = receipt.read_bytes()
                selector = {"schema": USD_SELECTOR_SCHEMA, "kind": "browser",
                            "label": "fresh", "receipt": {"path": "receipt.json",
                            "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}}
                (selected / "selector.json").write_text(
                    json.dumps(selector), encoding="utf-8")
                return root, selected

            positive_root, _ = make_selector_root("positive")
            selector_failures: list[str] = []
            selected_path, selected = selected_usd_receipt(
                positive_root, "browser", selector_failures)
            assert not selector_failures and selected_path is not None \
                and selected.get("label") == "fresh"

            no_selector = fixture_root / "none"
            no_selector.mkdir()
            selector_failures = []
            selected_usd_receipt(no_selector, "browser", selector_failures)
            assert selector_failures
            usd_selector_negatives.append("missing_selector")

            tampered_root, tampered = make_selector_root("tampered")
            (tampered / "receipt.json").write_text(
                '{"label":"fresh","tampered":true}\n', encoding="utf-8")
            selector_failures = []
            selected_usd_receipt(tampered_root, "browser", selector_failures)
            assert selector_failures
            usd_selector_negatives.append("receipt_tamper")

            duplicate_root, _ = make_selector_root("duplicate")
            second = duplicate_root / "second"
            second.mkdir()
            (second / "receipt.json").write_text('{"label":"second"}\n', encoding="utf-8")
            second_payload = (second / "receipt.json").read_bytes()
            (second / "selector.json").write_text(json.dumps({
                "schema": USD_SELECTOR_SCHEMA, "kind": "browser", "label": "second",
                "receipt": {"path": "receipt.json", "bytes": len(second_payload),
                            "sha256": hashlib.sha256(second_payload).hexdigest()},
            }), encoding="utf-8")
            selector_failures = []
            selected_usd_receipt(duplicate_root, "browser", selector_failures)
            assert selector_failures
            usd_selector_negatives.append("multiple_selectors")

            alias_root, alias_label = make_selector_root("alias")
            outside = fixture_root / "outside-label"
            alias_label.rename(outside)
            alias_label.symlink_to(outside, target_is_directory=True)
            selector_failures = []
            selected_usd_receipt(alias_root, "browser", selector_failures)
            assert selector_failures
            usd_selector_negatives.append("label_symlink")

            extra_root, extra_label = make_selector_root("extra")
            (extra_label / "unlisted").write_text("extra", encoding="utf-8")
            selector_failures = []
            selected_usd_receipt(extra_root, "browser", selector_failures)
            assert selector_failures
            usd_selector_negatives.append("unlisted_sibling")

            wrong_root, wrong_label = make_selector_root("wrong-kind")
            selector = json.loads((wrong_label / "selector.json").read_text())
            selector["kind"] = "native"
            (wrong_label / "selector.json").write_text(json.dumps(selector), encoding="utf-8")
            selector_failures = []
            selected_usd_receipt(wrong_root, "browser", selector_failures)
            assert selector_failures
            usd_selector_negatives.append("wrong_kind")

            duplicate_key_root, duplicate_key_label = make_selector_root("duplicate-key")
            selector_text = (duplicate_key_label / "selector.json").read_text()
            selector_text = selector_text.replace('"kind": "browser"',
                                                  '"kind": "browser", "kind": "browser"')
            (duplicate_key_label / "selector.json").write_text(selector_text, encoding="utf-8")
            selector_failures = []
            selected_usd_receipt(duplicate_key_root, "browser", selector_failures)
            assert any("duplicate JSON key" in failure for failure in selector_failures)
            usd_selector_negatives.append("duplicate_json_key")

            pair_failures: list[str] = []
            verify_usd_pair_label({"label": "final-a"}, {"label": "final-b"},
                                  None, pair_failures)
            assert pair_failures
            usd_selector_negatives.append("cross_run_pair")

            pair_failures = []
            verify_usd_pair_label({"label": "final-a"}, {"label": "final-a"},
                                  "final-b", pair_failures)
            assert pair_failures
            usd_selector_negatives.append("aggregate_label_rebind")
        checks = (
            CRITICAL_WIRE_LIMIT == 15_000_000,
            schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
            schema.get("properties", {}).get("schema", {}).get("const") ==
                fallback_contract.SCHEMA,
            schema.get("properties", {}).get("browsers", {}).get("minItems") == 2,
            schema.get("properties", {}).get("browsers", {}).get("maxItems") == 2,
            "sourceFreeze" in schema.get("properties", {}),
            "producer" in schema.get("properties", {}),
            "automationDriver" in browser_properties,
            "webdriverTranscript" in browser_properties,
            "renderer" in browser_properties and "storage" in browser_properties
                and "download" in browser_properties and "errors" in browser_properties,
            schema.get("additionalProperties") is False,
            producer_check.returncode == 0,
            "M7_FALLBACK_CAPTURE_SELFCHECK_PASS" in producer_check.stdout,
            "positive=7 negative=10 browser_launches=0" in producer_check.stdout,
            native_producer_check.returncode == 0,
            len(transcript_negatives) == 10,
            len(boundary_negatives) == 9,
            len(usd_selector_negatives) == 9,
            strict_exit_code([], False) == 0,
            strict_exit_code(["fixture failure"], False) == 1,
            strict_exit_code(["strict-only fixture"], True) == 0,
        )
        if not all(checks):
            print("M7_PRODUCT_GATE_SELFCHECK_FAIL producer=" + producer_check.stdout.strip()
                  + " native=" + native_producer_check.stdout.strip())
            return 1
        print("M7_PRODUCT_GATE_SELFCHECK_PASS usd=required fallback=schema-v4 "
              "freeze=full-project selector=immutable-per-label transcript=ordered-exact "
              "negative=" + ",".join(transcript_negatives + boundary_negatives +
                                       usd_selector_negatives))
        return 0
    subset_failures: list[str] = []
    staged = load(STAGED_RECEIPT, subset_failures)
    files = load(FILES_RECEIPT, subset_failures)

    staged_required = (
        "cross_origin_isolated", "shared_array_buffer", "stage0_boot", "first_pixels_present",
        "stage1_byte_exact", "progress_phases_visible", "service_worker_complete",
        "offline_reload_wm_main", "query_python_disabled", "query_args_disabled",
        "minimal_loader_visible", "loader_font_loaded", "source_link_visible",
    )
    files_required = (
        "physical_drop_trusted", "physical_drop_opened", "fsa_open_picker_supported",
        "fsa_open_trusted_activation", "fsa_open_acceptance", "fallback_open_acceptance",
        "fsa_save_picker_supported", "fsa_save_trusted_activation", "fsa_save_acceptance",
        "fallback_save_acceptance", "opfs_reload_roundtrip",
    )
    require(staged.get("verdict") == "PASS", "staged browser receipt is not PASS", subset_failures)
    require(files.get("verdict") == "PASS", "files browser receipt is not PASS", subset_failures)
    staged_browser = staged.get("browser", {}) if isinstance(staged.get("browser"), dict) else {}
    verify_m8.check_runtime_adapter(
        staged_browser.get("runtime_adapter"), "M7 staged browser", subset_failures)
    verify_m8.check_runtime_adapter(
        files.get("runtime_adapter"), "M7 files browser", subset_failures)
    for key in staged_required:
        require(staged.get(key) is True, f"staged proof missing/false: {key}", subset_failures)
    for key in files_required:
        require(files.get(key) is True, f"file proof missing/false: {key}", subset_failures)
    require(staged.get("external_request_count") == 0, "staged runtime made external requests", subset_failures)
    require(files.get("external_request_count") == 0, "file runtime made external requests", subset_failures)
    require(files.get("gpu_error_count") == 0, "file runtime recorded GPU/page errors", subset_failures)
    require(files.get("schema") == "blender-web.m7-files-browser.v3",
            "files browser receipt schema is not hash-bound v3", subset_failures)
    identity = files.get("bundle_identity")
    verify_file_receipt(identity, BUNDLE_IDENTITY, "files browser bundle identity", subset_failures)
    if isinstance(identity, dict):
        require(identity.get("split_manifest_sha256") ==
                sha256(verify_m8.BUILD / verify_m8.SPLIT_MANIFEST),
                "files browser split-manifest identity is stale", subset_failures)
        require(identity.get("public_split_manifest_sha256") ==
                sha256(verify_m8.BUNDLE / verify_m8.BUNDLE_SPLIT_MANIFEST),
                "files browser public split-manifest identity is stale", subset_failures)
    verify_bundle_binding(files.get("bundle_artifacts"), "files browser", subset_failures)

    source_check = subprocess.run(
        ["python3", str(ROOT / "sandbox/m7-product-gate/verify_bundle_sources.py")],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    require(source_check.returncode == 0,
            "bundle/source binding failed: " + source_check.stdout.strip(), subset_failures)
    for script in (ROOT / "sandbox/m7-io-smoke/export_scene.py",
                   ROOT / "sandbox/m7-io-smoke/roundtrip_scene.py"):
        require("CTYPES_SHIM" not in script.read_text(),
                f"probe-only glTF ctypes shim returned: {script.relative_to(ROOT)}", subset_failures)
    run_io_roundtrip(subset_failures)

    if subset_failures:
        print(f"M7_PUBLIC_PREVIEW_SUBSET_FAIL count={len(subset_failures)}")
        for failure in subset_failures:
            print(" - " + failure)
        return 1

    strict_failures: list[str] = []
    opt_cache = (ROOT / "build-wasm-windowed-opt/CMakeCache.txt").read_text(errors="replace")
    require("WITH_USD:BOOL=ON" in opt_cache,
            "USD is absent: resolved shipping configuration must set WITH_USD=ON", strict_failures)
    release_label = args.release_label or os.environ.get("FINAL_RUN_LABEL")
    if release_label is not None and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", release_label) is None:
        strict_failures.append("final M7 release label is unsafe")
    verify_usd_receipts(strict_failures, release_label)
    strict_staged = load(STRICT_STAGED_RECEIPT, strict_failures)
    if strict_staged:
        require(strict_staged.get("schema") == 1 and strict_staged.get("verdict") == "PASS",
                "strict staged receipt is not schema-1 PASS", strict_failures)
        verify_bundle_binding(strict_staged.get("bundle_artifacts"), "strict staged", strict_failures)
        proof = strict_staged.get("proof", {})
        require(proof.get("stage0_first_pixels") is True,
                "stage 0 reaches WM_main but not displayed product pixels", strict_failures)
        require(proof.get("interactive_viewport_under_8s") is True,
                f"interactive viewport exceeds 8s ({proof.get('interactive_viewport_ms')} ms)", strict_failures)
        performance = strict_staged.get("performance", {})
        critical = performance.get("critical_brotli_bytes")
        critical_by_file = performance.get("critical_brotli_by_file")
        require(isinstance(critical, int) and 0 < critical <= CRITICAL_WIRE_LIMIT,
                f"critical wire bytes exceed {CRITICAL_WIRE_LIMIT}: {critical!r}", strict_failures)
        require(isinstance(critical_by_file, dict)
                and all(isinstance(value, int) and value > 0 for value in critical_by_file.values())
                and sum(critical_by_file.values()) == critical,
                "critical wire per-file receipt does not sum to the exact total", strict_failures)
    verify_fallback_receipt(strict_failures)

    if args.subset:
        print("M7_PUBLIC_PREVIEW_SUBSET_PASS files+OPFS+trusted-drop+FSA+fallback+OBJ+glTF+staging+offline "
              f"strict_additions=usd,stage0,critical-wire,cross-browser")
        return 0
    if not strict_failures:
        print("M7_STRICT_PASS files+USD+stage0+critical-wire+cross-browser+source-freeze")
        return 0
    print(f"M7_STRICT_FAIL subset=PASS count={len(strict_failures)}")
    for failure in strict_failures:
        print(" - " + failure)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
