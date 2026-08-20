# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Score native/Wasm PNG RGB and individual multilayer EXR passes."""

import argparse
import csv
from pathlib import Path
import re
import subprocess


PASS_CHANNELS = {
    "Combined.RGB": "RenderLayer.Combined.R,RenderLayer.Combined.G,RenderLayer.Combined.B",
    "Combined.A": "RenderLayer.Combined.A",
    "Depth": "RenderLayer.Depth.Z",
    "Position": "RenderLayer.Position.X,RenderLayer.Position.Y,RenderLayer.Position.Z",
    "Normal": "RenderLayer.Normal.X,RenderLayer.Normal.Y,RenderLayer.Normal.Z",
    "UV": "RenderLayer.UV.U,RenderLayer.UV.V",
    "ObjectIndex": "RenderLayer.Object Index.X",
    "MaterialIndex": "RenderLayer.Material Index.X",
    "AmbientOcclusion": (
        "RenderLayer.Ambient Occlusion.R,RenderLayer.Ambient Occlusion.G,"
        "RenderLayer.Ambient Occlusion.B"
    ),
    "DiffuseColor": (
        "RenderLayer.Diffuse Color.R,RenderLayer.Diffuse Color.G,RenderLayer.Diffuse Color.B"
    ),
    "DiffuseDirect": (
        "RenderLayer.Diffuse Direct.R,RenderLayer.Diffuse Direct.G,RenderLayer.Diffuse Direct.B"
    ),
    "DiffuseIndirect": (
        "RenderLayer.Diffuse Indirect.R,RenderLayer.Diffuse Indirect.G,"
        "RenderLayer.Diffuse Indirect.B"
    ),
    "GlossyColor": (
        "RenderLayer.Glossy Color.R,RenderLayer.Glossy Color.G,RenderLayer.Glossy Color.B"
    ),
    "GlossyDirect": (
        "RenderLayer.Glossy Direct.R,RenderLayer.Glossy Direct.G,RenderLayer.Glossy Direct.B"
    ),
    "GlossyIndirect": (
        "RenderLayer.Glossy Indirect.R,RenderLayer.Glossy Indirect.G,"
        "RenderLayer.Glossy Indirect.B"
    ),
    "TransmissionColor": (
        "RenderLayer.Transmission Color.R,RenderLayer.Transmission Color.G,"
        "RenderLayer.Transmission Color.B"
    ),
    "TransmissionDirect": (
        "RenderLayer.Transmission Direct.R,RenderLayer.Transmission Direct.G,"
        "RenderLayer.Transmission Direct.B"
    ),
    "TransmissionIndirect": (
        "RenderLayer.Transmission Indirect.R,RenderLayer.Transmission Indirect.G,"
        "RenderLayer.Transmission Indirect.B"
    ),
    "Emission": "RenderLayer.Emission.R,RenderLayer.Emission.G,RenderLayer.Emission.B",
    "Environment": (
        "RenderLayer.Environment.R,RenderLayer.Environment.G,RenderLayer.Environment.B"
    ),
}

STAT_PATTERNS = {
    "mean": re.compile(r"Mean error = ([^\s]+)"),
    "rms": re.compile(r"RMS error = ([^\s]+)"),
    "max": re.compile(r"Max error\s+= ([^\s]+)"),
}
OVER_PATTERN = re.compile(r"(\d+) pixels \(([^)]+)\) over ([^\s]+)")


def compare(oiiotool, native, wasm, channels):
    command = [
        str(oiiotool),
        str(native),
        "--ch",
        channels,
        str(wasm),
        "--ch",
        channels,
        "--warn",
        "1e-6",
        "--fail",
        "0.016",
        "--failpercent",
        "0",
        "--diff",
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = result.stdout
    if "Computing diff of" in output and output.rstrip().endswith("PASS"):
        return {
            "mean": "0",
            "rms": "0",
            "max": "0",
            "over_1e6": "0",
            "pct_1e6": "0%",
            "over_0016": "0",
            "pct_0016": "0%",
        }
    stats = {}
    for name, pattern in STAT_PATTERNS.items():
        match = pattern.search(output)
        if match is None:
            raise RuntimeError(f"missing {name} statistic for {native.name}: {output.strip()}")
        stats[name] = match.group(1)
    over = {threshold: (pixels, percent) for pixels, percent, threshold in OVER_PATTERN.findall(output)}
    stats["over_1e6"], stats["pct_1e6"] = over.get("1e-06", ("0", "0%"))
    stats["over_0016"], stats["pct_0016"] = over.get("0.016", ("0", "0%"))
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("label")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    run_root = root / "sandbox/m6-cycles-edge-attribution/runs" / args.label
    oiiotool = root / "sandbox/m6-cycles-simd-probe/oiiotool-linux.sh"
    if not run_root.is_dir():
        raise SystemExit(f"missing run: {run_root}")

    native_files = sorted((run_root / "native").glob("*.exr"))
    if not native_files:
        raise SystemExit("no native EXRs")

    rows = []
    for native_exr in native_files:
        stem = native_exr.stem
        scene, variant = stem.split("__", 1)
        wasm_exr = run_root / "wasm" / native_exr.name
        native_png = native_exr.with_suffix(".png")
        wasm_png = wasm_exr.with_suffix(".png")
        targets = [("DisplayRGB", native_png, wasm_png, "R,G,B")]
        targets.extend(
            (pass_name, native_exr, wasm_exr, channels)
            for pass_name, channels in PASS_CHANNELS.items()
        )
        for pass_name, native, wasm, channels in targets:
            stats = compare(oiiotool, native, wasm, channels)
            rows.append({"scene": scene, "variant": variant, "pass": pass_name, **stats})

    output = run_root / "scores.tsv"
    fieldnames = (
        "scene",
        "variant",
        "pass",
        "mean",
        "rms",
        "max",
        "over_1e6",
        "pct_1e6",
        "over_0016",
        "pct_0016",
    )
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"M6_EDGE_ANALYZE_OK label={args.label} pairs={len(native_files)} rows={len(rows)}")


if __name__ == "__main__":
    main()
