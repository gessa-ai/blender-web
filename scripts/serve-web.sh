#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Tiny local static server for the browser product and legacy M4.pre shell.
#
# Serves two roots under one origin with the COOP/COEP headers that
# SharedArrayBuffer (pthreads) requires:
#   /            -> platform_web/shell/windowed.html when present
#   /index.html  -> the legacy headless M4.pre shell
#   /bin/<file>  -> build-wasm-windowed-opt/bin/ (product payload + worker)
#
# Usage:  scripts/serve-web.sh [PORT]        (default 8000)
#         BLENDER_WEB_BIN=/path/to/bin scripts/serve-web.sh
#         BLENDER_WEB_ENTRY=index.html scripts/serve-web.sh  # legacy headless root
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-${PORT:-8000}}"
BIN_DIR="${BLENDER_WEB_BIN:-$ROOT/build-wasm-windowed-opt/bin}"
# Docroot for "/". Override it for a standalone harness (for example,
# BLENDER_WEB_SHELL=platform_web/ghost/harness). Such index-only harnesses keep
# their existing root automatically.
SHELL_DIR="${BLENDER_WEB_SHELL:-$ROOT/platform_web/shell}"

if [ ! -d "$SHELL_DIR" ]; then
  echo "serve-web: shell directory not found: $SHELL_DIR" >&2; exit 1
fi

# The checked-in shell contains both the obsolete headless M4.pre page and the
# shipping windowed page. Make the product page the no-surprises default while
# keeping index-only harnesses and an explicit legacy override working.
DEFAULT_ENTRY="index.html"
if [ -f "$SHELL_DIR/windowed.html" ]; then
  DEFAULT_ENTRY="windowed.html"
fi
ENTRY_NAME="${BLENDER_WEB_ENTRY:-$DEFAULT_ENTRY}"
if [ ! -f "$BIN_DIR/blender_browser.js" ]; then
  echo "serve-web: $BIN_DIR/blender_browser.js not found — build it first:" >&2
  echo "  (configure with -DWITH_BLENDER_WEB_BROWSER=ON, then) ninja blender_browser" >&2
  # Not fatal: allow serving so the shell can still be inspected.
fi

export PORT BIN_DIR SHELL_DIR ENTRY_NAME
exec python3 <<'PYEOF'
import os, sys, http.server, socketserver

PORT = int(os.environ["PORT"])
BIN_DIR = os.path.realpath(os.environ["BIN_DIR"])
SHELL_DIR = os.path.realpath(os.environ["SHELL_DIR"])
ENTRY_NAME = os.environ["ENTRY_NAME"]
ENTRY_FILE = os.path.realpath(os.path.join(SHELL_DIR, ENTRY_NAME))
try:
    entry_is_contained = (os.path.commonpath((SHELL_DIR, ENTRY_FILE)) == SHELL_DIR and
                          ENTRY_FILE != SHELL_DIR)
except ValueError:
    entry_is_contained = False
if not entry_is_contained:
    sys.exit("serve-web: entry escapes shell directory: %s" % ENTRY_NAME)
if not os.path.isfile(ENTRY_FILE):
    sys.exit("serve-web: entry not found: %s" % ENTRY_FILE)

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
                return ENTRY_FILE
        full = os.path.realpath(os.path.join(base, rel))
        # containment check — no traversal outside the two roots
        if full != base and not full.startswith(base + os.sep):
            return ENTRY_FILE
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
print("  blender-web local shell:  http://localhost:%d/" % PORT)
print("  COOP=same-origin  COEP=require-corp  (SharedArrayBuffer enabled)")
print("  shell = %s" % SHELL_DIR)
print("  entry = %s" % ENTRY_NAME)
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
