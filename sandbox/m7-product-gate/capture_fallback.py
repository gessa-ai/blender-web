#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture immutable branded Firefox + Safari fallback evidence.

This is a production evidence driver, not a compatibility shim.  It talks to the
official applications through their W3C WebDriver services, exercises the exact
M8 staged tree served by ``serve_measure.py``, and publishes a selector only
after both rows satisfy the strict receipt schema.  Playwright Firefox/WebKit are
deliberately not accepted as substitutes for the branded products.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import urlopen

import jsonschema

import fallback_contract as contract

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sandbox/final-source-freeze"))
import freeze_release  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUNDLE = ROOT / "sandbox/m8-staged-deploy/bundle-staged"
EVIDENCE = HERE / "fallback-evidence"
SCHEMA = HERE / "fallback_receipt.schema.json"
PRODUCER = Path(__file__).resolve()
INPUT_SOURCE = ROOT / "sandbox/m4-goldens/default_cube.blend"
FIREFOX_APP = Path("/Applications/Firefox.app")
SAFARI_APP = Path("/Applications/Safari.app")
FIREFOX_BINARY = FIREFOX_APP / "Contents/MacOS/firefox"
SAFARI_BINARY = SAFARI_APP / "Contents/MacOS/Safari"
SAFARIDRIVER = Path("/System/Cryptexes/App/usr/bin/safaridriver")
DEFAULT_GECKODRIVER = (ROOT / ".m8-browsers/"
                       "geckodriver-v0.37.1-macos-aarch64/geckodriver")
CRITICAL_FROZEN_PATHS = (
    "platform_web/shell/windowed.html",
    "platform_web/shell/diagnostics-bootstrap.js",
    "platform_web/shell/boot-windowed.js",
    "platform_web/shell/file-bridge.js",
    "platform_web/shell/wgpu-preinit-worker.js",
    "sandbox/m7-product-gate/fallback_contract.py",
    "sandbox/m7-product-gate/capture_fallback.py",
    "sandbox/m7-product-gate/fallback_receipt.schema.json",
    "sandbox/m7-product-gate/verify_m7.py",
    "sandbox/m8-launch-gate/verify_m8.py",
    "sandbox/m8-launch-gate/bundle_identity.mjs",
    "sandbox/m8-staged-deploy/make_staged_bundle.sh",
    "sandbox/m8-staged-deploy/brotli_q11.mjs",
    "sandbox/m8-staged-deploy/public_shell_minify.mjs",
    "sandbox/m8-staged-deploy/serve_measure.py",
    "sandbox/m8-staged-deploy/transport_contract.py",
)
VOLATILE_GENERATED_OUTPUTS = {
    "ledger/results/m0.json", "ledger/results/m1.json", "ledger/results/m2b.json",
    "ledger/results/m3.json", "ledger/results/m4.json", "ledger/results/m5.json",
    "ledger/results/m6.json", "ledger/results/m7.json", "ledger/results/m8.json",
    "reports/dashboard.md",
}
ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"


class CaptureError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    path = path.absolute()
    if not path.is_file():
        raise CaptureError(f"required file is missing: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: object, where: str) -> dt.datetime:
    if not isinstance(value, str):
        raise CaptureError(f"{where} is not a timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CaptureError(f"{where} is invalid: {value!r}") from error
    if parsed.tzinfo is None:
        raise CaptureError(f"{where} has no timezone")
    return parsed.astimezone(dt.timezone.utc)


def load_json(path: Path, where: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CaptureError(f"cannot read {where}: {path}: {error}") from error
    if not isinstance(value, dict):
        raise CaptureError(f"{where} is not a JSON object: {path}")
    return value


def run_identity_command(command: list[str], where: str) -> subprocess.CompletedProcess[str]:
    """Run a host identity probe and turn a missing host tool into a closed failure."""
    try:
        return subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
    except OSError as error:
        raise CaptureError(f"{where} identity command is unavailable: {command[0]}: {error}") \
            from error


def validate_codesign_detail(detail: str, expected_identifier: str,
                             expected_team: str, where: str) -> None:
    """Require one exact Apple signing identifier and team in ``codesign`` output."""
    identifiers = re.findall(r"(?m)^Identifier=(.+)$", detail)
    teams = re.findall(r"(?m)^TeamIdentifier=(.+)$", detail)
    if identifiers != [expected_identifier] or teams != [expected_team]:
        raise CaptureError(f"unexpected signing identity for {where}")


def validate_capture_host(system_name: str) -> None:
    """Keep the two-row branded capture on the host that can run real Safari."""
    if system_name != "Darwin":
        raise CaptureError(
            "production branded Firefox + Safari capture requires macOS; "
            "use --selfcheck for host-independent contract validation")


def validate_source_freeze(path: Path) -> dt.datetime:
    if path.absolute() != contract.CANONICAL_FREEZE_RECEIPT or path.is_symlink():
        raise CaptureError(f"source freeze must be exact canonical receipt: "
                           f"{contract.CANONICAL_FREEZE_RECEIPT}")
    receipt, rows, errors = contract.validate_canonical_source_freeze(
        ROOT, path, freeze_release.REQUIRED_PROJECT_PATHS,
        freeze_release.REQUIRED_UPSTREAM_PATHS, freeze_release.VOLATILE_GENERATED_OUTPUTS)
    if errors:
        raise CaptureError(errors[0])
    missing_coverage = sorted(set(CRITICAL_FROZEN_PATHS) - set(rows))
    if missing_coverage:
        raise CaptureError("canonical source freeze omits fallback critical paths: " +
                           ", ".join(missing_coverage))
    return parse_utc(receipt.get("created_utc"), "source freeze created_utc")


def reserve_label(label: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", label):
        raise CaptureError("label must match [A-Za-z0-9][A-Za-z0-9._-]*")
    current = Path(EVIDENCE.anchor)
    for part in EVIDENCE.parts[1:-1]:
        current /= part
        try:
            info = current.lstat()
        except OSError as error:
            raise CaptureError(f"fallback evidence parent is missing: {current}") from error
        if not stat.S_ISDIR(info.st_mode) or current.is_symlink():
            raise CaptureError(f"fallback evidence parent is indirect/non-directory: {current}")
    if EVIDENCE.exists() or EVIDENCE.is_symlink():
        info = EVIDENCE.lstat()
        if not stat.S_ISDIR(info.st_mode) or EVIDENCE.is_symlink() or EVIDENCE.resolve() != EVIDENCE:
            raise CaptureError("fallback evidence root is not a canonical real directory")
    else:
        os.mkdir(EVIDENCE, 0o755)
    root = EVIDENCE / label
    try:
        os.mkdir(root, 0o755)
    except FileExistsError as error:
        raise CaptureError(f"refusing to overwrite immutable evidence label: {label}") from error
    if root.is_symlink() or not stat.S_ISDIR(root.lstat().st_mode) or root.resolve() != root:
        raise CaptureError("reserved fallback label is not a canonical real directory")
    write_exclusive(root / "INCOMPLETE", b"fallback capture did not complete\n")
    return root


def plist_identity(app: Path, binary: Path, expected_identifier: str,
                   expected_team: str) -> dict[str, Any]:
    info_path = app / "Contents/Info.plist"
    with info_path.open("rb") as handle:
        info = plistlib.load(handle)
    product = info.get("CFBundleName")
    version = info.get("CFBundleShortVersionString")
    identifier = info.get("CFBundleIdentifier")
    if not all(isinstance(value, str) and value for value in (product, version, identifier)):
        raise CaptureError(f"invalid app identity: {app}")
    if identifier != expected_identifier:
        raise CaptureError(f"unexpected app identifier for {app}: {identifier}")
    verify = run_identity_command(
        ["codesign", "--verify", "--deep", "--strict", str(app)], str(app))
    detail = run_identity_command(
        ["codesign", "-dv", "--verbose=2", str(app)], str(app))
    if verify.returncode or detail.returncode:
        raise CaptureError(f"code signature verification failed for {app}: {verify.stdout}{detail.stdout}")
    validate_codesign_detail(detail.stdout, expected_identifier, expected_team, str(app))
    return {
        "product": product,
        "version": version,
        "binary": file_record(binary),
        "signing": {"identifier": expected_identifier, "team": expected_team, "valid": True},
    }


def signed_driver_identity(path: Path, family: str, app_version: str) -> dict[str, Any]:
    verify = run_identity_command(
        ["codesign", "--verify", "--strict", str(path)], f"{family} WebDriver")
    detail = run_identity_command(
        ["codesign", "-dv", "--verbose=2", str(path)], f"{family} WebDriver")
    version = run_identity_command([str(path), "--version"], f"{family} WebDriver")
    if verify.returncode or detail.returncode or version.returncode:
        raise CaptureError(f"{family} WebDriver identity probe failed")
    first_line = version.stdout.splitlines()[0].strip() if version.stdout.splitlines() else ""
    if family == "firefox":
        expected_identifier, expected_team = contract.GECKODRIVER_IDENTIFIER, contract.GECKODRIVER_TEAM
        if not contract.geckodriver_release_matches(sha256(path), first_line):
            raise CaptureError("Firefox driver does not match the frozen official geckodriver pin")
    else:
        expected_identifier, expected_team = "com.apple.safaridriver", "not set"
        if path.resolve() != contract.SAFARIDRIVER.resolve() or \
                not first_line.startswith(f"Included with Safari {app_version} "):
            raise CaptureError("Safari driver version does not match the canonical Safari app")
    validate_codesign_detail(
        detail.stdout, expected_identifier, expected_team, f"{family} WebDriver")
    return {"artifact": file_record(path), "version": first_line,
            "signing": {"identifier": expected_identifier, "team": expected_team, "valid": True}}


def bundle_artifacts() -> dict[str, dict[str, object]]:
    sys.path.insert(0, str(ROOT / "sandbox/m8-launch-gate"))
    import verify_m8  # noqa: PLC0415
    verify_m8.validate_public_split_manifest()
    files = tuple(verify_m8.bundle_files())
    if not files:
        raise CaptureError("M8 exact bundle contract is empty")
    return {name: file_record(BUNDLE / name) for name in files}


def canonical_bundle_digest(artifacts: dict[str, dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for name in sorted(artifacts):
        row = artifacts[name]
        digest.update(f"{name}\0{row['bytes']}\0{row['sha256']}\n".encode("utf-8"))
    return digest.hexdigest()


def validate_server(base: str, artifacts: dict[str, dict[str, object]]) -> dict[str, Any]:
    parsed = urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} \
            or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise CaptureError("--base must be a plain loopback HTTP origin")
    normalized = base.rstrip("/")
    try:
        with urlopen(normalized + "/.well-known/bw-transport-proof", timeout=10) as response:
            proof = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise CaptureError(f"exact-tree server preflight failed: {error}") from error
    if proof.get("schema") != 1 or \
            proof.get("served_bundle_sha256") != canonical_bundle_digest(artifacts):
        raise CaptureError("server is not serving the exact current staged bundle")
    observed: dict[str, dict[str, Any]] = {}
    for name, expected in sorted(artifacts.items()):
        expected_url = normalized + "/" + quote(name, safe="/-._~")
        try:
            with urlopen(expected_url, timeout=120) as response:
                payload = response.read()
                final_url, status = response.geturl(), response.status
                header_bundle = response.headers.get("X-BW-Bundle-SHA256")
                header_bytes = response.headers.get("X-BW-Content-Bytes")
                header_sha = response.headers.get("X-BW-Content-SHA256")
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise CaptureError(f"exact-tree asset fetch failed for {name}: {error}") from error
        digest = hashlib.sha256(payload).hexdigest()
        if final_url != expected_url or status != 200 or len(payload) != expected["bytes"] or \
                digest != expected["sha256"] or header_bundle != canonical_bundle_digest(artifacts) or \
                header_bytes != str(expected["bytes"]) or header_sha != expected["sha256"]:
            raise CaptureError(f"server byte/header identity mismatch for {name}")
        observed[name] = {"url": final_url, "status": status, "bytes": len(payload),
                          "sha256": digest, "bundleSha256": header_bundle}
    return {"baseUrl": normalized, "servedBundleSha256": canonical_bundle_digest(artifacts),
            "artifacts": observed}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class WebDriver:
    def __init__(self, executable: Path, command: list[str], transcript: Path) -> None:
        self.executable = executable.resolve(strict=True)
        self.command = command
        self.transcript_path = transcript
        self.transcript = transcript.open("xb")
        self.sequence = 0
        self.process: subprocess.Popen[str] | None = None
        self.port = int(command[-1])
        self.session: str | None = None

    def record(self, direction: str, operation: str, payload: object) -> None:
        self.sequence += 1
        line = json.dumps({"sequence": self.sequence, "direction": direction,
                           "operation": operation, "payload": payload}, sort_keys=True,
                          separators=(",", ":")) + "\n"
        self.transcript.write(line.encode("utf-8"))
        self.transcript.flush()

    def request(self, operation: str, method: str, path: str,
                payload: object | None = None) -> Any:
        body = None if payload is None else json.dumps(payload, separators=(",", ":"))
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=250)
        try:
            connection.request(method, path, body=body,
                               headers={"Content-Type": "application/json;charset=UTF-8"})
            response = connection.getresponse()
            raw = response.read()
        except OSError as error:
            raise CaptureError(f"WebDriver request failed: {method} {path}: {error}") from error
        finally:
            connection.close()
        try:
            decoded = json.loads(raw) if raw else {}
        except json.JSONDecodeError as error:
            raise CaptureError(f"WebDriver returned non-JSON for {method} {path}") from error
        self.record("request", operation, {"method": method, "path": path, "body": payload})
        self.record("response", operation, {"status": response.status, "body": decoded})
        value = decoded.get("value", decoded) if isinstance(decoded, dict) else decoded
        if response.status >= 400 or (isinstance(value, dict) and value.get("error")):
            raise CaptureError(f"WebDriver error for {method} {path}: {value}")
        return value

    def start(self, capabilities: dict[str, Any]) -> dict[str, Any]:
        log = self.transcript_path.with_name("webdriver-service.log").open("xb")
        try:
            self.process = subprocess.Popen(self.command, stdout=log, stderr=subprocess.STDOUT,
                                            text=True, start_new_session=True)
        finally:
            log.close()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise CaptureError(f"WebDriver service exited early ({self.process.returncode})")
            try:
                status = self.request("webdriver.status", "GET", "/status")
                if isinstance(status, dict) and status.get("ready") is not False:
                    break
            except CaptureError:
                time.sleep(0.1)
        else:
            raise CaptureError("WebDriver service did not become ready")
        value = self.request("session.create", "POST", "/session",
                             {"capabilities": {"alwaysMatch": capabilities}})
        if not isinstance(value, dict) or not isinstance(value.get("sessionId"), str):
            raise CaptureError("WebDriver new-session response has no sessionId")
        self.session = value["sessionId"]
        self.request("session.timeouts", "POST", self.path("timeouts"),
                     {"script": 240000, "pageLoad": 240000, "implicit": 0})
        result = value.get("capabilities", {})
        return result if isinstance(result, dict) else {}

    def path(self, suffix: str) -> str:
        if not self.session:
            raise CaptureError("WebDriver session is not active")
        return f"/session/{quote(self.session, safe='')}/{suffix}"

    def navigate(self, url: str) -> None:
        self.request("navigation.open", "POST", self.path("url"), {"url": url})

    def refresh(self) -> None:
        self.request("navigation.refresh", "POST", self.path("refresh"), {})

    def execute(self, operation: str, script: str, args: list[Any] | None = None) -> Any:
        return self.request(operation, "POST", self.path("execute/sync"),
                            {"script": script, "args": args or []})

    def execute_async(self, operation: str, script: str,
                      args: list[Any] | None = None) -> Any:
        return self.request(operation, "POST", self.path("execute/async"),
                            {"script": script, "args": args or []})

    def element(self, operation: str, selector: str) -> str:
        value = self.request(operation, "POST", self.path("element"),
                             {"using": "css selector", "value": selector})
        if not isinstance(value, dict) or not isinstance(value.get(ELEMENT_KEY), str):
            raise CaptureError(f"WebDriver could not resolve element: {selector}")
        return value[ELEMENT_KEY]

    def click(self, operation: str, element: str) -> None:
        self.request(operation, "POST", self.path(f"element/{quote(element, safe='')}/click"), {})

    def set_file(self, operation: str, element: str, path: Path) -> None:
        text = str(path.resolve(strict=True))
        self.request(operation, "POST", self.path(f"element/{quote(element, safe='')}/value"),
                     {"text": text, "value": list(text)})

    def wait(self, operation: str, script: str, timeout: float, description: str) -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.execute(operation, script)
            if result:
                return result
            time.sleep(0.25)
        raise CaptureError(f"timed out waiting for {description}")

    def screenshot(self, operation: str, element: str) -> bytes:
        value = self.request(operation, "GET",
                             self.path(f"element/{quote(element, safe='')}/screenshot"))
        if not isinstance(value, str):
            raise CaptureError("WebDriver screenshot response is not base64")
        try:
            return __import__("base64").b64decode(value, validate=True)
        except ValueError as error:
            raise CaptureError("WebDriver screenshot response is invalid base64") from error

    def orbit(self, element: str) -> None:
        actions = json.loads(json.dumps(contract.ORBIT_ACTIONS))
        actions["actions"][0]["actions"][0]["origin"][ELEMENT_KEY] = element
        self.request("canvas.orbit", "POST", self.path("actions"), actions)

    def close(self) -> None:
        if self.session:
            try:
                self.request("session.delete", "DELETE", f"/session/{quote(self.session, safe='')}")
            except CaptureError:
                pass
            self.session = None
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.transcript.close()


def require_true(value: object, message: str) -> None:
    if value is not True:
        raise CaptureError(message)


def write_exclusive(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def scene_semantics(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("ok") is not True:
        raise CaptureError(f"Blender scene inspection failed: {value}")
    result = {key: value.get(key) for key in (
        "active", "objectCount", "objects", "meshVertices", "mode", "renderEngine")}
    if result["active"] != "Cube" or result["meshVertices"] != 8 or result["mode"] != "OBJECT" \
            or result["objects"] != ["Camera", "Cube", "Light"] or result["objectCount"] != 3:
        raise CaptureError(f"Blender scene semantic identity is not the input fixture: {result}")
    return result


def wait_download(path: Path, expected_bytes: int, timeout: float = 90) -> None:
    deadline, last_size, stable = time.monotonic() + timeout, -1, 0
    while time.monotonic() < deadline:
        if path.is_file():
            size = path.stat().st_size
            stable = stable + 1 if size == last_size else 0
            last_size = size
            if stable >= 3 and size == expected_bytes:
                return
        time.sleep(0.25)
    raise CaptureError(f"real browser download did not complete at exact isolated path: {path}")


def capture_browser(family: str, evidence_root: Path, base: str, driver_path: Path,
                    driver_identity: dict[str, Any], app_identity: dict[str, Any],
                    artifacts: dict[str, dict[str, object]], label: str,
                    nonce: str) -> dict[str, Any]:
    family_root = evidence_root / family
    family_root.mkdir()
    input_name = f"fallback-{label}-{nonce}.blend"
    save_name = f"fallback-save-{label}-{nonce}.blend"
    input_path = family_root / input_name
    shutil.copyfile(INPUT_SOURCE, input_path)
    download_dir = family_root / "downloads"
    download_dir.mkdir()
    download_path = download_dir / save_name
    browser_download_path = download_path
    transcript = family_root / "webdriver-transcript.jsonl"
    port = free_port()
    if family == "firefox":
        command = [str(driver_path), "--log", "trace", "--port", str(port)]
        capabilities = {"browserName": "firefox", "moz:firefoxOptions": {
            "binary": str(FIREFOX_BINARY), "prefs": {
                "browser.download.folderList": 2,
                "browser.download.dir": str(download_dir.resolve()),
                "browser.download.useDownloadDir": True,
                "browser.download.manager.showWhenStarting": False,
                "browser.helperApps.neverAsk.saveToDisk":
                    "application/x-blender,application/octet-stream",
                "pdfjs.disabled": True,
            }}}
    else:
        command = [str(driver_path), "--port", str(port)]
        capabilities = {"browserName": "safari"}
        canonical_downloads = Path.home() / "Downloads"
        if not canonical_downloads.is_dir() or canonical_downloads.is_symlink():
            raise CaptureError("canonical Safari Downloads directory is missing or unsafe")
        browser_download_path = canonical_downloads.resolve() / save_name
        if browser_download_path.exists() or browser_download_path.is_symlink():
            raise CaptureError("nonce Safari download target existed before capture")
    navigation_url = base.rstrip("/") + f"/index.html?m7fallback={quote(nonce, safe='')}"
    capabilities_sha = contract.json_sha256(capabilities)
    webdriver = WebDriver(driver_path, command, transcript)
    observed: dict[str, Any] = {}
    process_id = 0
    product_initial: dict[str, Any] = {}
    product_reload: dict[str, Any] = {}
    environment: dict[str, Any] = {}
    browser_assets: list[dict[str, Any]] = []
    after_open: dict[str, Any] = {}
    reload_store: dict[str, Any] = {}
    download_reopen: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    initial_pixels: dict[str, Any] = {}
    interaction_pixels: dict[str, Any] = {}
    pixel_difference = 0.0
    session_hash = ""
    try:
        observed = webdriver.start(capabilities)
        process_id = webdriver.process.pid if webdriver.process else 0
        session_hash = hashlib.sha256((webdriver.session or "").encode()).hexdigest()
        browser_name = str(observed.get("browserName", "")).lower()
        browser_version = str(observed.get("browserVersion", ""))
        if family not in browser_name or browser_version != app_identity["version"]:
            raise CaptureError(f"{family} WebDriver identity mismatch: {browser_name} {browser_version}")
        webdriver.navigate(navigation_url)
        webdriver.wait("boot.wait", contract.BOOT_STATE, 600, f"{family} editor boot")
        environment = webdriver.execute("environment.probe", contract.ENVIRONMENT_PROBE)
        if not isinstance(environment, dict) or any(environment.get(name) is not True
                for name in ("secure", "coi", "sab", "opfs", "observerPreload")) or \
                environment.get("fsa") is not False or environment.get("observerSchema") != 1:
            raise CaptureError(f"{family} fallback environment is incomplete: {environment}")
        specs = [{"name": name, "bytes": row["bytes"], "sha256": row["sha256"]}
                 for name, row in sorted(artifacts.items())]
        bundle_probe = webdriver.execute_async("bundle.probe", contract.BUNDLE_PROBE, [specs])
        if not isinstance(bundle_probe, dict) or bundle_probe.get("ok") is not True:
            raise CaptureError(f"{family} browser bundle fetch failed: {bundle_probe}")
        browser_assets = bundle_probe.get("artifacts", [])
        if not isinstance(browser_assets, list) or len(browser_assets) != len(specs):
            raise CaptureError(f"{family} browser bundle ledger is incomplete")
        bundle_digest = canonical_bundle_digest(artifacts)
        for expected, actual in zip(specs, browser_assets, strict=True):
            if not isinstance(actual, dict) or actual.get("name") != expected["name"] or \
                    actual.get("bytes") != expected["bytes"] or actual.get("sha256") != expected["sha256"] or \
                    actual.get("status") != 200 or actual.get("bundleSha256") != bundle_digest or \
                    actual.get("headerBytes") != str(expected["bytes"]) or \
                    actual.get("headerSha256") != expected["sha256"]:
                raise CaptureError(f"{family} browser-loaded artifact mismatch: {expected['name']}")
        product_initial = webdriver.execute_async("product.probe", contract.PRODUCT_PROBE)
        if not isinstance(product_initial, dict) or any(product_initial.get(key) is not True
                for key in ("ok", "workerDevice", "presented", "backend")):
            raise CaptureError(f"{family} Blender WebGPU product probe failed: {product_initial}")
        initial_scene = scene_semantics(product_initial.get("scene"))
        canvas = webdriver.element("canvas.screenshot.initial", "#canvas")
        initial_png = webdriver.screenshot("canvas.screenshot.initial", canvas)
        write_exclusive(family_root / "initial-canvas.png", initial_png)
        initial_pixels, initial_values = contract.png_pixel_proof(initial_png)
        require_true(initial_pixels.get("pass"), f"{family} initial product pixels absent")
        before = webdriver.execute_async("store.before", contract.STORE_BEFORE)
        if not isinstance(before, dict) or before.get("ok") is not True or \
                input_name in before.get("items", []) or save_name in before.get("items", []):
            raise CaptureError(f"{family} OPFS nonce was stale before run: {before}")
        webdriver.execute("open.install", contract.INSTALL_OPEN, [input_name])
        webdriver.click("open.button.click",
                        webdriver.element("open.button.find", "#bw_fallback_capture_open"))
        file_element = webdriver.element("file.input.find", "input[type=file]")
        webdriver.set_file("file.input.set", file_element, input_path)
        opened = webdriver.wait("open.wait", contract.OPEN_WAIT, 90,
                                f"{family} fallback input acceptance")
        result = opened.get("result", {}) if isinstance(opened, dict) else {}
        if not isinstance(opened, dict) or opened.get("error") is not None or \
                result.get("name") != input_name or result.get("size") != input_path.stat().st_size:
            raise CaptureError(f"{family} input fallback failed: {opened}")
        after_open = webdriver.execute_async("store.after_open", contract.STORE_AFTER_OPEN)
        if not isinstance(after_open, dict) or after_open.get("ok") is not True or \
                after_open.get("list", {}).get("items", []).count(input_name) != 1 or \
                scene_semantics(after_open.get("scene")) != initial_scene:
            raise CaptureError(f"{family} nonce-bound OPFS open failed: {after_open}")
        webdriver.orbit(canvas)
        time.sleep(0.4)
        interaction_png = webdriver.screenshot("canvas.screenshot.interaction", canvas)
        write_exclusive(family_root / "interaction-canvas.png", interaction_png)
        interaction_pixels, interaction_values = contract.png_pixel_proof(interaction_png)
        pixel_difference = contract.mean_absolute_difference(initial_values, interaction_values)
        if interaction_pixels.get("pass") is not True or pixel_difference <= 0.5:
            raise CaptureError(f"{family} canvas did not prove live Blender interaction")
        webdriver.execute("download.install", contract.INSTALL_DOWNLOAD, [save_name])
        webdriver.click("download.button.click",
                        webdriver.element("download.button.find", "#bw_fallback_capture_save"))
        saved = webdriver.wait("download.wait", contract.DOWNLOAD_WAIT, 90,
                               f"{family} real download fallback save")
        ack = saved.get("ack", {}) if isinstance(saved, dict) else {}
        if not isinstance(saved, dict) or saved.get("error") is not None or saved.get("via") != "download" \
                or not isinstance(ack, dict) or ack.get("ok") is not True or ack.get("name") != save_name:
            raise CaptureError(f"{family} real download fallback did not run: {saved}")
        wait_download(browser_download_path, int(ack.get("size", -1)))
        if family == "safari":
            os.replace(browser_download_path, download_path)
            directory_fd = os.open(download_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        downloaded = download_path.read_bytes()
        if len(downloaded) <= 1000 or downloaded[:4] != bytes.fromhex("28b52ffd"):
            raise CaptureError(f"{family} downloaded file is not a compressed .blend")
        before_download_reopen = webdriver.execute_async(
            "store.before_download_reopen", contract.STORE_BEFORE)
        before_items = before_download_reopen.get("items", []) \
            if isinstance(before_download_reopen, dict) else []
        if not isinstance(before_download_reopen, dict) or \
                before_download_reopen.get("ok") is not True or \
                before_items.count(input_name) != 1 or save_name in before_items:
            raise CaptureError(f"{family} downloaded-file reopen nonce was stale: "
                               f"{before_download_reopen}")
        webdriver.execute("download.reopen.install", contract.INSTALL_OPEN, [save_name])
        webdriver.click("download.reopen.button.click", webdriver.element(
            "download.reopen.button.find", "#bw_fallback_capture_open"))
        download_file_element = webdriver.element(
            "download.reopen.file.find", "input[type=file]")
        webdriver.set_file("download.reopen.file.set", download_file_element, download_path)
        reopened_download = webdriver.wait(
            "download.reopen.wait", contract.OPEN_WAIT, 90,
            f"{family} downloaded .blend semantic reopen")
        reopened_result = reopened_download.get("result", {}) \
            if isinstance(reopened_download, dict) else {}
        if not isinstance(reopened_download, dict) or reopened_download.get("error") is not None or \
                reopened_result.get("name") != save_name or \
                reopened_result.get("size") != len(downloaded):
            raise CaptureError(f"{family} downloaded .blend could not be authoritatively reopened: "
                               f"{reopened_download}")
        download_reopen = webdriver.execute_async(
            "store.after_download_reopen", contract.STORE_AFTER_OPEN)
        reopen_items = download_reopen.get("list", {}).get("items", []) \
            if isinstance(download_reopen, dict) else []
        if not isinstance(download_reopen, dict) or download_reopen.get("ok") is not True or \
                reopen_items.count(input_name) != 1 or reopen_items.count(save_name) != 1 or \
                scene_semantics(download_reopen.get("scene")) != scene_semantics(after_open.get("scene")):
            raise CaptureError(f"{family} downloaded .blend semantic identity differs: "
                               f"{download_reopen}")
        webdriver.refresh()
        webdriver.wait("boot.wait", contract.BOOT_STATE, 600, f"{family} reload editor boot")
        product_reload = webdriver.execute_async("product.probe", contract.PRODUCT_PROBE)
        if not isinstance(product_reload, dict) or any(product_reload.get(key) is not True
                for key in ("ok", "workerDevice", "presented", "backend")):
            raise CaptureError(f"{family} reload Blender WebGPU proof failed: {product_reload}")
        reload_store = webdriver.execute_async("store.reload", contract.STORE_RELOAD, [input_name])
        if not isinstance(reload_store, dict) or reload_store.get("ok") is not True or \
                reload_store.get("count") != 1 or reload_store.get("opened", {}).get("size") != input_path.stat().st_size \
                or reload_store.get("opened", {}).get("name") != input_name or \
                scene_semantics(reload_store.get("scene")) != scene_semantics(after_open.get("scene")):
            raise CaptureError(f"{family} nonce-bound OPFS semantic reload failed: {reload_store}")
        diagnostics = webdriver.execute("diagnostics.final", contract.DIAGNOSTICS_FINAL)
        if not isinstance(diagnostics, dict) or diagnostics.get("observerSchema") != 1 or \
                diagnostics.get("observerPreload") is not True or diagnostics.get("external") or \
                diagnostics.get("page") or diagnostics.get("gpu") or \
                diagnostics.get("productWorkerDevice") is not True or diagnostics.get("productPresented") is not True:
            raise CaptureError(f"{family} runtime diagnostics are not clean: {diagnostics}")
    finally:
        webdriver.close()
    try:
        rows = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as error:
        raise CaptureError(f"{family} WebDriver transcript is unreadable") from error
    transcript_errors = contract.validate_transcript_rows(rows, family, navigation_url, capabilities_sha)
    if transcript_errors:
        raise CaptureError(transcript_errors[0])
    service_log = family_root / "webdriver-service.log"
    driver_errors = [line[:500] for line in service_log.read_text(
        encoding="utf-8", errors="replace").splitlines()
        if re.search(r"\b(?:panic|fatal|uncaught)\b", line, re.I)]
    if driver_errors:
        raise CaptureError(f"{family} WebDriver service recorded fatal errors: {driver_errors}")
    return {
        "family": family, "product": app_identity["product"], "version": app_identity["version"],
        "platform": f"macOS {platform.mac_ver()[0]} {platform.machine()}",
        "officialBrandedBinary": True, "binary": app_identity["binary"],
        "signing": app_identity["signing"],
        "session": {"requestedCapabilitiesSha256": capabilities_sha,
                    "observedBrowserName": str(observed.get("browserName", "")),
                    "observedBrowserVersion": str(observed.get("browserVersion", "")),
                    "observedPlatform": str(observed.get("platformName", "")),
                    "navigationUrl": navigation_url, "sessionIdSha256": session_hash},
        "environment": {"secureContext": True, "crossOriginIsolated": True,
                        "sharedArrayBuffer": True, "opfs": True,
                        "fileSystemAccessPickers": False, "earlyObserverInstalled": True},
        "renderer": {"status": "editor_booted", "webgpuBackend": "WebGPU",
                     "productWorkerDevice": True, "presentedFrame": True,
                     "initialScreenshot": file_record(family_root / "initial-canvas.png"),
                     "interactionScreenshot": file_record(family_root / "interaction-canvas.png"),
                     "initialPixels": initial_pixels, "interactionPixels": interaction_pixels,
                     "interactionMeanAbsoluteDifference": pixel_difference,
                     "initialScene": scene_semantics(product_initial.get("scene")),
                     "reloadScene": scene_semantics(product_reload.get("scene"))},
        "storage": {"nonceName": input_name, "absentBefore": True,
                    "singleEntryAfterOpen": True, "reloadCount": reload_store.get("count"),
                    "openBytes": input_path.stat().st_size, "semanticReloadEqual": True},
        "download": {"suggestedName": save_name, "completed": True,
                     "ackBytes": download_path.stat().st_size,
                     "browserDownloadPath": str(browser_download_path),
                     "movedIntoEvidence": family == "safari",
                     "artifact": file_record(download_path),
                     "semanticReopen": {"nonceName": save_name, "absentBefore": True,
                                        "singleEntryAfter": True, "openBytes": len(downloaded),
                                        "scene": scene_semantics(download_reopen.get("scene"))}},
        "requests": {"browserLoadedArtifacts": browser_assets, "externalRequestCount": 0},
        "errors": {"page": [], "gpu": [], "driver": []}, "input": file_record(input_path),
        "automationDriver": {**driver_identity, "launchCommand": command,
                             "launchCommandSha256": contract.json_sha256(command),
                             "processId": process_id, "serviceLog": file_record(service_log)},
        "webdriverTranscript": file_record(transcript), "verdict": "PASS",
    }


def write_receipt(receipt: dict[str, Any], root: Path) -> None:
    schema = load_json(SCHEMA, "fallback receipt schema")
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema,
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(receipt), key=lambda error: list(error.path))
    if errors:
        raise CaptureError("generated fallback receipt failed schema: " + errors[0].message)
    receipt_path = root / "receipt.json"
    payload = json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    write_exclusive(receipt_path, payload)
    selector = {
        "schema": contract.SELECTOR_SCHEMA,
        "label": receipt["label"],
        "path": str(receipt_path.relative_to(ROOT)),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    selector_temp = root / "selector.tmp"
    selector_payload = json.dumps(selector, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    # Publish only after receipt + evidence are durable and INCOMPLETE is gone.
    directory_fd = os.open(root, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    (root / "INCOMPLETE").unlink()
    directory_fd = os.open(root, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    write_exclusive(selector_temp, selector_payload)
    os.replace(selector_temp, root / "selector.json")
    directory_fd = os.open(root, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def resolve_driver(value: str | None, default: str | Path, family: str) -> Path:
    candidate = value or str(default)
    if "/" not in candidate:
        found = shutil.which(candidate)
        if not found:
            raise CaptureError(f"{family} WebDriver not found: {candidate}")
        candidate = found
    path = Path(candidate).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise CaptureError(f"{family} WebDriver is not executable: {path}")
    return path


def selfcheck() -> None:
    positive = 0
    negative = 0
    if PRODUCER != Path(__file__).resolve() or ROOT != PRODUCER.parents[2] or \
            not (ROOT / "GOAL.md").is_file():
        raise CaptureError("repository root is not derived from the producer path")
    positive += 1
    schema = load_json(SCHEMA, "fallback receipt schema")
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema"]["const"] == contract.SCHEMA
    positive += 1
    geckodriver_relative = Path(
        ".m8-browsers/geckodriver-v0.37.1-macos-aarch64/geckodriver")
    canonical_geckodriver = ROOT / geckodriver_relative
    assert DEFAULT_GECKODRIVER == canonical_geckodriver
    positive += 1
    validate_codesign_detail(
        "Executable=/fixture\nIdentifier=org.mozilla.firefox\n"
        "TeamIdentifier=43AQ936H96\n",
        "org.mozilla.firefox", "43AQ936H96", "fixture Firefox")
    positive += 1
    validate_codesign_detail(
        "Executable=/fixture\nIdentifier=com.apple.Safari\nTeamIdentifier=not set\n",
        "com.apple.Safari", "not set", "fixture Safari")
    positive += 1
    validate_capture_host("Darwin")
    positive += 1
    for detail in (
            "Identifier=org.mozilla.firefox\nTeamIdentifier=BADTEAM000\n",
            "Identifier=org.mozilla.firefox.alias\nTeamIdentifier=43AQ936H96\n",
            "Identifier=org.mozilla.firefox\nIdentifier=org.mozilla.firefox\n"
            "TeamIdentifier=43AQ936H96\n",
            "Identifier=org.mozilla.firefox\n"):
        try:
            validate_codesign_detail(
                detail, "org.mozilla.firefox", "43AQ936H96", "negative fixture")
        except CaptureError:
            negative += 1
        else:
            raise CaptureError("false-green codesign detail fixture passed")
    try:
        run_identity_command(
            ["__bw_m7_missing_identity_command__", "--version"], "negative fixture")
    except CaptureError:
        negative += 1
    else:
        raise CaptureError("missing identity command did not fail closed")
    for system_name in ("Linux", "Windows"):
        try:
            validate_capture_host(system_name)
        except CaptureError:
            negative += 1
        else:
            raise CaptureError(f"unsupported capture host passed: {system_name}")
    assert contract.geckodriver_release_matches(
        contract.GECKODRIVER_SHA256, contract.GECKODRIVER_VERSION_LINE)
    positive += 1
    assert not contract.geckodriver_release_matches(
        "0" * 64, contract.GECKODRIVER_VERSION_LINE)
    negative += 1
    assert not contract.geckodriver_release_matches(
        contract.GECKODRIVER_SHA256,
        contract.GECKODRIVER_VERSION_LINE.replace("0.37.1", "0.37.0", 1))
    negative += 1
    assert not contract.geckodriver_release_matches(
        contract.GECKODRIVER_SHA256, contract.GECKODRIVER_VERSION_LINE + " suffix")
    negative += 1
    freeze_source = (ROOT / "sandbox/final-source-freeze/freeze_release.py").read_text()
    for relative in CRITICAL_FROZEN_PATHS:
        assert f'"{relative}"' in freeze_source
        assert (ROOT / relative).is_file()
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", "fallback-20260815-r1")
    assert not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", "../escape")
    with tempfile.TemporaryDirectory(prefix="m7-freeze-boundary-") as temporary:
        fixture_root = Path(temporary)
        fake_receipt = fixture_root / "attacker-receipt.json"
        fake_receipt.write_text('{"schema":1,"verdict":"PASS"}\n', encoding="utf-8")
        assert contract.validate_canonical_source_freeze(
            ROOT, fake_receipt, freeze_release.REQUIRED_PROJECT_PATHS,
            freeze_release.REQUIRED_UPSTREAM_PATHS,
            freeze_release.VOLATILE_GENERATED_OUTPUTS)[2]
        repository = fixture_root / "repository"
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        target = fixture_root / "outside.bin"
        target.write_bytes(b"same bytes")
        alias = repository / "regular.bin"
        alias.symlink_to(target)
        manifest = fixture_root / "live.manifest.jsonl"
        manifest.write_text(json.dumps({
            "mode": "100644", "path": "regular.bin", "size": len(b"same bytes"),
            "sha256": hashlib.sha256(b"same bytes").hexdigest()}) + "\n", encoding="ascii")
        manifest_errors: list[str] = []
        contract._validate_manifest_current(repository, manifest, set(), manifest_errors)
        assert any("type/mode mismatch" in error for error in manifest_errors)
    windowed = (ROOT / "platform_web/shell/windowed.html").read_text()
    diagnostics_tag = '<script src="/diagnostics-bootstrap.js"></script>'
    assert windowed.count(diagnostics_tag) == 1
    assert windowed.index(diagnostics_tag) < windowed.index('<script src="/bin/blender_browser.js"></script>')
    diagnostics_source = (ROOT / "platform_web/shell/diagnostics-bootstrap.js").read_text()
    assert "installedBeforeProductScripts: true" in diagnostics_source
    assert "window.addEventListener(\"error\"" in diagnostics_source
    assert "window.addEventListener(\"unhandledrejection\"" in diagnostics_source
    producer_source = PRODUCER.read_text(encoding="utf-8")
    runtime_source = producer_source[:producer_source.index("\ndef selfcheck()")]
    readme_source = (HERE / "README.md").read_text(encoding="utf-8")
    stale_nested_driver = "sandbox/m8-launch-gate/" + ".downloads/geckodriver"
    assert stale_nested_driver not in runtime_source
    assert stale_nested_driver not in readme_source
    assert runtime_source.count('ROOT / ".m8-browsers/"') == 1
    assert str(geckodriver_relative) in readme_source
    assert "/Users/paws/blender-web/.m8-browsers" not in readme_source
    assert len(re.findall(r"(?m)^def capture_browser\(", producer_source)) == 1
    for forbidden in ("CAPABILITY_PROBE", "originalClick", "__bwFallbackDownload.blob",
                      "includes('input.blend')", 'openStore(\'input.blend\')'):
        assert forbidden not in runtime_source
    file_fixture = {"path": "/fixture/file", "bytes": 2000, "sha256": "0" * 64}
    log_fixture = {"path": "/fixture/log", "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}
    signing = {"identifier": "fixture", "team": "fixture", "valid": True}
    http_fixture = {"url": "http://127.0.0.1:1/index.html", "status": 200,
                    "bytes": 2000, "sha256": "0" * 64, "bundleSha256": "1" * 64}
    browser_http = {"name": "index.html", **http_fixture,
                    "headerBytes": "2000", "headerSha256": "0" * 64}
    scene = {"active": "Cube", "objectCount": 3, "objects": ["Camera", "Cube", "Light"],
             "meshVertices": 8, "mode": "OBJECT", "renderEngine": "BLENDER_EEVEE_NEXT"}
    pixels = {"width": 1280, "height": 720, "nonblackRatio": 0.5,
              "quantizedColors": 256, "pngBytes": 2000, "pngSha256": "2" * 64, "pass": True}
    driver = {"artifact": file_fixture, "version": "fixture", "signing": signing,
              "launchCommand": ["/fixture/driver", "--port", "1"],
              "launchCommandSha256": "3" * 64, "processId": 1, "serviceLog": log_fixture}
    browser_fixture = {
        "family": "firefox", "product": "Firefox", "version": "1", "platform": "fixture",
        "officialBrandedBinary": True, "binary": file_fixture, "signing": signing,
        "session": {"requestedCapabilitiesSha256": "4" * 64, "observedBrowserName": "firefox",
                    "observedBrowserVersion": "1", "observedPlatform": "mac",
                    "navigationUrl": "http://127.0.0.1:1/index.html?m7fallback=" + "a" * 32,
                    "sessionIdSha256": "5" * 64},
        "environment": {"secureContext": True, "crossOriginIsolated": True,
                        "sharedArrayBuffer": True, "opfs": True,
                        "fileSystemAccessPickers": False, "earlyObserverInstalled": True},
        "renderer": {"status": "editor_booted", "webgpuBackend": "WebGPU",
                     "productWorkerDevice": True, "presentedFrame": True,
                     "initialScreenshot": file_fixture, "interactionScreenshot": file_fixture,
                     "initialPixels": pixels, "interactionPixels": pixels,
                     "interactionMeanAbsoluteDifference": 1.0,
                     "initialScene": scene, "reloadScene": scene},
        "storage": {"nonceName": "fallback-fixture-" + "a" * 32 + ".blend",
                    "absentBefore": True, "singleEntryAfterOpen": True,
                    "reloadCount": 1, "openBytes": 2000, "semanticReloadEqual": True},
        "download": {"suggestedName": "fallback-save-fixture-" + "a" * 32 + ".blend",
                     "completed": True, "ackBytes": 2000,
                     "browserDownloadPath": "/fixture/file", "movedIntoEvidence": False,
                     "artifact": file_fixture,
                     "semanticReopen": {
                         "nonceName": "fallback-save-fixture-" + "a" * 32 + ".blend",
                         "absentBefore": True, "singleEntryAfter": True,
                         "openBytes": 2000, "scene": scene}},
        "requests": {"browserLoadedArtifacts": [browser_http], "externalRequestCount": 0},
        "errors": {"page": [], "gpu": [], "driver": []}, "input": file_fixture,
        "automationDriver": driver,
        "webdriverTranscript": file_fixture, "verdict": "PASS",
    }
    safari_fixture = dict(browser_fixture, family="safari", product="Safari")
    receipt_fixture = {
        "schema": contract.SCHEMA, "label": "fixture", "nonce": "a" * 32,
        "createdUtc": "2026-08-15T00:00:00Z", "immutable": True, "verdict": "PASS",
        "evidenceRoot": "/fixture", "sourceFreeze": file_fixture, "producer": file_fixture,
        "server": {"baseUrl": "http://127.0.0.1:1", "servedBundleSha256": "1" * 64,
                   "artifacts": {"index.html": http_fixture}},
        "bundleArtifacts": {"index.html": file_fixture},
        "browsers": [browser_fixture, safari_fixture],
    }
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)
    validator.validate(receipt_fixture)
    false_green = json.loads(json.dumps(receipt_fixture))
    false_green["browsers"][0]["renderer"]["productWorkerDevice"] = False
    assert list(validator.iter_errors(false_green))
    false_green = json.loads(json.dumps(receipt_fixture))
    false_green["browsers"][0]["storage"]["absentBefore"] = False
    assert list(validator.iter_errors(false_green))
    false_green = json.loads(json.dumps(receipt_fixture))
    false_green["browsers"][0]["download"]["completed"] = False
    assert list(validator.iter_errors(false_green))
    print(f"M7_FALLBACK_CAPTURE_SELFCHECK_PASS schema=v4 branded=firefox+safari "
          "source_freeze=full-resnapshot selector=per-label-atomic "
          "driver=canonical-root-level-geckodriver+exact-full-version-line "
          f"host_root={ROOT} positive={positive} negative={negative} browser_launches=0 "
          "negatives=product-worker+stale-opfs+synthetic-download+stale-nested-driver+"
          "geckodriver-hash+version+suffix")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label")
    parser.add_argument("--source-freeze", type=Path)
    parser.add_argument("--base", default="http://127.0.0.1:8168")
    parser.add_argument("--geckodriver")
    parser.add_argument("--safaridriver")
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--preflight", action="store_true",
                        help="validate frozen source, bundle server, signed apps, and drivers only")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.selfcheck:
        selfcheck()
        return 0
    if not args.label or args.source_freeze is None:
        raise CaptureError("--label and --source-freeze are required")
    validate_capture_host(platform.system())
    freeze_time = validate_source_freeze(args.source_freeze)
    if freeze_time > dt.datetime.now(dt.timezone.utc):
        raise CaptureError("source freeze is future-dated")
    artifacts = bundle_artifacts()
    server = validate_server(args.base, artifacts)
    firefox = plist_identity(FIREFOX_APP, FIREFOX_BINARY, "org.mozilla.firefox", "43AQ936H96")
    safari = plist_identity(SAFARI_APP, SAFARI_BINARY, "com.apple.Safari", "not set")
    geckodriver = resolve_driver(args.geckodriver, DEFAULT_GECKODRIVER, "Firefox")
    safaridriver = resolve_driver(args.safaridriver, SAFARIDRIVER, "Safari")
    geckodriver_identity = signed_driver_identity(
        geckodriver, "firefox", str(firefox["version"]))
    safaridriver_identity = signed_driver_identity(
        safaridriver, "safari", str(safari["version"]))
    if args.preflight:
        print(f"M7_FALLBACK_PREFLIGHT_PASS bundle_files={len(artifacts)} "
              f"firefox={firefox['version']} safari={safari['version']} "
              f"geckodriver={geckodriver} safaridriver={safaridriver}")
        return 0
    root = reserve_label(args.label)
    nonce = secrets.token_hex(16)
    try:
        browsers = [
            capture_browser("firefox", root, args.base, geckodriver,
                            geckodriver_identity, firefox, artifacts, args.label, nonce),
            capture_browser("safari", root, args.base, safaridriver,
                            safaridriver_identity, safari, artifacts, args.label, nonce),
        ]
        # Close long-running capture races: source, exact staged bytes, and server
        # delivery must still match immediately before immutable publication.
        validate_source_freeze(args.source_freeze)
        if bundle_artifacts() != artifacts:
            raise CaptureError("staged bundle changed during fallback capture")
        if validate_server(args.base, artifacts) != server:
            raise CaptureError("exact-tree server delivery changed during fallback capture")
        created = utc_now()
        if parse_utc(created, "fallback createdUtc") < freeze_time:
            raise CaptureError("fallback receipt predates source freeze")
        receipt = {
            "schema": contract.SCHEMA,
            "label": args.label,
            "nonce": nonce,
            "createdUtc": created,
            "immutable": True,
            "verdict": "PASS",
            "evidenceRoot": str(root.resolve()),
            "sourceFreeze": file_record(args.source_freeze.resolve(strict=True)),
            "producer": file_record(PRODUCER),
            "server": server,
            "bundleArtifacts": artifacts,
            "browsers": browsers,
        }
        write_receipt(receipt, root)
    except BaseException as error:
        failed = root / "FAILED.txt"
        if not failed.exists():
            write_exclusive(failed, f"{type(error).__name__}: {error}\n".encode("utf-8"))
        raise
    print(f"M7_FALLBACK_CAPTURE_PASS label={args.label} receipt={root / 'receipt.json'} "
          f"selector={root / 'selector.json'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CaptureError as error:
        print(f"M7_FALLBACK_CAPTURE_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
