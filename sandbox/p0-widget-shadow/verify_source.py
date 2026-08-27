#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Device-free source contract for the P0-G widget-shadow RGB fix."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHADER = ROOT / "upstream/source/blender/gpu/shaders/gpu_shader_2D_widget_shadow_frag.glsl"
INFO = ROOT / "upstream/source/blender/gpu/shaders/infos/gpu_shader_2D_widget_infos.hh"
PATCH = ROOT / "patches/0284-gpu-widget-shadow-defined-rgb.patch"
SERIES = ROOT / "patches/series"
PREVIEW = ROOT / "patches/PREVIEW_SNAPSHOT.patch"
PREVIEW_SHA = ROOT / "patches/PREVIEW_SNAPSHOT.sha256"
DIAGNOSTIC = ROOT / "sandbox/p0-widget-shadow/capture_diagnostic.mjs"

FULL_OUTPUT = "fragColor = float4(0.0f, 0.0f, 0.0f, inner_alpha * shadow_alpha);"
SPLIT_OUTPUTS = ("fragColor = float4(0.0f);", "fragColor.a = inner_alpha * shadow_alpha;")


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def validate(shader: str, info: str, patch: str, series: str, preview: str, diagnostic: str) -> None:
    require(shader.count(FULL_OUTPUT) == 1, "shadow output is not one exact black-RGB/alpha value")
    for stale in SPLIT_OUTPUTS:
        require(stale not in shader, f"split fragment output survived: {stale}")
    require(shader.count("shadowFalloff * shadowFalloff * 0.722f") == 1,
            "shadow falloff curve changed")
    require(shader.count("smoothstep(0.0f, 0.05f, innerMask)") == 1,
            "inner shadow mask changed")

    shadow_info = info[info.index("GPU_SHADER_CREATE_INFO(gpu_shader_2D_widget_shadow)"):
                       info.index("GPU_SHADER_CREATE_END()", info.index(
                           "GPU_SHADER_CREATE_INFO(gpu_shader_2D_widget_shadow)"))]
    require(shadow_info.count("PUSH_CONSTANT") == 3, "widget-shadow push interface drifted")
    require("SAMPLER(" not in shadow_info and "IMAGE(" not in shadow_info,
            "widget-shadow unexpectedly acquired sampled/image resources")

    require(patch.count(FULL_OUTPUT) == 1, "0284 patch omits the exact postimage")
    series_entries = [
        line.strip()
        for line in series.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    require(series_entries.count("0284-gpu-widget-shadow-defined-rgb.patch") == 1,
            "0284 is not one active series entry")
    require(preview.count(FULL_OUTPUT) == 1, "canonical preview omits the shadow postimage")

    for marker in ("widget-wgsl", "widget-pipeline", "widget-pass", "widget-bind-group",
                   "push-map", "push-write", "--use-webgpu-adapter=swiftshader"):
        require(marker in diagnostic, f"diagnostic lost marker: {marker}")
    require("binds no receipt" in diagnostic, "fallback diagnostic lost its nonreceipt marker")
    require(diagnostic.count(", undefined, {") == 2,
            "Playwright waitForFunction options are not in the third argument")
    require("diagnostic-failure.json" in diagnostic and "consoleTail: consoleLines.slice(-80)" in diagnostic,
            "diagnostic failure evidence is not bounded and persistent")
    require("boot failed before running" in diagnostic,
            "diagnostic does not fail early on an explicit shell boot error")


def mutation_selfcheck(values: list[str]) -> int:
    negatives = 0
    mutations = [
        (0, values[0].replace(FULL_OUTPUT, "fragColor = float4(0.0f);\n  fragColor.a = inner_alpha * shadow_alpha;")),
        (0, values[0].replace("float4(0.0f, 0.0f, 0.0f,", "float4(1.0f, 1.0f, 1.0f,")),
        (0, values[0].replace("0.722f", "0.700f")),
        (1, values[1].replace("PUSH_CONSTANT(float, alpha)",
                              "PUSH_CONSTANT(float, alpha)\nSAMPLER(0, sampler2D, shadow_tx)")),
        (3, values[3].replace("0284-gpu-widget-shadow-defined-rgb.patch", "")),
        (3, values[3] + "\n0284-gpu-widget-shadow-defined-rgb.patch\n"),
        (5, values[5].replace("widget-bind-group", "widget-group")),
        (5, values[5].replace(", undefined, {", ", {", 1)),
        (5, values[5].replace("diagnostic-failure.json", "diagnostic.json")),
        (5, values[5].replace("boot failed before running", "boot state")),
    ]
    for index, replacement in mutations:
        candidate = values.copy()
        candidate[index] = replacement
        try:
            validate(*candidate)
        except ContractError:
            negatives += 1
        else:
            raise ContractError(f"mutation {negatives + 1} escaped")
    return negatives


def main() -> None:
    paths = [SHADER, INFO, PATCH, SERIES, PREVIEW, DIAGNOSTIC]
    values = [path.read_text(encoding="utf-8") for path in paths]
    validate(*values)
    negatives = mutation_selfcheck(values)

    expected_hash, expected_name = PREVIEW_SHA.read_text(encoding="utf-8").split()
    require(expected_name == "PREVIEW_SNAPSHOT.patch", "canonical hash filename drifted")
    actual_hash = hashlib.sha256(PREVIEW.read_bytes()).hexdigest()
    require(actual_hash == expected_hash, "canonical preview hash is stale")

    reverse = subprocess.run(
        ["git", "-C", str(ROOT / "upstream"), "apply", "--check", "--reverse", str(PATCH)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    require(reverse.returncode == 0, f"0284 live reverse-apply failed: {reverse.stderr.strip()}")
    print(f"P0G_WIDGET_SHADOW_SOURCE_PASS positive=1 negative={negatives} preview={actual_hash[:12]}")


if __name__ == "__main__":
    main()
