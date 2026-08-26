#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bind M7's runtime/performance proofs to exact current source and bundle bytes."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import statistics
import subprocess
import tempfile
from pathlib import Path

import verify_m8


ROOT = verify_m8.ROOT
BUNDLE = verify_m8.BUNDLE
VERIFY_PATH = ROOT / "sandbox/m8-staged-deploy/artifacts/verify_staged.json"
PERF_PATH = ROOT / "sandbox/m8-staged-deploy/artifacts/measure_staged-4g.json"
OUT = verify_m8.ART / "current-staged-receipt.json"


def expected_shard_requests(contract: dict[str, object]) -> list[str]:
    return sorted(
        f"/bin/{row['filename']}?sha256={row['sha256']}"
        if row["role"] == "deferred" else f"/bin/{row['filename']}"
        for row in contract["shipped_wasm"]
    )


def phase_request_failures(row: dict, contract: dict[str, object]) -> list[str]:
    """Return precise errors for one performance run's split request evidence."""
    failures: list[str] = []
    expected = expected_shard_requests(contract)
    if row.get("expected_shard_requests") != expected:
        failures.append("declared expected shard URLs differ from finalizer inventory")
    requests = row.get("wasm_requests")
    if not isinstance(requests, list):
        return failures + ["wasm request evidence is absent"]
    actual = sorted(
        request.get("url") for request in requests
        if isinstance(request, dict) and isinstance(request.get("url"), str)
    )
    if len(actual) != len(requests) or actual != expected:
        failures.append("observed Wasm requests are not the exact singleton inventory URLs")
    interaction = row.get("semantic_interaction_ms")
    if not isinstance(interaction, (int, float)):
        failures.append("semantic interaction timestamp is absent")
        return failures
    by_url = {
        request.get("url"): request for request in requests if isinstance(request, dict)
    }
    for shard in contract["shipped_wasm"]:
        url = (f"/bin/{shard['filename']}?sha256={shard['sha256']}"
               if shard["role"] == "deferred" else f"/bin/{shard['filename']}")
        request = by_url.get(url, {})
        at = request.get("at_ms") if isinstance(request, dict) else None
        if not isinstance(at, (int, float)):
            failures.append(f"{url} has no request timestamp")
        elif shard["critical"] and at > interaction:
            failures.append(f"critical shard was requested after semantic interaction: {url}")
        elif not shard["critical"] and at <= interaction:
            failures.append(f"deferred shard was requested before/at semantic interaction: {url}")
    return failures


def observed_critical_paths(row: dict, contract: dict[str, object],
                            bundle_files: object) -> tuple[list[str], list[str]]:
    """Derive and independently validate every pre-semantic same-origin response."""
    failures: list[str] = []
    interaction = row.get("semantic_interaction_ms")
    if (not isinstance(interaction, (int, float)) or isinstance(interaction, bool) or
            not math.isfinite(interaction)):
        return [], ["semantic interaction timestamp is absent or invalid"]
    requests = row.get("same_origin_requests")
    if not isinstance(requests, list):
        return [], ["same-origin request evidence is absent"]
    critical: list[dict[str, object]] = []
    for index, request_row in enumerate(requests):
        if not isinstance(request_row, dict):
            failures.append(f"same-origin request {index} is not an object")
            continue
        at = request_row.get("at_ms")
        if (not isinstance(at, (int, float)) or isinstance(at, bool) or
                not math.isfinite(at) or at < 0):
            failures.append(f"same-origin request {index} has an invalid timestamp")
            continue
        if at <= interaction:
            critical.append(request_row)

    paths: list[str] = []
    seen: set[str] = set()
    encodings = row.get("content_encoding")
    if not isinstance(encodings, dict):
        failures.append("critical content-encoding evidence is absent")
        encodings = {}
    for index, request_row in enumerate(critical):
        path = request_row.get("path")
        url = request_row.get("url")
        if not isinstance(path, str):
            failures.append(f"critical request {index} has no URL path")
            continue
        paths.append(path)
        if path in seen:
            failures.append(f"critical request path was fetched more than once: {path}")
        seen.add(path)
        if url != path:
            failures.append(f"critical request has a query or noncanonical URL: {url!r}")
        if request_row.get("method") != "GET":
            failures.append(f"critical request is not GET: {path}")
        artifact = path.removeprefix("/")
        if request_row.get("bundle_artifact") != artifact:
            failures.append(f"critical response does not map to its exact bundle artifact: {path}")
        response_count = request_row.get("response_count")
        if response_count != 1 or isinstance(response_count, bool):
            failures.append(f"critical request has {response_count!r} responses: {path}")
        if request_row.get("response_url") != url:
            failures.append(f"critical response URL differs from its request: {path}")
        if request_row.get("response_status") != 200:
            failures.append(f"critical response status is not 200: {path}")
        if request_row.get("content_encoding") != "br" or encodings.get(path) != "br":
            failures.append(f"critical response is not Brotli encoded: {path}")

    paths.sort()
    failures.extend(verify_m8.critical_path_failures(paths, contract, bundle_files))
    if row.get("critical_paths") != paths:
        failures.append("declared critical paths differ from observed request evidence")
    if row.get("critical_transport_valid") is not True:
        failures.append("producer did not accept the observed critical transport")
    if row.get("critical_transport_failures") != []:
        failures.append("producer reported critical transport failures")
    if row.get("wire_brotli") is not True:
        failures.append("producer did not accept complete Brotli transport")
    return paths, failures


def brotli_size(path: Path) -> int:
    sibling = path.with_name(path.name + ".br")
    if sibling.is_file():
        # Reuse the exact production-wire sibling only after proving that it
        # decompresses to the current raw artifact. Mtime is not an identity.
        proc = subprocess.Popen(
            [str(verify_m8.PINNED_NODE), str(verify_m8.BROTLI_CODEC),
             "decode-stdout", str(sibling)], stdout=subprocess.PIPE)
        assert proc.stdout is not None
        digest = hashlib.sha256()
        while True:
            chunk = proc.stdout.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if proc.wait() == 0 and digest.hexdigest() == verify_m8.sha256(path):
            return sibling.stat().st_size
    with tempfile.TemporaryDirectory(prefix="bw-receipt-brotli-") as temporary:
        output = Path(temporary) / "asset.br"
        proc = subprocess.run(
            [str(verify_m8.PINNED_NODE), str(verify_m8.BROTLI_CODEC),
             "encode", str(path), str(output)], capture_output=True, text=True)
        if proc.returncode != 0 or not output.is_file():
            raise RuntimeError(f"deterministic Brotli q11/lgwin=24 failed for {path}")
        return output.stat().st_size


def main() -> int:
    proof = json.loads(VERIFY_PATH.read_text(encoding="utf-8"))
    perf = json.loads(PERF_PATH.read_text(encoding="utf-8"))
    contract = verify_m8.artifact_contract()
    build_files = contract["build_files"]
    bundle_files = contract["bundle_files"]
    expected_source = {
        name: verify_m8.identity(verify_m8.BUILD / name) for name in build_files
    }
    expected_bundle = {
        name: verify_m8.identity(BUNDLE / name) for name in bundle_files
    }
    bundle_digest = verify_m8.canonical_artifact_digest(expected_bundle)
    validation_failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            validation_failures.append(message)

    require(proof.get("schema") == 1, "runtime proof schema != 1")
    require(proof.get("source_artifacts") == expected_source,
            "runtime proof source identities do not match current build")
    require(proof.get("bundle_artifacts") == expected_bundle,
            "runtime proof bundle identities do not match current deploy tree")
    require(proof.get("served_bundle_sha256") == bundle_digest,
            "runtime proof did not execute the exact current served bundle")
    require(proof.get("verdict") == "PASS", "runtime proof verdict is not PASS")
    require(proof.get("failures") == [], "runtime proof reported failures")
    staged_browser = proof.get("browser", {}) if isinstance(proof.get("browser"), dict) else {}
    require(staged_browser.get("engine") == "chrome", "staged proof is not branded Chrome")
    verify_m8.check_runtime_identity(
        staged_browser.get("runtime_identity"), "chrome", staged_browser.get("executable"),
        staged_browser.get("version"), "staged composer runtime", validation_failures)
    verify_m8.check_runtime_adapter(
        staged_browser.get("runtime_adapter"), "staged composer", validation_failures)
    staged_diagnostics = proof.get("early_diagnostics", {})
    require(isinstance(staged_diagnostics, dict) and set(staged_diagnostics) == {
        "cold_online", "online_warm", "offline_cold"},
        "staged proof early-diagnostics scenario set is not exact")
    if isinstance(staged_diagnostics, dict):
        for name in ("cold_online", "online_warm", "offline_cold"):
            verify_m8.check_early_diagnostics(
                staged_diagnostics.get(name), f"staged composer {name}", validation_failures)

    require(perf.get("schema") == 1, "performance proof schema != 1")
    require(perf.get("source_artifacts") == expected_source,
            "performance proof source identities do not match current build")
    require(perf.get("bundle_artifacts") == expected_bundle,
            "performance proof bundle identities do not match current deploy tree")
    require(perf.get("served_bundle_sha256") == bundle_digest,
            "performance proof did not execute the exact current served bundle")
    require(perf.get("label") == "staged-4g", "performance proof label is not staged-4g")
    profile_valid = perf.get("profile") == {
        "download_bytes_per_second": 1_500_000,
        "upload_bytes_per_second": 750_000,
        "latency_ms": 40,
    }
    require(profile_valid, "performance proof does not use the exact pinned network profile")
    browser = perf.get("browser", {})
    require(browser.get("channel") == "chrome", "performance proof is not branded Chrome")
    require(browser.get("current_at_test") is True and
            browser.get("version") == browser.get("official_version"),
            "performance Chrome was not current at test time")
    require(browser.get("signing") == {
        "identifier": "com.google.Chrome", "team": "EQHXZ8M8AV", "valid": True,
    }, "performance Chrome signature is invalid")
    verify_m8.check_runtime_identity(
        browser.get("runtime_identity"), "chrome", browser.get("executable"),
        browser.get("version"), "performance composer runtime", validation_failures)
    verify_m8.check_runtime_adapter(
        browser.get("runtime_adapter"), "performance composer", validation_failures)
    require(staged_browser.get("runtime_identity") == browser.get("runtime_identity"),
            "staged/performance composer runtime identities differ")
    require(staged_browser.get("runtime_adapter") == browser.get("runtime_adapter"),
            "staged/performance composer WebGPU adapters differ")
    try:
        checked = dt.datetime.fromisoformat(str(browser["checked_at"]).replace("Z", "+00:00"))
        age = dt.datetime.now(dt.timezone.utc) - checked
        require(dt.timedelta(0) <= age <= dt.timedelta(days=7),
                "performance Chrome current-version check is older than 7 days")
    except (KeyError, TypeError, ValueError):
        require(False, "performance Chrome checked_at is invalid")

    scenario = perf.get("scenarios", {}).get("cold-1.5mbps", {})
    rows = scenario.get("runs", [])
    run_count = perf.get("runs")
    observed_path_sets: list[list[str]] = []
    require(isinstance(run_count, int) and run_count >= 3,
            "performance proof has fewer than 3 cold runs")
    require(isinstance(rows, list) and len(rows) == run_count,
            "performance proof row count does not match declared cold runs")
    if isinstance(rows, list):
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                require(False, f"performance run {index + 1} is not an object")
                continue
            require(isinstance(row.get("fp"), (int, float)),
                    f"performance run {index + 1} has no first-pixel time")
            require(row.get("pixel_proof", {}).get("pass") is True,
                    f"performance run {index + 1} lacks strict canvas pixels")
            require(row.get("semantic_interaction", {}).get("pass") is True and
                    isinstance(row.get("semantic_interaction_ms"), (int, float)),
                    f"performance run {index + 1} lacks semantic trusted interaction")
            require(row.get("manifest_phase_valid") is True,
                    f"performance run {index + 1} observed a wasm shard in the wrong phase")
            for failure in phase_request_failures(row, contract):
                require(False, f"performance run {index + 1}: {failure}")
            observed_paths, transport_failures = observed_critical_paths(
                row, contract, bundle_files)
            observed_path_sets.append(observed_paths)
            for failure in transport_failures:
                require(False, f"performance run {index + 1}: {failure}")
            require(row.get("served_bundle_sha256") == bundle_digest,
                    f"performance run {index + 1} used the wrong served bundle")
            require(row.get("external_request_count") == 0,
                    f"performance run {index + 1} made external requests")
            require(row.get("page_error_count") == 0,
                    f"performance run {index + 1} recorded page errors/crashes")
            verify_m8.check_early_diagnostics(
                row.get("early_diagnostics"), f"performance composer run {index + 1}",
                validation_failures)
        fp_values = [row.get("fp") for row in rows if isinstance(row, dict)]
        wm_values = [row.get("wm") for row in rows if isinstance(row, dict)]
        require(scenario.get("fp") == fp_values, "performance first-pixel summary differs from rows")
        require(scenario.get("wm") == wm_values, "performance WM_main summary differs from rows")
        numeric_fp = [value for value in fp_values if isinstance(value, (int, float))]
        if len(numeric_fp) == len(rows) and numeric_fp:
            require(scenario.get("fp_median") == statistics.median(numeric_fp),
                    "performance first-pixel median differs from rows")
    first_pixels = scenario.get("fp_median")
    if first_pixels is None and scenario.get("fp"):
        first_pixels = statistics.median(scenario["fp"])
    critical_paths = sorted({path for paths in observed_path_sets for path in paths})
    bundle_file_set = set(bundle_files)
    critical_names = tuple(
        path.removeprefix("/") for path in critical_paths
        if (path.removeprefix("/") in bundle_file_set and
            f"{path.removeprefix('/')}.br" in bundle_file_set)
    )
    compressed = {name: brotli_size(BUNDLE / name) for name in critical_names}
    offline_ms = proof.get("offline_warm_wm_main_ms")
    receipt = {
        "schema": 1,
        "source_artifacts": expected_source,
        "bundle_artifacts": expected_bundle,
        "served_bundle_sha256": bundle_digest if not validation_failures else None,
        "source_runtime_verdict": proof.get("verdict"),
        "source_runtime_failures": proof.get("failures"),
        "proof": {
            key: proof.get(key) for key in (
                "cross_origin_isolated",
                "shared_array_buffer",
                "stage0_boot",
                "stage0_first_pixels",
                "stage0_first_pixels_ms",
                "first_pixels_present",
                "interactive_viewport_ms",
                "interactive_viewport_under_8s",
                "stage1_byte_exact",
                "stage1_complete",
                "stage1_memory_bounded",
                "progress_phases_visible",
                "service_worker_complete",
                "service_worker_inventory_exact",
                "trusted_semantic_interaction",
                "deferred_after_trusted_interaction_exactly_once",
                "two_phase_resumed_state_change",
                "online_warm_deferred_zero_origin",
                "online_warm_deferred_from_service_worker",
                "offline_cold_semantic_deferred",
                "offline_reload_wm_main",
                "external_request_count",
                "minimal_loader_visible",
                "loader_font_loaded",
                "source_link_visible",
                "trademark_disclaimer_visible",
                "query_python_disabled",
                "query_args_disabled",
                "query_dev_controls_disabled",
                "gpu_error_count",
                "page_error_count",
            )
        },
        "runtime_evidence": {
            "split_runtime": proof.get("split_runtime"),
            "transport": proof.get("transport"),
            "stage1_memory": proof.get("stage1_memory"),
        },
        "runtime_proofs": {
            "staged": {
                "browser": proof.get("browser"),
                "early_diagnostics": proof.get("early_diagnostics"),
            },
            "performance": {
                "browser": perf.get("browser"),
                "run_count": perf.get("runs"),
                "early_diagnostics": [row.get("early_diagnostics")
                                      for row in rows if isinstance(row, dict)],
            },
        },
        "performance": {
            "profile": "mid-laptop-1.5MBps-40ms" if profile_valid else None,
            "cold_first_pixels_ms": first_pixels,
            "critical_brotli_bytes": sum(compressed.values()),
            "critical_brotli_by_file": compressed,
            "critical_paths": critical_paths,
            "critical_paths_by_run": observed_path_sets,
            "split_inventory_sha256": verify_m8.sha256(verify_m8.BUILD / verify_m8.SPLIT_MANIFEST),
            "shard_phase_valid": bool(rows) and all(
                isinstance(row, dict) and row.get("manifest_phase_valid") is True and
                not phase_request_failures(row, contract) for row in rows),
            "offline_warm_wm_main_ms": offline_ms,
        },
        "source_proofs": {
            "runtime": str(VERIFY_PATH.relative_to(ROOT)),
            "performance": str(PERF_PATH.relative_to(ROOT)),
        },
        "validation_failures": validation_failures,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    p = receipt["performance"]
    passed = bool(not validation_failures and first_pixels is not None and first_pixels <= 8000 and
                  p["critical_brotli_bytes"] <= 15_000_000 and
                  offline_ms is not None and offline_ms <= 8000 and
                  all(receipt["proof"].get(key) is True for key in (
                      "cross_origin_isolated", "shared_array_buffer", "stage0_boot", "stage0_first_pixels",
                      "first_pixels_present", "interactive_viewport_under_8s",
                      "stage1_byte_exact", "stage1_complete", "stage1_memory_bounded",
                      "progress_phases_visible", "service_worker_complete",
                      "service_worker_inventory_exact",
                      "trusted_semantic_interaction",
                      "deferred_after_trusted_interaction_exactly_once",
                      "two_phase_resumed_state_change",
                      "online_warm_deferred_zero_origin",
                      "online_warm_deferred_from_service_worker",
                      "offline_cold_semantic_deferred",
                      "offline_reload_wm_main", "minimal_loader_visible",
                      "loader_font_loaded", "source_link_visible",
                      "trademark_disclaimer_visible",
                      "query_python_disabled", "query_args_disabled",
                      "query_dev_controls_disabled")) and
                  receipt["proof"].get("external_request_count") == 0 and
                  receipt["proof"].get("gpu_error_count") == 0 and
                  receipt["proof"].get("page_error_count") == 0)
    receipt["verdict"] = "PASS" if passed else "FAIL"
    OUT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"M8_STAGED_{'PASS' if passed else 'FAIL'} firstPixels={first_pixels}ms "
          f"criticalBr={p['critical_brotli_bytes']} -> {OUT.relative_to(ROOT)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
