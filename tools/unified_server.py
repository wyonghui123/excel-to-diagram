#!/usr/bin/env python3
"""
unified_server.py - v004 统一服务 (frontend + backend on 8081)

- GET /              → serve frontend_dist_files/index.html
- GET /assets/*      → serve frontend_dist_files/assets/*
- /api/*             → reverse proxy to 127.0.0.1:5001 (v004 backend)
- /                  → fallback to index.html (SPA)

需要先启 v004 backend on 5001
"""
import os
import sys
import json
import http.server
import socketserver
import urllib.request
import urllib.error
import threading
import socketserver
from http.server import BaseHTTPRequestHandler

PORT = 8081
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", 5001))
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
FRONTEND_DIR = sys.argv[1] if len(sys.argv) > 1 else "frontend_dist_files"
FRONTEND_DIR = os.path.abspath(FRONTEND_DIR)

print(f"[unified] frontend_dir={FRONTEND_DIR}", flush=True)
print(f"[unified] backend_url={BACKEND_URL}", flush=True)
print(f"[unified] listen=0.0.0.0:{PORT}", flush=True)


class UnifiedHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[unified] {self.address_string()} - {fmt%args}", flush=True)

    def _proxy(self):
        url = f"{BACKEND_URL}{self.path}"
        body = None
        if self.command in ("POST", "PUT", "PATCH", "DELETE"):
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else None
        try:
            req = urllib.request.Request(url, data=body, method=self.command)
            # 转发关键 header
            for k in ("Authorization", "Content-Type", "X-User-Id", "X-User-Name", "X-IP-Address"):
                v = self.headers.get(k)
                if v:
                    req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=60) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in ("content-type", "content-length", "access-control-allow-origin",
                                     "access-control-allow-credentials", "set-cookie"):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            ct = e.headers.get("Content-Type", "application/json")
            self.send_header("Content-Type", ct)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            err = json.dumps({"error": "proxy_error", "message": str(e), "success": False}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _serve_static(self, rel_path):
        # 阻止 ../
        if ".." in rel_path:
            self.send_error(400)
            return
        full = os.path.join(FRONTEND_DIR, rel_path.lstrip("/"))
        if not os.path.isfile(full):
            # SPA fallback
            full = os.path.join(FRONTEND_DIR, "index.html")
        if not os.path.isfile(full):
            self.send_error(404)
            return
        try:
            with open(full, "rb") as f:
                data = f.read()
            # 猜 mime
            if full.endswith(".html"):
                ct = "text/html"
            elif full.endswith(".js"):
                ct = "application/javascript"
            elif full.endswith(".css"):
                ct = "text/css"
            elif full.endswith(".json"):
                ct = "application/json"
            elif full.endswith(".png"):
                ct = "image/png"
            elif full.endswith(".svg"):
                ct = "image/svg+xml"
            else:
                ct = "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, str(e))

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        # 静态
        rel = self.path.split("?")[0]
        if rel == "/" or rel == "":
            rel = "/index.html"
        return self._serve_static(rel)

    def do_POST(self): return self._proxy()
    def do_PUT(self): return self._proxy()
    def do_PATCH(self): return self._proxy()
    def do_DELETE(self): return self._proxy()
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-User-Id, X-User-Name, X-IP-Address")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    with ThreadedServer(("0.0.0.0", PORT), UnifiedHandler) as httpd:
        print(f"[unified] serving on 0.0.0.0:{PORT}", flush=True)
        httpd.serve_forever()
