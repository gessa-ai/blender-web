#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute and emit strict M1 evidence directly from native/Wasm raw runs.

Every process is launched by this program.  It never consumes ledger summaries
or historical PASS flags.  Outputs are immutable and restricted to the final
post-freeze evidence tree.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path(__file__).resolve().parent / "evidence"
LABEL_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")
MAIN_CORPUS = {
    "startup": "upstream/release/datafiles/startup.blend",
    "mesh_dense": "sandbox/corpus-prep/corpus/mesh_dense.blend",
    "modifiers": "sandbox/corpus-prep/corpus/modifiers.blend",
    "animation": "sandbox/corpus-prep/corpus/animation.blend",
    "materials_nodes": "sandbox/corpus-prep/corpus/materials_nodes.blend",
    "curves_text": "sandbox/corpus-prep/corpus/curves_text.blend",
    "armature": "sandbox/corpus-prep/corpus/armature.blend",
    "collections_instancing": "sandbox/corpus-prep/corpus/collections_instancing.blend",
    "stress_mixed": "sandbox/corpus-prep/corpus/stress_mixed.blend",
}
VERSIONING_PASS = {
    "v255_nodegroup25", "v260_bhead4", "v272_ge_framing", "v272_ge_keyboard",
    "v273_ge_2dexample", "v273_ge_glsl249", "v283_fcurve", "v300_smallbhead8",
    "v306_nodegroup36", "v402_layered_action",
}
VERSIONING_REFUSE = {"v230_be_ctrlobject", "v236_be_pathdist"}
CONFIG_KEYS = {
    "CMAKE_BUILD_TYPE", "CMAKE_GENERATOR", "CMAKE_HOME_DIRECTORY",
    "CMAKE_TOOLCHAIN_FILE", "WITH_GMP",
    "WITH_TESTS_SINGLE_BINARY", "WITH_TESTS_BMESH_CORE_PARITY",
}
NINJA_NO_WORK_STDOUT = b"ninja: no work to do.\n"
NINJA_LOCKED_RELATIVE = "../scripts/ninja-locked.sh"
CANONICAL_NATIVE_ORACLE = ROOT / "oracle/bpy.sh"
CANONICAL_NODE = ROOT / "tools/emsdk/node/22.16.0_64bit/bin/node"
CANONICAL_RUNTIME_JS = ROOT / "build-wasm-m1-parity/bin/blender.js"
CANONICAL_NODE_VERSION = "v22.16.0"


class RunError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise RunError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ref(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError:
        fail(f"evidence reference escapes repository: {resolved}")
    if path.is_symlink() or not resolved.is_file():
        fail(f"evidence reference is not a non-symlink file: {relative}")
    return {"path": relative.as_posix(), "bytes": resolved.stat().st_size, "sha256": sha256(resolved)}


def canonical_file(raw: Path, expected: Path, where: str) -> Path:
    lexical = raw if raw.is_absolute() else ROOT / raw
    lexical = Path(os.path.normpath(os.fspath(lexical)))
    try:
        resolved = lexical.resolve(strict=True)
        canonical = expected.resolve(strict=True)
    except OSError as error:
        fail(f"{where}: missing canonical file: {error}")
    current = Path(expected.anchor)
    symlinked = False
    for part in expected.parts[1:]:
        current /= part
        symlinked = symlinked or current.is_symlink()
    if (lexical != expected or raw.is_symlink() or symlinked or resolved != canonical
            or not canonical.is_file()):
        fail(f"{where}: path is not the exact non-symlink canonical file")
    return canonical


def write_json(path: Path, value: Any) -> Path:
    if path.exists() or path.is_symlink():
        fail(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return path


def write_lines(path: Path, lines: list[str]) -> Path:
    if path.exists() or path.is_symlink():
        fail(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for line in lines:
            if not line or line.strip() != line or "\n" in line:
                fail(f"noncanonical line for {path}: {line!r}")
            stream.write(line + "\n")
    return path


def cmake_configuration(
    artifact: Path, *, wasm: bool, expected_source: Path | None = None
) -> tuple[Path, dict[str, Any]]:
    """Find and strictly summarize the cache that produced an executable."""
    cache = next((parent / "CMakeCache.txt" for parent in artifact.parents
                  if (parent / "CMakeCache.txt").is_file()), None)
    if cache is None:
        fail(f"executable is not inside a CMake build tree: {artifact}")
    values: dict[str, str] = {}
    for raw in cache.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith(("#", "//")) or "=" not in raw or ":" not in raw.split("=", 1)[0]:
            continue
        typed, value = raw.split("=", 1)
        key, _kind = typed.split(":", 1)
        if key in CONFIG_KEYS:
            if key in values:
                fail(f"duplicate CMake cache key {key}: {cache}")
            values[key] = value
    required = {
        "CMAKE_BUILD_TYPE", "CMAKE_GENERATOR", "CMAKE_HOME_DIRECTORY",
        "WITH_GMP", "WITH_TESTS_SINGLE_BINARY",
        "WITH_TESTS_BMESH_CORE_PARITY",
    }
    if not required <= set(values):
        fail(f"CMake cache lacks required configuration keys: {cache}")
    if values["CMAKE_BUILD_TYPE"] != "Release":
        fail(f"M1 test artifact is not a Release build: {artifact}")
    source = (expected_source or (ROOT / "upstream")).resolve()
    if values["CMAKE_GENERATOR"] != "Ninja" or Path(values["CMAKE_HOME_DIRECTORY"]).resolve() != source:
        fail(f"M1 cache has wrong generator/source root: {cache}")
    for key in ("WITH_GMP", "WITH_TESTS_SINGLE_BINARY", "WITH_TESTS_BMESH_CORE_PARITY"):
        if values[key] not in {"ON", "OFF"}:
            fail(f"noncanonical boolean {key} in {cache}")
    toolchain = values.get("CMAKE_TOOLCHAIN_FILE", "")
    expected_toolchain = (
        ROOT / "tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake"
    ).resolve()
    if wasm:
        if not toolchain or Path(toolchain).resolve() != expected_toolchain:
            fail(f"wrong exact Emscripten toolchain for {artifact}")
    elif toolchain:
        fail(f"native parity cache unexpectedly names a toolchain: {artifact}")
    return cache, {
        "build_type": values["CMAKE_BUILD_TYPE"],
        "generator": "Ninja",
        "source_root": "upstream",
        "toolchain": "emscripten" if wasm else "native",
        "with_gmp": values["WITH_GMP"] == "ON",
        "with_tests_single_binary": values["WITH_TESTS_SINGLE_BINARY"] == "ON",
        "with_tests_bmesh_core_parity": values["WITH_TESTS_BMESH_CORE_PARITY"] == "ON",
    }


def require_parity_build_contract(
    name: str,
    native: Path,
    wasm_js: Path,
    native_config: dict[str, Any],
    wasm_config: dict[str, Any],
) -> None:
    """Reject renamed or configuration-incompatible parity executables."""
    for platform, config in (("native", native_config), ("Wasm", wasm_config)):
        if config["with_gmp"]:
            fail(f"{name} parity requires {platform} WITH_GMP=OFF")
        if not config["with_tests_single_binary"]:
            fail(f"{name} parity requires {platform} WITH_TESTS_SINGLE_BINARY=ON")
        if not config["with_tests_bmesh_core_parity"]:
            fail(f"{name} parity requires {platform} WITH_TESTS_BMESH_CORE_PARITY=ON")
    expected = {
        "blenlib": ("BLI_test", "BLI_test.js"),
        "bmesh_core": ("bmesh_core_test", "bmesh_core_test.js"),
    }
    if name not in expected or (native.name, wasm_js.name) != expected[name]:
        fail(f"{name} parity executable names are not the exact configured targets")


def build_ninja_provenance(artifact: Path, name: str, *, wasm: bool) -> Path:
    build_root = ROOT / ("build-wasm-m1-parity" if wasm else "build-native-m1-parity")
    expected_artifact = build_root / "bin/tests" / {
        ("blenlib", False): "BLI_test",
        ("blenlib", True): "BLI_test.js",
        ("bmesh_core", False): "bmesh_core_test",
        ("bmesh_core", True): "bmesh_core_test.js",
    }[(name, wasm)]
    if artifact.resolve() != expected_artifact.resolve():
        fail(f"{name} artifact is outside the canonical {'Wasm' if wasm else 'native'} parity root")
    ninja = build_root / "build.ninja"
    if not ninja.is_file():
        fail(f"missing CMake Ninja provenance: {ninja}")
    output = expected_artifact.relative_to(build_root).as_posix()
    prefix = f"build {output}: "
    lines = ninja.read_text(encoding="utf-8").splitlines()
    indexes = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(indexes) != 1 or "EXECUTABLE_LINKER" not in lines[indexes[0]]:
        fail(f"{name} has no unique executable output rule in {ninja}")
    start = indexes[0]
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].startswith("build ")), len(lines))
    rule = "\n".join(lines[start:end])
    object_side = lines[start].split(" | ", 1)[0]
    if name == "blenlib":
        marker = "source/blender/blenlib/CMakeFiles/BLI_test.dir/tests/"
        if marker not in object_side or "blender_test.dir" in object_side:
            fail("BLI_test output rule is not the complete dedicated BLI target")
    else:
        marker = "source/blender/bmesh/CMakeFiles/bmesh_core_test.dir/tests/bmesh_core_test.cc.o"
        if object_side.count(".cc.o") != 1 or marker not in object_side or "blender_test.dir" in object_side:
            fail("bmesh_core_test output rule is not the exact one-source target")
    require_allocator_contract(rule, name, wasm=wasm)
    require_initial_memory_contract(rule, name, wasm=wasm)
    return ninja


def require_allocator_contract(rule: str, name: str, *, wasm: bool) -> None:
    """Require the exact effective allocator for each parity link target."""
    settings = emscripten_setting_values(rule, "MALLOC")
    expected = []
    if wasm:
        expected = ["mimalloc"] if name == "blenlib" else ["mimalloc", "dlmalloc"]
    if settings != expected:
        fail(
            f"{name} {'Wasm' if wasm else 'native'} allocator settings differ: "
            f"expected={expected!r} actual={settings!r}"
        )


def require_initial_memory_contract(rule: str, name: str, *, wasm: bool) -> None:
    """Keep the dedicated bmesh image above its measured static link floor."""
    settings = emscripten_setting_values(rule, "INITIAL_MEMORY")
    legacy_settings = emscripten_setting_values(rule, "TOTAL_MEMORY")
    try:
        tokens = shlex.split(rule, posix=True)
    except ValueError as error:
        fail(f"invalid shell tokenization in Ninja link rule: {error}")
    direct_linker_settings = [token for token in tokens if "--initial-memory" in token]
    expected = ["33554432"] if wasm and name == "bmesh_core" else []
    if settings != expected or legacy_settings or direct_linker_settings:
        fail(
            f"{name} {'Wasm' if wasm else 'native'} initial-memory settings differ: "
            f"expected={expected!r} actual={settings!r} legacy={legacy_settings!r} "
            f"direct_linker={direct_linker_settings!r}"
        )


def emscripten_setting_values(command: str, setting: str) -> list[str]:
    """Parse every Emscripten-supported ``-s`` spelling for one setting."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as error:
        fail(f"invalid shell tokenization in Ninja link rule: {error}")
    values: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        value: str | None = None
        consumed = 1
        if token == "-s" and index + 1 < len(tokens):
            following = tokens[index + 1]
            if following.startswith(setting + "="):
                value = following.split("=", 1)[1]
                consumed = 2
            elif following == setting:
                # cmdline.py treats a bare setting as boolean 1. A subsequent
                # token is positional; it is never the setting's value.
                value = "1"
                consumed = 2
        elif token == f"-s{setting}":
            value = "1"
        elif token.startswith(f"-s{setting}="):
            value = token.split("=", 1)[1]
        if value is not None:
            if re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
                fail(f"Emscripten {setting} setting has noncanonical value: {value!r}")
            values.append(value)
        index += consumed
    return values


def capture(
    argv: list[str], stdout: Path, stderr: Path, *, env: dict[str, str] | None = None,
    cwd: Path = ROOT, timeout: int = 1800,
) -> int:
    for path in (stdout, stderr):
        if path.exists() or path.is_symlink():
            fail(f"refusing to overwrite raw process evidence: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    with stdout.open("xb") as out, stderr.open("xb") as err:
        try:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=out, stderr=err,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            fail(f"process timed out after {timeout}s: {argv}")
    return result.returncode


def ninja_locked_command(*arguments: str) -> list[str]:
    """Return the only canonical Ninja command for a parity build root."""
    return [NINJA_LOCKED_RELATIVE, *arguments]


def require_ninja_no_work_result(
    command: list[str],
    cwd: Path,
    returncode: int,
    stdout: bytes,
    stderr: bytes,
    *,
    expected_build_root: Path,
    expected_target: str,
) -> None:
    """Accept only an exact successful dry-run for one canonical Ninja output."""
    if command != ninja_locked_command("-n", expected_target):
        fail(f"Ninja no-work command targets the wrong output: {command!r}")
    if cwd.resolve() != expected_build_root.resolve():
        fail(f"Ninja no-work command uses the wrong build root: {cwd}")
    if returncode != 0:
        fail(f"Ninja no-work command failed with exit code {returncode}")
    if stdout != NINJA_NO_WORK_STDOUT or stderr != b"":
        fail(
            "Ninja dry-run is stale or emitted noncanonical output: "
            f"stdout={stdout!r} stderr={stderr!r}"
        )


def attest_ninja_no_work(
    artifact: Path, name: str, *, wasm: bool, out: Path
) -> dict[str, Any]:
    """Run and preserve the canonical dry-run freshness attestation."""
    build_root = ROOT / ("build-wasm-m1-parity" if wasm else "build-native-m1-parity")
    target = artifact.relative_to(build_root).as_posix()
    command = ninja_locked_command("-n", target)
    platform = "wasm" if wasm else "native"
    stdout_path = out / f"{name}-{platform}-ninja-no-work.stdout"
    stderr_path = out / f"{name}-{platform}-ninja-no-work.stderr"
    returncode = capture(
        command, stdout_path, stderr_path, cwd=build_root, timeout=120
    )
    require_ninja_no_work_result(
        command,
        build_root,
        returncode,
        stdout_path.read_bytes(),
        stderr_path.read_bytes(),
        expected_build_root=build_root,
        expected_target=target,
    )
    return {
        "command": command,
        "cwd": build_root.relative_to(ROOT).as_posix(),
        "target": target,
        "returncode": returncode,
        "stdout": ref(stdout_path),
        "stderr": ref(stderr_path),
    }


def attest_runtime_ninja_no_work(out: Path) -> dict[str, Any]:
    """Bind the complete M1 Blender runtime to a current canonical link graph."""
    build_root = ROOT / "build-wasm-m1-parity"
    target = "blender"
    command = ninja_locked_command("-n", target)
    stdout_path = out / "runtime-blender-ninja-no-work.stdout"
    stderr_path = out / "runtime-blender-ninja-no-work.stderr"
    returncode = capture(command, stdout_path, stderr_path, cwd=build_root, timeout=120)
    require_ninja_no_work_result(
        command, build_root, returncode, stdout_path.read_bytes(), stderr_path.read_bytes(),
        expected_build_root=build_root, expected_target=target,
    )
    return {
        "command": command,
        "cwd": "build-wasm-m1-parity",
        "target": target,
        "returncode": returncode,
        "stdout": ref(stdout_path),
        "stderr": ref(stderr_path),
    }


def canonicalize_gtest_occurrences(names: list[str]) -> list[str]:
    """Retain duplicate gtest registrations without collapsing multiplicity."""
    counts: dict[str, int] = {}
    for name in names:
        if "@occurrence=" in name:
            fail(f"gtest name collides with occurrence encoding: {name}")
        counts[name] = counts.get(name, 0) + 1
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        if counts[name] == 1:
            result.append(name)
            continue
        seen[name] = seen.get(name, 0) + 1
        result.append(f"{name}@occurrence={seen[name]}")
    if len(result) != len(set(result)):
        fail("gtest occurrence canonicalization is not unique")
    return result


def require_exact_gtest_names(native: list[str], wasm: list[str], expected: int) -> None:
    if native != wasm or len(native) != expected:
        fail(f"native/Wasm gtest census mismatch or not exactly {expected}")


def parse_gtest_names(text: str) -> list[str]:
    suite = ""
    result: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not raw[:1].isspace():
            if not line.endswith("."):
                fail(f"invalid gtest suite-list line: {raw!r}")
            suite = line
        else:
            test = line.strip()
            if not suite or not test or any(char.isspace() for char in test):
                fail(f"invalid gtest test-list line: {raw!r}")
            result.append(suite + test)
    if not result:
        fail("gtest list is empty")
    return canonicalize_gtest_occurrences(result)


def parse_gtest_json(path: Path) -> tuple[int, int, set[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"invalid gtest JSON {path}: {error}")
    if not isinstance(value, dict) or not isinstance(value.get("testsuites"), list):
        fail(f"gtest JSON has no testsuites array: {path}")
    raw_names: list[str] = []
    failures = 0
    for suite in value["testsuites"]:
        if not isinstance(suite, dict) or not isinstance(suite.get("name"), str):
            fail(f"malformed gtest suite in {path}")
        cases = suite.get("testsuite")
        if not isinstance(cases, list):
            fail(f"malformed gtest case array in {path}")
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("name"), str):
                fail(f"malformed gtest case in {path}")
            raw_names.append(suite["name"] + "." + case["name"])
            failed = case.get("failures")
            if isinstance(failed, list) and failed:
                failures += 1
            elif case.get("result") not in {None, "COMPLETED"}:
                failures += 1
    declared_tests = value.get("tests")
    declared_failures = value.get("failures")
    names = canonicalize_gtest_occurrences(raw_names)
    if declared_tests != len(names) or declared_failures != failures:
        fail(f"gtest JSON counters disagree with rows: {path}")
    return len(names), failures, set(names)


def canonical_gtest_arguments(name: str, *, root: Path = ROOT) -> list[str]:
    """Return the only supplemental argument contract accepted by each parity suite."""
    if name == "bmesh_core":
        return []
    if name != "blenlib":
        fail(f"unknown gtest suite argument contract: {name}")
    try:
        canonical_root = root.resolve(strict=True)
    except OSError as error:
        fail(f"M1 root is missing: {error}")
    lexical = canonical_root / "upstream/tests/files"
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        if current.is_symlink():
            fail(f"BLI test-assets path contains a symlink component: {current}")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        fail(f"BLI test-assets path is missing: {error}")
    if resolved != lexical or not lexical.is_dir():
        fail(f"BLI test-assets path is not a canonical directory: {lexical}")
    return ["--test-assets-dir", str(lexical)]


def require_gtest_arguments(name: str, extra: list[str], *, root: Path = ROOT) -> list[str]:
    expected = canonical_gtest_arguments(name, root=root)
    if extra != expected:
        fail(
            f"{name} supplemental test arguments differ: "
            f"expected={expected!r} actual={extra!r}"
        )
    return expected


def run_gtest(
    *, name: str, native: Path, wasm_js: Path, node: Path, out: Path,
    label: str, freeze_hash: str, minimum: int, extra: list[str], stamp: str,
) -> dict[str, Any]:
    require_gtest_arguments(name, extra)
    test_arguments = {
        key: list(extra)
        for key in ("native_list", "wasm_list", "native_run", "wasm_run")
    }
    wasm = wasm_js.with_suffix(".wasm")
    for path in (native, wasm_js, wasm, node):
        if not path.is_file():
            fail(f"missing {name} executable artifact: {path}")
    native_cache, native_config = cmake_configuration(native, wasm=False)
    wasm_cache, wasm_config = cmake_configuration(wasm_js, wasm=True)
    if native_cache.resolve() != (ROOT / "build-native-m1-parity/CMakeCache.txt").resolve() or \
            wasm_cache.resolve() != (ROOT / "build-wasm-m1-parity/CMakeCache.txt").resolve():
        fail(f"{name} CMake caches are outside the canonical parity roots")
    require_parity_build_contract(name, native, wasm_js, native_config, wasm_config)
    native_ninja = build_ninja_provenance(native, name, wasm=False)
    wasm_ninja = build_ninja_provenance(wasm_js, name, wasm=True)
    no_work = {
        "native": attest_ninja_no_work(native, name, wasm=False, out=out),
        "wasm": attest_ninja_no_work(wasm_js, name, wasm=True, out=out),
    }
    list_native_out = out / f"{name}-native-list.stdout"
    list_native_err = out / f"{name}-native-list.stderr"
    list_wasm_out = out / f"{name}-wasm-list.stdout"
    list_wasm_err = out / f"{name}-wasm-list.stderr"
    if capture([str(native), "--gtest_list_tests", *extra], list_native_out, list_native_err) != 0:
        fail(f"native {name} list command failed")
    if capture([str(node), str(wasm_js), "--gtest_list_tests", *extra], list_wasm_out, list_wasm_err) != 0:
        fail(f"Wasm {name} list command failed")
    native_names = parse_gtest_names(list_native_out.read_text(encoding="utf-8"))
    wasm_names = parse_gtest_names(list_wasm_out.read_text(encoding="utf-8"))
    require_exact_gtest_names(native_names, wasm_names, minimum)
    if name == "bmesh_core" and native_names != ["BMeshCoreTest.BMVertCreate"]:
        fail("bmesh_core dedicated executable must enumerate exactly BMeshCoreTest.BMVertCreate")
    native_manifest = write_lines(out / f"{name}-native-tests.txt", native_names)
    wasm_manifest = write_lines(out / f"{name}-wasm-tests.txt", wasm_names)

    native_json = out / f"{name}-native-results.json"
    wasm_json = out / f"{name}-wasm-results.json"
    native_stdout, native_stderr = out / f"{name}-native.stdout", out / f"{name}-native.stderr"
    wasm_stdout, wasm_stderr = out / f"{name}-wasm.stdout", out / f"{name}-wasm.stderr"
    native_rc = capture([str(native), *extra, f"--gtest_output=json:{native_json}"],
                        native_stdout, native_stderr)
    wasm_rc = capture([str(node), str(wasm_js), *extra, f"--gtest_output=json:{wasm_json}"],
                      wasm_stdout, wasm_stderr)
    native_total, native_failed, native_rows = parse_gtest_json(native_json)
    wasm_total, wasm_failed, wasm_rows = parse_gtest_json(wasm_json)
    expected = set(native_names)
    if (native_rc, wasm_rc, native_failed, wasm_failed) != (0, 0, 0, 0):
        fail(f"{name} is not all-pass: native rc/fail={native_rc}/{native_failed}, Wasm={wasm_rc}/{wasm_failed}")
    if native_rows != expected or wasm_rows != expected or native_total != len(expected) or wasm_total != len(expected):
        fail(f"{name} raw result keyset differs from enumerated manifest")
    raw = write_json(out / f"{name}-raw-result.json", {
        "schema": 1, "verdict": "PASS", "run_label": label,
        "source_freeze_sha256": freeze_hash, "suite": name,
        "total": len(expected), "passed": len(expected), "failed": 0, "crashed": 0,
        "test_names_sha256": sha256(native_manifest),
        "native_executable_sha256": sha256(native),
        "javascript_sha256": sha256(wasm_js), "wasm_sha256": sha256(wasm),
        "native_cmake_cache_sha256": sha256(native_cache),
        "wasm_cmake_cache_sha256": sha256(wasm_cache),
        "native_build_ninja_sha256": sha256(native_ninja),
        "wasm_build_ninja_sha256": sha256(wasm_ninja),
        "no_work": no_work,
        "test_arguments": test_arguments,
    })
    return {
        "native_executable": ref(native), "javascript": ref(wasm_js), "wasm": ref(wasm),
        "native_cmake_cache": ref(native_cache), "wasm_cmake_cache": ref(wasm_cache),
        "native_build_ninja": ref(native_ninja), "wasm_build_ninja": ref(wasm_ninja),
        "no_work": no_work,
        "test_arguments": test_arguments,
        "configuration": {"native": native_config, "wasm": wasm_config},
        "raw_result": ref(raw),
        "native_manifest": ref(native_manifest), "wasm_manifest": ref(wasm_manifest),
        "total": len(expected), "passed": len(expected), "failed": 0, "crashed": 0,
        "native_keyset_sha256": sha256(native_manifest),
        "wasm_keyset_sha256": sha256(wasm_manifest),
    }


def dump_command(
    native_blender: Path, node: Path, wasm_js: Path, source: Path, output: Path,
    stdout: Path, stderr: Path, *, wasm: bool, timeout: int = 600,
) -> int:
    script = ROOT / "sandbox/corpus-prep/state_dump.py"
    common = ["--background", "--factory-startup", "--python", str(script), "--", str(source), str(output)]
    if wasm:
        env = os.environ.copy()
        env.update({
            "BLENDER_SYSTEM_RESOURCES": str(ROOT / "upstream"),
            "BLENDER_SYSTEM_PYTHON": str(ROOT / "lib/wasm"),
            "BLENDER_SYSTEM_DATAFILES": str(ROOT / "upstream/release/datafiles"),
        })
        argv = [str(node), str(wasm_js), *common]
    else:
        env = None
        argv = [str(native_blender), "--python", str(script), "--", str(source), str(output)]
    return capture(argv, stdout, stderr, env=env, timeout=timeout)


def run_corpus(native_blender: Path, node: Path, wasm_js: Path, out: Path) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for name, relative in MAIN_CORPUS.items():
        source = ROOT / relative
        if not source.is_file():
            fail(f"missing main corpus input: {source}")
        row_dir = out / "main" / name
        native_dump, wasm_dump = row_dir / "native.json", row_dir / "wasm.json"
        nrc = dump_command(native_blender, node, wasm_js, source, native_dump,
                           row_dir / "native.stdout", row_dir / "native.stderr", wasm=False)
        wrc = dump_command(native_blender, node, wasm_js, source, wasm_dump,
                           row_dir / "wasm.stdout", row_dir / "wasm.stderr", wasm=True)
        if nrc != 0 or wrc != 0 or not native_dump.is_file() or not wasm_dump.is_file():
            fail(f"main corpus execution failed for {name}: native={nrc} Wasm={wrc}")
        if b"_dump_error" in native_dump.read_bytes() or native_dump.read_bytes() != wasm_dump.read_bytes():
            fail(f"main corpus native/Wasm state mismatch: {name}")
        state = sha256(native_dump)
        rows[name] = {
            "blend": ref(source), "native_dump": ref(native_dump), "wasm_dump": ref(wasm_dump),
            "native_state_sha256": state, "wasm_state_sha256": state, "equal": True,
        }
    manifest = write_json(out / "main-corpus-manifest.json", {"names": sorted(rows)})
    return {"manifest": ref(manifest), "total": 9, "equal": 9, "rows": rows}


def versioning_inputs() -> dict[str, Path]:
    result: dict[str, Path] = {}
    corpus_list = ROOT / "sandbox/corpus-prep/versioning/corpus.list"
    for line in corpus_list.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) != 5:
            fail(f"malformed versioning corpus row: {line}")
        name, raw = fields[:2]
        source = Path(raw)
        result[name] = source if source.is_absolute() else ROOT / source
    if set(result) != VERSIONING_PASS | VERSIONING_REFUSE:
        fail("versioning corpus is not exact 12-key contract")
    return result


def run_versioning(native_blender: Path, node: Path, wasm_js: Path, out: Path) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for name, source in versioning_inputs().items():
        row_dir = out / "versioning" / name
        native_dump, wasm_dump = row_dir / "native-dump.json", row_dir / "wasm-dump.json"
        nstdout, nstderr = row_dir / "native.stdout", row_dir / "native.stderr"
        wstdout, wstderr = row_dir / "wasm.stdout", row_dir / "wasm.stderr"
        nrc = dump_command(native_blender, node, wasm_js, source, native_dump, nstdout, nstderr, wasm=False)
        wrc = dump_command(native_blender, node, wasm_js, source, wasm_dump, wstdout, wstderr, wasm=True)
        expected = "PASS" if name in VERSIONING_PASS else "ORACLE_REFUSE"
        if expected == "PASS":
            if nrc != 0 or wrc != 0 or not native_dump.is_file() or not wasm_dump.is_file():
                fail(f"versioning PASS execution failed for {name}: native={nrc} Wasm={wrc}")
            payload = native_dump.read_bytes()
            if b"_dump_error" in payload or payload != wasm_dump.read_bytes():
                fail(f"versioning state mismatch: {name}")
            native_result, wasm_result = native_dump, wasm_dump
        else:
            native_text = nstderr.read_text(encoding="utf-8", errors="replace")
            wasm_text = wstderr.read_text(encoding="utf-8", errors="replace")
            refusal = re.compile(r"Big Endian|removed|refus|load produced no dump", re.I)
            if native_dump.exists() or wasm_dump.exists() or not refusal.search(native_text) or not refusal.search(wasm_text):
                fail(f"versioning refusal is not independently reproduced: {name}")
            canonical = json.dumps({
                "outcome": "ORACLE_REFUSE", "name": name,
                "native_stderr_sha256": sha256(nstderr), "wasm_stderr_sha256": sha256(wstderr),
            }, sort_keys=True) + "\n"
            native_result = row_dir / "native-result.txt"
            wasm_result = row_dir / "wasm-result.txt"
            native_result.write_text(canonical, encoding="utf-8")
            wasm_result.write_text(canonical, encoding="utf-8")
        state = sha256(native_result)
        if state != sha256(wasm_result):
            fail(f"versioning canonical result differs: {name}")
        rows[name] = {
            "blend": ref(source), "native_result": ref(native_result), "wasm_result": ref(wasm_result),
            "native_outcome": expected, "wasm_outcome": expected,
            "native_state_sha256": state, "wasm_state_sha256": state, "equal": True,
        }
    manifest = write_json(out / "versioning-manifest.json", {"names": sorted(rows)})
    return {"manifest": ref(manifest), "total": 12, "pass": 10,
            "oracle_refuse": 2, "equal": 12, "rows": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--freeze-receipt", type=Path, required=True,
                        help="composite upstream child receipt (external or copied)")
    parser.add_argument("--native-blenlib", type=Path, required=True)
    parser.add_argument("--wasm-blenlib-js", type=Path, required=True)
    parser.add_argument("--native-bmesh", type=Path, required=True)
    parser.add_argument("--wasm-bmesh-js", type=Path, required=True)
    parser.add_argument("--native-blender", type=Path, required=True)
    parser.add_argument("--wasm-blender-js", type=Path, required=True)
    parser.add_argument("--node", type=Path,
                        default=ROOT / "tools/emsdk/node/22.16.0_64bit/bin/node")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if LABEL_RE.fullmatch(args.run_label) is None:
            fail("unsafe run label")
        output = OUTPUT_ROOT / args.run_label / "m1"
        if output.exists() or output.is_symlink():
            fail(f"refusing to overwrite M1 attempt: {output}")
        output.mkdir(parents=True)
        incomplete = output / "INCOMPLETE"
        incomplete.write_text("M1 raw execution in progress\n", encoding="utf-8")
        freeze = json.loads(args.freeze_receipt.read_text(encoding="utf-8"))
        if freeze.get("schema") != 1 or freeze.get("verdict") != "PASS":
            fail("source freeze is not schema-1 PASS")
        if Path(str(freeze.get("source", ""))).resolve() != (ROOT / "upstream").resolve():
            fail("source freeze does not identify the canonical upstream source root")
        freeze_hash = sha256(args.freeze_receipt)
        stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        common = {"schema": 1, "verdict": "PASS", "run_label": args.run_label,
                  "created_utc": stamp, "source_freeze_sha256": freeze_hash}
        raw = output / "raw"
        native_blender = canonical_file(
            args.native_blender, CANONICAL_NATIVE_ORACLE, "M1 native Blender oracle"
        )
        node = canonical_file(args.node, CANONICAL_NODE, "M1 Node runtime")
        runtime_js = canonical_file(
            args.wasm_blender_js, CANONICAL_RUNTIME_JS, "M1 Blender JavaScript runtime"
        )
        runtime_wasm = canonical_file(
            runtime_js.with_suffix(".wasm"), CANONICAL_RUNTIME_JS.with_suffix(".wasm"),
            "M1 Blender Wasm runtime",
        )
        runtime_cache, _runtime_config = cmake_configuration(runtime_js, wasm=True)
        runtime_cache = canonical_file(
            runtime_cache, ROOT / "build-wasm-m1-parity/CMakeCache.txt",
            "M1 Blender CMake cache",
        )
        runtime_ninja = canonical_file(
            ROOT / "build-wasm-m1-parity/build.ninja",
            ROOT / "build-wasm-m1-parity/build.ninja", "M1 Blender Ninja graph",
        )
        node_version = subprocess.run(
            [str(node), "--version"], capture_output=True, text=True, check=True
        ).stdout.strip()
        if node_version != CANONICAL_NODE_VERSION:
            fail(f"M1 Node version must be exactly {CANONICAL_NODE_VERSION}")
        runtime_no_work = attest_runtime_ninja_no_work(raw)
        runtime_raw = write_json(raw / "runtime-provenance.json", common | {
            "native_oracle_sha256": sha256(native_blender),
            "node_sha256": sha256(node), "node_version": node_version,
            "javascript_sha256": sha256(runtime_js), "wasm_sha256": sha256(runtime_wasm),
            "cmake_cache_sha256": sha256(runtime_cache),
            "build_ninja_sha256": sha256(runtime_ninja),
            "no_work": runtime_no_work,
        })
        blenlib = run_gtest(
            name="blenlib", native=args.native_blenlib.resolve(), wasm_js=args.wasm_blenlib_js.resolve(),
            node=node, out=raw / "gtests", label=args.run_label,
            freeze_hash=freeze_hash, minimum=1667,
            extra=canonical_gtest_arguments("blenlib"), stamp=stamp,
        )
        bmesh = run_gtest(
            name="bmesh_core", native=args.native_bmesh.resolve(), wasm_js=args.wasm_bmesh_js.resolve(),
            node=node, out=raw / "gtests", label=args.run_label,
            freeze_hash=freeze_hash, minimum=1, extra=[], stamp=stamp,
        )
        main_corpus = run_corpus(native_blender, node, runtime_js, raw)
        versioning = run_versioning(native_blender, node, runtime_js, raw)
        receipt = write_json(output / "receipt.json", common | {
            "runtime": {
                "native_oracle": ref(native_blender), "node": ref(node),
                "javascript": ref(runtime_js), "wasm": ref(runtime_wasm),
                "cmake_cache": ref(runtime_cache), "build_ninja": ref(runtime_ninja),
                "node_version": node_version, "worker_boot": True,
                "no_work": runtime_no_work, "raw_provenance": ref(runtime_raw),
            },
            "gtests": {"blenlib": blenlib, "bmesh_core": bmesh},
            "main_corpus": main_corpus, "versioning": versioning,
        })
        incomplete.unlink()
        print(f"FINAL_M1_RAW_PASS receipt={receipt.relative_to(ROOT)} sha256={sha256(receipt)}")
        return 0
    except (RunError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"FINAL_M1_RAW_FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
