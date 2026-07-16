#!/usr/bin/env python3
"""
unified_server.py - staging 版本 [V007.49-D 2026-07-13]
端口 18081 (vs 生产 8081) + backend 13011 (vs 生产 3011)
+ frontend 从 /opt/app/staging/frontend_dist_files/ 服务

原 v004 unified_server + token 持久化 (per client IP)
"""
import os
import sys
import json
import time
import http.server
import socketserver
import urllib.request
import urllib.error
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

# [V007.49-D] staging 端口 (vs 生产 8081)
PORT = 18081
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", 13011))
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
# [V007.49-D] staging frontend 目录 (vs 生产 /opt/app/deployments/frontend_dist_files)
DEFAULT_FRONTEND_DIR = "/opt/app/staging/frontend_dist_files"
FRONTEND_DIR = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FRONTEND_DIR
FRONTEND_DIR = os.path.abspath(FRONTEND_DIR)

print(f"[unified-staging] frontend_dir={FRONTEND_DIR}", flush=True)
print(f"[unified-staging] backend_url={BACKEND_URL}", flush=True)
print(f"[unified-staging] listen=0.0.0.0:{PORT}", flush=True)


# Token 持久化 (per client IP)
TOKEN_CACHE = {}
TOKEN_TTL = 86400
_token_lock = threading.Lock()

LOGIN_PATHS = (
    "/api/v1/auth/login",
    "/api/v2/action/user.authenticate",
)


def _save_token(client_ip: str, token: str):
    with _token_lock:
        TOKEN_CACHE[client_ip] = {
            "token": token,
            "ts": time.time(),
        }
    print(f"[unified-staging] token saved for {client_ip} (cache size: {len(TOKEN_CACHE)})", flush=True)


def _get_token(client_ip: str):
    with _token_lock:
        entry = TOKEN_CACHE.get(client_ip)
        if not entry:
            return None
        if time.time() - entry["ts"] > TOKEN_TTL:
            del TOKEN_CACHE[client_ip]
            return None
        return entry["token"]


def _extract_token(body: bytes) -> str:
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            inner = data.get("data", {})
            if isinstance(inner, dict):
                tok = inner.get("token")
                if tok:
                    return tok
            tok = data.get("token")
            if tok:
                return tok
    except Exception:
        pass
    return ""


def _is_login_request(method: str, path: str) -> bool:
    if method != "POST":
        return False
    path_only = urlparse(path).path
    return path_only in LOGIN_PATHS


class UnifiedHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[unified-staging] {self.address_string()} - {fmt%args}", flush=True)

    def _proxy(self):
        url = f"{BACKEND_URL}{self.path}"
        body = None
        if self.command in ("POST", "PUT", "PATCH", "DELETE"):
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else None

        client_ip = self.headers.get("X-Forwarded-For", self.client_address[0])
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()

        is_login = _is_login_request(self.command, self.path)

        try:
            req = urllib.request.Request(url, data=body, method=self.command)
            for k in ("Authorization", "Content-Type", "X-User-Id", "X-User-Name", "X-IP-Address"):
                v = self.headers.get(k)
                if v:
                    req.add_header(k, v)

            if not self.headers.get("Authorization"):
                cached = _get_token(client_ip)
                if cached:
                    req.add_header("Authorization", f"Bearer {cached}")
                    print(f"[unified-staging] inject cached token for {client_ip} (path: {self.path})", flush=True)

            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_body = resp.read()
                if is_login and resp.status == 200:
                    token = _extract_token(resp_body)
                    if token:
                        _save_token(client_ip, token)
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in ("content-type", "content-length", "access-control-allow-origin",
                                     "access-control-allow-credentials", "set-cookie"):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.send_response(e.code)
            ct = e.headers.get("Content-Type", "application/json")
            self.send_header("Content-Type", ct)
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            err = json.dumps({"error": "proxy_error", "message": str(e), "success": False}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _serve_static(self, rel_path):
        if ".." in rel_path:
            self.send_error(400)
            return
        full = os.path.join(FRONTEND_DIR, rel_path.lstrip("/"))
        if not os.path.isfile(full):
            full = os.path.join(FRONTEND_DIR, "index.html")
        if not os.path.isfile(full):
            self.send_error(404)
            return
        try:
            with open(full, "rb") as f:
                data = f.read()
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


def main():
    server = ThreadedServer(("0.0.0.0", PORT), UnifiedHandler)
    print(f"[unified-staging] serving on 0.0.0.0:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()