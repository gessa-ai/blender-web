#!/usr/bin/env python3
"""COOP/COEP static server: / -> shell/windowed.html, /bin/ -> bin dir."""
import os, sys, http.server, socketserver

SHELL_DIR = os.path.abspath(sys.argv[1])
BIN_DIR = os.path.abspath(sys.argv[2])
PORT = int(sys.argv[3])
MIME = {".wasm": "application/wasm", ".js": "text/javascript", ".mjs": "text/javascript",
        ".html": "text/html", ".json": "application/json", ".data": "application/octet-stream",
        ".css": "text/css", ".png": "image/png", ".blend": "application/octet-stream"}

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _resolve(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path in ("/", ""): return os.path.join(SHELL_DIR, "windowed.html")
        if path.startswith("/bin/"): root, rel = BIN_DIR, path[5:]
        else: root, rel = SHELL_DIR, path.lstrip("/")
        full = os.path.abspath(os.path.join(root, rel))
        return full if full.startswith(root) else None
    def _headers(self, full, length, status=200, partial=None, total=None):
        self.send_response(status)
        self.send_header("Content-Type", MIME.get(os.path.splitext(full)[1].lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(length))
        if partial: self.send_header("Content-Range", f"bytes {partial[0]}-{partial[1]}/{total}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
    def do_HEAD(self): self.do_GET(True)
    def do_GET(self, head_only=False):
        full = self._resolve(self.path)
        if not full or not os.path.isfile(full):
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
        size = os.path.getsize(full); start, end, status, partial = 0, size - 1, 200, None
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].split(",")[0].partition("-")
            if a: start, end = int(a), (int(b) if b else size - 1)
            elif b: start = max(0, size - int(b))
            end = min(end, size - 1); status, partial = 206, (start, end)
        length = end - start + 1
        self._headers(full, length, status, partial, size)
        if head_only: return
        with open(full, "rb") as fh:
            fh.seek(start); remaining = length
            while remaining > 0:
                chunk = fh.read(min(1 << 20, remaining))
                if not chunk: break
                try: self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError): return
                remaining -= len(chunk)

class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True; allow_reuse_address = True

print(f"serving on http://127.0.0.1:{PORT}", flush=True)
Server(("127.0.0.1", PORT), Handler).serve_forever()
