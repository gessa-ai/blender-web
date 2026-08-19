#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run and immutably bind the focused Wasm OpenEXR/OIIO policy probe."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "sandbox/m8-wasm-split/image-policy-probe.cc"
NODE = ROOT / "tools/emsdk/node/22.16.0_64bit/bin/node"
EMXX = ROOT / "tools/emsdk/upstream/emscripten/em++"
LLVM_AR = ROOT / "tools/emsdk/upstream/bin/llvm-ar"
LLVM_NM = ROOT / "tools/emsdk/upstream/bin/llvm-nm"
ARCHIVES = (
    "libOpenImageIO.a",
    "libOpenImageIO_Util.a",
    "libOpenColorIO.a",
    "libOpenEXR-3_4.a",
    "libIlmThread-3_4.a",
    "libIex-3_4.a",
    "libOpenEXRCore-3_4.a",
    "libImath-3_2.a",
    "libfmt.a",
    "libtbb.a",
    "libexpat.a",
    "libpystring.a",
    "libyaml-cpp.a",
    "libminizip.a",
    "libzstd.a",
    "libz.a",
    "libdeflate.a",
    "libjpeg.a",
    "libpng16.a",
    "libtiff.a",
    "libopenjph.a",
)
BLENDER_ARCHIVES = (
    "libbf_imbuf.a",
    "libbf_imbuf_openexr.a",
    "libbf_imbuf_openimageio.a",
)
EXPECTED = {
    "bootstrap": {"openexr_set": True, "openexr_threads": 0,
                  "oiio_set": True, "oiio_threads": 1},
    "applied": {"openexr_set": True, "openexr_threads": 8,
                "oiio_set": True, "oiio_threads": 8},
    "rollback": {"openexr_set": True, "openexr_threads": 0,
                 "oiio_set": True, "oiio_threads": 1},
}


def identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def relative_command(command: list[str]) -> list[str]:
    return [
        str(Path(arg).relative_to(ROOT)) if arg.startswith(str(ROOT) + "/") else arg
        for arg in command
    ]


def write_receipt(output: Path, receipt: dict[str, Any]) -> None:
    (output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def parse_line(stdout: str, prefix: str) -> dict[str, Any]:
    rows = [line for line in stdout.splitlines() if line.startswith(prefix)]
    if len(rows) != 1:
        raise RuntimeError(f"expected one {prefix!r} row, found {len(rows)}")
    return json.loads(rows[0][len(prefix) :])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--no-work-log", type=Path, required=True)
    args = parser.parse_args()
    if not args.label or "/" in args.label or args.label in {".", ".."}:
        raise SystemExit("invalid label")

    output = ROOT / "sandbox/m8-wasm-split/image-policy-probe/evidence" / args.label
    output.mkdir(parents=True, exist_ok=False)
    js = output / "probe.js"
    wasm = output / "probe.wasm"
    build_log = args.build_log.resolve()
    no_work_log = args.no_work_log.resolve()
    required = [SOURCE, NODE, EMXX, LLVM_AR, LLVM_NM, build_log, no_work_log]
    blender_archives = [ROOT / "build-wasm-windowed-opt/lib" / name for name in BLENDER_ARCHIVES]
    policy_sources = [
        ROOT / "upstream/source/blender/imbuf/intern/web_thread_policy.cc",
        ROOT / "upstream/source/blender/imbuf/intern/openexr/openexr_thread_policy.cpp",
        ROOT / "upstream/source/blender/imbuf/intern/oiio/openimageio_thread_policy.cpp",
    ]
    policy_objects = [
        ROOT / "build-wasm-windowed-opt/source/blender/imbuf/CMakeFiles/bf_imbuf.dir/"
        "intern/web_thread_policy.cc.o",
        ROOT / "build-wasm-windowed-opt/source/blender/imbuf/intern/openexr/CMakeFiles/"
        "bf_imbuf_openexr.dir/openexr_thread_policy.cpp.o",
        ROOT / "build-wasm-windowed-opt/source/blender/imbuf/intern/oiio/CMakeFiles/"
        "bf_imbuf_openimageio.dir/openimageio_thread_policy.cpp.o",
    ]
    archive_members = [
        "web_thread_policy.cc.o",
        "openexr_thread_policy.cpp.o",
        "openimageio_thread_policy.cpp.o",
    ]
    required.extend([*policy_sources, *policy_objects, *blender_archives])
    required.extend(ROOT / "lib/wasm/lib" / name for name in ARCHIVES)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing probe inputs: {missing}")
    build_text = build_log.read_text(encoding="utf-8")
    no_work_text = no_work_log.read_text(encoding="utf-8")
    build_markers = [
        "Building CXX object source/blender/imbuf/CMakeFiles/bf_imbuf.dir/intern/web_thread_policy.cc.o",
        "Building CXX object source/blender/imbuf/intern/openexr/CMakeFiles/"
        "bf_imbuf_openexr.dir/openexr_thread_policy.cpp.o",
        "Building CXX object source/blender/imbuf/intern/oiio/CMakeFiles/"
        "bf_imbuf_openimageio.dir/openimageio_thread_policy.cpp.o",
        "Linking CXX static library lib/libbf_imbuf.a",
        "Linking CXX static library lib/libbf_imbuf_openexr.a",
        "Linking CXX static library lib/libbf_imbuf_openimageio.a",
    ]
    missing_build_markers = [marker for marker in build_markers if marker not in build_text]
    if missing_build_markers:
        raise RuntimeError(f"build log lacks focused policy members: {missing_build_markers}")
    if "ninja: no work to do." not in no_work_text:
        raise RuntimeError("no-work log does not prove stable focused archives")
    for source, obj in zip(policy_sources, policy_objects):
        if obj.stat().st_mtime_ns < source.stat().st_mtime_ns:
            raise RuntimeError(f"policy object predates source: {obj}")

    expected_symbols = {
        "blender::IMB_web_thread_policy_apply(int, int)": (policy_objects[0], blender_archives[0]),
        "blender::imb_thread_count_openexr_set(int)": (policy_objects[1], blender_archives[1]),
        "blender::imb_thread_count_openexr_get()": (policy_objects[1], blender_archives[1]),
        "blender::OIIO_thread_count_set(int)": (policy_objects[2], blender_archives[2]),
        "blender::OIIO_thread_count_get()": (policy_objects[2], blender_archives[2]),
    }
    nm_outputs: dict[str, str] = {}
    for path in [*policy_objects, *blender_archives]:
        nm = subprocess.run(
            [str(LLVM_NM), "--defined-only", "--demangle", str(path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        nm_outputs[str(path.relative_to(ROOT))] = nm.stdout
    symbol_counts: dict[str, dict[str, int]] = {}
    for symbol, (expected_object, expected_archive) in expected_symbols.items():
        counts = {
            path: sum(symbol in line for line in output.splitlines())
            for path, output in nm_outputs.items()
        }
        symbol_counts[symbol] = counts
        if counts[str(expected_object.relative_to(ROOT))] != 1 or \
           counts[str(expected_archive.relative_to(ROOT))] != 1 or \
           any(counts[str(path.relative_to(ROOT))] != 0 for path in policy_objects
               if path != expected_object) or \
           any(counts[str(path.relative_to(ROOT))] != 0 for path in blender_archives
               if path != expected_archive):
            raise RuntimeError(f"policy symbol ownership is not exact for {symbol}: {counts}")
    archive_member_matches: dict[str, bool] = {}
    for archive, member, obj in zip(blender_archives, archive_members, policy_objects):
        members = subprocess.run(
            [str(LLVM_AR), "t", str(archive)], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.splitlines()
        if members.count(member) != 1:
            raise RuntimeError(f"expected one {member} in {archive}, found {members.count(member)}")
        archived_object = subprocess.run(
            [str(LLVM_AR), "p", str(archive), member], cwd=ROOT, capture_output=True, check=True
        ).stdout
        matches = archived_object == obj.read_bytes()
        archive_member_matches[member] = matches
        if not matches:
            raise RuntimeError(f"{archive} member {member} differs from bound build object")
    compile_command = [
        str(EMXX),
        str(SOURCE),
        "-std=c++20",
        "-O2",
        "-pthread",
        "-sPROXY_TO_PTHREAD=1",
        "-sPTHREAD_POOL_SIZE=8",
        "-sEXIT_RUNTIME=1",
        "-sALLOW_MEMORY_GROWTH=1",
        "-sINITIAL_MEMORY=67108864",
        "-sWASM_BIGINT=1",
        f"-I{ROOT / 'upstream/source/blender/imbuf'}",
        f"-I{ROOT / 'upstream/source/blender/gpu'}",
        f"-I{ROOT / 'upstream/source/blender/blenlib'}",
        f"-I{ROOT / 'upstream/source/blender/makesdna'}",
        f"-I{ROOT / 'build-wasm-windowed-opt/source/blender/makesdna/intern'}",
        f"-I{ROOT / 'upstream/intern/guardedalloc'}",
        f"-I{ROOT / 'lib/wasm/include'}",
        f"-I{ROOT / 'lib/wasm/include/Imath'}",
        "-Wl,--start-group",
        *(str(path) for path in blender_archives),
        *(str(ROOT / "lib/wasm/lib" / name) for name in ARCHIVES),
        "-Wl,--end-group",
        "-o",
        str(js),
    ]
    compile_run = subprocess.run(
        compile_command, cwd=ROOT, text=True, capture_output=True, check=False
    )
    (output / "compile-stdout.txt").write_text(compile_run.stdout, encoding="utf-8")
    (output / "compile-stderr.txt").write_text(compile_run.stderr, encoding="utf-8")
    base_inputs = {
        "source": identity(SOURCE),
        "node": identity(NODE),
        "emxx": identity(EMXX),
        "llvmAr": identity(LLVM_AR),
        "llvmNm": identity(LLVM_NM),
        "policySources": [identity(path) for path in policy_sources],
        "policyObjects": [identity(path) for path in policy_objects],
        "blenderArchives": [identity(path) for path in blender_archives],
        "archives": [identity(ROOT / "lib/wasm/lib" / name) for name in ARCHIVES],
        "buildLog": identity(build_log),
        "noWorkLog": identity(no_work_log),
    }
    if compile_run.returncode != 0 or not js.is_file() or not wasm.is_file():
        receipt = {
            "schema": 1,
            "label": args.label,
            "verdict": "FAIL",
            "failures": [f"probe compile failed with exit code {compile_run.returncode}"],
            "compileCommand": relative_command(compile_command),
            "compileExitCode": compile_run.returncode,
            "symbolOwnership": symbol_counts,
            "archiveMembersMatchObjects": archive_member_matches,
            "inputs": base_inputs,
        }
        write_receipt(output, receipt)
        print(json.dumps(receipt, sort_keys=True))
        return 1

    run = subprocess.run(
        [str(NODE), str(js)], cwd=ROOT, text=True, capture_output=True, check=False
    )
    (output / "stdout.txt").write_text(run.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(run.stderr, encoding="utf-8")
    aggregate_row = parse_line(run.stdout, "BW_IMAGE_POLICY_AGGREGATE ")
    failures: list[str] = []
    if run.returncode != 0:
        failures.append(f"node exit code {run.returncode}")
    if aggregate_row != EXPECTED:
        failures.append(f"aggregate mismatch: {aggregate_row!r}")

    receipt = {
        "schema": 1,
        "label": args.label,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "command": [str(NODE.relative_to(ROOT)), str(js.relative_to(ROOT))],
        "compileCommand": relative_command(compile_command),
        "compileExitCode": compile_run.returncode,
        "exitCode": run.returncode,
        "aggregate": aggregate_row,
        "symbolOwnership": symbol_counts,
        "archiveMembersMatchObjects": archive_member_matches,
        "inputs": {
            **base_inputs,
            "javascript": identity(js),
            "wasm": identity(wasm),
        },
    }
    write_receipt(output, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
