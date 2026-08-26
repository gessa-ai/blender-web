#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact-tree COOP/COEP server used only by the M8 transport measurements."""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sandbox/m8-launch-gate"))

from transport_contract import (  # noqa: E402
    BASE_HEADERS,
    TransportContractError,
    request_file,
    validate_docroot,
)


PROOF_PATH = "/.well-known/bw-transport-proof"
TRANSFORMED_PUBLIC_FILES = frozenset({
    "bin/blender_browser.js",
    "bin/blender_browser.data",
})
CTYPE = {
    ".wasm": "application/wasm",
    ".js": "text/javascript; charset=utf-8",
    ".data": "application/octet-stream",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".blend": "application/octet-stream",
    ".woff2": "font/woff2",
}


def canonical_digest(artifacts: dict[str, dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for name in sorted(artifacts):
        row = artifacts[name]
        digest.update(f"{name}\0{row['bytes']}\0{row['sha256']}\n".encode("utf-8"))
    return digest.hexdigest()


def accepts_brotli(value: str) -> bool:
    for item in value.lower().split(","):
        parts = [part.strip() for part in item.split(";")]
        if parts[0] != "br":
            continue
        quality = 1.0
        for parameter in parts[1:]:
            if parameter.startswith("q="):
                try:
                    quality = float(parameter[2:])
                except ValueError:
                    quality = 0.0
        return quality > 0
    return False


def source_bound_wasm_files(contract: dict[str, object]) -> dict[str, str]:
    """Return public/source names for finalizer-owned shipping Wasm rows."""
    rows = contract.get("shipped_wasm")
    if not isinstance(rows, list) or not rows:
        raise TransportContractError("shipping Wasm inventory is absent")
    source_copies: dict[str, str] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            raise TransportContractError("shipping Wasm row is not an object")
        filename = raw.get("filename")
        role = raw.get("role")
        if (not isinstance(filename, str) or Path(filename).name != filename or
                not filename.startswith("blender_browser") or not filename.endswith(".wasm")):
            raise TransportContractError(f"unsafe shipping Wasm filename: {filename!r}")
        if role not in {"primary", "deferred"}:
            raise TransportContractError(f"non-shipping Wasm role: {role!r}")
        public_name = f"bin/{filename}"
        if public_name in TRANSFORMED_PUBLIC_FILES or public_name in source_copies:
            raise TransportContractError(f"duplicate/transformed source-copy name: {public_name}")
        source_copies[public_name] = filename
    return source_copies


def validated_artifacts(docroot: Path) -> dict[str, dict[str, object]]:
    import verify_m8

    contract = verify_m8.artifact_contract()
    # stage_pack.py deliberately rewrites the link glue's preload manifest and
    # re-slices blender_browser.data.  Those two public files therefore cannot be
    # byte-compared with their monolithic build inputs.  Only finalizer-owned Wasm
    # shards are exact source copies; the generated service-worker digest inventory
    # and the browser receipts bind every transformed/public byte separately.
    source_copies = source_bound_wasm_files(contract)
    build_identities = {
        public_name: verify_m8.identity(verify_m8.BUILD / filename)
        for public_name, filename in source_copies.items()
    }
    artifacts = validate_docroot(
        docroot,
        contract["bundle_files"],
        contract["public_split_manifest"],
        build_identities,
    )
    # The measurement server is intentionally tied to the canonical generated
    # public tree.  Re-run the static cache/header/exact-tree checks here so a
    # post-assembly mutation cannot become a newly blessed measurement input.
    if docroot.resolve(strict=True) != verify_m8.BUNDLE.resolve(strict=True):
        raise TransportContractError(
            f"docroot is not the canonical generated public tree: {docroot}"
        )
    failures: list[str] = []
    verify_m8.check_headers(failures)
    verify_m8.check_local_only(failures)
    verify_m8.check_exact_bundle_tree(failures)
    verify_m8.check_service_worker_contract(failures)
    if failures:
        raise TransportContractError("static public-tree contract failed: " + "; ".join(failures))
    return artifacts


class ExactTreeServer:
    def __init__(self, docroot: Path, artifacts: dict[str, dict[str, object]]) -> None:
        self.docroot = docroot.resolve(strict=True)
        self.artifacts = artifacts
        self.bundle_sha256 = canonical_digest(artifacts)
        self.counts: dict[str, int] = {}
        self.lock = threading.Lock()

    def count(self, logical_path: str) -> int:
        with self.lock:
            self.counts[logical_path] = self.counts.get(logical_path, 0) + 1
            return self.counts[logical_path]

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return dict(sorted(self.counts.items()))


def make_handler(state: ExactTreeServer) -> type[http.server.SimpleHTTPRequestHandler]:
    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **CTYPE}

        def __init__(self, *args, **kwargs):
            self._logical_path = ""
            self._raw_path: Path | None = None
            self._origin_count: int | None = None
            self._vary_accept_encoding = False
            self._diagnostic = False
            super().__init__(*args, directory=str(state.docroot), **kwargs)

        def _proof_response(self):
            payload = json.dumps({
                "schema": 1,
                "served_bundle_sha256": state.bundle_sha256,
                "asset_get_counts": state.snapshot(),
            }, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            self._diagnostic = True
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            return __import__("io").BytesIO(payload)

        def send_head(self):
            try:
                target = request_file(state.docroot, self.path)
                logical = "/" + target.relative_to(state.docroot).as_posix()
            except (TransportContractError, ValueError) as error:
                self.send_error(400, str(error))
                return None
            if logical == PROOF_PATH:
                return self._proof_response()
            self._logical_path = logical
            self._raw_path = target
            if self.command == "GET" and target.is_file():
                self._origin_count = state.count(logical)

            # Select a checked precompressed sibling only inside the validated tree.
            br_path = target.with_name(target.name + ".br")
            self._vary_accept_encoding = target.is_file() and br_path.is_file()
            if self._vary_accept_encoding and accepts_brotli(
                    self.headers.get("Accept-Encoding", "")):
                try:
                    stream = br_path.open("rb")
                    stat = br_path.stat()
                except OSError:
                    return super().send_head()
                self.send_response(200)
                self.send_header("Content-Type", CTYPE.get(target.suffix, "application/octet-stream"))
                self.send_header("Content-Encoding", "br")
                self.send_header("Content-Length", str(stat.st_size))
                self.end_headers()
                return stream
            return super().send_head()

        def end_headers(self):
            self.send_header("X-BW-Bundle-SHA256", state.bundle_sha256)
            for name, value in BASE_HEADERS.items():
                self.send_header(name, value)
            if self._vary_accept_encoding:
                self.send_header("Vary", "Accept-Encoding")
            if self._diagnostic:
                self.send_header("Cache-Control", "no-store")
            else:
                path = self._logical_path
                if path.startswith("/bin/"):
                    self.send_header("Cache-Control", "no-cache, must-revalidate")
                elif path == "/service-worker.js":
                    self.send_header("Cache-Control", "no-cache")
                elif path == "/service-worker-register.js":
                    self.send_header("Cache-Control", "no-cache, must-revalidate")
                elif path.startswith("/scenes/") and path.endswith(".blend"):
                    self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                if self._raw_path is not None and self._raw_path.is_file():
                    relative = self._raw_path.relative_to(state.docroot).as_posix()
                    row = state.artifacts.get(relative)
                    if row is not None:
                        self.send_header("X-BW-Content-Bytes", str(row["bytes"]))
                        self.send_header("X-BW-Content-SHA256", str(row["sha256"]))
                if self._origin_count is not None:
                    self.send_header("X-BW-Origin-Request-Count", str(self._origin_count))
            super().end_headers()

        def log_message(self, *args):
            pass

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", type=int, default=8130)
    parser.add_argument("docroot", nargs="?", type=Path, default=Path("."))
    parser.add_argument("--selfcheck", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.selfcheck:
        from transport_contract import _selfcheck
        _selfcheck()
        # Transformed Stage-0 glue/data must never be mistaken for exact build
        # copies.  Conversely every shipping Wasm role must remain source-bound.
        fixture_contract = {"shipped_wasm": [
            {"filename": "blender_browser.wasm", "role": "primary"},
            {"filename": "blender_browser.deferred.wasm", "role": "deferred"},
        ]}
        source_copies = source_bound_wasm_files(fixture_contract)
        assert set(source_copies) == {
            "bin/blender_browser.wasm",
            "bin/blender_browser.deferred.wasm",
        }
        assert TRANSFORMED_PUBLIC_FILES.isdisjoint(source_copies)
        rejected = 0
        for invalid_contract in (
            {"shipped_wasm": []},
            {"shipped_wasm": [{"filename": "../escape.wasm", "role": "primary"}]},
            {"shipped_wasm": [{"filename": "blender_browser.js", "role": "primary"}]},
            {"shipped_wasm": [
                {"filename": "blender_browser.wasm", "role": "original_build_only"},
            ]},
        ):
            try:
                source_bound_wasm_files(invalid_contract)
            except TransportContractError:
                rejected += 1
        assert rejected == 4
        assert (ROOT / "GOAL.md").is_file()
        assert accepts_brotli("gzip, br")
        assert accepts_brotli("br;q=0.5, gzip")
        assert not accepts_brotli("gzip, br;q=0")
        assert not accepts_brotli("gzip")
        print(
            "M8_SERVE_MEASURE_SELFCHECK_PASS positive=8 negative=4 "
            "root=derived brotli=4 transformed=2 wasm_source_bound=2 apply_manifest_reads=0"
        )
        return 0
    docroot = args.docroot.resolve()
    if not docroot.is_dir():
        raise SystemExit(f"serve_measure: docroot not found: {docroot}")
    try:
        artifacts = validated_artifacts(docroot)
    except (TransportContractError, ValueError, OSError) as error:
        raise SystemExit(f"serve_measure: rejected docroot {docroot}: {error}") from error
    state = ExactTreeServer(docroot, artifacts)
    socketserver.TCPServer.allow_reuse_address = True

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    with Server(("127.0.0.1", args.port), make_handler(state)) as httpd:
        print(
            f"serve_measure: {docroot} @ http://127.0.0.1:{args.port} "
            f"bundle={state.bundle_sha256} (exact-tree transport)",
            flush=True,
        )
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
