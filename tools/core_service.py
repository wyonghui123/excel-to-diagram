"""
[V007.53] core_service.py - 极简元能力服务
  只做两件事: 上传文件 + 执行命令
  监听: 9200
  依赖: Python 3.6+ 标准库, 无第三方依赖

  设计原则:
    1. 极简 (~150 行) - 越少代码越少 bug
    2. 不做服务管理 - 避免 pkill/Popen 误杀自身
    3. 调用方决定生命周期 - 通过 exec pkill 停服务, exec bash start.sh 启服务
    4. [v1.2] 审计日志 - 所有 upload/exec 记录到 /var/log/core_service_audit.log

  端点:
    GET  /api                      服务信息
    POST /api/upload?path=PATH     上传文件 (500MB)
    GET  /api/exec?cmd=CMD         执行命令 (白名单, bg=true 后台)
    GET  /api/audit?lines=N        查看最近审计日志 (token, 默认 50)
"""

from __future__ import annotations
import os, sys, json, time, hashlib, threading, subprocess
import http.server, socketserver
from urllib.parse import urlparse, parse_qs

# --- config ---
VERSION         = "v1.3"
PORT            = int(os.environ.get("CORE_SERVICE_PORT", 9200))
BIND            = os.environ.get("CORE_SERVICE_BIND", "0.0.0.0")
TOKEN_HR        = 8
MAX_UPLOAD_MB   = 500
_START_TIME     = time.time()

# [V007.54 v1.3] 三级 token 权限:
#   admin: 全权限 (upload + exec + audit read)
#   write: 可写 (upload + exec)
#   read:  只读 (audit + 允许的只读 exec: ls/cat/grep/ps 等)
SECRETS = {
    "admin": os.environ.get("CORE_SERVICE_ADMIN_SECRET", "v007.52-core-admin"),
    "write": os.environ.get("CORE_SERVICE_WRITE_SECRET", "v007.52-core-write"),
    "read":  os.environ.get("CORE_SERVICE_READ_SECRET",  "v007.52-core-read"),
}
# 向后兼容: 如果设置了单一 SECRET, 当作 admin
_single_secret = os.environ.get("CORE_SERVICE_SECRET")
if _single_secret:
    SECRETS["admin"] = _single_secret

# [V007.54 v1.3] read 权限允许的命令 (子集)
EXEC_WHITELIST_READONLY = {
    "ls", "cat", "head", "tail", "wc", "find", "grep", "du", "df",
    "ps", "top", "ss", "netstat", "curl", "wget",
    "echo", "date", "whoami", "id", "uname", "hostname",
    "md5sum", "sha256sum", "pgrep",
    "test", "true", "false",
}

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
def _gen_tokens() -> dict:
    """为每个权限等级生成当前小时的 token 列表 (含历史 8 小时漂移)"""
    now = int(time.time())
    out = {}
    for level, secret in SECRETS.items():
        tokens = set()
        for off in range(TOKEN_HR + 1):
            h = (now - off * 3600) // 3600
            tokens.add(hashlib.sha256(f"{secret}:{h}".encode()).hexdigest()[:16])
        out[level] = tokens
    return out

def _check_token(params: dict) -> str:
    """返回 token 的权限等级, 无效返回 '' """
    t = params.get("token", [""])[0]
    if not t:
        return ""
    tokens = _gen_tokens()
    for level in ("admin", "write", "read"):
        if t in tokens[level]:
            return level
    return ""

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
    # [V007.53] audit log - 记录所有敏感操作到 /var/log/core_service_audit.log
    AUDIT_LOG = "/var/log/core_service_audit.log"
    AUDIT_LOCK = threading.Lock()

    @classmethod
    def _audit(cls, action, client_ip, detail):
        """线程安全审计日志 - 写入 /var/log/core_service_audit.log"""
        try:
            import datetime as _dt
            ts = _dt.datetime.now().isoformat(timespec='seconds')
            line = json.dumps({"ts": ts, "ip": client_ip, "action": action, **detail},
                              ensure_ascii=False)
            with cls.AUDIT_LOCK:
                with open(cls.AUDIT_LOG, "a") as f:
                    f.write(line + "\n")
        except Exception:
            pass  # audit 失败不影响主流程

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
            elif route == "/api/audit":
                return self._audit_log(q)
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
            "endpoints": ["/api", "/api/upload", "/api/exec", "/api/audit"],
            "allowed_dirs": ALLOWED_DIRS,
            "exec_whitelist_count": len(EXEC_WHITELIST),
            "exec_readonly_count": len(EXEC_WHITELIST_READONLY),
            "audit_log": self.AUDIT_LOG,
            "token_levels": {
                "admin": {"permission": "full", "endpoints": "all",
                          "exec_whitelist_count": len(EXEC_WHITELIST),
                          "secret_env": "CORE_SERVICE_ADMIN_SECRET"},
                "write": {"permission": "write+exec", "endpoints": "upload+exec+audit",
                          "exec_whitelist_count": len(EXEC_WHITELIST),
                          "secret_env": "CORE_SERVICE_WRITE_SECRET"},
                "read":  {"permission": "readonly", "endpoints": "exec(readonly)+audit",
                          "exec_whitelist_count": len(EXEC_WHITELIST_READONLY),
                          "secret_env": "CORE_SERVICE_READ_SECRET",
                          "no_background": True},
            },
            "usage": {
                "upload": "POST /api/upload?path=/tmp/file.sh&token=XXX  (need write+admin)",
                "exec":   "GET  /api/exec?cmd=ls+/tmp&token=XXX  (bg=true need write+admin)",
                "audit":  "GET  /api/audit?lines=50&token=XXX  (need read+)",
                "token":  "SHA256(secret:hour)[:16], valid 8h. 3 levels: admin/write/read",
            },
        })

    # ── GET /api/audit ─────────────────────────────────────
    def _audit_log(self, q):
        """[V007.53 v1.2] 返回最近 N 条审计日志 (默认 50, max 500)
        [V007.54 v1.3] 需要 read+ 权限"""
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})
        try:
            n = min(int(q.get("lines", ["50"])[0]), 500)
        except ValueError:
            n = 50
        if not os.path.exists(self.AUDIT_LOG):
            return self._json(200, {"file": self.AUDIT_LOG, "count": 0, "entries": []})
        try:
            with open(self.AUDIT_LOG, "r") as f:
                lines = f.readlines()[-n:]
            entries = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    entries.append({"raw": line})  # 容错
            return self._json(200, {
                "file": self.AUDIT_LOG,
                "count": len(entries),
                "entries": entries,
            })
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def _upload(self, q):
        """[V007.54 v1.3] 需要 write+ 权限 (admin 也可)"""
        level = _check_token(q)
        if not level:
            self._audit("upload_denied", self.client_address[0], {"reason": "no_token"})
            return self._json(403, {"error": "token required"})
        if level not in ("write", "admin"):
            self._audit("upload_denied", self.client_address[0],
                        {"reason": "insufficient_permission", "level": level, "required": "write"})
            return self._json(403, {"error": f"insufficient permission: have '{level}', need 'write' or 'admin'"})
        target = q.get("path", [""])[0]
        if not target:
            return self._json(400, {"error": "path param required"})
        if not _path_allowed(target):
            self._audit("upload_denied", self.client_address[0], {"reason": "path_not_allowed", "path": target})
            return self._json(403, {"error": f"path not allowed: {target}"})
        clen = int(self.headers.get("Content-Length", 0))
        if clen > MAX_UPLOAD_MB * 1024 * 1024:
            self._audit("upload_denied", self.client_address[0], {"reason": "too_large", "size": clen})
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
            self._audit("upload_ok", self.client_address[0],
                        {"level": level, "path": target, "size": len(body), "executable": exe})
            return self._json(200, {"action": "uploaded", "path": target,
                                    "size": len(body), "executable": exe})
        except Exception as e:
            self._audit("upload_fail", self.client_address[0], {"path": target, "err": str(e)})
            return self._json(500, {"error": str(e)})

    def _exec(self, q):
        """[V007.54 v1.3] read 只能用只读子集, write/admin 可用全白名单"""
        level = _check_token(q)
        if not level:
            self._audit("exec_denied", self.client_address[0], {"reason": "no_token"})
            return self._json(403, {"error": "token required"})
        cmd = q.get("cmd", [""])[0]
        timeout = min(int(q.get("timeout", ["30"])[0]), 120)
        bg = q.get("bg", ["0"])[0] in ("1", "true", "yes")
        if not cmd:
            return self._json(400, {"error": "cmd param required"})
        for pat in EXEC_BLACKLIST:
            if pat in cmd.lower():
                self._audit("exec_denied", self.client_address[0], {"reason": "blacklist", "pattern": pat, "cmd": cmd[:200]})
                return self._json(403, {"error": f"blacklisted: {pat}"})
        base = os.path.basename(cmd.split()[0]) if cmd.split() else ""
        # [V007.54 v1.3] read 权限只能用只读子集
        if level == "read":
            if base not in EXEC_WHITELIST_READONLY:
                self._audit("exec_denied", self.client_address[0],
                            {"reason": "readonly_violation", "level": level, "base": base, "cmd": cmd[:200]})
                return self._json(403, {
                    "error": f"readonly token cannot exec '{base}'",
                    "readonly_allowed": sorted(EXEC_WHITELIST_READONLY),
                    "hint": "use write/admin token for full whitelist",
                })
            if bg:
                self._audit("exec_denied", self.client_address[0],
                            {"reason": "readonly_cannot_bg", "cmd": cmd[:200]})
                return self._json(403, {"error": "readonly token cannot exec in background"})
        else:
            # write/admin
            if base not in EXEC_WHITELIST:
                self._audit("exec_denied", self.client_address[0], {"reason": "not_whitelisted", "base": base, "cmd": cmd[:200]})
                return self._json(403, {"error": f"not whitelisted: {base}"})
        try:
            if bg:
                with open(os.devnull, "w") as devnull:
                    proc = subprocess.Popen(cmd, shell=True, stdout=devnull,
                                            stderr=devnull, close_fds=True,
                                            start_new_session=True)
                self._audit("exec_ok", self.client_address[0], {"mode": "bg", "cmd": cmd[:200], "pid": proc.pid})
                return self._json(200, {"mode": "background", "cmd": cmd, "pid": proc.pid})
            t0 = time.time()
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            out = r.stdout or ""
            err = r.stderr or ""
            elapsed = round((time.time() - t0) * 1000, 1)
            self._audit("exec_ok", self.client_address[0], {"mode": "sync", "cmd": cmd[:200], "exit_code": r.returncode, "elapsed_ms": elapsed})
            return self._json(200, {
                "cmd": cmd, "exit_code": r.returncode,
                "stdout": out[:50000], "stderr": err[:10000],
                "elapsed_ms": elapsed,
                "truncated_stdout": len(out) > 50000,
            })
        except subprocess.TimeoutExpired:
            self._audit("exec_fail", self.client_address[0], {"reason": "timeout", "cmd": cmd[:200], "timeout": timeout})
            return self._json(408, {"error": f"timeout after {timeout}s"})
        except Exception as e:
            self._audit("exec_fail", self.client_address[0], {"cmd": cmd[:200], "err": str(e)})
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
