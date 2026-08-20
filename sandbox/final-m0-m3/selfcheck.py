#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hermetic positive and adversarial fixtures for verify.py."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location("final_m0_m3_verify", HERE / "verify.py")
assert SPEC and SPEC.loader
verify_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_module)


def write(path: Path, payload: bytes | str, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    path.write_bytes(data)
    path.chmod(0o755 if executable else 0o644)
    return path


def write_json(path: Path, value: Any) -> Path:
    return write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", os.fspath(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def common(label: str, stamp: str, freeze_hash: str) -> dict[str, Any]:
    return {
        "schema": 1,
        "verdict": "PASS",
        "run_label": label,
        "created_utc": stamp,
        "source_freeze_sha256": freeze_hash,
    }


def build_fixture(root: Path, now: dt.datetime) -> Path:
    label = "fixture-final-m0-m3-r1"
    freeze_stamp = (now - dt.timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    run_stamp = (now - dt.timedelta(minutes=10)).isoformat().replace("+00:00", "Z")

    upstream = root / "upstream"
    upstream.mkdir(parents=True)
    (upstream / "tests/files").mkdir(parents=True)
    git(upstream, "init", "--quiet")
    git(upstream, "config", "user.name", "Fixture")
    git(upstream, "config", "user.email", "fixture@example.invalid")
    source_path = write(upstream / "source.txt", "pinned\n")
    locale_languages = write(
        upstream / "locale/languages",
        "".join(f"{number}:Language {number}:lang_{number}:100%\n" for number in range(51)),
    )
    base_script_source = write(
        upstream / "scripts/startup/fixture.py", "# fixture base script\n"
    )
    datafile_source = write(
        upstream / "release/datafiles/fixture.dat", b"fixture runtime datafile\n"
    )
    asset_source = write(
        upstream / "assets/fixture.blend", b"fixture bundled asset\n"
    )
    cpp_limit_assignments = "".join(
        f"required_limits.{field} = supported_limits.{field};\n"
        for field in verify_module.M3_WEBGPU_DEVICE_LIMIT_FIELDS
    )
    native_limit_source = write(
        root / verify_module.M3_WEBGPU_DEVICE_LIMIT_PATHS["native_context"],
        cpp_limit_assignments + "device_desc.requiredLimits = &required_limits;\n",
    )
    web_fallback_limit_source = write(
        root / verify_module.M3_WEBGPU_DEVICE_LIMIT_PATHS["web_fallback"],
        cpp_limit_assignments + "desc.requiredLimits = &required_limits;\n",
    )
    worker_limit_source = write(
        root / verify_module.M3_WEBGPU_DEVICE_LIMIT_PATHS["worker_preinit"],
        "var requiredLimits = {\n"
        + "".join(
            f"  {field}: adapter.limits.{field},\n"
            for field in verify_module.M3_WEBGPU_DEVICE_LIMIT_FIELDS
        )
        + "};\nadapter.requestDevice({requiredLimits: requiredLimits,});\n",
    )
    cache_marker_source = write(
        root / verify_module.M3_CACHE_MARKER_SOURCE,
        "bool emit_cache_result(const std::string &name) {\n"
        '  const char *census_dir = std::getenv("BW_SHADER_CACHE_CENSUS_DIR");\n'
        "  if (census_dir == nullptr) { return true; }\n"
        '  const char *active_dir = std::getenv("BW_SHADER_CACHE_DIR");\n'
        "  if (active_dir == nullptr || active_dir[0] == '\\0' || "
        "std::strcmp(active_dir, census_dir) != 0) { return false; }\n"
        "  return true;\n}\n"
        "void compile() { if (emit_cache_result(sources.name)) {} }\n",
    )
    opensubdiv_recipe = write(
        root / verify_module.M3_OPENSUBDIV_SOURCE_PATHS["recipe"],
        "#!/bin/sh\n"
        f'OSD_VERSION="{verify_module.M3_OPENSUBDIV_VERSION}"\n'
        f'OSD_MD5="{verify_module.M3_OPENSUBDIV_TARBALL_MD5}"\n'
        'if [ "$1" = "--test" ]; then\n'
        "  echo 'OSD_WASM_REFINE nverts_level1=26 glsl_bytes=4096 param=1 evaluate=1'\n"
        "fi\n",
        True,
    )
    opensubdiv_configure = write(
        root / verify_module.M3_OPENSUBDIV_SOURCE_PATHS["configure"],
        "set(OPENSUBDIV_LIBRARIES libosdCPU.a libosdGPU.a)\n",
    )
    opensubdiv_cmake = write(
        root / verify_module.M3_OPENSUBDIV_SOURCE_PATHS["upstream_cmake"],
        "if(WITH_WEBGPU_BACKEND)\n  add_definitions(-DWITH_WEBGPU_BACKEND)\nendif()\n",
    )
    opensubdiv_evaluator = write(
        root / verify_module.M3_OPENSUBDIV_SOURCE_PATHS["evaluator"],
        "#if defined(WITH_WEBGPU_BACKEND)\n"
        "case GPU_BACKEND_WEBGPU:\n"
        "GLSLPatchShaderSource::GetPatchBasisShaderSource();\n"
        "#endif\n",
    )
    opensubdiv_header = write(
        root / verify_module.M3_OPENSUBDIV_HEADER,
        "class GLSLPatchShaderSource {\n"
        "  static std::string GetPatchBasisShaderSource();\n"
        "};\n",
    )
    opensubdiv_cpu = write(root / verify_module.M3_OPENSUBDIV_CPU_ARCHIVE, b"cpu-archive")
    opensubdiv_gpu = write(root / verify_module.M3_OPENSUBDIV_GPU_ARCHIVE, b"gpu-archive")
    opensubdiv_tools = {
        "emar": write(
            root / verify_module.M3_OPENSUBDIV_TOOLS["emar"],
            "#!/bin/sh\nprintf 'version.cpp.o\\nglslPatchShaderSource.cpp.o\\n'\n",
            True,
        ),
        "emnm": write(
            root / verify_module.M3_OPENSUBDIV_TOOLS["emnm"],
            "#!/bin/sh\n"
            "case \" $* \" in\n"
            "  *' --defined-only '*) printf '00000ca1 T OpenSubdiv::v3_7_0::Osd::GLSLPatchShaderSource::GetPatchBasisShaderSource()\\n' ;;\n"
            "  *) printf 'glslPatchShaderSource.cpp.o:\\n U _Znwm\\n' ;;\n"
            "esac\n",
            True,
        ),
    }
    pass_delta_note = write(
        root / verify_module.M2_PASS_DELTA_NOTE_PATH,
        b"\n".join(verify_module.M2_PASS_DELTA_NOTE_REQUIRED) + b"\n",
    )
    cycles_source_names = (
        "__init__.py", "camera.py", "engine.py", "maketx.py", "operators.py",
        "osl.py", "presets.py", "properties.py", "ui.py", "version_update.py",
    )
    cycles_sources = {
        name: write(
            upstream / "intern/cycles/blender/addon" / name,
            f"# fixture Cycles source {name}\n",
        )
        for name in cycles_source_names
    }
    git(upstream, "add", ".")
    git(upstream, "commit", "--quiet", "-m", "fixture pin")
    fixture_pin = git(upstream, "rev-parse", "HEAD")
    verify_module.BLENDER_COMMIT = fixture_pin
    write(source_path, "web port\n")

    # Root-level M0 artifacts.
    oracle_pin = write(root / "oracle/PIN", f"{fixture_pin[:12]} blender-v5.2-release\n")
    write(
        root / "oracle/TOOLCHAIN",
        f"emsdk {verify_module.EMSDK_VERSION}\n"
        f"release {verify_module.EMSDK_RELEASE_COMMIT}\n"
        f"compiler {verify_module.EMCC_COMMIT}\n",
    )
    write(root / "containers/oracle/Dockerfile", "FROM scratch\n")
    write(root / "scripts/oracle-container.sh", "#!/bin/sh\nexit 0\n", True)
    native_oracle = write(root / "oracle/bpy.sh", "#!/bin/sh\nexit 0\n", True)
    node = write(
        root / "tools/emsdk/node/22.16.0_64bit/bin/node",
        "#!/bin/sh\necho v22.16.0\n", True,
    )
    write(root / "scripts/m0-oracle-receipt.py", "print('PASS')\n", True)
    write(root / "scripts/m0-selfcheck.py", "print('PASS')\n")
    write(
        root / "scripts/ninja-locked.sh",
        (REPOSITORY_ROOT / "scripts/ninja-locked.sh").read_bytes(),
        True,
    )
    write(root / "harness/buildwrap.sh", "#!/bin/sh\nexec \"$@\"\n", True)
    write(
        root / "patches/blender_web.cmake",
        "set(WITH_PYTHON ON)\n"
        "set(OPENSUBDIV_LIBRARIES libosdCPU.a libosdGPU.a)\n",
    )
    write(root / "reuse.toml", "version = 1\n")
    fixture_license = write(root / "LICENSES/BSD-3-Clause.txt", "fixture BSD-3-Clause text\n")
    write(
        root / ".github/workflows/m0.yml",
        "EM_CACHE CCACHE_DIR reuse-action actions/cache "
        f"{verify_module.EMSDK_VERSION} {verify_module.EMSDK_REPO_COMMIT}\n",
    )
    deferrals = []
    for item in sorted(
        set().union(*verify_module.M2_DEFERRALS.values())
        | verify_module.M3_COMPILER_DEFERRALS
        | set(verify_module.M2_PASS_DELTA_LEDGER)
    ):
        if item in verify_module.M2_PASS_DELTA_LEDGER:
            deferrals.append({"id": item, **verify_module.M2_PASS_DELTA_LEDGER[item]})
            continue
        status = (
            verify_module.M2_DETECTOR_ACTIVE_STATUS
            if item == verify_module.M2_DETECTOR_ACTIVE_ID else "deferred"
        )
        deferrals.append({
            "id": item, "status": status, "milestone": "M2/M3",
            "evidence": f"fixture evidence for {item}",
        })
    write_json(root / "ledger/deferred.json", {"deferred": deferrals})
    built: dict[str, Any] = {}
    for name in sorted(verify_module.REQUIRED_DEPS):
        built[name] = {
            "version": "1.0",
            "license": "BSD-3-Clause",
            "gpl_compatible": True,
            "rationale": f"fixture {name}",
            "source": f"fixture source {name}",
            "notes": f"fixture {name}",
        }
    built["opensubdiv"] = {
        "version": verify_module.M3_OPENSUBDIV_VERSION,
        "license": "Apache-2.0",
        "gpl_compatible": True,
        "rationale": "fixture opensubdiv",
        "source": "fixture OpenSubdiv source",
        "notes": "fixture opensubdiv",
    }
    write_json(root / "ledger/deps.json", {"wasm_built": built})
    write(root / "sandbox/tierb-prep/suites.tsv", "\n".join(verify_module.M2_KEYS) + "\n")
    normalize_sed = write(
        root / "sandbox/tierb-prep/normalize.sed",
        (HERE.parent / "tierb-prep/normalize.sed").read_bytes(),
    )
    wasm_denoise = write(
        root / "sandbox/tierb-prep/wasm-denoise.pl",
        (HERE.parent / "tierb-prep/wasm-denoise.pl").read_bytes(),
    )
    m2_producer_source = write(
        root / "sandbox/final-m0-m3/run_m2.py", "# fixture-bound M2 producer\n"
    )

    # Canonical freeze files and receipt.
    freeze_dir = root / "evidence/freeze"
    patch = write(freeze_dir / "canonical-source.patch", git(upstream, "diff", "--binary") + "\n")
    manifest_rows = []
    for relative in git(upstream, "ls-files").splitlines():
        payload = (upstream / relative).read_bytes()
        manifest_rows.append({
            "mode": "100644",
            "path": relative,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        })
    manifest_bytes = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        for row in manifest_rows
    )
    live = write(freeze_dir / "live.manifest.jsonl", manifest_bytes)
    replay = write(freeze_dir / "replay.manifest.jsonl", manifest_bytes)
    freeze_receipt_value = {
        "schema": 1,
        "verdict": "PASS",
        "created_utc": freeze_stamp,
        "source": os.fspath(upstream.resolve()),
        "expected_pin": fixture_pin,
        "recorded_pin_file": {"path": os.fspath(oracle_pin.resolve()), "sha256": digest(oracle_pin)},
        "git_version": git(root, "--version") if (root / ".git").exists() else subprocess.run(["git", "--version"], check=True, capture_output=True, text=True).stdout.strip(),
        "patch": {"path": patch.name, "bytes": patch.stat().st_size, "sha256": digest(patch)},
        "live_manifest": {"path": live.name, "entries": len(manifest_rows), "bytes": live.stat().st_size, "sha256": digest(live)},
        "replay_manifest": {"path": replay.name, "entries": len(manifest_rows), "bytes": replay.stat().st_size, "sha256": digest(replay)},
        "ignored_worktree_paths": {"policy": "excluded by the repository's standard Git ignore rules", "count": 0, "nul_list_sha256": hashlib.sha256(b"").hexdigest()},
        "checks": {
            "source_head_exact_pin": True,
            "source_real_index_pristine": True,
            "source_repository_operation_idle": True,
            "initialized_submodules_clean": True,
            "replay_started_pristine": True,
            "patch_regenerated_byte_exact": True,
            "manifest_replay_byte_exact": True,
            "live_resnapshot_byte_exact": True,
            "pin_and_ignore_inputs_stable": True,
            "outputs_created_without_overwrite": True,
        },
    }
    freeze_receipt = write_json(freeze_dir / "receipt.json", freeze_receipt_value)
    freeze_hash = digest(freeze_receipt)

    receipt_dir = root / "evidence/receipts"
    artifact_dir = root / "evidence/artifacts"
    raw_dir = root / "evidence/raw"

    container_digest = "sha256:" + "a" * 64
    container_proof = write_json(raw_dir / "m0-container.json", {
        "schema": 1, "verdict": "PASS", "run_label": label,
        "image_digest": container_digest, "blender_version": "5.2.0",
        "blender_commit": fixture_pin, "oiiotool_version": "2.4.17.0", "exit_code": 0,
    })
    reuse_proof = write_json(raw_dir / "reuse.json", {
        "schema": 1, "verdict": "PASS", "run_label": label,
        "source_freeze_sha256": freeze_hash,
        "reuse_config_sha256": digest(root / "reuse.toml"),
        "exit_code": 0, "violations": 0,
    })
    m0_artifacts = {key: ref(root, root / value) for key, value in verify_module.M0_ARTIFACTS.items()}
    m0_value = common(label, run_stamp, freeze_hash) | {
        "pins": {
            "blender": {"branch": verify_module.BLENDER_BRANCH, "commit": fixture_pin},
            "emsdk": {"version": verify_module.EMSDK_VERSION, "release_commit": verify_module.EMSDK_RELEASE_COMMIT, "repo_commit": verify_module.EMSDK_REPO_COMMIT, "compiler_commit": verify_module.EMCC_COMMIT},
            "oracle": {"version": "5.2.0", "commit": fixture_pin},
        },
        "artifacts": m0_artifacts,
        "container": {"image_digest": container_digest, "proof": ref(root, container_proof)},
        "ci": {"em_cache": True, "ccache": True, "reuse_lint": True, "pinned_actions": True, "static_selfcheck": True, "runtime_check": True},
        "reuse": {"proof": ref(root, reuse_proof), "exit_code": 0, "violations": 0},
    }
    m0 = write_json(receipt_dir / "m0.json", m0_value)

    # M1 all-pass gtests and exact corpus parity.
    native_build = root / "build-native-m1-parity"
    wasm_build = root / "build-wasm-m1-parity"
    native_cache = write(
        native_build / "CMakeCache.txt",
        f"CMAKE_BUILD_TYPE:STRING=Release\nCMAKE_GENERATOR:INTERNAL=Ninja\n"
        f"CMAKE_HOME_DIRECTORY:INTERNAL={root / 'upstream'}\nWITH_GMP:BOOL=OFF\n"
        "WITH_TESTS_SINGLE_BINARY:BOOL=ON\nWITH_TESTS_BMESH_CORE_PARITY:BOOL=ON\n",
    )
    wasm_cache = write(
        wasm_build / "CMakeCache.txt",
        f"CMAKE_BUILD_TYPE:STRING=Release\nCMAKE_GENERATOR:INTERNAL=Ninja\n"
        f"CMAKE_HOME_DIRECTORY:INTERNAL={root / 'upstream'}\n"
        f"CMAKE_TOOLCHAIN_FILE:FILEPATH={root / 'tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake'}\n"
        "WITH_OPENIMAGEDENOISE:BOOL=OFF\n"
        "WITH_GMP:BOOL=OFF\nWITH_TESTS_SINGLE_BINARY:BOOL=ON\n"
        "WITH_TESTS_BMESH_CORE_PARITY:BOOL=ON\n",
    )
    for build in (native_build, wasm_build):
        write(
            build / "source/blender/blenlib/CMakeFiles/BLI_test.dir/tests/BLI_any_test.cc.o",
            "BLI object\n",
        )
        write(
            build / "source/blender/bmesh/CMakeFiles/bmesh_core_test.dir/tests/bmesh_core_test.cc.o",
            "bmesh object\n",
        )
    native_ninja = write(native_build / "build.ninja", "\n".join([
        "rule CXX_EXECUTABLE_LINKER",
        "  command = true",
        "build bin/tests/BLI_test: CXX_EXECUTABLE_LINKER source/blender/blenlib/CMakeFiles/BLI_test.dir/tests/BLI_any_test.cc.o",
        "  LINK_FLAGS = -pthread",
        "build bin/tests/bmesh_core_test: CXX_EXECUTABLE_LINKER source/blender/bmesh/CMakeFiles/bmesh_core_test.dir/tests/bmesh_core_test.cc.o",
        "  LINK_FLAGS = -pthread",
    ]) + "\n")
    wasm_ninja = write(wasm_build / "build.ninja", "\n".join([
        "rule CXX_EXECUTABLE_LINKER",
        "  command = true",
        "build bin/tests/BLI_test.js: CXX_EXECUTABLE_LINKER source/blender/blenlib/CMakeFiles/BLI_test.dir/tests/BLI_any_test.cc.o",
        "  LINK_FLAGS = -pthread -sMALLOC=mimalloc",
        "build bin/tests/bmesh_core_test.js: CXX_EXECUTABLE_LINKER source/blender/bmesh/CMakeFiles/bmesh_core_test.dir/tests/bmesh_core_test.cc.o",
        "  LINK_FLAGS = -pthread -sMALLOC=mimalloc -sMALLOC=dlmalloc -sINITIAL_MEMORY=33554432",
        "build bin/blender.js: CXX_EXECUTABLE_LINKER source/blender/blenlib/CMakeFiles/BLI_test.dir/tests/BLI_any_test.cc.o",
        "  LINK_FLAGS = -pthread -sMALLOC=mimalloc",
        "build blender: phony bin/blender.js",
    ]) + "\n")
    blender_js = write(wasm_build / "bin/blender.js", "javascript\n")
    blender_wasm = write(wasm_build / "bin/blender.wasm", b"\x00asmfixture")
    def gtest(name: str, total: int) -> dict[str, Any]:
        stem = "BLI_test" if name == "blenlib" else "bmesh_core_test"
        native = write(native_build / f"bin/tests/{stem}", f"{name} native\n")
        js = write(wasm_build / f"bin/tests/{stem}.js", f"{name} js\n")
        wasm = write(wasm_build / f"bin/tests/{stem}.wasm", b"\x00asm" + name.encode())
        names = (["BMeshCoreTest.BMVertCreate"] if name == "bmesh_core" else
                 [f"{name}.test_{index:04d}" for index in range(total)])
        native_manifest = write(raw_dir / f"{name}-native-tests.txt", "\n".join(names) + "\n")
        wasm_manifest = write(raw_dir / f"{name}-wasm-tests.txt", native_manifest.read_bytes())
        keyhash = digest(native_manifest)
        extra = (["--test-assets-dir", str((root / "upstream/tests/files").resolve())]
                 if name == "blenlib" else [])
        test_arguments = {
            key: list(extra)
            for key in ("native_list", "wasm_list", "native_run", "wasm_run")
        }
        no_work: dict[str, Any] = {}
        for platform, build, target in (
            ("native", native_build, f"bin/tests/{stem}"),
            ("wasm", wasm_build, f"bin/tests/{stem}.js"),
        ):
            no_work_stdout = write(
                raw_dir / f"{name}-{platform}-ninja-no-work.stdout",
                "ninja: no work to do.\n",
            )
            no_work_stderr = write(
                raw_dir / f"{name}-{platform}-ninja-no-work.stderr", b""
            )
            no_work[platform] = {
                "command": verify_module.ninja_locked_command("-n", target),
                "cwd": build.relative_to(root).as_posix(),
                "target": target,
                "returncode": 0,
                "stdout": ref(root, no_work_stdout),
                "stderr": ref(root, no_work_stderr),
            }
        raw = write_json(raw_dir / f"{name}.json", {
            "schema": 1, "verdict": "PASS", "run_label": label,
            "source_freeze_sha256": freeze_hash, "suite": name,
            "total": total, "passed": total, "failed": 0, "crashed": 0,
            "test_names_sha256": keyhash, "native_executable_sha256": digest(native),
            "javascript_sha256": digest(js), "wasm_sha256": digest(wasm),
            "native_cmake_cache_sha256": digest(native_cache),
            "wasm_cmake_cache_sha256": digest(wasm_cache),
            "native_build_ninja_sha256": digest(native_ninja),
            "wasm_build_ninja_sha256": digest(wasm_ninja),
            "no_work": no_work,
            "test_arguments": test_arguments,
        })
        return {
            "native_executable": ref(root, native), "javascript": ref(root, js),
            "wasm": ref(root, wasm),
            "native_cmake_cache": ref(root, native_cache),
            "wasm_cmake_cache": ref(root, wasm_cache),
            "native_build_ninja": ref(root, native_ninja),
            "wasm_build_ninja": ref(root, wasm_ninja),
            "no_work": no_work,
            "test_arguments": test_arguments,
            "configuration": {
                "native": {"build_type": "Release", "generator": "Ninja", "source_root": "upstream", "toolchain": "native", "with_gmp": False, "with_tests_single_binary": True, "with_tests_bmesh_core_parity": True},
                "wasm": {"build_type": "Release", "generator": "Ninja", "source_root": "upstream", "toolchain": "emscripten", "with_gmp": False, "with_tests_single_binary": True, "with_tests_bmesh_core_parity": True},
            },
            "raw_result": ref(root, raw),
            "native_manifest": ref(root, native_manifest),
            "wasm_manifest": ref(root, wasm_manifest),
            "total": total,
            "passed": total,
            "failed": 0,
            "crashed": 0,
            "native_keyset_sha256": keyhash,
            "wasm_keyset_sha256": keyhash,
        }

    main_rows: dict[str, Any] = {}
    for name in sorted(verify_module.MAIN_CORPUS):
        blend = write(artifact_dir / "corpus" / f"{name}.blend", f"blend {name}\n")
        native = write(raw_dir / "main-native" / f"{name}.json", f'{{"name":"{name}"}}\n')
        wasm = write(raw_dir / "main-wasm" / f"{name}.json", native.read_bytes())
        state = digest(native)
        main_rows[name] = {"blend": ref(root, blend), "native_dump": ref(root, native), "wasm_dump": ref(root, wasm), "native_state_sha256": state, "wasm_state_sha256": state, "equal": True}
    main_manifest = write_json(raw_dir / "main-manifest.json", {"names": sorted(verify_module.MAIN_CORPUS)})
    version_rows: dict[str, Any] = {}
    for name in sorted(verify_module.VERSIONING_PASS | verify_module.VERSIONING_REFUSE):
        blend = write(artifact_dir / "versioning" / f"{name}.blend", f"blend {name}\n")
        outcome = "PASS" if name in verify_module.VERSIONING_PASS else "ORACLE_REFUSE"
        native_result = write(raw_dir / "versioning-native" / f"{name}.txt", f"{outcome} {name}\n")
        wasm_result = write(raw_dir / "versioning-wasm" / f"{name}.txt", native_result.read_bytes())
        state = digest(native_result)
        version_rows[name] = {"blend": ref(root, blend), "native_result": ref(root, native_result), "wasm_result": ref(root, wasm_result), "native_outcome": outcome, "wasm_outcome": outcome, "native_state_sha256": state, "wasm_state_sha256": state, "equal": True}
    version_manifest = write_json(raw_dir / "versioning-manifest.json", {"names": sorted(version_rows)})
    runtime_no_work_stdout = write(
        raw_dir / "runtime-blender-ninja-no-work.stdout",
        verify_module.NINJA_NO_WORK_STDOUT,
    )
    runtime_no_work_stderr = write(
        raw_dir / "runtime-blender-ninja-no-work.stderr", b""
    )
    runtime_no_work = {
        "command": verify_module.ninja_locked_command("-n", "blender"),
        "cwd": "build-wasm-m1-parity", "target": "blender", "returncode": 0,
        "stdout": ref(root, runtime_no_work_stdout),
        "stderr": ref(root, runtime_no_work_stderr),
    }
    runtime_raw = write_json(raw_dir / "runtime-provenance.json", {
        "schema": 1, "verdict": "PASS", "run_label": label,
        "created_utc": run_stamp, "source_freeze_sha256": freeze_hash,
        "native_oracle_sha256": digest(native_oracle), "node_sha256": digest(node),
        "node_version": "v22.16.0", "javascript_sha256": digest(blender_js),
        "wasm_sha256": digest(blender_wasm), "cmake_cache_sha256": digest(wasm_cache),
        "build_ninja_sha256": digest(wasm_ninja), "no_work": runtime_no_work,
    })
    m1_value = common(label, run_stamp, freeze_hash) | {
        "runtime": {
            "native_oracle": ref(root, native_oracle), "node": ref(root, node),
            "javascript": ref(root, blender_js), "wasm": ref(root, blender_wasm),
            "cmake_cache": ref(root, wasm_cache), "build_ninja": ref(root, wasm_ninja),
            "node_version": "v22.16.0", "worker_boot": True,
            "no_work": runtime_no_work, "raw_provenance": ref(root, runtime_raw),
        },
        "gtests": {"blenlib": gtest("blenlib", 1667), "bmesh_core": gtest("bmesh_core", 1)},
        "main_corpus": {"manifest": ref(root, main_manifest), "total": 9, "equal": 9, "rows": main_rows},
        "versioning": {"manifest": ref(root, version_manifest), "total": 12, "pass": 10, "oracle_refuse": 2, "equal": 12, "rows": version_rows},
    }
    # Seed Ninja's command-hash log with harmless fixture rules. The executable
    # bytes already exist and the rule deliberately does not rewrite them.
    for build, targets in (
        (native_build, ("bin/tests/BLI_test", "bin/tests/bmesh_core_test")),
        (wasm_build, ("bin/tests/BLI_test.js", "bin/tests/bmesh_core_test.js", "blender")),
    ):
        subprocess.run(
            verify_module.ninja_locked_command(*targets), cwd=build, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    m1 = write_json(receipt_dir / "m1.json", m1_value)

    # M2 fixture covers exact parity, nonzero deferrals, structured
    # canonicalizers, and all three explicit PASS_WITH_DEFERRAL rows.
    py_manifest = write(raw_dir / "python-stdlib.manifest", "python3.13/os.py\n")
    normalization = write_json(raw_dir / "normalization-policy.json", {
        "schema": 1,
        "pipeline": {
            "native": [ref(root, m2_producer_source), ref(root, normalize_sed)],
            "wasm": [
                ref(root, m2_producer_source), ref(root, normalize_sed),
                ref(root, wasm_denoise),
            ],
        },
        "platform_envelope": {
            "native": "one exact adjacent optional-dot-prefix allocator + pinned native banner",
            "wasm": "one exact adjacent optional-dot-prefix allocator + pinned Wasm banner",
            "wasm_optional": [
                "exact immediately-following locale startup warning",
            ],
        },
        "suite_envelope": {
            verify_module.M2_NO_DENOISER_SUITE: {
                "wasm": {
                    "exact_count": 1,
                    "exact_normalized_line": (
                        verify_module.M2_NO_DENOISER_NORMALIZED_LINE.decode().rstrip("\n")
                    ),
                },
                "native_optional": {
                    "max_count": 1,
                    "exact_normalized_line": (
                        verify_module.M2_NATIVE_CUEW_NORMALIZED_LINE.decode().rstrip("\n")
                    ),
                },
                "required_cache_flag": "WITH_OPENIMAGEDENOISE:BOOL=OFF",
            },
        },
        "scratch_root": {
            "suites": dict(sorted(verify_module.M2_SCRATCH_ROOT_POLICIES.items())),
            "platforms": ["native", "wasm"],
            "replacement": verify_module.M2_SCRATCH_ROOT_TOKEN.decode(),
        },
        "repository_root": {
            "accepted": ["producer host root", "/work container root"],
            "replacement": verify_module.M2_REPOSITORY_ROOT_TOKEN.decode(),
            "mixed_roots": "reject",
        },
        "exit_code_primary": True,
        "normalized_bytes_exact_for_pass": True,
        "exact_replay_by_verifier": True,
    })

    def physics_fixture_body(name: str) -> bytes:
        blend_file, tests = verify_module.M2_PHYSICS_ORDER[name]
        lines = [
            f'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/physics/{blend_file}"\n'.encode(),
            b"\n",
        ]
        for test_name, frames in tests:
            lines.append(f"START {test_name} test.\n".encode())
            lines.extend(
                f"bake: frame {frame} :: {frames}\n".encode()
                for frame in range(1, frames + 1)
            )
            lines.extend([
                f"PASSED {test_name} test successfully.\n".encode(),
                b"Results:\n", b"Mesh Comparison : Same\n",
                b"Mesh Validation : Valid\n", b"\n", b"\n",
            ])
        lines.append(b"Blender quit\n")
        return b"".join(lines)

    keymap_first = [f"\tFixture Keymap {number:03d}\n".encode() for number in range(159)]
    keymap_second = [
        f"    ('Fixture {number:03d}', 'EMPTY', 'WINDOW', []),\n".encode()
        for number in range(28)
    ]
    keymap_native_body = b"".join([
        verify_module.M2_KEYMAP_FIRST_HEADER, *reversed(keymap_first),
        verify_module.M2_KEYMAP_SECOND_HEADER, *reversed(keymap_second),
        *verify_module.M2_KEYMAP_TAIL,
    ])
    keymap_wasm_body = b"".join([
        verify_module.M2_KEYMAP_FIRST_HEADER, *keymap_first,
        verify_module.M2_KEYMAP_SECOND_HEADER, *keymap_second,
        *verify_module.M2_KEYMAP_TAIL,
    ])

    rna_native_body = b"rna-prefix\n" + b"".join(
        verify_module.m2_rna_menu_lines(verify_module.M2_RNA_NATIVE_MENUS[1])
    ) + b"rna-suffix\n"
    rna_wasm_body = b"rna-prefix\n" + b"".join(
        verify_module.m2_rna_menu_lines(verify_module.M2_RNA_WASM_MENU)
    ) + b"rna-suffix\n"

    animation_info = verify_module.M2_ANIMATION_INFO_LIBRARY
    animation_missing = verify_module.M2_ANIMATION_MISSING_DATA
    animation_native_group = (
        b"ERROR: one of the ID's for the groups to assign to is invalid "
        b"(ptr=0xADDR, val=0x0)\n"
    )
    animation_wasm_group = animation_native_group.replace(b"val=0x0", b"val=0")
    animation_summary = b"----------------------------------------------------------------------\nRan 32 tests in <T>s\n\nOK\n"
    animation_slot_context = (
        b"." + verify_module.M2_ANIMATION_SLOT_XX_WARNING
        + verify_module.M2_ANIMATION_REPORT_CONTINUATION
        + verify_module.M2_ANIMATION_SLOT_OB_WARNING
        + verify_module.M2_ANIMATION_REPORT_CONTINUATION
    )
    animation_native_body = b"animation-prefix\n" + (
        b".." + verify_module.M2_ANIMATION_SLOT_UNASSIGNED_ERROR
        + animation_slot_context
        + b"." * 22 + verify_module.M2_ANIMATION_REMAP_READ
        + verify_module.M2_ANIMATION_SECOND_REMAP_READ + verify_module.M2_ANIMATION_SAVED
        + verify_module.M2_ANIMATION_TEMP_READ + b"." + animation_info
        + verify_module.M2_ANIMATION_LAYERED_READ_BARE + animation_summary
        + verify_module.M2_ANIMATION_ASSIGNMENT_WARNING
        + animation_native_group.replace(b"val=0x0", b"val=(nil)")
        + verify_module.M2_ANIMATION_FCURVE_ERROR
    )
    animation_wasm_body = b"animation-prefix\n" + (
        b"." + verify_module.M2_ANIMATION_SLOT_UNASSIGNED_ERROR
        + animation_slot_context
        + b"." * 4 + verify_module.M2_ANIMATION_ASSIGNMENT_WARNING
        + b"." * 6 + animation_wasm_group
        + verify_module.M2_ANIMATION_FCURVE_ERROR
        + b"." * 13 + verify_module.M2_ANIMATION_REMAP_READ
        + verify_module.M2_ANIMATION_SECOND_REMAP_READ + verify_module.M2_ANIMATION_SAVED
        + verify_module.M2_ANIMATION_TEMP_READ
        + verify_module.M2_ANIMATION_OBJECTDATA_WARNING + animation_info
        + animation_missing + verify_module.M2_ANIMATION_LAYERED_READ
        + animation_summary
    )
    library_prefix = b"".join(
        f"library-prefix-{number:02d}\n".encode()
        for number in range(verify_module.M2_LIBRARY_OVERRIDE_PHASE_BEFORE_INDEX)
    )
    library_native_body = (
        library_prefix + verify_module.M2_LIBRARY_OVERRIDE_PHASE_BEFORE
        + b"".join(verify_module.M2_LIBRARY_OVERRIDE_NATIVE_PHASE)
        + verify_module.M2_LIBRARY_OVERRIDE_PHASE_AFTER
        + b"library-shared-following\n"
        + b"".join(
            f"library-shared-set-{number:02d} ".encode()
            + verify_module.M2_LIBRARY_OVERRIDE_SET_CANONICAL + b"\n"
            for number in range(
                verify_module.M2_LIBRARY_OVERRIDE_SET_OCCURRENCES
                - len(verify_module.M2_LIBRARY_OVERRIDE_NATIVE_PHASE)
            )
        )
        + b"library-suffix\n"
    ).replace(
        verify_module.M2_LIBRARY_OVERRIDE_SET_CANONICAL,
        verify_module.M2_LIBRARY_OVERRIDE_SET_REVERSED,
    )
    library_wasm_body = (
        library_prefix + verify_module.M2_LIBRARY_OVERRIDE_PHASE_BEFORE
        + b"".join(verify_module.M2_LIBRARY_OVERRIDE_WASM_PHASE)
        + verify_module.M2_LIBRARY_OVERRIDE_PHASE_AFTER
        + b"library-shared-following\n"
        + b"".join(
            f"library-shared-set-{number:02d} ".encode()
            + verify_module.M2_LIBRARY_OVERRIDE_SET_CANONICAL + b"\n"
            for number in range(
                verify_module.M2_LIBRARY_OVERRIDE_SET_OCCURRENCES
                - len(verify_module.M2_LIBRARY_OVERRIDE_WASM_PHASE)
            )
        )
        + b"library-suffix\n"
    )

    m2_rows: dict[str, Any] = {}
    for name in verify_module.M2_KEYS:
        native_body = wasm_body = f"normalized {name}\n".encode()
        if name == verify_module.M2_KEYMAP_ORDER_SUITE:
            native_body, wasm_body = keymap_native_body, keymap_wasm_body
        elif name in verify_module.M2_PHYSICS_ORDER:
            canonical = physics_fixture_body(name)
            native_body = b"".join(reversed(canonical.splitlines(keepends=True)))
            wasm_body = canonical
        elif name == verify_module.M2_TEMPDIR_SUITE:
            native_body = (
                verify_module.M2_TEMPDIR_PROGRESS_FIXTURES[0]
                + verify_module.M2_TEMPDIR_RESULT_TAIL
            )
            wasm_body = (
                verify_module.M2_TEMPDIR_PROGRESS_FIXTURES[1]
                + verify_module.M2_TEMPDIR_RESULT_TAIL
            )
        elif name == verify_module.M2_PROP_ARRAY_SUITE:
            diagnostics = b"".join(verify_module.M2_PROP_ARRAY_DIAGNOSTICS)
            native_body = (
                b"." * 30 + diagnostics + b"." * 12 + b"\n"
                + verify_module.M2_PROP_ARRAY_RESULT_TAIL
            )
            wasm_body = (
                b"." * 29 + diagnostics + b"." * 13 + b"\n"
                + verify_module.M2_PROP_ARRAY_RESULT_TAIL
            )
        elif name == verify_module.M2_TEXT_SUITE:
            native_body = b"....\n.\n" + verify_module.M2_TEXT_RESULT_TAIL
            wasm_body = b".....\n" + verify_module.M2_TEXT_RESULT_TAIL
        elif name == verify_module.M2_SEQUENCER_STRIP_NAMING_SUITE:
            native_body = (
                b".....\n.\n" + verify_module.M2_SEQUENCER_STRIP_NAMING_RESULT_TAIL
            )
            wasm_body = (
                b"......\n" + verify_module.M2_SEQUENCER_STRIP_NAMING_RESULT_TAIL
            )
        elif name == verify_module.M2_ANIMATION_ARMATURE_SUITE:
            native_body = verify_module.M2_ANIMATION_ARMATURE_CANONICAL
            wasm_body = (
                verify_module.M2_ANIMATION_ARMATURE_HOMEFILE + b"."
                + verify_module.M2_ANIMATION_ARMATURE_READ + b".....\n"
                + verify_module.M2_ANIMATION_ARMATURE_RESULT_TAIL
            )
        elif name == verify_module.M2_SCULPT_BRUSH_CURVE_PRESETS_SUITE:
            native_body = (
                b".........\n\n"
                + verify_module.M2_SCULPT_BRUSH_CURVE_PRESETS_RESULT_TAIL
            )
            wasm_body = (
                b".........\n"
                + verify_module.M2_SCULPT_BRUSH_CURVE_PRESETS_RESULT_TAIL
            )
        elif name == verify_module.M2_OPERATOR_FUNCTION_PY_API_SUITE:
            native_body = (
                b"." * 7 + b"\n" + b"." * 26 + b"\n"
                + verify_module.M2_OPERATOR_FUNCTION_PY_API_RESULT_TAIL
            )
            wasm_body = (
                b"." * 33 + b"\n"
                + verify_module.M2_OPERATOR_FUNCTION_PY_API_RESULT_TAIL
            )
        elif name == verify_module.M2_GEOMETRY_ATTRIBUTES_SUITE:
            native_body = (
                b"." * 9 + b"\n" + b"." * 7 + b"\n"
                + verify_module.M2_GEOMETRY_ATTRIBUTES_RESULT_TAIL
            )
            wasm_body = (
                b"." * 16 + b"\n"
                + verify_module.M2_GEOMETRY_ATTRIBUTES_RESULT_TAIL
            )
        elif name == verify_module.M2_NO_DENOISER_SUITE:
            native_body = (
                b"rna-prefix\n." + verify_module.M2_RNA_ACCESSORS_COLORSPACE_WARNING
                + b"\n" + verify_module.M2_RNA_ACCESSORS_RESULT_SEPARATOR
                + b"rna-suffix\n"
            )
            wasm_body = (
                b"rna-prefix\n" + verify_module.M2_RNA_ACCESSORS_COLORSPACE_WARNING
                + b".\n" + verify_module.M2_RNA_ACCESSORS_RESULT_SEPARATOR
                + b"rna-suffix\n"
            )
        elif name == verify_module.M2_NODE_GROUP_COMPAT_SUITE:
            nodegroup36_native = b"".join([
                verify_module.M2_NODE_GROUP_COMPAT_NODEGROUP36_READ,
                verify_module.M2_NODE_GROUP_COMPAT_OUTPUT_WARNING,
                verify_module.M2_NODE_GROUP_COMPAT_NODEGROUP36_READ[1:],
                b"." + verify_module.M2_NODE_GROUP_COMPAT_OUTPUT_WARNING,
                verify_module.M2_NODE_GROUP_COMPAT_NODEGROUP36_READ,
                verify_module.M2_NODE_GROUP_COMPAT_OUTPUT_WARNING,
            ])
            native_body = (
                b"node-prefix\n" + nodegroup36_native
                + verify_module.M2_NODE_GROUP_COMPAT_COMPOSITOR_READ
                + b"." + verify_module.M2_NODE_GROUP_COMPAT_DOVERSION_WARNING
                + b"node-suffix\n"
            )
            wasm_body = (
                b"node-prefix\n"
                + verify_module.M2_NODE_GROUP_COMPAT_NODEGROUP36_CANONICAL
                + b"." + verify_module.M2_NODE_GROUP_COMPAT_COMPOSITOR_READ
                + verify_module.M2_NODE_GROUP_COMPAT_DOVERSION_WARNING
                + b"node-suffix\n"
            )
        elif name == verify_module.M2_NODE_TOOLS_SUITE:
            native_body = b"...\n.\n" + verify_module.M2_NODE_TOOLS_RESULT_TAIL
            wasm_body = b"....\n" + verify_module.M2_NODE_TOOLS_RESULT_TAIL
        elif name == verify_module.M2_ANIMATION_KEYFRAMING_SUITE:
            native_body = b"".join([
                b"keyframing-prefix\n",
                b"." + verify_module.M2_ANIMATION_KEYFRAMING_FIRST_WARNING,
                *verify_module.M2_ANIMATION_KEYFRAMING_PROGRESS_MIDDLE,
                verify_module.M2_ANIMATION_KEYFRAMING_FCURVE_CREATE_WARNING,
                b"." + verify_module.M2_ANIMATION_KEYFRAMING_KEYING_SET_ERROR,
                b"keyframing-suffix\n",
            ])
            wasm_body = (
                b"keyframing-prefix\n"
                + verify_module.M2_ANIMATION_KEYFRAMING_PROGRESS_CANONICAL
                + b"keyframing-suffix\n"
            )
        elif name == verify_module.M2_VERTEX_GROUP_PAINTING_SUITE:
            native_body = (
                verify_module.M2_VERTEX_GROUP_PAINTING_READ + b"."
                + verify_module.M2_VERTEX_GROUP_PAINTING_READ + b".\n"
                + verify_module.M2_VERTEX_GROUP_PAINTING_RESULT_TAIL
                + verify_module.M2_VERTEX_GROUP_PAINTING_ERROR
            )
            wasm_body = verify_module.M2_VERTEX_GROUP_PAINTING_CANONICAL
        elif name == verify_module.M2_ANIMATION_FCURVES_SUITE:
            native_euler = b"".join([
                verify_module.M2_ANIMATION_FCURVES_EULER_READ,
                b"." + verify_module.M2_ANIMATION_FCURVES_EULER_MISSING,
                verify_module.M2_ANIMATION_FCURVES_EULER_FILTERED,
                verify_module.M2_ANIMATION_FCURVES_EULER_READ,
                verify_module.M2_ANIMATION_FCURVES_EULER_MISSING,
                verify_module.M2_ANIMATION_FCURVES_EULER_FILTERED,
            ])
            native_body = (
                b"fcurves-prefix\n" + native_euler
                + b"".join(verify_module.m2_animation_fcurves_warning_block(
                    verify_module.M2_ANIMATION_FCURVES_NATIVE_DOT_OFFSETS
                )) + b"fcurves-suffix\n"
            )
            wasm_body = (
                b"fcurves-prefix\n"
                + verify_module.M2_ANIMATION_FCURVES_EULER_CANONICAL
                + verify_module.M2_ANIMATION_FCURVES_WARNING_CANONICAL
                + b"fcurves-suffix\n"
            )
        elif name == verify_module.M2_MESH_VALIDATE_SUITE:
            native_body = b"".join([
                b"mesh-prefix\n",
                *verify_module.M2_MESH_VALIDATE_PROGRESS_ERRORS[:-1],
                b"....." + verify_module.M2_MESH_VALIDATE_PROGRESS_ERRORS[-1],
                b"mesh-suffix\n",
            ])
            wasm_body = (
                b"mesh-prefix\n" + verify_module.M2_MESH_VALIDATE_PROGRESS_CANONICAL
                + b"mesh-suffix\n"
            )
        elif name == verify_module.M2_SCULPT_FACE_SET_SUITE:
            native_body = (
                verify_module.M2_SCULPT_FACE_SET_READ
                + verify_module.M2_SCULPT_FACE_SET_READ
                + b".." + verify_module.M2_SCULPT_FACE_SET_READ + b".\n"
                + verify_module.M2_SCULPT_FACE_SET_RESULT_TAIL
            )
            wasm_body = verify_module.M2_SCULPT_FACE_SET_CANONICAL
        elif name == "script_pyapi_idprop":
            native_body = b'  File "/work/upstream/tests/python/bl_pyapi_idprop.py"\n'
            wasm_body = (
                b'  File "' + os.fsencode(root.resolve())
                + b'/upstream/tests/python/bl_pyapi_idprop.py"\n'
            )
        elif name == "bl_rna_paths":
            native_body, wasm_body = rna_native_body, rna_wasm_body
        elif name == "bl_animation_action":
            native_body, wasm_body = animation_native_body, animation_wasm_body
        elif name == "blendfile_library_overrides":
            native_body, wasm_body = library_native_body, library_wasm_body
        native_body = native_body.replace(
            verify_module.M2_REPOSITORY_ROOT_TOKEN,
            verify_module.M2_CONTAINER_REPOSITORY_ROOT,
        )
        wasm_body = wasm_body.replace(
            verify_module.M2_REPOSITORY_ROOT_TOKEN,
            os.fsencode(root.resolve()),
        )
        native_scratch = (
            root.resolve() / "sandbox/final-m0-m3/evidence" / label / "m2" /
            "scratch" / name / "native"
        )
        wasm_scratch = (
            root.resolve() / "sandbox/final-m0-m3/evidence" / label / "m2" /
            "scratch" / name / "wasm"
        )
        if name == verify_module.M2_SCRATCH_ROOT_SUITE:
            native_body = b"".join(
                os.fsencode(native_scratch / f"fixture-{number}.blend") + b"\n"
                for number in range(verify_module.M2_SCRATCH_ROOT_OCCURRENCES)
            ) + native_body
            wasm_body = b"".join(
                os.fsencode(wasm_scratch / f"fixture-{number}.blend") + b"\n"
                for number in range(verify_module.M2_SCRATCH_ROOT_OCCURRENCES)
            ) + wasm_body
        elif name == "blendfile_liblink":
            native_body = b"".join(
                os.fsencode(native_scratch / f"blendfile_io/fixture-{number}.blend") + b"\n"
                for number in range(
                    verify_module.M2_SCRATCH_ROOT_POLICIES["blendfile_liblink"]
                )
            ) + native_body
            wasm_body = b"".join(
                os.fsencode(wasm_scratch / f"blendfile_io/fixture-{number}.blend") + b"\n"
                for number in range(
                    verify_module.M2_SCRATCH_ROOT_POLICIES["blendfile_liblink"]
                )
            ) + wasm_body
        elif name == "blendfile_relationships":
            native_body = b"".join(
                os.fsencode(native_scratch / f"blendfile_io/fixture-{number}.blend") + b"\n"
                for number in range(
                    verify_module.M2_SCRATCH_ROOT_POLICIES["blendfile_relationships"]
                )
            ) + native_body
            wasm_body = b"".join(
                os.fsencode(wasm_scratch / f"blendfile_io/fixture-{number}.blend") + b"\n"
                for number in range(
                    verify_module.M2_SCRATCH_ROOT_POLICIES["blendfile_relationships"]
                )
            ) + wasm_body
        elif name == "blendfile_library_overrides":
            def materialize_library_override_scratch(
                body: bytes, scratch_root: Path
            ) -> bytes:
                encoded_root = os.fsencode(scratch_root)
                before = verify_module.M2_LIBRARY_OVERRIDE_SCRATCH_PHASE_BEFORE.replace(
                    verify_module.M2_SCRATCH_ROOT_TOKEN, encoded_root
                )
                after = verify_module.M2_LIBRARY_OVERRIDE_SCRATCH_PHASE_AFTER.replace(
                    verify_module.M2_SCRATCH_ROOT_TOKEN, encoded_root
                )
                body = body.replace(
                    verify_module.M2_LIBRARY_OVERRIDE_PHASE_BEFORE, before, 1
                ).replace(
                    verify_module.M2_LIBRARY_OVERRIDE_PHASE_AFTER, after, 1
                )
                filler_count = (
                    verify_module.M2_SCRATCH_ROOT_POLICIES[
                        "blendfile_library_overrides"
                    ] - 3
                )
                filler = b" ".join(
                    encoded_root + f"/fixture-{number}.blend".encode()
                    for number in range(filler_count)
                )
                return body.replace(
                    b"library-prefix-00\n",
                    b"library-prefix-00 " + filler + b"\n",
                    1,
                )

            native_body = materialize_library_override_scratch(
                native_body, native_scratch
            )
            wasm_body = materialize_library_override_scratch(
                wasm_body, wasm_scratch
            )
        elif name == "bl_animation_action":
            native_temp_read = (
                b'<LOG_TIME>  blend            | Read blend: "'
                + os.fsencode(
                    native_scratch / "bl_animation_action/liboverride-action-slot.blend"
                ) + b'"\n'
            )
            wasm_temp_read = (
                b'<LOG_TIME>  blend            | Read blend: "'
                + os.fsencode(
                    wasm_scratch / "bl_animation_action/liboverride-action-slot.blend"
                ) + b'"\n'
            )
            native_body = native_body.replace(
                verify_module.M2_ANIMATION_TEMP_READ, native_temp_read, 1
            )
            wasm_body = wasm_body.replace(
                verify_module.M2_ANIMATION_TEMP_READ, wasm_temp_read, 1
            )
        normalized_native = verify_module.m2_canonicalize_suite_records(
            verify_module.m2_canonicalize_repository_roots(
                verify_module.m2_canonicalize_suite_scratch_root(
                    native_body, suite=name, scratch_root=native_scratch,
                    root=root.resolve(),
                ),
                root=root.resolve(),
            ),
            name,
        )
        normalized_wasm = verify_module.m2_canonicalize_suite_records(
            verify_module.m2_canonicalize_repository_roots(
                verify_module.m2_canonicalize_suite_scratch_root(
                    wasm_body, suite=name, scratch_root=wasm_scratch,
                    root=root.resolve(),
                ),
                root=root.resolve(),
            ),
            name,
        )
        native = write(
            raw_dir / "m2-native" / f"{name}.txt",
            normalized_native,
        )
        detector = name == verify_module.M2_DETECTOR_ACTIVE_SUITE
        detector_marker = verify_module.M2_DETECTOR_ACTIVE_MARKER
        wasm = write(
            raw_dir / "m2-wasm" / f"{name}.txt",
            detector_marker + "\n" if detector else normalized_wasm,
        )
        native_runtime_warning = (
            verify_module.M2_NATIVE_CUEW_NORMALIZED_LINE.replace(
                b"<LOG_TIME>", b"00:01.002"
            )
            if name == verify_module.M2_NO_DENOISER_SUITE else b""
        )
        native_raw = write(
            raw_dir / "m2-native-raw" / f"{name}.txt",
            native_runtime_warning + native_body
            + verify_module.M2_ALLOCATOR_LINE
            + b"Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:31:22)\n"
        )
        denoiser_warning = (
            b"00:01.002  bpy.rna          | WARNING current value '4' matches no enum in "
            b"'CyclesRenderSettings', '', 'denoiser'\n"
            if name == verify_module.M2_NO_DENOISER_SUITE else b""
        )
        wasm_raw = write(
            raw_dir / "m2-wasm-raw" / f"{name}.txt",
            verify_module.M2_ALLOCATOR_LINE
            + verify_module.M2_WASM_BANNER_LINE
            + (
                detector_marker.replace("0xADDR", "0x12345").encode() + b"\n"
                if detector else denoiser_warning + wasm_body
            )
        )
        detector_id = verify_module.M2_DETECTOR_ACTIVE_ID
        pass_delta_id = verify_module.M2_PASS_DELTA_DEFERRALS.get(name)
        deferral_ids = [detector_id] if detector else [pass_delta_id] if pass_delta_id else []
        deferral_records = [{
            "id": detector_id,
            "status": verify_module.M2_DETECTOR_ACTIVE_STATUS,
            "evidence": f"fixture evidence for {detector_id}",
            "marker": detector_marker,
        }] if detector else [{
            "id": pass_delta_id,
            "status": verify_module.M2_PASS_DELTA_LEDGER[pass_delta_id]["status"],
            "evidence": verify_module.M2_PASS_DELTA_LEDGER[pass_delta_id]["evidence"],
            "marker": verify_module.M2_PASS_DELTA_MARKERS[name],
        }] if pass_delta_id else []
        m2_rows[name] = {
            "native_exit": 0, "wasm_exit": 1 if detector else 0,
            "native_raw_log": ref(root, native_raw), "wasm_raw_log": ref(root, wasm_raw),
            "native_log": ref(root, native), "wasm_log": ref(root, wasm),
            "native_normalized_sha256": digest(native),
            "wasm_normalized_sha256": digest(wasm),
            "result": "DEFERRED" if detector else "PASS_WITH_DEFERRAL" if pass_delta_id else "PASS",
            "deferral_ids": deferral_ids, "deferral_records": deferral_records,
        }
    staged_cycles = {
        name: write(
            raw_dir.parent / "scripts/addons_core/cycles" / name,
            source.read_bytes(),
        )
        for name, source in cycles_sources.items()
    }
    runtime_assets = write_json(raw_dir / "runtime-assets.json", {
        "schema": 1,
        "system_resources": ".",
        "system_scripts": "scripts",
        "python_environment": {
            "PYTHONHASHSEED": "0", "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        "pass_delta_note": ref(root, pass_delta_note),
        "base_scripts": [{
            "source": ref(root, base_script_source),
            "staged": ref(root, write(
                raw_dir.parent / "scripts/startup/fixture.py",
                base_script_source.read_bytes(),
            )),
        }],
        "cycles_addon": [
            {"source": ref(root, cycles_sources[name]), "staged": ref(root, staged_cycles[name])}
            for name in sorted(cycles_sources)
        ],
        "datafiles": [{
            "source": ref(root, datafile_source),
            "staged": ref(root, write(
                raw_dir.parent / "datafiles/fixture.dat", datafile_source.read_bytes(),
            )),
        }],
        "assets": [{
            "source": ref(root, asset_source),
            "staged": ref(root, write(
                raw_dir.parent / "datafiles/assets/fixture.blend", asset_source.read_bytes(),
            )),
        }],
        "locale_languages": {
            "source": ref(root, locale_languages),
            "staged": ref(root, write(
                raw_dir.parent / "datafiles/locale/languages",
                locale_languages.read_bytes(),
            )),
        },
    })
    python_probe_result = write_json(raw_dir / "python-probe.json", {
        "version": "3.13.13", "import_bpy": True,
        "cycles_engine": True, "language_count": 51,
    })
    python_probe_stdout = write(
        raw_dir / "python-probe.stdout", "Blender 5.2.0 LTS\n\nBlender quit\n"
    )
    python_probe_stderr = write(raw_dir / "python-probe.stderr", b"")
    m2_value = common(label, run_stamp, freeze_hash) | {
        "runtime": {
            "native_oracle": ref(root, native_oracle), "node": ref(root, node),
            "javascript": ref(root, blender_js), "wasm": ref(root, blender_wasm),
            "cmake_cache": ref(root, wasm_build / "CMakeCache.txt"),
            "node_version": "v22.16.0", "python_stdlib_manifest": ref(root, py_manifest),
            "python_version": "3.13.13", "import_bpy": True, "cycles_engine": True,
            "language_count": 51, "openimagedenoise": False,
            "python_probe_result": ref(root, python_probe_result),
            "python_probe_stdout": ref(root, python_probe_stdout),
            "python_probe_stderr": ref(root, python_probe_stderr),
            "runtime_assets": ref(root, runtime_assets), "factory_startup": True,
        },
        "suite_manifest": ref(root, root / "sandbox/tierb-prep/suites.tsv"),
        "normalization_policy": ref(root, normalization),
        "deferral_registry": ref(root, root / "ledger/deferred.json"),
        "total": 75,
        "rows": m2_rows,
    }
    m2 = write_json(receipt_dir / "m2.json", m2_value)

    inventory_lines: list[str] = []
    dependency_rows: list[dict[str, Any]] = []
    dependency_spec_rows: dict[str, Any] = {}
    for name in sorted(verify_module.REQUIRED_DEPS):
        artifact = write(root / "lib/wasm/lib" / f"lib{name}.a", f"archive {name}\n")
        inventory_lines.append(artifact.relative_to(root).as_posix())
        dependency_spec_rows[name] = {
            "runtime_linked": True,
            "artifacts": [artifact.relative_to(root).as_posix()],
            "license_payloads": [fixture_license.relative_to(root).as_posix()],
        }
        dependency_rows.append({
            "name": name, "version": "1.0", "license": "BSD-3-Clause",
            "gpl_compatible": True, "runtime_linked": True,
            "notice": f"fixture {name}", "source": f"fixture source {name}",
            "license_payloads": [ref(root, fixture_license)],
            "artifacts": [ref(root, artifact)],
        })
    osd_artifacts = [opensubdiv_cpu, opensubdiv_gpu]
    inventory_lines.extend(path.relative_to(root).as_posix() for path in osd_artifacts)
    dependency_spec_rows["opensubdiv"] = {
        "runtime_linked": True,
        "artifacts": [path.relative_to(root).as_posix() for path in osd_artifacts],
        "license_payloads": [fixture_license.relative_to(root).as_posix()],
    }
    dependency_rows.append({
        "name": "opensubdiv", "version": verify_module.M3_OPENSUBDIV_VERSION,
        "license": "Apache-2.0", "gpl_compatible": True, "runtime_linked": True,
        "notice": "fixture opensubdiv", "source": "fixture OpenSubdiv source",
        "license_payloads": [ref(root, fixture_license)],
        "artifacts": [ref(root, path) for path in osd_artifacts],
    })
    dependency_spec = write_json(
        root / "sandbox/final-m0-m3/m2_dependency_inventory.json",
        {"schema": 1, "dependencies": dependency_spec_rows},
    )
    inventory = write(raw_dir / "deps-inventory.txt", "\n".join(inventory_lines) + "\n")
    compliance = write_json(raw_dir / "deps-compliance.json", {"schema": 1, "verdict": "PASS", "run_label": label, "source_freeze_sha256": freeze_hash, "reuse_exit_code": 0, "violations": 0, "deps_ledger_sha256": digest(root / "ledger/deps.json"), "inventory_sha256": digest(inventory), "inventory_spec_sha256": digest(dependency_spec)})
    m2_deps_value = common(label, run_stamp, freeze_hash) | {
        "deps_ledger": ref(root, root / "ledger/deps.json"),
        "inventory_spec": ref(root, dependency_spec), "inventory_manifest": ref(root, inventory),
        "compliance_proof": ref(root, compliance), "unlisted_artifacts": 0, "missing_artifacts": 0,
        "dependencies": dependency_rows, "unresolved_external_policy": [],
        "external_policy_pass": True,
    }
    m2_deps = write_json(receipt_dir / "m2-deps.json", m2_deps_value)

    # M3 exact suite, canonical build provenance, exact no-work state, and a
    # real cold/warm cache binding.
    m3_build = root / "build-native-gpu"
    m3_cache = write(
        m3_build / "CMakeCache.txt",
        f"CMAKE_BUILD_TYPE:STRING=Release\n"
        f"CMAKE_GENERATOR:INTERNAL=Ninja\n"
        f"CMAKE_HOME_DIRECTORY:INTERNAL={(root / 'upstream').resolve()}\n"
        "WITH_GTESTS:BOOL=ON\n"
        "WITH_GPU_BACKEND_TESTS:BOOL=ON\n"
        "WITH_GPU_DRAW_TESTS:BOOL=ON\n"
        "WITH_OPENSUBDIV:BOOL=ON\n"
        "WITH_WEBGPU_BACKEND:BOOL=ON\n",
    )
    m3_ninja = write(m3_build / "build.ninja", "\n".join([
        "rule CXX_EXECUTABLE_LINKER__blender_test_Release",
        "  command = :",
        "build bin/tests/blender_test: CXX_EXECUTABLE_LINKER__blender_test_Release",
        "build blender_test: phony bin/tests/blender_test",
    ]) + "\n")
    binary = write(
        m3_build / "bin/tests/blender_test", "native test binary\n", True
    )
    # Record the fixture command hash without changing the already-created
    # output, so the independently repeated dry-run is literally no-work.
    subprocess.run(
        verify_module.ninja_locked_command("blender_test"), cwd=m3_build, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    no_work_stdout = write(
        raw_dir / "m3-ninja-no-work.stdout", verify_module.NINJA_NO_WORK_STDOUT
    )
    no_work_stderr = write(raw_dir / "m3-ninja-no-work.stderr", b"")
    m3_no_work = {
        "command": verify_module.ninja_locked_command("-n", "blender_test"),
        "cwd": "build-native-gpu",
        "target": "blender_test",
        "returncode": 0,
        "stdout": ref(root, no_work_stdout),
        "stderr": ref(root, no_work_stderr),
    }
    final_no_work_stdout = write(
        raw_dir / "m3-ninja-final-no-work.stdout", verify_module.NINJA_NO_WORK_STDOUT
    )
    final_no_work_stderr = write(raw_dir / "m3-ninja-final-no-work.stderr", b"")
    m3_final_no_work = {
        "command": verify_module.ninja_locked_command("-n", "blender_test"),
        "cwd": "build-native-gpu",
        "target": "blender_test",
        "returncode": 0,
        "stdout": ref(root, final_no_work_stdout),
        "stderr": ref(root, final_no_work_stderr),
    }
    gpu_names = sorted([
        f"GPUWebGPUTest.test_{index:03d}"
        for index in range(verify_module.M3_GPU_TEST_COUNT)
    ])
    draw_names = list(verify_module.M3_DRAW_WEBGPU_TESTS)
    shader_names = sorted([verify_module.M3_REQUIRED_SHADER_ID] + [
        f"shader_{index:04d}" for index in range(verify_module.M3_SHADER_COUNT - 1)
    ])
    canonical_gpu_manifest = write(
        root / verify_module.M3_GPU_CANONICAL_MANIFEST, "\n".join(gpu_names) + "\n"
    )
    canonical_shader_manifest = write(
        root / verify_module.M3_SHADER_CANONICAL_MANIFEST,
        "\n".join(shader_names) + "\n",
    )
    gpu_manifest = write(raw_dir / "gpu-tests.txt", "\n".join(gpu_names) + "\n")
    gpu_list_stdout = write(
        raw_dir / "gpu-list.stdout",
        "GPUWebGPUTest.\n"
        + "".join(f"  {name.split('.', 1)[1]}\n" for name in gpu_names),
    )
    gpu_list_stderr = write(raw_dir / "gpu-list.stderr", b"")
    draw_manifest = write(raw_dir / "draw-webgpu-tests.txt", "\n".join(draw_names) + "\n")
    draw_list_stdout = write(
        raw_dir / "draw-webgpu-list.stdout",
        "DrawWebGPUTest.\n" + "".join(f"  {name.split('.', 1)[1]}\n" for name in draw_names),
    )
    draw_list_stderr = write(raw_dir / "draw-webgpu-list.stderr", b"")
    draw_logs = {
        name: write(
            raw_dir / f"{name}.log",
            f"[ RUN      ] {name}\n[       OK ] {name} (1 ms)\n",
        )
        for name in draw_names
    }
    gpu_logs = {
        name: write(
            raw_dir / f"{name}.log",
            f"[ RUN      ] {name}\n[       OK ] {name} (1 ms)\n",
        )
        for name in gpu_names
    }
    shader_manifest = write(raw_dir / "shaders.txt", "\n".join(shader_names) + "\n")
    gpu_raw = write_json(raw_dir / "gpu-raw.json", {
        "schema": 1, "verdict": "PASS", "run_label": label,
        "source_freeze_sha256": freeze_hash, "binary_sha256": digest(binary),
        "cmake_cache_sha256": digest(m3_cache),
        "build_ninja_sha256": digest(m3_ninja), "no_work": m3_no_work,
        "final_no_work": m3_final_no_work,
        "manifest_sha256": digest(gpu_manifest),
        "canonical_manifest_sha256": digest(canonical_gpu_manifest),
        "list_stdout_sha256": digest(gpu_list_stdout),
        "list_stderr_sha256": digest(gpu_list_stderr),
        "total": verify_module.M3_GPU_TEST_COUNT,
        "passed": verify_module.M3_GPU_TEST_COUNT,
        "failed": 0, "crashed": 0,
    })
    shader_raw = write_json(raw_dir / "shader-raw.json", {
        "schema": 1, "verdict": "PASS", "run_label": label,
        "source_freeze_sha256": freeze_hash, "binary_sha256": digest(binary),
        "cmake_cache_sha256": digest(m3_cache),
        "build_ninja_sha256": digest(m3_ninja), "no_work": m3_no_work,
        "final_no_work": m3_final_no_work,
        "manifest_sha256": digest(shader_manifest), "total": verify_module.M3_SHADER_COUNT,
        "canonical_manifest_sha256": digest(canonical_shader_manifest),
        "passed": verify_module.M3_SHADER_COUNT, "excluded": 0, "failed": 0,
    })
    draw_raw = write_json(raw_dir / "draw-webgpu-raw.json", {
        "schema": 1, "verdict": "PASS", "run_label": label,
        "source_freeze_sha256": freeze_hash, "binary_sha256": digest(binary),
        "cmake_cache_sha256": digest(m3_cache),
        "build_ninja_sha256": digest(m3_ninja), "no_work": m3_no_work,
        "final_no_work": m3_final_no_work,
        "manifest_sha256": digest(draw_manifest),
        "list_stdout_sha256": digest(draw_list_stdout),
        "list_stderr_sha256": digest(draw_list_stderr),
        "total": len(draw_names), "passed": len(draw_names),
        "failed": 0, "crashed": 0,
    })
    def static_log(cache_status: str) -> str:
        return (
            "[ RUN      ] GPUWebGPUTest.static_shaders\n"
            + verify_module.M3_CENSUS_BEGIN + "\n"
            + "".join(
                f"BW_SHADER_CACHE_RESULT {cache_status} {name}\n"
                for name in shader_names
            )
            + "".join(
                f"BW_SHADER_RESULT PASS {name}\n"
                for name in shader_names
            )
            + verify_module.M3_CENSUS_END + "\n"
            + "[       OK ] GPUWebGPUTest.static_shaders (1 ms)\n"
        )
    cold_shader_log = write(raw_dir / "static-shaders-cold.log", static_log("MISS"))
    warm_shader_log = write(raw_dir / "static-shaders-warm.log", static_log("HIT"))
    gpu_logs["GPUWebGPUTest.static_shaders"] = cold_shader_log
    cache_manifest = write(raw_dir / "cache.manifest", "\n".join(f"{name} deadbeef" for name in shader_names) + "\n")
    source_digest = freeze_hash
    toolchain_digest = digest(m0)
    def cache_proof(mode: str, hits: int, misses: int) -> Path:
        return write_json(raw_dir / f"cache-{mode}.json", {"schema": 1, "verdict": "PASS", "run_label": label, "mode": mode, "cache_manifest_sha256": digest(cache_manifest), "source_digest": source_digest, "toolchain_digest": toolchain_digest, "hits": hits, "misses": misses})
    cold = cache_proof("cold", 0, verify_module.M3_SHADER_COUNT)
    warm = cache_proof("warm", verify_module.M3_SHADER_COUNT, 0)
    opensubdiv_members = write(
        raw_dir / "opensubdiv-gpu-members.log",
        "version.cpp.o\nglslPatchShaderSource.cpp.o\n",
    )
    opensubdiv_defined = write(
        raw_dir / "opensubdiv-gpu-defined.log",
        "00000ca1 T OpenSubdiv::v3_7_0::Osd::GLSLPatchShaderSource::"
        "GetPatchBasisShaderSource()\n",
    )
    opensubdiv_undefined = write(
        raw_dir / "opensubdiv-gpu-undefined.log",
        "glslPatchShaderSource.cpp.o:\n U _Znwm\n",
    )
    opensubdiv_smoke = write(
        raw_dir / "opensubdiv-wasm-smoke.log",
        "OSD_WASM_REFINE nverts_level1=26 glsl_bytes=4096 param=1 evaluate=1\n",
    )
    critical_rows = []
    for key, relative in sorted(verify_module.m3_critical_input_paths().items()):
        path = root / relative
        critical_rows.append(f"{key}\t{relative}\t{path.stat().st_size}\t{digest(path)}")
    critical_before = write(
        raw_dir / "critical-inputs-before.manifest", "\n".join(critical_rows) + "\n"
    )
    critical_after = write(
        raw_dir / "critical-inputs-after.manifest", "\n".join(critical_rows) + "\n"
    )
    m3_value = common(label, run_stamp, freeze_hash) | {
        "binary": ref(root, binary), "cmake_cache": ref(root, m3_cache),
        "build_ninja": ref(root, m3_ninja), "no_work": m3_no_work,
        "final_no_work": m3_final_no_work,
        "critical_inputs": {
            "before": ref(root, critical_before), "after": ref(root, critical_after)
        },
        "device_limit_sources": {
            "native_context": ref(root, native_limit_source),
            "web_fallback": ref(root, web_fallback_limit_source),
            "worker_preinit": ref(root, worker_limit_source),
        },
        "cache_marker_source": ref(root, cache_marker_source),
        "opensubdiv": {
            "version": verify_module.M3_OPENSUBDIV_VERSION,
            "tarball_md5": verify_module.M3_OPENSUBDIV_TARBALL_MD5,
            "sources": {
                "recipe": ref(root, opensubdiv_recipe),
                "configure": ref(root, opensubdiv_configure),
                "upstream_cmake": ref(root, opensubdiv_cmake),
                "evaluator": ref(root, opensubdiv_evaluator),
            },
            "header": ref(root, opensubdiv_header),
            "cpu_archive": ref(root, opensubdiv_cpu),
            "gpu_archive": ref(root, opensubdiv_gpu),
            "tools": {key: ref(root, path) for key, path in opensubdiv_tools.items()},
            "members": ref(root, opensubdiv_members),
            "defined_symbols": ref(root, opensubdiv_defined),
            "undefined_symbols": ref(root, opensubdiv_undefined),
            "wasm_smoke": ref(root, opensubdiv_smoke),
        },
        "toolchain_binding_sha256": digest(m0),
        "gpu_tests": {
            "canonical_manifest": ref(root, canonical_gpu_manifest),
            "manifest": ref(root, gpu_manifest), "raw_result": ref(root, gpu_raw),
            "list_stdout": ref(root, gpu_list_stdout),
            "list_stderr": ref(root, gpu_list_stderr),
            "total": verify_module.M3_GPU_TEST_COUNT,
            "passed": verify_module.M3_GPU_TEST_COUNT, "failed": 0, "crashed": 0,
            "rows": {name: {"status": "PASS", "exit_code": 0,
                            "raw_log": ref(root, gpu_logs[name])} for name in gpu_names},
        },
        "draw_webgpu_tests": {
            "manifest": ref(root, draw_manifest), "raw_result": ref(root, draw_raw),
            "list_stdout": ref(root, draw_list_stdout),
            "list_stderr": ref(root, draw_list_stderr),
            "total": len(draw_names), "passed": len(draw_names),
            "failed": 0, "crashed": 0,
            "rows": {
                name: {"status": "PASS", "exit_code": 0, "raw_log": ref(root, draw_logs[name])}
                for name in draw_names
            },
        },
        "static_shaders": {
            "canonical_manifest": ref(root, canonical_shader_manifest),
            "manifest": ref(root, shader_manifest), "raw_result": ref(root, shader_raw),
            "cold_log": ref(root, cold_shader_log), "warm_log": ref(root, warm_shader_log),
            "total": verify_module.M3_SHADER_COUNT, "passed": verify_module.M3_SHADER_COUNT,
            "excluded": 0, "failed": 0,
            "rows": {name: {"status": "PASS"} for name in shader_names},
        },
        "shader_cache": {"manifest": ref(root, cache_manifest), "cold_proof": ref(root, cold), "warm_proof": ref(root, warm), "source_digest": source_digest, "toolchain_digest": toolchain_digest, "entries": verify_module.M3_SHADER_COUNT},
    }
    m3 = write_json(receipt_dir / "m3.json", m3_value)

    manifest_value = {
        "schema": 1, "verdict": "PASS", "run_label": label, "created_utc": run_stamp,
        "source_tree": "upstream",
        "source_freeze": {"receipt": ref(root, freeze_receipt), "patch": ref(root, patch), "live_manifest": ref(root, live), "replay_manifest": ref(root, replay)},
        "receipts": {"m0": ref(root, m0), "m1": ref(root, m1), "m2": ref(root, m2), "m2_deps": ref(root, m2_deps), "m3": ref(root, m3)},
    }
    return write_json(root / "evidence/final-m0-m3.json", manifest_value)


def main() -> int:
    now = dt.datetime(2026, 8, 11, 18, 0, tzinfo=dt.timezone.utc)
    negative_checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="final-m0-m3-selfcheck-") as temp_name:
        root = Path(temp_name)
        manifest = build_fixture(root, now)

        def run_ok() -> None:
            result = verify_module.verify(root, manifest, now, 3600)
            assert result["verdict"] == "PASS"

        limit_paths = {
            key: root / path
            for key, path in verify_module.M3_WEBGPU_DEVICE_LIMIT_PATHS.items()
        }
        verify_module.verify_m3_device_limit_contract(limit_paths)
        cache_marker_path = root / verify_module.M3_CACHE_MARKER_SOURCE
        verify_module.verify_m3_cache_marker_contract(cache_marker_path)

        cache_marker_old = cache_marker_path.read_bytes()
        cache_marker_path.write_text(
            cache_marker_old.decode("utf-8").replace(
                "std::strcmp(active_dir, census_dir) != 0", "active_dir == census_dir", 1
            ),
            encoding="utf-8",
        )
        try:
            try:
                verify_module.verify_m3_cache_marker_contract(cache_marker_path)
            except verify_module.VerificationError:
                negative_checks.append("m3_cache_marker_wrong_active_directory")
            else:
                raise AssertionError("wrong cache-marker activation directory unexpectedly passed")
        finally:
            cache_marker_path.write_bytes(cache_marker_old)

        def reject_limit_contract(
            name: str, key: str, change: Callable[[str], str]
        ) -> None:
            path = limit_paths[key]
            old = path.read_bytes()
            path.write_text(change(old.decode("utf-8")), encoding="utf-8")
            try:
                try:
                    verify_module.verify_m3_device_limit_contract(limit_paths)
                except verify_module.VerificationError:
                    negative_checks.append(name)
                else:
                    raise AssertionError(
                        f"negative device-limit fixture unexpectedly passed: {name}"
                    )
            finally:
                path.write_bytes(old)

        first_limit = verify_module.M3_WEBGPU_DEVICE_LIMIT_FIELDS[0]
        second_limit = verify_module.M3_WEBGPU_DEVICE_LIMIT_FIELDS[1]
        reject_limit_contract(
            "m3_device_limits_missing_native",
            "native_context",
            lambda text: text.replace(
                f"required_limits.{first_limit} = supported_limits.{first_limit};\n", "", 1
            ),
        )
        reject_limit_contract(
            "m3_device_limits_duplicate_fallback",
            "web_fallback",
            lambda text: text.replace(
                f"required_limits.{first_limit} = supported_limits.{first_limit};\n",
                f"required_limits.{first_limit} = supported_limits.{first_limit};\n" * 2,
                1,
            ),
        )
        reject_limit_contract(
            "m3_device_limits_wrong_cpp_source",
            "native_context",
            lambda text: text.replace(
                f"supported_limits.{second_limit}", f"device_limits.{second_limit}", 1
            ),
        )
        reject_limit_contract(
            "m3_device_limits_wrong_worker_value",
            "worker_preinit",
            lambda text: text.replace(
                f"adapter.limits.{second_limit}", f"adapter.limits.{first_limit}", 1
            ),
        )

        m3_cache_path = root / "build-native-gpu/CMakeCache.txt"
        verify_module.verify_m3_cmake_cache(m3_cache_path, root)
        m3_cache_old = m3_cache_path.read_bytes()
        m3_cache_path.write_text(
            m3_cache_old.decode("utf-8").replace(
                "WITH_OPENSUBDIV:BOOL=ON", "WITH_OPENSUBDIV:BOOL=OFF", 1
            ),
            encoding="utf-8",
        )
        try:
            try:
                verify_module.verify_m3_cmake_cache(m3_cache_path, root)
            except verify_module.VerificationError:
                negative_checks.append("m3_opensubdiv_disabled")
            else:
                raise AssertionError("OpenSubdiv-disabled M3 cache unexpectedly passed")
        finally:
            m3_cache_path.write_bytes(m3_cache_old)

        m3_cache_path.write_text(
            m3_cache_old.decode("utf-8").replace(
                "WITH_GPU_DRAW_TESTS:BOOL=ON", "WITH_GPU_DRAW_TESTS:BOOL=OFF", 1
            ),
            encoding="utf-8",
        )
        try:
            try:
                verify_module.verify_m3_cmake_cache(m3_cache_path, root)
            except verify_module.VerificationError:
                negative_checks.append("m3_gpu_draw_tests_disabled")
            else:
                raise AssertionError("GPU draw-test-disabled M3 cache unexpectedly passed")
        finally:
            m3_cache_path.write_bytes(m3_cache_old)

        draw_list_path = root / "evidence/raw/draw-webgpu-list.stdout"
        draw_list_stderr_path = root / "evidence/raw/draw-webgpu-list.stderr"
        verify_module.verify_m3_draw_webgpu_list(draw_list_path, draw_list_stderr_path)

        def reject_draw_list_contract(name: str, change: Callable[[str], str]) -> None:
            old = draw_list_path.read_bytes()
            draw_list_path.write_text(change(old.decode("utf-8")), encoding="utf-8")
            try:
                try:
                    verify_module.verify_m3_draw_webgpu_list(
                        draw_list_path, draw_list_stderr_path
                    )
                except verify_module.VerificationError:
                    negative_checks.append(name)
                else:
                    raise AssertionError(f"invalid DrawWebGPUTest list passed: {name}")
            finally:
                draw_list_path.write_bytes(old)

        reject_draw_list_contract(
            "m3_draw_webgpu_list_missing_test",
            lambda text: text.replace("  draw_debug_lifetime_rebind\n", "", 1),
        )
        reject_draw_list_contract(
            "m3_draw_webgpu_list_stale_identity",
            lambda text: text.replace(
                "draw_debug_lifetime_rebind", "draw_debug_display_only", 1
            ),
        )

        draw_run_name = verify_module.M3_DRAW_WEBGPU_TESTS[0]
        draw_run_path = root / "evidence/raw" / f"{draw_run_name}.log"
        verify_module.verify_m3_draw_webgpu_run(draw_run_path, draw_run_name)
        draw_run_old = draw_run_path.read_bytes()
        draw_run_path.write_bytes(
            draw_run_old
            + b"[WebGPU] uncaptured device error (type 2): delayed draw failure\n"
        )
        try:
            try:
                verify_module.verify_m3_draw_webgpu_run(draw_run_path, draw_run_name)
            except verify_module.VerificationError:
                negative_checks.append("m3_draw_webgpu_run_device_error")
            else:
                raise AssertionError("DrawWebGPUTest device error unexpectedly passed")
        finally:
            draw_run_path.write_bytes(draw_run_old)

        gpu_run_name = "GPUWebGPUTest.test_000"
        gpu_run_path = root / "evidence/raw" / f"{gpu_run_name}.log"
        verify_module.verify_m3_gpu_webgpu_run(gpu_run_path, gpu_run_name)
        gpu_run_old = gpu_run_path.read_bytes()
        gpu_run_path.write_text(
            gpu_run_old.decode("utf-8").replace(
                gpu_run_name, "GPUWebGPUTest.test_001"
            ),
            encoding="utf-8",
        )
        try:
            try:
                verify_module.verify_m3_gpu_webgpu_run(gpu_run_path, gpu_run_name)
            except verify_module.VerificationError:
                negative_checks.append("m3_gpu_run_wrong_identity")
            else:
                raise AssertionError("wrong GPUWebGPUTest identity unexpectedly passed")
        finally:
            gpu_run_path.write_bytes(gpu_run_old)

        def reject(name: str, mutate: Callable[[], list[tuple[Path, bytes]]]) -> None:
            restorations = mutate()
            try:
                try:
                    verify_module.verify(root, manifest, now, 3600)
                except verify_module.VerificationError:
                    negative_checks.append(name)
                else:
                    raise AssertionError(f"negative fixture unexpectedly passed: {name}")
            finally:
                for path, payload in reversed(restorations):
                    path.write_bytes(payload)

        def mutate_receipt(name: str, change: Callable[[dict[str, Any]], None]) -> list[tuple[Path, bytes]]:
            manifest_value = json.loads(manifest.read_text())
            receipt_path = root / manifest_value["receipts"][name]["path"]
            old_receipt = receipt_path.read_bytes()
            old_manifest = manifest.read_bytes()
            value = json.loads(old_receipt)
            change(value)
            write_json(receipt_path, value)
            manifest_value["receipts"][name] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(receipt_path, old_receipt), (manifest, old_manifest)]

        def mutate_dependency_spec(change: Callable[[dict[str, Any]], None]) -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m2_deps"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            spec_path = root / receipt_value["inventory_spec"]["path"]
            spec_old = spec_path.read_bytes()
            spec_value = json.loads(spec_old)
            proof_path = root / receipt_value["compliance_proof"]["path"]
            proof_old = proof_path.read_bytes()
            proof_value = json.loads(proof_old)
            change(spec_value)
            write_json(spec_path, spec_value)
            receipt_value["inventory_spec"] = ref(root, spec_path)
            proof_value["inventory_spec_sha256"] = digest(spec_path)
            write_json(proof_path, proof_value)
            receipt_value["compliance_proof"] = ref(root, proof_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m2_deps"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [
                (spec_path, spec_old), (proof_path, proof_old),
                (receipt_path, receipt_old), (manifest, manifest_old),
            ]

        def tamper_artifact() -> list[tuple[Path, bytes]]:
            path = root / "build-wasm-m1-parity/bin/blender.wasm"
            old = path.read_bytes()
            write(path, b"tampered")
            return [(path, old)]

        def tamper_ninja_locked() -> list[tuple[Path, bytes]]:
            path = root / "scripts/ninja-locked.sh"
            old = path.read_bytes()
            write(path, old + b"# tampered locked runner\n", True)
            return [(path, old)]

        run_ok()
        expected_assets = ["--test-assets-dir", str((root / "upstream/tests/files").resolve())]
        exact_argument_rows = {
            key: list(expected_assets)
            for key in verify_module.GTEST_ARGUMENT_PHASES
        }
        assert verify_module.verify_gtest_arguments(
            exact_argument_rows, root, "blenlib", "fixture.arguments"
        ) == exact_argument_rows
        assert verify_module.verify_gtest_arguments(
            {key: [] for key in verify_module.GTEST_ARGUMENT_PHASES},
            root,
            "bmesh_core",
            "fixture.bmesh_arguments",
        )

        def reject_arguments(name: str, rows: dict[str, Any]) -> None:
            try:
                verify_module.verify_gtest_arguments(
                    rows, root, "blenlib", "fixture.arguments"
                )
            except verify_module.VerificationError:
                negative_checks.append(name)
            else:
                raise AssertionError(f"invalid gtest arguments unexpectedly passed: {name}")

        reject_arguments(
            "m1_gtest_assets_missing_argument",
            {key: [] for key in verify_module.GTEST_ARGUMENT_PHASES},
        )
        reject_arguments(
            "m1_gtest_assets_wrong_argument",
            {
                key: ["--test-assets-dir", str(root / "upstream/tests")]
                for key in verify_module.GTEST_ARGUMENT_PHASES
            },
        )
        assets = root / "upstream/tests/files"
        alternate_assets = root / "alternate-test-assets"
        alternate_assets.mkdir()
        assets.rmdir()
        assets.symlink_to(alternate_assets, target_is_directory=True)
        try:
            reject_arguments("m1_gtest_assets_symlink", exact_argument_rows)
        finally:
            assets.unlink()
            assets.mkdir()

        no_work_root = root / "build-native-m1-parity"
        no_work_target = "bin/tests/BLI_test"
        no_work_command = verify_module.ninja_locked_command("-n", no_work_target)
        verify_module.require_ninja_no_work_result(
            no_work_command,
            no_work_root,
            0,
            verify_module.NINJA_NO_WORK_STDOUT,
            b"",
            expected_build_root=no_work_root,
            expected_target=no_work_target,
            where="fixture.no_work",
        )

        def reject_no_work_result(
            name: str,
            command: list[str],
            returncode: int,
            stdout: bytes,
            stderr: bytes,
            *,
            cwd: Path = no_work_root,
        ) -> None:
            try:
                verify_module.require_ninja_no_work_result(
                    command,
                    cwd,
                    returncode,
                    stdout,
                    stderr,
                    expected_build_root=no_work_root,
                    expected_target=no_work_target,
                    where="fixture.no_work",
                )
            except verify_module.VerificationError:
                negative_checks.append(name)
            else:
                raise AssertionError(f"invalid Ninja no-work result unexpectedly passed: {name}")

        reject_no_work_result(
            "m1_ninja_no_work_raw_bypass",
            ["ninja", "-n", no_work_target],
            0,
            verify_module.NINJA_NO_WORK_STDOUT,
            b"",
        )
        reject_no_work_result(
            "m1_ninja_no_work_wrong_cwd",
            no_work_command,
            0,
            verify_module.NINJA_NO_WORK_STDOUT,
            b"",
            cwd=root,
        )
        reject_no_work_result(
            "m1_ninja_no_work_stale",
            no_work_command,
            0,
            b"[1/1] Linking CXX executable bin/tests/BLI_test\n",
            b"",
        )
        reject_no_work_result(
            "m1_ninja_no_work_nonzero",
            no_work_command,
            1,
            b"",
            b"ninja: error: failed\n",
        )
        reject_no_work_result(
            "m1_ninja_no_work_wrong_target",
            verify_module.ninja_locked_command("-n", "bin/tests/blender_test"),
            0,
            verify_module.NINJA_NO_WORK_STDOUT,
            b"",
        )
        reject_no_work_result(
            "m1_ninja_no_work_wrong_output",
            no_work_command,
            0,
            b"ninja: no work to do.\nextra\n",
            b"",
        )
        reject_no_work_result(
            "m1_ninja_no_work_nonempty_stderr",
            no_work_command,
            0,
            verify_module.NINJA_NO_WORK_STDOUT,
            b"ninja: warning: unexpected diagnostic\n",
        )

        stale_input = (
            root
            / "build-native-m1-parity/source/blender/bmesh/CMakeFiles/"
            "bmesh_core_test.dir/tests/bmesh_core_test.cc.o"
        )
        stale_stat = stale_input.stat()
        output_stat = (root / "build-native-m1-parity/bin/tests/bmesh_core_test").stat()
        os.utime(
            stale_input,
            ns=(stale_stat.st_atime_ns, output_stat.st_mtime_ns + 1_000_000_000),
        )
        try:
            try:
                verify_module.verify(root, manifest, now, 3600)
            except verify_module.VerificationError:
                negative_checks.append("m1_ninja_live_stale_input")
            else:
                raise AssertionError("live stale Ninja target unexpectedly passed")
        finally:
            os.utime(
                stale_input, ns=(stale_stat.st_atime_ns, stale_stat.st_mtime_ns)
            )

        verify_module.verify_gtest_occurrence_names(
            ["stack.Peek@occurrence=1", "stack.Peek@occurrence=2"], "fixture")
        def reject_occurrence(name: str, names: list[str]) -> None:
            try:
                verify_module.verify_gtest_occurrence_names(names, "fixture")
            except verify_module.VerificationError:
                negative_checks.append(name)
            else:
                raise AssertionError(f"invalid occurrence encoding unexpectedly passed: {name}")
        reject_occurrence("m1_invalid_occurrence_encoding", ["stack.Peek@occurrence=1"])
        reject_occurrence("m1_occurrence_leading_zero", [
            "stack.Peek@occurrence=01", "stack.Peek@occurrence=02"])
        reject_occurrence("m1_occurrence_nested_alias", [
            "stack.Peek@occurrence=1@occurrence=1",
            "stack.Peek@occurrence=1@occurrence=2"])
        wasm_ninja = root / "build-wasm-m1-parity/build.ninja"
        bmesh_js = root / "build-wasm-m1-parity/bin/tests/bmesh_core_test.js"
        allocator_original = wasm_ninja.read_bytes()
        canonical_allocator = b"-sMALLOC=mimalloc -sMALLOC=dlmalloc"
        for token, replacement in (
            ("m1_bmesh_allocator_override_missing", b"-sMALLOC=mimalloc"),
            ("m1_bmesh_allocator_wrong_last", b"-sMALLOC=dlmalloc -sMALLOC=mimalloc"),
            ("m1_bmesh_allocator_late_split_equals",
             canonical_allocator + b" -s MALLOC=mimalloc"),
            ("m1_bmesh_allocator_late_split_bare",
             canonical_allocator + b" -s MALLOC mimalloc"),
            ("m1_bmesh_allocator_late_compact_bare",
             canonical_allocator + b" -sMALLOC mimalloc"),
            ("m1_bmesh_allocator_malformed_empty",
             canonical_allocator + b" -sMALLOC="),
            ("m1_bmesh_allocator_bare_missing_value",
             canonical_allocator + b" -s MALLOC"),
            ("m1_bmesh_allocator_compact_bare_false_green",
             b"-sMALLOC mimalloc -sMALLOC dlmalloc"),
            ("m1_bmesh_allocator_split_bare_false_green",
             b"-s MALLOC mimalloc -s MALLOC dlmalloc"),
        ):
            wasm_ninja.write_bytes(allocator_original.replace(
                canonical_allocator, replacement, 1
            ))
            try:
                verify_module.verify_ninja_output_rule(
                    wasm_ninja, bmesh_js, "bmesh_core", wasm=True,
                    root=root, where="m1.bmesh_core.wasm",
                )
            except verify_module.VerificationError:
                negative_checks.append(token)
            else:
                raise AssertionError(f"invalid allocator provenance unexpectedly passed: {token}")
            finally:
                wasm_ninja.write_bytes(allocator_original)
        canonical_memory = b"-sINITIAL_MEMORY=33554432"
        for token, replacement in (
            ("m1_bmesh_initial_memory_missing", b""),
            ("m1_bmesh_initial_memory_too_small", b"-sINITIAL_MEMORY=16777216"),
            ("m1_bmesh_initial_memory_late_override",
             canonical_memory + b" -s INITIAL_MEMORY=16777216"),
            ("m1_bmesh_initial_memory_compact_bare_false_green",
             b"-sINITIAL_MEMORY 33554432"),
            ("m1_bmesh_initial_memory_split_bare_false_green",
             b"-s INITIAL_MEMORY 33554432"),
            ("m1_bmesh_initial_memory_legacy_alias",
             canonical_memory + b" -sTOTAL_MEMORY=16777216"),
            ("m1_bmesh_initial_memory_direct_linker",
             canonical_memory + b" -Wl,--initial-memory=16777216"),
        ):
            wasm_ninja.write_bytes(allocator_original.replace(
                canonical_memory, replacement, 1
            ))
            try:
                verify_module.verify_ninja_output_rule(
                    wasm_ninja, bmesh_js, "bmesh_core", wasm=True,
                    root=root, where="m1.bmesh_core.wasm",
                )
            except verify_module.VerificationError:
                negative_checks.append(token)
            else:
                raise AssertionError(
                    f"invalid initial-memory provenance unexpectedly passed: {token}"
                )
            finally:
                wasm_ninja.write_bytes(allocator_original)
        native_ninja = root / "build-native-m1-parity/build.ninja"
        native_original = native_ninja.read_bytes()
        native_ninja.write_bytes(native_original.replace(
            b"LINK_FLAGS = -pthread", b"LINK_FLAGS = -pthread -s MALLOC=dlmalloc", 1
        ))
        try:
            verify_module.verify_ninja_output_rule(
                native_ninja, root / "build-native-m1-parity/bin/tests/BLI_test",
                "blenlib", wasm=False, root=root, where="m1.blenlib.native",
            )
        except verify_module.VerificationError:
            negative_checks.append("m1_native_allocator_injection")
        else:
            raise AssertionError("native allocator injection unexpectedly passed")
        finally:
            native_ninja.write_bytes(native_original)
        reject("artifact_digest_tamper", tamper_artifact)
        reject("m0_ninja_locked_tamper", tamper_ninja_locked)
        def tamper_gtest_manifest() -> list[tuple[Path, bytes]]:
            path = root / "evidence/raw/blenlib-wasm-tests.txt"
            old = path.read_bytes()
            write(path, old + b"blenlib.unlisted_test\n")
            return [(path, old)]
        reject("m1_test_manifest_tamper", tamper_gtest_manifest)
        reject("m1_nonzero_failure", lambda: mutate_receipt("m1", lambda value: value["gtests"]["blenlib"].update({"passed": 1664, "failed": 1})))
        reject("m1_native_executable_unbound", lambda: mutate_receipt(
            "m1", lambda value: value["gtests"]["blenlib"]["native_executable"].update({"sha256": "0" * 64})))
        def mutate_raw_test_arguments() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m1"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            row = receipt_value["gtests"]["blenlib"]
            raw_path = root / row["raw_result"]["path"]
            raw_old = raw_path.read_bytes()
            raw_value = json.loads(raw_old)
            raw_value["test_arguments"]["wasm_run"] = []
            write_json(raw_path, raw_value)
            row["raw_result"] = ref(root, raw_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m1"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(raw_path, raw_old), (receipt_path, receipt_old), (manifest, manifest_old)]
        reject("m1_gtest_argument_raw_mismatch", mutate_raw_test_arguments)
        def mutate_raw_no_work() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m1"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            row = receipt_value["gtests"]["bmesh_core"]
            raw_path = root / row["raw_result"]["path"]
            raw_old = raw_path.read_bytes()
            raw_value = json.loads(raw_old)
            raw_value["no_work"]["wasm"]["target"] = "bin/tests/BLI_test.js"
            raw_value["no_work"]["wasm"]["command"] = (
                verify_module.ninja_locked_command("-n", "bin/tests/BLI_test.js")
            )
            write_json(raw_path, raw_value)
            row["raw_result"] = ref(root, raw_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m1"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(raw_path, raw_old), (receipt_path, receipt_old), (manifest, manifest_old)]
        reject("m1_ninja_no_work_raw_mismatch", mutate_raw_no_work)
        reject("m1_gmp_configuration_mismatch", lambda: mutate_receipt(
            "m1", lambda value: value["gtests"]["blenlib"]["configuration"]["native"].update({"with_gmp": True})))
        def enable_gmp_consistently() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m1"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            row = receipt_value["gtests"]["blenlib"]
            cache_path = root / row["native_cmake_cache"]["path"]
            cache_old = cache_path.read_bytes()
            raw_path = root / row["raw_result"]["path"]
            raw_old = raw_path.read_bytes()
            write(cache_path, cache_old.replace(b"WITH_GMP:BOOL=OFF", b"WITH_GMP:BOOL=ON"))
            row["native_cmake_cache"] = ref(root, cache_path)
            row["configuration"]["native"]["with_gmp"] = True
            raw_value = json.loads(raw_old)
            raw_value["native_cmake_cache_sha256"] = digest(cache_path)
            write_json(raw_path, raw_value)
            row["raw_result"] = ref(root, raw_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m1"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(cache_path, cache_old), (raw_path, raw_old),
                    (receipt_path, receipt_old), (manifest, manifest_old)]
        reject("m1_gmp_enabled_consistent_receipt", enable_gmp_consistently)
        reject("m1_bmesh_monolithic_mislabeled", lambda: mutate_receipt(
            "m1", lambda value: value["gtests"]["bmesh_core"].update({
                "native_executable": value["gtests"]["blenlib"]["native_executable"]})))
        alternate_js = write(root / "alternate-runtime/blender.js", "alternate\n")
        alternate_oracle = write(root / "alternate-runtime/bpy.sh", "#!/bin/sh\nexit 0\n", True)
        alternate_node = write(
            root / "alternate-runtime/node", "#!/bin/sh\necho v22.16.0\n", True
        )
        reject("m1_runtime_alternate_javascript", lambda: mutate_receipt(
            "m1", lambda value: value["runtime"].update({
                "javascript": ref(root, alternate_js)})))
        reject("m1_native_oracle_alternate", lambda: mutate_receipt(
            "m1", lambda value: value["runtime"].update({
                "native_oracle": ref(root, alternate_oracle)})))
        reject("m2_native_oracle_alternate", lambda: mutate_receipt(
            "m2", lambda value: value["runtime"].update({
                "native_oracle": ref(root, alternate_oracle)})))
        reject("m1_node_alternate", lambda: mutate_receipt(
            "m1", lambda value: value["runtime"].update({
                "node": ref(root, alternate_node)})))
        reject("m2_node_version", lambda: mutate_receipt(
            "m2", lambda value: value["runtime"].update({
                "node_version": "v22.16.1"})))
        stale_runtime_stdout = write(
            root / "evidence/raw/runtime-blender-stale.stdout",
            "[1/1] Linking CXX executable bin/blender.js\n",
        )
        reject("m1_runtime_ninja_stale", lambda: mutate_receipt(
            "m1", lambda value: value["runtime"]["no_work"].update({
                "stdout": ref(root, stale_runtime_stdout)})))
        reject("m1_runtime_ninja_raw_bypass", lambda: mutate_receipt(
            "m1", lambda value: value["runtime"]["no_work"].update({
                "command": ["ninja", "-n", "blender"]})))
        def make_m1_runtime_wrong_target(value: dict[str, Any]) -> None:
            value["runtime"]["no_work"].update({
                "command": verify_module.ninja_locked_command("-n", "bin/blender.js"),
                "target": "bin/blender.js",
            })
        reject("m1_runtime_ninja_wrong_target", lambda: mutate_receipt(
            "m1", make_m1_runtime_wrong_target))

        def mutate_m1_runtime_raw(change: Callable[[dict[str, Any]], None]) -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m1"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            raw_path = root / receipt_value["runtime"]["raw_provenance"]["path"]
            raw_old = raw_path.read_bytes()
            raw_value = json.loads(raw_old)
            change(raw_value)
            write_json(raw_path, raw_value)
            receipt_value["runtime"]["raw_provenance"] = ref(root, raw_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m1"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(raw_path, raw_old), (receipt_path, receipt_old), (manifest, manifest_old)]

        reject("m1_runtime_raw_mismatch", lambda: mutate_m1_runtime_raw(
            lambda value: value["no_work"].update({"target": "bin/blender.js"})))
        def reject_runtime_cross_mismatch() -> None:
            manifest_value = json.loads(manifest.read_text())
            receipts = {
                name: json.loads((root / manifest_value["receipts"][name]["path"]).read_text())
                for name in ("m0", "m1", "m2")
            }
            receipts["m2"]["runtime"]["javascript"] = dict(
                receipts["m2"]["runtime"]["javascript"], sha256="0" * 64
            )
            try:
                verify_module.verify_runtime_cross_binding(
                    receipts["m0"], receipts["m1"], receipts["m2"]
                )
            except verify_module.VerificationError:
                negative_checks.append("m1_m2_runtime_cross_mismatch")
            else:
                raise AssertionError("M1/M2 runtime cross mismatch unexpectedly passed")
        reject_runtime_cross_mismatch()
        reject("m2_missing_key", lambda: mutate_receipt("m2", lambda value: value["rows"].pop(verify_module.M2_KEYS[0])))
        reject("m2_language_count_not_source_derived", lambda: mutate_receipt(
            "m2", lambda value: value["runtime"].update({"language_count": 52})))
        tampered_locale = write(
            root / "evidence/raw/tampered-languages", "tampered locale index\n"
        )
        m2_receipt_value = json.loads((root / "evidence/receipts/m2.json").read_text())
        runtime_assets_path = root / m2_receipt_value["runtime"]["runtime_assets"]["path"]
        tampered_assets_value = json.loads(runtime_assets_path.read_text())
        tampered_assets_value["locale_languages"]["staged"] = ref(root, tampered_locale)
        tampered_assets = write_json(
            root / "evidence/raw/tampered-runtime-assets.json", tampered_assets_value
        )
        reject("m2_staged_locale_languages_tamper", lambda: mutate_receipt(
            "m2", lambda value: value["runtime"].update({
                "runtime_assets": ref(root, tampered_assets),
            })))
        tampered_datafile = write(
            root / "evidence/tampered/datafiles/fixture.dat", b"tampered datafile\n"
        )
        tampered_datafile_assets_value = json.loads(runtime_assets_path.read_text())
        tampered_datafile_assets_value["datafiles"][0]["staged"] = ref(
            root, tampered_datafile
        )
        tampered_datafile_assets = write_json(
            root / "evidence/raw/tampered-datafile-runtime-assets.json",
            tampered_datafile_assets_value,
        )
        reject("m2_staged_datafile_tamper", lambda: mutate_receipt(
            "m2", lambda value: value["runtime"].update({
                "runtime_assets": ref(root, tampered_datafile_assets),
            })))
        tampered_asset = write(
            root / "evidence/tampered/datafiles/assets/fixture.blend",
            b"tampered bundled asset\n",
        )
        tampered_asset_assets_value = json.loads(runtime_assets_path.read_text())
        tampered_asset_assets_value["assets"][0]["staged"] = ref(root, tampered_asset)
        tampered_asset_assets = write_json(
            root / "evidence/raw/tampered-asset-runtime-assets.json",
            tampered_asset_assets_value,
        )
        reject("m2_staged_asset_tamper", lambda: mutate_receipt(
            "m2", lambda value: value["runtime"].update({
                "runtime_assets": ref(root, tampered_asset_assets),
            })))

        def reject_tree_growth(name: str, path: Path, payload: bytes) -> None:
            write(path, payload)
            try:
                try:
                    verify_module.verify(root, manifest, now, 3600)
                except verify_module.VerificationError:
                    negative_checks.append(name)
                else:
                    raise AssertionError(f"unreceipted staged tree growth passed: {name}")
            finally:
                path.unlink()

        reject_tree_growth(
            "m2_unreceipted_datafile_tree_growth",
            root / "evidence/datafiles/unreceipted.bin", b"extra datafile\n",
        )
        reject_tree_growth(
            "m2_unreceipted_scripts_tree_growth",
            root / "evidence/scripts/unreceipted.py", b"# extra script\n",
        )

        leaf_target = write(
            root / "evidence/symlink-target/datafiles/fixture.dat",
            (root / "upstream/release/datafiles/fixture.dat").read_bytes(),
        )
        leaf_link = root / "evidence/symlink-leaf/datafiles/fixture.dat"
        leaf_link.parent.mkdir(parents=True)
        leaf_link.symlink_to(leaf_target)
        leaf_assets_value = json.loads(runtime_assets_path.read_text())
        leaf_assets_value["datafiles"][0]["staged"] = ref(root, leaf_link)
        leaf_assets = write_json(
            root / "evidence/raw/symlink-leaf-runtime-assets.json", leaf_assets_value
        )
        reject("m2_staged_leaf_symlink", lambda: mutate_receipt(
            "m2", lambda value: value["runtime"].update({
                "runtime_assets": ref(root, leaf_assets),
            })))

        intermediate_target = write(
            root / "evidence/intermediate-real/datafiles/fixture.dat",
            (root / "upstream/release/datafiles/fixture.dat").read_bytes(),
        )
        intermediate_link = root / "evidence/intermediate-link"
        intermediate_link.symlink_to(intermediate_target.parents[1])
        intermediate_staged = intermediate_link / "datafiles/fixture.dat"
        intermediate_assets_value = json.loads(runtime_assets_path.read_text())
        intermediate_assets_value["datafiles"][0]["staged"] = ref(
            root, intermediate_staged
        )
        intermediate_assets = write_json(
            root / "evidence/raw/symlink-intermediate-runtime-assets.json",
            intermediate_assets_value,
        )
        reject("m2_staged_intermediate_symlink", lambda: mutate_receipt(
            "m2", lambda value: value["runtime"].update({
                "runtime_assets": ref(root, intermediate_assets),
            })))

        def reject_missing_note() -> None:
            note_path = root / verify_module.M2_PASS_DELTA_NOTE_PATH
            payload = note_path.read_bytes()
            note_path.unlink()
            try:
                try:
                    verify_module.verify(root, manifest, now, 3600)
                except verify_module.VerificationError:
                    negative_checks.append("m2_pass_delta_note_missing")
                else:
                    raise AssertionError("missing pass-delta evidence note passed")
            finally:
                note_path.write_bytes(payload)

        reject_missing_note()

        def mutate_pass_delta_note() -> list[tuple[Path, bytes]]:
            note_path = root / verify_module.M2_PASS_DELTA_NOTE_PATH
            old_note = note_path.read_bytes()
            old_assets = runtime_assets_path.read_bytes()
            note_path.write_bytes(old_note.replace(b"Exact M2", b"Tampered M2", 1))
            assets_value = json.loads(old_assets)
            assets_value["pass_delta_note"] = ref(root, note_path)
            write_json(runtime_assets_path, assets_value)
            receipt_restorations = mutate_receipt(
                "m2", lambda value: value["runtime"].update({
                    "runtime_assets": ref(root, runtime_assets_path),
                })
            )
            return [
                (note_path, old_note), (runtime_assets_path, old_assets),
                *receipt_restorations,
            ]

        reject("m2_pass_delta_note_tamper", mutate_pass_delta_note)

        def coherent_m2_wasm_delta(name: str, payload: bytes, token: str) -> list[tuple[Path, bytes]]:
            normalized = write(root / f"evidence/raw/{token}.normalized", payload)
            raw = write(
                root / f"evidence/raw/{token}.raw",
                verify_module.M2_ALLOCATOR_LINE + verify_module.M2_WASM_BANNER_LINE + payload,
            )
            return mutate_receipt("m2", lambda value: value["rows"][name].update({
                "wasm_raw_log": ref(root, raw),
                "wasm_log": ref(root, normalized),
                "wasm_normalized_sha256": digest(normalized),
            }))

        def coherent_m2_pair_delta(
            name: str, native_payload: bytes, wasm_payload: bytes, token: str
        ) -> list[tuple[Path, bytes]]:
            native_normalized = write(
                root / f"evidence/raw/{token}.native.normalized", native_payload
            )
            wasm_normalized = write(
                root / f"evidence/raw/{token}.wasm.normalized", wasm_payload
            )
            native_raw = write(
                root / f"evidence/raw/{token}.native.raw",
                native_payload + verify_module.M2_ALLOCATOR_LINE
                + b"Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:31:22)\n",
            )
            wasm_raw = write(
                root / f"evidence/raw/{token}.wasm.raw",
                verify_module.M2_ALLOCATOR_LINE + verify_module.M2_WASM_BANNER_LINE
                + wasm_payload,
            )
            return mutate_receipt("m2", lambda value: value["rows"][name].update({
                "native_raw_log": ref(root, native_raw),
                "wasm_raw_log": ref(root, wasm_raw),
                "native_log": ref(root, native_normalized),
                "wasm_log": ref(root, wasm_normalized),
                "native_normalized_sha256": digest(native_normalized),
                "wasm_normalized_sha256": digest(wasm_normalized),
            }))

        baseline_m2 = json.loads((root / "evidence/receipts/m2.json").read_text())
        animation_row = baseline_m2["rows"]["bl_animation_action"]
        animation_wasm_log = (
            root / animation_row["wasm_log"]["path"]
        ).read_bytes()
        relocated_animation = animation_wasm_log.replace(
            verify_module.M2_ANIMATION_OBJECTDATA_WARNING, b"", 1
        ) + verify_module.M2_ANIMATION_OBJECTDATA_WARNING
        reject("m2_animation_delta_relocated", lambda: coherent_m2_wasm_delta(
            "bl_animation_action", relocated_animation, "animation-relocated"
        ))
        animation_native_log = (
            root / animation_row["native_log"]["path"]
        ).read_bytes()

        def relocate_library_phase(payload: bytes, *, wasm: bool) -> bytes:
            lines = payload.splitlines(keepends=True)
            start = lines.index(verify_module.M2_ANIMATION_TEMP_READ)
            layered_read = (
                verify_module.M2_ANIMATION_LAYERED_READ
                if wasm else verify_module.M2_ANIMATION_LAYERED_READ_BARE
            )
            end = lines.index(layered_read, start) + 1
            phase = lines[start:end]
            del lines[start:end]
            lines[1:1] = phase
            return b"".join(lines)

        relocated_native_phase = relocate_library_phase(animation_native_log, wasm=False)
        relocated_wasm_phase = relocate_library_phase(animation_wasm_log, wasm=True)
        reject("m2_animation_whole_phase_relocated", lambda: coherent_m2_pair_delta(
            "bl_animation_action", relocated_native_phase, relocated_wasm_phase,
            "animation-whole-phase-relocated",
        ))

        library_row = baseline_m2["rows"]["blendfile_library_overrides"]
        library_wasm_log = (root / library_row["wasm_log"]["path"]).read_bytes()
        changed_association = library_wasm_log.replace(
            verify_module.M2_LIBRARY_OVERRIDE_WASM_PHASE[1],
            verify_module.M2_LIBRARY_OVERRIDE_NATIVE_PHASE[1], 1,
        )
        reject("m2_library_delta_association_tamper", lambda: coherent_m2_wasm_delta(
            "blendfile_library_overrides", changed_association, "library-association"
        ))
        relocated_library = library_wasm_log.replace(
            b"".join(verify_module.M2_LIBRARY_OVERRIDE_WASM_PHASE),
            b"".join([
                verify_module.M2_LIBRARY_OVERRIDE_WASM_PHASE[0],
                verify_module.M2_LIBRARY_OVERRIDE_WASM_PHASE[2],
                verify_module.M2_LIBRARY_OVERRIDE_WASM_PHASE[1],
                *verify_module.M2_LIBRARY_OVERRIDE_WASM_PHASE[3:],
            ]),
            1,
        )
        reject("m2_library_delta_position_tamper", lambda: coherent_m2_wasm_delta(
            "blendfile_library_overrides", relocated_library, "library-position"
        ))

        library_native_log = (root / library_row["native_log"]["path"]).read_bytes()
        library_native_phase = b"".join(verify_module.M2_LIBRARY_OVERRIDE_NATIVE_PHASE)
        library_wasm_phase = b"".join(verify_module.M2_LIBRARY_OVERRIDE_WASM_PHASE)
        library_following = b"library-shared-following\n"

        def relocate_whole_library_phase(payload: bytes, phase: bytes) -> bytes:
            without = payload.replace(phase, b"", 1)
            return without.replace(library_following, library_following + phase, 1)

        reject("m2_library_delta_whole_phase_relocated", lambda: coherent_m2_pair_delta(
            "blendfile_library_overrides",
            relocate_whole_library_phase(library_native_log, library_native_phase),
            relocate_whole_library_phase(library_wasm_log, library_wasm_phase),
            "library-whole-phase-relocated",
        ))
        library_native_raw = (
            root / library_row["native_raw_log"]["path"]
        ).read_bytes()
        assert (
            library_native_raw.count(verify_module.M2_LIBRARY_OVERRIDE_SET_REVERSED)
            == verify_module.M2_LIBRARY_OVERRIDE_SET_OCCURRENCES
        )
        mixed_library_sets = write(
            root / "evidence/raw/m2-library-set-mixed.raw",
            library_native_raw.replace(
                verify_module.M2_LIBRARY_OVERRIDE_SET_REVERSED,
                verify_module.M2_LIBRARY_OVERRIDE_SET_CANONICAL,
                1,
            ),
        )
        reject("m2_library_set_mixed_order", lambda: mutate_receipt(
            "m2", lambda value: value["rows"]["blendfile_library_overrides"].update({
                "native_raw_log": ref(root, mixed_library_sets),
            })))
        extra_library_set = write(
            root / "evidence/raw/m2-library-set-extra.raw",
            library_native_raw + verify_module.M2_LIBRARY_OVERRIDE_SET_REVERSED + b"\n",
        )
        reject("m2_library_set_extra_occurrence", lambda: mutate_receipt(
            "m2", lambda value: value["rows"]["blendfile_library_overrides"].update({
                "native_raw_log": ref(root, extra_library_set),
            })))

        def mutate_pass_delta_status(deferral_id: str, status: str) -> list[tuple[Path, bytes]]:
            ledger_path = root / "ledger/deferred.json"
            old_ledger = ledger_path.read_bytes()
            value = json.loads(old_ledger)
            row = next(item for item in value["deferred"] if item["id"] == deferral_id)
            row["status"] = status
            write_json(ledger_path, value)
            receipt_restorations = mutate_receipt(
                "m2", lambda receipt: receipt.update({
                    "deferral_registry": ref(root, ledger_path),
                })
            )
            return [(ledger_path, old_ledger), *receipt_restorations]

        reject("m2_pass_delta_resolved_status", lambda: mutate_pass_delta_status(
            "wasm32-animation-action-objectdata", "resolved"
        ))
        reject("m2_pass_delta_wrong_goal_status", lambda: mutate_pass_delta_status(
            "os-shell-affordances", "deferred"
        ))
        blendfile_row = baseline_m2["rows"][verify_module.M2_SCRATCH_ROOT_SUITE]
        blendfile_native_raw = (
            root / blendfile_row["native_raw_log"]["path"]
        ).read_bytes()
        blendfile_native_scratch = (
            root.resolve() / "sandbox/final-m0-m3/evidence" / baseline_m2["run_label"] /
            "m2/scratch" / verify_module.M2_SCRATCH_ROOT_SUITE / "native"
        )
        blendfile_root_bytes = os.fsencode(blendfile_native_scratch)
        assert (
            blendfile_native_raw.count(blendfile_root_bytes)
            == verify_module.M2_SCRATCH_ROOT_OCCURRENCES
        )
        missing_scratch_occurrence = write(
            root / "evidence/raw/m2-blendfile-scratch-missing.raw",
            blendfile_native_raw.replace(
                blendfile_root_bytes, b"/wrong/scratch", 1
            ),
        )
        reject("m2_blendfile_scratch_occurrence_missing", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_SCRATCH_ROOT_SUITE].update({
                "native_raw_log": ref(root, missing_scratch_occurrence),
            })))
        extra_scratch_occurrence = write(
            root / "evidence/raw/m2-blendfile-scratch-extra.raw",
            blendfile_native_raw + blendfile_root_bytes + b"/extra.blend\n",
        )
        reject("m2_blendfile_scratch_occurrence_extra", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_SCRATCH_ROOT_SUITE].update({
                "native_raw_log": ref(root, extra_scratch_occurrence),
            })))
        arbitrary_scratch_path = write(
            root / "evidence/raw/m2-blendfile-arbitrary-path.raw",
            blendfile_native_raw + b"/arbitrary/unowned/path/visible.blend\n",
        )
        reject("m2_blendfile_arbitrary_path_remains_visible", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_SCRATCH_ROOT_SUITE].update({
                "native_raw_log": ref(root, arbitrary_scratch_path),
            })))
        reserved_scratch_token = write(
            root / "evidence/raw/m2-blendfile-scratch-reserved.raw",
            blendfile_native_raw + verify_module.M2_SCRATCH_ROOT_TOKEN + b"\n",
        )
        reject("m2_blendfile_reserved_scratch_token", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_SCRATCH_ROOT_SUITE].update({
                "native_raw_log": ref(root, reserved_scratch_token),
            })))
        animation_row = baseline_m2["rows"]["bl_animation_action"]
        animation_native_raw = (
            root / animation_row["native_raw_log"]["path"]
        ).read_bytes()
        animation_native_scratch = (
            root.resolve() / "sandbox/final-m0-m3/evidence" / baseline_m2["run_label"] /
            "m2/scratch/bl_animation_action/native"
        )
        animation_root_bytes = os.fsencode(animation_native_scratch)
        assert animation_native_raw.count(animation_root_bytes) == 1
        animation_missing_scratch = write(
            root / "evidence/raw/m2-animation-scratch-missing.raw",
            animation_native_raw.replace(animation_root_bytes, b"/wrong/scratch", 1),
        )
        reject("m2_animation_scratch_occurrence_missing", lambda: mutate_receipt(
            "m2", lambda value: value["rows"]["bl_animation_action"].update({
                "native_raw_log": ref(root, animation_missing_scratch),
            })))
        animation_extra_scratch = write(
            root / "evidence/raw/m2-animation-scratch-extra.raw",
            animation_native_raw + animation_root_bytes + b"/extra.blend\n",
        )
        reject("m2_animation_scratch_occurrence_extra", lambda: mutate_receipt(
            "m2", lambda value: value["rows"]["bl_animation_action"].update({
                "native_raw_log": ref(root, animation_extra_scratch),
            })))
        animation_reserved_scratch = write(
            root / "evidence/raw/m2-animation-scratch-reserved.raw",
            animation_native_raw + verify_module.M2_SCRATCH_ROOT_TOKEN + b"\n",
        )
        reject("m2_animation_reserved_scratch_token", lambda: mutate_receipt(
            "m2", lambda value: value["rows"]["bl_animation_action"].update({
                "native_raw_log": ref(root, animation_reserved_scratch),
            })))
        animation_arbitrary_path = write(
            root / "evidence/raw/m2-animation-arbitrary-path.raw",
            animation_native_raw + b"/arbitrary/unowned/path/visible.blend\n",
        )
        reject("m2_animation_arbitrary_path_remains_visible", lambda: mutate_receipt(
            "m2", lambda value: value["rows"]["bl_animation_action"].update({
                "native_raw_log": ref(root, animation_arbitrary_path),
            })))
        liblink_row = baseline_m2["rows"]["blendfile_liblink"]
        liblink_native_raw = (
            root / liblink_row["native_raw_log"]["path"]
        ).read_bytes()
        liblink_native_scratch = (
            root.resolve() / "sandbox/final-m0-m3/evidence" / baseline_m2["run_label"] /
            "m2/scratch/blendfile_liblink/native"
        )
        liblink_root_bytes = os.fsencode(liblink_native_scratch)
        assert (
            liblink_native_raw.count(liblink_root_bytes)
            == verify_module.M2_SCRATCH_ROOT_POLICIES["blendfile_liblink"]
        )
        liblink_missing_scratch = write(
            root / "evidence/raw/m2-liblink-scratch-missing.raw",
            liblink_native_raw.replace(liblink_root_bytes, b"/wrong/scratch", 1),
        )
        reject("m2_liblink_scratch_occurrence_missing", lambda: mutate_receipt(
            "m2", lambda value: value["rows"]["blendfile_liblink"].update({
                "native_raw_log": ref(root, liblink_missing_scratch),
            })))
        liblink_extra_scratch = write(
            root / "evidence/raw/m2-liblink-scratch-extra.raw",
            liblink_native_raw + liblink_root_bytes + b"/extra.blend\n",
        )
        reject("m2_liblink_scratch_occurrence_extra", lambda: mutate_receipt(
            "m2", lambda value: value["rows"]["blendfile_liblink"].update({
                "native_raw_log": ref(root, liblink_extra_scratch),
            })))
        liblink_reserved_scratch = write(
            root / "evidence/raw/m2-liblink-scratch-reserved.raw",
            liblink_native_raw + verify_module.M2_SCRATCH_ROOT_TOKEN + b"\n",
        )
        reject("m2_liblink_reserved_scratch_token", lambda: mutate_receipt(
            "m2", lambda value: value["rows"]["blendfile_liblink"].update({
                "native_raw_log": ref(root, liblink_reserved_scratch),
            })))
        liblink_arbitrary_path = write(
            root / "evidence/raw/m2-liblink-arbitrary-path.raw",
            liblink_native_raw + b"/arbitrary/unowned/path/visible.blend\n",
        )
        reject("m2_liblink_arbitrary_path_remains_visible", lambda: mutate_receipt(
            "m2", lambda value: value["rows"]["blendfile_liblink"].update({
                "native_raw_log": ref(root, liblink_arbitrary_path),
            })))
        hidden_failure_raw = write(
            root / "evidence/raw/m2-hidden-failure.raw",
            b"FAILED (failures=1)\n"
            + verify_module.M2_ALLOCATOR_LINE
            + b"Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:31:22)\n",
        )
        reject("m2_raw_failure_cannot_hide_behind_normalized_log", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_KEYS[0]].update({
                "native_raw_log": ref(root, hidden_failure_raw),
            })))
        multiprocessing_suffix_failure = write(
            root / "evidence/raw/m2-multiprocessing-suffix-failure.raw",
            verify_module.M2_ALLOCATOR_LINE + verify_module.M2_WASM_BANNER_LINE
            + b"Traceback (most recent call last):\n"
            + b"  File \"fixture.py\", line 1\n"
            + b"ModuleNotFoundError: No module named '_multiprocessing'; REAL FAILURE\n",
        )
        reject("m2_multiprocessing_prefix_cannot_hide_failure_suffix", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_KEYS[0]].update({
                "wasm_raw_log": ref(root, multiprocessing_suffix_failure),
            })))
        unknown_build_hash = write(
            root / "evidence/raw/m2-unknown-build-hash.raw",
            verify_module.M2_ALLOCATOR_LINE + verify_module.M2_WASM_BANNER_LINE
            + b"Blender 5.2.0 LTS (hash deadbeefdead built 2099-01-01 00:00:00)\n",
        )
        reject("m2_unknown_build_hash_remains_visible", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_KEYS[0]].update({
                "wasm_raw_log": ref(root, unknown_build_hash),
            })))
        misplaced_wasm_envelope = write(
            root / "evidence/raw/m2-nonadjacent-envelope.raw",
            verify_module.M2_ALLOCATOR_LINE + b"test output between launcher metadata\n"
            + verify_module.M2_WASM_BANNER_LINE,
        )
        reject("m2_nonadjacent_platform_envelope", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_KEYS[0]].update({
                "wasm_raw_log": ref(root, misplaced_wasm_envelope),
            })))
        cycles_notice = b'Add-on not loaded: "cycles", cause: No module named \'cycles\'\n'
        cycles_visible = write(
            root / "evidence/raw/m2-cycles-visible.raw",
            verify_module.M2_ALLOCATOR_LINE + verify_module.M2_WASM_BANNER_LINE
            + b"normalized script_pyapi_bpy_app\n" + cycles_notice,
        )
        reject("m2_cycles_startup_failure_remains_visible", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_KEYS[0]].update({
                "wasm_raw_log": ref(root, cycles_visible),
            })))
        scoped_denoiser = (
            b"00:01.002  bpy.rna          | WARNING current value '4' matches no enum in "
            b"'CyclesRenderSettings', '', 'denoiser'\n"
        )
        denoiser_wrong_suite = write(
            root / "evidence/raw/m2-denoiser-wrong-suite.raw",
            verify_module.M2_ALLOCATOR_LINE + verify_module.M2_WASM_BANNER_LINE
            + scoped_denoiser + b"normalized script_pyapi_bpy_app\n",
        )
        reject("m2_denoiser_warning_not_hidden_outside_exact_suite", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_KEYS[0]].update({
                "wasm_raw_log": ref(root, denoiser_wrong_suite),
            })))
        rna_missing_denoiser = write(
            root / "evidence/raw/m2-rna-missing-denoiser.raw",
            verify_module.M2_ALLOCATOR_LINE + verify_module.M2_WASM_BANNER_LINE
            + b"normalized bl_rna_accessors\n",
        )
        reject("m2_rna_requires_exact_denoiser_warning", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_NO_DENOISER_SUITE].update({
                "wasm_raw_log": ref(root, rna_missing_denoiser),
            })))
        rna_duplicate_denoiser = write(
            root / "evidence/raw/m2-rna-duplicate-denoiser.raw",
            verify_module.M2_ALLOCATOR_LINE + verify_module.M2_WASM_BANNER_LINE
            + scoped_denoiser + scoped_denoiser + b"normalized bl_rna_accessors\n",
        )
        reject("m2_rna_rejects_duplicate_denoiser_warning", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][verify_module.M2_NO_DENOISER_SUITE].update({
                "wasm_raw_log": ref(root, rna_duplicate_denoiser),
            })))
        broad_policy = write_json(root / "evidence/raw/m2-broad-normalization-policy.json", {
            "schema": 1,
            "pipeline": {
                "native": [
                    ref(root, root / "sandbox/final-m0-m3/run_m2.py"),
                    ref(root, root / "sandbox/tierb-prep/normalize.sed"),
                ],
                "wasm": [
                    ref(root, root / "sandbox/final-m0-m3/run_m2.py"),
                    ref(root, root / "sandbox/tierb-prep/normalize.sed"),
                    ref(root, root / "sandbox/tierb-prep/wasm-denoise.pl"),
                ],
            },
            "platform_envelope": {
                "native": "drop any native noise",
                "wasm": "drop any Wasm noise",
                "wasm_optional": ["drop warnings"],
            },
            "exit_code_primary": True,
            "normalized_bytes_exact_for_pass": True,
            "exact_replay_by_verifier": True,
        })
        reject("m2_broad_normalization_policy", lambda: mutate_receipt(
            "m2", lambda value: value.update({
                "normalization_policy": ref(root, broad_policy),
            })))
        def reject_deferral_registry(name: str, row: dict[str, Any]) -> None:
            path = root / "evidence/raw" / f"{name}.json"
            write_json(path, {"deferred": [row]})
            try:
                verify_module.active_deferrals(path)
            except verify_module.VerificationError:
                negative_checks.append(name)
            else:
                raise AssertionError(f"invalid detector-active registry passed: {name}")

        detector_fixture = {
            "id": verify_module.M2_DETECTOR_ACTIVE_ID,
            "status": verify_module.M2_DETECTOR_ACTIVE_STATUS,
            "evidence": "fixture detector evidence",
        }
        reject_deferral_registry(
            "m2_detector_unknown_status",
            dict(detector_fixture, status="detector-pending"),
        )
        reject_deferral_registry(
            "m2_detector_wrong_id",
            dict(detector_fixture, id="wasm32-other-collision"),
        )
        def make_m2_detector_wrong_suite(value: dict[str, Any]) -> None:
            row = value["rows"]["blendfile_io"]
            row.update({
                "wasm_exit": 1, "result": "DEFERRED",
                "deferral_ids": [verify_module.M2_DETECTOR_ACTIVE_ID],
                "deferral_records": [{
                    "id": verify_module.M2_DETECTOR_ACTIVE_ID,
                    "status": verify_module.M2_DETECTOR_ACTIVE_STATUS,
                    "evidence": (
                        f"fixture evidence for {verify_module.M2_DETECTOR_ACTIVE_ID}"
                    ),
                    "marker": verify_module.M2_DETECTOR_ACTIVE_MARKER,
                }],
            })
        reject("m2_detector_wrong_suite", lambda: mutate_receipt(
            "m2", make_m2_detector_wrong_suite))
        reject("m2_detector_stale_evidence", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][
                verify_module.M2_DETECTOR_ACTIVE_SUITE
            ]["deferral_records"][0].update({"evidence": "stale evidence"})))
        missing_detector_raw = write(
            root / "evidence/raw/m2-detector-missing-marker.raw", "unrelated failure\n"
        )
        reject("m2_detector_missing_marker", lambda: mutate_receipt(
            "m2", lambda value: value["rows"][
                verify_module.M2_DETECTOR_ACTIVE_SUITE
            ].update({"wasm_raw_log": ref(root, missing_detector_raw)})))
        wrong_detector_log = write(
            root / "evidence/raw/m2-detector-wrong-marker.normalized",
            verify_module.M2_DETECTOR_ACTIVE_MARKER.replace("ADR-004", "ADR-005") + "\n",
        )
        def make_m2_detector_wrong_marker(value: dict[str, Any]) -> None:
            row = value["rows"][verify_module.M2_DETECTOR_ACTIVE_SUITE]
            row.update({
                "wasm_log": ref(root, wrong_detector_log),
                "wasm_normalized_sha256": digest(wrong_detector_log),
            })
        reject("m2_detector_wrong_marker", lambda: mutate_receipt(
            "m2", make_m2_detector_wrong_marker))
        reject("m2_deps_missing_license_payload", lambda: mutate_receipt(
            "m2_deps", lambda value: value["dependencies"][0].update({"license_payloads": []})))
        reject("m2_deps_implicit_compatibility", lambda: mutate_receipt(
            "m2_deps", lambda value: value["dependencies"][0].update({"gpl_compatible": None})))
        reject("m2_deps_extra_unresolved_policy", lambda: mutate_receipt(
            "m2_deps", lambda value: value["unresolved_external_policy"].append({
                "name": value["dependencies"][0]["name"],
                "license": value["dependencies"][0]["license"],
                "reason": "invented", "license_payloads": value["dependencies"][0]["license_payloads"],
            })))
        reject("m2_deps_spec_keyset_tamper", lambda: mutate_dependency_spec(
            lambda value: value["dependencies"].pop(sorted(value["dependencies"])[0])))
        reject("m2_deps_spec_artifact_path_tamper", lambda: mutate_dependency_spec(
            lambda value: value["dependencies"][sorted(value["dependencies"])[0]]["artifacts"].append(
                "lib/wasm/lib/libfabricated.a")))
        reject("m2_deps_spec_license_path_tamper", lambda: mutate_dependency_spec(
            lambda value: value["dependencies"][sorted(value["dependencies"])[0]].update({
                "license_payloads": ["LICENSES/GPL-3.0-or-later.txt"]})))
        def make_m2_undeferred_failure(value: dict[str, Any]) -> None:
            row = value["rows"]["blendfile_io"]
            row.update({"wasm_exit": 1, "result": "DEFERRED"})
        reject("m2_undeferred_failure", lambda: mutate_receipt("m2", make_m2_undeferred_failure))
        reject("m3_not_197_pass", lambda: mutate_receipt(
            "m3", lambda value: value["gpu_tests"].update({"passed": 196, "failed": 1})))
        reject("m3_gpu_raw_log_missing", lambda: mutate_receipt(
            "m3", lambda value: value["gpu_tests"]["rows"][
                "GPUWebGPUTest.test_000"
            ].pop("raw_log")))
        def swap_m3_device_limit_refs(value: dict[str, Any]) -> None:
            sources = value["device_limit_sources"]
            sources["native_context"], sources["web_fallback"] = (
                sources["web_fallback"], sources["native_context"]
            )
        reject("m3_device_limit_source_ref_swap", lambda: mutate_receipt(
            "m3", swap_m3_device_limit_refs))
        def mutate_m3_cache_marker_source() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            source_path = root / receipt_value["cache_marker_source"]["path"]
            source_old = source_path.read_bytes()
            source_path.write_text(
                source_old.decode("utf-8").replace(
                    "{ return false; }", "{ return true; }", 1
                ),
                encoding="utf-8",
            )
            receipt_value["cache_marker_source"] = ref(root, source_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [
                (source_path, source_old),
                (receipt_path, receipt_old),
                (manifest, manifest_old),
            ]
        reject("m3_cache_marker_pre_activation_not_suppressed",
               mutate_m3_cache_marker_source)
        reject("m3_opensubdiv_tarball_md5_drift", lambda: mutate_receipt(
            "m3", lambda value: value["opensubdiv"].update({"tarball_md5": "0" * 32})))
        reject("m3_opensubdiv_archive_ref_swap", lambda: mutate_receipt(
            "m3", lambda value: value["opensubdiv"].update(
                {"gpu_archive": value["opensubdiv"]["cpu_archive"]}
            )))
        def stale_196_gpu_census() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            gpu = receipt_value["gpu_tests"]
            gpu_manifest_path = root / gpu["manifest"]["path"]
            gpu_manifest_old = gpu_manifest_path.read_bytes()
            raw_path = root / gpu["raw_result"]["path"]
            raw_old = raw_path.read_bytes()

            stale_name = gpu_manifest_old.decode("utf-8").splitlines()[-1]
            gpu_manifest_path.write_bytes(
                b"\n".join(gpu_manifest_old.splitlines()[:-1]) + b"\n"
            )
            gpu["manifest"] = ref(root, gpu_manifest_path)
            gpu.update({"total": 196, "passed": 196})
            gpu["rows"].pop(stale_name)

            raw_value = json.loads(raw_old)
            raw_value.update({
                "manifest_sha256": digest(gpu_manifest_path),
                "total": 196,
                "passed": 196,
            })
            write_json(raw_path, raw_value)
            gpu["raw_result"] = ref(root, raw_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [
                (gpu_manifest_path, gpu_manifest_old),
                (raw_path, raw_old),
                (receipt_path, receipt_old),
                (manifest, manifest_old),
            ]
        reject("m3_stale_196_census", stale_196_gpu_census)

        def mutate_m3_gpu_list(
            key: str, change: Callable[[str], str]
        ) -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            gpu = receipt_value["gpu_tests"]
            list_path = root / gpu[key]["path"]
            list_old = list_path.read_bytes()
            raw_path = root / gpu["raw_result"]["path"]
            raw_old = raw_path.read_bytes()
            write(list_path, change(list_old.decode("utf-8")))
            gpu[key] = ref(root, list_path)
            raw_value = json.loads(raw_old)
            raw_value[f"{key}_sha256"] = digest(list_path)
            write_json(raw_path, raw_value)
            gpu["raw_result"] = ref(root, raw_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [
                (list_path, list_old), (raw_path, raw_old),
                (receipt_path, receipt_old), (manifest, manifest_old),
            ]

        reject("m3_gpu_raw_list_unexpected_suite", lambda: mutate_m3_gpu_list(
            "list_stdout", lambda text: text + "OtherSuite.\n  hidden\n"
        ))
        reject("m3_gpu_raw_list_nonempty_stderr", lambda: mutate_m3_gpu_list(
            "list_stderr", lambda text: text + "fixture warning\n"
        ))

        def coherent_m3_gpu_identity_substitution() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            gpu = receipt_value["gpu_tests"]
            old_name = "GPUWebGPUTest.test_000"
            new_name = "GPUWebGPUTest.fabricated_000"
            paths = {
                "manifest": root / gpu["manifest"]["path"],
                "list_stdout": root / gpu["list_stdout"]["path"],
                "raw_result": root / gpu["raw_result"]["path"],
                "log": root / gpu["rows"][old_name]["raw_log"]["path"],
            }
            old = {key: path.read_bytes() for key, path in paths.items()}
            write(paths["manifest"], old["manifest"].decode().replace(old_name, new_name, 1))
            write(
                paths["list_stdout"],
                old["list_stdout"].decode().replace("  test_000\n", "  fabricated_000\n", 1),
            )
            write(paths["log"], old["log"].decode().replace(old_name, new_name))
            gpu["rows"][new_name] = gpu["rows"].pop(old_name)
            gpu["rows"][new_name]["raw_log"] = ref(root, paths["log"])
            gpu["manifest"] = ref(root, paths["manifest"])
            gpu["list_stdout"] = ref(root, paths["list_stdout"])
            raw_value = json.loads(old["raw_result"])
            raw_value["manifest_sha256"] = digest(paths["manifest"])
            raw_value["list_stdout_sha256"] = digest(paths["list_stdout"])
            write_json(paths["raw_result"], raw_value)
            gpu["raw_result"] = ref(root, paths["raw_result"])
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [
                *((paths[key], old[key]) for key in ("manifest", "list_stdout", "raw_result", "log")),
                (receipt_path, receipt_old), (manifest, manifest_old),
            ]
        reject("m3_gpu_canonical_identity_substitution",
               coherent_m3_gpu_identity_substitution)

        def mutate_m3_gpu_run_marker(marker: bytes) -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            gpu = receipt_value["gpu_tests"]
            name = "GPUWebGPUTest.test_000"
            log_path = root / gpu["rows"][name]["raw_log"]["path"]
            log_old = log_path.read_bytes()
            write(
                log_path,
                log_old + marker,
            )
            gpu["rows"][name]["raw_log"] = ref(root, log_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(log_path, log_old), (receipt_path, receipt_old), (manifest, manifest_old)]

        reject("m3_gpu_pass_with_uncaptured_device_error", lambda: mutate_m3_gpu_run_marker(
            b"[WebGPU] uncaptured device error (type 2): delayed pipeline failure\n"
        ))
        reject("m3_gpu_pass_with_memory_leak", lambda: mutate_m3_gpu_run_marker(
            b"Error: Not freed memory blocks: 1\n"
        ))
        def mutate_m3_gpu_run_suffix() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            gpu = receipt_value["gpu_tests"]
            name = "GPUWebGPUTest.test_000"
            log_path = root / gpu["rows"][name]["raw_log"]["path"]
            log_old = log_path.read_bytes()
            write(log_path, log_old.decode("utf-8").replace(name, name + "_SUFFIX"))
            gpu["rows"][name]["raw_log"] = ref(root, log_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(log_path, log_old), (receipt_path, receipt_old), (manifest, manifest_old)]
        reject("m3_gpu_raw_run_suffix_alias", mutate_m3_gpu_run_suffix)
        reject("m3_draw_webgpu_not_2_pass", lambda: mutate_receipt(
            "m3", lambda value: value["draw_webgpu_tests"].update(
                {"passed": 1, "failed": 1}
            )))

        def mutate_m3_draw_list(change: Callable[[str], str]) -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            draw = receipt_value["draw_webgpu_tests"]
            list_path = root / draw["list_stdout"]["path"]
            list_old = list_path.read_bytes()
            raw_path = root / draw["raw_result"]["path"]
            raw_old = raw_path.read_bytes()
            write(list_path, change(list_old.decode("utf-8")))
            draw["list_stdout"] = ref(root, list_path)
            raw_value = json.loads(raw_old)
            raw_value["list_stdout_sha256"] = digest(list_path)
            write_json(raw_path, raw_value)
            draw["raw_result"] = ref(root, raw_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [
                (list_path, list_old), (raw_path, raw_old),
                (receipt_path, receipt_old), (manifest, manifest_old),
            ]

        reject("m3_draw_webgpu_raw_list_stale_identity", lambda: mutate_m3_draw_list(
            lambda text: text.replace(
                "draw_debug_lifetime_rebind", "draw_debug_display_only", 1
            )))

        def mutate_m3_draw_run_marker(marker: bytes) -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            draw = receipt_value["draw_webgpu_tests"]
            name = verify_module.M3_DRAW_WEBGPU_TESTS[0]
            log_path = root / draw["rows"][name]["raw_log"]["path"]
            log_old = log_path.read_bytes()
            write(
                log_path,
                log_old + marker,
            )
            draw["rows"][name]["raw_log"] = ref(root, log_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(log_path, log_old), (receipt_path, receipt_old), (manifest, manifest_old)]

        reject("m3_draw_webgpu_raw_run_device_error", lambda: mutate_m3_draw_run_marker(
            b"[WebGPU] uncaptured device error (type 2): delayed draw failure\n"
        ))
        reject("m3_draw_webgpu_raw_run_memory_leak", lambda: mutate_m3_draw_run_marker(
            b"Error: Not freed memory blocks: 1\n"
        ))
        def mutate_m3_draw_run_suffix() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            draw = receipt_value["draw_webgpu_tests"]
            name = verify_module.M3_DRAW_WEBGPU_TESTS[0]
            log_path = root / draw["rows"][name]["raw_log"]["path"]
            log_old = log_path.read_bytes()
            write(log_path, log_old.decode("utf-8").replace(name, name + "_SUFFIX"))
            draw["rows"][name]["raw_log"] = ref(root, log_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(log_path, log_old), (receipt_path, receipt_old), (manifest, manifest_old)]
        reject("m3_draw_webgpu_raw_run_suffix_alias", mutate_m3_draw_run_suffix)

        def mutate_m3_opensubdiv_log(
            key: str, change: Callable[[str], str]
        ) -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            osd = receipt_value["opensubdiv"]
            proof_path = root / osd[key]["path"]
            proof_old = proof_path.read_bytes()
            write(proof_path, change(proof_old.decode("utf-8")))
            osd[key] = ref(root, proof_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(proof_path, proof_old), (receipt_path, receipt_old), (manifest, manifest_old)]

        reject("m3_opensubdiv_missing_glsl_member", lambda: mutate_m3_opensubdiv_log(
            "members", lambda text: text.replace("glslPatchShaderSource.cpp.o\n", "", 1)
        ))
        reject("m3_opensubdiv_gl_api_import", lambda: mutate_m3_opensubdiv_log(
            "undefined_symbols", lambda text: text + " U _glCreateShader\n"
        ))
        reject("m3_opensubdiv_smoke_missing_source_marker", lambda: mutate_m3_opensubdiv_log(
            "wasm_smoke", lambda text: text.replace("evaluate=1", "evaluate=0", 1)
        ))
        reject("m3_opensubdiv_live_proof_mismatch", lambda: mutate_m3_opensubdiv_log(
            "members", lambda text: text + "harmlessExtraObject.cpp.o\n"
        ))

        def mutate_m3_critical_after() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            after_path = root / receipt_value["critical_inputs"]["after"]["path"]
            after_old = after_path.read_bytes()
            write(
                after_path,
                after_old.decode("utf-8").replace("binary\t", "binary_changed\t", 1),
            )
            receipt_value["critical_inputs"]["after"] = ref(root, after_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [(after_path, after_old), (receipt_path, receipt_old), (manifest, manifest_old)]
        reject("m3_critical_input_before_after_mutation", mutate_m3_critical_after)

        def mutate_m3_osd_after_proof() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            archive_path = root / receipt_value["opensubdiv"]["gpu_archive"]["path"]
            archive_old = archive_path.read_bytes()
            after_path = root / receipt_value["critical_inputs"]["after"]["path"]
            after_old = after_path.read_bytes()
            write(archive_path, archive_old + b"post-proof-mutation")
            receipt_value["opensubdiv"]["gpu_archive"] = ref(root, archive_path)
            replacement = (
                f"opensubdiv_gpu_archive\t{verify_module.M3_OPENSUBDIV_GPU_ARCHIVE}\t"
                f"{archive_path.stat().st_size}\t{digest(archive_path)}"
            )
            after_lines = [
                replacement if line.startswith("opensubdiv_gpu_archive\t") else line
                for line in after_old.decode("utf-8").splitlines()
            ]
            write(after_path, "\n".join(after_lines) + "\n")
            receipt_value["critical_inputs"]["after"] = ref(root, after_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [
                (archive_path, archive_old), (after_path, after_old),
                (receipt_path, receipt_old), (manifest, manifest_old),
            ]
        reject("m3_opensubdiv_post_proof_input_mutation", mutate_m3_osd_after_proof)

        def coherent_m3_shader_identity_substitution() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            static = receipt_value["static_shaders"]
            old_name = "shader_0000"
            new_name = "fabricated_shader_identity"
            paths = {
                "manifest": root / static["manifest"]["path"],
                "cold": root / static["cold_log"]["path"],
                "warm": root / static["warm_log"]["path"],
                "raw_result": root / static["raw_result"]["path"],
            }
            old = {key: path.read_bytes() for key, path in paths.items()}
            for key in ("manifest", "cold", "warm"):
                write(paths[key], old[key].decode().replace(old_name, new_name))
            static["rows"][new_name] = static["rows"].pop(old_name)
            static["manifest"] = ref(root, paths["manifest"])
            static["cold_log"] = ref(root, paths["cold"])
            static["warm_log"] = ref(root, paths["warm"])
            raw_value = json.loads(old["raw_result"])
            raw_value["manifest_sha256"] = digest(paths["manifest"])
            write_json(paths["raw_result"], raw_value)
            static["raw_result"] = ref(root, paths["raw_result"])
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [
                *((paths[key], old[key]) for key in ("manifest", "cold", "warm", "raw_result")),
                (receipt_path, receipt_old), (manifest, manifest_old),
            ]
        reject("m3_static_canonical_identity_substitution",
               coherent_m3_shader_identity_substitution)
        def mutate_m3_static_log(
            log_key: str, change: Callable[[str], str]
        ) -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            log_path = root / receipt_value["static_shaders"][log_key]["path"]
            log_old = log_path.read_bytes()
            write(log_path, change(log_old.decode("utf-8")))
            receipt_value["static_shaders"][log_key] = ref(root, log_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [
                (log_path, log_old),
                (receipt_path, receipt_old),
                (manifest, manifest_old),
            ]

        reject("m3_raw_uncaptured_device_error", lambda: mutate_m3_static_log(
            "cold_log", lambda text: text.replace(
                verify_module.M3_CENSUS_END,
                "[WebGPU] uncaptured device error (type 2): invalid BGL\n"
                + verify_module.M3_CENSUS_END,
                1,
            )))
        reject("m3_raw_pre_census_device_error", lambda: mutate_m3_static_log(
            "cold_log", lambda text:
                "[WebGPU] uncaptured device error (type 2): fixture setup failure\n" + text
            ))
        reject("m3_raw_post_census_device_error", lambda: mutate_m3_static_log(
            "warm_log", lambda text: text
                + "[WebGPU] uncaptured device error (type 2): delayed pipeline failure\n"
            ))
        reject("m3_raw_post_census_memory_leak", lambda: mutate_m3_static_log(
            "warm_log", lambda text: text + "Error: Not freed memory blocks: 1\n"
            ))
        reject("m3_raw_cold_false_hit", lambda: mutate_m3_static_log(
            "cold_log", lambda text: text.replace(
                "BW_SHADER_CACHE_RESULT MISS",
                "BW_SHADER_CACHE_RESULT HIT",
                1,
            )))
        reject("m3_raw_stale_fullscreen_substitution", lambda: mutate_m3_static_log(
            "cold_log", lambda text: text.replace(
                verify_module.M3_REQUIRED_SHADER_ID,
                verify_module.M3_FORBIDDEN_SHADER_ID,
            )))
        def mutate_m3_raw_no_work() -> list[tuple[Path, bytes]]:
            manifest_old = manifest.read_bytes()
            manifest_value = json.loads(manifest_old)
            receipt_path = root / manifest_value["receipts"]["m3"]["path"]
            receipt_old = receipt_path.read_bytes()
            receipt_value = json.loads(receipt_old)
            raw_path = root / receipt_value["gpu_tests"]["raw_result"]["path"]
            raw_old = raw_path.read_bytes()
            raw_value = json.loads(raw_old)
            raw_value["no_work"]["target"] = "bin/tests/blender_test"
            raw_value["no_work"]["command"] = verify_module.ninja_locked_command(
                "-n", "bin/tests/blender_test"
            )
            write_json(raw_path, raw_value)
            receipt_value["gpu_tests"]["raw_result"] = ref(root, raw_path)
            write_json(receipt_path, receipt_value)
            manifest_value["receipts"]["m3"] = ref(root, receipt_path)
            write_json(manifest, manifest_value)
            return [
                (raw_path, raw_old),
                (receipt_path, receipt_old),
                (manifest, manifest_old),
            ]
        reject("m3_ninja_no_work_raw_mismatch", mutate_m3_raw_no_work)
        reject("m3_final_ninja_no_work_wrong_target", lambda: mutate_receipt(
            "m3", lambda value: value["final_no_work"].update({
                "target": "bin/tests/blender_test",
                "command": verify_module.ninja_locked_command(
                    "-n", "bin/tests/blender_test"
                ),
            })
        ))
        reject("m3_final_ninja_no_work_raw_bypass", lambda: mutate_receipt(
            "m3", lambda value: value["final_no_work"].update({
                "command": ["ninja", "-n", "blender_test"],
            })
        ))
        reject("alternate_unbound_label", lambda: mutate_receipt("m3", lambda value: value.update({"run_label": "alternate-r2"})))
        reject("unknown_receipt_field", lambda: mutate_receipt("m0", lambda value: value.update({"optional": True})))
        def unscoped_shader(value: dict[str, Any]) -> None:
            first = next(iter(value["static_shaders"]["rows"]))
            value["static_shaders"].update({"passed": 1002, "excluded": 1})
            value["static_shaders"]["rows"][first] = {"status": "EXCLUDED", "deferral_id": "not-registered", "feature_scope": "", "non_shipping": False}
        reject("unscoped_shader_exclusion", lambda: mutate_receipt("m3", unscoped_shader))
        def stale_manifest() -> list[tuple[Path, bytes]]:
            old = manifest.read_bytes()
            value = json.loads(old)
            value["created_utc"] = "2026-08-09T00:00:00Z"
            write_json(manifest, value)
            return [(manifest, old)]
        reject("stale_manifest", stale_manifest)
        def unknown_manifest() -> list[tuple[Path, bytes]]:
            old = manifest.read_bytes()
            value = json.loads(old)
            value["unknown"] = "ignored?"
            write_json(manifest, value)
            return [(manifest, old)]
        reject("unknown_manifest_field", unknown_manifest)
        def duplicate_manifest_field() -> list[tuple[Path, bytes]]:
            old = manifest.read_bytes()
            text = old.decode("utf-8").replace('  "schema": 1,', '  "schema": 1,\n  "schema": 1,', 1)
            write(manifest, text)
            return [(manifest, old)]
        reject("duplicate_manifest_field", duplicate_manifest_field)
        run_ok()

        print(json.dumps({"schema": 1, "verdict": "PASS", "positive": 2, "negative": len(negative_checks), "negative_checks": negative_checks}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
