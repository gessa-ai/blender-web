#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adversarial parity check for CAPTURE hardware-adapter receipt consumers."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MERGE = load_module("bw_merge_profiles", HERE / "merge_profiles.py")
FINALIZER = load_module("bw_finalize_wasm_split", REPO / "scripts/finalize-wasm-split.py")
CONSUMERS = (MERGE.verify_capture_browser, FINALIZER.verify_capture_browser)


def accepted_capture(platform: str = "linux") -> dict[str, object]:
    return {
        "browser": {
            "version": "149.0.7827.55",
            "playwrightRoot": str((REPO / ".m4-node/node_modules").resolve()),
            "playwrightVersion": "1.61.1",
            "pngjsVersion": "7.0.0",
            "nodeVersion": "v22.16.0",
            "args": ["--enable-unsafe-webgpu"]
            + (["--use-angle=metal"] if platform == "darwin" else []),
            "headed": True,
            "adapter": {
                "contract": "hardware-webgpu-adapter-v1",
                "status": "ACCEPTED",
                "present": True,
                "platform": platform,
                "powerPreference": "high-performance",
                "isFallbackAdapter": None,
                "info": {
                    "vendor": "NVIDIA" if platform == "linux" else "apple",
                    "architecture": "Ada" if platform == "linux" else "apple m3 max",
                    "device": "GeForce RTX 4090" if platform == "linux" else "",
                    "description": "",
                },
                "softwareMatches": [],
                "reason": "accepted-hardware",
            },
        }
    }


def rejected(capture: dict[str, object]) -> bool:
    for consumer in CONSUMERS:
        try:
            consumer(copy.deepcopy(capture), "fixture")
        except (ValueError, RuntimeError):
            continue
        return False
    return True


def main() -> None:
    positive = 0
    negative = 0
    for platform in ("linux", "darwin"):
        fixture = accepted_capture(platform)
        for consumer in CONSUMERS:
            consumer(copy.deepcopy(fixture), f"positive-{platform}")
            positive += 1

    mutations = [
        ("browser_absent", lambda value: value.pop("browser")),
        ("wrong_node", lambda value: value["browser"].update(nodeVersion="v25.1.0")),
        ("wrong_playwright", lambda value: value["browser"].update(playwrightVersion="1.61.0")),
        ("wrong_pngjs", lambda value: value["browser"].update(pngjsVersion="6.0.0")),
        ("wrong_chromium", lambda value: value["browser"].update(version="149.0.7827.54")),
        ("headless", lambda value: value["browser"].update(headed=False)),
        ("relative_modules", lambda value: value["browser"].update(playwrightRoot=".m4-node")),
        ("wrong_args", lambda value: value["browser"].update(args=[])),
        ("wrong_platform", lambda value: value["browser"]["adapter"].update(platform="win32")),
        ("fallback", lambda value: value["browser"]["adapter"].update(isFallbackAdapter=True)),
        ("wrong_fallback_type", lambda value: value["browser"]["adapter"].update(isFallbackAdapter=1)),
        ("absent", lambda value: value["browser"]["adapter"].update(present=False)),
        ("rejected", lambda value: value["browser"]["adapter"].update(status="REJECTED")),
        ("wrong_preference", lambda value: value["browser"]["adapter"].update(powerPreference="low-power")),
        ("wrong_reason", lambda value: value["browser"]["adapter"].update(reason="fixture")),
        ("claimed_match", lambda value: value["browser"]["adapter"].update(softwareMatches=["fixture"])),
        ("extra_adapter_field", lambda value: value["browser"]["adapter"].update(extra=True)),
        ("extra_info_field", lambda value: value["browser"]["adapter"]["info"].update(extra="x")),
        ("masked_info", lambda value: value["browser"]["adapter"].update(
            info={"vendor": "", "architecture": "", "device": "", "description": ""}
        )),
        ("vendor_only", lambda value: value["browser"]["adapter"].update(
            info={"vendor": "Google", "architecture": "", "device": "", "description": ""}
        )),
    ]
    for token in (*MERGE.SOFTWARE_ADAPTER_TOKENS, "CPU Vulkan adapter"):
        mutations.append(
            (
                f"software_{token}",
                lambda value, token=token: value["browser"]["adapter"]["info"].update(
                    vendor="fixture", architecture=token, device="", description=""
                ),
            )
        )
    for name, mutate in mutations:
        fixture = accepted_capture()
        mutate(fixture)
        assert rejected(fixture), f"false green: {name}"
        negative += 1

    assert MERGE.ADAPTER_CONTRACT == FINALIZER.ADAPTER_CONTRACT == "hardware-webgpu-adapter-v1"
    assert MERGE.SOFTWARE_ADAPTER_TOKENS == FINALIZER.SOFTWARE_ADAPTER_TOKENS
    assert MERGE.CHROMIUM_VERSION == FINALIZER.CAPTURE_CHROMIUM_VERSION == "149.0.7827.55"
    print(
        "BW_CAPTURE_PROFILE_ADAPTER_CONTRACT_TEST PASS "
        f"positive={positive} negative={negative} consumers={len(CONSUMERS)}"
    )


if __name__ == "__main__":
    main()
