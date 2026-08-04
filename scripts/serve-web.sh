#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Tiny local static server for the M4.pre browser boot shell.
#
# Serves two roots under one origin with the COOP/COEP headers that
# SharedArrayBuffer (pthreads) requires:
#   /            -> platform_web/shell/  (index.html, boot.js)
#   /bin/<file>  -> build-wasm/bin/      (blender_browser.{js,wasm,data} + worker)
#
# Usage:  scripts/serve-web.sh [PORT]        (default 8000)
#         BLENDER_WEB_BIN=/path/to/bin scripts/serve-web.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-${PORT:-8000}}"
BIN_DIR="${BLENDER_WEB_BIN:-$ROOT/build-wasm/bin}"
SHELL_DIR="$ROOT/platform_web/shell"

if [ ! -f "$SHELL_DIR/index.html" ]; then
  echo "serve-web: missing $SHELL_DIR/index.html" >&2; exit 1
fi
if [ ! -f "$BIN_DIR/blender_browser.js" ]; then
  echo "serve-web: $BIN_DIR/blender_browser.js not found — build it first:" >&2
  echo "  (configure with -DWITH_BLENDER_WEB_BROWSER=ON, then) ninja blender_browser" >&2
  # Not fatal: allow serving so the shell can still be inspected.
fi

export PORT BIN_DIR SHELL_DIR
exec python3 <<'PYEOF'
import os, sys, http.server, socketserver

PORT = int(os.environ["PORT"])
BIN_DIR = os.path.realpath(os.environ["BIN_DIR"])
SHELL_DIR = os.path.realpath(os.environ["SHELL_DIR"])

EXTRA_TYPES = {".wasm": "application/wasm", ".data": "application/octet-stream",
               ".js": "text/javascript", ".mjs": "text/javascript"}

class Handler(http.server.SimpleHTTPRequestHandler):
    def _resolve(self, path):
        # strip query/fragment, normalize
        p = path.split("?", 1)[0].split("#", 1)[0]
        p = os.path.normpath(p).replace("\\", "/")
        if p in ("/bin", "/bin/") or p.startswith("/bin/"):
            base, rel = BIN_DIR, p[len("/bin"):].lstrip("/")
        else:
            base, rel = SHELL_DIR, p.lstrip("/")
            if rel == "":
                rel = "index.html"
        full = os.path.realpath(os.path.join(base, rel))
        # containment check — no traversal outside the two roots
        if full != base and not full.startswith(base + os.sep):
            return os.path.join(base, "index.html")
        return full

    def translate_path(self, path):
        return self._resolve(path)

    def guess_type(self, path):
        ext = os.path.splitext(str(path))[1].lower()
        if ext in EXTRA_TYPES:
            return EXTRA_TYPES[ext]
        return super().guess_type(path)

    def end_headers(self):
        # Mandatory for SharedArrayBuffer / pthreads.
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

print("=" * 64)
print("  blender-web M4.pre shell:  http://localhost:%d/" % PORT)
print("  COOP=same-origin  COEP=require-corp  (SharedArrayBuffer enabled)")
print("  shell = %s" % SHELL_DIR)
print("  /bin  = %s" % BIN_DIR)
print("  Ctrl-C to stop.")
print("=" * 64)
sys.stdout.flush()

with Server(("127.0.0.1", PORT), Handler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nserve-web: stopped.")
PYEOF
