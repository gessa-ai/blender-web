#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# serve_measure.py [PORT] [DOCROOT] - COOP/COEP static server that mirrors the
# PRODUCTION _headers cache policy (Cache-Control: public, max-age=3600 on /bin/*),
# so WARM boots can reuse the HTTP + compiled-wasm cache exactly as they will when
# hosted. (serve_bundle.py forces no-store, which defeats warm measurement.)
import http.server, os, socketserver, sys
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8130
DOCROOT = sys.argv[2] if len(sys.argv) > 2 else "."
if not os.path.isdir(DOCROOT):
    sys.exit(f"serve_measure: docroot not found: {DOCROOT}")

CTYPE = {".wasm": "application/wasm", ".js": "text/javascript",
         ".data": "application/octet-stream", ".html": "text/html",
         ".json": "application/json"}

class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **CTYPE}
    def __init__(self, *a, **k): super().__init__(*a, directory=DOCROOT, **k)

    def send_head(self):
        # Serve a precompressed .br sibling (Content-Encoding: br) when the client
        # accepts br - the CDP throttle then measures the REALISTIC compressed wire,
        # exactly as Cloudflare would serve it. Falls back to the raw file otherwise.
        p = self.path.split("?", 1)[0]
        if "br" in self.headers.get("Accept-Encoding", ""):
            rel = p.lstrip("/")
            brpath = os.path.join(DOCROOT, rel + ".br")
            rawpath = os.path.join(DOCROOT, rel)
            if os.path.isfile(brpath) and os.path.isfile(rawpath):
                ext = os.path.splitext(rel)[1]
                try:
                    f = open(brpath, "rb"); st = os.fstat(f.fileno())
                except OSError:
                    return super().send_head()
                self.send_response(200)
                self.send_header("Content-Type", CTYPE.get(ext, "application/octet-stream"))
                self.send_header("Content-Encoding", "br")
                self.send_header("Content-Length", str(st.st_size))
                self.end_headers()
                return f
        return super().send_head()
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        p = self.path.split("?", 1)[0]
        # Production policy: cache the immutable payload; never cache the document.
        if p.startswith("/bin/"):
            self.send_header("Cache-Control", "public, max-age=3600")
        else:
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()
    def log_message(self, *a): pass

socketserver.TCPServer.allow_reuse_address = True
class S(socketserver.ThreadingTCPServer): daemon_threads = True
with S(("127.0.0.1", PORT), H) as httpd:
    print(f"serve_measure: {DOCROOT} @ http://127.0.0.1:{PORT} (prod cache policy)", flush=True)
    httpd.serve_forever()
