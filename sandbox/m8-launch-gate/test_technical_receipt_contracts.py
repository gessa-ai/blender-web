#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser-free adversarial selfchecks for M8 receipt-only contracts."""

from __future__ import annotations

import tempfile
from pathlib import Path

import make_staged_receipt
import verify_m8


PRIMARY = {
    "filename": "blender_browser.wasm",
    "role": "primary",
    "sha256": "a" * 64,
    "critical": True,
}
DEFERRED = {
    "filename": "blender_browser.deferred.wasm",
    "role": "deferred",
    "sha256": "b" * 64,
    "critical": False,
}
CONTRACT = {"shipped_wasm": [PRIMARY, DEFERRED]}
WORKER_IDENTITY = {"bytes": 1234, "sha256": "c" * 64}


def request(url: str, at_ms: int) -> dict[str, object]:
    return {"url": url, "path": url.split("?", 1)[0], "at_ms": at_ms}


def transport_request(url: str, at_ms: int = 10, **overrides: object) -> dict[str, object]:
    path = str(overrides.pop("path", url.split("?", 1)[0]))
    row: dict[str, object] = {
        "url": url,
        "path": path,
        "method": "GET",
        "at_ms": at_ms,
        "bundle_artifact": path.removeprefix("/"),
        "response_count": 1,
        "response_url": url,
        "response_status": 200,
        "content_encoding": "br",
    }
    row.update(overrides)
    return row


def pthread_blob_fields() -> dict[str, object]:
    origin = "https://fixture.invalid"
    return {
        "page_origin": origin,
        "pthread_blob_proof": {
            "contract": "pthread-main-script-blob-v1",
            "sourcePath": "/bin/blender_browser.worker.js",
            "phase": "ready",
            **WORKER_IDENTITY,
            "factoryCalls": 1,
            "error": None,
        },
        "pthread_blob_workers": [
            {"url": f"blob:{origin}/{index}", "protocol": "blob:", "origin": origin,
             "kind": "dedicated-worker", "at_ms": 20 + index}
            for index in range(9)
        ],
        "pthread_blob_transport_valid": True,
        "pthread_blob_transport_failures": [],
    }


def phase_selfcheck() -> tuple[int, int]:
    expected = make_staged_receipt.expected_shard_requests(CONTRACT)
    positive = {
        "semantic_interaction_ms": 100,
        "expected_shard_requests": expected,
        "wasm_requests": [
            request("/bin/blender_browser.wasm", 10),
            request(f"/bin/blender_browser.deferred.wasm?sha256={'b' * 64}", 101),
        ],
    }
    assert make_staged_receipt.phase_request_failures(positive, CONTRACT) == []
    negatives = [
        {**positive, "wasm_requests": positive["wasm_requests"][:1]},
        {**positive, "wasm_requests": [positive["wasm_requests"][0],
                                       request(f"/bin/blender_browser.deferred.wasm?sha256={'b' * 64}", 100)]},
        {**positive, "wasm_requests": [positive["wasm_requests"][0],
                                       request("/bin/blender_browser.deferred.wasm", 101)]},
        {**positive, "wasm_requests": [*positive["wasm_requests"],
                                       request("/bin/blender_browser.wasm", 12)]},
        {**positive, "wasm_requests": [request("/bin/blender_browser.wasm", 101),
                                       positive["wasm_requests"][1]]},
        {**positive, "expected_shard_requests": []},
    ]
    for mutated in negatives:
        assert make_staged_receipt.phase_request_failures(mutated, CONTRACT), mutated
    return 1, len(negatives)


def critical_path_selfcheck() -> tuple[int, int]:
    mandatory = sorted((
        "/index.html",
        "/diagnostics-bootstrap.js",
        "/file-bridge.js",
        "/boot-windowed.js",
        "/pthread-main-loader.js",
        "/stage1-loader.js",
        "/service-worker-register.js",
        "/service-worker.js",
        "/fonts/bw-interface-sans.woff2",
        "/bin/blender_browser.js",
        "/bin/blender_browser.worker.js",
        "/bin/blender_browser.data",
        "/bin/blender_browser.wasm",
    ))
    bundle_files = sorted({
        name for path in mandatory for name in (
            path.removeprefix("/"), f"{path.removeprefix('/')}" + ".br")
    } | {
        "bin/blender_browser.deferred.wasm",
        "bin/blender_browser.deferred.wasm.br",
    })
    bundle_artifacts = {
        name: (WORKER_IDENTITY if name == "bin/blender_browser.worker.js" else
               {"bytes": 1, "sha256": "e" * 64})
        for name in bundle_files
    }
    requests = [transport_request(path, 10 + index) for index, path in enumerate(mandatory)]
    requests.append(transport_request(
        f"/bin/blender_browser.deferred.wasm?sha256={'b' * 64}", 101,
        path="/bin/blender_browser.deferred.wasm",
        bundle_artifact="bin/blender_browser.deferred.wasm",
    ))
    positive = {
        "semantic_interaction_ms": 100,
        "same_origin_requests": requests,
        "critical_paths": mandatory,
        "critical_transport_valid": True,
        "critical_transport_failures": [],
        "content_encoding": {path: "br" for path in mandatory},
        "wire_brotli": True,
        **pthread_blob_fields(),
    }
    actual, failures = make_staged_receipt.observed_critical_paths(
        positive, CONTRACT, bundle_files, bundle_artifacts)
    assert actual == mandatory and failures == []

    extra_path = "/extra.js"
    dynamic_paths = sorted((*mandatory, extra_path))
    dynamic_bundle = sorted((*bundle_files, "extra.js", "extra.js.br"))
    dynamic = {
        **positive,
        "same_origin_requests": [*requests, transport_request(extra_path, 90)],
        "critical_paths": dynamic_paths,
        "content_encoding": {**positive["content_encoding"], extra_path: "br"},
    }
    actual, failures = make_staged_receipt.observed_critical_paths(
        dynamic, CONTRACT, dynamic_bundle,
        {**bundle_artifacts, "extra.js": {"bytes": 1, "sha256": "f" * 64},
         "extra.js.br": {"bytes": 1, "sha256": "f" * 64}})
    assert actual == dynamic_paths and failures == []
    assert verify_m8.critical_path_failures(dynamic_paths, CONTRACT, dynamic_bundle) == []
    receipt_paths = {
        "critical_paths": dynamic_paths,
        "critical_paths_by_run": [mandatory, dynamic_paths, mandatory],
    }
    assert verify_m8.critical_path_receipt_failures(
        receipt_paths, CONTRACT, dynamic_bundle, 3) == []

    mutated_requests = [*requests, transport_request(extra_path, 90)]
    query_request = transport_request("/extra.js?v=1", 90, path="/extra.js")
    negatives = (
        (dynamic, bundle_files),
        ({**positive, "same_origin_requests": [*requests, requests[0]]}, bundle_files),
        ({**positive, "same_origin_requests": [*requests, query_request]}, dynamic_bundle),
        ({**dynamic, "same_origin_requests": [*requests,
                                               transport_request(extra_path, 90,
                                                                 response_count=0)]},
         dynamic_bundle),
        ({**dynamic, "same_origin_requests": mutated_requests,
          "critical_paths": mandatory}, dynamic_bundle),
        ({**positive, "pthread_blob_workers": positive["pthread_blob_workers"][:8]},
         bundle_files),
        ({**positive, "pthread_blob_proof": {
            **positive["pthread_blob_proof"], "sha256": "d" * 64}}, bundle_files),
        ({**positive, "page_origin": "https://other.invalid"}, bundle_files),
        ({**positive, "pthread_blob_workers": [
            *positive["pthread_blob_workers"][:-1],
            {**positive["pthread_blob_workers"][-1], "kind": "shared-worker"}]},
         bundle_files),
    )
    for row, files in negatives:
        artifacts = {name: (WORKER_IDENTITY if name == "bin/blender_browser.worker.js" else
                            {"bytes": 1, "sha256": "e" * 64}) for name in files}
        _, failures = make_staged_receipt.observed_critical_paths(
            row, CONTRACT, files, artifacts)
        assert failures, row
    assert verify_m8.critical_path_receipt_failures(
        {**receipt_paths, "critical_paths": mandatory}, CONTRACT, dynamic_bundle, 3)

    expected_static_brotli = {
        f"{path.removeprefix('/')}.br" for path in mandatory if not path.endswith(".wasm")
    }
    assert expected_static_brotli <= set(verify_m8.STATIC_BUNDLE_FILES)
    return 5, len(negatives) + 1


def exact_receipt_inventory_selfcheck() -> tuple[int, int]:
    with tempfile.TemporaryDirectory(
            prefix=".m8-receipt-selfcheck-", dir=verify_m8.SELF) as temporary:
        root = Path(temporary)
        (root / "a").write_bytes(b"a")
        recorded = {"a": verify_m8.identity(root / "a")}
        failures: list[str] = []
        verify_m8.receipt_matches_files({"files": recorded}, "files", root, ("a",), failures)
        assert failures == []
        failures = []
        verify_m8.receipt_matches_files(
            {"files": {**recorded, "unlisted": {"bytes": 0, "sha256": "0" * 64}}},
            "files", root, ("a",), failures,
        )
        assert any("inventory differs" in failure for failure in failures)
    return 1, 1


def generated_input_exclusion_selfcheck() -> tuple[int, int]:
    assert b"ledger/results/m8.json" in verify_m8.GENERATED_INPUT_PATHS
    assert b"reports/dashboard.md" in verify_m8.GENERATED_INPUT_PATHS
    negatives = (
        b"ledger/results/m0.json",
        b"ledger/results/m7.json",
        b"harness/run.sh",
        b"sandbox/m8-launch-gate/verify_m8.py",
    )
    for path in negatives:
        assert path not in verify_m8.GENERATED_INPUT_PATHS
        assert not path.startswith(verify_m8.GENERATED_INPUT_PREFIXES)
    return 2, len(negatives)


if __name__ == "__main__":
    positives = negatives = 0
    for positive, negative in (
            phase_selfcheck(), critical_path_selfcheck(), exact_receipt_inventory_selfcheck(),
            generated_input_exclusion_selfcheck()):
        positives += positive
        negatives += negative
    print(f"M8_TECHNICAL_RECEIPT_SELFCHECK_PASS positive={positives} negative={negatives}")
