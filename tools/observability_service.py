"""
[V007.61] observability_service.py v1.0 - 可观测性 + 扩展能力服务
  独立于 core_service, 重启不影响核心元能力 (upload/exec)
  监听: 9201
  依赖: Python 3.6+ 标准库, 无第三方依赖

  设计原则:
    1. 独立进程 - 重启不影响 core_service (9200)
    2. 只读观察 - metrics 从 core_service audit log 读取, 不干扰核心
    3. 代理扩展 - 批量上传等重型操作在这里处理
    4. 请求追踪 - 每个响应带 X-Request-Id

  端点:
    GET  /api                          服务信息
    GET  /api/health  /api/live        Liveness probe (公开, 无 token)
    GET  /api/ready                    Readiness probe (公开, 检查 core_service + 自身)
    GET  /api/metrics?token=XXX        Prometheus 监控指标 (read+ token)
    POST /api/upload_multi?base_dir=DIR&token=XXX  批量上传 multipart/form-data (write+)
"""

from __future__ import annotations
import os, sys, json, time, hashlib, threading, re
import http.server, socketserver
from urllib.parse import urlparse, parse_qs

# --- config ---
VERSION         = "v1.0"
PORT            = int(os.environ.get("OBS_SERVICE_PORT", 9201))
BIND            = os.environ.get("OBS_SERVICE_BIND", "0.0.0.0")
_START_TIME     = time.time()

# core_service 地址 (用于 ready probe)
CORE_URL        = os.environ.get("OBS_CORE_URL", "https://127.0.0.1:9200")
CORE_SSL_VERIFY = os.environ.get("OBS_CORE_SSL_VERIFY", "0") == "1"

# token secrets (与 core_service 共享)
SECRETS = {
    "admin": os.environ.get("CORE_SERVICE_ADMIN_SECRET", "v007.52-core-admin"),
    "write": os.environ.get("CORE_SERVICE_WRITE_SECRET", "v007.52-core-write"),
    "read":  os.environ.get("CORE_SERVICE_READ_SECRET",  "v007.52-core-read"),
}
_single_secret = os.environ.get("CORE_SERVICE_SECRET")
if _single_secret:
    SECRETS["admin"] = _single_secret

TOKEN_HR = 8
MAX_UPLOAD_MB = 500
AUDIT_LOG = os.environ.get("CORE_SERVICE_AUDIT_LOG", "/var/log/core_service_audit.log")
AUDIT_BACKUP_KEEP = int(os.environ.get("CORE_SERVICE_AUDIT_BACKUPS", 3))

ALLOWED_DIRS = [
    "/opt/app/deployments",
    "/opt/app/shared",
    "/opt/app/backups",
    "/tmp",
    "/var/log",
]

# --- token (shared logic with core_service) ---
def _gen_tokens() -> dict:
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

# --- metrics collector (reads core_service audit log) ---
def _collect_metrics():
    """从 core_service audit log 读取并计算 Prometheus 指标"""
    c = {
        "upload_ok": 0, "upload_denied": 0, "upload_fail": 0,
        "exec_ok": 0, "exec_denied": 0, "exec_fail": 0,
        "audit_rotate_ok": 0, "audit_rotate_denied": 0,
        "upload_multi_ok": 0, "upload_multi_denied": 0,
        "total_entries": 0,
        "by_action": {},
    }
    all_files = [AUDIT_LOG]
    for i in range(1, AUDIT_BACKUP_KEEP + 1):
        p = f"{AUDIT_LOG}.{i}"
        if os.path.exists(p):
            all_files.append(p)
    for fpath in sorted(all_files, key=lambda x: (x.count("."), x)):
        try:
            with open(fpath, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        action = entry.get("action", "")
                        c["total_entries"] += 1
                        c["by_action"][action] = c["by_action"].get(action, 0) + 1
                        # 分类计数
                        if action == "upload_ok":
                            c["upload_ok"] += 1
                        elif action == "upload_denied":
                            c["upload_denied"] += 1
                        elif action == "upload_fail":
                            c["upload_fail"] += 1
                        elif action == "exec_ok":
                            c["exec_ok"] += 1
                        elif action == "exec_denied":
                            c["exec_denied"] += 1
                        elif action == "exec_fail":
                            c["exec_fail"] += 1
                        elif action == "audit_rotate_ok":
                            c["audit_rotate_ok"] += 1
                        elif action == "audit_rotate_denied":
                            c["audit_rotate_denied"] += 1
                        elif action == "upload_multi_ok":
                            c["upload_multi_ok"] += 1
                        elif action == "upload_multi_denied":
                            c["upload_multi_denied"] += 1
                    except Exception:
                        continue
        except OSError:
            continue
    # audit log size
    log_size = 0
    if os.path.exists(AUDIT_LOG):
        try:
            log_size = os.path.getsize(AUDIT_LOG)
        except OSError:
            pass
    c["audit_log_bytes"] = log_size
    return c

# --- handler ---
class ObsHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a, **kw):
        pass

    def _assign_request_id(self):
        """给每个请求分配唯一 request_id"""
        import secrets as _sec
        client_id = self.headers.get("X-Request-Id", "").strip()
        if client_id and len(client_id) <= 64 and all(c.isalnum() or c in "-_" for c in client_id):
            self.request_id = client_id
        else:
            ts = int(time.time() * 1000)
            rnd = _sec.token_hex(3)
            self.request_id = f"obs-{ts}-{rnd}"

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        rid = getattr(self, "request_id", None)
        if rid:
            self.send_header("X-Request-Id", rid)
        self.end_headers()
        self.wfile.write(body)

    def _text(self, code, body_str, content_type="text/plain; charset=utf-8"):
        body = body_str.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        rid = getattr(self, "request_id", None)
        if rid:
            self.send_header("X-Request-Id", rid)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._assign_request_id()
        p = urlparse(self.path)
        q = parse_qs(p.query)
        route = p.path.rstrip("/")
        try:
            if route in ("", "/", "/api"):
                return self._root()
            elif route == "/api/health" or route == "/api/live":
                return self._health()
            elif route == "/api/ready":
                return self._ready()
            elif route == "/api/metrics":
                return self._metrics(q)
            return self._json(404, {"error": "not found", "route": route})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def do_POST(self):
        self._assign_request_id()
        p = urlparse(self.path)
        q = parse_qs(p.query)
        route = p.path.rstrip("/")
        try:
            if route == "/api/upload_multi":
                return self._upload_multi(q)
            return self._json(404, {"error": "POST not found", "route": route})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def _root(self):
        return self._json(200, {
            "service": "observability_service",
            "version": VERSION,
            "uptime_sec": int(time.time() - _START_TIME),
            "port": PORT,
            "endpoints": ["/api", "/api/health", "/api/ready", "/api/metrics", "/api/upload_multi"],
            "core_service_url": CORE_URL,
            "description": "observability + extended capabilities, restart-safe (decoupled from core_service:9200)",
        })

    # ── GET /api/health ────────────────────────────────
    def _health(self):
        """Liveness probe - 永远 200, 不限流, 公开"""
        return self._json(200, {
            "status": "alive",
            "service": "observability",
            "version": VERSION,
            "uptime_sec": int(time.time() - _START_TIME),
        })

    # ── GET /api/ready ────────────────────────────────
    def _ready(self):
        """Readiness probe - 检查 core_service 是否可连通"""
        checks = {}
        all_ok = True

        # 检查 core_service 连通性
        try:
            import urllib.request as _ur
            import ssl as _ssl
            ctx = _ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            req = _ur.Request(f"{CORE_URL}/api", method="GET")
            with _ur.urlopen(req, timeout=5, context=ctx) as r:
                data = json.loads(r.read().decode())
                checks["core_service"] = {
                    "reachable": True,
                    "version": data.get("version", "unknown"),
                    "status_code": r.status,
                }
        except Exception as e:
            checks["core_service"] = {"reachable": False, "error": str(e)}
            all_ok = False

        # 检查 audit log 可读
        try:
            if os.path.exists(AUDIT_LOG):
                with open(AUDIT_LOG, "r") as f:
                    f.read(100)
                checks["audit_log_readable"] = True
            else:
                checks["audit_log_readable"] = "no_file_yet"
        except Exception as e:
            checks["audit_log_readable"] = False
            checks["audit_log_error"] = str(e)
            all_ok = False

        status_code = 200 if all_ok else 503
        status_str = "ready" if all_ok else "not_ready"
        return self._json(status_code, {
            "status": status_str,
            "version": VERSION,
            "uptime_sec": int(time.time() - _START_TIME),
            "checks": checks,
        })

    # ── GET /api/metrics ──────────────────────────────
    def _metrics(self, q):
        """Prometheus 格式指标 (从 core_service audit log 读取)
        需要 read+ token
        """
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})
        c = _collect_metrics()
        lines = []
        lines.append("# HELP observability_uptime_seconds Service uptime in seconds")
        lines.append("# TYPE observability_uptime_seconds gauge")
        lines.append(f"observability_uptime_seconds {int(time.time() - _START_TIME)}")
        # core_service 审计指标
        lines.append("# HELP core_service_audit_events_total Total audit events by action (from audit log)")
        lines.append("# TYPE core_service_audit_events_total counter")
        for action, cnt in sorted(c.get("by_action", {}).items()):
            safe = action.replace('"', '\\"')
            lines.append(f'core_service_audit_events_total{{action="{safe}"}} {cnt}')
        # 分类
        lines.append("# HELP core_service_upload_total Total upload actions")
        lines.append("# TYPE core_service_upload_total counter")
        lines.append(f'core_service_upload_total{{result="ok"}} {c.get("upload_ok", 0)}')
        lines.append(f'core_service_upload_total{{result="denied"}} {c.get("upload_denied", 0)}')
        lines.append(f'core_service_upload_total{{result="fail"}} {c.get("upload_fail", 0)}')
        lines.append("# HELP core_service_exec_total Total exec actions")
        lines.append("# TYPE core_service_exec_total counter")
        lines.append(f'core_service_exec_total{{result="ok"}} {c.get("exec_ok", 0)}')
        lines.append(f'core_service_exec_total{{result="denied"}} {c.get("exec_denied", 0)}')
        lines.append(f'core_service_exec_total{{result="fail"}} {c.get("exec_fail", 0)}')
        # audit log size
        lines.append("# HELP core_service_audit_log_bytes Current audit log file size")
        lines.append("# TYPE core_service_audit_log_bytes gauge")
        lines.append(f"core_service_audit_log_bytes {c.get('audit_log_bytes', 0)}")
        # info
        lines.append("# HELP observability_info Service info")
        lines.append("# TYPE observability_info gauge")
        lines.append(f'observability_info{{version="{VERSION}",python="{sys.version.split()[0]}"}} 1')
        # output
        body = ("\n".join(lines) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        rid = getattr(self, "request_id", None)
        if rid:
            self.send_header("X-Request-Id", rid)
        self.end_headers()
        self.wfile.write(body)

    # ── POST /api/upload_multi ─────────────────────────
    def _upload_multi(self, q):
        """multipart/form-data 批量上传 (write+ token)"""
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})
        if level not in ("write", "admin"):
            return self._json(403, {"error": f"insufficient permission: have '{level}', need 'write' or 'admin'"})

        base_dir = q.get("base_dir", ["/tmp"])[0]
        if not _path_allowed(base_dir):
            return self._json(403, {"error": f"base_dir not allowed: {base_dir}"})

        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            return self._json(400, {"error": "Content-Type must be multipart/form-data", "got": ctype[:100]})

        m = re.search(r'boundary=(?:"([^"]+)"|([^\s;]+))', ctype)
        if not m:
            return self._json(400, {"error": "missing boundary in Content-Type"})
        boundary = m.group(1) or m.group(2)
        boundary_bytes = b"--" + boundary.encode("latin-1")

        clen = int(self.headers.get("Content-Length", 0))
        if clen > MAX_UPLOAD_MB * 1024 * 1024:
            return self._json(413, {"error": f"too large: {clen} bytes"})
        try:
            body = self.rfile.read(clen)
        except Exception as e:
            return self._json(500, {"error": f"read failed: {e}"})

        try:
            parts = self._parse_multipart(body, boundary_bytes)
        except Exception as e:
            return self._json(400, {"error": f"multipart parse failed: {e}"})

        if not parts:
            return self._json(400, {"error": "no parts in multipart body"})

        results = []
        ok_count = 0
        fail_count = 0
        for part in parts:
            filename = part["filename"]
            data = part["data"]
            if "/" in filename or "\\" in filename or ".." in filename or filename.startswith("."):
                results.append({"filename": filename, "ok": False, "error": "invalid filename"})
                fail_count += 1
                continue
            target = os.path.join(base_dir, filename)
            if not _path_allowed(target):
                results.append({"filename": filename, "ok": False, "error": f"path not allowed"})
                fail_count += 1
                continue
            try:
                os.makedirs(os.path.dirname(target) or "/tmp", exist_ok=True)
                with open(target, "wb") as f:
                    f.write(data)
                exe = target.endswith((".sh", ".py"))
                if exe:
                    os.chmod(target, 0o755)
                results.append({"filename": filename, "ok": True, "size": len(data), "path": target, "executable": exe})
                ok_count += 1
            except Exception as e:
                results.append({"filename": filename, "ok": False, "error": str(e)})
                fail_count += 1

        return self._json(200, {
            "action": "uploaded_multi",
            "base_dir": base_dir,
            "total": len(parts),
            "ok": ok_count,
            "fail": fail_count,
            "results": results,
        })

    @staticmethod
    def _parse_multipart(body, boundary_bytes):
        parts = []
        if not body.startswith(boundary_bytes):
            raise ValueError("body does not start with boundary")
        segments = body.split(boundary_bytes)
        for seg in segments:
            if not seg or seg == b"--\r\n" or seg == b"--":
                continue
            if seg.startswith(b"\r\n"):
                seg = seg[2:]
            if seg.endswith(b"\r\n"):
                seg = seg[:-2]
            if not seg:
                continue
            sep = b"\r\n\r\n"
            idx = seg.find(sep)
            if idx < 0:
                continue
            header_text = seg[:idx].decode("latin-1", errors="replace")
            data = seg[idx + 4:]
            filename = None
            for line in header_text.split("\r\n"):
                if line.lower().startswith("content-disposition:"):
                    m = re.search(r'filename\*?=(?:"([^"]+)"|([^;\s]+))', line)
                    if m:
                        filename = m.group(1) or m.group(2)
                        break
            if not filename:
                continue
            parts.append({"filename": filename, "data": data})
        return parts


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    print(f"[observability {VERSION}] port={PORT}", flush=True)
    print(f"  core_service: {CORE_URL}", flush=True)
    print(f"  audit_log: {AUDIT_LOG}", flush=True)
    server = _Server((BIND, PORT), ObsHandler)
    print(f"[observability] listening on {BIND}:{PORT} (HTTP)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
