#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Threaded COOP/COEP split-artifact server with byte-exact transfer receipts."""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import socketserver
import threading
import time
from pathlib import Path


def identity(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int)
    parser.add_argument("docroot", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("--identity-root", type=Path, action="append", default=[])
    args = parser.parse_args()
    docroot = args.docroot.resolve()
    log_path = args.log.resolve()
    if not docroot.is_dir():
        raise SystemExit(f"missing docroot: {docroot}")
    if log_path.exists():
        raise SystemExit(f"refusing overwrite: {log_path}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("x", encoding="utf-8")
    log_lock = threading.Lock()
    identity_roots = [docroot, *(path.resolve() for path in args.identity_root)]
    identities: dict[str, dict[str, object]] = {}
    for root in identity_roots:
        if not root.is_dir():
            raise SystemExit(f"missing identity root: {root}")
        for path in root.rglob("*.wasm"):
            resolved = path.resolve()
            if resolved.is_file():
                identities[str(resolved)] = identity(resolved)

    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".wasm": "application/wasm"}

        def __init__(self, *handler_args, **handler_kwargs):
            self._status = None
            self._started = time.perf_counter()
            super().__init__(*handler_args, directory=str(docroot), **handler_kwargs)

        def send_response(self, code, message=None):
            self._status = code
            return super().send_response(code, message)

        def end_headers(self):
            path = Path(self.translate_path(self.path)).resolve()
            row = identities.get(str(path))
            if row:
                self.send_header("X-BW-Content-SHA256", str(row["sha256"]))
                self.send_header("X-BW-Content-Bytes", str(row["bytes"]))
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def copyfile(self, source, outputfile):
            path = Path(self.translate_path(self.path)).resolve()
            expected = identities.get(str(path))
            if not expected:
                return super().copyfile(source, outputfile)
            sent = 0
            error = None
            try:
                while chunk := source.read(1024 * 1024):
                    outputfile.write(chunk)
                    sent += len(chunk)
            except (BrokenPipeError, ConnectionResetError) as exc:
                error = type(exc).__name__
            row = {
                "path": self.path.split("?", 1)[0],
                "request_target": self.path,
                "status": self._status,
                "bytes_sent": sent,
                "expected_bytes": expected["bytes"],
                "sha256": expected["sha256"],
                "complete": sent == expected["bytes"] and error is None,
                "error": error,
                "elapsed_ms": round((time.perf_counter() - self._started) * 1000, 3),
                "client": self.client_address[0],
            }
            with log_lock:
                log_handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
                log_handle.flush()

        def log_message(self, *_args):
            pass

    socketserver.TCPServer.allow_reuse_address = True

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    try:
        with Server(("127.0.0.1", args.port), Handler) as server:
            print(json.dumps({"ready": True, "port": args.port, "docroot": str(docroot),
                              "log": str(log_path), "wasm": identities}, sort_keys=True), flush=True)
            server.serve_forever()
    finally:
        log_handle.close()


if __name__ == "__main__":
    main()
