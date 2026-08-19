#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Create a provenance-checked Workbench result set from immutable run inputs."""

import csv
import hashlib
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "sandbox/m6-prep/manifest.tsv"
COLOR_SCORE = {
    ("colorspace", "acescg_blackbody"): "score-ocio.json",
    ("colorspace", "rec2020_lights"): "score-ocio.json",
}
HEADER = [
    "engine", "dir", "test", "verdict", "cluster", "mean_err",
    "max_err", "pct_over", "gpuErr", "gpu_sig",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_results(path):
    rows = {}
    with path.open(newline="") as handle:
        reader = csv.reader((line for line in handle if not line.startswith("#")), delimiter="\t")
        for row in reader:
            if not row:
                continue
            row += [""] * (len(HEADER) - len(row))
            record = dict(zip(HEADER, row))
            key = (record["engine"], record["dir"], record["test"])
            if key in rows:
                raise ValueError(f"duplicate row in {path}: {key}")
            rows[key] = record
    return rows


def expected_rows():
    rows = []
    with MANIFEST.open(newline="") as handle:
        reader = csv.reader((line for line in handle if not line.startswith("#")), delimiter="\t")
        for row in reader:
            if row and row[0] == "workbench":
                rows.append((row[0], row[1], row[2]))
    if len(rows) != 20 or len(set(rows)) != 20:
        raise ValueError(f"expected 20 unique Workbench manifest rows, got {len(rows)}")
    return rows


def capture_dir(run_root, key):
    _, directory, test = key
    return run_root / "caps" / f"workbench_{directory}_{test}"


def validate_capture(run_root, key):
    manifest_path = capture_dir(run_root, key) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("sentinel") != "OK BLENDER_WORKBENCH":
        raise ValueError(f"bad sentinel for {key}: {manifest.get('sentinel')!r}")
    if manifest.get("pageCrashed") or manifest.get("pageUnresponsive"):
        raise ValueError(f"browser failure for {key}")
    if manifest.get("gpuErrorCount") != 0:
        raise ValueError(f"GPU errors for {key}: {manifest.get('gpuErrorCount')}")
    if len(manifest.get("caps", [])) != 2 or len(manifest.get("doneLines", [])) != 2:
        raise ValueError(f"expected two completed readbacks for {key}")
    return manifest_path


def score_row(score_path, key):
    score = json.loads(score_path.read_text())
    return {
        "engine": key[0],
        "dir": key[1],
        "test": key[2],
        "verdict": score.get("verdict", ""),
        "cluster": score.get("cluster", ""),
        "mean_err": score.get("mean_error", ""),
        "max_err": score.get("max_error", ""),
        "pct_over": score.get("pct_over", ""),
        "gpuErr": str(score.get("gpuErrorCount", 0)),
        "gpu_sig": score.get("gpu_sig", "") or "",
    }


def main():
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: reconcile_workbench.py PRIMARY_RUN AA_RETRY_RUN XRAY1_RETRY_RUN NEW_OUTPUT_DIR"
        )
    primary = Path(sys.argv[1]).resolve()
    aa_retry = Path(sys.argv[2]).resolve()
    xray1_retry = Path(sys.argv[3]).resolve()
    output = Path(sys.argv[4]).resolve()
    if output.exists():
        raise SystemExit(f"refusing to reuse output directory: {output}")

    primary_results = primary / "results.tsv"
    retry_results = aa_retry / "results.tsv"
    primary_rows = read_results(primary_results)
    retry_rows = read_results(retry_results)
    expected = expected_rows()
    aa_key = ("workbench", "workbench", "aa-disabled")
    xray1_key = ("workbench", "workbench", "x-ray_1")

    if set(primary_rows) != set(expected):
        raise ValueError("primary run must contain exactly the 20 Workbench manifest rows")
    if set(retry_rows) != {aa_key}:
        raise ValueError("AA retry run must contain only workbench/workbench/aa-disabled")
    invalid = primary_rows[aa_key]
    if invalid["verdict"] not in {"RENDER-ERR", "RIG-FAIL"}:
        raise ValueError("primary aa-disabled row was expected to be the explicitly excluded rig failure")

    reconciled = []
    provenance = {}
    for key in expected:
        if key == aa_key:
            row = retry_rows[key]
            run_root = aa_retry
            result_source = retry_results
            score_path = capture_dir(run_root, key) / "score.json"
            rule = "aa-only retry; excludes invalid primary-run rig row"
        elif key == xray1_key:
            run_root = xray1_retry
            score_path = capture_dir(run_root, key) / "score.json"
            row = score_row(score_path, key)
            result_source = score_path
            rule = "x-ray_1-only retry after WebGPU shadow-volume bias parity fix"
        else:
            row = primary_rows[key]
            run_root = primary
            result_source = primary_results
            score_path = capture_dir(run_root, key) / COLOR_SCORE.get(key[1:], "score.json")
            rule = "primary run"
            if key[1:] in COLOR_SCORE:
                row = score_row(score_path, key)
                rule = "primary capture; offline current-OCIO rescore"

        manifest_path = validate_capture(run_root, key)
        if row["verdict"] not in {"PASS", "FAIL"}:
            raise ValueError(f"non-functional verdict retained for {key}: {row['verdict']}")
        if int(row["gpuErr"] or 0) != 0:
            raise ValueError(f"nonzero TSV GPU error count for {key}")
        reconciled.append(row)
        provenance["/".join(key)] = {
            "rule": rule,
            "results_source": os.path.relpath(result_source, ROOT),
            "results_sha256": digest(result_source),
            "capture_manifest": os.path.relpath(manifest_path, ROOT),
            "capture_manifest_sha256": digest(manifest_path),
            "score_source": os.path.relpath(score_path, ROOT),
            "score_sha256": digest(score_path),
        }

    verdicts = {name: sum(row["verdict"] == name for row in reconciled) for name in ("PASS", "FAIL")}
    summary = {
        "rows": len(reconciled),
        "unique_rows": len({(row["engine"], row["dir"], row["test"]) for row in reconciled}),
        "strict_pass": verdicts["PASS"],
        "strict_fail": verdicts["FAIL"],
        "functional_pass": len(reconciled),
        "rows_with_gpu_errors": sum(int(row["gpuErr"] or 0) > 0 for row in reconciled),
        "invalid_primary_row_excluded": "/".join(aa_key),
        "invalid_primary_verdict": invalid["verdict"],
        "residual_tests": ["/".join((row["dir"], row["test"])) for row in reconciled if row["verdict"] == "FAIL"],
    }
    if summary != {
        "rows": 20,
        "unique_rows": 20,
        "strict_pass": 15,
        "strict_fail": 5,
        "functional_pass": 20,
        "rows_with_gpu_errors": 0,
        "invalid_primary_row_excluded": "workbench/workbench/aa-disabled",
        "invalid_primary_verdict": invalid["verdict"],
        "residual_tests": [
            "workbench/aa-disabled", "workbench/aa-single-pass", "workbench/dof",
            "workbench/in_front", "workbench/in_front_dof",
        ],
    }:
        raise ValueError(f"unexpected reconciled summary: {summary}")

    output.mkdir(parents=True)
    results_path = output / "results.tsv"
    with results_path.open("w", newline="") as handle:
        handle.write("# SPDX-FileCopyrightText: 2026 blender-web contributors\n")
        handle.write("# SPDX-License-Identifier: CC0-1.0\n")
        handle.write("# Reconciled current-tree Workbench matrix; see provenance.json.\n")
        writer = csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(reconciled)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "provenance.json").write_text(json.dumps({
        "primary_run": os.path.relpath(primary, ROOT),
        "aa_retry_run": os.path.relpath(aa_retry, ROOT),
        "xray1_retry_run": os.path.relpath(xray1_retry, ROOT),
        "manifest": os.path.relpath(MANIFEST, ROOT),
        "manifest_sha256": digest(MANIFEST),
        "excluded_primary_row": invalid,
        "rows": provenance,
    }, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(results_path)


if __name__ == "__main__":
    main()
