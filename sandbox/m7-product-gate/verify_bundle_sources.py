#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail closed if the public bundle is not made from the reviewed M7 sources."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sandbox/m8-staged-deploy"))
from stage_pack import parse_manifest  # noqa: E402

GLTF_SOURCES = {
    "/bw/scripts/addons_core/io_scene_gltf2/io/com/library.py":
        "scripts/addons_core/io_scene_gltf2/io/com/library.py",
    "/bw/scripts/addons_core/io_scene_gltf2/blender/exp/export.py":
        "scripts/addons_core/io_scene_gltf2/blender/exp/export.py",
    "/bw/scripts/addons_core/io_scene_gltf2/blender/imp/mesh.py":
        "scripts/addons_core/io_scene_gltf2/blender/imp/mesh.py",
    "/bw/scripts/addons_core/io_scene_gltf2/io/exp/meshopt.py":
        "scripts/addons_core/io_scene_gltf2/io/exp/meshopt.py",
    "/bw/scripts/addons_core/io_scene_gltf2/io/imp/gltf2_io_binary_meshopt.py":
        "scripts/addons_core/io_scene_gltf2/io/imp/gltf2_io_binary_meshopt.py",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bundle",
        type=pathlib.Path,
        default=ROOT / "sandbox/m8-staged-deploy/bundle-staged",
    )
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    glue_path = bundle / "bin/blender_browser.js"
    data_path = bundle / "bin/blender_browser.data"
    missing = [path for path in (glue_path, data_path) if not path.is_file()]
    if missing:
        for path in missing:
            print("M7_BUNDLE_FAIL", f"missing bundle file: {path}")
        return 1
    glue = glue_path.read_text()
    data = data_path.read_bytes()
    _, _, entries, remote_size = parse_manifest(glue)
    index = {name: (start, end) for name, start, end in entries}

    failures: list[str] = []
    if remote_size != len(data):
        failures.append(f"stage0 manifest bytes {remote_size} != data bytes {len(data)}")
    for packed, relative in GLTF_SOURCES.items():
        if packed not in index:
            failures.append(f"missing stage0 glTF source: {packed}")
            continue
        start, end = index[packed]
        expected = (ROOT / "upstream" / relative).read_bytes()
        actual = data[start:end]
        if actual != expected:
            failures.append(
                f"stale glTF source: {packed} bundle={len(actual)} source={len(expected)}"
            )

    public_boot = (bundle / "boot-windowed.js").read_text()
    if public_boot.count("const BW_ALLOW_QUERY_DEV_HOOKS = false;") != 1:
        failures.append("public query dev-hook marker is not exactly once/false")
    if "const BW_ALLOW_QUERY_DEV_HOOKS = true;" in public_boot:
        failures.append("public bundle still enables query dev hooks")

    service_worker = (bundle / "service-worker.js").read_text()
    if "__BW_CACHE_VERSION__" in service_worker:
        failures.append("service-worker cache version placeholder was not replaced")

    deferred = json.loads((ROOT / "ledger/deferred.json").read_text())["deferred"]
    usd = [entry for entry in deferred if entry.get("id") == "usd-io-wasm"]
    if usd and (len(usd) != 1 or usd[0].get("status") != "resolved"):
        failures.append("USD is enabled but ledger/deferred.json still records an active USD deferral")
    for cache in (ROOT / "build-wasm-windowed-opt/CMakeCache.txt",):
        if cache.exists() and "WITH_USD:BOOL=ON" not in cache.read_text(errors="replace"):
            failures.append(f"USD build state is not explicit ON: {cache}")

    if failures:
        for failure in failures:
            print("M7_BUNDLE_FAIL", failure)
        return 1
    print(
        f"M7_BUNDLE_PASS gltf_sources={len(GLTF_SOURCES)} "
        f"stage0_bytes={len(data)} public_query_hooks=off usd=enabled"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
