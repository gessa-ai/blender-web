# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed verifier for the M6 Cycles late-registration attribution."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess


SCENES = ("principled_bsdf_default", "principled_bsdf_emission_alpha")


def fail(message):
    raise SystemExit(f"M6_EDGE_VERIFY_FAIL {message}")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percent(value):
    return float(value.removesuffix("%"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("label")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    run_root = root / "sandbox/m6-cycles-edge-attribution/runs" / args.label
    analyzer = root / "sandbox/m6-cycles-edge-attribution/analyze_matrix.py"
    oracle = root / "scripts/oracle-container.sh"
    if not run_root.is_dir():
        fail(f"missing run {run_root}")

    for receipt_name in ("source-inputs.sha256", "wasm-product.sha256"):
        result = subprocess.run(
            ["sha256sum", "-c", str(run_root / receipt_name)],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            fail(f"hash receipt rejected: {receipt_name}")

    status_rows = list(csv.DictReader((run_root / "render-status.tsv").open(), delimiter="\t"))
    expected_variants = {
        "baseline",
        "film_transparent",
        "alpha_one",
        "samples_1",
        "samples_100",
        "pixel_jitter",
        "filter_box",
        "shader_diffuse",
        "geometry_flat",
        "geometry_no_subsurf",
        "geometry_plane_only",
        "geometry_sphere_only",
        "sampling_tabulated_sobol",
        "sampling_tabulated_light_tree_off",
        "addon_do_versions",
    }
    expected_pairs = {(scene, variant) for scene in SCENES for variant in expected_variants}
    actual_pairs = {(row["scene"], row["variant"]) for row in status_rows}
    if actual_pairs != expected_pairs or any(
        row["native_status"] != "0" or row["wasm_status"] != "0" for row in status_rows
    ):
        fail("render matrix is incomplete or contains a nonzero process")
    for log in (run_root / "logs").rglob("*.log"):
        if "Traceback (most recent call last)" in log.read_text(errors="replace"):
            fail(f"Python traceback in {log.relative_to(run_root)}")

    analysis = subprocess.run(
        [str(root / ".host-tools/bin/python3.13"), str(analyzer), args.label],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if analysis.returncode != 0:
        fail(f"pass analyzer rejected run: {analysis.stdout.strip()}")

    score_rows = list(csv.DictReader((run_root / "scores.tsv").open(), delimiter="\t"))
    scores = {(row["scene"], row["variant"], row["pass"]): row for row in score_rows}

    def score(scene, variant, pass_name):
        try:
            return scores[(scene, variant, pass_name)]
        except KeyError:
            fail(f"missing score {scene}/{variant}/{pass_name}")

    for scene in SCENES:
        if percent(score(scene, "baseline", "DisplayRGB")["pct_0016"]) <= 1.0:
            fail(f"baseline no longer reproduces exclusion: {scene}")
        if percent(score(scene, "addon_do_versions", "DisplayRGB")["pct_0016"]) >= 1.0:
            fail(f"versioned control does not pass native/Wasm threshold: {scene}")
        if percent(score(scene, "samples_100", "DisplayRGB")["pct_0016"]) >= percent(
            score(scene, "baseline", "DisplayRGB")["pct_0016"]
        ):
            fail(f"100-sample control does not converge: {scene}")
        if float(score(scene, "samples_1", "Position")["max"]) >= 2e-5:
            fail(f"primary position boundary moved at one sample: {scene}")
        if float(score(scene, "samples_1", "ObjectIndex")["max"]) != 0:
            fail(f"primary object identity diverged at one sample: {scene}")
        if int(score(scene, "samples_1", "DiffuseDirect")["over_0016"]) == 0:
            fail(f"direct-light pass did not reproduce first-sample divergence: {scene}")

        native_baseline = json.loads((run_root / "native" / f"{scene}__baseline.json").read_text())
        wasm_baseline = json.loads((run_root / "wasm" / f"{scene}__baseline.json").read_text())
        expected_scene_differences = {
            "sampling_pattern": ("TABULATED_SOBOL", "AUTOMATIC"),
            "use_adaptive_sampling": (False, True),
            "use_light_tree": (False, True),
        }
        for name, expected in expected_scene_differences.items():
            actual = (
                native_baseline["cyclesSettings"][name],
                wasm_baseline["cyclesSettings"][name],
            )
            if actual != expected:
                fail(f"unexpected baseline {name} values for {scene}: {actual}")

        native_fixed = json.loads(
            (run_root / "native" / f"{scene}__addon_do_versions.json").read_text()
        )
        wasm_fixed = json.loads(
            (run_root / "wasm" / f"{scene}__addon_do_versions.json").read_text()
        )
        for key in ("cyclesSettings", "worldSettings", "lightSettings", "materialSettings"):
            if native_fixed[key] != wasm_fixed[key]:
                fail(f"versioned effective settings differ for {scene}: {key}")

    default_native = json.loads(
        (run_root / "native/principled_bsdf_default__baseline.json").read_text()
    )
    default_wasm = json.loads(
        (run_root / "wasm/principled_bsdf_default__baseline.json").read_text()
    )
    extra_default_differences = {
        "blur_glossy": (0.0, 1.0),
        "sample_clamp_indirect": (0.0, 10.0),
    }
    for name, expected in extra_default_differences.items():
        actual = (
            default_native["cyclesSettings"][name],
            default_wasm["cyclesSettings"][name],
        )
        if actual != expected:
            fail(f"unexpected old-file {name} values: {actual}")
    if (
        default_native["worldSettings"]["World"]["sampling_method"],
        default_wasm["worldSettings"]["World"]["sampling_method"],
    ) != ("NONE", "AUTOMATIC"):
        fail("old-file world sampling migration is not reproduced")

    version = subprocess.run(
        [str(oracle), "oiiotool", "--version"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if version.returncode != 0 or "2.4.17.0" not in version.stdout:
        fail("pinned OIIO 2.4.17.0 is unavailable")

    comparator_dir = run_root / "golden-comparators"
    comparator_dir.mkdir(exist_ok=True)
    for scene in SCENES:
        render = run_root / "wasm" / f"{scene}__addon_do_versions.png"
        golden = root / "sandbox/m6-prep/goldens/cycles/principled_bsdf" / f"{scene}.png"
        command = [
            str(oracle),
            "oiiotool",
            str(render),
            "--ch",
            "R,G,B",
            str(golden),
            "--ch",
            "R,G,B",
            "--fail",
            "0.016",
            "--failpercent",
            "1",
            "--diff",
        ]
        result = subprocess.run(
            command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        transcript = comparator_dir / f"{scene}.txt"
        transcript.write_text(result.stdout)
        if result.returncode != 0:
            fail(f"pinned golden comparator rejected {scene}")

    summary = {
        "schema": "blender-web.m6-cycles-edge-attribution.v1",
        "label": args.label,
        "pairs": len(status_rows),
        "scoresSha256": sha256(run_root / "scores.tsv"),
        "baselinePercentOver": {
            scene: score(scene, "baseline", "DisplayRGB")["pct_0016"] for scene in SCENES
        },
        "versionedPercentOver": {
            scene: score(scene, "addon_do_versions", "DisplayRGB")["pct_0016"]
            for scene in SCENES
        },
        "pinnedGoldenComparators": {
            scene: sha256(comparator_dir / f"{scene}.txt") for scene in SCENES
        },
    }
    (run_root / "attribution-receipt.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(
        "M6_EDGE_VERIFY_OK",
        f"label={args.label}",
        f"pairs={len(status_rows)}",
        "root=late-addon-version-handler",
        "goldens=2/2",
    )


if __name__ == "__main__":
    main()
