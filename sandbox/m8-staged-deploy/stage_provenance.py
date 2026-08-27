#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministically prove that staged preload outputs derive from the build.

This module deliberately invokes the canonical ``stage_pack.py`` in a fresh
directory.  It never trusts an assembler-authored receipt: the consumer compares
the newly derived bytes with every shipping stage-pack output.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from public_shell_hardening import harden_boot_source


ROOT = Path(__file__).resolve().parents[2]
STAGE_PACK = ROOT / "sandbox/m8-staged-deploy/stage_pack.py"
STAGE_PACK_CONTRACT = ROOT / "sandbox/m8-staged-deploy/test_stage_pack.py"
BROTLI_CODEC = ROOT / "sandbox/m8-staged-deploy/brotli_q11.mjs"
PUBLIC_MINIFIER = ROOT / "sandbox/m8-staged-deploy/public_shell_minify.mjs"
PUBLIC_QUERY_CONTRACT = (
    ROOT / "sandbox/m8-staged-deploy/verify_public_query_hardening.mjs"
)
PTHREAD_LOADER_CONTRACT = (
    ROOT / "sandbox/m8-staged-deploy/test_pthread_main_loader.mjs"
)
TERSER_BUNDLE = (
    ROOT / "tools/emsdk/upstream/emscripten/node_modules/terser/dist/bundle.min.js"
)
PINNED_NODE = Path(os.environ.get(
    "EMSDK_NODE", ROOT / "tools/emsdk/node/22.16.0_64bit/bin/node"))
DERIVED_NAMES = (
    "blender_browser.js",
    "blender_browser.data",
    "stage1.data",
    "stage1-manifest.json",
)
SOURCE_NAMES = ("blender_browser.js", "blender_browser.data")
HEADERS_SUFFIX = """
/bin/*.json
  Content-Type: application/json; charset=utf-8
  Cache-Control: no-cache, must-revalidate

/service-worker.js
  Content-Type: text/javascript; charset=utf-8
  Cache-Control: no-cache

/service-worker-register.js
  Content-Type: text/javascript; charset=utf-8
  Cache-Control: no-cache, must-revalidate

/scenes/*.blend
  Content-Type: application/octet-stream
  Cache-Control: public, max-age=31536000, immutable
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, object]:
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def derive(source_bin: Path, output_bin: Path) -> None:
    command = [sys.executable, str(STAGE_PACK), "--bin", str(source_bin),
               "--out", str(output_bin), "--defer-datafiles"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"canonical stage_pack derivation failed: {detail}")


def verify(source_bin: Path, staged_bin: Path) -> tuple[dict[str, object], list[str]]:
    failures: list[str] = []
    source_bin = source_bin.resolve(strict=True)
    staged_bin = staged_bin.resolve(strict=True)
    for name in SOURCE_NAMES:
        path = source_bin / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != source_bin:
            failures.append(f"stage provenance source is missing/noncanonical: {name}")
    for name in DERIVED_NAMES:
        path = staged_bin / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != staged_bin:
            failures.append(f"stage provenance output is missing/noncanonical: {name}")
    if failures:
        return {}, failures
    with tempfile.TemporaryDirectory(prefix="bw-stage-provenance-") as temporary:
        regenerated = Path(temporary) / "bin"
        try:
            derive(source_bin, regenerated)
        except ValueError as error:
            return {}, [str(error)]
        actual_names = sorted(path.name for path in regenerated.iterdir() if path.is_file())
        if actual_names != sorted(DERIVED_NAMES):
            failures.append(
                "canonical stage_pack output inventory differs: " + repr(actual_names))
        derived: dict[str, dict[str, object]] = {}
        for name in DERIVED_NAMES:
            expected = regenerated / name
            actual = staged_bin / name
            if not expected.is_file():
                failures.append(f"canonical stage_pack omitted output: {name}")
                continue
            derived[name] = identity(expected)
            if identity(actual) != derived[name] or not filecmp.cmp(expected, actual, shallow=False):
                failures.append(f"staged output is not canonical stage_pack bytes: {name}")
        proof = {
            "schema": 1,
            "mode": "defer-datafiles",
            "producer": {"path": str(STAGE_PACK.relative_to(ROOT)), **identity(STAGE_PACK)},
            "source": {name: identity(source_bin / name) for name in SOURCE_NAMES},
            "derived": derived,
        }
    return proof, failures


def _compare_bytes(path: Path, expected: bytes, label: str, failures: list[str]) -> None:
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_size != len(expected) or \
                path.read_bytes() != expected:
            failures.append(f"staged output does not derive exactly from {label}: {path.name}")
    except OSError as error:
        failures.append(f"staged output is unreadable for {label}: {path}: {error}")


def minify_bytes(source: bytes) -> bytes:
    """Replay the pinned public-shell minifier without trusting bundle output."""
    with tempfile.TemporaryDirectory(prefix="bw-public-minifier-") as temporary:
        input_path = Path(temporary) / "input.js"
        output_path = Path(temporary) / "output.js"
        input_path.write_bytes(source)
        try:
            result = subprocess.run(
                [str(PINNED_NODE), str(PUBLIC_MINIFIER),
                 "--input", str(input_path), "--output", str(output_path)],
                cwd=ROOT, capture_output=True, text=True)
        except OSError as error:
            raise ValueError(f"cannot execute deterministic public-shell minifier: {error}") \
                from error
        if result.returncode != 0 or not output_path.is_file():
            detail = (result.stderr or result.stdout).strip()
            raise ValueError(f"deterministic public-shell minification failed: {detail}")
        return output_path.read_bytes()


def render_controls(bundle: Path, worker_template: Path, register_template: Path,
                    rows: list[dict[str, object]], cache_files: list[str],
                    identity_files: list[str]) -> tuple[bytes, bytes, str]:
    identity_rows = [(name, sha256(bundle / name)) for name in identity_files]
    identity_rows.extend((f"{path.name}.template", sha256(path))
                         for path in (worker_template, register_template))
    payload = "".join(f"{digest}  {name}\n" for name, digest in sorted(identity_rows)).encode()
    version = hashlib.sha256(payload).hexdigest()[:20]

    register_text = register_template.read_text(encoding="utf-8")
    register_token = "__BW_EXPECTED_CACHE_VERSION__"
    if register_text.count(register_token) != 1:
        raise ValueError("service-worker registration template token is absent/ambiguous")
    register = register_text.replace(register_token, version).encode("utf-8")

    precache = ["/"] + sorted("/" + name for name in cache_files if name != "_headers")
    cache_first: list[str] = []
    deferred: dict[str, str] = {}
    for row in rows:
        if row["role"] == "deferred":
            filename = str(row["filename"])
            query_url = f"/bin/{filename}?sha256={row['sha256']}"
            cache_first.append(query_url)
            precache[precache.index(f"/bin/{filename}")] = query_url
            deferred[f"/bin/{filename}"] = query_url
    precache = [precache[0]] + sorted(precache[1:])
    cache_first = [url for url in precache if url != "/service-worker-register.js"]
    digests: dict[str, str] = {}
    for name in cache_files:
        if name == "_headers":
            continue
        url = deferred.get(f"/{name}", f"/{name}")
        digests[url] = sha256(bundle / name)
    digests["/"] = digests["/index.html"]
    worker_text = worker_template.read_text(encoding="utf-8")
    tokens = {
        "__BW_CACHE_VERSION__": version,
        "__BW_PRECACHE_URLS__": json.dumps(precache, separators=(",", ":")),
        "__BW_CACHE_FIRST_URLS__": json.dumps(cache_first, separators=(",", ":")),
        "__BW_CACHE_SHA256__": json.dumps(sorted(digests.items()), separators=(",", ":")),
    }
    for token, value in tokens.items():
        if worker_text.count(token) != 1:
            raise ValueError(f"service-worker template token is absent/ambiguous: {token}")
        worker_text = worker_text.replace(token, value)
    return worker_text.encode("utf-8"), register, version


def verify_full(source_root: Path, source_bin: Path, bundle: Path,
                shipped_rows: list[dict[str, object]],
                public_manifest: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    """Verify every assembler output against its source or deterministic generator."""
    proof, failures = verify(source_bin, bundle / "bin")
    source_root = source_root.resolve(strict=True)
    bundle = bundle.resolve(strict=True)
    staged_root = source_root / "sandbox/m8-staged-deploy"
    shell = source_root / "platform_web/shell"
    copy_map = {
        "wgpu-preinit-worker.js": shell / "wgpu-preinit-worker.js",
        "fonts/bw-interface-sans.woff2": shell / "fonts/bw-interface-sans.woff2",
        "scenes/stress-mixed.blend": source_root / "sandbox/corpus-prep/corpus/stress_mixed.blend",
        "scenes/stress-mixed.blend.license": staged_root / "share-scene.license",
        "legal/LICENSE.txt": source_root / "LICENSE",
        "legal/AUTHORS.txt": source_root / "AUTHORS",
        "legal/NOTICE.txt": source_root / "NOTICE",
        "legal/THIRD-PARTY.md": source_root / "THIRD-PARTY.md",
        "legal/PROVENANCE.md": source_root / "PROVENANCE.md",
        "legal/LICENSES/Apache-2.0.txt": source_root / "LICENSES/Apache-2.0.txt",
        "legal/LICENSES/BSD-3-Clause.txt": source_root / "LICENSES/BSD-3-Clause.txt",
        "legal/LICENSES/Bitstream-Vera.txt": source_root / "LICENSES/Bitstream-Vera.txt",
        "legal/LICENSES/CC0-1.0.txt": source_root / "LICENSES/CC0-1.0.txt",
        "legal/LICENSES/GPL-2.0-or-later.txt": source_root / "LICENSES/GPL-2.0-or-later.txt",
        "legal/LICENSES/GPL-3.0-or-later.txt": source_root / "LICENSES/GPL-3.0-or-later.txt",
        "legal/LICENSES/OFL-1.1.txt": source_root / "LICENSES/OFL-1.1.txt",
        "legal/LICENSES/LicenseRef-OpenSubdiv-TOST-1.0.txt":
            source_root / "LICENSES/LicenseRef-OpenSubdiv-TOST-1.0.txt",
        "legal/THIRD_PARTY_NOTICES/OpenSubdiv-3.7.0-NOTICE.txt":
            source_root / "THIRD_PARTY_NOTICES/OpenSubdiv-3.7.0-NOTICE.txt",
        "legal/OpenUSD-26.03/LICENSE.txt":
            source_root / "lib/wasm/share/licenses/OpenUSD-26.03/LICENSE.txt",
        "legal/OpenUSD-26.03/NOTICE.txt":
            source_root / "lib/wasm/share/licenses/OpenUSD-26.03/NOTICE.txt",
    }
    derived: dict[str, dict[str, object]] = dict(proof.get("derived", {}))
    for name, source in copy_map.items():
        _compare_bytes(bundle / name, source.read_bytes(), str(source.relative_to(source_root)), failures)
        if (bundle / name).is_file():
            derived[name] = identity(bundle / name)

    minified_copy_map = {
        "diagnostics-bootstrap.js": shell / "diagnostics-bootstrap.js",
        "file-bridge.js": shell / "file-bridge.js",
        "pthread-main-loader.js": staged_root / "pthread-main-loader.js",
        "stage1-loader.js": staged_root / "stage1-loader.js",
    }
    for name, source in minified_copy_map.items():
        try:
            expected = minify_bytes(source.read_bytes())
        except (OSError, ValueError) as error:
            failures.append(f"cannot derive minified public shell {name}: {error}")
            continue
        _compare_bytes(bundle / name, expected,
                       f"deterministically minified {source.relative_to(source_root)}", failures)
        if (bundle / name).is_file():
            derived[name] = identity(bundle / name)

    boot = (shell / "boot-windowed.js").read_bytes()
    try:
        hardened_boot = harden_boot_source(boot)
    except ValueError as error:
        failures.append(f"boot-windowed public hardening failed: {error}")
    else:
        try:
            minified_boot = minify_bytes(hardened_boot)
        except ValueError as error:
            failures.append(f"cannot derive minified public boot-windowed.js: {error}")
        else:
            _compare_bytes(bundle / "boot-windowed.js", minified_boot,
                           "deterministic boot-windowed hardening and minification", failures)
    worker_source = bundle / "bin/blender_browser.worker.js"
    public_main = bundle / "bin/blender_browser.js"
    if public_main.is_file():
        _compare_bytes(worker_source, public_main.read_bytes(),
                       "public Stage-0 main glue", failures)
    else:
        failures.append("public Stage-0 main glue is absent for pthread derivation")
    if worker_source.is_file():
        derived["bin/blender_browser.worker.js"] = identity(worker_source)

    index = (shell / "windowed.html").read_text(encoding="utf-8")
    boot_tag = '<script src="/boot-windowed.js"></script>'
    boot_injected = boot_tag + "\n  <!-- STAGED DEPLOY: stream the deferred payload after first pixels, then cache it -->\n" \
        '  <script src="/stage1-loader.js"></script>\n' \
        '  <script src="/service-worker-register.js"></script>'
    main_tag = '<script src="/bin/blender_browser.js"></script>'
    pthread_injected = main_tag + \
        '\n  <!-- PUBLIC: one origin fetch supplies every in-memory pthread worker. -->\n' \
        '  <script src="/pthread-main-loader.js"></script>'
    if index.count(boot_tag) != 1:
        failures.append("windowed stage-loader injection seam is absent/ambiguous")
    if index.count(main_tag) != 1:
        failures.append("windowed pthread-loader injection seam is absent/ambiguous")
    if index.count(boot_tag) == 1 and index.count(main_tag) == 1:
        expected_index = index.replace(main_tag, pthread_injected, 1).replace(
            boot_tag, boot_injected, 1)
        _compare_bytes(bundle / "index.html", expected_index.encode(),
                       "deterministic staged index injection", failures)
    header_template = staged_root / "_headers"
    if not header_template.is_file():
        header_template = source_root / "sandbox/m8-deploy/_headers"
    _compare_bytes(bundle / "_headers", header_template.read_bytes() + HEADERS_SUFFIX.encode(),
                   "deterministic staged headers", failures)
    expected_public = json.dumps(public_manifest, indent=2, sort_keys=True).encode() + b"\n"
    _compare_bytes(bundle / "bin/split-build.json", expected_public,
                   "finalizer-owned public split projection", failures)
    for row in shipped_rows:
        name = str(row["filename"])
        _compare_bytes(bundle / "bin" / name, (source_bin / name).read_bytes(),
                       f"source build {name}", failures)

    cache_files = [
        "index.html", "diagnostics-bootstrap.js", "boot-windowed.js", "file-bridge.js",
        "pthread-main-loader.js", "wgpu-preinit-worker.js", "_headers", "stage1-loader.js",
        "service-worker-register.js",
        "fonts/bw-interface-sans.woff2",
        "scenes/stress-mixed.blend", "scenes/stress-mixed.blend.license",
        "legal/LICENSE.txt", "legal/AUTHORS.txt", "legal/NOTICE.txt", "legal/THIRD-PARTY.md",
        "legal/PROVENANCE.md", "legal/LICENSES/Apache-2.0.txt",
        "legal/LICENSES/BSD-3-Clause.txt", "legal/LICENSES/Bitstream-Vera.txt",
        "legal/LICENSES/CC0-1.0.txt",
        "legal/LICENSES/GPL-2.0-or-later.txt", "legal/LICENSES/GPL-3.0-or-later.txt",
        "legal/LICENSES/OFL-1.1.txt",
        "legal/LICENSES/LicenseRef-OpenSubdiv-TOST-1.0.txt",
        "legal/THIRD_PARTY_NOTICES/OpenSubdiv-3.7.0-NOTICE.txt",
        "legal/OpenUSD-26.03/LICENSE.txt", "legal/OpenUSD-26.03/NOTICE.txt",
        "bin/blender_browser.js", "bin/blender_browser.worker.js",
        "bin/blender_browser.data", "bin/split-build.json",
        "bin/stage1-manifest.json", "bin/stage1.data",
        *(f"bin/{row['filename']}" for row in shipped_rows),
    ]
    payload_br_names = [
        "bin/blender_browser.js.br", "bin/blender_browser.worker.js.br",
        "bin/blender_browser.data.br", "bin/stage1.data.br",
        *(f"bin/{row['filename']}.br" for row in shipped_rows),
    ]
    shell_br_names = [
        f"{name}.br" for name in (
            "index.html", "diagnostics-bootstrap.js", "file-bridge.js", "boot-windowed.js",
            "pthread-main-loader.js", "stage1-loader.js", "service-worker-register.js",
            "service-worker.js",
            "fonts/bw-interface-sans.woff2",
        )
    ]
    br_names = payload_br_names + shell_br_names
    # Generated service-worker controls contain the version token, so their
    # compressed representations cannot feed that token's own identity. The
    # exact bundle digest and deterministic Brotli replay still bind every .br.
    identity_files = [
        name for name in cache_files if name != "service-worker-register.js"
    ] + payload_br_names
    try:
        worker, register, version = render_controls(
            bundle, staged_root / "service-worker.js", staged_root / "service-worker-register.js",
            shipped_rows, cache_files, identity_files)
        _compare_bytes(bundle / "service-worker.js", worker,
                       "deterministic service-worker template expansion", failures)
        _compare_bytes(bundle / "service-worker-register.js", register,
                       "deterministic service-worker registration expansion", failures)
        proof["cache_version"] = version
    except (OSError, ValueError, KeyError) as error:
        failures.append(f"cannot deterministically generate service-worker controls: {error}")

    with tempfile.TemporaryDirectory(prefix="bw-stage-brotli-") as temporary:
        for name in br_names:
            raw = bundle / name[:-3]
            expected_br = Path(temporary) / Path(name).name
            try:
                result = subprocess.run(
                    [str(PINNED_NODE), str(BROTLI_CODEC), "encode",
                     str(raw), str(expected_br)], capture_output=True, text=True)
            except OSError as error:
                failures.append(f"cannot execute deterministic Brotli codec: {error}")
                break
            if result.returncode != 0 or not filecmp.cmp(expected_br, bundle / name, shallow=False):
                failures.append(
                    f"Brotli output is not deterministic q11/lgwin=24 source bytes: {name}")
    proof["brotli"] = {
        "path": str(BROTLI_CODEC.relative_to(ROOT)),
        **identity(BROTLI_CODEC),
        "node_version": "v22.16.0",
        "quality": 11,
        "lgwin": 24,
    }
    proof["public_shell_minifier"] = {
        "path": str(PUBLIC_MINIFIER.relative_to(ROOT)),
        **identity(PUBLIC_MINIFIER),
        "node_version": "v22.16.0",
        "terser_version": "5.39.0",
        "terser_bundle": identity(TERSER_BUNDLE),
        "compress_passes": 2,
    }
    proof["derived"] = derived
    proof["full_stage"] = not failures
    return proof, failures


def selfcheck() -> None:
    minifier_contract = subprocess.run(
        [str(PINNED_NODE), str(PUBLIC_MINIFIER), "--selfcheck"],
        cwd=ROOT, capture_output=True, text=True
    )
    assert minifier_contract.returncode == 0 and \
        "BW_PUBLIC_SHELL_MINIFIER_SELFCHECK_PASS node=v22.16.0 terser=5.39.0" in \
        minifier_contract.stdout
    with tempfile.TemporaryDirectory(prefix="bw-minified-stage-contract-") as temporary:
        minified_stage = Path(temporary) / "stage1-loader.js"
        minified_stage.write_bytes(minify_bytes(
            (ROOT / "sandbox/m8-staged-deploy/stage1-loader.js").read_bytes()))
        minified_contract = subprocess.run(
            [str(PINNED_NODE), str(PUBLIC_QUERY_CONTRACT), str(minified_stage),
             "--positive-only"], cwd=ROOT, capture_output=True, text=True)
        assert minified_contract.returncode == 0 and \
            "M8_PUBLIC_QUERY_HARDENING_MINIFIED_PASS" in minified_contract.stdout
        minified_pthread = Path(temporary) / "pthread-main-loader.js"
        minified_pthread.write_bytes(minify_bytes(
            (ROOT / "sandbox/m8-staged-deploy/pthread-main-loader.js").read_bytes()))
        pthread_contract = subprocess.run(
            [str(PINNED_NODE), str(PTHREAD_LOADER_CONTRACT), str(minified_pthread)],
            cwd=ROOT, capture_output=True, text=True)
        assert pthread_contract.returncode == 0 and \
            "M8_PTHREAD_MAIN_LOADER_CONTRACT_PASS" in pthread_contract.stdout
    wire_sources = (
        ("diagnostics-bootstrap.js",
         (ROOT / "platform_web/shell/diagnostics-bootstrap.js").read_bytes()),
        ("file-bridge.js", (ROOT / "platform_web/shell/file-bridge.js").read_bytes()),
        ("boot-windowed.js", harden_boot_source(
            (ROOT / "platform_web/shell/boot-windowed.js").read_bytes())),
        ("pthread-main-loader.js",
         (ROOT / "sandbox/m8-staged-deploy/pthread-main-loader.js").read_bytes()),
        ("stage1-loader.js",
         (ROOT / "sandbox/m8-staged-deploy/stage1-loader.js").read_bytes()),
    )
    raw_wire = 0
    minified_wire = 0
    with tempfile.TemporaryDirectory(prefix="bw-public-shell-wire-") as temporary:
        wire_root = Path(temporary)
        for name, source in wire_sources:
            raw = wire_root / f"raw-{name}"
            minified = wire_root / f"minified-{name}"
            raw.write_bytes(source)
            minified.write_bytes(minify_bytes(source))
            for path, kind in ((raw, "raw"), (minified, "minified")):
                encoded = wire_root / f"{path.name}.br"
                result = subprocess.run(
                    [str(PINNED_NODE), str(BROTLI_CODEC), "encode",
                     str(path), str(encoded)], cwd=ROOT, capture_output=True, text=True)
                assert result.returncode == 0 and encoded.is_file()
                if kind == "raw":
                    raw_wire += encoded.stat().st_size
                else:
                    minified_wire += encoded.stat().st_size
    wire_tuple = (raw_wire, minified_wire, raw_wire - minified_wire)
    assert wire_tuple == (27555, 13944, 13611), wire_tuple
    codec_contract = subprocess.run(
        [str(PINNED_NODE), str(BROTLI_CODEC), "--selfcheck"],
        cwd=ROOT, capture_output=True, text=True
    )
    assert codec_contract.returncode == 0 and \
        "BW_BROTLI_Q11_SELFCHECK_PASS node=v22.16.0 quality=11 lgwin=24" in \
        codec_contract.stdout
    codec_source = BROTLI_CODEC.read_text(encoding="utf-8")
    codec_mutations = (
        ('const PINNED_NODE_VERSION = "v22.16.0";',
         'const PINNED_NODE_VERSION = "v25.1.0";'),
        ("const QUALITY = 11;", "const QUALITY = 10;"),
        ("const LGWIN = 24;", "const LGWIN = 22;"),
        ("a5077aeebb2f4d96af19e64de3de26a11b56382106d3db388dccf400ff82ef62",
         "b5077aeebb2f4d96af19e64de3de26a11b56382106d3db388dccf400ff82ef62"),
    )
    with tempfile.TemporaryDirectory(prefix="bw-brotli-codec-mutations-") as temporary:
        for index, (old, new) in enumerate(codec_mutations):
            assert codec_source.count(old) == 1
            mutated = Path(temporary) / f"codec-{index}.mjs"
            mutated.write_text(codec_source.replace(old, new, 1), encoding="utf-8")
            result = subprocess.run(
                [str(PINNED_NODE), str(mutated), "--selfcheck"],
                cwd=ROOT, capture_output=True, text=True)
            assert result.returncode != 0, f"codec mutation {index} passed unexpectedly"
    packer_contract = subprocess.run(
        [sys.executable, str(STAGE_PACK_CONTRACT)], cwd=ROOT, capture_output=True, text=True
    )
    assert packer_contract.returncode == 0 and \
        "BW_STAGE_PACK_CONTRACT_PASS classifications=572 discovery=5 positive=9 negative=13" in \
        packer_contract.stdout
    with tempfile.TemporaryDirectory(prefix="bw-stage-provenance-selfcheck-") as temporary:
        root = Path(temporary)
        source = root / "source"
        staged = root / "staged"
        source.mkdir()
        blob = b"KEEPDEFER"
        glue = (
            'prefix;Module["FS_createPath"]("/","usd",true,true);'
            'loadPackage({files:[{filename:"/keep",start:0,end:4},'
            '{filename:"/usd/defer",start:4,end:9}],remote_package_size:9});suffix;'
        )
        (source / "blender_browser.js").write_text(glue, encoding="utf-8")
        (source / "blender_browser.data").write_bytes(blob)
        derive(source, staged)
        proof, failures = verify(source, staged)
        assert not failures and proof["schema"] == 1
        rejected: list[str] = []
        for name in DERIVED_NAMES:
            path = staged / name
            original = path.read_bytes()
            path.write_bytes(original + b"tamper")
            if verify(source, staged)[1]:
                rejected.append(name)
            path.write_bytes(original)
        original_data = (source / "blender_browser.data").read_bytes()
        (source / "blender_browser.data").write_bytes(original_data + b"x")
        assert verify(source, staged)[1]
        assert rejected == list(DERIVED_NAMES)
        static_source = root / "diagnostics-bootstrap.js"
        static_bundle = root / "bundle" / "diagnostics-bootstrap.js"
        static_bundle.parent.mkdir()
        static_source.write_bytes(b"const trustedDiagnostics = () => 42;\n")
        static_bundle.write_bytes(minify_bytes(static_source.read_bytes()))
        comparator_failures: list[str] = []
        _compare_bytes(static_bundle, minify_bytes(static_source.read_bytes()),
                       "minified diagnostics source",
                       comparator_failures)
        assert not comparator_failures
        static_bundle.write_bytes(b"no-op API returning [] with preserved marker strings")
        _compare_bytes(static_bundle, minify_bytes(static_source.read_bytes()),
                       "minified diagnostics source",
                       comparator_failures)
        assert comparator_failures

        controls = root / "controls"
        controls.mkdir()
        (controls / "index.html").write_text("index", encoding="utf-8")
        worker_template = root / "service-worker.js"
        register_template = root / "service-worker-register.js"
        worker_template.write_text(
            "const V='__BW_CACHE_VERSION__';\nconst P=__BW_PRECACHE_URLS__;\n"
            "const F=__BW_CACHE_FIRST_URLS__;\nconst S=__BW_CACHE_SHA256__;\n",
            encoding="utf-8")
        register_template.write_text("const V='__BW_EXPECTED_CACHE_VERSION__';\n",
                                     encoding="utf-8")
        worker, register, _version = render_controls(
            controls, worker_template, register_template, [], ["index.html"], ["index.html"])
        (controls / "service-worker.js").write_bytes(worker)
        (controls / "service-worker-register.js").write_bytes(register)
        control_failures: list[str] = []
        _compare_bytes(controls / "service-worker.js", worker, "worker generator", control_failures)
        _compare_bytes(controls / "service-worker-register.js", register,
                       "register generator", control_failures)
        assert not control_failures
        (controls / "service-worker.js").write_bytes(worker + b"behavior drift")
        (controls / "service-worker-register.js").write_bytes(register + b"behavior drift")
        _compare_bytes(controls / "service-worker.js", worker, "worker generator", control_failures)
        _compare_bytes(controls / "service-worker-register.js", register,
                       "register generator", control_failures)
        assert len(control_failures) == 2
    print("M8_STAGE_PROVENANCE_SELFCHECK_PASS derived=4 negatives=8 codec=1/4 "
          "minifier=5/6 minified_stage=23 pthread=10/10 wire=27555->13944(-13611) "
          "packer=572/5/9/13 "
          "coherent=diagnostics+worker+register")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-bin", type=Path)
    parser.add_argument("--staged-bin", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        selfcheck()
        return 0
    if args.source_bin is None or args.staged_bin is None:
        parser.error("--source-bin and --staged-bin are required")
    proof, failures = verify(args.source_bin, args.staged_bin)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(proof)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
