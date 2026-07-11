"""
[V007.53] core_service.py - 极简元能力服务
  只做两件事: 上传文件 + 执行命令
  监听: 9200
  依赖: Python 3.6+ 标准库, 无第三方依赖

  设计原则:
    1. 极简 (~150 行) - 越少代码越少 bug
    2. 不做服务管理 - 避免 pkill/Popen 误杀自身
    3. 调用方决定生命周期 - 通过 exec pkill 停服务, exec bash start.sh 启服务

  端点:
    GET  /api                      服务信息
    POST /api/upload?path=PATH     上传文件 (500MB)
    GET  /api/exec?cmd=CMD         执行命令 (白名单, bg=true 后台)
"""

from __future__ import annotations
import os, sys, json, time, hashlib, threading, subprocess
import http.server, socketserver
from urllib.parse import urlparse, parse_qs

# --- config ---
VERSION         = "v1.1"
PORT            = int(os.environ.get("CORE_SERVICE_PORT", 9200))
BIND            = os.environ.get("CORE_SERVICE_BIND", "0.0.0.0")
SECRET          = os.environ.get("CORE_SERVICE_SECRET", "v007.52-core")
TOKEN_HR        = 8
MAX_UPLOAD_MB   = 500
_START_TIME     = time.time()

ALLOWED_DIRS = [
    "/opt/app/deployments",
    "/opt/app/shared",
    "/opt/app/backups",
    "/tmp",
    "/var/log",
]

EXEC_WHITELIST = [
    "ls", "cat", "head", "tail", "wc", "find", "grep", "du", "df",
    "ps", "top", "ss", "netstat", "curl", "wget",
    "systemctl", "journalctl", "dmesg", "iostat", "free",
    "echo", "date", "whoami", "id", "uname", "hostname",
    "chmod", "chown", "mkdir", "cp", "mv", "ln", "touch",
    "python3", "python", "pip3", "pip",
    "md5sum", "sha256sum",
    "pkill", "kill", "killall", "pgrep",
    "bash", "sh", "unzip", "tar", "nohup",
    "sed", "awk", "sort", "uniq",
    "test", "true", "false", "sleep",
]

EXEC_BLACKLIST = ["rm -rf /", "dd if=", "mkfs.", ":(){:|:&};:", "> /dev/sd",
                  "shutdown", "reboot", "init 0", "init 6"]

# --- token ---
def _gen_token() -> str:
    now = int(time.time())
    return ",".join(
        hashlib.sha256(f"{SECRET}:{(now - off * 3600) // 3600}".encode()).hexdigest()[:16]
        for off in range(TOKEN_HR + 1)
    )

def _check_token(params: dict) -> bool:
    t = params.get("token", [""])[0]
    return bool(t) and t in _gen_token().split(",")

# --- path ---
def _path_allowed(fp: str) -> bool:
    fp = os.path.realpath(fp)
    for d in ALLOWED_DIRS:
        rd = os.path.realpath(d) if os.path.exists(d) else d
        try:
            if os.path.commonpath([fp, rd]) == rd:
                return True
        except ValueError:
            continue
    return False

# --- rate limit ---
class _Limiter:
    def __init__(self, max_per_sec=20):
        self._lock = threading.Lock()
        self._max = max_per_sec
        self._buckets = {}
    def allow(self, ip):
        now = time.time()
        with self._lock:
            b = self._buckets.setdefault(ip, [])
            b[:] = [t for t in b if now - t < 1.0]
            if len(b) >= self._max:
                return False
            b.append(now)
            return True

_limiter = _Limiter()

# --- handler ---
class CoreHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a, **kw):
        pass

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not _limiter.allow(self.client_address[0]):
            return self._json(429, {"error": "rate limited"})
        try:
            p = urlparse(self.path)
            q = parse_qs(p.query)
            route = p.path.rstrip("/")
            if route in ("", "/", "/api"):
                return self._root(q)
            elif route == "/api/exec":
                return self._exec(q)
            return self._json(404, {"error": "not found", "route": route})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def do_POST(self):
        if not _limiter.allow(self.client_address[0]):
            return self._json(429, {"error": "rate limited"})
        try:
            p = urlparse(self.path)
            q = parse_qs(p.query)
            route = p.path.rstrip("/")
            if route == "/api/upload":
                return self._upload(q)
            return self._json(404, {"error": "POST not found", "route": route})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def _root(self, q):
        return self._json(200, {
            "service": "core_service",
            "version": VERSION,
            "uptime_sec": int(time.time() - _START_TIME),
            "port": PORT,
            "endpoints": ["/api", "/api/upload", "/api/exec"],
            "allowed_dirs": ALLOWED_DIRS,
            "exec_whitelist_count": len(EXEC_WHITELIST),
            "usage": {
                "upload": "POST /api/upload?path=/tmp/file.sh&token=XXX  (body=raw bytes)",
                "exec":   "GET  /api/exec?cmd=ls+/tmp&token=XXX  (bg=true for background)",
                "token":  "SHA256(secret:hour)[:16], valid 8h",
            },
        })

    def _upload(self, q):
        if not _check_token(q):
            return self._json(403, {"error": "token required"})
        target = q.get("path", [""])[0]
        if not target:
            return self._json(400, {"error": "path param required"})
        if not _path_allowed(target):
            return self._json(403, {"error": f"path not allowed: {target}"})
        clen = int(self.headers.get("Content-Length", 0))
        if clen > MAX_UPLOAD_MB * 1024 * 1024:
            return self._json(413, {"error": f"too large: {clen} bytes"})
        try:
            body = self.rfile.read(clen)
        except Exception as e:
            return self._json(500, {"error": f"read failed: {e}"})
        try:
            os.makedirs(os.path.dirname(target) or "/tmp", exist_ok=True)
            with open(target, "wb") as f:
                f.write(body)
            exe = target.endswith((".sh", ".py"))
            if exe:
                os.chmod(target, 0o755)
            return self._json(200, {"action": "uploaded", "path": target,
                                    "size": len(body), "executable": exe})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def _exec(self, q):
        if not _check_token(q):
            return self._json(403, {"error": "token required"})
        cmd = q.get("cmd", [""])[0]
        timeout = min(int(q.get("timeout", ["30"])[0]), 120)
        bg = q.get("bg", ["0"])[0] in ("1", "true", "yes")
        if not cmd:
            return self._json(400, {"error": "cmd param required"})
        for pat in EXEC_BLACKLIST:
            if pat in cmd.lower():
                return self._json(403, {"error": f"blacklisted: {pat}"})
        base = os.path.basename(cmd.split()[0]) if cmd.split() else ""
        if base not in EXEC_WHITELIST:
            return self._json(403, {"error": f"not whitelisted: {base}"})
        try:
            if bg:
                with open(os.devnull, "w") as devnull:
                    proc = subprocess.Popen(cmd, shell=True, stdout=devnull,
                                            stderr=devnull, close_fds=True,
                                            start_new_session=True)
                return self._json(200, {"mode": "background", "cmd": cmd, "pid": proc.pid})
            t0 = time.time()
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            out = r.stdout or ""
            err = r.stderr or ""
            return self._json(200, {
                "cmd": cmd, "exit_code": r.returncode,
                "stdout": out[:50000], "stderr": err[:10000],
                "elapsed_ms": round((time.time() - t0) * 1000, 1),
                "truncated_stdout": len(out) > 50000,
            })
        except subprocess.TimeoutExpired:
            return self._json(408, {"error": f"timeout after {timeout}s"})
        except Exception as e:
            return self._json(500, {"error": str(e)})


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def handle_error(self, request, client_address):
        import traceback
        with open("/var/log/core_service_crash.log", "a") as f:
            f.write(f"\n[{time.time()}] HANDLE_ERROR from {client_address}\n")
            f.write(traceback.format_exc())


def main():
    print(f"[core_service {VERSION}] port={PORT}", flush=True)
    print(f"  allowed_dirs: {ALLOWED_DIRS}", flush=True)
    print(f"  exec_whitelist: {len(EXEC_WHITELIST)} commands", flush=True)
    server = _Server((BIND, PORT), CoreHandler)
    print(f"[core_service] listening on {BIND}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
