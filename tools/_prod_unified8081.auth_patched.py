#!/usr/bin/env python3
"""
unified_server.py - v004 统一服务 (frontend + backend on 8081) + token 持久化

增强:
- 登录响应 (POST /api/v1/auth/login 或 POST /api/v2/action/user.authenticate) 捕获 token
- 按 client IP 存 in-memory token dict
- 后续请求没 Authorization, 自动用存的 token (前端 boService 401 修复)

需要先启 backend on BACKEND_PORT
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

PORT = 8081
# [L4 NSFOCUS 2026-07-14]
BIND = os.environ.get("UNIFIED_8081_BIND", "0.0.0.0")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", 3011))
BACKEND_URL = f"http://{os.environ.get('BACKEND_HOST', '127.0.0.1')}:{BACKEND_PORT}"
FRONTEND_DIR = sys.argv[1] if len(sys.argv) > 1 else "frontend_dist_files"
FRONTEND_DIR = os.path.abspath(FRONTEND_DIR)

print(f"[unified] frontend_dir={FRONTEND_DIR}", flush=True)
print(f"[unified] backend_url={BACKEND_URL}", flush=True)
print(f"[unified] listen=0.0.0.0:{PORT}", flush=True)


# ============================================================
# Token 持久化 (per client IP)
# ============================================================
# 解决 v4 前端 boService 调 BO endpoints 不传 Authorization header 的问题
# unified 拦截 login 响应, 把 token 存起来, 后续同 IP 请求自动用
TOKEN_CACHE = {}  # client_ip -> {token, exp, ts}
TOKEN_TTL = 86400  # 24h
_token_lock = threading.Lock()

# [FIX 2026-09-26 G1] 缓存落盘持久化: 此前 cache 仅在内存, unified 重启(含每次
#   部署)即清空 -> 前端不发 Authorization 头的请求全部 401 -> 全体在线用户被弹到
#   登录页。落盘后重启自动恢复, 会话跨重启/部署存活。
#   路径: <脚本目录上两级>/unified_token_cache.json (=/opt/app/deployments/,
#   不随 dist / meta 包部署被替换), 可用 UNIFIED_TOKEN_CACHE 覆盖。
TOKEN_CACHE_PATH = os.environ.get(
    "UNIFIED_TOKEN_CACHE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "unified_token_cache.json"),
)


def _load_token_cache():
    """启动时从磁盘恢复 token 缓存 (丢弃过期条目), 失败不影响启动。"""
    try:
        with open(TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        now = time.time()
        n = 0
        for ip, entry in (data or {}).items():
            if isinstance(entry, dict) and entry.get("token") \
                    and now - entry.get("ts", 0) < TOKEN_TTL:
                TOKEN_CACHE[ip] = {"token": entry["token"], "ts": entry["ts"]}
                n += 1
        print(f"[unified] token cache restored from {TOKEN_CACHE_PATH} ({n} entries)", flush=True)
    except FileNotFoundError:
        print(f"[unified] token cache file not found (first boot): {TOKEN_CACHE_PATH}", flush=True)
    except Exception as e:
        print(f"[unified] token cache load failed (ignored): {e}", flush=True)


def _persist_token_cache():
    """原子落盘 token 缓存 (仅登录时触发, 频率低); 失败只打日志。"""
    try:
        with _token_lock:
            snapshot = dict(TOKEN_CACHE)
        tmp = TOKEN_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f)
        os.replace(tmp, TOKEN_CACHE_PATH)
    except Exception as e:
        print(f"[unified] token cache persist failed (ignored): {e}", flush=True)


# Login 端点 (统一识别)
LOGIN_PATHS = (
    "/api/v1/auth/login",
    "/api/v2/action/user.authenticate",
)


def _save_token(client_ip: str, token: str):
    """保存 token 到 per-IP cache"""
    with _token_lock:
        TOKEN_CACHE[client_ip] = {
            "token": token,
            "ts": time.time(),
        }
    print(f"[unified] token saved for {client_ip} (cache size: {len(TOKEN_CACHE)})", flush=True)
    _persist_token_cache()


def _get_token(client_ip: str):
    """从 per-IP cache 取 token, 过期返回 None"""
    with _token_lock:
        entry = TOKEN_CACHE.get(client_ip)
        if not entry:
            return None
        if time.time() - entry["ts"] > TOKEN_TTL:
            del TOKEN_CACHE[client_ip]
            return None
        return entry["token"]


def _extract_token(body: bytes) -> str:
    """从 login 响应 body 提取 token"""
    try:
        data = json.loads(body)
        # v4 格式: {"data": {"token": "..."}, ...}
        # v3 格式: {"data": {"token": "..."}, ...}
        if isinstance(data, dict):
            inner = data.get("data", {})
            if isinstance(inner, dict):
                tok = inner.get("token")
                if tok:
                    return tok
            # 兜底
            tok = data.get("token")
            if tok:
                return tok
    except Exception:
        pass
    return ""


def _is_login_request(method: str, path: str) -> bool:
    """判断是否是登录请求"""
    if method not in ("POST", "GET"):
        return False
    # 去掉 query string
    from urllib.parse import urlparse
    path_only = urlparse(path).path
    return path_only in LOGIN_PATHS


class UnifiedHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[unified] {self.address_string()} - {fmt%args}", flush=True)

    def _proxy(self):
        url = f"{BACKEND_URL}{self.path}"
        body = None
        if self.command in ("POST", "PUT", "PATCH", "DELETE"):
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else None

        # 客户端 IP (考虑代理)
        client_ip = self.headers.get("X-Forwarded-For", self.client_address[0])
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()

        is_login = _is_login_request(self.command, self.path)

        try:
            req = urllib.request.Request(url, data=body, method=self.command)
            # 转发关键 header
            for k in ("Authorization", "Content-Type", "Cookie", "X-User-Id", "X-User-Name", "X-IP-Address"):
                v = self.headers.get(k)
                if v:
                    req.add_header(k, v)

            # 兜底: 如果客户端没传 Authorization, 用 cached token
            if not self.headers.get("Authorization") and "auth_token=" not in (self.headers.get("Cookie") or ""):
                cached = _get_token(client_ip)
                if cached:
                    req.add_header("Authorization", f"Bearer {cached}")
                    print(f"[unified] inject cached token for {client_ip} (path: {self.path})", flush=True)

            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_body = resp.read()

                # Login 响应: 捕获 token
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
        # 阻止 ../
        if ".." in rel_path:
            self.send_error(400)
            return
        full = os.path.join(FRONTEND_DIR, rel_path.lstrip("/"))
        if not os.path.isfile(full):
            # [FIX 2026-09-26] SPA fallback 只允许 HTML 导航请求 (无后缀 / .html)。
            #   静态资源 (.js/.css 等) 缺失时必须 404: 部署整目录替换 dist 后旧哈希
            #   chunk 消失, 旧页面点菜单会 import 旧 URL; 若把 index.html 当 200 返回,
            #   动态 import 拿到 HTML 解析失败且无失败信号, 造成"菜单 tab 空白"。
            #   404 让 router.onError (前端自愈) 能可靠识别并自动刷新。
            lower = rel_path.lower()
            if lower.endswith((
                    ".js", ".mjs", ".css", ".map", ".json", ".wasm",
                    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
                    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".txt", ".xml")):
                self.send_error(404)
                return
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
    _load_token_cache()
    with ThreadedServer((BIND, PORT), UnifiedHandler) as httpd:
        print(f"[unified] serving on {BIND}:{PORT} (L4 NSFOCUS compliant) (token cache enabled)", flush=True)
        httpd.serve_forever()
