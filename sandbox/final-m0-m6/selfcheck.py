#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hermetic end-to-end and adversarial checks for the M0--M8 aggregate gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import copy
import datetime as dt
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import quote_from_bytes


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("final_m0_m6_verify", HERE / "verify.py")
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)
COMPOSE_SPEC = importlib.util.spec_from_file_location("final_m0_m6_compose", HERE / "compose.py")
assert COMPOSE_SPEC and COMPOSE_SPEC.loader
compose_module = importlib.util.module_from_spec(COMPOSE_SPEC)
COMPOSE_SPEC.loader.exec_module(compose_module)
FREEZE_SPEC = importlib.util.spec_from_file_location(
    "final_source_freeze_release", HERE.parent / "final-source-freeze/freeze_release.py"
)
assert FREEZE_SPEC and FREEZE_SPEC.loader
sys.path.insert(0, str(HERE.parent / "final-source-freeze"))
freeze_release = importlib.util.module_from_spec(FREEZE_SPEC)
FREEZE_SPEC.loader.exec_module(freeze_release)

NOW_TEXT = "2026-08-15T12:05:00Z"
CREATED = "2026-08-15T12:01:00Z"
FREEZE_TIME = "2026-08-15T12:00:00Z"
LABEL = "release-r1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def external_ref(path: Path) -> dict[str, object]:
    path = path.resolve()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}


def write(path: Path, payload: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload.encode() if isinstance(payload, str) else payload)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def tree_ref(root: Path, path: Path) -> dict[str, object]:
    h = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    for item in files:
        h.update(item.relative_to(path).as_posix().encode() + b"\0")
        h.update(item.read_bytes() + b"\0")
    return {"path": path.relative_to(root).as_posix(), "files": len(files), "sha256": h.hexdigest()}


def current_manifest(repo: Path) -> tuple[bytes, int]:
    names = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True, check=True,
    ).stdout.split(b"\0")
    staged = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--stage", "-z"],
        capture_output=True, check=True,
    ).stdout.split(b"\0")
    modes = {}
    for item in staged:
        if item:
            header, name = item.split(b"\t", 1)
            modes[name] = header.split(b" ", 1)[0].decode()
    rows = []
    for raw in sorted(name for name in names if name):
        path = repo / Path(os.fsdecode(raw))
        if path.is_symlink():
            payload = os.fsencode(os.readlink(path)); mode = "120000"
        else:
            payload = path.read_bytes(); mode = modes.get(raw, "100755" if os.access(path, os.X_OK) else "100644")
        rows.append(json.dumps({
            "mode": mode, "path": quote_from_bytes(raw, safe="/-._~"),
            "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload),
        }, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    return b"".join(rows), len(rows)


def ignored_record(repo: Path) -> dict[str, object]:
    names = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        capture_output=True, check=True,
    ).stdout.split(b"\0")
    values = sorted(name for name in names if name)
    payload = b"\0".join(values) + (b"\0" if values else b"")
    return {
        "policy": "excluded by the repository's standard Git ignore rules",
        "count": len(values), "nul_list_sha256": hashlib.sha256(payload).hexdigest(),
    }


def component_receipt(repo: Path, output: Path, pin_file: Path | None = None) -> dict:
    output.mkdir(parents=True)
    patch = output / "canonical-source.patch"; write(patch, "fixture patch\n")
    manifest, count = current_manifest(repo)
    live = output / "live.manifest.jsonl"; write(live, manifest)
    replay = output / "replay.manifest.jsonl"; write(replay, manifest)
    pin = git(repo, "rev-parse", "HEAD")
    receipt = {
        "schema": 1, "verdict": "PASS", "created_utc": FREEZE_TIME,
        "source": str(repo.resolve()), "expected_pin": pin,
        "recorded_pin_file": (
            {"path": str(pin_file.resolve()), "sha256": digest(pin_file)} if pin_file else None
        ),
        "git_version": "git version fixture",
        "patch": {"path": patch.name, "bytes": patch.stat().st_size, "sha256": digest(patch)},
        "live_manifest": {"path": live.name, "entries": count, "bytes": live.stat().st_size, "sha256": digest(live)},
        "replay_manifest": {"path": replay.name, "entries": count, "bytes": replay.stat().st_size, "sha256": digest(replay)},
        "ignored_worktree_paths": ignored_record(repo),
        "checks": {key: True for key in verify.COMPONENT_CHECKS},
    }
    receipt_path = output / "receipt.json"; write(receipt_path, json.dumps(receipt, sort_keys=True))
    return receipt


def make_fixture(root: Path) -> tuple[Path, dict, dict[str, Path]]:
    root.mkdir()
    ignore = """/upstream/
/evidence/
/build-wasm-windowed-opt/
/sandbox/m5-click-pick/evidence/
/sandbox/m5-canvas-smoke/evidence/
/sandbox/m5-latency/evidence/
/sandbox/gpu-r61/workbench-preview/runs/
/sandbox/gpu-r61/eevee-matrix-preview/runs/
/sandbox/gpu-r61/cycles-windowed/evidence/
/sandbox/m6-prep/cycles-runs/
/sandbox/m7-product-gate/fallback-evidence/
/sandbox/m7-product-gate/verify_files.json
/sandbox/m7-product-gate/bundle-identity.json
/sandbox/m7-usd-prep/browser-roundtrip/
/sandbox/m7-usd-prep/native-capability/
/sandbox/m8-launch-gate/artifacts/
/sandbox/m8-staged-deploy/artifacts/
/sandbox/m8-staged-deploy/bundle-staged/
"""
    write(root / ".gitignore", ignore)
    write(root / "harness/run.sh", "fixture\n")
    write(root / "scripts/dashboard.sh", "fixture\n")
    write(root / "scripts/finalize-wasm-split.py", "fixture\n")
    write(root / "platform_web/shell/boot-windowed.js", "fixture\n")
    write(root / "platform_web/shell/file-bridge.js", "fixture\n")
    write(root / "sandbox/m8-staged-deploy/make_staged_bundle.sh", "fixture\n")
    write(root / "sandbox/m8-launch-gate/verify_m8.py", "fixture\n")
    write(root / "sandbox/final-m0-m6/verify.py", "fixture aggregate source v1\n")
    write(root / "sandbox/m5-final/runtime-artifacts.mjs", "fixture\n")
    for required in freeze_release.REQUIRED_PROJECT_PATHS:
        if not (root / required).exists():
            write(root / required, f"fixture {required}\n")

    m03_stub = """#!/usr/bin/env python3
import hashlib,json,sys
a=sys.argv; m=json.load(open(a[a.index('--manifest')+1])); p=m['source_freeze']['receipt']['path']; b=open(p,'rb').read()
print(json.dumps({'verdict':'PASS','run_label':m['run_label'],'source_freeze_sha256':hashlib.sha256(b).hexdigest()}))
"""
    m4_stub = """#!/usr/bin/env python3
import json,os
assert json.load(open(os.environ['M4_BINDING']))['run'].endswith('.m4')
print('M4_BINDING_PASS fixture')
"""
    m5_stub = """#!/usr/bin/env python3
import os
assert os.environ['BW_DEFERRED_WASM_FILENAME']=='blender_browser.placeholder_ab12.wasm'
assert all(os.environ['M5_'+x+'_RUN_LABEL'].startswith('release-r1.') for x in ('CLICK','CANVAS','LATENCY'))
print('M5_FINAL_PASS fixture')
"""
    m6_stub = """#!/usr/bin/env python3
import json,os,pathlib
assert os.environ['BW_DEFERRED_WASM_FILENAME']=='blender_browser.placeholder_ab12.wasm'
marker=pathlib.Path('evidence/mutate')
if marker.exists(): pathlib.Path(os.environ['SELFCHECK_M4_BINDING']).write_text('{\"run\":\"tampered\"}')
grow=pathlib.Path('evidence/growtree')
if grow.exists(): pathlib.Path(os.environ['SELFCHECK_M6_TREE'],'late.txt').write_text('late')
if pathlib.Path('evidence/m6-cycle-mutate').exists():
 pathlib.Path(os.environ['SELFCHECK_M6_CYCLES']).write_text('mutated cycles sibling')
print('M6_RENDER_PASS fixture')
"""
    m7_stub = """#!/usr/bin/env python3
import os,pathlib,sys
root=pathlib.Path(__file__).resolve().parents[2]
assert sys.argv[1:] == ['--release-label','release-r1']
assert os.environ['FINAL_RUN_LABEL'] == 'release-r1'
if (root/'evidence/m7-mutate').exists():
 (root/'sandbox/m7-product-gate/verify_files.json').write_text('{"tampered":true}')
if (root/'evidence/m7-grow').exists():
 (root/'sandbox/m7-usd-prep/browser-roundtrip/release-r1/unlisted.json').write_text('{}')
print('M7_STRICT_PASS fixture')
"""
    m8_stub = """#!/usr/bin/env python3
import json,pathlib,sys
assert sys.argv[1:] == ['--post-receipt']
root=pathlib.Path(__file__).resolve().parents[2]
art=root/'sandbox/m8-launch-gate/artifacts'
required=[
 'current-staged-receipt.json','current-browser-matrix.json',
 'current-product-receipt.json','current-soak-result.json',
 'current-compliance-receipt.json',
]
assert all((art/name).is_file() for name in required)
if (root/'evidence/m8-fail').exists():
 print('M8_TECHNICAL_POST_RECEIPT_FAIL fixture')
 raise SystemExit(1)
if (root/'evidence/m8-mutate').exists():
 (art/'current-staged-receipt.json').write_text('{"tampered":true}')
if (root/'evidence/m8-delete').exists():
 (root/'sandbox/m8-staged-deploy/artifacts/measure_staged-4g.json').unlink()
if (root/'evidence/m8-grow-launch').exists():
 (art/'unlisted-after-verifier.json').write_text('{}')
bundle=root/'sandbox/m8-staged-deploy/bundle-staged'
if (root/'evidence/m8-mutate-bundle').exists():
 (bundle/'fixture.txt').write_text('mutated')
if (root/'evidence/m8-delete-bundle').exists():
 (bundle/'fixture.txt').unlink()
if (root/'evidence/m8-grow-bundle').exists():
 (bundle/'unlisted.bin').write_bytes(b'unlisted')
preflight={
 'schema':1,'checked_at':'2026-08-15T12:04:00+00:00',
 'mode':'technical_post_receipt','technical_pass':True,'post_receipt_pass':True,
 'external_launch_pass':None,'external_verification_deferred':None,
 'external_verification_reason':None,'launch_ready':False,
 'technical_failures':[],'post_receipt_failures':[],'external_blockers':[],
}
if (root/'evidence/m8-bad-preflight').exists(): preflight['technical_pass']=False
(art/'current-m8-preflight.json').write_text(json.dumps(preflight))
print('M8_TECHNICAL_POST_RECEIPT_PASS fixture')
"""
    for name, source in (
        ("sandbox/final-m0-m3/verify.py", m03_stub),
        ("sandbox/m4-d9-gate/verify_current_binding.py", m4_stub),
        ("sandbox/m5-final/verify_m5.py", m5_stub),
        ("sandbox/m6-prep/verify_render_closeout.py", m6_stub),
        ("sandbox/m7-product-gate/verify_m7.py", m7_stub),
        ("sandbox/m8-launch-gate/verify_m8.py", m8_stub),
    ):
        write(root / name, source)
    for relative in verify.VOLATILE_GENERATED_OUTPUTS:
        if relative.startswith("ledger/results/"):
            scope = Path(relative).stem
            write(root / relative, json.dumps({"scope": scope, "pass": True, "generation": 0}))
        else:
            write(root / relative, "<!-- Generated by scripts/dashboard.sh -->\ninitial\n")
    # This tracked sibling deliberately resembles generated M8 state but is not
    # on the exact volatile allowlist. It must remain source-frozen.
    write(root / "sandbox/m8-staged-deploy/volatile-policy-adjacent.txt", "frozen\n")
    git(root, "init", "--quiet"); git(root, "config", "user.name", "Fixture"); git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "add", "-A"); git(root, "commit", "--quiet", "-m", "project pin")
    project_pin = git(root, "rev-parse", "HEAD")
    write(root / "sandbox/final-m0-m6/verify.py", "fixture aggregate source v2\n")

    upstream = root / "upstream"; upstream.mkdir()
    for required in freeze_release.REQUIRED_UPSTREAM_PATHS:
        write(upstream / required, f"fixture {required}\n")
    write(upstream / "source.cc", "pin\n")
    git(upstream, "init", "--quiet"); git(upstream, "config", "user.name", "Fixture"); git(upstream, "config", "user.email", "fixture@example.invalid")
    git(upstream, "add", "-A"); git(upstream, "commit", "--quiet", "-m", "upstream pin")
    write(upstream / "source.cc", "ported\n")
    pin_file = root / "oracle/PIN"; write(pin_file, git(upstream, "rev-parse", "HEAD")[:12] + " fixture\n")

    bindir = root / "build-wasm-windowed-opt/bin"; bindir.mkdir(parents=True)
    js = bindir / "blender_browser.js"; data = bindir / "blender_browser.data"
    primary = bindir / "blender_browser.wasm"
    deferred = bindir / "blender_browser.placeholder_ab12.wasm"
    original = bindir / "blender_browser.wasm.orig"
    for path, payload in ((js, b"js"), (data, b"data"), (primary, b"primary"),
                          (deferred, b"deferred"), (original, b"original")):
        write(path, payload)
    def embedded(path: Path, role: str, shipped: bool, critical: bool, phase: str) -> dict:
        return {"role": role, "filename": path.name, "path": str(path.resolve()),
                "bytes": path.stat().st_size, "sha256": digest(path),
                "shipped": shipped, "critical": critical, "request_phase": phase}
    rows = [embedded(primary,"primary",True,True,"stage0"), embedded(deferred,"deferred",True,False,"after_semantic_first_interaction"), embedded(original,"original_build_only",False,False,"never")]
    split = {"schema":1,"mode":"apply","verdict":"PASS","contract":"fixture","reserve_bytes":1,
             "original":{},"profile":{},"profile_receipt":{},"primary":{k:rows[0][k] for k in ("path","bytes","sha256")},
             "secondary":{k:rows[1][k] for k in ("path","bytes","sha256")},"js":{"sha256":digest(js)},
             "single_flight":{},"shared_memory_view_refresh":{},"pthread_memory_range_sync":{},"controller_closure":{},
             "link_command":{},"finalizer":{},"binaryen_features":[],"placeholder_modules":[],"maps":[],"facts":{},
             "wasm_inventory":rows,"inventory_policy":{"glob":"blender_browser*.wasm*","unlisted":"reject","bundle_roles":["primary","deferred"],"build_only_roles":["original_build_only"],"profile_export_absent":True,"prior_receipt_invalidated_before_mutation":True}}
    split_path = bindir / "blender_browser.split-build.json"; write(split_path, json.dumps(split))
    artifacts = {"manifest":ref(root,split_path),"javascript":ref(root,js),"preload":ref(root,data),"primary":ref(root,primary),"deferred":ref(root,deferred)}

    release_dir = root.parent / "release-freeze"
    freeze_release.freeze_release(
        root, project_pin, upstream, git(upstream, "rev-parse", "HEAD"), pin_file, release_dir
    )
    release_path = release_dir / "receipt.json"
    release_time = dt.datetime.fromisoformat(
        json.loads(release_path.read_text())["created_utc"].replace("Z", "+00:00")
    )
    candidate_created = (release_time + dt.timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    verify_now = (release_time + dt.timedelta(seconds=2)).isoformat().replace("+00:00", "Z")
    # Simulate the authorized post-freeze harness/dashboard regeneration. These
    # exact paths must be accepted only because the final candidate binds them.
    for relative in verify.VOLATILE_GENERATED_OUTPUTS:
        if relative.startswith("ledger/results/"):
            scope = Path(relative).stem
            write(root / relative, json.dumps({"scope": scope, "pass": True, "generation": 1}))
        else:
            write(root / relative, "<!-- Generated by scripts/dashboard.sh -->\npost-freeze\n")

    freeze_copy = root / "evidence/upstream-freeze"; freeze_copy.mkdir(parents=True)
    for name in ("receipt.json","canonical-source.patch","live.manifest.jsonl","replay.manifest.jsonl"):
        write(freeze_copy/name,(release_dir/"upstream"/name).read_bytes())
    m03_manifest=root/"evidence/m03.json"
    write(m03_manifest,json.dumps({"run_label":LABEL,"source_freeze":{"receipt":ref(root,freeze_copy/"receipt.json")}}))
    m4_binding=root/"evidence/m4.json"; write(m4_binding,json.dumps({"run":f"{LABEL}.m4"}))
    m5_rows={}
    for kind, base in (("click","sandbox/m5-click-pick/evidence"),("canvas","sandbox/m5-canvas-smoke/evidence"),("latency","sandbox/m5-latency/evidence")):
        run=f"{LABEL}.m5-{kind}"; directory=root/base/run; directory.mkdir(parents=True)
        receipt=directory/"receipt.json"; write(receipt,json.dumps({"run":run}))
        write(directory/"receipt.sha256",f"{digest(receipt)} receipt.json\n")
        m5_rows[kind]={"run_label":run,"receipt_sha256":digest(receipt)}
    wb=root/f"sandbox/gpu-r61/workbench-preview/runs/{LABEL}.m6-workbench"; write(wb/"proof.txt","wb\n")
    ee=root/f"sandbox/gpu-r61/eevee-matrix-preview/runs/{LABEL}.m6-eevee"; write(ee/"proof.txt","ee\n")
    cycles_sibling=root/f"sandbox/gpu-r61/cycles-windowed/evidence/{LABEL}.m6-cycles-smoke-console.log"
    write(cycles_sibling,"cycles console\n")
    smoke=root/f"sandbox/gpu-r61/cycles-windowed/evidence/{LABEL}.m6-cycles-smoke-manifest.json"
    write(smoke,json.dumps({"evidence":{"console":ref(root,cycles_sibling)}}))
    suite=root/f"sandbox/m6-prep/cycles-runs/{LABEL}.m6-cycles-suite"; write(suite/"proof.txt","cycles\n")
    m7_inputs={}
    for key, relative in verify.M7_TECHNICAL_INPUTS.items():
        path=root/relative; write(path,json.dumps({"schema":1,"fixture":key}))
        m7_inputs[key]=ref(root,path)
    m7_tree_paths={
        "fallback":root/f"sandbox/m7-product-gate/fallback-evidence/{LABEL}",
        "usd_browser":root/f"sandbox/m7-usd-prep/browser-roundtrip/{LABEL}",
        "usd_native":root/f"sandbox/m7-usd-prep/native-capability/{LABEL}",
    }
    write(m7_tree_paths["fallback"]/"receipt.json",json.dumps({"label":LABEL,"fixture":"fallback"}))
    write(m7_tree_paths["fallback"]/"selector.json",json.dumps({"label":LABEL,"fixture":"selector"}))
    for kind in ("usd_browser","usd_native"):
        write(m7_tree_paths[kind]/"receipt.json",json.dumps({"label":LABEL,"fixture":kind}))
        write(m7_tree_paths[kind]/"selector.json",json.dumps({"label":LABEL,"fixture":"selector"}))
    bundle=root/"sandbox/m8-staged-deploy/bundle-staged"
    write(bundle/"fixture.txt",b"bundle fixture")
    m8_inputs={}
    for key, relative in verify.M8_TECHNICAL_INPUTS.items():
        path=root/relative
        if key == "runtime_screenshot": payload=b"PNG fixture"
        elif key == "runtime_screenshot_license": payload="SPDX-License-Identifier: CC0-1.0\n"
        elif key == "runtime_console": payload="runtime console clean\n"
        elif key == "staged_receipt": payload=json.dumps({
            "schema":1,"fixture":key,
            "source_artifacts":{"blender_browser.js":{
                "bytes":js.stat().st_size,"sha256":digest(js)}},
            "bundle_artifacts":{"fixture.txt":{
                "bytes":(bundle/"fixture.txt").stat().st_size,
                "sha256":digest(bundle/"fixture.txt")}},
        })
        else: payload=json.dumps({"schema":1,"fixture":key})
        write(path,payload)
        m8_inputs[key]=ref(root,path)
    def projected(path: Path, excluded: tuple[str, ...]) -> dict[str, object]:
        h=hashlib.sha256(); count=0
        for item in sorted(path.rglob("*")):
            relative=item.relative_to(path).as_posix()
            if relative in excluded: continue
            if item.is_file():
                h.update(relative.encode()+b"\0"); h.update(item.read_bytes()+b"\0"); count+=1
        return {"path":path.relative_to(root).as_posix(),"excluded":list(excluded),
                "files":count,"sha256":h.hexdigest()}
    m8_trees={
        key:projected(root/relative,excluded)
        for key,(relative,excluded) in verify.M8_TECHNICAL_TREES.items()
    }
    candidate={"schema":1,"verdict":"PASS","run_label":LABEL,"created_utc":candidate_created,
               "source_freeze":{"receipt":external_ref(release_path)},
               "generated_outputs":{relative:ref(root,root/relative) for relative in verify.VOLATILE_GENERATED_OUTPUTS},
               "m0_m3":{"manifest":ref(root,m03_manifest),"verifier":ref(root,root/"sandbox/final-m0-m3/verify.py")},
               "artifacts":artifacts,
               "m7_technical":{"verifier":ref(root,root/"sandbox/m7-product-gate/verify_m7.py"),
                                  "evidence":m7_inputs,
                                  "evidence_trees":{key:tree_ref(root,path) for key,path in m7_tree_paths.items()}},
               "m8_technical":{"verifier":ref(root,root/"sandbox/m8-launch-gate/verify_m8.py"),
                                 "evidence":m8_inputs,
                                 "evidence_trees":m8_trees,
                                 "result":ref(root,root/"ledger/results/m8.json"),
                                 "dashboard":ref(root,root/"reports/dashboard.md")},
               "milestones":{"m4":{"verifier":ref(root,root/"sandbox/m4-d9-gate/verify_current_binding.py"),"binding":ref(root,m4_binding)},
                             "m5":{"verifier":ref(root,root/"sandbox/m5-final/verify_m5.py"),**m5_rows},
                             "m6":{"verifier":ref(root,root/"sandbox/m6-prep/verify_render_closeout.py"),
                                   "workbench":{"run_label":f"{LABEL}.m6-workbench","evidence":tree_ref(root,wb)},
                                   "eevee":{"run_label":f"{LABEL}.m6-eevee","evidence":tree_ref(root,ee)},
                                   "cycles_smoke":{"run_label":f"{LABEL}.m6-cycles-smoke","evidence":ref(root,smoke),
                                                   "evidence_tree":tree_ref(root,smoke.parent)},
                                   "cycles_suite":{"run_label":f"{LABEL}.m6-cycles-suite","evidence":tree_ref(root,suite)}}}}
    candidate_path=root/"evidence/candidate.json"; write(candidate_path,json.dumps(candidate))
    paths={"candidate":candidate_path,"binding":m4_binding,"suite":suite,"bindir":bindir,"release":release_path,
           "source":root/"harness/run.sh","generated":root/"ledger/results/m6.json",
           "cycles_sibling":cycles_sibling,
           "volatile_adjacent":root/"sandbox/m8-staged-deploy/volatile-policy-adjacent.txt",
           "m7_file":root/verify.M7_TECHNICAL_INPUTS["files_receipt"],
           "m7_tree":m7_tree_paths["usd_browser"],
           "m8_staged":root/verify.M8_TECHNICAL_INPUTS["staged_receipt"],
           "m8_performance":root/verify.M8_TECHNICAL_INPUTS["performance_proof"]}
    paths["verify_now"] = Path(verify_now)
    return candidate_path,candidate,paths


def expect_failure(callback, token: str, failures: list[str]) -> None:
    try:
        callback()
    except verify.VerificationError:
        failures.append(token)
    else:
        raise AssertionError(f"negative accepted: {token}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="final-m0-m6-selfcheck-") as raw:
        outer=Path(raw).resolve(); root=outer/"project"
        candidate_path,candidate,paths=make_fixture(root)
        now=verify.parse_time(str(paths["verify_now"]),"now")
        # The M6 stub receives this only for the mutation negative.
        os.environ["SELFCHECK_M4_BINDING"]=str(paths["binding"])
        os.environ["SELFCHECK_M6_TREE"]=str(paths["suite"])
        os.environ["SELFCHECK_M6_CYCLES"]=str(paths["cycles_sibling"])
        result=verify.verify(root,candidate_path,now,600)
        assert result["verdict"]=="PASS" and result["artifact_sha256"]["deferred_filename"]=="blender_browser.placeholder_ab12.wasm"
        assert result["candidate_manifest"]=={
            "bytes":candidate_path.stat().st_size,"sha256":digest(candidate_path)}
        compose_module.require_bound_verification(result,candidate_path,LABEL,root)
        negatives=[]

        source_original=paths["source"].read_bytes(); write(paths["source"],b"source tamper")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"post_freeze_source_mutation",negatives)
        write(paths["source"],source_original)

        generated_original=paths["generated"].read_bytes(); write(paths["generated"],b'{"scope":"m6","pass":true,"tamper":1}')
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"generated_output_tamper",negatives)
        write(paths["generated"],generated_original)

        adjacent_original=paths["volatile_adjacent"].read_bytes()
        write(paths["volatile_adjacent"],b"unlisted post-freeze mutation")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),
                       "unlisted_volatile_sibling_mutation",negatives)
        write(paths["volatile_adjacent"],adjacent_original)

        cycles_original=paths["cycles_sibling"].read_bytes()
        write(root/"evidence/m6-cycle-mutate",b"1")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),
                       "m6_cycles_post_verifier_mutation",negatives)
        (root/"evidence/m6-cycle-mutate").unlink()
        write(paths["cycles_sibling"],cycles_original)

        candidate["generated_outputs"]["sandbox/m8-staged-deploy/volatile-policy-adjacent.txt"] = ref(
            root, paths["volatile_adjacent"]
        )
        write(candidate_path,json.dumps(candidate))
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),
                       "volatile_allowlist_growth",negatives)
        del candidate["generated_outputs"]["sandbox/m8-staged-deploy/volatile-policy-adjacent.txt"]
        write(candidate_path,json.dumps(candidate))

        # The aggregate independently requires critical paths from each Git
        # root. A self-consistent coverage count cannot make an omission pass.
        release_original=paths["release"].read_bytes()
        def reject_freeze_coverage_omission(
            name: str, list_key: str, count_key: str, omitted: str
        ) -> None:
            release=json.loads(release_original)
            release["coverage"][list_key].remove(omitted)
            release["coverage"][count_key]-=1
            write(paths["release"],json.dumps(release))
            candidate["source_freeze"]["receipt"]=external_ref(paths["release"])
            write(candidate_path,json.dumps(candidate))
            expect_failure(lambda:verify.verify(root,candidate_path,now,600),name,negatives)
            write(paths["release"],release_original)
            candidate["source_freeze"]["receipt"]=external_ref(paths["release"])
            write(candidate_path,json.dumps(candidate))

        reject_freeze_coverage_omission(
            "freeze_critical_project_device_limit_omission",
            "required_paths", "required_paths_present",
            "platform_web/ghost/GHOST_ContextWGPUWeb.cc",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_project_worker_limit_omission",
            "required_paths", "required_paths_present",
            "platform_web/shell/wgpu-preinit-worker.js",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_project_opensubdiv_recipe_omission",
            "required_paths", "required_paths_present",
            "scripts/deps/opensubdiv.sh",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_project_gpu_manifest_omission",
            "required_paths", "required_paths_present",
            "sandbox/final-m0-m3/gpu_webgpu_tests.txt",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_project_shader_manifest_omission",
            "required_paths", "required_paths_present",
            "sandbox/final-m0-m3/static_shader_identities.txt",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_project_dawn_probe_omission",
            "required_paths", "required_paths_present",
            "sandbox/dawn-probe/build.sh",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_device_limit_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "intern/ghost/intern/GHOST_ContextWGPU.cc",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_opensubdiv_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "intern/opensubdiv/internal/evaluator/evaluator_capi.cc",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_cache_marker_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "source/blender/gpu/webgpu/wgpu_shader_compiler.cc",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_shader_cache_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "source/blender/gpu/webgpu/wgpu_shader_cache.cc",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_texture_clear_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "source/blender/gpu/webgpu/wgpu_texture.cc",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_atomic_test_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "source/blender/gpu/tests/shaders/gpu_texture_atomic_test.glsl",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_debug_compact_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "source/blender/draw/intern/shaders/draw_debug_draw_compact_comp.glsl",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_draw_test_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "source/blender/draw/tests/draw_debug_test.cc",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_curves_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "source/blender/draw/intern/draw_curves.cc",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_subdiv_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "source/blender/draw/intern/shaders/subdiv_patch_evaluation_comp.glsl",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_fullscreen_scope_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "source/blender/gpu/metal/kernels/gpu_shader_fullscreen_blit_infos.hh",
        )
        reject_freeze_coverage_omission(
            "freeze_critical_upstream_omission",
            "required_upstream_paths", "required_upstream_paths_present",
            "source/blender/blenlib/tests/BLI_fileops_test.cc",
        )

        m7_original=paths["m7_file"].read_bytes()
        write(root/"evidence/m7-mutate",b"1")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),
                       "m7_post_verifier_mutation",negatives)
        (root/"evidence/m7-mutate").unlink(); write(paths["m7_file"],m7_original)

        write(root/"evidence/m7-grow",b"1")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),
                       "m7_post_verifier_tree_growth",negatives)
        (root/"evidence/m7-grow").unlink()
        (paths["m7_tree"]/"unlisted.json").unlink()

        saved=candidate["m8_technical"]["evidence"].pop("soak")
        write(candidate_path,json.dumps(candidate))
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"m8_missing_evidence_key",negatives)
        candidate["m8_technical"]["evidence"]["soak"]=saved
        candidate["m8_technical"]["evidence"]["unlisted"] = saved
        write(candidate_path,json.dumps(candidate))
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"m8_extra_evidence_key",negatives)
        del candidate["m8_technical"]["evidence"]["unlisted"]
        write(candidate_path,json.dumps(candidate))

        staged_original=paths["m8_staged"].read_bytes(); write(paths["m8_staged"],b'{"stale":true}')
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"m8_stale_receipt",negatives)
        write(paths["m8_staged"],staged_original)

        performance_original=paths["m8_performance"].read_bytes(); paths["m8_performance"].unlink()
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"m8_missing_artifact",negatives)
        write(paths["m8_performance"],performance_original)

        result_original=copy.deepcopy(candidate["m8_technical"]["result"])
        candidate["m8_technical"]["result"]=candidate["generated_outputs"]["ledger/results/m7.json"]
        write(candidate_path,json.dumps(candidate))
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"m8_result_alias",negatives)
        candidate["m8_technical"]["result"]=result_original
        write(candidate_path,json.dumps(candidate))

        write(root/"evidence/m8-fail",b"1")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"m8_authoritative_verifier_red",negatives)
        (root/"evidence/m8-fail").unlink()

        write(root/"evidence/m8-mutate",b"1")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"m8_post_verifier_mutation",negatives)
        (root/"evidence/m8-mutate").unlink(); write(paths["m8_staged"],staged_original)

        write(root/"evidence/m8-delete",b"1")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"m8_post_verifier_deletion",negatives)
        (root/"evidence/m8-delete").unlink(); write(paths["m8_performance"],performance_original)

        write(root/"evidence/m8-bad-preflight",b"1")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"m8_invalid_post_receipt_preflight",negatives)
        (root/"evidence/m8-bad-preflight").unlink()

        for marker, token, cleanup in (
            ("m8-grow-launch", "m8_launch_tree_growth", root/"sandbox/m8-launch-gate/artifacts/unlisted-after-verifier.json"),
            ("m8-mutate-bundle", "m8_bundle_mutation", root/"sandbox/m8-staged-deploy/bundle-staged/fixture.txt"),
            ("m8-delete-bundle", "m8_bundle_deletion", root/"sandbox/m8-staged-deploy/bundle-staged/fixture.txt"),
            ("m8-grow-bundle", "m8_bundle_growth", root/"sandbox/m8-staged-deploy/bundle-staged/unlisted.bin"),
        ):
            write(root/f"evidence/{marker}",b"1")
            expect_failure(lambda:verify.verify(root,candidate_path,now,600),token,negatives)
            (root/f"evidence/{marker}").unlink()
            if marker == "m8-mutate-bundle" or marker == "m8-delete-bundle":
                write(root/"sandbox/m8-staged-deploy/bundle-staged/fixture.txt",b"bundle fixture")
            elif cleanup.exists():
                cleanup.unlink()

        extra=paths["bindir"]/"blender_browser.unlisted.wasm"; extra.mkdir()
        ctx=verify.Context(root,now,600)
        expect_failure(lambda:verify.validate_split_inventory(ctx,candidate["artifacts"]),"unlisted_directory",negatives)
        extra.rmdir()

        real=root/"evidence/real"; real.mkdir(); write(real/"payload",b"x"); (root/"evidence/alias").symlink_to(real,target_is_directory=True)
        expect_failure(lambda:verify.Context(root,now,600).file_ref({"path":"evidence/alias/payload","bytes":1,"sha256":digest(real/"payload")},"symlink"),"intermediate_symlink",negatives)

        outside=outer/"outside.json"; write(outside,"{}")
        expect_failure(lambda:verify.verify(root,outside,now,600),"candidate_escape",negatives)

        suite_file=paths["suite"]/"proof.txt"; original=suite_file.read_bytes(); write(suite_file,b"tamper")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"m6_tree_tamper",negatives)
        write(suite_file,original)

        write(root/"evidence/mutate",b"1")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"post_comparator_mutation",negatives)
        (root/"evidence/mutate").unlink()

        # Restore the binding changed by the previous negative, then prove that
        # post-comparator tree growth is detected even when all original files
        # remain byte-identical.
        write(paths["binding"],json.dumps({"run":f"{LABEL}.m4"}))
        candidate["milestones"]["m4"]["binding"]=ref(root,paths["binding"])
        write(candidate_path,json.dumps(candidate))
        write(root/"evidence/growtree",b"1")
        expect_failure(lambda:verify.verify(root,candidate_path,now,600),"post_comparator_tree_growth",negatives)

        # A PASS subprocess result is not publication authority after any input
        # or candidate byte changes. The composer rechecks this exact closure.
        (root/"evidence/growtree").unlink()
        (paths["suite"] / "late.txt").unlink()
        result=verify.verify(root,candidate_path,now,600)
        staged_original=paths["m8_staged"].read_bytes()
        write(paths["m8_staged"],b'{"post_verify":"mutated"}')
        try:
            compose_module.recheck_verification_closure(result,root)
        except compose_module.ComposeError:
            negatives.append("composer_post_verify_input_mutation")
        else:
            raise AssertionError("negative accepted: composer_post_verify_input_mutation")
        write(paths["m8_staged"],staged_original)
        candidate_original=candidate_path.read_bytes(); write(candidate_path,candidate_original+b" ")
        try:
            compose_module.require_bound_verification(result,candidate_path,LABEL,root)
        except compose_module.ComposeError:
            negatives.append("composer_candidate_manifest_mutation")
        else:
            raise AssertionError("negative accepted: composer_candidate_manifest_mutation")
        write(candidate_path,candidate_original)

        print(json.dumps({"schema":1,"verdict":"PASS","positive":"full-workflow",
                          "dynamic_deferred":"blender_browser.placeholder_ab12.wasm",
                          "negative":negatives},sort_keys=True))


if __name__ == "__main__":
    main()
