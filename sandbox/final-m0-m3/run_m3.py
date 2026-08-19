#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the strict 197-test GPU census and named cold/warm shader census."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path(__file__).resolve().parent / "evidence"
LABEL_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")
SHADER_ROW_RE = re.compile(r"^BW_SHADER_RESULT (PASS|FAIL) ([A-Za-z0-9_.-]+)$", re.MULTILINE)
CACHE_ROW_RE = re.compile(r"^BW_SHADER_CACHE_RESULT (HIT|MISS) ([A-Za-z0-9_.-]+)$", re.MULTILINE)
CACHE_FILE_RE = re.compile(r"[0-9a-f]{32}\.wgslc")
CENSUS_BEGIN = "BW_SHADER_CENSUS_BEGIN"
CENSUS_END = "BW_SHADER_CENSUS_END"
UNCAPTURED_DEVICE_ERROR = "[WebGPU] uncaptured device error"
MEMORY_LEAK_ERROR = "Error: Not freed memory blocks"
GPU_TEST_COUNT = 197
STATIC_SHADER_COUNT = 1003
GPU_TEST_CANONICAL_MANIFEST = Path(__file__).resolve().parent / "gpu_webgpu_tests.txt"
STATIC_SHADER_CANONICAL_MANIFEST = Path(__file__).resolve().parent / "static_shader_identities.txt"
DRAW_WEBGPU_TESTS = (
    "DrawWebGPUTest.draw_curves_lib",
    "DrawWebGPUTest.draw_debug_lifetime_rebind",
)
REQUIRED_SHADER_ID = "draw_debug_draw_compact"
FORBIDDEN_SHADER_ID = "fullscreen_blit"
WEBGPU_DEVICE_LIMIT_FIELDS = (
    "maxStorageTexturesPerShaderStage",
    "maxSampledTexturesPerShaderStage",
    "maxSamplersPerShaderStage",
    "maxStorageBuffersPerShaderStage",
    "maxBufferSize",
    "maxStorageBufferBindingSize",
    "maxColorAttachmentBytesPerSample",
    "maxComputeWorkgroupStorageSize",
    "maxComputeInvocationsPerWorkgroup",
    "maxComputeWorkgroupSizeX",
)
WEBGPU_DEVICE_LIMIT_PATHS = {
    "native_context": ROOT / "upstream/intern/ghost/intern/GHOST_ContextWGPU.cc",
    "web_fallback": ROOT / "platform_web/ghost/GHOST_ContextWGPUWeb.cc",
    "worker_preinit": ROOT / "platform_web/shell/wgpu-preinit-worker.js",
}
CACHE_MARKER_SOURCE = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_shader_compiler.cc"
OPENSUBDIV_VERSION = "v3_7_0"
OPENSUBDIV_TARBALL_MD5 = "470d53c4d4335a601c33a052ce7c33b4"
OPENSUBDIV_SOURCE_PATHS = {
    "recipe": ROOT / "scripts/deps/opensubdiv.sh",
    "configure": ROOT / "patches/blender_web.cmake",
    "upstream_cmake": ROOT / "upstream/intern/opensubdiv/CMakeLists.txt",
    "evaluator": ROOT / "upstream/intern/opensubdiv/internal/evaluator/evaluator_capi.cc",
}
OPENSUBDIV_HEADER = ROOT / "lib/wasm/include/opensubdiv/osd/glslPatchShaderSource.h"
OPENSUBDIV_CPU_ARCHIVE = ROOT / "lib/wasm/lib/libosdCPU.a"
OPENSUBDIV_GPU_ARCHIVE = ROOT / "lib/wasm/lib/libosdGPU.a"
OPENSUBDIV_EMAR = ROOT / "tools/emsdk/upstream/emscripten/emar"
OPENSUBDIV_EMNM = ROOT / "tools/emsdk/upstream/emscripten/emnm"
M3_BUILD_ROOT = ROOT / "build-native-gpu"
M3_BINARY = M3_BUILD_ROOT / "bin/tests/blender_test"
M3_CMAKE_CACHE = M3_BUILD_ROOT / "CMakeCache.txt"
M3_BUILD_NINJA = M3_BUILD_ROOT / "build.ninja"
M3_NINJA_TARGET = "blender_test"
NINJA_NO_WORK_STDOUT = b"ninja: no work to do.\n"


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
        fail(f"reference escapes repository: {resolved}")
    if path.is_symlink() or not resolved.is_file():
        fail(f"reference is not one non-symlink file: {relative}")
    return {"path": relative.as_posix(), "bytes": resolved.stat().st_size, "sha256": sha256(resolved)}


def exact_name_manifest(path: Path, expected_count: int, where: str) -> list[str]:
    if path.is_symlink() or not path.is_file():
        fail(f"{where} is missing, non-regular, or a symlink: {path}")
    payload = path.read_bytes()
    try:
        names = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        fail(f"{where} is not UTF-8: {error}")
    if payload != ("\n".join(names) + "\n").encode("utf-8"):
        fail(f"{where} is not canonical LF-terminated text")
    if (len(names) != expected_count or len(set(names)) != expected_count or
            any(re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None for name in names)):
        fail(f"{where} is not exactly {expected_count} unique canonical identities")
    return names


def critical_input_paths(
    binary: Path, cmake_cache: Path, build_ninja: Path
) -> dict[str, Path]:
    return {
        "binary": binary,
        "cmake_cache": cmake_cache,
        "build_ninja": build_ninja,
        "gpu_canonical_manifest": GPU_TEST_CANONICAL_MANIFEST,
        "static_shader_canonical_manifest": STATIC_SHADER_CANONICAL_MANIFEST,
        "cache_marker_source": CACHE_MARKER_SOURCE,
        **{f"device_limit_{key}": path for key, path in WEBGPU_DEVICE_LIMIT_PATHS.items()},
        **{f"opensubdiv_source_{key}": path for key, path in OPENSUBDIV_SOURCE_PATHS.items()},
        "opensubdiv_header": OPENSUBDIV_HEADER,
        "opensubdiv_cpu_archive": OPENSUBDIV_CPU_ARCHIVE,
        "opensubdiv_gpu_archive": OPENSUBDIV_GPU_ARCHIVE,
        "opensubdiv_tool_emar": OPENSUBDIV_EMAR,
        "opensubdiv_tool_emnm": OPENSUBDIV_EMNM,
    }


def critical_input_snapshot(
    paths: dict[str, Path], *, root: Path = ROOT
) -> list[str]:
    rows: list[str] = []
    for key in sorted(paths):
        path = paths[key]
        resolved = path.resolve(strict=True)
        try:
            relative = resolved.relative_to(root.resolve(strict=True))
        except ValueError:
            fail(f"critical input escapes repository: {resolved}")
        if path.is_symlink() or not resolved.is_file():
            fail(f"critical input is not one non-symlink file: {relative}")
        rows.append(
            f"{key}\t{relative.as_posix()}\t{resolved.stat().st_size}\t{sha256(resolved)}"
        )
    return rows


def require_webgpu_device_limit_contract(
    paths: dict[str, Path] = WEBGPU_DEVICE_LIMIT_PATHS,
) -> None:
    if set(paths) != set(WEBGPU_DEVICE_LIMIT_PATHS):
        fail("WebGPU device-limit source keyset is not canonical")
    expected = set(WEBGPU_DEVICE_LIMIT_FIELDS)
    for key in ("native_context", "web_fallback"):
        path = paths[key]
        if path.is_symlink() or not path.is_file():
            fail(f"WebGPU device-limit source is missing, non-regular, or a symlink: {path}")
        text = path.read_text(encoding="utf-8")
        assignments = re.findall(
            r"\brequired_limits\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+);",
            text,
        )
        names = [name for name, _ in assignments]
        if len(assignments) != len(expected) or set(names) != expected:
            fail(f"{key} WebGPU required-limit assignments are not the exact 10-field keyset")
        for name, value in assignments:
            normalized = re.sub(r"\s+", "", value)
            if normalized != f"supported_limits.{name}":
                fail(f"{key} WebGPU required limit {name} does not use its adapter-supported value")
        descriptor = "device_desc" if key == "native_context" else "desc"
        if len(re.findall(
            rf"\b{descriptor}\.requiredLimits\s*=\s*&required_limits\s*;", text
        )) != 1:
            fail(f"{key} does not bind the exact required-limit structure to RequestDevice")

    worker = paths["worker_preinit"]
    if worker.is_symlink() or not worker.is_file():
        fail(f"WebGPU worker device-limit source is missing, non-regular, or a symlink: {worker}")
    text = worker.read_text(encoding="utf-8")
    objects = re.findall(r"\bvar requiredLimits\s*=\s*\{(.*?)\n\s*\};", text, re.DOTALL)
    if len(objects) != 1:
        fail("worker WebGPU requiredLimits object is missing or duplicated")
    assignments = re.findall(
        r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^,]+),\s*$",
        objects[0],
        re.MULTILINE,
    )
    names = [name for name, _ in assignments]
    if len(assignments) != len(expected) or set(names) != expected:
        fail("worker WebGPU required-limit assignments are not the exact 10-field keyset")
    for name, value in assignments:
        normalized = re.sub(r"\s+", "", value)
        if normalized != f"adapter.limits.{name}":
            fail(f"worker WebGPU required limit {name} does not use its adapter value")
    if len(re.findall(r"\brequiredLimits\s*:\s*requiredLimits\s*,", text)) != 1:
        fail("worker does not bind the exact requiredLimits object to requestDevice")


def require_cache_marker_activation_contract(path: Path = CACHE_MARKER_SOURCE) -> None:
    if path.is_symlink() or not path.is_file():
        fail(f"WebGPU cache-marker source is missing, non-regular, or a symlink: {path}")
    text = path.read_text(encoding="utf-8")
    for token in (
        'std::getenv("BW_SHADER_CACHE_CENSUS_DIR")',
        'std::getenv("BW_SHADER_CACHE_DIR")',
        "emit_cache_result(sources.name)",
    ):
        if text.count(token) != 1:
            fail(f"WebGPU cache-marker source lacks one exact activation token: {token}")
    activation = re.compile(
        r'const\s+char\s+\*census_dir\s*=\s*std::getenv\('
        r'"BW_SHADER_CACHE_CENSUS_DIR"\)\s*;\s*'
        r'if\s*\(census_dir\s*==\s*nullptr\)\s*\{\s*return\s+true\s*;\s*\}\s*'
        r'const\s+char\s+\*active_dir\s*=\s*std::getenv\('
        r'"BW_SHADER_CACHE_DIR"\)\s*;\s*'
        r"if\s*\(active_dir\s*==\s*nullptr\s*\|\|\s*active_dir\[0\]\s*==\s*'\\0'\s*"
        r'\|\|\s*std::strcmp\(active_dir,\s*census_dir\)\s*!=\s*0\)\s*'
        r'\{\s*return\s+false\s*;\s*\}',
        re.DOTALL,
    )
    if activation.search(text) is None:
        fail(
            "WebGPU census cache markers are not suppressed until the exact "
            "census cache directory is active"
        )


def require_opensubdiv_source_contract() -> None:
    paths = list(OPENSUBDIV_SOURCE_PATHS.values()) + [
        OPENSUBDIV_HEADER, OPENSUBDIV_CPU_ARCHIVE, OPENSUBDIV_GPU_ARCHIVE,
        OPENSUBDIV_EMAR, OPENSUBDIV_EMNM,
    ]
    for path in paths:
        if path.is_symlink() or not path.is_file():
            fail(f"OpenSubdiv provenance input is missing, non-regular, or a symlink: {path}")
    recipe = OPENSUBDIV_SOURCE_PATHS["recipe"].read_text(encoding="utf-8")
    if (recipe.count(f'OSD_VERSION="{OPENSUBDIV_VERSION}"') != 1 or
            recipe.count(f'OSD_MD5="{OPENSUBDIV_TARBALL_MD5}"') != 1):
        fail("OpenSubdiv recipe does not pin the exact v3_7_0 tarball MD5")
    configure = OPENSUBDIV_SOURCE_PATHS["configure"].read_text(encoding="utf-8")
    if "libosdCPU.a" not in configure or "libosdGPU.a" not in configure:
        fail("WebAssembly configure does not link both OpenSubdiv archives")
    cmake = OPENSUBDIV_SOURCE_PATHS["upstream_cmake"].read_text(encoding="utf-8")
    if ("if(WITH_WEBGPU_BACKEND)" not in cmake or
            "add_definitions(-DWITH_WEBGPU_BACKEND)" not in cmake):
        fail("OpenSubdiv CMake does not propagate the WebGPU backend define")
    evaluator = OPENSUBDIV_SOURCE_PATHS["evaluator"].read_text(encoding="utf-8")
    for marker in (
        "defined(WITH_WEBGPU_BACKEND)", "GPU_BACKEND_WEBGPU",
        "GLSLPatchShaderSource::GetPatchBasisShaderSource()",
    ):
        if marker not in evaluator:
            fail(f"OpenSubdiv evaluator lacks WebGPU GLSL source selection: {marker}")
    header = OPENSUBDIV_HEADER.read_text(encoding="utf-8")
    if ("class GLSLPatchShaderSource" not in header or
            "static std::string GetPatchBasisShaderSource();" not in header):
        fail("harvested OpenSubdiv GLSL patch-source header lacks the required API")
    if OPENSUBDIV_CPU_ARCHIVE.stat().st_size <= 8 or OPENSUBDIV_GPU_ARCHIVE.stat().st_size <= 8:
        fail("harvested OpenSubdiv archive is empty")


def require_opensubdiv_binary_proof(
    members: str, defined: str, undefined: str, smoke: str
) -> None:
    member_names = [line.strip() for line in members.splitlines() if line.strip()]
    if not any("glslPatchShaderSource" in name for name in member_names):
        fail("OpenSubdiv GPU archive lacks the GLSL patch-source object")
    forbidden_members = ("glComputeEvaluator", "glVertexBuffer", "glPatchTable", "glMesh")
    if any(any(token in name for token in forbidden_members) for name in member_names):
        fail("OpenSubdiv GPU archive contains forbidden OpenGL API objects")
    symbol = (
        "OpenSubdiv::v3_7_0::Osd::GLSLPatchShaderSource::"
        "GetPatchBasisShaderSource()"
    )
    if re.search(rf"(?m)^\S+\s+[TtWw]\s+{re.escape(symbol)}$", defined) is None:
        fail("OpenSubdiv GPU archive lacks the defined GLSL patch-source symbol")
    if re.search(r"(?:^|\s)_?gl[A-Z]", undefined, re.MULTILINE) is not None:
        fail("OpenSubdiv GPU archive imports an OpenGL API symbol")
    if re.search(
        r"OSD_WASM_REFINE nverts_level1=26 glsl_bytes=[1-9][0-9]* "
        r"param=1 evaluate=1",
        smoke,
    ) is None:
        fail("OpenSubdiv Wasm smoke lacks Far=26 and both GLSL source markers")


def capture_command_log(command: list[str], output: Path, timeout: int = 300) -> str:
    if output.exists() or output.is_symlink():
        fail(f"refusing to overwrite OpenSubdiv proof output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        try:
            result = subprocess.run(
                command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            fail(f"OpenSubdiv proof command timed out: {command!r}")
    if result.returncode != 0:
        fail(f"OpenSubdiv proof command failed rc={result.returncode}: {command!r}")
    return output.read_text(encoding="utf-8", errors="replace")


def capture_opensubdiv_proof(output: Path) -> dict[str, Any]:
    require_opensubdiv_source_contract()
    members_path = output / "opensubdiv-gpu-members.log"
    defined_path = output / "opensubdiv-gpu-defined.log"
    undefined_path = output / "opensubdiv-gpu-undefined.log"
    smoke_path = output / "opensubdiv-wasm-smoke.log"
    members = capture_command_log(
        [str(OPENSUBDIV_EMAR), "t", str(OPENSUBDIV_GPU_ARCHIVE)], members_path
    )
    defined = capture_command_log(
        [str(OPENSUBDIV_EMNM), "-C", "--defined-only", str(OPENSUBDIV_GPU_ARCHIVE)],
        defined_path,
    )
    undefined = capture_command_log(
        [str(OPENSUBDIV_EMNM), "--undefined-only", str(OPENSUBDIV_GPU_ARCHIVE)],
        undefined_path,
    )
    smoke = capture_command_log(
        [str(OPENSUBDIV_SOURCE_PATHS["recipe"]), "--test"], smoke_path, timeout=900
    )
    require_opensubdiv_binary_proof(members, defined, undefined, smoke)
    return {
        "version": OPENSUBDIV_VERSION,
        "tarball_md5": OPENSUBDIV_TARBALL_MD5,
        "sources": {key: ref(path) for key, path in OPENSUBDIV_SOURCE_PATHS.items()},
        "header": ref(OPENSUBDIV_HEADER),
        "cpu_archive": ref(OPENSUBDIV_CPU_ARCHIVE),
        "gpu_archive": ref(OPENSUBDIV_GPU_ARCHIVE),
        "tools": {"emar": ref(OPENSUBDIV_EMAR), "emnm": ref(OPENSUBDIV_EMNM)},
        "members": ref(members_path),
        "defined_symbols": ref(defined_path),
        "undefined_symbols": ref(undefined_path),
        "wasm_smoke": ref(smoke_path),
    }


def write_json(path: Path, value: Any) -> Path:
    if path.exists() or path.is_symlink():
        fail(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return path


def write_lines(path: Path, values: list[str]) -> Path:
    if path.exists() or path.is_symlink():
        fail(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        for value in values:
            if not value or value.strip() != value or "\n" in value:
                fail(f"noncanonical manifest value: {value!r}")
            stream.write(value + "\n")
    return path


def require_m3_cmake_cache(cache: Path, *, root: Path = ROOT) -> None:
    required = {
        "CMAKE_BUILD_TYPE": "Release",
        "CMAKE_GENERATOR": "Ninja",
        "CMAKE_HOME_DIRECTORY": os.fspath((root / "upstream").resolve()),
        "WITH_GTESTS": "ON",
        "WITH_GPU_BACKEND_TESTS": "ON",
        "WITH_GPU_DRAW_TESTS": "ON",
        "WITH_OPENSUBDIV": "ON",
        "WITH_WEBGPU_BACKEND": "ON",
    }
    values: dict[str, str] = {}
    for raw in cache.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith(("#", "//")) or "=" not in raw:
            continue
        typed, value = raw.split("=", 1)
        if ":" not in typed:
            continue
        key, _kind = typed.split(":", 1)
        if key in required:
            if key in values:
                fail(f"duplicate M3 CMake cache key {key}: {cache}")
            values[key] = value
    if values != required:
        fail(f"M3 CMake cache does not match the canonical native WebGPU test build: {cache}")


def require_m3_build_provenance(binary: Path, *, root: Path = ROOT) -> tuple[Path, Path]:
    build_root = root / "build-native-gpu"
    expected_binary = build_root / "bin/tests/blender_test"
    cache = build_root / "CMakeCache.txt"
    ninja = build_root / "build.ninja"
    if build_root.is_symlink() or not build_root.is_dir():
        fail(f"M3 canonical build root is missing, not a directory, or a symlink: {build_root}")
    if binary != expected_binary:
        fail(f"M3 binary is outside the canonical build-native-gpu root: {binary}")
    for path, label in ((binary, "binary"), (cache, "CMake cache"), (ninja, "Ninja graph")):
        if path.is_symlink() or not path.is_file():
            fail(f"M3 canonical {label} is missing, not regular, or a symlink: {path}")
    require_m3_cmake_cache(cache, root=root)
    lines = ninja.read_text(encoding="utf-8").splitlines()
    link_prefix = "build bin/tests/blender_test: "
    links = [line for line in lines if line.startswith(link_prefix)]
    aliases = [line for line in lines if line.startswith("build blender_test: ")]
    if (len(links) != 1 or "CXX_EXECUTABLE_LINKER" not in links[0]
            or aliases != ["build blender_test: phony bin/tests/blender_test"]):
        fail("M3 build.ninja lacks the unique canonical blender_test link and target alias")
    return cache, ninja


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
    if command != ["ninja", "-n", expected_target]:
        fail(f"M3 Ninja no-work command targets the wrong output: {command!r}")
    if cwd.resolve() != expected_build_root.resolve():
        fail(f"M3 Ninja no-work command uses the wrong build root: {cwd}")
    if isinstance(returncode, bool) or returncode != 0:
        fail(f"M3 Ninja no-work command failed with exit code {returncode}")
    if stdout != NINJA_NO_WORK_STDOUT or stderr != b"":
        fail(
            "M3 Ninja dry-run is stale or emitted noncanonical output: "
            f"stdout={stdout!r} stderr={stderr!r}"
        )


def attest_ninja_no_work(
    output: Path, *, root: Path = ROOT, stem: str = "ninja-no-work"
) -> dict[str, Any]:
    build_root = root / "build-native-gpu"
    command = ["ninja", "-n", M3_NINJA_TARGET]
    try:
        result = subprocess.run(
            command, cwd=build_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=120, check=False,
        )
    except subprocess.TimeoutExpired:
        fail("M3 Ninja no-work command timed out after 120s")
    stdout_path = output / f"{stem}.stdout"
    stderr_path = output / f"{stem}.stderr"
    for path, payload in ((stdout_path, result.stdout), (stderr_path, result.stderr)):
        if path.exists() or path.is_symlink():
            fail(f"refusing to overwrite M3 Ninja no-work evidence: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload)
    require_ninja_no_work_result(
        command, build_root, result.returncode, result.stdout, result.stderr,
        expected_build_root=build_root, expected_target=M3_NINJA_TARGET,
    )
    return {
        "command": command,
        "cwd": build_root.relative_to(root).as_posix(),
        "target": M3_NINJA_TARGET,
        "returncode": result.returncode,
        "stdout": ref(stdout_path),
        "stderr": ref(stderr_path),
    }


def capture(binary: Path, test: str, output: Path, *, env: dict[str, str] | None,
            timeout: int) -> int:
    if output.exists() or output.is_symlink():
        fail(f"refusing to overwrite raw test evidence: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        try:
            result = subprocess.run(
                [str(binary), f"--gtest_filter=GPUWebGPUTest.{test}"], cwd=ROOT, env=env,
                stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            fail(f"GPU test timed out after {timeout}s: {test}")
    return result.returncode


def capture_exact_gtest(binary: Path, name: str, output: Path, timeout: int) -> int:
    if output.exists() or output.is_symlink():
        fail(f"refusing to overwrite raw supplemental test evidence: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        try:
            result = subprocess.run(
                [str(binary), f"--gtest_filter={name}"],
                cwd=ROOT,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            fail(f"supplemental GPU test timed out after {timeout}s: {name}")
    return result.returncode


def parse_gpu_test_list(text: str) -> list[str]:
    names: list[str] = []
    saw_suite = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if raw[:1].isspace():
            if not saw_suite:
                fail("GPUWebGPUTest list contains an orphan test")
            names.append(line.strip())
        else:
            if line != "GPUWebGPUTest." or saw_suite:
                fail(f"GPUWebGPUTest list contains an unexpected suite/header: {line}")
            saw_suite = True
    if len(names) != GPU_TEST_COUNT or len(set(names)) != GPU_TEST_COUNT:
        fail(
            f"GPUWebGPUTest census is not {GPU_TEST_COUNT} unique names: {len(names)}"
        )
    return names


def list_tests(binary: Path, stdout_path: Path, stderr_path: Path) -> list[str]:
    result = subprocess.run(
        [str(binary), "--gtest_list_tests", "--gtest_filter=GPUWebGPUTest.*"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    for path, payload in ((stdout_path, result.stdout), (stderr_path, result.stderr)):
        if path.exists() or path.is_symlink():
            fail(f"refusing to overwrite GPU list evidence: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    if result.returncode != 0 or result.stderr != "":
        fail(
            "GPUWebGPUTest list command failed or wrote stderr: "
            f"rc={result.returncode} stderr={result.stderr!r}"
        )
    return parse_gpu_test_list(result.stdout)


def parse_draw_webgpu_test_list(text: str) -> list[str]:
    names: list[str] = []
    saw_suite = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if raw[:1].isspace():
            if not saw_suite:
                fail("DrawWebGPUTest list contains an orphan test")
            names.append(f"DrawWebGPUTest.{line.strip()}")
        else:
            if line != "DrawWebGPUTest." or saw_suite:
                fail(f"DrawWebGPUTest list contains an unexpected suite/header: {line}")
            saw_suite = True
    if tuple(names) != DRAW_WEBGPU_TESTS:
        fail(
            "supplemental DrawWebGPUTest list is not the exact two-test identity: "
            f"{names!r}"
        )
    return names


def list_draw_webgpu_tests(
    binary: Path, stdout_path: Path, stderr_path: Path
) -> list[str]:
    result = subprocess.run(
        [str(binary), "--gtest_list_tests", "--gtest_filter=DrawWebGPUTest.*"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    for path, payload in ((stdout_path, result.stdout), (stderr_path, result.stderr)):
        if path.exists() or path.is_symlink():
            fail(f"refusing to overwrite DrawWebGPUTest list evidence: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    if result.returncode != 0 or result.stderr != "":
        fail(
            "DrawWebGPUTest list command failed or wrote stderr: "
            f"rc={result.returncode} stderr={result.stderr!r}"
        )
    return parse_draw_webgpu_test_list(result.stdout)


def parse_draw_webgpu_test_run(path: Path, expected_name: str) -> None:
    if expected_name not in DRAW_WEBGPU_TESTS:
        fail(f"unexpected supplemental DrawWebGPUTest identity: {expected_name}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.count(UNCAPTURED_DEVICE_ERROR) != 0:
        fail(f"supplemental DrawWebGPUTest has an uncaptured device error: {expected_name}")
    if text.count(MEMORY_LEAK_ERROR) != 0:
        fail(f"supplemental DrawWebGPUTest reports leaked memory: {expected_name}")
    run_rows = re.findall(r"(?m)^\[ RUN      \] (.+)$", text)
    ok_rows = re.findall(r"(?m)^\[       OK \] (.+)$", text)
    ok_pattern = re.compile(
        rf"^{re.escape(expected_name)}(?: \((?:[0-9]+|<1) ms\))?$"
    )
    if run_rows != [expected_name] or len(ok_rows) != 1 or ok_pattern.fullmatch(ok_rows[0]) is None:
        fail(f"supplemental DrawWebGPUTest lacks one exact RUN/OK pair: {expected_name}")
    if "[  FAILED  ]" in text or "[  SKIPPED ]" in text:
        fail(f"supplemental DrawWebGPUTest contains a failed/skipped result: {expected_name}")


def parse_gpu_webgpu_test_run(path: Path, expected_name: str) -> None:
    if not expected_name.startswith("GPUWebGPUTest."):
        fail(f"unexpected primary GPUWebGPUTest identity: {expected_name}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.count(UNCAPTURED_DEVICE_ERROR) != 0:
        fail(f"GPUWebGPUTest has an uncaptured device error: {expected_name}")
    if text.count(MEMORY_LEAK_ERROR) != 0:
        fail(f"GPUWebGPUTest reports leaked memory: {expected_name}")
    run_rows = re.findall(r"(?m)^\[ RUN      \] (.+)$", text)
    ok_rows = re.findall(r"(?m)^\[       OK \] (.+)$", text)
    ok_pattern = re.compile(
        rf"^{re.escape(expected_name)}(?: \((?:[0-9]+|<1) ms\))?$"
    )
    if run_rows != [expected_name] or len(ok_rows) != 1 or ok_pattern.fullmatch(ok_rows[0]) is None:
        fail(f"GPUWebGPUTest lacks one exact RUN/OK pair: {expected_name}")
    if "[  FAILED  ]" in text or "[  SKIPPED ]" in text:
        fail(f"GPUWebGPUTest contains a failed/skipped row: {expected_name}")


def parse_static(path: Path, expected_cache: str) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    begin_rows = [index for index, line in enumerate(lines) if line == CENSUS_BEGIN]
    end_rows = [index for index, line in enumerate(lines) if line == CENSUS_END]
    if len(begin_rows) != 1 or len(end_rows) != 1 or begin_rows[0] >= end_rows[0]:
        fail(
            "static shader log lacks one ordered census boundary pair: "
            f"begin={begin_rows} end={end_rows}"
        )
    before = "\n".join(lines[:begin_rows[0]])
    after = "\n".join(lines[end_rows[0] + 1:])
    if (SHADER_ROW_RE.search(before) or SHADER_ROW_RE.search(after) or
            CACHE_ROW_RE.search(before) or CACHE_ROW_RE.search(after)):
        fail("static shader/cache row escaped the census boundaries")
    census = "\n".join(lines[begin_rows[0] + 1:end_rows[0]]) + "\n"
    # Device validation is asynchronous. An error attributed to a shader may
    # arrive before the first marker or after the END marker, so the entire raw
    # invocation must be clean even though result/cache rows stay boundary-scoped.
    device_errors = text.count(UNCAPTURED_DEVICE_ERROR)
    if device_errors != 0:
        fail(f"static shader log has {device_errors} uncaptured WebGPU device errors")
    memory_leaks = text.count(MEMORY_LEAK_ERROR)
    if memory_leaks != 0:
        fail(f"static shader log has {memory_leaks} leaked-memory reports")
    shader_rows = SHADER_ROW_RE.findall(census)
    cache_rows = CACHE_ROW_RE.findall(census)
    if (len(shader_rows) != STATIC_SHADER_COUNT or
            len({name for _, name in shader_rows}) != STATIC_SHADER_COUNT):
        fail(
            f"named static shader census is not exactly {STATIC_SHADER_COUNT} rows: "
            f"{len(shader_rows)}"
        )
    if any(status != "PASS" for status, _ in shader_rows):
        failures = [name for status, name in shader_rows if status != "PASS"]
        fail(f"static shader census has compile failures: {failures[:20]}")
    if (len(cache_rows) != STATIC_SHADER_COUNT or
            len({name for _, name in cache_rows}) != STATIC_SHADER_COUNT):
        fail(
            f"shader cache census is not exactly {STATIC_SHADER_COUNT} unique rows: "
            f"{len(cache_rows)}"
        )
    if any(status != expected_cache for status, _ in cache_rows):
        fail(f"shader cache expected all {expected_cache}")
    shader_names = [name for _, name in shader_rows]
    cache_names = [name for _, name in cache_rows]
    if set(shader_names) != set(cache_names):
        fail("shader compile/cache keysets differ")
    if REQUIRED_SHADER_ID not in shader_names or FORBIDDEN_SHADER_ID in shader_names:
        fail(
            "static shader census lacks the exact fullscreen_blit -> "
            "draw_debug_draw_compact substitution"
        )
    return shader_names, cache_names


def cache_manifest_rows(directory: Path, expected_count: int = STATIC_SHADER_COUNT) -> list[str]:
    if directory.is_symlink() or not directory.is_dir():
        fail(f"shader cache root is missing, not a directory, or a symlink: {directory}")
    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    if len(entries) != expected_count:
        fail(f"shader cache does not contain exactly {expected_count} entries: {len(entries)}")
    rows = []
    for path in entries:
        if path.is_symlink() or not path.is_file():
            fail(f"shader cache entry is not one regular non-symlink file: {path}")
        if CACHE_FILE_RE.fullmatch(path.name) is None:
            fail(f"shader cache entry has a noncanonical content-addressed name: {path.name}")
        rows.append(f"{path.name}\t{path.stat().st_size}\t{sha256(path)}")
    return rows


def require_cache_unchanged(cold_rows: list[str], warm_rows: list[str]) -> None:
    if warm_rows != cold_rows:
        fail("warm shader run changed the cold cache manifest")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--freeze-receipt", type=Path, required=True)
    parser.add_argument("--m0-receipt", type=Path, required=True)
    parser.add_argument("--binary", type=Path,
                        default=ROOT / "build-native-gpu/bin/tests/blender_test")
    parser.add_argument("--test-timeout", type=int, default=300)
    parser.add_argument("--shader-timeout", type=int, default=1800)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if LABEL_RE.fullmatch(args.run_label) is None:
            fail("unsafe run label")
        output = OUTPUT_ROOT / args.run_label / "m3"
        if output.exists() or output.is_symlink():
            fail(f"refusing to overwrite M3 attempt: {output}")
        output.mkdir(parents=True)
        incomplete = output / "INCOMPLETE"
        incomplete.write_text("M3 raw execution in progress\n", encoding="utf-8")
        binary_argument = args.binary if args.binary.is_absolute() else ROOT / args.binary
        if binary_argument.is_symlink():
            fail(f"GPU test binary argument is a symlink: {binary_argument}")
        binary = binary_argument.resolve(strict=True)
        if not os.access(binary, os.X_OK):
            fail(f"GPU test binary is not executable: {binary}")
        require_webgpu_device_limit_contract()
        require_cache_marker_activation_contract()
        cmake_cache, build_ninja = require_m3_build_provenance(binary)
        canonical_gpu_names = exact_name_manifest(
            GPU_TEST_CANONICAL_MANIFEST, GPU_TEST_COUNT, "canonical GPUWebGPUTest manifest"
        )
        if canonical_gpu_names != sorted(canonical_gpu_names):
            fail("canonical GPUWebGPUTest manifest is not sorted")
        canonical_shader_names = exact_name_manifest(
            STATIC_SHADER_CANONICAL_MANIFEST,
            STATIC_SHADER_COUNT,
            "canonical static-shader manifest",
        )
        if canonical_shader_names != sorted(canonical_shader_names):
            fail("canonical static-shader manifest is not sorted")
        critical_paths = critical_input_paths(binary, cmake_cache, build_ninja)
        critical_before_rows = critical_input_snapshot(critical_paths)
        critical_before = write_lines(
            output / "raw/critical-inputs-before.manifest", critical_before_rows
        )
        freeze = json.loads(args.freeze_receipt.read_text(encoding="utf-8"))
        if freeze.get("schema") != 1 or freeze.get("verdict") != "PASS":
            fail("source freeze is not schema-1 PASS")
        freeze_hash = sha256(args.freeze_receipt)
        m0_hash = sha256(args.m0_receipt)
        opensubdiv = capture_opensubdiv_proof(output / "raw")
        no_work = attest_ninja_no_work(output / "raw")
        gpu_list_stdout = output / "raw/gpu-list.stdout"
        gpu_list_stderr = output / "raw/gpu-list.stderr"
        names = list_tests(binary, gpu_list_stdout, gpu_list_stderr)
        if sorted(f"GPUWebGPUTest.{name}" for name in names) != canonical_gpu_names:
            fail("raw GPUWebGPUTest enumeration differs from the checked-in exact manifest")
        draw_list_stdout = output / "raw/draw-webgpu-list.stdout"
        draw_list_stderr = output / "raw/draw-webgpu-list.stderr"
        draw_names = list_draw_webgpu_tests(binary, draw_list_stdout, draw_list_stderr)
        rows: dict[str, Any] = {}
        cache_dir = output / "shader-cache"
        cache_dir.mkdir()
        cold_env = os.environ.copy()
        cold_env.pop("BW_SHADER_CACHE_DIR", None)
        cold_env["BW_SHADER_CACHE_CENSUS_DIR"] = str(cache_dir)
        static_cold = output / "raw/tests/static_shaders.log"
        for name in names:
            log = static_cold if name == "static_shaders" else output / "raw/tests" / f"{name}.log"
            rc = capture(binary, name, log, env=cold_env if name == "static_shaders" else None,
                         timeout=args.shader_timeout if name == "static_shaders" else args.test_timeout)
            if rc != 0:
                fail(f"GPU test is not PASS: {name} rc={rc}")
            full_name = f"GPUWebGPUTest.{name}"
            parse_gpu_webgpu_test_run(log, full_name)
            rows[full_name] = {"status": "PASS", "exit_code": 0, "raw_log": ref(log)}
        draw_rows: dict[str, Any] = {}
        for name in draw_names:
            log = output / "raw/tests" / f"{name}.log"
            rc = capture_exact_gtest(binary, name, log, args.test_timeout)
            if rc != 0:
                fail(f"supplemental GPU test is not PASS: {name} rc={rc}")
            parse_draw_webgpu_test_run(log, name)
            draw_rows[name] = {"status": "PASS", "exit_code": 0, "raw_log": ref(log)}
        gpu_manifest = write_lines(output / "raw/gpu-tests.txt", canonical_gpu_names)
        draw_manifest = write_lines(output / "raw/draw-webgpu-tests.txt", draw_names)
        shader_names, _ = parse_static(static_cold, "MISS")
        if set(shader_names) != set(canonical_shader_names):
            fail("cold static shader identities differ from the checked-in exact manifest")
        cold_cache_manifest = cache_manifest_rows(cache_dir)
        warm_log = output / "raw/static-shaders-warm.log"
        warm_rc = capture(binary, "static_shaders", warm_log, env=cold_env,
                          timeout=args.shader_timeout)
        if warm_rc != 0:
            fail(f"warm static shader run failed rc={warm_rc}")
        warm_names, _ = parse_static(warm_log, "HIT")
        if set(shader_names) != set(warm_names):
            fail("cold/warm shader identity sets differ")
        warm_cache_manifest = cache_manifest_rows(cache_dir)
        require_cache_unchanged(cold_cache_manifest, warm_cache_manifest)
        shader_manifest = write_lines(output / "raw/shaders.txt", canonical_shader_names)
        cache_manifest = write_lines(
            output / "raw/cache.manifest",
            cold_cache_manifest,
        )
        final_no_work = attest_ninja_no_work(
            output / "raw", stem="ninja-final-no-work"
        )
        critical_after_rows = critical_input_snapshot(critical_paths)
        if critical_after_rows != critical_before_rows:
            fail("critical M3 binary/build/OpenSubdiv inputs changed during execution")
        critical_after = write_lines(
            output / "raw/critical-inputs-after.manifest", critical_after_rows
        )
        stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        gpu_raw = write_json(output / "raw/gpu-result.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "source_freeze_sha256": freeze_hash, "binary_sha256": sha256(binary),
            "cmake_cache_sha256": sha256(cmake_cache),
            "build_ninja_sha256": sha256(build_ninja), "no_work": no_work,
            "final_no_work": final_no_work,
            "manifest_sha256": sha256(gpu_manifest),
            "canonical_manifest_sha256": sha256(GPU_TEST_CANONICAL_MANIFEST),
            "list_stdout_sha256": sha256(gpu_list_stdout),
            "list_stderr_sha256": sha256(gpu_list_stderr),
            "total": GPU_TEST_COUNT, "passed": GPU_TEST_COUNT,
            "failed": 0, "crashed": 0,
        })
        shader_raw = write_json(output / "raw/shader-result.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "source_freeze_sha256": freeze_hash, "binary_sha256": sha256(binary),
            "cmake_cache_sha256": sha256(cmake_cache),
            "build_ninja_sha256": sha256(build_ninja), "no_work": no_work,
            "final_no_work": final_no_work,
            "manifest_sha256": sha256(shader_manifest), "total": STATIC_SHADER_COUNT,
            "canonical_manifest_sha256": sha256(STATIC_SHADER_CANONICAL_MANIFEST),
            "passed": STATIC_SHADER_COUNT, "excluded": 0, "failed": 0,
        })
        draw_raw = write_json(output / "raw/draw-webgpu-result.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "source_freeze_sha256": freeze_hash, "binary_sha256": sha256(binary),
            "cmake_cache_sha256": sha256(cmake_cache),
            "build_ninja_sha256": sha256(build_ninja), "no_work": no_work,
            "final_no_work": final_no_work,
            "manifest_sha256": sha256(draw_manifest),
            "list_stdout_sha256": sha256(draw_list_stdout),
            "list_stderr_sha256": sha256(draw_list_stderr),
            "total": len(DRAW_WEBGPU_TESTS), "passed": len(DRAW_WEBGPU_TESTS),
            "failed": 0, "crashed": 0,
        })
        cold = write_json(output / "raw/cache-cold.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "mode": "cold", "cache_manifest_sha256": sha256(cache_manifest),
            "source_digest": freeze_hash, "toolchain_digest": m0_hash,
            "hits": 0, "misses": STATIC_SHADER_COUNT,
        })
        warm = write_json(output / "raw/cache-warm.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "mode": "warm", "cache_manifest_sha256": sha256(cache_manifest),
            "source_digest": freeze_hash, "toolchain_digest": m0_hash,
            "hits": STATIC_SHADER_COUNT, "misses": 0,
        })
        receipt = write_json(output / "receipt.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "created_utc": stamp, "source_freeze_sha256": freeze_hash,
            "binary": ref(binary), "cmake_cache": ref(cmake_cache),
            "build_ninja": ref(build_ninja), "no_work": no_work,
            "final_no_work": final_no_work,
            "critical_inputs": {
                "before": ref(critical_before), "after": ref(critical_after)
            },
            "device_limit_sources": {
                key: ref(path) for key, path in WEBGPU_DEVICE_LIMIT_PATHS.items()
            },
            "cache_marker_source": ref(CACHE_MARKER_SOURCE),
            "opensubdiv": opensubdiv,
            "toolchain_binding_sha256": m0_hash,
            "gpu_tests": {"canonical_manifest": ref(GPU_TEST_CANONICAL_MANIFEST),
                          "manifest": ref(gpu_manifest), "raw_result": ref(gpu_raw),
                          "list_stdout": ref(gpu_list_stdout),
                          "list_stderr": ref(gpu_list_stderr),
                          "total": GPU_TEST_COUNT, "passed": GPU_TEST_COUNT,
                          "failed": 0, "crashed": 0,
                          "rows": rows},
            "draw_webgpu_tests": {
                "manifest": ref(draw_manifest), "raw_result": ref(draw_raw),
                "list_stdout": ref(draw_list_stdout), "list_stderr": ref(draw_list_stderr),
                "total": len(DRAW_WEBGPU_TESTS), "passed": len(DRAW_WEBGPU_TESTS),
                "failed": 0, "crashed": 0, "rows": draw_rows,
            },
            "static_shaders": {
                               "canonical_manifest": ref(STATIC_SHADER_CANONICAL_MANIFEST),
                               "manifest": ref(shader_manifest), "raw_result": ref(shader_raw),
                               "cold_log": ref(static_cold), "warm_log": ref(warm_log),
                               "total": STATIC_SHADER_COUNT, "passed": STATIC_SHADER_COUNT,
                               "excluded": 0, "failed": 0,
                               "rows": {name: {"status": "PASS"}
                                        for name in canonical_shader_names}},
            "shader_cache": {"manifest": ref(cache_manifest), "cold_proof": ref(cold),
                             "warm_proof": ref(warm), "source_digest": freeze_hash,
                             "toolchain_digest": m0_hash, "entries": STATIC_SHADER_COUNT},
        })
        incomplete.unlink()
        print(f"FINAL_M3_RAW_PASS receipt={receipt.relative_to(ROOT)} sha256={sha256(receipt)}")
        return 0
    except (RunError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"FINAL_M3_RAW_FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
