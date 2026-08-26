#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed local verifier for the M8 technical launch contract.

This verifier deliberately distinguishes a locally testable technical candidate from
the complete LAUNCH.md gate.  Missing owner/legal/brand/deployment decisions remain
hard blockers in ``--launch`` mode; this script never fabricates them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SELF = ROOT / "sandbox/m8-launch-gate"
ART = SELF / "artifacts"
BUILD = ROOT / "build-wasm-windowed-opt/bin"
BUNDLE = ROOT / "sandbox/m8-staged-deploy/bundle-staged"
BROTLI_CODEC = ROOT / "sandbox/m8-staged-deploy/brotli_q11.mjs"
PUBLIC_MINIFIER = ROOT / "sandbox/m8-staged-deploy/public_shell_minify.mjs"
TERSER_BUNDLE = (
    ROOT / "tools/emsdk/upstream/emscripten/node_modules/terser/dist/bundle.min.js"
)
PINNED_NODE = Path(os.environ.get(
    "EMSDK_NODE", ROOT / "tools/emsdk/node/22.16.0_64bit/bin/node"))
REUSE_VERSION = "6.2.0"

DARWIN_RUNTIME_SIGNING = {
    "chrome": ("com.google.Chrome", "EQHXZ8M8AV", "Google Chrome.app", "Google Chrome"),
    "edge": ("com.microsoft.edgemac", "UBF8T346G9", "Microsoft Edge.app", "Microsoft Edge"),
}
LINUX_RUNTIME_CONTRACTS = {
    "chrome": {
        "executable": "/opt/google/chrome/chrome",
        "package": "google-chrome-stable",
        "source": "/etc/apt/sources.list.d/blender-web-google-chrome.list",
        "keyring": "/etc/apt/keyrings/blender-web-google-linux.gpg",
        "uri": "https://dl.google.com/linux/chrome/deb/",
        "suite": "stable",
        "component": "main",
        "fingerprint": "EB4C1BFD4F042F6DDDCCEC917721F63BD38B4796",
    },
    "edge": {
        "executable": "/opt/microsoft/msedge/msedge",
        "package": "microsoft-edge-stable",
        "source": "/etc/apt/sources.list.d/blender-web-microsoft-edge.list",
        "keyring": "/etc/apt/keyrings/blender-web-microsoft-edge.gpg",
        "uri": "https://packages.microsoft.com/repos/edge",
        "suite": "stable",
        "component": "main",
        "fingerprint": "BC528686B50D79E339D3721CEB3E94ADBE1229CF",
    },
}
RUNTIME_ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1"
RUNTIME_ADAPTER_FIELDS = {
    "contract", "status", "present", "platform", "powerPreference",
    "isFallbackAdapter", "info", "softwareMatches", "reason",
}
RUNTIME_ADAPTER_INFO_FIELDS = {"vendor", "architecture", "device", "description"}
SOFTWARE_ADAPTER_TOKENS = (
    "swiftshader", "llvmpipe", "lavapipe", "softpipe", "software rasterizer",
    "microsoft basic render", "warp",
)

GENERATED_INPUT_PREFIXES = (
    b"sandbox/m8-launch-gate/artifacts/",
    b"sandbox/m8-staged-deploy/artifacts/",
)
GENERATED_INPUT_PATHS = {
    b"ledger/results/m8.json",
    b"reports/dashboard.md",
}

SPLIT_MANIFEST = "blender_browser.split-build.json"
BUNDLE_SPLIT_MANIFEST = "bin/split-build.json"
STATIC_BUNDLE_FILES = (
    "index.html",
    "diagnostics-bootstrap.js",
    "boot-windowed.js",
    "file-bridge.js",
    "wgpu-preinit-worker.js",
    "stage1-loader.js",
    "service-worker-register.js",
    "service-worker.js",
    "_headers",
    "scenes/stress-mixed.blend",
    "scenes/stress-mixed.blend.license",
    "legal/LICENSE.txt",
    "legal/AUTHORS.txt",
    "legal/NOTICE.txt",
    "legal/THIRD-PARTY.md",
    "legal/PROVENANCE.md",
    "legal/LICENSES/Apache-2.0.txt",
    "legal/LICENSES/BSD-3-Clause.txt",
    "legal/LICENSES/CC0-1.0.txt",
    "legal/LICENSES/GPL-2.0-or-later.txt",
    "legal/LICENSES/GPL-3.0-or-later.txt",
    "legal/LICENSES/LicenseRef-OpenSubdiv-TOST-1.0.txt",
    "legal/THIRD_PARTY_NOTICES/OpenSubdiv-3.7.0-NOTICE.txt",
    "legal/OpenUSD-26.03/LICENSE.txt",
    "legal/OpenUSD-26.03/NOTICE.txt",
    "bin/blender_browser.js",
    "bin/blender_browser.data",
    "bin/stage1.data",
    "bin/stage1-manifest.json",
    BUNDLE_SPLIT_MANIFEST,
    "bin/blender_browser.js.br",
    "bin/blender_browser.data.br",
    "bin/stage1.data.br",
    "index.html.br",
    "diagnostics-bootstrap.js.br",
    "file-bridge.js.br",
    "boot-windowed.js.br",
    "stage1-loader.js.br",
    "service-worker-register.js.br",
    "service-worker.js.br",
)

BOOT_CRITICAL_PATHS = (
    "/index.html",
    "/diagnostics-bootstrap.js",
    "/file-bridge.js",
    "/boot-windowed.js",
    "/stage1-loader.js",
    "/service-worker-register.js",
    "/service-worker.js",
    "/bin/blender_browser.js",
    "/bin/blender_browser.data",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, object]:
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def expected_critical_paths(contract: dict[str, object]) -> list[str]:
    """Return every response fetched before the first semantic interaction."""
    return sorted((
        *BOOT_CRITICAL_PATHS,
        *(f"/bin/{row['filename']}" for row in contract["shipped_wasm"] if row["critical"]),
    ))


def canonical_artifact_digest(artifacts: dict[str, dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for name in sorted(artifacts):
        row = artifacts[name]
        digest.update(f"{name}\0{row['bytes']}\0{row['sha256']}\n".encode("utf-8"))
    return digest.hexdigest()


def _inventory_error(message: str) -> None:
    raise ValueError(f"invalid split-build inventory: {message}")


def artifact_contract(build: Path = BUILD) -> dict[str, object]:
    """Load and validate the finalizer-owned wasm inventory without guessing shards."""
    build = build.resolve(strict=True)
    path = build / SPLIT_MANIFEST
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _inventory_error(f"cannot read {SPLIT_MANIFEST}: {error}")
    if not isinstance(manifest, dict):
        _inventory_error("manifest is not an object")
    if manifest.get("schema") != 1:
        _inventory_error("schema must be 1")
    if (manifest.get("mode"), manifest.get("verdict")) != ("apply", "PASS"):
        _inventory_error("only a successful APPLY inventory may ship")
    if manifest.get("contract") != "shared-main-memory-profile-v1":
        _inventory_error("unexpected split contract")
    policy = manifest.get("inventory_policy")
    if not isinstance(policy, dict):
        _inventory_error("inventory_policy is absent")
    if policy.get("unlisted") != "reject" or policy.get("glob") != "blender_browser*.wasm*":
        _inventory_error("inventory policy does not reject the exact wasm glob")
    if policy.get("profile_export_absent") is not True:
        _inventory_error("profile export remains in shipping bytes")
    if policy.get("bundle_roles") != ["primary", "deferred"]:
        _inventory_error("bundle_roles must be primary+deferred")
    if policy.get("build_only_roles") != ["original_build_only"]:
        _inventory_error("build_only_roles must contain only original_build_only")
    rows = manifest.get("wasm_inventory")
    if not isinstance(rows, list) or len(rows) < 3:
        _inventory_error("wasm_inventory is missing/incomplete")
    inventory: list[dict[str, object]] = []
    all_roles = {"primary", "deferred", "original_build_only"}
    filename_pattern = re.compile(r"^blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm(?:\.orig)?$")
    for raw in rows:
        if not isinstance(raw, dict):
            _inventory_error("inventory row is not an object")
        row = dict(raw)
        filename = row.get("filename")
        role = row.get("role")
        if not isinstance(filename, str) or not filename_pattern.fullmatch(filename) or Path(filename).name != filename:
            _inventory_error(f"unsafe or unsupported wasm filename: {filename!r}")
        if role not in all_roles:
            _inventory_error(f"unknown role for {filename}: {role!r}")
        should_ship = role in {"primary", "deferred"}
        if row.get("shipped") is not should_ship or not isinstance(row.get("critical"), bool):
            _inventory_error(f"shipping/critical flags invalid for {filename}")
        phase = row.get("request_phase")
        if role == "primary" and (row.get("critical"), phase) != (True, "stage0"):
            _inventory_error("primary wasm must be critical stage0")
        if role == "deferred" and (row.get("critical"), phase) != (
                False, "after_semantic_first_interaction"):
            _inventory_error(f"{filename} is not classified after semantic first interaction")
        if role == "original_build_only" and (row.get("critical"), phase) != (False, "never"):
            _inventory_error(f"build-only wasm {filename} must never be requested")
        unresolved_path = build / filename
        expected_path = unresolved_path.resolve()
        if (unresolved_path.is_symlink() or expected_path.parent != build or
                Path(str(row.get("path", ""))).resolve() != expected_path or
                not expected_path.is_file()):
            _inventory_error(f"missing/noncanonical path for {filename}")
        if {"bytes": row.get("bytes"), "sha256": row.get("sha256")} != identity(expected_path):
            _inventory_error(f"identity mismatch for {filename}")
        inventory.append(row)
    names = [str(row["filename"]) for row in inventory]
    if len(names) != len(set(names)):
        _inventory_error("duplicate wasm inventory filenames")
    for role, count in (("primary", 1), ("original_build_only", 1)):
        if sum(row["role"] == role for row in inventory) != count:
            _inventory_error(f"inventory must contain exactly one {role}")
    if not any(row["role"] == "deferred" for row in inventory):
        _inventory_error("inventory must contain at least one deferred shard")
    actual_wasm = sorted(
        item.name for item in build.iterdir()
        if item.is_file() and re.fullmatch(r"blender_browser.*\.wasm.*", item.name)
    )
    if actual_wasm != sorted(names):
        _inventory_error(f"unlisted wasm files: actual={actual_wasm!r} inventory={sorted(names)!r}")
    js_actual = identity(build / "blender_browser.js")
    if not isinstance(manifest.get("js"), dict) or manifest["js"].get("sha256") != js_actual["sha256"]:
        _inventory_error("shipping glue does not match split manifest")
    shipped = sorted((row for row in inventory if row["shipped"]), key=lambda row: str(row["filename"]))
    build_files = ("blender_browser.js", "blender_browser.data", SPLIT_MANIFEST,
                   *(str(row["filename"]) for row in shipped))
    bundle_files = (*STATIC_BUNDLE_FILES,
                    *(value for row in shipped for value in (
                        f"bin/{row['filename']}", f"bin/{row['filename']}.br")))
    if len(build_files) != len(set(build_files)) or len(bundle_files) != len(set(bundle_files)):
        _inventory_error("duplicate generated artifact names")
    public_split_manifest = {
        "schema": 1,
        "contract": manifest["contract"],
        "source_manifest_sha256": sha256(path),
        "js_sha256": js_actual["sha256"],
        "inventory_policy": {"unlisted": "reject", "bundle_roles": ["primary", "deferred"]},
        "wasm_inventory": [
            {key: row[key] for key in (
                "filename", "role", "bytes", "sha256", "critical", "request_phase")}
            for row in shipped
        ],
    }
    return {"manifest": manifest, "inventory": inventory, "shipped_wasm": shipped,
            "build_files": build_files, "bundle_files": bundle_files,
            "public_split_manifest": public_split_manifest}


def build_files() -> tuple[str, ...]:
    return artifact_contract()["build_files"]  # type: ignore[return-value]


def bundle_files() -> tuple[str, ...]:
    return artifact_contract()["bundle_files"]  # type: ignore[return-value]


def validate_public_split_manifest() -> None:
    contract = artifact_contract()
    path = BUNDLE / BUNDLE_SPLIT_MANIFEST
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _inventory_error(f"cannot read public split manifest: {error}")
    if actual != contract["public_split_manifest"]:
        _inventory_error("public split manifest is stale, incomplete, or leaks non-public fields")


def current_bundle_digest() -> str:
    names = bundle_files()
    validate_public_split_manifest()
    expected = set(names)
    if not BUNDLE.is_dir():
        raise ValueError(f"exact deploy bundle directory is missing: {BUNDLE}")
    actual: set[str] = set()
    for path in BUNDLE.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"deploy bundle contains a symlink: {path.relative_to(BUNDLE)}")
        if path.is_file():
            actual.add(path.relative_to(BUNDLE).as_posix())
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"deploy bundle tree mismatch: missing={missing!r} extra={extra!r}")
    return canonical_artifact_digest({name: identity(BUNDLE / name) for name in names})


def repo_input_digest() -> str:
    # Bind both tracked source and untracked non-ignored source. During an
    # integration closeout many new legal/docs/verifier files exist before the
    # final commit; `git ls-files` alone would let those bytes change without
    # invalidating the compliance receipt.
    names = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True
    ).stdout.split(b"\0")
    digest = hashlib.sha256()
    for raw in sorted(name for name in names if name):
        if raw in GENERATED_INPUT_PATHS or raw.startswith(GENERATED_INPUT_PREFIXES):
            continue
        path = ROOT / raw.decode("utf-8", errors="surrogateescape")
        if path.is_symlink():
            payload = str(path.readlink()).encode("utf-8", errors="surrogateescape")
        elif path.is_file():
            payload = path.read_bytes()
        else:
            # Git can report an ignored-directory boundary during concurrent
            # generated-tree cleanup. It is not a source file and contributes no
            # licensing input.
            continue
        digest.update(raw + b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def git_history_digest() -> str:
    """Bind compliance to the complete reachable commit graph and metadata."""
    history = subprocess.run(
        ["git", "log", "--all", "--format=%H%x00%an%x00%ae%x00%aI%x00%P%x00%B%x00"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    return hashlib.sha256(history).hexdigest()


def load_json(path: Path, failures: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        failures.append(f"missing receipt: {path.relative_to(ROOT)}")
        return {}
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"unreadable receipt {path.relative_to(ROOT)}: {error}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"receipt is not an object: {path.relative_to(ROOT)}")
        return {}
    return value


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def check_early_diagnostics(value: object, label: str, failures: list[str]) -> None:
    require(isinstance(value, dict) and set(value) == {"schema", "preload", "snapshot"}
            and value.get("schema") == 1 and value.get("preload") is True
            and value.get("snapshot") == [],
            f"{label} early diagnostics are not exact schema-1/preloaded/empty", failures)


def _runtime_command(arguments: list[str], runner=subprocess.run) -> tuple[str, str]:
    try:
        result = runner(
            arguments,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"identity command is unavailable: {arguments[0]}: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"identity command failed: {' '.join(arguments)}" + (f": {detail}" if detail else ""))
    return result.stdout.strip(), result.stderr.strip()


def _exact_runtime_file(path_text: str, kind: str, executable: bool = False) -> dict[str, object]:
    path = Path(path_text)
    if not path.is_absolute() or os.path.normpath(path_text) != path_text:
        raise RuntimeError(f"{kind} path is not absolute and normalized")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError(f"{kind} path contains symlink component: {current}")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or path.resolve(strict=True) != path:
        raise RuntimeError(f"{kind} is not an exact nonempty regular file")
    if executable and not os.access(path, os.X_OK):
        raise RuntimeError(f"{kind} is not executable")
    return {"path": path_text, "bytes": info.st_size, "sha256": sha256(path)}


def _primary_fingerprints(colon_text: str) -> list[str]:
    fingerprints: list[str] = []
    waiting = False
    for line in colon_text.splitlines():
        fields = line.split(":")
        if fields[0] == "pub":
            waiting = True
        elif fields[0] == "fpr" and waiting:
            fingerprint = fields[9].upper() if len(fields) > 9 else ""
            if re.fullmatch(r"[0-9A-F]{40}", fingerprint) is None:
                raise RuntimeError("APT keyring primary fingerprint is noncanonical")
            fingerprints.append(fingerprint)
            waiting = False
    if waiting or not fingerprints or len(fingerprints) != len(set(fingerprints)):
        raise RuntimeError("APT keyring primary fingerprint inventory is absent or ambiguous")
    return sorted(fingerprints)


def _deb822_fields(text: str) -> dict[str, str]:
    wanted = {"Package", "Version", "Architecture", "Filename", "SHA256"}
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9-]*):\s*(.*)", line)
        if match is None or match.group(1) not in wanted:
            continue
        if match.group(1) in values:
            raise RuntimeError(f"APT package metadata duplicates {match.group(1)}")
        values[match.group(1)] = match.group(2).strip()
    if set(values) != wanted or any(not value for value in values.values()):
        raise RuntimeError("APT package metadata is incomplete")
    return values


def _debian_upstream_version(version: str) -> str:
    without_epoch = re.sub(r"^\d+:", "", version)
    upstream = without_epoch.rsplit("-", 1)[0] if "-" in without_epoch else without_epoch
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,4}", upstream) is None:
        raise RuntimeError(f"browser package version is noncanonical: {version}")
    return upstream


def _collect_linux_runtime_identity(channel: str, executable_text: str,
                                    runtime_version: str, runner=subprocess.run,
                                    contract_override: dict[str, str] | None = None
                                    ) -> dict[str, object]:
    contract = contract_override or LINUX_RUNTIME_CONTRACTS.get(channel)
    if contract is None:
        raise RuntimeError(f"unsupported Linux browser channel: {channel}")
    if executable_text != contract["executable"]:
        raise RuntimeError(f"Linux executable is not canonical: {executable_text}")
    executable = _exact_runtime_file(executable_text, "browser executable", executable=True)
    executable["requested_path"] = executable_text
    # Match the producer's exact key order only semantically; JSON object order is irrelevant.
    executable = {
        "requested_path": executable["requested_path"], "path": executable["path"],
        "bytes": executable["bytes"], "sha256": executable["sha256"],
    }
    source = _exact_runtime_file(contract["source"], "APT source")
    keyring = _exact_runtime_file(contract["keyring"], "APT keyring")
    active_lines = [line.strip() for line in Path(contract["source"]).read_text(
        encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
    expected_line = (
        f"deb [arch=amd64 signed-by={contract['keyring']}] {contract['uri']} "
        f"{contract['suite']} {contract['component']}")
    if active_lines != [expected_line]:
        raise RuntimeError("APT source is not the exact signed vendor stable repository")

    gpg, _ = _runtime_command([
        "gpg", "--batch", "--no-options", "--show-keys", "--with-colons", "--fingerprint",
        contract["keyring"],
    ], runner)
    fingerprints = _primary_fingerprints(gpg)
    if fingerprints != [contract["fingerprint"]]:
        raise RuntimeError("APT keyring does not contain only the accepted vendor primary key")

    readelf, _ = _runtime_command(["readelf", "-hW", executable_text], runner)
    elf_value = lambda name: (re.search(rf"(?m)^\s*{re.escape(name)}:\s*(.+)$", readelf)
                              .group(1).strip()
                              if re.search(rf"(?m)^\s*{re.escape(name)}:\s*(.+)$", readelf)
                              else None)
    elf = {
        "class": elf_value("Class"),
        "data": elf_value("Data"),
        "type": (elf_value("Type") or "").split()[0] or None,
        "machine": elf_value("Machine"),
    }
    if elf != {"class": "ELF64", "data": "2's complement, little endian", "type": "DYN",
               "machine": "Advanced Micro Devices X86-64"}:
        raise RuntimeError(f"browser executable is not the canonical amd64 PIE ELF: {elf}")

    owner, _ = _runtime_command(["dpkg-query", "-S", executable_text], runner)
    if re.fullmatch(rf"{re.escape(contract['package'])}(?::amd64)?: "
                    rf"{re.escape(executable_text)}", owner) is None:
        raise RuntimeError("browser ELF is not uniquely owned by the canonical package")
    installed_text, _ = _runtime_command([
        "dpkg-query", "-W",
        "-f=${db:Status-Abbrev}\\t${binary:Package}\\t${Version}\\t${Architecture}\\n",
        contract["package"],
    ], runner)
    installed = installed_text.split("\t")
    if len(installed) != 4 or installed[0] != "ii " or \
            installed[1] not in {contract["package"], f"{contract['package']}:amd64"} or \
            not installed[2] or installed[3] != "amd64":
        raise RuntimeError("canonical browser package is not exactly installed for amd64")
    package_version = installed[2]
    product_version = _debian_upstream_version(package_version)

    policy, _ = _runtime_command(["apt-cache", "policy", contract["package"]], runner)
    installed_match = re.search(r"(?m)^\s*Installed:\s*(\S+)\s*$", policy)
    candidate_match = re.search(r"(?m)^\s*Candidate:\s*(\S+)\s*$", policy)
    repository_marker = (
        f"{contract['uri'].rstrip('/')} {contract['suite']}/{contract['component']} "
        "amd64 Packages")
    if not installed_match or not candidate_match or \
            installed_match.group(1) != package_version or \
            candidate_match.group(1) != package_version or repository_marker not in policy:
        raise RuntimeError("installed browser is not the exact vendor-repository APT candidate")
    metadata_text, _ = _runtime_command([
        "apt-cache", "show", "--no-all-versions", f"{contract['package']}={package_version}"],
        runner)
    metadata = _deb822_fields(metadata_text)
    if metadata["Package"] != contract["package"] or metadata["Version"] != package_version or \
            metadata["Architecture"] != "amd64" or \
            re.fullmatch(r"[0-9a-fA-F]{64}", metadata["SHA256"]) is None or \
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+._/-]*\.deb", metadata["Filename"]) is None or \
            ".." in metadata["Filename"]:
        raise RuntimeError("APT candidate archive metadata is not exact")
    verified_out, verified_err = _runtime_command(
        ["dpkg", "--verify", contract["package"]], runner)
    if verified_out or verified_err:
        raise RuntimeError("dpkg reports modified browser package files")
    if runtime_version != product_version:
        raise RuntimeError("runtime version does not match the package upstream version")

    return {
        "schema": 2,
        "platform": "linux",
        "executable": executable,
        "product": {"channel": channel, "version": product_version,
                    "package_version": package_version},
        "elf": elf,
        "package": {
            "manager": "dpkg+apt", "name": contract["package"], "status": "ii",
            "version": package_version, "architecture": "amd64", "owner_verified": True,
            "files_verified": True,
            "source": {**source, "uri": contract["uri"], "suite": contract["suite"],
                       "component": contract["component"], "signed_by": contract["keyring"]},
            "keyring": {**keyring, "required_fingerprint": contract["fingerprint"],
                        "primary_fingerprints": fingerprints},
            "candidate": {"version": metadata["Version"], "filename": metadata["Filename"],
                          "sha256": metadata["SHA256"].lower()},
        },
        "runtime_version": runtime_version,
        "version_matches_product": True,
    }


def check_runtime_identity(identity_value: object, channel: str, executable_value: object,
                           version_value: object, label: str,
                           failures: list[str]) -> None:
    """Independently bind a receipt to current macOS notarization or Linux APT state."""
    if not isinstance(identity_value, dict):
        failures.append(f"{label} runtime identity is absent")
        return
    if identity_value.get("schema") == 2 and identity_value.get("platform") == "linux":
        try:
            require(isinstance(executable_value, str) and isinstance(version_value, str),
                    f"{label} Linux runtime path/version is absent", failures)
            if not isinstance(executable_value, str) or not isinstance(version_value, str):
                return
            current = _collect_linux_runtime_identity(channel, executable_value, version_value)
            require(identity_value == current,
                    f"{label} current Linux ELF/APT identity differs", failures)
        except (OSError, RuntimeError, UnicodeError) as error:
            failures.append(f"{label} Linux runtime identity verification failed: {error}")
        return
    require(set(identity_value) == {"schema", "executable", "app", "codesign",
                                   "notarization", "runtime_version",
                                   "version_matches_app"},
            f"{label} runtime identity keys are not exact", failures)
    executable = identity_value.get("executable", {})
    app = identity_value.get("app", {})
    signing = identity_value.get("codesign", {})
    notarization = identity_value.get("notarization", {})
    expected_signing = DARWIN_RUNTIME_SIGNING.get(channel)
    require(expected_signing is not None, f"{label} runtime channel is unsupported", failures)
    if expected_signing is None or not all(isinstance(value, dict) for value in (
            executable, app, signing, notarization)):
        failures.append(f"{label} runtime identity members are not objects")
        return
    require(set(executable) == {"requested_path", "path", "bytes", "sha256"}
            and set(app) == {"path", "version"}
            and set(signing) == {"deep_strict", "identifier", "team_identifier", "cdhash"}
            and set(notarization) == {"assessed", "accepted", "source", "origin"},
            f"{label} runtime identity nested keys are not exact", failures)
    requested = executable.get("requested_path")
    resolved = executable.get("path")
    app_text = app.get("path")
    require(isinstance(requested, str) and isinstance(resolved, str)
            and requested == resolved == executable_value
            and os.path.isabs(resolved) and os.path.normpath(resolved) == resolved,
            f"{label} runtime executable path is not exact", failures)
    if not isinstance(resolved, str) or not isinstance(app_text, str):
        return
    executable_path = Path(resolved)
    app_path = Path(app_text)
    require(app_path.name == expected_signing[2]
            and executable_path.parent.parent.parent == app_path
            and executable_path.name == expected_signing[3],
            f"{label} runtime executable is not the canonical branded app member", failures)
    try:
        require(not executable_path.is_symlink() and executable_path.is_file()
                and executable_path.resolve(strict=True) == executable_path
                and executable.get("bytes") == executable_path.stat().st_size
                and executable.get("sha256") == sha256(executable_path),
                f"{label} runtime executable bytes differ from current disk", failures)
        plist_path = app_path / "Contents/Info.plist"
        require(not app_path.is_symlink() and app_path.is_dir()
                and not plist_path.is_symlink() and plist_path.is_file(),
                f"{label} runtime app/plist is absent or indirect", failures)
        with plist_path.open("rb") as stream:
            current_version = str(plistlib.load(stream).get("CFBundleShortVersionString", ""))
        require(current_version == app.get("version") == identity_value.get("runtime_version")
                == version_value and identity_value.get("version_matches_app") is True,
                f"{label} runtime/app/receipt version binding differs", failures)

        verified = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_path)],
            capture_output=True, text=True)
        detail = subprocess.run(
            ["codesign", "-d", "--verbose=4", str(app_path)],
            capture_output=True, text=True)
        detail_text = detail.stderr + "\n" + detail.stdout
        field = lambda name: (re.search(rf"(?m)^{name}=(.+)$", detail_text).group(1).strip()
                              if re.search(rf"(?m)^{name}=(.+)$", detail_text) else None)
        current_identifier = field("Identifier")
        current_team = field("TeamIdentifier")
        current_cdhash = (field("CDHash") or "").lower()
        require(verified.returncode == 0 and detail.returncode == 0
                and signing == {"deep_strict": True, "identifier": current_identifier,
                                "team_identifier": current_team, "cdhash": current_cdhash}
                and (current_identifier, current_team) == expected_signing[:2]
                and re.fullmatch(r"[0-9a-f]{40,64}", current_cdhash) is not None,
                f"{label} current codesign identity/CDHash differs", failures)
        assessment = subprocess.run(
            ["spctl", "--assess", "--type", "execute", "--verbose=4", str(app_path)],
            capture_output=True, text=True)
        assessment_text = assessment.stderr + "\n" + assessment.stdout
        source_match = re.search(r"(?m)^source=(.+)$", assessment_text)
        origin_match = re.search(r"(?m)^origin=(.+)$", assessment_text)
        require(assessment.returncode == 0 and re.search(r"(?m): accepted$", assessment_text)
                and notarization == {"assessed": True, "accepted": True,
                    "source": source_match.group(1).strip() if source_match else None,
                    "origin": origin_match.group(1).strip() if origin_match else None}
                and notarization.get("source") == "Notarized Developer ID"
                and isinstance(notarization.get("origin"), str)
                and bool(notarization.get("origin")),
                f"{label} current notarization identity differs", failures)
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        failures.append(f"{label} runtime identity verification failed: {error}")


def check_runtime_adapter(adapter_value: object, label: str,
                          failures: list[str]) -> None:
    """Independently reject absent, masked, fallback, and software WebGPU adapters."""
    if not isinstance(adapter_value, dict):
        failures.append(f"{label} runtime adapter is absent")
        return
    require(set(adapter_value) == RUNTIME_ADAPTER_FIELDS,
            f"{label} runtime adapter keys are not exact", failures)
    info = adapter_value.get("info")
    require(isinstance(info, dict) and set(info) == RUNTIME_ADAPTER_INFO_FIELDS,
            f"{label} runtime adapter info keys are not exact", failures)
    if not isinstance(info, dict):
        return
    require(all(type(info.get(key)) is str for key in RUNTIME_ADAPTER_INFO_FIELDS),
            f"{label} runtime adapter info values are not strings", failures)
    identity_text = " ".join(
        info.get(key) if isinstance(info.get(key), str) else ""
        for key in ("vendor", "architecture", "device", "description")
    ).strip().lower()
    detail_identity = " ".join(
        info.get(key) if isinstance(info.get(key), str) else ""
        for key in ("architecture", "device", "description")
    ).strip()
    software_matches = [token for token in SOFTWARE_ADAPTER_TOKENS
                        if token in identity_text]
    if re.search(r"(^|[^a-z0-9])cpu([^a-z0-9]|$)", identity_text):
        software_matches.append("cpu")
    expected_platform = "darwin" if sys.platform == "darwin" else \
        "linux" if sys.platform.startswith("linux") else None
    require(adapter_value.get("contract") == RUNTIME_ADAPTER_CONTRACT,
            f"{label} runtime adapter contract differs", failures)
    require(adapter_value.get("status") == "ACCEPTED"
            and adapter_value.get("reason") == "accepted-hardware",
            f"{label} runtime adapter is not accepted hardware", failures)
    require(adapter_value.get("present") is True
            and adapter_value.get("powerPreference") == "high-performance",
            f"{label} runtime adapter presence/preference differs", failures)
    require(adapter_value.get("platform") == expected_platform,
            f"{label} runtime adapter platform differs from verifier host", failures)
    require(adapter_value.get("isFallbackAdapter") is False,
            f"{label} runtime adapter fallback status is not explicit false", failures)
    require(bool(identity_text) and bool(detail_identity),
            f"{label} runtime adapter identity is masked/incomplete", failures)
    require(not software_matches and adapter_value.get("softwareMatches") == [],
            f"{label} runtime adapter is software or its match inventory is forged", failures)


def expected_signing_projection(channel: str, runtime_identity: object) -> tuple[str, str] | None:
    if isinstance(runtime_identity, dict) and runtime_identity.get("schema") == 2 and \
            runtime_identity.get("platform") == "linux":
        contract = LINUX_RUNTIME_CONTRACTS.get(channel)
        return (contract["package"], contract["fingerprint"]) if contract else None
    contract = DARWIN_RUNTIME_SIGNING.get(channel)
    return contract[:2] if contract else None


def receipt_matches_files(
    receipt: dict,
    key: str,
    base: Path,
    names: tuple[str, ...],
    failures: list[str],
) -> None:
    recorded = receipt.get(key)
    require(isinstance(recorded, dict), f"receipt missing object {key}", failures)
    if not isinstance(recorded, dict):
        return
    require(set(recorded) == set(names),
            f"receipt {key} inventory differs from exact contract: "
            f"extra={sorted(set(recorded) - set(names))} "
            f"missing={sorted(set(names) - set(recorded))}", failures)
    for name in names:
        path = base / name
        require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}", failures)
        if not path.is_file():
            continue
        require(recorded.get(name) == identity(path), f"stale/mismatched identity: {name}", failures)


def check_headers(failures: list[str]) -> None:
    path = BUNDLE / "_headers"
    if not path.is_file():
        failures.append("staged bundle has no _headers")
        return
    staged_tools = str(ROOT / "sandbox/m8-staged-deploy")
    if staged_tools not in sys.path:
        sys.path.insert(0, staged_tools)
    from transport_contract import TransportContractError, validate_headers
    try:
        validate_headers(path)
    except TransportContractError as error:
        failures.append(str(error))


def check_local_only(failures: list[str]) -> None:
    # Executable bundle resources must be same-origin.  Comments may cite standards,
    # so check HTML URL-bearing attributes and live fetch/import/Worker calls rather
    # than banning documentation URLs in comments.
    html = BUNDLE / "index.html"
    if html.is_file():
        source = html.read_text(encoding="utf-8")
        remote = re.findall(r"(?:src|href)\s*=\s*['\"]https?://[^'\"]+", source, re.I)
        require(not remote, "bundle HTML loads cross-origin resources: " + ", ".join(remote), failures)
        scripts = re.findall(r"<script\b[^>]*\bsrc=['\"]([^'\"]+)['\"][^>]*>", source, re.I)
        require(bool(scripts) and scripts[0] == "/diagnostics-bootstrap.js",
                "diagnostics bootstrap is not the first executable bundle script", failures)
    diagnostics = BUNDLE / "diagnostics-bootstrap.js"
    if diagnostics.is_file():
        source = (ROOT / "platform_web/shell/diagnostics-bootstrap.js").read_text(
            encoding="utf-8")
        require("installedBeforeProductScripts: true" in source
                and 'window.addEventListener("error"' in source
                and 'window.addEventListener("unhandledrejection"' in source,
                "early diagnostics bootstrap contract is incomplete", failures)
    call_re = re.compile(r"(?:fetch|importScripts|new\s+Worker)\s*\(\s*['\"]https?://", re.I)
    for name in bundle_files():
        path = BUNDLE / name
        if path.suffix not in {".js", ".html"} or not path.is_file():
            continue
        require(call_re.search(path.read_text(encoding="utf-8")) is None,
                f"cross-origin runtime fetch in {name}", failures)


def check_exact_bundle_tree(failures: list[str]) -> None:
    if not BUNDLE.is_dir():
        failures.append("staged deploy tree is missing")
        return
    actual = {
        str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    expected = set(bundle_files())
    require(actual == expected,
            "staged deploy tree differs from allowlist: "
            f"extra={sorted(actual - expected)} missing={sorted(expected - actual)}", failures)
    for path in BUNDLE.rglob("*"):
        require(not path.is_symlink(),
                f"public deploy tree contains symlink: {path.relative_to(BUNDLE)}", failures)
    for name in sorted(value for value in expected if value.endswith(".br")):
        compressed = BUNDLE / name
        raw = BUNDLE / name[:-3]
        if not compressed.is_file() or not raw.is_file():
            continue
        try:
            proc = subprocess.Popen(
                [str(PINNED_NODE), str(BROTLI_CODEC), "decode-stdout", str(compressed)],
                stdout=subprocess.PIPE)
        except OSError as error:
            failures.append(f"cannot execute deterministic Brotli decoder: {error}")
            continue
        assert proc.stdout is not None
        digest = hashlib.sha256()
        for chunk in iter(lambda: proc.stdout.read(1024 * 1024), b""):
            digest.update(chunk)
        require(proc.wait() == 0 and digest.hexdigest() == sha256(raw),
                f"Brotli sibling does not decode to raw asset: {name}", failures)


def check_assembler_provenance(failures: list[str]) -> None:
    """Re-derive stage_pack outputs instead of trusting independent end hashes."""
    staged_tools = str(ROOT / "sandbox/m8-staged-deploy")
    if staged_tools not in sys.path:
        sys.path.insert(0, staged_tools)
    try:
        import stage_provenance
        contract = artifact_contract()
        proof, provenance_failures = stage_provenance.verify_full(
            ROOT, BUILD, BUNDLE, list(contract["shipped_wasm"]),
            contract["public_split_manifest"])
    except Exception as error:
        failures.append(
            f"stage provenance verifier exception: {type(error).__name__}: {error}")
        return
    failures.extend(provenance_failures)
    require(proof.get("schema") == 1 and proof.get("mode") == "defer-datafiles"
            and proof.get("full_stage") is True,
            "stage provenance proof is missing or has the wrong mode", failures)
    require(proof.get("producer") == {
        "path": "sandbox/m8-staged-deploy/stage_pack.py",
        **identity(ROOT / "sandbox/m8-staged-deploy/stage_pack.py"),
    }, "stage provenance did not use the canonical current stage_pack.py", failures)
    require(proof.get("brotli") == {
        "path": "sandbox/m8-staged-deploy/brotli_q11.mjs",
        **identity(BROTLI_CODEC),
        "node_version": "v22.16.0",
        "quality": 11,
        "lgwin": 24,
    }, "stage provenance did not use deterministic Brotli q11/lgwin=24", failures)
    require(proof.get("public_shell_minifier") == {
        "path": "sandbox/m8-staged-deploy/public_shell_minify.mjs",
        **identity(PUBLIC_MINIFIER),
        "node_version": "v22.16.0",
        "terser_version": "5.39.0",
        "terser_bundle": identity(TERSER_BUNDLE),
        "compress_passes": 2,
    }, "stage provenance did not use the pinned deterministic public-shell minifier",
            failures)

    expected_public = json.dumps(
        contract["public_split_manifest"], indent=2, sort_keys=True) + "\n"
    public_path = BUNDLE / BUNDLE_SPLIT_MANIFEST
    require(public_path.is_file() and
            public_path.read_text(encoding="utf-8") == expected_public,
            "public split receipt is not the deterministic source-manifest projection", failures)
    for row in contract["shipped_wasm"]:
        name = str(row["filename"])
        source = BUILD / name
        staged = BUNDLE / "bin" / name
        require(source.is_file() and staged.is_file() and
                identity(source) == identity(staged),
                f"shipping Wasm is not an exact source-build copy: {name}", failures)


def check_service_worker_contract(failures: list[str]) -> None:
    path = BUNDLE / "service-worker.js"
    if not path.is_file():
        failures.append("staged deploy tree has no generated service worker")
        return
    source = path.read_text(encoding="utf-8")
    require("__BW_" not in source, "service-worker template tokens remain", failures)
    register_path = BUNDLE / "service-worker-register.js"
    register_source = register_path.read_text(encoding="utf-8") if register_path.is_file() else ""
    require("__BW_" not in register_source,
            "service-worker registration template token remains", failures)
    contract = artifact_contract()
    deferred = {
        f"/bin/{row['filename']}": f"/bin/{row['filename']}?sha256={row['sha256']}"
        for row in contract["shipped_wasm"] if row["role"] == "deferred"
    }
    expected_precache = ["/"] + sorted([
        deferred.get(f"/{name}", f"/{name}") for name in STATIC_BUNDLE_FILES
        if name not in {"_headers", "service-worker.js"} and not name.endswith(".br")
    ] + list(deferred.values()) + [
        f"/bin/{row['filename']}" for row in contract["shipped_wasm"]
        if row["role"] != "deferred"
    ])
    expected_cache_first = [
        url for url in expected_precache if url != "/service-worker-register.js"
    ]
    expected_digests: dict[str, str] = {}
    for name in STATIC_BUNDLE_FILES:
        if name in {"_headers", "service-worker.js"} or name.endswith(".br"):
            continue
        url = deferred.get(f"/{name}", f"/{name}")
        expected_digests[url] = sha256(BUNDLE / name)
    for row in contract["shipped_wasm"]:
        name = f"bin/{row['filename']}"
        url = deferred.get(f"/{name}", f"/{name}")
        expected_digests[url] = sha256(BUNDLE / name)
    expected_digests["/"] = expected_digests["/index.html"]

    def parse_json_constant(name: str) -> object:
        match = re.search(rf"(?m)^const {name} = (.+);$", source)
        if match is None:
            raise ValueError(f"generated service worker has no exact {name} constant")
        return json.loads(match.group(1))

    try:
        actual_precache = parse_json_constant("PRECACHE_URLS")
        cache_first_text = re.search(
            r"(?m)^const CACHE_FIRST_URLS = new Set\((.+)\);$", source)
        if cache_first_text is None:
            raise ValueError("generated service worker has no exact CACHE_FIRST_URLS constant")
        actual_cache_first = json.loads(cache_first_text.group(1))
        cache_sha_text = re.search(
            r"(?m)^const CACHE_SHA256 = new Map\((.+)\);$", source)
        if cache_sha_text is None:
            raise ValueError("generated service worker has no exact CACHE_SHA256 constant")
        actual_digests = dict(json.loads(cache_sha_text.group(1)))
    except (ValueError, json.JSONDecodeError) as error:
        failures.append(str(error))
        return
    require(actual_precache == expected_precache,
            "service-worker precache inventory differs from exact bundle", failures)
    require(actual_cache_first == expected_cache_first,
            "service-worker cache-first inventory differs from exact update-safe policy", failures)
    require("/service-worker-register.js" in actual_precache and
            "/service-worker-register.js" not in actual_cache_first,
            "registration control resource is not precached/network-first", failures)
    require(source.count('return await fetchCurrent(request);') == 1 and
            'fetch(request, {cache: "no-cache"})' in source and
            'return await fetch(request);' not in source,
            "registration control resource can reuse the browser HTTP cache", failures)
    require(actual_digests == expected_digests,
            "service-worker cache digest inventory differs from exact raw assets", failures)
    require('CACHE_FIRST_URLS.has(logicalKey)' in source,
            "service-worker does not apply cache-first routing", failures)
    require('const logicalKey = url.pathname + url.search;' in source,
            "service-worker cache-first key drops the content-address query", failures)
    require('crypto.subtle.digest("SHA-256", bytes)' in source,
            "service-worker does not verify cached response bodies", failures)
    require('return await verifiedResponse(request, cached);' in source and
            'verifiedCacheKeys' not in source,
            "service-worker can return a cached body without re-verifying it", failures)
    require('const cache = await caches.open(CACHE_NAME);' in source and
            'await caches.match(request)' not in source,
            "service-worker fallback can escape the exact versioned cache", failures)
    activate_start = source.find('self.addEventListener("activate"')
    precache_start = source.find('async function precache')
    fetch_start = source.find('self.addEventListener("fetch"')
    claim_pos = source.find('await self.clients.claim();')
    enumerate_caches_pos = source.find('const keys = await caches.keys();')
    require(activate_start >= 0 and precache_start >= 0 and fetch_start >= 0 and
            precache_start < claim_pos < enumerate_caches_pos < fetch_start,
            "service-worker claim/old-cache cleanup order is not transactional", failures)

    version_match = re.search(r'(?m)^const CACHE_VERSION = "([0-9a-f]{20})";$', source)
    require(version_match is not None, "service-worker cache version is not 20-hex", failures)
    if version_match is not None:
        rows = []
        for name in bundle_files():
            if name in {"service-worker.js", "service-worker-register.js"}:
                continue
            rows.append((name, sha256(BUNDLE / name)))
        for template_name in ("service-worker.js", "service-worker-register.js"):
            template = ROOT / "sandbox/m8-staged-deploy" / template_name
            rows.append((f"{template_name}.template", sha256(template)))
        payload = "".join(
            f"{digest}  {name}\n" for name, digest in sorted(rows)
        ).encode("utf-8")
        expected_version = hashlib.sha256(payload).hexdigest()[:20]
        require(version_match.group(1) == expected_version,
                "service-worker cache version does not bind exact raw+Brotli tree", failures)
        expected_literal = (
            f'const EXPECTED_CACHE_VERSION = "{expected_version}";')
        require(expected_literal in register_source,
                "registration does not bind the exact generated worker version", failures)
        for marker in (
            "active = registered.active",
            "currentIdentity.version === EXPECTED_CACHE_VERSION",
            "event.source !== exactWorker",
            "worker.postMessage({type: \"BW_PRECACHE\"})",
            "navigator.serviceWorker.controller !== worker",
        ):
            require(marker in register_source,
                    f"registration lacks exact-controller guard: {marker}", failures)
        update_fixture = ROOT / "sandbox/m8-staged-deploy/verify_update_transition.mjs"
        fixture = subprocess.run(
            ["node", str(update_fixture)], cwd=ROOT, capture_output=True, text=True)
        require(fixture.returncode == 0 and
                "M8_SW_UPDATE_TRANSITION_SELFCHECK_PASS" in fixture.stdout,
                "two-version service-worker transition selfcheck failed: " +
                (fixture.stderr or fixture.stdout).strip(), failures)


def check_staged(receipt: dict, failures: list[str]) -> None:
    validate_public_split_manifest()
    require(receipt.get("schema") == 1, "staged receipt schema != 1", failures)
    require(receipt.get("verdict") == "PASS", "staged receipt verdict is not PASS", failures)
    require(receipt.get("source_runtime_verdict") == "PASS",
            "raw staged runtime verdict is not PASS", failures)
    require(receipt.get("source_runtime_failures") == [],
            "raw staged runtime reported failures", failures)
    receipt_matches_files(receipt, "source_artifacts", BUILD, build_files(), failures)
    receipt_matches_files(receipt, "bundle_artifacts", BUNDLE, bundle_files(), failures)
    check_assembler_provenance(failures)
    runtime_proofs = receipt.get("runtime_proofs", {})
    require(isinstance(runtime_proofs, dict) and set(runtime_proofs) == {
        "staged", "performance"}, "staged receipt runtime proof set is not exact", failures)
    if isinstance(runtime_proofs, dict):
        staged_runtime = runtime_proofs.get("staged", {})
        performance_runtime = runtime_proofs.get("performance", {})
        require(isinstance(staged_runtime, dict) and set(staged_runtime) == {
            "browser", "early_diagnostics"}, "staged runtime proof keys are not exact", failures)
        require(isinstance(performance_runtime, dict) and set(performance_runtime) == {
            "browser", "run_count", "early_diagnostics"},
            "performance runtime proof keys are not exact", failures)
        if isinstance(staged_runtime, dict):
            browser = staged_runtime.get("browser", {})
            if isinstance(browser, dict):
                require(browser.get("engine") == "chrome",
                        "staged runtime is not branded Chrome", failures)
                check_runtime_identity(browser.get("runtime_identity"), "chrome",
                                       browser.get("executable"), browser.get("version"),
                                       "staged", failures)
                check_runtime_adapter(browser.get("runtime_adapter"), "staged", failures)
            diagnostics = staged_runtime.get("early_diagnostics", {})
            require(isinstance(diagnostics, dict) and set(diagnostics) == {
                "cold_online", "online_warm", "offline_cold"},
                "staged early-diagnostics scenario set is not exact", failures)
            if isinstance(diagnostics, dict):
                for name in ("cold_online", "online_warm", "offline_cold"):
                    check_early_diagnostics(diagnostics.get(name), f"staged {name}", failures)
        if isinstance(performance_runtime, dict):
            browser = performance_runtime.get("browser", {})
            if isinstance(browser, dict):
                require(browser.get("channel") == "chrome",
                        "performance runtime is not branded Chrome", failures)
                check_runtime_identity(browser.get("runtime_identity"), "chrome",
                                       browser.get("executable"), browser.get("version"),
                                       "performance", failures)
                check_runtime_adapter(browser.get("runtime_adapter"), "performance", failures)
            diagnostics = performance_runtime.get("early_diagnostics")
            require(isinstance(diagnostics, list)
                    and isinstance(performance_runtime.get("run_count"), int)
                    and performance_runtime.get("run_count") >= 3
                    and len(diagnostics) == performance_runtime.get("run_count"),
                    "performance early-diagnostics runs are absent", failures)
            if isinstance(diagnostics, list):
                for index, value in enumerate(diagnostics, 1):
                    check_early_diagnostics(value, f"performance run {index}", failures)
        if isinstance(staged_runtime, dict) and isinstance(performance_runtime, dict):
            require(staged_runtime.get("browser", {}).get("runtime_identity") ==
                    performance_runtime.get("browser", {}).get("runtime_identity"),
                    "staged/performance Chrome runtime identities differ", failures)
            require(staged_runtime.get("browser", {}).get("runtime_adapter") ==
                    performance_runtime.get("browser", {}).get("runtime_adapter"),
                    "staged/performance WebGPU adapters differ", failures)
    bundle_digest = current_bundle_digest()
    require(receipt.get("served_bundle_sha256") == bundle_digest,
            "staged runtime was not served from the exact current bundle", failures)
    check_headers(failures)
    check_local_only(failures)
    check_exact_bundle_tree(failures)
    check_service_worker_contract(failures)

    proof = receipt.get("proof", {})
    require(proof.get("cross_origin_isolated") is True, "no COOP/COEP runtime proof", failures)
    require(proof.get("shared_array_buffer") is True, "no SharedArrayBuffer runtime proof", failures)
    require(proof.get("stage0_boot") is True, "stage-0 boot proof missing", failures)
    require(proof.get("stage0_first_pixels") is True, "stage 0 does not reach product pixels", failures)
    require(isinstance(proof.get("stage0_first_pixels_ms"), (int, float)) and
            proof.get("stage0_first_pixels_ms", 999999) <= 8000,
            f"stage-0 product pixels exceed 8s: {proof.get('stage0_first_pixels_ms')!r}", failures)
    require(proof.get("first_pixels_present") is True, "stage-0 displayed-product pixel proof missing", failures)
    require(proof.get("interactive_viewport_under_8s") is True,
            f"interactive viewport exceeds 8s: {proof.get('interactive_viewport_ms')!r}", failures)
    require(proof.get("stage1_byte_exact") is True, "stage-1 byte-exact proof missing", failures)
    require(proof.get("stage1_complete") is True,
            "stage-1 did not install every deferred byte/file cleanly", failures)
    require(proof.get("progress_phases_visible") is True, "visible phase/MB progress proof missing", failures)
    require(proof.get("service_worker_complete") is True, "service-worker cache proof missing", failures)
    require(proof.get("service_worker_inventory_exact") is True,
            "service-worker cache does not exactly cover shipped raw assets", failures)
    require(proof.get("trusted_semantic_interaction") is True,
            "trusted semantic interaction proof missing", failures)
    require(proof.get("deferred_after_trusted_interaction_exactly_once") is True,
            "deferred shard was not requested exactly once after trusted semantic input", failures)
    require(proof.get("two_phase_resumed_state_change") is True,
            "PARK/PREPARED/APPLY/PAGE_READY/RESUMED state-change proof missing", failures)
    require(proof.get("online_warm_deferred_zero_origin") is True,
            "online warm deferred shard made an origin request", failures)
    require(proof.get("online_warm_deferred_from_service_worker") is True,
            "online warm deferred shard was not served by the active service worker", failures)
    require(proof.get("offline_cold_semantic_deferred") is True,
            "offline cold semantic/deferred lifecycle proof missing", failures)
    require(proof.get("offline_reload_wm_main") is True, "real offline WM_main reload proof missing", failures)
    require(proof.get("external_request_count") == 0, "runtime made external requests", failures)
    require(proof.get("native_proof_visible") is True, "visible no-server/no-streaming proof missing", failures)
    require(proof.get("desktop_limit_visible") is True, "visible desktop/browser limitation missing", failures)
    require(proof.get("trademark_disclaimer_visible") is True,
            "visible trademark/non-endorsement disclaimer missing", failures)
    require(proof.get("legal_notices_visible") is True,
            "visible same-origin licenses/notices link missing", failures)
    require(proof.get("query_python_disabled") is True, "public ?pyexpr execution hook is enabled", failures)
    require(proof.get("query_args_disabled") is True, "public ?args argv hook is enabled", failures)
    require(proof.get("query_dev_controls_disabled") is True,
            "public gate/keepalive query diagnostics are enabled", failures)
    require(proof.get("gpu_error_count") == 0, "staged runtime recorded GPU errors", failures)
    require(proof.get("page_error_count") == 0, "staged runtime recorded page errors/crashes", failures)

    runtime_evidence = receipt.get("runtime_evidence", {})
    require(isinstance(runtime_evidence, dict), "staged runtime evidence is not an object", failures)
    if isinstance(runtime_evidence, dict):
        split = runtime_evidence.get("split_runtime", {})
        transport = runtime_evidence.get("transport", {})
        require(isinstance(split, dict), "split runtime evidence is not an object", failures)
        require(isinstance(transport, dict), "transport evidence is not an object", failures)
        contract_rows = artifact_contract()["shipped_wasm"]
        deferred_rows = [row for row in contract_rows if row["role"] == "deferred"]
        require(len(deferred_rows) == 1,
                "staged runtime contract requires exactly one deferred shard", failures)
        if isinstance(split, dict) and len(deferred_rows) == 1:
            deferred = deferred_rows[0]
            request_key = f"/bin/{deferred['filename']}?sha256={deferred['sha256']}"
            require(split.get("deferred_identity") == {
                "filename": deferred["filename"], "bytes": deferred["bytes"],
                "sha256": deferred["sha256"], "request_key": request_key,
            }, "split runtime deferred identity differs from finalizer inventory", failures)
            for run_name, from_worker in (
                    ("cold_online", None), ("online_warm", True), ("offline_cold", True)):
                run = split.get(run_name, {})
                require(isinstance(run, dict), f"{run_name} split lifecycle is absent", failures)
                if not isinstance(run, dict):
                    continue
                resumed = run.get("resumed", {})
                native = resumed.get("native", {}) if isinstance(resumed, dict) else {}
                before = run.get("before_scene", {})
                after = run.get("after_scene", {})
                deferred_proof = run.get("deferred", {})
                requests = deferred_proof.get("requests", []) if isinstance(deferred_proof, dict) else []
                responses = deferred_proof.get("responses", []) if isinstance(deferred_proof, dict) else []
                require(native.get("phase") == 10 and native.get("resumedGeneration") == 1 and
                        native.get("errorGeneration") == 0,
                        f"{run_name} did not reach exact RESUMED generation", failures)
                require(isinstance(before, dict) and isinstance(after, dict) and
                        isinstance(before.get("meshVertices"), int) and
                        isinstance(after.get("meshVertices"), int) and
                        after["meshVertices"] > before["meshVertices"],
                        f"{run_name} has no post-RESUME semantic state change", failures)
                require(isinstance(requests, list) and len(requests) == 1 and
                        requests[0].get("url") == request_key and
                        isinstance(run.get("interaction_complete_ms"), (int, float)) and
                        isinstance(requests[0].get("at_ms"), (int, float)) and
                        requests[0]["at_ms"] > run["interaction_complete_ms"] and
                        str(requests[0].get("phase", "")).endswith(":PREPARED"),
                        f"{run_name} deferred request is not exact/single", failures)
                require(isinstance(responses, list) and len(responses) == 1 and
                        responses[0].get("url") == request_key and
                        responses[0].get("status") == 200 and
                        responses[0].get("content_type") == "application/wasm" and
                        responses[0].get("content_bytes") == deferred["bytes"] and
                        responses[0].get("content_sha256") == deferred["sha256"] and
                        (from_worker is None or
                         responses[0].get("from_service_worker") is from_worker),
                        f"{run_name} deferred response transport is invalid", failures)
        if isinstance(transport, dict) and len(deferred_rows) == 1:
            path = f"/bin/{deferred_rows[0]['filename']}"
            snapshots = [transport.get(name, {}) for name in (
                "before_cold", "after_cold", "after_precache",
                "after_online_warm", "after_offline_cold")]
            require(all(isinstance(row, dict) and
                        row.get("served_bundle_sha256") == bundle_digest
                        for row in snapshots),
                    "origin-counter snapshots do not bind the exact bundle", failures)
            if all(isinstance(row, dict) for row in snapshots):
                counts = [row.get("asset_get_counts", {}).get(path, 0) for row in snapshots]
                require(all(isinstance(value, int) for value in counts) and
                        counts[1] == counts[0] + 1 and counts[2] in {counts[1], counts[1] + 1} and
                        counts[3] == counts[2] and counts[4] == counts[3],
                        "deferred origin count is not runtime+1/precache+(0|1)/warm+0/offline+0: "
                        f"{counts!r}", failures)

    perf = receipt.get("performance", {})
    require(perf.get("profile") == "mid-laptop-1.5MBps-40ms",
            "performance receipt is not the pinned mid-laptop profile", failures)
    first_pixels = perf.get("cold_first_pixels_ms")
    require(isinstance(first_pixels, (int, float)) and first_pixels <= 8000,
            f"cold first pixels exceed 8s: {first_pixels!r}", failures)
    critical = perf.get("critical_brotli_bytes")
    require(isinstance(critical, int) and critical <= 15_000_000,
            f"critical brotli payload exceeds 15MB: {critical!r}", failures)
    contract = artifact_contract()
    expected_critical = expected_critical_paths(contract)
    require(sorted(perf.get("critical_paths", [])) == expected_critical,
            "performance critical assets differ from split inventory", failures)
    require(perf.get("split_inventory_sha256") == sha256(BUILD / SPLIT_MANIFEST),
            "performance receipt is not bound to split inventory bytes", failures)
    require(perf.get("shard_phase_valid") is True,
            "runtime requested a wasm shard outside its declared phase", failures)
    warm = perf.get("offline_warm_wm_main_ms")
    require(isinstance(warm, (int, float)) and warm <= 8000,
            f"offline/warm WM_main exceeds 8s: {warm!r}", failures)


def check_soak(receipt: dict, failures: list[str]) -> None:
    require(receipt.get("schema") == 1, "soak receipt schema != 1", failures)
    receipt_matches_files(receipt, "source_artifacts", BUILD, build_files(), failures)
    receipt_matches_files(receipt, "bundle_artifacts", BUNDLE, bundle_files(), failures)
    require(receipt.get("served_bundle_sha256") == current_bundle_digest(),
            "soak was not served from the exact current bundle", failures)
    browser = receipt.get("browser", {})
    if not isinstance(browser, dict):
        browser = {}
    check_runtime_identity(browser.get("runtime_identity"), "chrome",
                           browser.get("executable"), browser.get("version"),
                           "soak", failures)
    check_runtime_adapter(browser.get("runtime_adapter"), "soak", failures)
    check_early_diagnostics(receipt.get("early_diagnostics"), "soak", failures)
    require(browser.get("engine") == "chrome",
            "soak did not use branded Chrome", failures)
    require(browser.get("current_at_test") is True and
            browser.get("version") == browser.get("official_version"),
            "soak Chrome was not current at test time", failures)
    try:
        checked = dt.datetime.fromisoformat(str(browser["checked_at"]).replace("Z", "+00:00"))
        age = dt.datetime.now(dt.timezone.utc) - checked
        require(dt.timedelta(0) <= age <= dt.timedelta(days=7),
                "soak Chrome current-version check is older than 7 days", failures)
    except (KeyError, TypeError, ValueError):
        failures.append("soak Chrome current-version timestamp invalid")
    signing = browser.get("signing", {}) if isinstance(browser.get("signing"), dict) else {}
    expected_signing = expected_signing_projection("chrome", browser.get("runtime_identity"))
    require(signing.get("valid") is True and
            (signing.get("identifier"), signing.get("team")) == expected_signing,
            "soak Chrome executable/package signing identity is invalid", failures)
    require(browser.get("fresh_profile") is True, "soak profile was not fresh", failures)
    require(receipt.get("duration_seconds", 0) >= 1800, "soak shorter than full 30-minute gate", failures)
    require(receipt.get("sample_count", 0) >= 60, "soak has fewer than 60 samples", failures)
    samples = receipt.get("samples", [])
    require(isinstance(samples, list) and receipt.get("sample_count") == len(samples),
            "soak sample count differs from receipt rows", failures)
    if isinstance(samples, list):
        require(all(isinstance(sample, dict) and
                    isinstance(sample.get("t_seconds"), int) and
                    isinstance(sample.get("js_heap_bytes"), int) and
                    sample["js_heap_bytes"] > 0 and
                    isinstance(sample.get("process_rss_bytes"), int) and
                    sample["process_rss_bytes"] > 0 and
                    sample.get("module_alive") is True for sample in samples),
                "soak contains an invalid/zero/dead sample", failures)
        times = [sample.get("t_seconds") for sample in samples if isinstance(sample, dict)]
        gaps = [later - earlier for earlier, later in zip(times, times[1:])
                if isinstance(earlier, int) and isinstance(later, int)]
        require(len(times) >= 60 and all(isinstance(value, int) for value in times) and
                times == sorted(times) and len(set(times)) == len(times) and
                bool(gaps) and max(gaps) <= 45 and
                isinstance(receipt.get("duration_seconds"), int) and
                receipt["duration_seconds"] - times[-1] <= 45,
                "soak sampling cadence is discontinuous", failures)
    verdict = receipt.get("verdict", {})
    require(verdict.get("pass") is True, "soak verdict is not PASS", failures)
    for key in ("boot_ok", "js_heap_ok", "process_rss_ok", "sample_integrity_ok",
                "live_ok", "gpu_ok", "no_fatal", "external_ok"):
        require(verdict.get(key) is True, f"soak verdict missing/failed: {key}", failures)
    require(verdict.get("js_heap_growth_pct", 999) < 10, "JS heap growth is >=10%", failures)
    require(verdict.get("process_rss_growth_pct", 999) < 10, "browser RSS growth is >=10%", failures)
    require(verdict.get("stalls") == 0, "soak recorded present stalls", failures)
    require(verdict.get("gpu_errors") == 0, "soak recorded GPU errors", failures)
    require(verdict.get("fatals") == 0, "soak recorded fatal errors", failures)
    require(verdict.get("external_requests") == 0 and receipt.get("external_requests") == [],
            "soak made external runtime requests", failures)
    require(receipt.get("errors") == [], "soak recorded harness/runtime errors", failures)
    require(verdict.get("interaction_failures") == 0,
            "soak recorded trusted-input bursts without a visible response", failures)
    require(isinstance(verdict.get("visible_interactions"), int) and
            verdict.get("visible_interactions", 0) >= verdict.get("minimum_visible_interactions", 1),
            "soak has too few visibly confirmed trusted-input bursts", failures)


def check_browsers(receipt: dict, failures: list[str]) -> None:
    require(receipt.get("schema") == 1, "browser matrix schema != 1", failures)
    require(receipt.get("verdict") == "PASS", "browser matrix combined verdict is not PASS", failures)
    receipt_matches_files(receipt, "source_artifacts", BUILD, build_files(), failures)
    receipt_matches_files(receipt, "bundle_artifacts", BUNDLE, bundle_files(), failures)
    bundle_digest = current_bundle_digest()
    require(receipt.get("served_bundle_sha256") == bundle_digest,
            "browser matrix was not served from the exact current bundle", failures)
    engines = receipt.get("engines", {})
    require(isinstance(engines, dict) and set(engines) == {"chrome", "edge"},
            "browser matrix engine set is not exact chrome+edge", failures)
    exact_row_keys = {
        "channel", "executable", "actual_version", "official_version",
        "official_version_source", "signing", "runtime_identity", "runtime_adapter",
        "early_diagnostics",
        "served_bundle_sha256", "checked_at", "current_at_test", "wm_main", "wm_main_ms",
        "first_pixels", "pixel_proof", "interaction_smoke", "interaction_proof",
        "offline_reload", "query_hooks_disabled", "external_request_count",
        "external_requests", "gpu_errors", "errors",
    }
    for name in ("chrome", "edge"):
        row = engines.get(name, {}) if isinstance(engines, dict) else {}
        require(isinstance(row, dict) and set(row) == exact_row_keys,
                f"{name} browser matrix row keys are not exact", failures)
        expected = expected_signing_projection(name, row.get("runtime_identity"))
        require(row.get("channel") == name, f"{name} receipt is not branded {name} channel", failures)
        check_runtime_identity(row.get("runtime_identity"), name,
                               row.get("executable"), row.get("actual_version"),
                               f"browser matrix {name}", failures)
        check_runtime_adapter(row.get("runtime_adapter"),
                              f"browser matrix {name}", failures)
        diagnostics = row.get("early_diagnostics", {})
        require(isinstance(diagnostics, dict) and set(diagnostics) == {
            "online", "offline_reload"},
            f"{name} early-diagnostics scenario set is not exact", failures)
        if isinstance(diagnostics, dict):
            check_early_diagnostics(diagnostics.get("online"), f"{name} online", failures)
            check_early_diagnostics(diagnostics.get("offline_reload"),
                                    f"{name} offline reload", failures)
        require(row.get("served_bundle_sha256") == bundle_digest,
                f"{name} did not test the exact current served bundle", failures)
        require(row.get("current_at_test") is True, f"{name} was not current at test time", failures)
        require(row.get("actual_version") == row.get("official_version"),
                f"{name} version differs from official stable", failures)
        signing = row.get("signing", {})
        require(signing.get("valid") is True and
                (signing.get("identifier"), signing.get("team")) == expected,
                f"{name} branded executable/package signing identity invalid", failures)
        require(row.get("wm_main") is True, f"{name} did not reach WM_main", failures)
        require(isinstance(row.get("wm_main_ms"), (int, float)) and row["wm_main_ms"] > 0,
                f"{name} WM_main timing is absent/invalid", failures)
        require(row.get("first_pixels") is True, f"{name} did not present pixels", failures)
        pixel = row.get("pixel_proof", {}) if isinstance(row.get("pixel_proof"), dict) else {}
        require(pixel.get("pass") is True and pixel.get("width", 0) >= 1000 and
                pixel.get("height", 0) >= 600 and pixel.get("nonblack_ratio", 0) > 0.1 and
                pixel.get("quantized_colors", 0) > 128,
                f"{name} strict displayed-pixel proof is absent", failures)
        require(row.get("interaction_smoke") is True, f"{name} interaction smoke missing", failures)
        require(row.get("offline_reload") is True, f"{name} offline reload missing", failures)
        require(row.get("query_hooks_disabled") is True, f"{name} public query hooks enabled", failures)
        require(row.get("external_request_count") == 0, f"{name} made external runtime requests", failures)
        require(row.get("external_requests") == [],
                f"{name} external request inventory is not empty", failures)
        errors = row.get("errors")
        require(isinstance(errors, list) and row.get("gpu_errors") == len(errors) == 0,
                f"{name} has GPU/page/crash errors", failures)
        try:
            checked = dt.datetime.fromisoformat(str(row["checked_at"]).replace("Z", "+00:00"))
            age = dt.datetime.now(dt.timezone.utc) - checked
            require(dt.timedelta(0) <= age <= dt.timedelta(days=7),
                    f"{name} current-version check is older than 7 days", failures)
        except (KeyError, TypeError, ValueError):
            failures.append(f"{name} current-version timestamp invalid")


def check_results_and_deferrals(failures: list[str]) -> None:
    mapping = {"m0": "m0", "m1": "m1", "m2": "m2b", "m3": "m3",
               "m4": "m4", "m5": "m5", "m6": "m6", "m7": "m7"}
    for milestone, stem in mapping.items():
        path = ROOT / f"ledger/results/{stem}.json"
        doc = load_json(path, failures)
        require(doc.get("pass") is True, f"{milestone} result is not PASS", failures)

    deferred = load_json(ROOT / "ledger/deferred.json", failures)
    rows = deferred.get("deferred", [])
    by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    for deferral_id in (
        "cycles-final-gpu", "osl", "mantaflow", "large-scenes-16gb", "os-shell-affordances",
    ):
        row = by_id.get(deferral_id, {})
        require(row.get("status") == "deferred-by-goal",
                f"required launch deferral absent/wrong: {deferral_id}", failures)
        require(bool(row.get("blocker")), f"deferral has no named blocker: {deferral_id}", failures)


def check_post_receipt(failures: list[str]) -> None:
    result = load_json(ROOT / "ledger/results/m8.json", failures)
    require(result.get("scope") == "m8", "m8 result has the wrong scope", failures)
    require(result.get("pass") is True, "m8 result is not PASS", failures)
    checks = result.get("checks")
    require(isinstance(checks, dict) and set(checks) == {"technical_release"},
            "m8 result does not contain exactly the technical_release check", failures)
    if isinstance(checks, dict) and isinstance(checks.get("technical_release"), dict):
        row = checks["technical_release"]
        require(row.get("pass") is True,
                "m8 technical_release check is not PASS", failures)
        require(str(row.get("detail", "")).startswith("M8_TECHNICAL_PASS "),
                "m8 technical_release detail is not the technical verifier PASS", failures)
    dashboard = ROOT / "reports/dashboard.md"
    require(dashboard.is_file(), "generated dashboard missing", failures)
    if dashboard.is_file():
        text = dashboard.read_text(encoding="utf-8")
        require(text.startswith("<!-- Generated by scripts/dashboard.sh"),
                "dashboard is not generator-owned", failures)
        require("per-suite pass" in text.lower() or "per-suite" in text.lower(),
                "dashboard lacks per-suite reporting", failures)
        require("Deferral registry" in text, "dashboard lacks deferral registry", failures)
        with tempfile.TemporaryDirectory(prefix="m8-dashboard-") as temporary:
            regenerated = Path(temporary) / "dashboard.md"
            run = subprocess.run(
                ["bash", "scripts/dashboard.sh", str(regenerated)], cwd=ROOT,
                capture_output=True, text=True,
            )
            require(run.returncode == 0 and regenerated.is_file(),
                    "dashboard generator failed during byte-exact verification", failures)
            if run.returncode == 0 and regenerated.is_file():
                require(dashboard.read_bytes() == regenerated.read_bytes(),
                        "dashboard differs from a fresh generator output", failures)


def check_compliance_tool(receipt: dict, failures: list[str]) -> None:
    """Revalidate the exact REUSE executable recorded by the producer."""
    details = receipt.get("details")
    recorded = details.get("reuse_tool") if isinstance(details, dict) else None
    require(isinstance(recorded, dict) and
            set(recorded) == {"path", "version", "bytes", "sha256"},
            "compliance REUSE tool identity is absent or malformed", failures)
    if not isinstance(recorded, dict) or \
            set(recorded) != {"path", "version", "bytes", "sha256"}:
        return
    path_text = recorded.get("path")
    if not isinstance(path_text, str):
        failures.append("compliance REUSE tool path is absent")
        return
    try:
        current = _exact_runtime_file(path_text, "REUSE executable", executable=True)
        stdout, _ = _runtime_command([path_text, "--version"])
    except (OSError, RuntimeError, UnicodeError) as error:
        failures.append(f"compliance REUSE tool verification failed: {error}")
        return
    first_line = stdout.splitlines()[0] if stdout.splitlines() else ""
    require(first_line == f"reuse, version {REUSE_VERSION}",
            "compliance REUSE tool version output differs", failures)
    expected = {
        "path": path_text,
        "version": REUSE_VERSION,
        "bytes": current["bytes"],
        "sha256": current["sha256"],
    }
    require(recorded == expected,
            "compliance REUSE tool identity differs from current executable", failures)


def check_compliance(receipt: dict, failures: list[str]) -> None:
    require(receipt.get("schema") == 1, "compliance receipt schema != 1", failures)
    require(receipt.get("repo_input_digest") == repo_input_digest(),
            "compliance receipt is stale for tracked inputs", failures)
    require(receipt.get("git_history_digest") == git_history_digest(),
            "compliance receipt is stale for git history/metadata", failures)
    check_compliance_tool(receipt, failures)
    technical_required = (
        "reuse_pass",
        "aggregate_gpl3",
        "derived_headers_complete",
        "license_texts_complete",
        "provenance_complete",
        "notice_authors_complete",
        "third_party_complete",
        "dependency_notices_complete",
        "dependency_registry_consistent",
    )
    external_policy = (
        "public_disclaimer_complete",
        "dependency_compatibility_complete",
        "source_code_link_present",
        "history_policy_complete",
    )
    require(receipt.get("technical_required_checks") == list(technical_required),
            "compliance technical-check classification is absent/stale", failures)
    require(receipt.get("external_policy_checks") == list(external_policy),
            "compliance external-policy classification is absent/stale", failures)
    for key in technical_required:
        require(receipt.get(key) is True,
                f"technical package compliance check missing/failed: {key}", failures)
    require(receipt.get("technical_release_pass") is True,
            "technical package compliance verdict is not PASS", failures)
    # Preserve public/legal/history facts without making the local technical gate
    # depend on owner publication or professional/legal policy authority.
    for key in external_policy:
        require(isinstance(receipt.get(key), bool),
                f"external-policy compliance fact is absent/non-boolean: {key}", failures)
    require(isinstance(receipt.get("external_policy_pass"), bool),
            "external-policy compliance verdict is absent/non-boolean", failures)


def check_product_bar(receipt: dict, chrome: dict, failures: list[str]) -> None:
    require(receipt.get("schema") == 1, "30-second product receipt schema != 1", failures)
    require(receipt.get("verdict") == "PASS", "30-second product verdict is not PASS", failures)
    require(receipt.get("failures") == [], "30-second product receipt reported failures", failures)
    receipt_matches_files(receipt, "source_artifacts", BUILD, build_files(), failures)
    receipt_matches_files(receipt, "bundle_artifacts", BUNDLE, bundle_files(), failures)
    require(receipt.get("served_bundle_sha256") == current_bundle_digest(),
            "30-second product run did not use the exact current served bundle", failures)
    browser = receipt.get("browser", {}) if isinstance(receipt.get("browser"), dict) else {}
    check_runtime_identity(browser.get("runtime_identity"), "chrome",
                           browser.get("executable"), browser.get("version"),
                           "30-second product", failures)
    check_runtime_adapter(browser.get("runtime_adapter"), "30-second product", failures)
    diagnostics = receipt.get("early_diagnostics", {})
    require(isinstance(diagnostics, dict) and set(diagnostics) == {
        "skeptic", "own_blend", "rejected_share", "allowed_share"},
        "30-second product early-diagnostics scenario set is not exact", failures)
    if isinstance(diagnostics, dict):
        for name in ("skeptic", "own_blend", "rejected_share", "allowed_share"):
            check_early_diagnostics(diagnostics.get(name), f"30-second product {name}", failures)
    signing = browser.get("signing", {}) if isinstance(browser.get("signing"), dict) else {}
    require(browser.get("engine") == "chrome" and
            browser.get("version") == chrome.get("actual_version"),
            "30-second product run did not use the matrix's exact Chrome version", failures)
    require(signing.get("valid") is True and
            (signing.get("identifier"), signing.get("team")) ==
            expected_signing_projection("chrome", browser.get("runtime_identity")),
            "30-second product Chrome executable/package signing identity is invalid", failures)
    try:
        checked = dt.datetime.fromisoformat(str(receipt["checked_at"]).replace("Z", "+00:00"))
        age = dt.datetime.now(dt.timezone.utc) - checked
        require(dt.timedelta(0) <= age <= dt.timedelta(days=7),
                "30-second product receipt is older than 7 days", failures)
    except (KeyError, TypeError, ValueError):
        failures.append("30-second product checked_at is invalid")
    for key in (
        "interactive_viewport_under_8s",
        "first_interaction_local",
        "orbit_tab_extrude",
        "own_blend_wow_under_30s",
        "fidelity_tells_under_10s",
        "share_scene_allowlisted",
        "skeptic_path_complete",
    ):
        require(receipt.get(key) is True, f"30-second product bar missing/failed: {key}", failures)
    require(receipt.get("skeptic_path_seconds", 999) <= 30,
            f"skeptic path exceeds 30 seconds: {receipt.get('skeptic_path_seconds')!r}", failures)
    require(receipt.get("own_blend_wow_seconds", 999) <= 30,
            f"own .blend wow exceeds 30 seconds: {receipt.get('own_blend_wow_seconds')!r}", failures)
    require(isinstance(receipt.get("interactive_viewport_ms"), (int, float)) and
            receipt.get("interactive_viewport_ms", 999999) <= 8000,
            f"product navigation-to-interactive exceeds 8 seconds: "
            f"{receipt.get('interactive_viewport_ms')!r}", failures)
    runtime = receipt.get("details", {}).get("runtime", {})
    require(runtime.get("external_request_count") == 0,
            "30-second product run made external requests", failures)
    require(runtime.get("gpu_or_page_error_count") == 0,
            "30-second product run recorded GPU/page errors", failures)


def check_external_launch(receipt: dict, bundle_digest: str | None,
                          failures: list[str]) -> None:
    # These values can only come from the owner/external reviewers.  Keeping them in
    # a separate signed-off receipt prevents a technical runner from inventing them.
    require(receipt.get("schema") == 2, "external sign-off schema != 2", failures)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    require(receipt.get("git_commit") == head,
            "external sign-off is not bound to current git commit", failures)
    # A missing/invalid technical bundle is a technical prerequisite, not an
    # owner-policy failure.  The caller records external verification as
    # deferred in that state and this binding is checked once exact bytes exist.
    if bundle_digest is not None:
        require(receipt.get("bundle_sha256") == bundle_digest,
                "external sign-off is not bound to current deploy bundle", failures)
    harness = ROOT / "harness/run.sh"
    require(receipt.get("harness_policy_reviewed") is True,
            "owner has not ratified the final harness policy", failures)
    require(harness.is_file() and receipt.get("harness_run_sha256") == sha256(harness),
            "owner harness ratification is not bound to exact harness/run.sh bytes", failures)
    product_name = receipt.get("product_name")
    require(isinstance(product_name, str) and bool(product_name.strip()) and
            not re.match(r"(?i)^blender\b", product_name.strip()),
            "owner-approved independent product name missing/invalid", failures)
    for key in ("source_url", "production_url", "dashboard_url", "methodology_url"):
        value = receipt.get(key)
        require(isinstance(value, str) and re.match(r"^https://", value) is not None and
                not re.search(r"(?i)(?:example\.(?:com|org|invalid)|placeholder)", value),
                f"external sign-off has no real HTTPS {key}", failures)
    compliance = load_json(ART / "current-compliance-receipt.json", failures)
    require(receipt.get("source_url") == compliance.get("details", {}).get("source_code_href"),
            "signed source URL differs from the public one-click source link", failures)
    require(isinstance(receipt.get("lawyer_reviewer"), str) and
            bool(receipt.get("lawyer_reviewer", "").strip()),
            "signed GPL lawyer reviewer identity missing", failures)
    require(re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("final_post_sha256", ""))) is not None,
            "signed final-post SHA-256 missing", failures)
    require(re.fullmatch(r"[0-9a-f]{64}",
                         str(receipt.get("production_transport_sha256", ""))) is not None,
            "signed production-transport receipt SHA-256 missing", failures)
    try:
        reviewed = dt.datetime.fromisoformat(str(receipt["reviewed_at"]).replace("Z", "+00:00"))
        age = dt.datetime.now(dt.timezone.utc) - reviewed
        require(dt.timedelta(0) <= age <= dt.timedelta(days=30),
                "external sign-off is older than 30 days", failures)
    except (KeyError, TypeError, ValueError):
        failures.append("external sign-off reviewed_at is invalid")

    signoff_path = ART / "external-launch-signoff.json"
    signature_path = ART / "external-launch-signoff.json.sig"
    allowed_signers = ROOT / "launch-owner.allowed_signers"
    require(signature_path.is_file(), "owner launch signature missing", failures)
    require(allowed_signers.is_file(), "trusted owner signer file missing", failures)
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(allowed_signers.relative_to(ROOT))],
        cwd=ROOT, capture_output=True,
    ).returncode == 0 if allowed_signers.is_file() else False
    require(tracked, "trusted owner signer file is not tracked", failures)
    if signature_path.is_file() and allowed_signers.is_file() and signoff_path.is_file():
        verified = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", str(allowed_signers),
             "-I", "launch-owner", "-n", "blender-web-launch", "-s", str(signature_path)],
            input=signoff_path.read_bytes(), capture_output=True,
        )
        require(verified.returncode == 0, "owner launch signature is invalid", failures)
    for key in (
        "brand_approved",
        "trademark_disclaimer_published",
        "lawyer_review_complete",
        "history_policy_complete",
        "production_deploy_verified",
        "dashboard_public",
        "methodology_public",
    ):
        require(receipt.get(key) is True, f"external/owner launch blocker: {key}", failures)
    launch_doc = (ROOT / "LAUNCH.md").read_text(encoding="utf-8")
    require(re.search(r"(?m)^\s*- \[ \]", launch_doc) is None,
            "LAUNCH.md still has unchecked boxes", failures)


def check_production_transport(receipt: dict, external: dict,
                               bundle_digest: str | None,
                               logical_assets: tuple[str, ...] | None,
                               failures: list[str]) -> None:
    """Require an actual deployed-byte receipt; local `.br` rewriting is not one."""
    require(receipt.get("schema") == 1, "production transport schema != 1", failures)
    require(receipt.get("production_url") == external.get("production_url"),
            "production transport URL differs from signed owner URL", failures)
    transport_path = ART / "production-transport-receipt.json"
    require(transport_path.is_file() and
            external.get("production_transport_sha256") == sha256(transport_path),
            "production transport receipt differs from signed owner-reviewed bytes", failures)
    if bundle_digest is not None:
        require(receipt.get("bundle_sha256") == bundle_digest,
                "production transport is not bound to the current bundle", failures)
    require(receipt.get("provider") not in {None, "", "cloudflare-pages-unmodified"},
            "owner-selected deploy provider/package is missing or incompatible", failures)
    require(receipt.get("browser_boot_pass") is True and
            receipt.get("cross_origin_isolated") is True and
            receipt.get("offline_reload_pass") is True,
            "deployed host did not prove isolated browser boot + offline reload", failures)
    try:
        checked = dt.datetime.fromisoformat(str(receipt["checked_at"]).replace("Z", "+00:00"))
        age = dt.datetime.now(dt.timezone.utc) - checked
        require(dt.timedelta(0) <= age <= dt.timedelta(days=7),
                "production transport receipt is older than 7 days", failures)
    except (KeyError, TypeError, ValueError):
        failures.append("production transport checked_at is invalid")
    assets = receipt.get("assets", {})
    require(isinstance(assets, dict), "production transport assets are missing", failures)
    if not isinstance(assets, dict):
        return
    # `_headers` is deploy control metadata and `.br` files are packaging
    # sidecars. Production proves canonical logical URLs whose decoded bytes
    # match the corresponding raw local assets.
    # Exact-tree checks likewise wait for a valid local deploy inventory.  Do
    # not misclassify its absence as a host/owner blocker.
    if logical_assets is None:
        return
    names = logical_assets
    require(set(assets) == set(names),
            "production transport asset inventory differs from exact deploy tree", failures)
    for name in names:
        row = assets.get(name, {})
        local = BUNDLE / name
        require(row.get("status") == 200, f"production asset HTTP failure: {name}", failures)
        require(row.get("decoded_bytes") == local.stat().st_size if local.is_file() else False,
                f"production asset byte count mismatch: {name}", failures)
        require(row.get("decoded_sha256") == sha256(local) if local.is_file() else False,
                f"production asset SHA-256 mismatch: {name}", failures)
        headers = row.get("headers", {}) if isinstance(row.get("headers"), dict) else {}
        require(headers.get("cross-origin-opener-policy") == "same-origin" and
                headers.get("cross-origin-embedder-policy") == "require-corp",
                f"production asset lacks COOP/COEP: {name}", failures)
        if local.is_file() and local.stat().st_size > 25_000_000:
            require(row.get("wire_content_encoding") in {"br", "gzip", "zstd"} and
                    isinstance(row.get("wire_content_length"), int) and
                    row.get("wire_content_length") < local.stat().st_size,
                    f"oversized production asset has no verified compressed transport: {name}", failures)


def chrome_runtime_identities(staged: dict, soak: dict, product: dict,
                              browsers: dict) -> list[object]:
    runtime_proofs = staged.get("runtime_proofs", {}) \
        if isinstance(staged.get("runtime_proofs"), dict) else {}
    staged_runtime = runtime_proofs.get("staged", {}) \
        if isinstance(runtime_proofs.get("staged"), dict) else {}
    performance_runtime = runtime_proofs.get("performance", {}) \
        if isinstance(runtime_proofs.get("performance"), dict) else {}
    soak_browser = soak.get("browser", {}) if isinstance(soak.get("browser"), dict) else {}
    engines = browsers.get("engines", {}) if isinstance(browsers.get("engines"), dict) else {}
    chrome = engines.get("chrome", {}) if isinstance(engines.get("chrome"), dict) else {}
    return [
        staged_runtime.get("browser", {}).get("runtime_identity")
            if isinstance(staged_runtime.get("browser"), dict) else None,
        performance_runtime.get("browser", {}).get("runtime_identity")
            if isinstance(performance_runtime.get("browser"), dict) else None,
        soak_browser.get("runtime_identity"),
        product.get("browser", {}).get("runtime_identity")
            if isinstance(product.get("browser"), dict) else None,
        chrome.get("runtime_identity"),
    ]


def chrome_runtime_adapters(staged: dict, soak: dict, product: dict,
                            browsers: dict) -> list[object]:
    runtime_proofs = staged.get("runtime_proofs", {}) \
        if isinstance(staged.get("runtime_proofs"), dict) else {}
    staged_runtime = runtime_proofs.get("staged", {}) \
        if isinstance(runtime_proofs.get("staged"), dict) else {}
    performance_runtime = runtime_proofs.get("performance", {}) \
        if isinstance(runtime_proofs.get("performance"), dict) else {}
    soak_browser = soak.get("browser", {}) if isinstance(soak.get("browser"), dict) else {}
    product_browser = product.get("browser", {}) \
        if isinstance(product.get("browser"), dict) else {}
    engines = browsers.get("engines", {}) if isinstance(browsers.get("engines"), dict) else {}
    chrome = engines.get("chrome", {}) if isinstance(engines.get("chrome"), dict) else {}
    return [
        staged_runtime.get("browser", {}).get("runtime_adapter")
            if isinstance(staged_runtime.get("browser"), dict) else None,
        performance_runtime.get("browser", {}).get("runtime_adapter")
            if isinstance(performance_runtime.get("browser"), dict) else None,
        soak_browser.get("runtime_adapter"),
        product_browser.get("runtime_adapter"),
        chrome.get("runtime_adapter"),
    ]


def linux_runtime_verifier_selfcheck() -> tuple[int, int]:
    positive = 0
    negative = 0
    fingerprint = LINUX_RUNTIME_CONTRACTS["chrome"]["fingerprint"]
    package_version = "151.0.7922.173-1"
    package_sha256 = "d" * 64
    with tempfile.TemporaryDirectory(prefix="m8-linux-runtime-") as temporary:
        root = Path(temporary).resolve()
        executable = root / "opt/google/chrome/chrome"
        source = root / "etc/apt/sources.list.d/blender-web-google-chrome.list"
        keyring = root / "etc/apt/keyrings/blender-web-google-linux.gpg"
        executable.parent.mkdir(parents=True)
        source.parent.mkdir(parents=True)
        keyring.parent.mkdir(parents=True)
        executable.write_bytes(b"fixture Linux ELF bytes")
        executable.chmod(0o755)
        keyring.write_bytes(b"fixture vendor keyring")
        contract = {
            **LINUX_RUNTIME_CONTRACTS["chrome"],
            "executable": str(executable), "source": str(source), "keyring": str(keyring),
        }
        source_line = (
            f"deb [arch=amd64 signed-by={keyring}] {contract['uri']} stable main\n")
        source.write_text(source_line, encoding="utf-8")
        gpg_fixture = "\n".join((
            "pub:-:4096:1:7721F63BD38B4796:0:0::::::scESC::::::23::0:",
            ":".join(("fpr", "", "", "", "", "", "", "", "", fingerprint, "")),
        ))
        readelf_fixture = "\n".join((
            "ELF Header:",
            "  Class:                             ELF64",
            "  Data:                              2's complement, little endian",
            "  Type:                              DYN (Position-Independent Executable file)",
            "  Machine:                           Advanced Micro Devices X86-64",
        ))

        def fixture_runner(arguments: list[str], **_kwargs):
            command = (arguments[0], arguments[1] if len(arguments) > 1 else "")
            output = ""
            if command == ("gpg", "--batch"):
                output = gpg_fixture
            elif command == ("readelf", "-hW"):
                output = readelf_fixture
            elif command == ("dpkg-query", "-S"):
                output = f"google-chrome-stable: {executable}\n"
            elif command == ("dpkg-query", "-W"):
                output = f"ii \tgoogle-chrome-stable\t{package_version}\tamd64\n"
            elif command == ("apt-cache", "policy"):
                output = (
                    f"google-chrome-stable:\n  Installed: {package_version}\n"
                    f"  Candidate: {package_version}\n"
                    "        500 https://dl.google.com/linux/chrome/deb "
                    "stable/main amd64 Packages\n")
            elif command == ("apt-cache", "show"):
                output = (
                    f"Package: google-chrome-stable\nVersion: {package_version}\n"
                    "Architecture: amd64\n"
                    "Filename: pool/main/g/google-chrome-stable.deb\n"
                    f"SHA256: {package_sha256}\n")
            elif command == ("dpkg", "--verify"):
                output = ""
            else:
                return subprocess.CompletedProcess(arguments, 1, "", "unexpected command")
            return subprocess.CompletedProcess(arguments, 0, output, "")

        identity_value = _collect_linux_runtime_identity(
            "chrome", str(executable), "151.0.7922.173", fixture_runner, contract)
        assert identity_value["schema"] == 2 and identity_value["platform"] == "linux"
        assert identity_value["package"]["candidate"]["sha256"] == package_sha256
        assert expected_signing_projection("chrome", identity_value) == \
            ("google-chrome-stable", fingerprint)
        positive += 3

        def reject(name: str, runner) -> None:
            nonlocal negative
            try:
                _collect_linux_runtime_identity(
                    "chrome", str(executable), "151.0.7922.173", runner, contract)
            except RuntimeError:
                negative += 1
                return
            raise AssertionError(f"Linux runtime verifier false green: {name}")

        def mutate(command_key: tuple[str, str], replacement: str):
            def runner(arguments: list[str], **kwargs):
                key = (arguments[0], arguments[1] if len(arguments) > 1 else "")
                if key == command_key:
                    return subprocess.CompletedProcess(arguments, 0, replacement, "")
                return fixture_runner(arguments, **kwargs)
            return runner

        reject("wrong_machine", mutate(
            ("readelf", "-hW"), readelf_fixture.replace("Advanced Micro Devices X86-64", "AArch64")))
        reject("wrong_fingerprint", mutate(
            ("gpg", "--batch"), gpg_fixture.replace(fingerprint, "A" * 40)))
        reject("stale_candidate", mutate(
            ("apt-cache", "policy"),
            f"  Installed: {package_version}\n  Candidate: 150.0.0.0-1\n"
            "  500 https://dl.google.com/linux/chrome/deb stable/main amd64 Packages\n"))
        reject("modified_package", mutate(
            ("dpkg", "--verify"), f"??5?????? {executable}\n"))
        source.write_text(source_line.replace("signed-by=", "trusted=yes signed-by="),
                          encoding="utf-8")
        reject("source_drift", fixture_runner)
        source.write_text(source_line, encoding="utf-8")
    return positive, negative


def runtime_consumer_selfcheck() -> None:
    identity_fixture = {
        "schema": 1, "executable": {"requested_path": "/fixture", "path": "/fixture",
            "bytes": 1, "sha256": "a" * 64}, "app": {"path": "/Fixture.app", "version": "1"},
        "codesign": {"deep_strict": True, "identifier": "fixture",
                     "team_identifier": "fixture", "cdhash": "b" * 40},
        "notarization": {"assessed": True, "accepted": True,
                         "source": "Notarized Developer ID", "origin": "fixture"},
        "runtime_version": "1", "version_matches_app": True,
    }
    adapter_fixture = {
        "contract": RUNTIME_ADAPTER_CONTRACT,
        "status": "ACCEPTED",
        "present": True,
        "platform": "darwin" if sys.platform == "darwin" else "linux",
        "powerPreference": "high-performance",
        "isFallbackAdapter": False,
        "info": {"vendor": "NVIDIA", "architecture": "Ada",
                 "device": "GeForce RTX 4090", "description": ""},
        "softwareMatches": [],
        "reason": "accepted-hardware",
    }
    staged = {"runtime_proofs": {
        "staged": {"browser": {"runtime_identity": identity_fixture,
                                "runtime_adapter": adapter_fixture}},
        "performance": {"browser": {"runtime_identity": identity_fixture,
                                     "runtime_adapter": adapter_fixture}}}}
    soak = {"browser": {"runtime_identity": identity_fixture,
                        "runtime_adapter": adapter_fixture}}
    product = {"browser": {"runtime_identity": identity_fixture,
                           "runtime_adapter": adapter_fixture}}
    browsers = {"engines": {"chrome": {"runtime_identity": identity_fixture,
                                        "runtime_adapter": adapter_fixture}}}
    identities = chrome_runtime_identities(staged, soak, product, browsers)
    assert all(identity == identities[0] for identity in identities[1:])
    mutated = json.loads(json.dumps(product))
    mutated["browser"]["runtime_identity"]["executable"]["sha256"] = "f" * 64
    identities = chrome_runtime_identities(staged, soak, mutated, browsers)
    assert not all(identity == identities[0] for identity in identities[1:])
    adapters = chrome_runtime_adapters(staged, soak, product, browsers)
    assert all(adapter == adapters[0] for adapter in adapters[1:])
    adapter_failures: list[str] = []
    check_runtime_adapter(adapter_fixture, "fixture", adapter_failures)
    assert not adapter_failures
    adapter_mutations = (
        lambda value: value.pop("reason"),
        lambda value: value.update(status="REJECTED"),
        lambda value: value.update(present=False),
        lambda value: value.update(platform="win32"),
        lambda value: value.update(powerPreference="low-power"),
        lambda value: value.update(isFallbackAdapter=None),
        lambda value: value["info"].update(architecture="llvmpipe"),
        lambda value: value["info"].update(architecture="", device=""),
        lambda value: value.update(softwareMatches=["fixture"]),
        lambda value: value.update(extra=True),
    )
    for mutate_adapter in adapter_mutations:
        candidate = json.loads(json.dumps(adapter_fixture))
        mutate_adapter(candidate)
        failures: list[str] = []
        check_runtime_adapter(candidate, "fixture mutation", failures)
        assert failures
    mutated_adapter_product = json.loads(json.dumps(product))
    mutated_adapter_product["browser"]["runtime_adapter"]["info"]["device"] = "other"
    adapters = chrome_runtime_adapters(staged, soak, mutated_adapter_product, browsers)
    assert not all(adapter == adapters[0] for adapter in adapters[1:])
    diagnostics_failures: list[str] = []
    check_early_diagnostics({"schema": 1, "preload": True, "snapshot": []},
                            "fixture", diagnostics_failures)
    assert not diagnostics_failures
    check_early_diagnostics({"schema": 1, "preload": True,
                             "snapshot": [{"type": "error"}]},
                            "fixture", diagnostics_failures)
    assert diagnostics_failures
    with tempfile.TemporaryDirectory(prefix="m8-compliance-consumer-") as temporary:
        tool = Path(temporary).resolve() / "reuse"
        tool.write_text("#!/bin/sh\nprintf 'reuse, version 6.2.0\\n'\n", encoding="utf-8")
        tool.chmod(0o755)
        tool_identity = {
            "path": str(tool), "version": REUSE_VERSION,
            "bytes": tool.stat().st_size, "sha256": sha256(tool),
        }
        compliance_fixture = {"details": {"reuse_tool": tool_identity}}
        compliance_failures: list[str] = []
        check_compliance_tool(compliance_fixture, compliance_failures)
        assert not compliance_failures
        forged = json.loads(json.dumps(compliance_fixture))
        forged["details"]["reuse_tool"]["sha256"] = "0" * 64
        check_compliance_tool(forged, compliance_failures)
        assert compliance_failures
    node = PINNED_NODE
    assert node.is_file() and subprocess.run(
        [str(node), "--version"], capture_output=True, text=True, check=True).stdout.strip() == "v22.16.0"
    for script, marker in (
        (SELF / "runtime_evidence_selfcheck.mjs", "M8_RUNTIME_EVIDENCE_SELFCHECK_PASS"),
        (SELF / "browser_matrix.mjs", "M8_BROWSER_MATRIX_SELFCHECK_PASS"),
        (ROOT / "sandbox/m8-staged-deploy/public_shell_hardening.py",
         "M8_PUBLIC_SHELL_HARDENING_SELFCHECK_PASS"),
        (ROOT / "sandbox/m8-staged-deploy/verify_public_query_hardening.mjs",
         "M8_PUBLIC_QUERY_HARDENING_CONTRACT_PASS"),
        (BROTLI_CODEC, "BW_BROTLI_Q11_SELFCHECK_PASS"),
        (PUBLIC_MINIFIER, "BW_PUBLIC_SHELL_MINIFIER_SELFCHECK_PASS"),
        (ROOT / "sandbox/m8-staged-deploy/stage_provenance.py",
         "M8_STAGE_PROVENANCE_SELFCHECK_PASS"),
    ):
        command = [str(node), str(script), *(
            ["--selfcheck"] if script.name in {
                "browser_matrix.mjs", "brotli_q11.mjs", "public_shell_minify.mjs"
            } else [])] \
            if script.suffix == ".mjs" else \
            [sys.executable, str(script), "--selfcheck"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0 and marker in result.stdout, result.stderr or result.stdout
    composer_source = (SELF / "make_staged_receipt.py").read_text(encoding="utf-8")
    assert composer_source.count("check_runtime_identity(") >= 2
    assert composer_source.count("check_runtime_adapter(") >= 2
    assert composer_source.count("check_early_diagnostics(") >= 2
    matrix_source = (SELF / "browser_matrix.mjs").read_text(encoding="utf-8")
    assert "receipt.verdict = matrixPass ? \"PASS\" : \"INCOMPLETE\"" in matrix_source
    assert re.search(
        r"validatePriorBrowserMatrix\(\s*prior,\s*CHANNEL,\s*sourceArtifacts,\s*"
        r"bundleArtifacts,\s*expectedBundleDigest,\s*Object\.keys\(row\),",
        matrix_source,
    )
    assert "browserMatrixInvocationPass(priorExists, matrixPass, pass)" in matrix_source
    linux_positive, linux_negative = linux_runtime_verifier_selfcheck()
    print("M8_RUNTIME_CONSUMER_SELFCHECK_PASS cross_lane=identity5+adapter5 "
          f"adapter=1+{len(adapter_mutations)} negative=identity+diagnostics "
          f"linux={linux_positive}+{linux_negative} composer=strict matrix=exact "
          "compliance_tool=live+tamper full_stage=deterministic")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", action="store_true", help="also require owner/external launch sign-off")
    parser.add_argument("--post-receipt", action="store_true",
                        help="after the ratified harness writes m8, require its row and exact dashboard")
    parser.add_argument("--selfcheck", action="store_true",
                        help="run browser/build-free adversarial consumer contract checks")
    args = parser.parse_args()
    if args.selfcheck:
        runtime_consumer_selfcheck()
        return 0

    technical_failures: list[str] = []
    post_receipt_failures: list[str] = []
    external_blockers: list[str] = []

    def run_check(label: str, callback, target: list[str]) -> None:
        try:
            callback()
        except Exception as error:  # A verifier crash is a failure, never a green shortcut.
            target.append(f"{label} verifier exception: {type(error).__name__}: {error}")

    staged = load_json(ART / "current-staged-receipt.json", technical_failures)
    soak = load_json(ART / "current-soak-result.json", technical_failures)
    browsers = load_json(ART / "current-browser-matrix.json", technical_failures)
    compliance = load_json(ART / "current-compliance-receipt.json", technical_failures)
    product = load_json(ART / "current-product-receipt.json", technical_failures)
    run_check("staged", lambda: check_staged(staged, technical_failures), technical_failures)
    run_check("soak", lambda: check_soak(soak, technical_failures), technical_failures)
    run_check("browser matrix", lambda: check_browsers(browsers, technical_failures), technical_failures)
    soak_browser = soak.get("browser", {}) if isinstance(soak.get("browser"), dict) else {}
    engines = browsers.get("engines", {}) if isinstance(browsers.get("engines"), dict) else {}
    chrome = engines.get("chrome", {}) if isinstance(engines.get("chrome"), dict) else {}
    chrome_identities = chrome_runtime_identities(staged, soak, product, browsers)
    require(all(isinstance(identity, dict) for identity in chrome_identities)
            and all(identity == chrome_identities[0] for identity in chrome_identities[1:]),
            "Chrome runtime identity differs across staged/performance/soak/product/matrix lanes",
            technical_failures)
    chrome_adapters = chrome_runtime_adapters(staged, soak, product, browsers)
    require(all(isinstance(adapter, dict) for adapter in chrome_adapters)
            and all(adapter == chrome_adapters[0] for adapter in chrome_adapters[1:]),
            "WebGPU adapter differs across staged/performance/soak/product/matrix lanes",
            technical_failures)
    require(soak_browser.get("version") == chrome.get("actual_version"),
            "soak Chrome version differs from the signed current-browser receipt", technical_failures)
    run_check("milestones/deferrals",
              lambda: check_results_and_deferrals(technical_failures), technical_failures)
    run_check("compliance", lambda: check_compliance(compliance, technical_failures), technical_failures)
    run_check("30-second product",
              lambda: check_product_bar(product, chrome, technical_failures),
              technical_failures)
    if args.post_receipt:
        run_check("post-receipt/dashboard",
                  lambda: check_post_receipt(post_receipt_failures), post_receipt_failures)
    external_verification_deferred = False
    external_verification_reason = None
    if args.launch:
        external_bundle_digest: str | None = None
        external_logical_assets: tuple[str, ...] | None = None
        try:
            external_bundle_digest = current_bundle_digest()
            external_logical_assets = tuple(
                name for name in bundle_files()
                if name != "_headers" and not name.endswith(".br")
            )
        except Exception as error:
            external_verification_deferred = True
            external_verification_reason = (
                "exact local deploy bundle is not yet technically valid: "
                f"{type(error).__name__}: {error}"
            )
        external = load_json(ART / "external-launch-signoff.json", external_blockers)
        run_check("owner launch sign-off",
                  lambda: check_external_launch(
                      external, external_bundle_digest, external_blockers),
                  external_blockers)
        transport = load_json(ART / "production-transport-receipt.json", external_blockers)
        run_check("production transport",
                  lambda: check_production_transport(
                      transport, external, external_bundle_digest,
                      external_logical_assets, external_blockers),
                  external_blockers)

    mode = "launch" if args.launch else "technical"
    if args.post_receipt:
        mode += "_post_receipt"
    preflight = {
        "schema": 1,
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": mode,
        "technical_pass": not technical_failures,
        "post_receipt_pass": not post_receipt_failures if args.post_receipt else None,
        "external_launch_pass": (
            None if args.launch and external_verification_deferred
            else (not external_blockers if args.launch else None)
        ),
        "external_verification_deferred": (
            external_verification_deferred if args.launch else None
        ),
        "external_verification_reason": external_verification_reason,
        "launch_ready": not technical_failures and not post_receipt_failures and
                        (not external_blockers if args.launch else False) and
                        not external_verification_deferred,
        "technical_failures": technical_failures,
        "post_receipt_failures": post_receipt_failures,
        "external_blockers": external_blockers,
    }
    ART.mkdir(parents=True, exist_ok=True)
    (ART / "current-m8-preflight.json").write_text(
        json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    all_failures = technical_failures + post_receipt_failures + external_blockers
    if all_failures:
        print(f"M8_{mode.upper()}_FAIL technical={len(technical_failures)} "
              f"post={len(post_receipt_failures)} external={len(external_blockers)}")
        for label, rows in (("TECHNICAL", technical_failures),
                            ("POST-RECEIPT", post_receipt_failures),
                            ("EXTERNAL", external_blockers)):
            for failure in rows:
                print(f" - [{label}] {failure}")
        return 1
    passed_scope = "staged+offline+perf+soak+chrome+edge+product+M0-M7+compliance"
    if args.post_receipt:
        passed_scope += "+M8+dashboard"
    if args.launch:
        passed_scope += "+signed-owner+production-transport"
    print(f"M8_{mode.upper()}_PASS {passed_scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
