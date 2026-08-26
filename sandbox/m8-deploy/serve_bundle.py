#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# serve_bundle.py - minimal cross-origin-isolated static server for LOCAL
# verification of the M8 deploy bundle. Mirrors the production Cloudflare Pages
# `_headers` (COOP/COEP/CORP) and the MIME expectations documented in README.md so
# the bundle boots here exactly as it will when hosted. Prepare/verify-only; not a
# production server.
#
# Usage:  python3 serve_bundle.py [PORT] [DOCROOT]
#   PORT     default 8130 (this lane's port)
#   DOCROOT  default sandbox/m8-deploy/bundle
#
# The three headers below are the whole point: without COOP+COEP the page is not
# crossOriginIsolated, SharedArrayBuffer is undefined, and the -pthread wasm aborts
# before WM_main. `application/wasm` is required for WebAssembly.instantiateStreaming.
import http.server
import os
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8130
DOCROOT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bundle"
)

if not os.path.isdir(DOCROOT):
    sys.stderr.write(
        f"serve_bundle: docroot not found: {DOCROOT}\n"
        f"  run make_bundle.sh first.\n"
    )
    sys.exit(1)


class Handler(http.server.SimpleHTTPRequestHandler):
    # Match the bundle _headers MIME contract. `.data` has no registered type;
    # Emscripten fetches it as an ArrayBuffer so octet-stream is correct.
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".js": "text/javascript",
        ".data": "application/octet-stream",
        ".html": "text/html",
        ".json": "application/json",
        ".woff2": "font/woff2",
    }

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DOCROOT, **kw)

    def end_headers(self):
        # Cross-origin isolation (== the production _headers /* block).
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        # Local dev: never cache, so a rebuilt binary is always re-fetched.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("serve_bundle: %s\n" % (fmt % args))


socketserver.TCPServer.allow_reuse_address = True


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True


with Server(("127.0.0.1", PORT), Handler) as httpd:
    print(f"serve_bundle: serving {DOCROOT} at http://127.0.0.1:{PORT}", flush=True)
    print(f"serve_bundle: index -> http://127.0.0.1:{PORT}/index.html", flush=True)
    httpd.serve_forever()
