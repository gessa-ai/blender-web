#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed, live-comparator M6 render-parity closeout verifier.

The default remains the complete hardware-bound M6 gate. ``--cycles-only``
verifies the independently runnable Cycles-CPU component without accepting it
as a substitute for Workbench, EEVEE, or the browser-render smoke.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
PREP = ROOT / "sandbox/m6-prep"
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DEFERRED_WASM_FILENAME = os.environ.get(
    "BW_DEFERRED_WASM_FILENAME", "blender_browser.deferred.wasm"
)
DEFERRED_RE = re.compile(r"^blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm$")
WB_LABEL = os.environ.get("M6_WORKBENCH_RUN", "m6-current-wb-final-r2")
EEVEE_LABEL = os.environ.get("M6_EEVEE_RUN", "eevee-final-full-r16")
CYCLES_LABEL = os.environ.get("M6_CYCLES_SMOKE", "m6-current-cycles-f12-r5")
CYCLES_SUITE_LABEL = os.environ.get("M6_CYCLES_RESULTS", "")
WB_ROOT = ROOT / "sandbox/gpu-r61/workbench-preview/runs" / WB_LABEL
EEVEE_ROOT = ROOT / "sandbox/gpu-r61/eevee-matrix-preview/runs" / EEVEE_LABEL
CYCLES_SMOKE = ROOT / "sandbox/gpu-r61/cycles-windowed/evidence" / f"{CYCLES_LABEL}-manifest.json"
CYCLES_SUITE_ROOT = PREP / "cycles-runs" / CYCLES_SUITE_LABEL if CYCLES_SUITE_LABEL else None
ARTIFACTS = {
    "javascript": ROOT / "build-wasm-windowed-opt/bin/blender_browser.js",
    "wasm": ROOT / "build-wasm-windowed-opt/bin/blender_browser.wasm",
    "deferred": ROOT / "build-wasm-windowed-opt/bin" / DEFERRED_WASM_FILENAME,
    "preload": ROOT / "build-wasm-windowed-opt/bin/blender_browser.data",
}
SHELL_FILES = {
    "index": ROOT / "platform_web/shell/index.html",
    "windowed": ROOT / "platform_web/shell/windowed.html",
    "diagnostics": ROOT / "platform_web/shell/diagnostics-bootstrap.js",
    "boot": ROOT / "platform_web/shell/boot-windowed.js",
    "fileBridge": ROOT / "platform_web/shell/file-bridge.js",
    "preinit": ROOT / "platform_web/shell/wgpu-preinit-worker.js",
}
CYCLES_ARTIFACTS = {
    "javascript": ROOT / "build-wasm-cycles/bin/blender.js",
    "wasm": ROOT / "build-wasm-cycles/bin/blender.wasm",
}
OIIOTOOL = shutil.which("oiiotool") or "/opt/homebrew/bin/oiiotool"
MAX_RE = re.compile(r"Max error\s*=\s*([0-9.eE+-]+)")
PERCENT_RE = re.compile(r"\(([0-9.]+)%\)\s*over")
ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1"
SOFTWARE_ADAPTER_TOKENS = (
    "swiftshader", "llvmpipe", "lavapipe", "softpipe", "software rasterizer",
    "microsoft basic render", "warp",
)
CYCLES_LEGACY_RE = re.compile(
    r"^M6T_LEGACY_SETTINGS_OK "
    r"file_version=([0-9]+\.[0-9]+\.[0-9]+) "
    r"handler_hits=1 addon_handler_preloaded=1 "
    r"sampling=(TABULATED_SOBOL|NOT_APPLICABLE)$",
    re.MULTILINE,
)


def fail(message: str) -> None:
    raise AssertionError(message)


def sha256(path: Path) -> str:
    if not path.is_file():
        fail(f"missing file: {path}")
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(path: Path) -> tuple[str, int]:
    if not path.is_dir():
        fail(f"missing directory: {path}")
    h = hashlib.sha256()
    files = sorted(candidate for candidate in path.rglob("*") if candidate.is_file())
    for item in files:
        h.update(item.relative_to(path).as_posix().encode())
        h.update(b"\0")
        h.update(item.read_bytes())
        h.update(b"\0")
    return h.hexdigest(), len(files)


def verify_hardware_adapter_receipt(receipt: dict, context: str) -> dict:
    if not isinstance(receipt, dict):
        fail(f"{context}: hardware adapter receipt missing")
    info = receipt.get("info")
    info_keys = {"vendor", "architecture", "device", "description"}
    if (receipt.get("contract") != ADAPTER_CONTRACT
            or receipt.get("status") != "ACCEPTED"
            or receipt.get("reason") != "accepted-hardware"
            or receipt.get("present") is not True
            or receipt.get("isFallbackAdapter") is not False
            or receipt.get("powerPreference") != "high-performance"
            or not isinstance(receipt.get("platform"), str)
            or not receipt.get("platform")):
        fail(f"{context}: hardware adapter acceptance fields invalid")
    if (not isinstance(info, dict) or set(info) != info_keys
            or any(not isinstance(info.get(key), str) for key in info_keys)):
        fail(f"{context}: hardware adapter info shape invalid")
    identity = " ".join(info.values()).strip().lower()
    detail_identity = " ".join(
        (info["architecture"], info["device"], info["description"])
    ).strip()
    software_matches = [token for token in SOFTWARE_ADAPTER_TOKENS if token in identity]
    if re.search(r"(^|[^a-z0-9])cpu([^a-z0-9]|$)", identity):
        software_matches.append("cpu")
    if (not identity or not detail_identity or software_matches
            or receipt.get("softwareMatches") != []):
        fail(f"{context}: hardware adapter identity is absent or software-backed")
    return {
        "contract": receipt["contract"],
        "status": receipt["status"],
        "present": receipt["present"],
        "platform": receipt["platform"],
        "powerPreference": receipt["powerPreference"],
        "isFallbackAdapter": receipt["isFallbackAdapter"],
        "info": {key: info[key] for key in sorted(info_keys)},
        "softwareMatches": [],
        "reason": receipt["reason"],
    }


def verify_tree_receipt(item: dict, context: str, expected_path: Path) -> None:
    if not isinstance(item, dict):
        fail(f"{context}: tree receipt missing")
    path = Path(str(item.get("path", ""))).resolve()
    if path != expected_path.resolve():
        fail(f"{context}: path {path} != {expected_path.resolve()}")
    digest, count = sha256_tree(path)
    if item.get("sha256Tree") != digest or item.get("fileCount") != count:
        fail(f"{context}: tree receipt is stale")


def load_json(path: Path):
    if not path.is_file():
        fail(f"missing JSON: {path}")
    return json.loads(path.read_text())


def receipt_path(item: dict, context: str) -> Path:
    text = item.get("path") or item.get("hostPath")
    if not isinstance(text, str):
        fail(f"{context}: receipt path missing")
    path = Path(text)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def verify_file_receipt(item: dict, context: str, expected_path: Path | None = None) -> Path:
    if not isinstance(item, dict):
        fail(f"{context}: file receipt missing")
    path = receipt_path(item, context)
    if expected_path is not None and path != expected_path.resolve():
        fail(f"{context}: path {path} != {expected_path.resolve()}")
    actual_sha = sha256(path)
    if item.get("sha256") != actual_sha:
        fail(f"{context}: sha256 {item.get('sha256')} != {actual_sha}")
    if "bytes" in item and item.get("bytes") != path.stat().st_size:
        fail(f"{context}: bytes {item.get('bytes')} != {path.stat().st_size}")
    return path


def verify_artifact_binding(binding: dict, expected: dict[str, Path], context: str) -> dict:
    if not isinstance(binding, dict) or set(binding) != set(expected):
        fail(f"{context}: artifact set {sorted(binding) if isinstance(binding, dict) else binding} != {sorted(expected)}")
    normalized = {}
    for key, path in expected.items():
        verify_file_receipt(binding[key], f"{context}/{key}", path)
        normalized[key] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
    return normalized


def verify_served_shell(inputs: dict, context: str) -> dict:
    served = inputs.get("servedShell") if isinstance(inputs, dict) else None
    expected = inputs.get("expectedServedShell") if isinstance(inputs, dict) else None
    if not isinstance(served, dict) or set(served) != set(SHELL_FILES):
        fail(f"{context}: served-shell set is not exact")
    if not isinstance(expected, dict) or set(expected) != set(SHELL_FILES):
        fail(f"{context}: local shell set is not exact")
    suffixes = {"index": "/index.html", "windowed": "/windowed.html",
                "diagnostics": "/diagnostics-bootstrap.js",
                "boot": "/boot-windowed.js", "fileBridge": "/file-bridge.js",
                "preinit": "/wgpu-preinit-worker.js"}
    normalized = {}
    for key, path in SHELL_FILES.items():
        verify_file_receipt(expected[key], f"{context}/{key} local shell", path)
        item = served[key]
        if (not isinstance(item, dict) or not str(item.get("url", "")).endswith(suffixes[key])
                or item.get("bytes") != path.stat().st_size or item.get("sha256") != sha256(path)):
            fail(f"{context}/{key}: served bytes differ from exact local shell")
        normalized[key] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
    return normalized


def live_compare(golden: Path, candidate: Path, threshold: str, fail_percent: str, *, rgb: bool) -> dict:
    argv = [OIIOTOOL, str(golden)]
    if rgb:
        argv += ["--ch", "R,G,B"]
    argv.append(str(candidate))
    if rgb:
        argv += ["--ch", "R,G,B"]
    argv += ["--fail", threshold, "--failpercent", fail_percent, "--diff"]
    result = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, check=False)
    output = (result.stdout + result.stderr).strip()
    max_match = MAX_RE.search(output)
    percent_matches = PERCENT_RE.findall(output)
    return {
        "pass": result.returncode == 0,
        "returnCode": result.returncode,
        "maxError": float(max_match.group(1)) if max_match else None,
        "percentOver": float(percent_matches[-1]) if percent_matches else None,
        "argv": argv,
        "output": output,
    }


def stored_percent(value) -> float | None:
    if value is None:
        return None
    matches = re.findall(r"([0-9.]+)%", str(value))
    return float(matches[-1]) if matches else None


def verify_metrics(stored_max, stored_pct, live: dict, context: str) -> None:
    if live["maxError"] is None and live["percentOver"] is None:
        missing_stored = stored_max in {None, "", "-"} and stored_pct in {None, "", "-"}
        if live["pass"] and missing_stored:
            return
        fail(f"{context}: exact-match comparator/stored metrics disagree: {live['output']}")
    if live["maxError"] is None or live["percentOver"] is None:
        fail(f"{context}: live comparator metrics missing: {live['output']}")
    try:
        maximum = float(stored_max)
    except (TypeError, ValueError):
        fail(f"{context}: stored max metric invalid: {stored_max}")
    percent = stored_percent(stored_pct)
    if percent is None or abs(maximum - live["maxError"]) > 1e-12 or abs(percent - live["percentOver"]) > 1e-12:
        fail(f"{context}: stored/live metrics differ max={maximum}/{live['maxError']} pct={percent}/{live['percentOver']}")


def clean_tsv(value) -> str:
    if value is None:
        return ""
    return re.sub(r"[\t\r\n]+", " ", str(value))


def load_manifest() -> dict[tuple[str, str], dict[str, object]]:
    mapping = {}
    with (PREP / "manifest.tsv").open(newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if not row or row[0].startswith("#"):
                continue
            if len(row) != 7:
                fail(f"malformed manifest row: {row}")
            engine, directory, test, blend, golden, threshold, fail_percent = row
            key = (engine, f"{directory}/{test}")
            if key in mapping:
                fail(f"duplicate manifest row: {key}")
            mapping[key] = {
                "engine": engine,
                "directory": directory,
                "test": test,
                "blend": (ROOT / blend).resolve(),
                "basename": Path(blend).name,
                "golden": (ROOT / golden).resolve(),
                "threshold": threshold,
                "failPercent": fail_percent,
            }
    counts = {engine: sum(key[0] == engine for key in mapping) for engine in ("workbench", "eevee", "cycles")}
    if counts != {"workbench": 20, "eevee": 30, "cycles": 27}:
        fail(f"manifest engine counts changed: {counts}")
    return mapping


def parse_blacklist() -> list[dict[str, object]]:
    entries = []
    for number, raw in enumerate((PREP / "blacklist.txt").read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        body, marker, reason = line.partition("#")
        fields = body.split()
        if len(fields) != 2 or not marker or not reason.strip():
            fail(f"malformed blacklist line {number}: {raw}")
        engine, pattern_text = fields
        if engine not in {"workbench", "eevee", "cycles", "*"}:
            fail(f"unknown blacklist engine at line {number}: {engine}")
        try:
            pattern = re.compile(pattern_text)
        except re.error as exc:
            fail(f"invalid blacklist regex at line {number}: {exc}")
        entries.append({
            "id": number, "engine": engine, "patternText": pattern_text,
            "pattern": pattern, "reason": reason.strip(),
        })
    return entries


def verify_blacklist_coverage(entries: list[dict], manifest: dict) -> None:
    for entry in entries:
        matches = [key for key, row in manifest.items()
                   if entry["engine"] in {"*", key[0]} and entry["pattern"].match(row["basename"])]
        if len(matches) != 1:
            fail(f"blacklist line {entry['id']} must match exactly one manifest row, found {matches}")


def blacklist_entry(entries: list[dict], engine: str, basename: str) -> dict | None:
    hits = [entry for entry in entries
            if entry["engine"] in {engine, "*"} and entry["pattern"].match(basename)]
    if len(hits) > 1:
        fail(f"multiple blacklist entries match {engine}/{basename}")
    return hits[0] if hits else None


def valid_physical_f12(invocation: dict) -> bool:
    receipt = invocation.get("keyReceipt")
    return (
        invocation.get("method") == "page.keyboard.press(F12)"
        and invocation.get("count") == 1
        and invocation.get("physicalTrustedF12") is True
        and isinstance(receipt, list) and len(receipt) == 1
        and receipt[0].get("key") == "F12" and receipt[0].get("code") == "F12"
        and receipt[0].get("isTrusted") is True and receipt[0].get("repeat") is False
        and receipt[0].get("targetId") == "canvas" and receipt[0].get("activeId") == "canvas"
    )


def expected_keys(manifest: dict, engine: str) -> set[str]:
    return {key for candidate_engine, key in manifest if candidate_engine == engine}


def verify_workbench(entries, manifest_rows) -> tuple[int, int]:
    result_path = WB_ROOT / "results.tsv"
    if not result_path.is_file():
        fail(f"missing Workbench result matrix: {result_path}")
    rows = [row for row in csv.reader((line for line in result_path.open() if not line.startswith("#")), delimiter="\t") if row]
    if len(rows) != 20:
        fail(f"Workbench row count {len(rows)} != 20")
    passed = skipped = 0
    seen = set()
    artifact_binding = None
    for row in rows:
        if len(row) != 10:
            fail(f"invalid Workbench result width: {row}")
        engine, directory, test, verdict = row[:4]
        if engine != "workbench" or verdict not in {"PASS", "FAIL"}:
            fail(f"invalid Workbench row: {row}")
        key = f"{directory}/{test}"
        if key in seen:
            fail(f"duplicate Workbench key: {key}")
        seen.add(key)
        expected = manifest_rows[(engine, key)]
        exclusion = blacklist_entry(entries, engine, expected["basename"])
        cap = WB_ROOT / "caps" / f"workbench_{directory}_{test}"
        product_path = cap / "render_result.png"
        manifest = load_json(cap / "manifest.json")
        score = load_json(cap / "score.json")
        if manifest.get("schema") != "blender-web.workbench-product.v2":
            fail(f"Workbench receipt schema is not v2: {key}")
        if manifest.get("productGate", {}).get("pass") is not True:
            fail(f"Workbench product gate failed: {key}")
        if not valid_physical_f12(manifest.get("invocation", {})):
            fail(f"Workbench physical trusted F12 receipt failed: {key}")
        if manifest.get("gpuErrorCount") != 0 or manifest.get("pageErrorCount") != 0 or manifest.get("pageCrashed") or manifest.get("pageUnresponsive"):
            fail(f"Workbench browser/GPU health failed: {key}")
        inputs = manifest.get("inputs", {})
        verify_file_receipt(inputs.get("blend"), f"Workbench {key} blend", expected["blend"])
        verify_served_shell(inputs, f"Workbench {key}")
        current_binding = verify_artifact_binding(inputs.get("shippingBinary"), ARTIFACTS, f"Workbench {key}")
        if artifact_binding is None:
            artifact_binding = current_binding
        elif current_binding != artifact_binding:
            fail(f"Workbench artifact binding drift within matrix: {key}")
        sources = manifest.get("sources", {})
        verify_file_receipt(
            sources.get("driver"), f"Workbench {key} driver",
            ROOT / "sandbox/gpu-r61/workbench-preview/drive_workbench_case.mjs",
        )
        verify_file_receipt(
            sources.get("matrixRunner"), f"Workbench {key} matrix runner",
            ROOT / "sandbox/gpu-r61/workbench-preview/run_matrix.sh",
        )
        verify_file_receipt(
            sources.get("bridge"), f"Workbench {key} bridge",
            ROOT / "sandbox/gpu-r35/bridge_boot.mjs",
        )
        verify_file_receipt(
            sources.get("manifest"), f"Workbench {key} source manifest",
            PREP / "manifest.tsv",
        )
        captures = manifest.get("productCaptures")
        if not isinstance(captures, list) or len(captures) != 1:
            fail(f"Workbench product capture set invalid: {key}")
        capture = captures[0]
        if capture.get("sha256") != sha256(product_path) or capture.get("byteLength") != product_path.stat().st_size:
            fail(f"Workbench product capture hash/size mismatch: {key}")
        if (score.get("capdir") != str(cap) or score.get("golden") != str(expected["golden"])
                or score.get("gpuErrorCount") != 0 or score.get("pageErrorCount") != 0):
            fail(f"Workbench scorer identity/health mismatch: {key}")
        verify_file_receipt(
            score.get("sources", {}).get("scorer"), f"Workbench {key} scorer",
            ROOT / "sandbox/gpu-r61/workbench-preview/score_workbench.py",
        )
        comparator = score.get("comparator", {})
        verify_file_receipt(comparator.get("golden"), f"Workbench {key} golden", expected["golden"])
        verify_file_receipt(comparator.get("product"), f"Workbench {key} product", product_path)
        golden_rgb = verify_file_receipt(comparator.get("golden_rgb"), f"Workbench {key} golden RGB", cap / "golden_rgb.png")
        product_rgb = verify_file_receipt(comparator.get("product_rgb"), f"Workbench {key} product RGB", cap / "render_result_rgb.png")
        if comparator.get("threshold") != expected["threshold"] or comparator.get("fail_percent") != expected["failPercent"]:
            fail(f"Workbench threshold drift: {key}")
        expected_argv = ["oiiotool", str(golden_rgb), str(product_rgb), "--fail", expected["threshold"],
                         "--failpercent", expected["failPercent"], "--diff"]
        if comparator.get("argv") != expected_argv:
            fail(f"Workbench comparator argv drift: {key}")
        live = live_compare(expected["golden"], product_path, expected["threshold"], expected["failPercent"], rgb=True)
        verify_metrics(score.get("max_error"), score.get("pct_over"), live, f"Workbench {key}")
        live_verdict = "PASS" if live["pass"] else "FAIL"
        if verdict != live_verdict or score.get("verdict") != live_verdict or score.get("oiiotool_rc") != live["returnCode"]:
            fail(f"Workbench stored/live verdict mismatch: {key}")
        expected_result_tail = [
            str(score.get("cluster") or ""),
            str(score.get("mean_error") or ""),
            str(score.get("max_error") or ""),
            str(score.get("pct_over") or "").replace("\t", " "),
            str(score.get("gpuErrorCount", 0)),
            str(score.get("gpu_sig") or ""),
        ]
        if row[4:] != expected_result_tail:
            fail(f"Workbench result TSV/scorer mismatch: {key}")
        if live["pass"]:
            if exclusion:
                fail(f"Workbench blacklist is stale because row now passes: {key}")
            passed += 1
        else:
            if not exclusion:
                fail(f"unjustified Workbench pixel failure: {key}")
            skipped += 1
    if seen != expected_keys(manifest_rows, "workbench"):
        fail(f"Workbench exact row set mismatch: missing={expected_keys(manifest_rows, 'workbench') - seen}")
    if (passed, skipped) != (19, 1):
        fail(f"Workbench totals {(passed, skipped)} != (19 pass, 1 skip)")
    return passed, skipped


def verify_eevee_provenance(manifest_rows) -> tuple[dict[str, dict], dict]:
    provenance = load_json(EEVEE_ROOT / "provenance.json")
    progress = provenance.get("progress", {})
    run = provenance.get("run", {})
    if (provenance.get("schema") != "blender-web.eevee-matrix-provenance.v2"
            or run.get("label") != EEVEE_LABEL or Path(str(run.get("root", ""))).resolve() != EEVEE_ROOT.resolve()
            or run.get("productMode") is not True or run.get("markerIndependent") is not True
            or run.get("physicalF12") is not True or run.get("browserRowsSerialized") is not True
            or run.get("maximumGpuConcurrency") != 1 or run.get("canonicalProbes") is not True
            or run.get("hardwareAdapterContract") != ADAPTER_CONTRACT
            or provenance.get("rowCount") != 30
            or provenance.get("status") != "FAIL" or progress.get("completed") != 30
            or progress.get("pending") != 0 or progress.get("pass") != 13 or progress.get("fail") != 17
            or progress.get("rowsWithGpuErrors") != 0):
        fail("EEVEE provenance run identity/status failed")
    verify_file_receipt(provenance.get("manifest"), "EEVEE provenance manifest", PREP / "manifest.tsv")
    verify_file_receipt(provenance.get("harness"), "EEVEE provenance harness", ROOT / "sandbox/gpu-r61/eevee-matrix-preview/run_eevee_matrix.mjs")
    verify_file_receipt(provenance.get("inputContract"), "EEVEE input contract", ROOT / "sandbox/gpu-r61/eevee-matrix-preview/eevee-input-contract.tsv")
    sources = provenance.get("thresholdSources", {})
    verify_file_receipt(sources.get("validator"), "EEVEE threshold validator", PREP / "validate_eevee_thresholds.py")
    verify_file_receipt(sources.get("upstreamRunner"), "EEVEE upstream threshold source", ROOT / "upstream/tests/python/eevee_render_tests.py")
    verify_file_receipt(
        provenance.get("canonicalDriver"), "EEVEE canonical driver",
        ROOT / "sandbox/gpu-r61/f12-eevee-acceptance/drive_eevee_f12.mjs",
    )
    expected = [key for (engine, key) in manifest_rows if engine == "eevee"]
    selection = provenance.get("selection", {})
    if (selection.get("mode") != "full-manifest" or selection.get("manifestRowCount") != 30
            or selection.get("selectedRowCount") != 30 or selection.get("requestedKeys") != expected):
        fail("EEVEE provenance selection is not the exact full manifest")
    generated = provenance.get("temporaryDrivers", {})
    generated_rows = generated.get("rows") if isinstance(generated, dict) else None
    if (not isinstance(generated, dict) or generated.get("persisted") is not False
            or not isinstance(generated_rows, list)
            or len(generated_rows) != 30):
        fail("EEVEE generated-driver provenance invalid")
    mapping = {}
    for index, item in enumerate(generated_rows, 1):
        key = item.get("key")
        if item.get("index") != index or key != expected[index - 1] or key in mapping:
            fail(f"EEVEE generated-driver row identity invalid at {index}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            fail(f"EEVEE generated-driver hash invalid: {key}")
        substitutions = item.get("substitutions", {})
        expected_row = manifest_rows[("eevee", key)]
        expected_label = f"{EEVEE_LABEL}-eevee-{expected_row['directory']}-{expected_row['test']}"
        expected_dir = EEVEE_ROOT / "rows" / f"{index:02d}-{expected_row['directory']}-{expected_row['test']}"
        if (Path(str(substitutions.get("blendHost", ""))).resolve() != expected_row["blend"]
                or substitutions.get("blendSha256") != sha256(expected_row["blend"])
                or Path(str(substitutions.get("goldenHost", ""))).resolve() != expected_row["golden"]
                or substitutions.get("goldenSha256") != sha256(expected_row["golden"])
                or substitutions.get("failThreshold") != expected_row["threshold"]
                or substitutions.get("failPercent") != expected_row["failPercent"]
                or substitutions.get("outputLabel") != expected_label
                or Path(str(substitutions.get("outputDir", ""))).resolve() != expected_dir.resolve()
                or substitutions.get("manifestSelector") != f"eevee/{key}"):
            fail(f"EEVEE generated-driver substitutions stale: {key}")
        mapping[key] = item
    hardware_adapter = verify_hardware_adapter_receipt(
        provenance.get("hardwareAdapter"), "EEVEE provenance"
    )
    return mapping, hardware_adapter


def verify_eevee(entries, manifest_rows) -> tuple[int, int]:
    generated_rows, hardware_adapter = verify_eevee_provenance(manifest_rows)
    results = EEVEE_ROOT / "results.tsv"
    rows = [row for row in csv.reader((line for line in results.open() if not line.startswith("#")), delimiter="\t") if row]
    if len(rows) != 30:
        fail(f"EEVEE row count {len(rows)} != 30")
    passed = skipped = 0
    seen = set()
    artifact_binding = None
    rows_root = (EEVEE_ROOT / "rows").resolve()
    setup_routes = {"browser-canonical-modal-bake": 0, "upstream-scene-probe-skip": 0}
    for ordinal, row in enumerate(rows, 1):
        if len(row) != 26:
            fail(f"invalid EEVEE result width: {row}")
        _, engine, directory, test, _, _, _, _, threshold, fail_percent, label, _, _, verdict = row[:14]
        key = f"{directory}/{test}"
        if row[0] != str(ordinal) or engine != "eevee" or verdict not in {"PASS", "FAIL"} or key in seen:
            fail(f"invalid/duplicate EEVEE row: {row}")
        seen.add(key)
        expected = manifest_rows[(engine, key)]
        expected_label = f"{EEVEE_LABEL}-eevee-{directory}-{test}"
        if label != expected_label or threshold != expected["threshold"] or fail_percent != expected["failPercent"]:
            fail(f"EEVEE label/threshold result drift: {key}")
        if row[14] != "true" or row[16] not in {"true", "false"}:
            fail(f"EEVEE binding/comparator result receipt invalid: {key}")
        manifest_path = Path(row[24]).resolve()
        if manifest_path.parent.parent != rows_root or manifest_path.name != f"{expected_label}-manifest.json":
            fail(f"EEVEE manifest escaped selected immutable run: {key}")
        if row[23] != sha256(manifest_path):
            fail(f"EEVEE manifest result hash mismatch: {key}")
        manifest = load_json(manifest_path)
        if manifest.get("schema") != "blender-web.f12-eevee-acceptance.v5" or not valid_physical_f12(manifest.get("invocation", {})):
            fail(f"EEVEE schema/trusted F12 receipt failed: {key}")
        row_adapter = verify_hardware_adapter_receipt(
            manifest.get("hardwareAdapter"), f"EEVEE {key}"
        )
        if row_adapter != hardware_adapter:
            fail(f"EEVEE hardware adapter identity drift within matrix: {key}")
        if manifest.get("assertions", {}).get("acceptedHardwareAdapter") is not True:
            fail(f"EEVEE hardware adapter assertion failed: {key}")
        generated = generated_rows[key]
        substitutions = generated["substitutions"]
        if manifest.get("driver", {}).get("sha256") != generated["sha256"]:
            fail(f"EEVEE generated driver receipt mismatch: {key}")
        failures = manifest.get("failures", {})
        if (failures.get("gpuErrors") or failures.get("pageErrors") or failures.get("pageCrashed")
                or failures.get("heartbeatError")):
            fail(f"EEVEE browser/GPU health failed: {key}")
        if manifest.get("render", {}).get("completionReceipt", {}).get("status") != "OK":
            fail(f"EEVEE render completion failed: {key}")
        render = manifest.get("render", {})
        probe_state = manifest.get("probePreparation", {}).get("receipt", {}).get("state")
        expected_route = "upstream-scene-probe-skip" if probe_state == "SKIPPED_BY_SCENE" else "browser-canonical-modal-bake"
        if (row[4] != substitutions.get("blendSource") or row[5] != expected_route
                or row[6] != str(substitutions.get("expectedSamples"))
                or row[7] != substitutions.get("expectedColorMode")
                or render.get("expectedEffectiveSamples") != substitutions.get("expectedSamples")
                or render.get("expectedViewTransform") != substitutions.get("expectedViewTransform")
                or render.get("expectedColorMode") != substitutions.get("expectedColorMode")):
            fail(f"EEVEE result/setup provenance mismatch: {key}")
        setup_routes[expected_route] += 1
        inputs = manifest.get("inputs", {})
        verify_file_receipt(inputs.get("blend"), f"EEVEE {key} blend", expected["blend"])
        verify_file_receipt(inputs.get("golden"), f"EEVEE {key} golden", expected["golden"])
        verify_served_shell(inputs, f"EEVEE {key}")
        current_binding = verify_artifact_binding(inputs.get("shippingBinary"), ARTIFACTS, f"EEVEE {key}")
        if artifact_binding is None:
            artifact_binding = current_binding
        elif current_binding != artifact_binding:
            fail(f"EEVEE artifact binding drift within matrix: {key}")
        evidence = manifest.get("evidence", {})
        row_root = manifest_path.parent
        render_path = verify_file_receipt(
            evidence.get("renderResult"), f"EEVEE {key} render",
            row_root / f"{expected_label}-render-result.png",
        )
        verify_file_receipt(
            evidence.get("comparator"), f"EEVEE {key} comparator",
            row_root / f"{expected_label}-comparator.txt",
        )
        verify_file_receipt(
            evidence.get("console"), f"EEVEE {key} console",
            row_root / f"{expected_label}-console.log",
        )
        verify_file_receipt(
            evidence.get("screenshot"), f"EEVEE {key} screenshot",
            row_root / f"{expected_label}-1280x720.png",
        )
        comparator = manifest.get("comparator", {})
        if comparator.get("threshold") != expected["threshold"] or comparator.get("failPercent") != expected["failPercent"]:
            fail(f"EEVEE manifest threshold drift: {key}")
        if comparator.get("argv") != [str(expected["golden"]), str(render_path), "--fail", expected["threshold"], "--failpercent", expected["failPercent"], "--diff"]:
            fail(f"EEVEE comparator argv drift: {key}")
        live = live_compare(expected["golden"], render_path, expected["threshold"], expected["failPercent"], rgb=False)
        stored = comparator.get("result", {})
        verify_metrics(stored.get("maxError"), stored.get("percentOver"), live, f"EEVEE {key}")
        run_error = failures.get("runError")
        if live["pass"]:
            if run_error is not None:
                fail(f"EEVEE passing row recorded a run error: {key}")
        else:
            expected_error_prefix = (
                f"Error: pixel comparator failed rc={live['returnCode']} "
                f"max={stored.get('maxError')} over={stored.get('percentOver')}"
            )
            if not isinstance(run_error, str) or not run_error.startswith(expected_error_prefix):
                fail(f"EEVEE comparator-failure error receipt mismatch: {key}")
        expected_run_error = clean_tsv(failures.get("runError"))
        if (stored.get("pass") is not live["pass"] or (row[16] == "true") is not live["pass"]
                or row[14] != "true" or row[15] != "" or row[17] != clean_tsv(stored.get("maxError"))
                or row[18] != clean_tsv(stored.get("percentOver")) or row[19:22] != ["0", "0", "false"]
                or row[22] != expected_run_error or row[12] != ""
                or ((row[11] == "0") is not live["pass"])
                or row[25] != str(row_root / f"{expected_label}-matrix.log")):
            fail(f"EEVEE comparator stored/live mismatch: {key}")
        sha256(Path(row[25]))
        exclusion = blacklist_entry(entries, engine, expected["basename"])
        if live["pass"]:
            if verdict != "PASS" or manifest.get("verdict") != "PASS" or exclusion:
                fail(f"EEVEE PASS/blacklist mismatch: {key}")
            passed += 1
        else:
            if verdict != "FAIL" or not exclusion:
                fail(f"unjustified EEVEE pixel failure: {key}")
            skipped += 1
    if seen != expected_keys(manifest_rows, "eevee"):
        fail("EEVEE exact row set mismatch")
    if (passed, skipped) != (13, 17):
        fail(f"EEVEE totals {(passed, skipped)} != (13 pass, 17 skip)")
    if setup_routes != {"browser-canonical-modal-bake": 29, "upstream-scene-probe-skip": 1}:
        fail(f"EEVEE setup-route totals changed: {setup_routes}")
    return passed, skipped


def verify_cycles_suite(entries, manifest_rows) -> tuple[int, int]:
    if CYCLES_SUITE_ROOT is None or not LABEL_RE.fullmatch(CYCLES_SUITE_LABEL):
        fail("M6_CYCLES_RESULTS must select one immutable Cycles suite label")
    provenance = load_json(CYCLES_SUITE_ROOT / "provenance.json")
    if (provenance.get("schema") != "blender-web.cycles-wasm-suite.v3"
            or provenance.get("label") != CYCLES_SUITE_LABEL or provenance.get("immutable") is not True
            or provenance.get("artifactStable") is not True):
        fail("Cycles suite provenance identity failed")
    verify_artifact_binding(provenance.get("artifacts"), CYCLES_ARTIFACTS, "Cycles suite artifacts")
    sources = provenance.get("sources", {})
    verify_file_receipt(sources.get("manifest"), "Cycles suite manifest", PREP / "manifest.tsv")
    verify_file_receipt(sources.get("blacklist"), "Cycles suite blacklist", PREP / "blacklist.txt")
    verify_file_receipt(sources.get("runner"), "Cycles suite runner", PREP / "run_wasm_cycles.sh")
    verify_file_receipt(sources.get("driver"), "Cycles suite driver", PREP / "wasm-first-render/render_test.py")
    verify_tree_receipt(sources.get("addon"), "Cycles suite addon", PREP / "wasm-first-render/addon")
    results_path = verify_file_receipt(provenance.get("results"), "Cycles suite results", CYCLES_SUITE_ROOT / "results.tsv")
    with results_path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        expected_fields = [
            "test", "render_s", "node_exit", "diff_exit", "verdict", "max_err", "pct_over", "note",
            "file_version", "legacy_settings", "log_sha256", "input_sha256", "golden_sha256",
            "render_sha256", "threshold", "fail_percent", "comparator_sha256",
        ]
        if reader.fieldnames != expected_fields:
            fail(f"Cycles result schema changed: {reader.fieldnames}")
        rows = list(reader)
    if len(rows) != 27:
        fail(f"Cycles row count {len(rows)} != 27")
    passed = skipped = 0
    seen = set()
    for row in rows:
        key = row["test"]
        if key in seen:
            fail(f"duplicate Cycles key: {key}")
        seen.add(key)
        expected = manifest_rows[("cycles", key)]
        directory, test = key.split("/", 1)
        render_path = CYCLES_SUITE_ROOT / "renders" / directory / f"{test}.png"
        comparator_path = CYCLES_SUITE_ROOT / "comparators" / directory / f"{test}.txt"
        log_path = CYCLES_SUITE_ROOT / "logs" / directory / f"{test}.log"
        if row["input_sha256"] != sha256(expected["blend"]) or row["golden_sha256"] != sha256(expected["golden"]):
            fail(f"Cycles input/golden hash mismatch: {key}")
        if (row["render_sha256"] != sha256(render_path)
                or row["comparator_sha256"] != sha256(comparator_path)
                or row["log_sha256"] != sha256(log_path)):
            fail(f"Cycles render/comparator/log hash mismatch: {key}")
        if row["threshold"] != expected["threshold"] or row["fail_percent"] != expected["failPercent"]:
            fail(f"Cycles threshold drift: {key}")
        if row["node_exit"] != "0":
            fail(f"Cycles node render did not exit 0: {key}")
        log_text = log_path.read_text(errors="replace")
        legacy_matches = CYCLES_LEGACY_RE.findall(log_text)
        if len(legacy_matches) != 1:
            fail(f"Cycles legacy-settings receipt count is not one: {key}")
        file_version, legacy_settings = legacy_matches[0]
        if row["file_version"] != file_version or row["legacy_settings"] != legacy_settings:
            fail(f"Cycles legacy-settings result/log mismatch: {key}")
        version = tuple(int(part) for part in file_version.split("."))
        expected_legacy = "TABULATED_SOBOL" if version <= (4, 2, 52) else "NOT_APPLICABLE"
        if legacy_settings != expected_legacy:
            fail(f"Cycles legacy-settings migration mismatch: {key}")
        if log_text.count("M6T_ENGINE_OK addon-registered-before-load") != 1:
            fail(f"Cycles staged add-on was not registered exactly once before load: {key}")
        live = live_compare(expected["golden"], render_path, expected["threshold"], expected["failPercent"], rgb=False)
        verify_metrics(row["max_err"], row["pct_over"], live, f"Cycles {key}")
        exclusion = blacklist_entry(entries, "cycles", expected["basename"])
        if live["pass"]:
            if row["diff_exit"] != "0" or row["verdict"] != "PASS" or row["note"] != "-":
                fail(f"Cycles PASS receipt invalid: {key}")
            if exclusion:
                fail(f"Cycles blacklist is stale because measured row now passes: {key}")
            passed += 1
        else:
            if row["diff_exit"] == "0" or row["verdict"] != "SKIP" or row["note"] != "blacklist" or not exclusion:
                fail(f"unjustified/invalid Cycles measured failure: {key}")
            skipped += 1
    if seen != expected_keys(manifest_rows, "cycles"):
        fail(f"Cycles exact row set mismatch: missing={expected_keys(manifest_rows, 'cycles') - seen}")
    if (passed, skipped) != (27, 0):
        fail(f"Cycles totals {(passed, skipped)} != (27 pass, 0 skip)")
    if provenance.get("counts") != {"pass": 27, "fail": 0, "skip": 0, "stale": 0, "blocked": 0} or provenance.get("status") != "PASS":
        fail("Cycles suite provenance totals/status mismatch")
    return passed, skipped


def verify_cycles_smoke() -> None:
    smoke = load_json(CYCLES_SMOKE)
    if smoke.get("schema") != "blender-web.cycles-windowed-f12-acceptance.v2" or smoke.get("verdict") != "PASS":
        fail("current-artifact Cycles smoke schema/verdict failed")
    if not valid_physical_f12(smoke.get("invocation", {})):
        fail("current-artifact Cycles physical-F12 receipt failed")
    assertions = smoke.get("assertions", {})
    required_true = {
        "opfsStartupFile", "physicalTrustedF12ExactlyOnce", "noBpyExec",
        "computeWorkgroupStorageAtLeast32768", "cyclesAddonRegisteredAndCpuOnly",
        "markerIndependentProductMode", "wmTickAdvancedAfterRender",
        "renderHandlerCompletedExactlyOnce", "nonBlack", "finitePng", "comparatorPass",
        "noGpuError", "noRenderWindowError", "noPageError", "noPageCrash", "noRunError",
    }
    if any(assertions.get(key) is not True for key in required_true) or assertions.get("exactAsyncSemanticOrder") is not None:
        fail("current-artifact Cycles assertion set failed")
    failures = smoke.get("failures", {})
    if failures.get("gpuErrors") or failures.get("pageErrors") or failures.get("pageCrashed") or failures.get("runError") or failures.get("renderErrors"):
        fail("current-artifact Cycles browser/GPU health failed")
    verify_file_receipt(smoke.get("driver"), "Cycles smoke driver", ROOT / "sandbox/gpu-r61/cycles-windowed/drive_cycles_f12.mjs")
    inputs = smoke.get("inputs", {})
    verify_served_shell(inputs, "Cycles smoke")
    golden_path = verify_file_receipt(
        inputs.get("golden"), "Cycles smoke golden",
        PREP / "wasm-first-render/native_ref/cube_.png",
    )
    verify_file_receipt(
        inputs.get("blend"), "Cycles smoke blend",
        ROOT / "upstream/release/datafiles/startup.blend",
    )
    verify_artifact_binding(inputs.get("shippingBinary"), ARTIFACTS, "Cycles smoke")
    addon = inputs.get("cyclesAddonPreload", {})
    addon_path = ROOT / "upstream/intern/cycles/blender/addon"
    addon_digest, _ = sha256_tree(addon_path)
    if (Path(str(addon.get("hostPath", ""))).resolve() != addon_path.resolve()
            or addon.get("guestEntry") != "/bw/scripts/addons_core/cycles/__init__.py"
            or addon.get("sha256Tree") != addon_digest):
        fail("Cycles smoke addon preload receipt is stale")
    evidence = smoke.get("evidence", {})
    evidence_root = ROOT / "sandbox/gpu-r61/cycles-windowed/evidence"
    manifest_evidence = evidence.get("manifest", {})
    if Path(str(manifest_evidence.get("path", ""))).resolve() != CYCLES_SMOKE.resolve():
        fail("Cycles smoke manifest evidence identity failed")
    render_path = verify_file_receipt(
        evidence.get("renderResult"), "Cycles smoke render",
        evidence_root / f"{CYCLES_LABEL}-render-result.png",
    )
    verify_file_receipt(
        evidence.get("comparator"), "Cycles smoke comparator",
        evidence_root / f"{CYCLES_LABEL}-comparator.txt",
    )
    verify_file_receipt(
        evidence.get("console"), "Cycles smoke console",
        evidence_root / f"{CYCLES_LABEL}-console.log",
    )
    verify_file_receipt(
        evidence.get("screenshot"), "Cycles smoke screenshot",
        evidence_root / f"{CYCLES_LABEL}-1280x720.png",
    )
    comparator = smoke.get("comparator", {})
    if comparator.get("threshold") != "0.016" or comparator.get("failPercent") != "1":
        fail("Cycles smoke threshold drift")
    if comparator.get("argv") != [str(golden_path), str(render_path), "--fail", "0.016", "--failpercent", "1", "--diff"]:
        fail("Cycles smoke comparator argv drift")
    live = live_compare(golden_path, render_path, "0.016", "1", rgb=False)
    stored = comparator.get("result", {})
    verify_metrics(stored.get("maxError"), stored.get("percentOver"), live, "Cycles smoke")
    if not live["pass"] or stored.get("pass") is not True or smoke.get("render", {}).get("completionReceipt", {}).get("status") != "OK":
        fail("Cycles smoke live comparator/render completion failed")


def selfcheck() -> int:
    if any(LABEL_RE.fullmatch(value) for value in ("", ".", "..", "-escape")):
        fail("unsafe-label negative self-check")
    exact_live = {"maxError": None, "percentOver": None, "pass": True, "output": "PASS"}
    verify_metrics(None, None, exact_live, "exact-match self-check")
    verify_metrics("-", "-", exact_live, "Cycles exact-match self-check")
    try:
        verify_metrics("0.1", "1%", exact_live, "exact-match negative self-check")
    except AssertionError:
        pass
    else:
        fail("exact-match comparator negative self-check")
    hardware_adapter = {
        "contract": ADAPTER_CONTRACT,
        "status": "ACCEPTED",
        "present": True,
        "platform": "darwin",
        "powerPreference": "high-performance",
        "isFallbackAdapter": False,
        "info": {
            "vendor": "apple", "architecture": "metal-3",
            "device": "", "description": "",
        },
        "softwareMatches": [],
        "reason": "accepted-hardware",
    }
    verify_hardware_adapter_receipt(hardware_adapter, "hardware adapter positive self-check")
    adapter_negative_fixtures = []
    for changes in ({"isFallbackAdapter": True}, {"isFallbackAdapter": None}):
        fixture = json.loads(json.dumps(hardware_adapter))
        fixture.update(changes)
        adapter_negative_fixtures.append(fixture)
    software_fixture = json.loads(json.dumps(hardware_adapter))
    software_fixture["info"] = {
        "vendor": "Google", "architecture": "SwiftShader", "device": "", "description": "",
    }
    adapter_negative_fixtures.append(software_fixture)
    masked_fixture = json.loads(json.dumps(hardware_adapter))
    masked_fixture["info"] = {
        "vendor": "apple", "architecture": "", "device": "", "description": "",
    }
    adapter_negative_fixtures.append(masked_fixture)
    reported_software_fixture = json.loads(json.dumps(hardware_adapter))
    reported_software_fixture["softwareMatches"] = ["untrusted-reported-match"]
    adapter_negative_fixtures.append(reported_software_fixture)
    for index, fixture in enumerate(adapter_negative_fixtures):
        try:
            verify_hardware_adapter_receipt(fixture, f"hardware adapter negative self-check {index}")
        except AssertionError:
            pass
        else:
            fail(f"hardware adapter negative self-check {index}")
    manifest_rows = load_manifest()
    entries = parse_blacklist()
    verify_blacklist_coverage(entries, manifest_rows)
    counts = {engine: sum(entry["engine"] == engine for entry in entries) for engine in ("workbench", "eevee", "cycles")}
    if counts != {"workbench": 1, "eevee": 17, "cycles": 0}:
        fail(f"blacklist count self-check changed: {counts}")
    if set(SHELL_FILES) != {"index", "windowed", "diagnostics", "boot", "fileBridge", "preinit"}:
        fail("served-shell set self-check changed")
    positive_f12 = {
        "method": "page.keyboard.press(F12)", "count": 1, "physicalTrustedF12": True,
        "keyReceipt": [{"key": "F12", "code": "F12", "isTrusted": True, "repeat": False,
                        "targetId": "canvas", "activeId": "canvas"}],
    }
    if not valid_physical_f12(positive_f12):
        fail("physical F12 parser self-check")
    negative_f12 = json.loads(json.dumps(positive_f12))
    negative_f12["keyReceipt"][0]["isTrusted"] = False
    if valid_physical_f12(negative_f12):
        fail("untrusted F12 negative self-check")
    orphan = [{
        "id": -1, "engine": "cycles", "patternText": "definitely_orphan\\.blend$",
        "pattern": re.compile(r"definitely_orphan\.blend$"), "reason": "negative self-check",
    }]
    try:
        verify_blacklist_coverage(orphan, manifest_rows)
    except AssertionError:
        pass
    else:
        fail("orphan blacklist negative self-check")
    print("M6_RENDER_SELFCHECK_PASS rows=20+30+27 blacklist=1+17+0 selectors=workbench,eevee,cycles-smoke,cycles-suite legacy_receipts=1 adapter=hardware-webgpu-adapter-v1")
    return 0


def main() -> int:
    if "--selfcheck" in sys.argv[1:]:
        return selfcheck()
    if "--cycles-only" in sys.argv[1:]:
        if sys.argv[1:] != ["--cycles-only"]:
            fail("--cycles-only does not accept additional arguments")
        if not LABEL_RE.fullmatch(CYCLES_SUITE_LABEL):
            fail("M6_CYCLES_RESULTS must select one immutable Cycles suite label")
        entries = parse_blacklist()
        manifest_rows = load_manifest()
        verify_blacklist_coverage(entries, manifest_rows)
        cycles = verify_cycles_suite(entries, manifest_rows)
        hashes = ",".join(
            f"{key}={sha256(path)[:12]}" for key, path in CYCLES_ARTIFACTS.items()
        )
        print(
            "M6_CYCLES_CPU_PASS "
            f"cycles={cycles[0]}pass/{cycles[1]}skip artifacts={hashes}"
        )
        return 0
    if (DEFERRED_RE.fullmatch(DEFERRED_WASM_FILENAME) is None
            or DEFERRED_WASM_FILENAME in {"blender_browser.wasm", "blender_browser.wasm.orig"}):
        fail("invalid BW_DEFERRED_WASM_FILENAME")
    for name, label in (("Workbench", WB_LABEL), ("EEVEE", EEVEE_LABEL),
                        ("Cycles smoke", CYCLES_LABEL), ("Cycles suite", CYCLES_SUITE_LABEL)):
        if not LABEL_RE.fullmatch(label):
            fail(f"unsafe or missing {name} run label: {label}")
    entries = parse_blacklist()
    manifest_rows = load_manifest()
    verify_blacklist_coverage(entries, manifest_rows)
    wb = verify_workbench(entries, manifest_rows)
    eevee = verify_eevee(entries, manifest_rows)
    cycles = verify_cycles_suite(entries, manifest_rows)
    verify_cycles_smoke()
    hashes = ",".join(f"{key}={sha256(path)[:12]}" for key, path in ARTIFACTS.items())
    print(
        "M6_RENDER_PASS "
        f"workbench={wb[0]}pass/{wb[1]}skip "
        f"eevee={eevee[0]}pass/{eevee[1]}skip "
        f"cycles={cycles[0]}pass/{cycles[1]}skip artifacts={hashes}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, IndexError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"M6_RENDER_FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
