#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared, source-frozen contract for branded fallback evidence."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import zlib
from typing import Any
from urllib.parse import quote, unquote_to_bytes


SCHEMA = "blender-web.m7-cross-browser-fallback.v4"
SELECTOR_SCHEMA = "blender-web.m7-fallback-selector.v2"
GECKODRIVER_VERSION = "0.37.1"
GECKODRIVER_VERSION_LINE = (
    "geckodriver 0.37.1 (300705c65d1b 2026-07-17 09:25 +0000)"
)
GECKODRIVER_SHA256 = "5d82307edc8549124bd4e7b6f275e1228e0a530e5abbfb294be3f310486561a4"
GECKODRIVER_IDENTIFIER = "geckodriver"
GECKODRIVER_TEAM = "43AQ936H96"
SAFARIDRIVER = Path("/System/Cryptexes/App/usr/bin/safaridriver")
DIAGNOSTICS_MARKER = "__bwEarlyDiagnostics"
ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"
CANONICAL_FREEZE_ROOT = Path("/Users/paws/blender-web-final-source-freeze")
CANONICAL_FREEZE_RECEIPT = CANONICAL_FREEZE_ROOT / "receipt.json"
FREEZE_TOP_KEYS = {"schema", "verdict", "created_utc", "project", "upstream",
                   "coverage", "final_paired_resnapshot", "checks"}
FREEZE_CHECKS = {
    "repositories_disjoint", "project_component_pass", "upstream_component_pass",
    "technical_release_inputs_present", "cross_root_resnapshot_byte_exact",
    "final_overlapping_double_resnapshot", "both_heads_and_real_indexes_stable",
    "outputs_created_without_overwrite",
}
COMPONENT_CHECKS = {
    "source_head_exact_pin", "source_real_index_pristine",
    "source_repository_operation_idle", "initialized_submodules_clean",
    "replay_started_pristine", "patch_regenerated_byte_exact",
    "manifest_replay_byte_exact", "live_resnapshot_byte_exact",
    "pin_and_ignore_inputs_stable", "outputs_created_without_overwrite",
}
COMPONENT_KEYS = {"schema", "verdict", "created_utc", "source", "expected_pin",
                  "recorded_pin_file", "git_version", "patch", "live_manifest",
                  "replay_manifest", "ignored_worktree_paths", "checks"}


BOOT_STATE = """
const state = document.querySelector('#state')?.textContent || '';
return state.includes('main loop (WM_main)') && !!window.__bwModule &&
  !!window.BWFileBridge && window.__bwStage1?.phase === 'done' &&
  !window.__bwStage1?.error && window.__bwServiceWorker?.phase === 'done';
"""

ENVIRONMENT_PROBE = """
return {secure:isSecureContext,coi:crossOriginIsolated,
  sab:typeof SharedArrayBuffer==='function',opfs:!!navigator.storage?.getDirectory,
  fsa:typeof showOpenFilePicker==='function'||typeof showSaveFilePicker==='function',
  observerSchema:window.__bwEarlyDiagnostics?.schema||null,
  observerPreload:window.__bwEarlyDiagnostics?.installedBeforeProductScripts===true};
"""

BUNDLE_PROBE = """
const specs=arguments[0],done=arguments[arguments.length-1];
(async()=>{const rows=[];for(const spec of specs){
  const response=await fetch('/'+spec.name,{cache:'no-store',credentials:'same-origin',redirect:'error'});
  const bytes=new Uint8Array(await response.arrayBuffer());
  const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',bytes));
  const sha=Array.from(digest,v=>v.toString(16).padStart(2,'0')).join('');
  rows.push({name:spec.name,url:response.url,status:response.status,bytes:bytes.length,sha256:sha,
    headerBytes:response.headers.get('X-BW-Content-Bytes'),
    headerSha256:response.headers.get('X-BW-Content-SHA256'),
    bundleSha256:response.headers.get('X-BW-Bundle-SHA256')});
}done({ok:true,artifacts:rows});})().catch(error=>done({ok:false,error:String(error)}));
"""

PRODUCT_PROBE = """
const done=arguments[arguments.length-1];(async()=>{try{
 const log=document.querySelector('#log')?.textContent||'';
 const scene=await window.BWFileBridge.inspectScene();
 done({ok:true,scene,state:document.querySelector('#state')?.textContent||'',
  stage1:window.__bwStage1?.phase||null,serviceWorker:window.__bwServiceWorker?.phase||null,
  workerDevice:/WM-worker WebGPU device pre-acquired/.test(log),
  presented:/presentBackbuffer frame/.test(log),
  backend:/WebGPU|WGPUWeb/.test(log),canvas:[document.querySelector('#canvas')?.width||0,
    document.querySelector('#canvas')?.height||0]});
}catch(error){done({ok:false,error:String(error)})}})();
"""

STORE_BEFORE = """
const done=arguments[arguments.length-1];window.BWFileBridge.listStore().then(done,
 error=>done({ok:false,error:String(error)}));
"""

INSTALL_OPEN = """
const name=arguments[0];document.querySelector('#bw_fallback_capture_open')?.remove();
window.__bwFallbackOpen={done:false,error:null,result:null};
const button=document.createElement('button');button.id='bw_fallback_capture_open';
button.textContent='open';button.style='position:fixed;left:2px;top:2px;z-index:99999';
button.onclick=()=>window.BWFileBridge.openFromDisk().then(result=>{
 window.__bwFallbackOpen={done:true,error:null,result,name};},error=>{
 window.__bwFallbackOpen={done:true,error:String(error),result:null,name};});
document.body.appendChild(button);return true;
"""

OPEN_WAIT = "return window.__bwFallbackOpen?.done ? window.__bwFallbackOpen : false;"

STORE_AFTER_OPEN = """
const done=arguments[arguments.length-1];(async()=>{try{done({ok:true,
 list:await window.BWFileBridge.listStore(),scene:await window.BWFileBridge.inspectScene()});}
catch(error){done({ok:false,error:String(error)})}})();
"""

INSTALL_DOWNLOAD = """
const name=arguments[0];document.querySelector('#bw_fallback_capture_save')?.remove();
window.__bwFallbackDownload={done:false,error:null,result:null};
const button=document.createElement('button');button.id='bw_fallback_capture_save';
button.textContent='save';button.style='position:fixed;left:2px;top:32px;z-index:99999';
button.onclick=()=>window.BWFileBridge.saveToDisk(name).then(result=>{
 window.__bwFallbackDownload={done:true,error:null,result};},error=>{
 window.__bwFallbackDownload={done:true,error:String(error),result:null};});
document.body.appendChild(button);return true;
"""

DOWNLOAD_WAIT = """
return window.__bwFallbackDownload?.done ? {error:window.__bwFallbackDownload.error,
 via:window.__bwFallbackDownload.result?.via||null,
 ack:window.__bwFallbackDownload.result?.ack||null} : false;
"""

STORE_RELOAD = """
const name=arguments[0],done=arguments[arguments.length-1];(async()=>{try{
 const list=await window.BWFileBridge.listStore();
 const count=(list.items||[]).filter(item=>item===name).length;
 const opened=count===1?await window.BWFileBridge.openStore(name):null;
 const scene=opened?.ok?await window.BWFileBridge.inspectScene():null;
 done({ok:true,list,count,opened,scene});
}catch(error){done({ok:false,error:String(error)})}})();
"""

DIAGNOSTICS_FINAL = """
const origin=location.origin;
const external=performance.getEntriesByType('resource').map(entry=>entry.name).filter(url=>{
 try{return new URL(url,location.href).origin!==origin}catch(_){return true}});
const log=document.querySelector('#log')?.textContent||'';
return {observerSchema:window.__bwEarlyDiagnostics?.schema||null,
 observerPreload:window.__bwEarlyDiagnostics?.installedBeforeProductScripts===true,
 page:window.__bwEarlyDiagnostics?.snapshot?.()||null,external,
 gpu:Array.from(log.matchAll(/.*(?:ValidationError|GPU-ERROR|GPU-LOST|uncaptured WebGPU error).*/gi),m=>m[0]),
 productWorkerDevice:/WM-worker WebGPU device pre-acquired/.test(log),
 productPresented:/presentBackbuffer frame/.test(log)};
"""

SCRIPT_BY_OPERATION = {
    "boot.wait": BOOT_STATE,
    "environment.probe": ENVIRONMENT_PROBE,
    "bundle.probe": BUNDLE_PROBE,
    "product.probe": PRODUCT_PROBE,
    "store.before": STORE_BEFORE,
    "open.install": INSTALL_OPEN,
    "open.wait": OPEN_WAIT,
    "store.after_open": STORE_AFTER_OPEN,
    "store.before_download_reopen": STORE_BEFORE,
    "download.reopen.install": INSTALL_OPEN,
    "download.reopen.wait": OPEN_WAIT,
    "store.after_download_reopen": STORE_AFTER_OPEN,
    "download.install": INSTALL_DOWNLOAD,
    "download.wait": DOWNLOAD_WAIT,
    "store.reload": STORE_RELOAD,
    "diagnostics.final": DIAGNOSTICS_FINAL,
}


def geckodriver_release_matches(sha256_value: str, version_line: str) -> bool:
    """Return true only for the exact source-frozen official driver release."""
    return sha256_value == GECKODRIVER_SHA256 and version_line == GECKODRIVER_VERSION_LINE

EXPECTED_PHASES = (
    "webdriver.status", "session.create", "session.timeouts", "navigation.open",
    "boot.wait", "environment.probe", "bundle.probe", "product.probe",
    "canvas.screenshot.initial", "store.before", "open.install", "open.button.find",
    "open.button.click", "file.input.find", "file.input.set", "open.wait",
    "store.after_open", "canvas.orbit", "canvas.screenshot.interaction",
    "download.install", "download.button.find", "download.button.click", "download.wait",
    "store.before_download_reopen", "download.reopen.install",
    "download.reopen.button.find", "download.reopen.button.click",
    "download.reopen.file.find", "download.reopen.file.set", "download.reopen.wait",
    "store.after_download_reopen",
    "navigation.refresh", "boot.wait", "product.probe", "store.reload",
    "diagnostics.final", "session.delete",
)

ORBIT_ACTIONS = {"actions": [{"type": "pointer", "id": "mouse",
    "parameters": {"pointerType": "mouse"}, "actions": [
        {"type": "pointerMove", "duration": 0, "origin": {"element-6066-11e4-a52e-4f735466cecf": "__ELEMENT__"}, "x": 0, "y": 0},
        {"type": "pointerDown", "button": 1},
        {"type": "pointerMove", "duration": 350, "origin": "pointer", "x": 80, "y": 40},
        {"type": "pointerUp", "button": 1},
    ]}]}


def json_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def script_sha256(script: str) -> str:
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def _file_identity(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def _real_directory(path: Path, label: str, errors: list[str]) -> bool:
    try:
        info = path.lstat()
        valid = stat.S_ISDIR(info.st_mode) and not path.is_symlink() and path.resolve() == path
    except OSError:
        valid = False
    if not valid:
        errors.append(f"{label} is not a canonical real directory: {path}")
    return valid


def _safe_current_path(root: Path, raw: bytes, errors: list[str]) -> Path | None:
    relative = os.fsdecode(raw)
    candidate = root / relative
    try:
        candidate.relative_to(root)
    except ValueError:
        errors.append(f"freeze manifest path escapes source root: {relative!r}")
        return None
    if raw.startswith(b"/") or b"\0" in raw or any(part in {b"", b".", b".."}
                                                       for part in raw.split(b"/")):
        errors.append(f"freeze manifest path is noncanonical: {relative!r}")
        return None
    current = root
    for part in raw.split(b"/")[:-1]:
        current = current / os.fsdecode(part)
        try:
            info = current.lstat()
        except OSError:
            errors.append(f"freeze manifest parent disappeared: {relative!r}")
            return None
        if not stat.S_ISDIR(info.st_mode) or current.is_symlink():
            errors.append(f"freeze manifest parent is indirect/non-directory: {relative!r}")
            return None
    return candidate


def _validate_manifest_current(root: Path, manifest: Path, volatile: set[str],
                               errors: list[str]) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    raw_names: set[bytes] = set()
    try:
        lines = manifest.read_bytes().splitlines()
    except OSError as error:
        errors.append(f"cannot read canonical freeze manifest: {manifest}: {error}")
        return rows
    allowed_modes = {"100644", "100755", "120000", "160000"}
    for number, line in enumerate(lines, 1):
        try:
            row = json.loads(line, object_pairs_hook=strict_json_object)
            if not isinstance(row, dict) or set(row) != {"mode", "path", "sha256", "size"}:
                raise ValueError("row keys")
            encoded = row["path"]
            if not isinstance(encoded, str):
                raise ValueError("path type")
            raw = unquote_to_bytes(encoded)
            if raw in raw_names:
                raise ValueError("duplicate path")
            if row["mode"] not in allowed_modes or not isinstance(row["size"], int) or \
                    row["size"] < 0 or not isinstance(row["sha256"], str) or \
                    re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None:
                raise ValueError("row identity")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            errors.append(f"invalid canonical freeze manifest row {number}: {error}")
            continue
        raw_names.add(raw)
        relative = os.fsdecode(raw)
        rows[relative] = row
        current = _safe_current_path(root, raw, errors)
        if current is None:
            continue
        mode = str(row["mode"])
        try:
            info = current.lstat()
            if mode in {"100644", "100755"}:
                expected_mode = "100755" if info.st_mode & 0o111 else "100644"
                if not stat.S_ISREG(info.st_mode) or current.is_symlink() or expected_mode != mode:
                    raise ValueError("regular-file type/mode mismatch")
                payload_size, payload_sha = info.st_size, _file_identity(current)["sha256"]
            elif mode == "120000":
                if not stat.S_ISLNK(info.st_mode):
                    raise ValueError("symlink type mismatch")
                payload = os.fsencode(os.readlink(current))
                payload_size, payload_sha = len(payload), hashlib.sha256(payload).hexdigest()
            else:
                if not stat.S_ISDIR(info.st_mode) or current.is_symlink():
                    raise ValueError("gitlink worktree type mismatch")
                staged = subprocess.run(
                    ["git", "-C", str(root), "ls-files", "--stage", "-z", "--", relative],
                    capture_output=True, check=False)
                fields = staged.stdout.rstrip(b"\0").split(None, 3)
                if staged.returncode != 0 or len(fields) != 4 or fields[0] != b"160000" or \
                        fields[2] != b"0" or fields[3] != raw:
                    raise ValueError("gitlink index identity mismatch")
                payload = fields[1]
                payload_size, payload_sha = len(payload), hashlib.sha256(payload).hexdigest()
            if relative not in volatile and (row["size"] != payload_size or
                                              row["sha256"] != payload_sha):
                raise ValueError("content identity mismatch")
        except (OSError, ValueError) as error:
            errors.append(f"current frozen path mismatch {relative!r}: {error}")
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
        capture_output=True, check=False)
    if listed.returncode != 0:
        errors.append(f"cannot enumerate current frozen source: {root}")
    else:
        actual = {value for value in listed.stdout.split(b"\0") if value}
        allowed_volatile = {os.fsencode(value) for value in volatile}
        extras = sorted(actual - raw_names - allowed_volatile)
        if extras:
            errors.append("source gained paths after canonical freeze: " +
                          ", ".join(os.fsdecode(value) for value in extras[:20]))
    return rows


def validate_canonical_source_freeze(project_root: Path, receipt_path: Path,
                                     required_project: tuple[str, ...],
                                     required_upstream: tuple[str, ...],
                                     volatile: tuple[str, ...]) -> tuple[dict[str, Any],
                                                                         dict[str, dict],
                                                                         list[str]]:
    """Validate the exact composite producer contract and both current source roots."""
    errors: list[str] = []
    if receipt_path != CANONICAL_FREEZE_RECEIPT:
        return {}, {}, [f"source freeze must be exact canonical receipt: {CANONICAL_FREEZE_RECEIPT}"]
    if not _real_directory(CANONICAL_FREEZE_ROOT, "canonical freeze root", errors):
        return {}, {}, errors
    _real_directory(project_root, "canonical project source root", errors)
    _real_directory(project_root / "upstream", "canonical upstream source root", errors)
    try:
        if {entry.name for entry in CANONICAL_FREEZE_ROOT.iterdir()} != {
                "receipt.json", "project", "upstream"}:
            errors.append("canonical freeze root tree is not exact")
        receipt_info = receipt_path.lstat()
        if not stat.S_ISREG(receipt_info.st_mode) or receipt_path.is_symlink():
            errors.append("canonical freeze receipt is not a real regular file")
            return {}, {}, errors
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"),
                             object_pairs_hook=strict_json_object)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {}, {}, errors + [f"canonical freeze receipt is unreadable: {error}"]
    if not isinstance(receipt, dict) or set(receipt) != FREEZE_TOP_KEYS or \
            receipt.get("schema") != 1 or receipt.get("verdict") != "PASS":
        errors.append("canonical freeze top receipt/schema/keys are not exact")
        return receipt if isinstance(receipt, dict) else {}, {}, errors
    if receipt.get("checks") != {name: True for name in FREEZE_CHECKS}:
        errors.append("canonical freeze check set is not exact")
    expected_coverage = {
        "policy": "all project+upstream source byte-exact; exact generator-owned outputs independently post-bound",
        "required_paths": list(required_project),
        "required_paths_present": len(required_project),
        "required_upstream_paths": list(required_upstream),
        "required_upstream_paths_present": len(required_upstream),
        "volatile_generated_outputs": list(volatile),
    }
    if receipt.get("coverage") != expected_coverage:
        errors.append("canonical freeze required coverage contract differs")
    if receipt.get("final_paired_resnapshot") != {
            "policy": "nested overlapping live resnapshots immediately before publication",
            "order": ["project", "upstream", "upstream", "project"],
            "checks_per_root": 2}:
        errors.append("canonical freeze paired-resnapshot contract differs")
    project_rows: dict[str, dict] = {}
    for name, source_root in (("project", project_root), ("upstream", project_root / "upstream")):
        component_dir = CANONICAL_FREEZE_ROOT / name
        if not _real_directory(component_dir, f"canonical {name} component", errors):
            continue
        try:
            if {entry.name for entry in component_dir.iterdir()} != {
                    "canonical-source.patch", "live.manifest.jsonl",
                    "replay.manifest.jsonl", "receipt.json"}:
                errors.append(f"canonical {name} component tree is not exact")
            for child in component_dir.iterdir():
                info = child.lstat()
                if child.is_symlink() or not stat.S_ISREG(info.st_mode):
                    errors.append(f"canonical {name} component contains indirect/non-file entry")
            component_receipt_path = component_dir / "receipt.json"
            component = json.loads(component_receipt_path.read_text(encoding="utf-8"),
                                   object_pairs_hook=strict_json_object)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"canonical {name} component is unreadable: {error}")
            continue
        top_identity = receipt.get(name)
        if not isinstance(top_identity, dict) or set(top_identity) != {
                "directory", "receipt_sha256", "patch", "live_manifest"}:
            errors.append(f"canonical {name} top identity is not exact")
            continue
        if not isinstance(component, dict) or set(component) != COMPONENT_KEYS or \
                component.get("schema") != 1 or component.get("verdict") != "PASS" or \
                component.get("checks") != {check: True for check in COMPONENT_CHECKS}:
            errors.append(f"canonical {name} component receipt contract differs")
            continue
        ignored = component.get("ignored_worktree_paths")
        if not isinstance(ignored, dict) or set(ignored) != {
                "policy", "count", "nul_list_sha256"} or \
                ignored.get("policy") != "excluded by the repository's standard Git ignore rules" or \
                not isinstance(ignored.get("count"), int) or ignored.get("count") < 0 or \
                re.fullmatch(r"[0-9a-f]{64}", str(ignored.get("nul_list_sha256", ""))) is None:
            errors.append(f"canonical {name} ignored-path contract differs")
        current_git_version = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, check=False).stdout.strip()
        if component.get("git_version") != current_git_version or \
                re.fullmatch(r"[0-9a-f]{40,64}", str(component.get("expected_pin", ""))) is None:
            errors.append(f"canonical {name} producer/version pin identity differs")
        expected_pin = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False).stdout.strip()
        if component.get("source") != str(source_root) or component.get("expected_pin") != expected_pin:
            errors.append(f"canonical {name} component source/pin differs")
        recorded_pin = component.get("recorded_pin_file")
        if name == "project":
            if recorded_pin is not None:
                errors.append("canonical project component unexpectedly records a pin file")
        else:
            pin_path = project_root / "oracle/PIN"
            if recorded_pin != {"path": str(pin_path), "sha256": _file_identity(pin_path)["sha256"]}:
                errors.append("canonical upstream component pin-file identity differs")
        patch = component_dir / "canonical-source.patch"
        live = component_dir / "live.manifest.jsonl"
        replay = component_dir / "replay.manifest.jsonl"
        expected_patch = {"path": patch.name, **_file_identity(patch)}
        expected_live = {"path": live.name,
                         "entries": len(live.read_bytes().splitlines()), **_file_identity(live)}
        expected_replay = {"path": replay.name,
                           "entries": len(replay.read_bytes().splitlines()), **_file_identity(replay)}
        if component.get("patch") != expected_patch or component.get("live_manifest") != expected_live or \
                component.get("replay_manifest") != expected_replay or live.read_bytes() != replay.read_bytes():
            errors.append(f"canonical {name} component artifacts differ from receipt")
        if top_identity != {"directory": name,
                            "receipt_sha256": _file_identity(component_receipt_path)["sha256"],
                            "patch": expected_patch, "live_manifest": expected_live}:
            errors.append(f"canonical {name} top/component identity differs")
        rows = _validate_manifest_current(source_root, live,
                                          set(volatile) if name == "project" else set(), errors)
        if name == "project":
            project_rows = rows
    return receipt, project_rows, errors


def validate_transcript_rows(rows: object, family: str, navigation_url: str,
                             capabilities_sha256: str) -> list[str]:
    """Return fail-closed transcript errors; used by verifier and adversarial tests."""
    errors: list[str] = []
    if not isinstance(rows, list) or not rows or len(rows) % 2:
        return [f"{family} transcript must contain request/response pairs"]
    operations: list[str] = []
    session_id: str | None = None
    occurrence_counts: dict[str, int] = {}
    element_ids: dict[str, str] = {}
    async_scripts = {"bundle.probe", "product.probe", "store.before",
                     "store.after_open", "store.before_download_reopen",
                     "store.after_download_reopen", "store.reload"}
    for offset in range(0, len(rows), 2):
        request, response = rows[offset:offset + 2]
        if not isinstance(request, dict) or not isinstance(response, dict):
            errors.append(f"{family} transcript pair is not object-valued")
            continue
        expected_keys = {"sequence", "direction", "operation", "payload"}
        if set(request) != expected_keys or set(response) != expected_keys:
            errors.append(f"{family} transcript row keys are not exact")
            continue
        if request["sequence"] != offset + 1 or response["sequence"] != offset + 2:
            errors.append(f"{family} transcript sequence is not contiguous")
        operation = request.get("operation")
        if request.get("direction") != "request" or response.get("direction") != "response" \
                or response.get("operation") != operation or not isinstance(operation, str):
            errors.append(f"{family} transcript request/response ordering is invalid")
            continue
        operations.append(operation)
        occurrence_counts[operation] = occurrence_counts.get(operation, 0) + 1
        req = request.get("payload")
        res = response.get("payload")
        if not isinstance(req, dict) or set(req) != {"method", "path", "body"}:
            errors.append(f"{family} transcript request payload is not exact")
            continue
        if not isinstance(res, dict) or set(res) != {"status", "body"} \
                or not isinstance(res.get("status"), int) or not 200 <= res["status"] < 300:
            errors.append(f"{family} transcript response is not a successful exact response")
            continue
        path = req.get("path")
        if operation == "session.create":
            if req.get("method") != "POST" or path != "/session" or \
                    json_sha256(req.get("body", {}).get("capabilities", {}).get("alwaysMatch")) != capabilities_sha256:
                errors.append(f"{family} transcript session capabilities mismatch")
            value = res["body"].get("value", {}) if isinstance(res["body"], dict) else {}
            session_id = value.get("sessionId") if isinstance(value, dict) else None
            if not isinstance(session_id, str) or not session_id:
                errors.append(f"{family} transcript session response has no ID")
        elif operation == "webdriver.status":
            if req.get("method") != "GET" or path != "/status" or req.get("body") is not None:
                errors.append(f"{family} transcript status path mismatch")
        else:
            prefix = f"/session/{quote(session_id or '', safe='')}"
            if not session_id or not isinstance(path, str) or not path.startswith(prefix):
                errors.append(f"{family} transcript request is not bound to its one session")
            if operation == "navigation.open" and req.get("body") != {"url": navigation_url}:
                errors.append(f"{family} transcript navigation URL mismatch")
            if operation in SCRIPT_BY_OPERATION:
                body = req.get("body")
                if not isinstance(body, dict) or set(body) != {"script", "args"} or \
                        body.get("script") != SCRIPT_BY_OPERATION[operation] or \
                        not isinstance(body.get("args"), list):
                    errors.append(f"{family} transcript script mismatch: {operation}")
                suffix = "/execute/async" if operation in async_scripts else "/execute/sync"
                if req.get("method") != "POST" or path != prefix + suffix:
                    errors.append(f"{family} transcript script endpoint mismatch: {operation}")
            expected_suffixes = {
                "session.timeouts": ("POST", "/timeouts"),
                "navigation.open": ("POST", "/url"),
                "navigation.refresh": ("POST", "/refresh"),
                "open.button.find": ("POST", "/element"),
                "open.button.click": ("POST", "/click"),
                "file.input.find": ("POST", "/element"),
                "file.input.set": ("POST", "/value"),
                "canvas.orbit": ("POST", "/actions"),
                "download.button.find": ("POST", "/element"),
                "download.button.click": ("POST", "/click"),
                "download.reopen.button.find": ("POST", "/element"),
                "download.reopen.button.click": ("POST", "/click"),
                "download.reopen.file.find": ("POST", "/element"),
                "download.reopen.file.set": ("POST", "/value"),
                "session.delete": ("DELETE", ""),
            }
            if operation in expected_suffixes:
                expected_method, suffix = expected_suffixes[operation]
                if req.get("method") != expected_method or (path != prefix + suffix
                        if suffix in {"", "/timeouts", "/url", "/refresh", "/element", "/actions"}
                        else not path.endswith(suffix)):
                    errors.append(f"{family} transcript endpoint mismatch: {operation}")
            if operation == "session.timeouts" and req.get("body") != {
                    "script": 240000, "pageLoad": 240000, "implicit": 0}:
                errors.append(f"{family} transcript timeout contract mismatch")
            if operation == "navigation.refresh" and req.get("body") != {}:
                errors.append(f"{family} transcript refresh body mismatch")
            if operation == "session.delete" and req.get("body") is not None:
                errors.append(f"{family} transcript delete body mismatch")
            selectors = {
                "open.button.find": "#bw_fallback_capture_open",
                "file.input.find": "input[type=file]",
                "download.button.find": "#bw_fallback_capture_save",
                "download.reopen.button.find": "#bw_fallback_capture_open",
                "download.reopen.file.find": "input[type=file]",
            }
            if operation in selectors:
                if req.get("body") != {"using": "css selector", "value": selectors[operation]}:
                    errors.append(f"{family} transcript selector mismatch: {operation}")
                value = res.get("body", {}).get("value", {}) if isinstance(res.get("body"), dict) else {}
                element_id = value.get(ELEMENT_KEY) if isinstance(value, dict) else None
                if not isinstance(element_id, str) or not element_id:
                    errors.append(f"{family} transcript element response mismatch: {operation}")
                else:
                    element_ids[operation] = element_id
            click_sources = {
                "open.button.click": "open.button.find",
                "download.button.click": "download.button.find",
                "download.reopen.button.click": "download.reopen.button.find",
            }
            if operation in click_sources:
                element_id = element_ids.get(click_sources[operation])
                if not element_id or path != prefix + f"/element/{quote(element_id, safe='')}/click" \
                        or req.get("body") != {}:
                    errors.append(f"{family} transcript click is not bound to its element: {operation}")
            if operation == "file.input.set":
                element_id = element_ids.get("file.input.find")
                body = req.get("body")
                if not element_id or path != prefix + f"/element/{quote(element_id, safe='')}/value" or \
                        not isinstance(body, dict) or set(body) != {"text", "value"} or \
                        not isinstance(body.get("text"), str) or body.get("value") != list(body["text"]):
                    errors.append(f"{family} transcript file input is not bound to its element")
            if operation == "download.reopen.file.set":
                element_id = element_ids.get("download.reopen.file.find")
                body = req.get("body")
                if not element_id or path != prefix + f"/element/{quote(element_id, safe='')}/value" or \
                        not isinstance(body, dict) or set(body) != {"text", "value"} or \
                        not isinstance(body.get("text"), str) or body.get("value") != list(body["text"]):
                    errors.append(f"{family} downloaded-file reopen is not bound to its chooser")
            if operation == "canvas.screenshot.initial":
                occurrence = occurrence_counts[operation]
                valid = occurrence == 1 and req.get("method") == "POST" and \
                    path == prefix + "/element" and req.get("body") == {
                        "using": "css selector", "value": "#canvas"}
                if valid:
                    value = res.get("body", {}).get("value", {}) if isinstance(res.get("body"), dict) else {}
                    canvas_id = value.get(ELEMENT_KEY) if isinstance(value, dict) else None
                    if isinstance(canvas_id, str) and canvas_id:
                        element_ids["canvas"] = canvas_id
                    else:
                        valid = False
                elif occurrence == 2:
                    canvas_id = element_ids.get("canvas")
                    valid = bool(canvas_id) and req.get("method") == "GET" and \
                        path == prefix + f"/element/{quote(canvas_id, safe='')}/screenshot" and \
                        req.get("body") is None
                if not valid:
                    errors.append(f"{family} transcript screenshot endpoint mismatch: {operation}")
            if operation == "canvas.screenshot.interaction":
                canvas_id = element_ids.get("canvas")
                if occurrence_counts[operation] != 1 or not canvas_id or req.get("method") != "GET" or \
                        path != prefix + f"/element/{quote(canvas_id, safe='')}/screenshot" or \
                        req.get("body") is not None:
                    errors.append(f"{family} interaction screenshot is not bound to initial canvas")
            if operation == "canvas.orbit":
                canvas_id = element_ids.get("canvas")
                expected_actions = json.loads(json.dumps(ORBIT_ACTIONS))
                if canvas_id:
                    expected_actions["actions"][0]["actions"][0]["origin"][ELEMENT_KEY] = canvas_id
                if not canvas_id or req.get("body") != expected_actions:
                    errors.append(f"{family} orbit actions are not bound to initial canvas")
    collapsed: list[str] = []
    group_counts: list[int] = []
    for operation in operations:
        if not collapsed or collapsed[-1] != operation:
            collapsed.append(operation)
            group_counts.append(1)
        else:
            group_counts[-1] += 1
    if tuple(collapsed) != EXPECTED_PHASES:
        errors.append(f"{family} transcript phase ordering mismatch")
    elif any(count != (2 if operation == "canvas.screenshot.initial" else 1)
             for operation, count in zip(collapsed, group_counts, strict=True)
             if operation not in {"boot.wait", "open.wait", "download.wait",
                                  "download.reopen.wait"}):
        errors.append(f"{family} transcript contains an unauthorized repeated operation")
    if operations.count("session.create") != 1 or operations.count("session.delete") != 1:
        errors.append(f"{family} transcript does not contain exactly one session lifecycle")
    if operations.count("canvas.screenshot.initial") != 2 or \
            operations.count("canvas.screenshot.interaction") != 1:
        errors.append(f"{family} transcript screenshot multiplicity mismatch")
    return errors


def png_pixel_proof(payload: bytes) -> tuple[dict[str, Any], list[int]]:
    """Decode a WebDriver PNG with the standard library and return sampled pixels."""
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("screenshot is not PNG")
    cursor = 8
    width = height = color = depth = 0
    compressed = bytearray()
    while cursor + 12 <= len(payload):
        size = int.from_bytes(payload[cursor:cursor + 4], "big")
        kind = payload[cursor + 4:cursor + 8]
        data = payload[cursor + 8:cursor + 8 + size]
        cursor += 12 + size
        if kind == b"IHDR":
            width, height = int.from_bytes(data[:4], "big"), int.from_bytes(data[4:8], "big")
            depth, color = data[8], data[9]
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
    channels = {2: 3, 6: 4}.get(color)
    if depth != 8 or channels is None or width < 1 or height < 1:
        raise ValueError("unsupported PNG screenshot format")
    raw = zlib.decompress(bytes(compressed))
    stride = width * channels
    if len(raw) != height * (stride + 1):
        raise ValueError("PNG screenshot has unexpected scanline size")
    rows: list[bytearray] = []
    position = 0
    for _y in range(height):
        filter_type = raw[position]
        source = raw[position + 1:position + 1 + stride]
        position += stride + 1
        row = bytearray(stride)
        prior = rows[-1] if rows else bytearray(stride)
        for index, value in enumerate(source):
            left = row[index - channels] if index >= channels else 0
            up = prior[index]
            upper_left = prior[index - channels] if index >= channels else 0
            if filter_type == 0:
                decoded = value
            elif filter_type == 1:
                decoded = value + left
            elif filter_type == 2:
                decoded = value + up
            elif filter_type == 3:
                decoded = value + ((left + up) // 2)
            elif filter_type == 4:
                estimate = left + up - upper_left
                distances = (abs(estimate - left), abs(estimate - up), abs(estimate - upper_left))
                decoded = value + (left if distances[0] <= distances[1] and distances[0] <= distances[2]
                                   else up if distances[1] <= distances[2] else upper_left)
            else:
                raise ValueError("unsupported PNG filter")
            row[index] = decoded & 255
        rows.append(row)
    values: list[int] = []
    colors: set[tuple[int, int, int]] = set()
    nonblack = 0
    for y in range(0, height, 8):
        for x in range(0, width, 8):
            index = x * channels
            rgb = tuple(rows[y][index:index + 3])
            values.append(sum(rgb) // 3)
            colors.add(tuple(value >> 3 for value in rgb))
            nonblack += int(sum(rgb) > 30)
    ratio = nonblack / len(values) if values else 0.0
    proof = {"width": width, "height": height, "nonblackRatio": ratio,
             "quantizedColors": len(colors), "pngBytes": len(payload),
             "pngSha256": hashlib.sha256(payload).hexdigest(),
             "pass": width >= 1000 and height >= 600 and ratio > 0.1 and len(colors) > 128}
    return proof, values


def mean_absolute_difference(first: list[int], second: list[int]) -> float:
    if not first or len(first) != len(second):
        return 0.0
    return sum(abs(a - b) for a, b in zip(first, second, strict=True)) / len(first)
