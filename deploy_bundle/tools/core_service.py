"""
[V007.59] core_service.py - 极简元能力服务
  只做两件事: 上传文件 + 执行命令
  监听: 9200
  依赖: Python 3.6+ 标准库, 无第三方依赖

  设计原则:
    1. 极简 (~150 行) - 越少代码越少 bug
    2. 不做服务管理 - 避免 pkill/Popen 误杀自身
    3. 调用方决定生命周期 - 通过 exec pkill 停服务, exec bash start.sh 启服务
    4. [v1.2] 审计日志 - 所有 upload/exec 记录到 /var/log/core_service_audit.log
    5. [v1.3] 三级权限 - admin (full) / write (upload+exec) / read (exec readonly + audit)
    6. [v1.4] HTTPS 支持 - 当 CORE_SERVICE_SSL_CERTFILE 设置时自动启用 TLS 1.2+
    7. [v1.5] audit log 轮转 - 10MB 自动 rotate, 保留 3 个 backup
    8. [v1.6] 批量上传 (multipart/form-data) - /api/upload_multi, 不依赖第三方
    9. [v1.7] 监控指标 - /api/metrics (Prometheus 格式)
   10. [v1.8] 健康检查 - /api/health (liveness) + /api/ready (readiness), 无需 token

  端点:
    GET   /api                          服务信息
    POST  /api/upload?path=PATH         上传单文件 (500MB)
    POST  /api/upload_multi?base_dir=DIR 批量上传 (multipart/form-data)
    GET   /api/exec?cmd=CMD             执行命令 (白名单, bg=true 后台)
    GET   /api/audit?lines=N            查看最近审计日志 (token, 默认 50)
    POST  /api/audit/rotate             手动触发 audit 轮转 (admin only)
    GET   /api/metrics                  Prometheus 监控指标 (read+)
    GET   /api/health / /api/live       Liveness probe (公开, 无 token)
    GET   /api/ready                    Readiness probe (公开, 无 token)
"""

from __future__ import annotations
import os, sys, json, time, hashlib, threading, subprocess
import http.server, socketserver
from urllib.parse import urlparse, parse_qs

# --- config ---
VERSION         = "v1.8"
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
    # [V007.58 v1.7] 全局计数器 (类变量, 线程安全用 LOCK)
    _counter_lock = threading.Lock()
    _counters = {
        "requests_total": 0,
        "requests_2xx": 0,
        "requests_4xx": 0,
        "requests_5xx": 0,
        "upload_total": 0,
        "upload_bytes_total": 0,
        "exec_total": 0,
        "exec_bg_total": 0,
        "audit_total": 0,
        "rotate_total": 0,
        "rate_limited": 0,
        "by_route": {},   # 路由命中数
        "by_action": {},  # audit 事件数
    }

    @classmethod
    def _inc(cls, key, value=1, sub_key=None, sub_dict=None):
        """[V007.58 v1.7] 线程安全计数器"""
        with cls._counter_lock:
            if sub_dict and sub_key is not None:
                d = cls._counters.setdefault(sub_dict, {})
                d[sub_key] = d.get(sub_key, 0) + value
            else:
                cls._counters[key] = cls._counters.get(key, 0) + value
    # [V007.53] audit log - 记录所有敏感操作到 /var/log/core_service_audit.log
    AUDIT_LOG = os.environ.get("CORE_SERVICE_AUDIT_LOG", "/var/log/core_service_audit.log")
    AUDIT_LOCK = threading.Lock()
    # [V007.56 v1.5] audit log 轮转
    AUDIT_MAX_BYTES = int(os.environ.get("CORE_SERVICE_AUDIT_MAX_BYTES", 10 * 1024 * 1024))  # 10MB
    AUDIT_BACKUP_KEEP = int(os.environ.get("CORE_SERVICE_AUDIT_BACKUPS", 3))  # 保留 3 个 backup

    @classmethod
    def _audit(cls, action, client_ip, detail):
        """线程安全审计日志 + 自动轮转
        - 线程安全 (threading.Lock)
        - 写入失败不影响主流程
        - 文件超过 AUDIT_MAX_BYTES 自动 rotate: .log → .log.1 → .log.2 ...
        - 保留最近 AUDIT_BACKUP_KEEP 个 backup, 老的删除
        """
        # [V007.58 v1.7] 计数 audit 事件
        cls._inc("audit_total", sub_key=action, sub_dict="by_action")
        try:
            import datetime as _dt
            ts = _dt.datetime.now().isoformat(timespec='seconds')
            line = json.dumps({"ts": ts, "ip": client_ip, "action": action, **detail},
                              ensure_ascii=False)
            with cls.AUDIT_LOCK:
                # 轮转检查 (只在需要时检查, 避免每次都 stat)
                if os.path.exists(cls.AUDIT_LOG):
                    try:
                        size = os.path.getsize(cls.AUDIT_LOG)
                        if size >= cls.AUDIT_MAX_BYTES:
                            cls._rotate_audit()
                    except OSError:
                        pass
                with open(cls.AUDIT_LOG, "a") as f:
                    f.write(line + "\n")
        except Exception:
            pass  # audit 失败不影响主流程

    @classmethod
    def _rotate_audit(cls):
        """[V007.56 v1.5] 轮转 audit log
        算法:
          1. 删除最老的 backup (如果超过 keep 数)
          2. 把 .log.N 改名为 .log.(N+1)
          3. 把当前 .log 改名为 .log.1
          4. 下次写会创建新的 .log
        """
        try:
            # 1. 删除最老的
            oldest = f"{cls.AUDIT_LOG}.{cls.AUDIT_BACKUP_KEEP}"
            if os.path.exists(oldest):
                os.unlink(oldest)
            # 2-3. 逐个 rename
            for i in range(cls.AUDIT_BACKUP_KEEP - 1, 0, -1):
                src = f"{cls.AUDIT_LOG}.{i}"
                dst = f"{cls.AUDIT_LOG}.{i + 1}"
                if os.path.exists(src):
                    os.rename(src, dst)
            # 4. 当前 .log → .log.1
            if os.path.exists(cls.AUDIT_LOG):
                os.rename(cls.AUDIT_LOG, f"{cls.AUDIT_LOG}.1")
        except Exception as e:
            sys.stderr.write(f"[core_service] audit rotate failed: {e}\n")

    def log_message(self, *a, **kw):
        pass

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        # [V007.58 v1.7] 按 status 计数
        if 200 <= code < 300:
            self._inc("requests_2xx")
        elif 400 <= code < 500:
            self._inc("requests_4xx")
        elif 500 <= code < 600:
            self._inc("requests_5xx")

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)
        route = p.path.rstrip("/")
        # [V007.59 v1.8] health/ready 不走 rate limit (K8s 探活会频繁调用)
        if route not in ("/api/health", "/api/live", "/api/ready"):
            if not _limiter.allow(self.client_address[0]):
                self._inc("rate_limited")
                return self._json(429, {"error": "rate limited"})
        try:
            self._inc("requests_total", sub_key=route, sub_dict="by_route")
            # 路由级计数
            if route == "/api/exec":
                self._inc("exec_total")
                if q.get("bg", ["0"])[0] in ("1", "true", "yes"):
                    self._inc("exec_bg_total")
            elif route == "/api/audit":
                self._inc("audit_total")
            elif route == "/api/metrics":
                pass  # 自己计
            elif route in ("/api/health", "/api/live", "/api/ready"):
                pass  # 探活端点单独处理
            if route in ("", "/", "/api"):
                return self._root(q)
            elif route == "/api/metrics":
                return self._metrics(q)
            elif route == "/api/health" or route == "/api/live":
                return self._health(q)
            elif route == "/api/ready":
                return self._ready(q)
            elif route == "/api/exec":
                return self._exec(q)
            elif route == "/api/audit":
                return self._audit_log(q)
            elif route == "/api/audit/rotate":
                return self._audit_rotate_endpoint(q)
            return self._json(404, {"error": "not found", "route": route})
        except Exception as e:
            self._inc("requests_5xx")
            return self._json(500, {"error": str(e)})

    def do_POST(self):
        if not _limiter.allow(self.client_address[0]):
            self._inc("rate_limited")
            return self._json(429, {"error": "rate limited"})
        try:
            p = urlparse(self.path)
            q = parse_qs(p.query)
            route = p.path.rstrip("/")
            self._inc("requests_total", sub_key=route, sub_dict="by_route")
            if route == "/api/upload":
                self._inc("upload_total")
            if route == "/api/upload":
                return self._upload(q)
            elif route == "/api/upload_multi":
                return self._upload_multi(q)
            elif route == "/api/audit/rotate":
                return self._audit_rotate_endpoint(q)
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
            # [V007.56 v1.5] 合并当前 + 所有 backup (从最老到最新)
            all_files = [self.AUDIT_LOG]
            for i in range(1, self.AUDIT_BACKUP_KEEP + 1):
                p = f"{self.AUDIT_LOG}.{i}"
                if os.path.exists(p):
                    all_files.append(p)
            # 读取 (顺序: 最老 backup 先, 当前 log 最后, 保证最新在尾巴)
            all_lines = []
            for f in sorted(all_files, key=lambda x: (x.count("."), x)):
                try:
                    with open(f, "r") as fh:
                        all_lines.extend(fh.readlines())
                except OSError:
                    continue
            # 取最后 n 条
            recent = all_lines[-n:]
            entries = []
            for line in recent:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    entries.append({"raw": line})  # 容错
            return self._json(200, {
                "file": self.AUDIT_LOG,
                "backup_files": [f for f in all_files if f != self.AUDIT_LOG],
                "count": len(entries),
                "entries": entries,
            })
        except Exception as e:
            return self._json(500, {"error": str(e)})

    # ── POST /api/audit/rotate (admin only) ───────────────
    def _audit_rotate_endpoint(self, q):
        """[V007.56 v1.5] 手动触发 audit log 轮转
        需要 admin 权限, 用于测试和紧急情况
        """
        level = _check_token(q)
        if not level:
            self._audit("audit_rotate_denied", self.client_address[0], {"reason": "no_token"})
            return self._json(403, {"error": "token required"})
        if level != "admin":
            self._audit("audit_rotate_denied", self.client_address[0],
                        {"reason": "not_admin", "level": level})
            return self._json(403, {"error": f"admin required, have '{level}'"})
        # 执行轮转
        try:
            existed = os.path.exists(self.AUDIT_LOG)
            size_before = os.path.getsize(self.AUDIT_LOG) if existed else 0
            self._rotate_audit()
            self._inc("rotate_total")
            self._audit("audit_rotate_ok", self.client_address[0],
                        {"size_before": size_before})
            return self._json(200, {
                "rotated": True,
                "size_before": size_before,
                "backups_kept": self.AUDIT_BACKUP_KEEP,
            })
        except Exception as e:
            return self._json(500, {"error": str(e)})

    # ── GET /api/metrics (read+ token) ────────────────────
    def _metrics(self, q):
        """[V007.58 v1.7] 监控指标 (Prometheus 格式)
        包含:
        - core_service_uptime_seconds
        - core_service_requests_total (with status label)
        - core_service_upload_total / _bytes_total
        - core_service_exec_total (with mode label)
        - core_service_audit_total (with action label)
        - core_service_audit_log_bytes
        - core_service_requests_by_route
        - core_service_rate_limited_total
        """
        # read+ 权限 (read token 也可访问, 只读)
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})
        # 收集指标
        c = self._counters
        lines = []
        # HELP/TYPE
        lines.append("# HELP core_service_uptime_seconds Service uptime in seconds")
        lines.append("# TYPE core_service_uptime_seconds gauge")
        lines.append(f'core_service_uptime_seconds {int(time.time() - _START_TIME)}')
        # 通用请求计数
        lines.append("# HELP core_service_requests_total Total HTTP requests by status")
        lines.append("# TYPE core_service_requests_total counter")
        lines.append(f'core_service_requests_total{{status="2xx"}} {c.get("requests_2xx", 0)}')
        lines.append(f'core_service_requests_total{{status="4xx"}} {c.get("requests_4xx", 0)}')
        lines.append(f'core_service_requests_total{{status="5xx"}} {c.get("requests_5xx", 0)}')
        # 限流
        lines.append("# HELP core_service_rate_limited_total Total 429 rate-limit responses")
        lines.append("# TYPE core_service_rate_limited_total counter")
        lines.append(f'core_service_rate_limited_total {c.get("rate_limited", 0)}')
        # upload
        lines.append("# HELP core_service_upload_total Total single-file upload requests")
        lines.append("# TYPE core_service_upload_total counter")
        lines.append(f'core_service_upload_total {c.get("upload_total", 0)}')
        lines.append("# HELP core_service_upload_bytes_total Total bytes uploaded (single-file)")
        lines.append("# TYPE core_service_upload_bytes_total counter")
        lines.append(f'core_service_upload_bytes_total {c.get("upload_bytes_total", 0)}')
        # exec
        lines.append("# HELP core_service_exec_total Total exec calls by mode")
        lines.append("# TYPE core_service_exec_total counter")
        lines.append(f'core_service_exec_total{{mode="sync"}} {c.get("exec_total", 0)}')
        lines.append(f'core_service_exec_total{{mode="bg"}} {c.get("exec_bg_total", 0)}')
        # audit
        lines.append("# HELP core_service_audit_total Total audit events by action")
        lines.append("# TYPE core_service_audit_total counter")
        for action, cnt in sorted(c.get("by_action", {}).items()):
            # 安全的 label 值 (转义引号)
            safe_action = action.replace('"', '\\"')
            lines.append(f'core_service_audit_total{{action="{safe_action}"}} {cnt}')
        # audit log 大小
        log_size = 0
        if os.path.exists(self.AUDIT_LOG):
            try:
                log_size = os.path.getsize(self.AUDIT_LOG)
            except OSError:
                pass
        lines.append("# HELP core_service_audit_log_bytes Current audit log file size")
        lines.append("# TYPE core_service_audit_log_bytes gauge")
        lines.append(f'core_service_audit_log_bytes {log_size}')
        # 路由命中 (方便看哪个端点用得多)
        lines.append("# HELP core_service_requests_by_route Total requests by route")
        lines.append("# TYPE core_service_requests_by_route counter")
        for route, cnt in sorted(c.get("by_route", {}).items()):
            safe_route = route.replace('"', '\\"')
            lines.append(f'core_service_requests_by_route{{route="{safe_route}"}} {cnt}')
        # 进程信息
        lines.append("# HELP core_service_info Service version and build info")
        lines.append("# TYPE core_service_info gauge")
        lines.append(f'core_service_info{{version="{VERSION}",python="{sys.version.split()[0]}"}} 1')
        # 输出 (text/plain; version=0.0.4 是 Prometheus 期望的 MIME)
        body = ("\n".join(lines) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self._inc("metrics_total", sub_key="/api/metrics", sub_dict="by_route")

    # ── GET /api/health (公开, 无 token) ─────────────────
    def _health(self, q):
        """[V007.59 v1.8] Liveness probe - 进程是否存活
        永远返回 200, 只要进程能响应就说明活着
        用途: Kubernetes livenessProbe, 负载均衡健康检查
        特点:
        - 无需 token (公开端点)
        - 极轻量 (不查 audit log, 不计 metrics)
        - 响应时间 < 1ms
        """
        return self._json(200, {
            "status": "alive",
            "version": VERSION,
            "uptime_sec": int(time.time() - _START_TIME),
        })

    # ── GET /api/ready (公开, 无 token) ─────────────────
    def _ready(self, q):
        """[V007.59 v1.8] Readiness probe - 是否能处理请求
        检查:
        - audit log 目录是否可写
        - ALLOWED_DIRS 是否存在
        - 计数器是否被 lock 过 (简单 liveness)
        返回 200 = ready, 503 = not ready
        用途: Kubernetes readinessProbe, 负载均衡流量切换
        """
        checks = {}
        all_ok = True
        # 检查 audit log 目录
        audit_dir = os.path.dirname(self.AUDIT_LOG) or "/var/log"
        try:
            os.makedirs(audit_dir, exist_ok=True)
            test_file = os.path.join(audit_dir, ".ready_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.unlink(test_file)
            checks["audit_log_writable"] = True
        except Exception as e:
            checks["audit_log_writable"] = False
            checks["audit_log_error"] = str(e)
            all_ok = False
        # 检查 ALLOWED_DIRS 存在
        missing = [d for d in ALLOWED_DIRS if not os.path.exists(d)]
        checks["allowed_dirs_ok"] = not missing
        if missing:
            checks["missing_dirs"] = missing
            all_ok = False
        # 检查 audit log 大小 (不能超过 2x MAX, 否则可能要处理)
        log_size = 0
        if os.path.exists(self.AUDIT_LOG):
            try:
                log_size = os.path.getsize(self.AUDIT_LOG)
            except OSError:
                pass
        # audit log 超过 90MB (9x max) 算超载
        checks["audit_log_size_bytes"] = log_size
        if log_size > self.AUDIT_MAX_BYTES * 9:
            checks["audit_log_critical"] = True
            all_ok = False
        status_code = 200 if all_ok else 503
        status_str = "ready" if all_ok else "not_ready"
        return self._json(status_code, {
            "status": status_str,
            "version": VERSION,
            "uptime_sec": int(time.time() - _START_TIME),
            "checks": checks,
        })

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
            self._inc("upload_bytes_total", value=len(body))
            return self._json(200, {"action": "uploaded", "path": target,
                                    "size": len(body), "executable": exe})
        except Exception as e:
            self._audit("upload_fail", self.client_address[0], {"path": target, "err": str(e)})
            return self._json(500, {"error": str(e)})

    def _upload_multi(self, q):
        """[V007.57 v1.6] multipart/form-data 批量上传
        POST /api/upload_multi?base_dir=/tmp/batch&token=XXX
        Content-Type: multipart/form-data; boundary=BOUNDARY
        Body: 标准 multipart (每个 part 有 filename)

        特点:
        - 不依赖第三方 (手写 multipart parser)
        - 写权限 (write/admin)
        - 文件名前缀 base_dir 必须在 ALLOWED_DIRS 内
        - 返回每个文件的成功/失败状态

        支持两种调用方式:
        1. 客户端指定 base_dir (推荐, 路径白名单)
        2. 客户端用 X-Path header 单独指定 (更灵活, 但不安全)

        当前实现: 强制要求 base_dir 参数, 文件名从 multipart part 的 filename 取
        """
        level = _check_token(q)
        if not level:
            self._audit("upload_multi_denied", self.client_address[0], {"reason": "no_token"})
            return self._json(403, {"error": "token required"})
        if level not in ("write", "admin"):
            self._audit("upload_multi_denied", self.client_address[0],
                        {"reason": "insufficient_permission", "level": level, "required": "write"})
            return self._json(403, {"error": f"insufficient permission: have '{level}', need 'write' or 'admin'"})

        base_dir = q.get("base_dir", ["/tmp"])[0]
        if not _path_allowed(base_dir):
            self._audit("upload_multi_denied", self.client_address[0],
                        {"reason": "base_dir_not_allowed", "base_dir": base_dir})
            return self._json(403, {"error": f"base_dir not allowed: {base_dir}"})

        # Content-Type 必须含 multipart
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            return self._json(400, {"error": "Content-Type must be multipart/form-data",
                                    "got": ctype[:100]})

        # 提取 boundary
        import re
        m = re.search(r'boundary=(?:"([^"]+)"|([^\s;]+))', ctype)
        if not m:
            return self._json(400, {"error": "missing boundary in Content-Type"})
        boundary = m.group(1) or m.group(2)
        boundary_bytes = b"--" + boundary.encode("latin-1")

        # 读取 body (有 size 限制)
        clen = int(self.headers.get("Content-Length", 0))
        if clen > MAX_UPLOAD_MB * 1024 * 1024:
            self._audit("upload_multi_denied", self.client_address[0],
                        {"reason": "too_large", "size": clen})
            return self._json(413, {"error": f"too large: {clen} bytes"})
        try:
            body = self.rfile.read(clen)
        except Exception as e:
            return self._json(500, {"error": f"read failed: {e}"})

        # 解析 multipart
        try:
            parts = self._parse_multipart(body, boundary_bytes)
        except Exception as e:
            return self._json(400, {"error": f"multipart parse failed: {e}"})

        if not parts:
            return self._json(400, {"error": "no parts in multipart body"})

        # 写文件
        results = []
        ok_count = 0
        fail_count = 0
        for part in parts:
            filename = part["filename"]
            data = part["data"]
            # 拼接 target path
            # 安全检查: filename 不能含 .. 或 / (防止路径穿越)
            if "/" in filename or "\\" in filename or ".." in filename or filename.startswith("."):
                results.append({"filename": filename, "ok": False, "error": "invalid filename"})
                fail_count += 1
                continue
            target = os.path.join(base_dir, filename)
            if not _path_allowed(target):
                results.append({"filename": filename, "ok": False, "error": f"path not allowed: {target}"})
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

        # 审计 (只记总数, 不列每个文件)
        self._audit("upload_multi_ok", self.client_address[0], {
            "level": level,
            "base_dir": base_dir,
            "total": len(parts),
            "ok": ok_count,
            "fail": fail_count,
        })

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
        """[V007.57 v1.6] 手写 multipart/form-data 解析
        返回: [{"filename": str, "data": bytes}, ...]
        跳过没有 filename 的 part (form 字段)
        """
        parts = []
        # body 必须以 --BOUNDARY 开始
        if not body.startswith(boundary_bytes):
            raise ValueError("body does not start with boundary")
        # 分段
        # body.split(b"--BOUNDARY") -> 第一个元素是空, 后面是 \r\nHeaders\r\n\r\nData\r\n 或 \r\n--\r\n
        segments = body.split(boundary_bytes)
        for seg in segments:
            if not seg or seg == b"--\r\n" or seg == b"--":
                continue
            # 去掉前导 \r\n 和尾部 \r\n
            if seg.startswith(b"\r\n"):
                seg = seg[2:]
            if seg.endswith(b"\r\n"):
                seg = seg[:-2]
            if not seg:
                continue
            # 分 header 和 body
            sep = b"\r\n\r\n"
            idx = seg.find(sep)
            if idx < 0:
                continue
            header_text = seg[:idx].decode("latin-1", errors="replace")
            data = seg[idx + 4:]
            # 解析 Content-Disposition 找 filename
            filename = None
            for line in header_text.split("\r\n"):
                if line.lower().startswith("content-disposition:"):
                    # 找 filename="..."
                    import re as _re
                    m = _re.search(r'filename\*?=(?:"([^"]+)"|([^;\s]+))', line)
                    if m:
                        filename = m.group(1) or m.group(2)
                        break
            if not filename:
                continue  # 跳过 form 字段
            parts.append({"filename": filename, "data": data})
        return parts

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


# [V007.55 v1.4] HTTPS 支持: 当 SSL_CERTFILE 环境变量设置时启用 TLS
# 用 stdlib ssl 包装, 不引入第三方依赖
def _make_ssl_context():
    certfile = os.environ.get("CORE_SERVICE_SSL_CERTFILE", "")
    keyfile = os.environ.get("CORE_SERVICE_SSL_KEYFILE", "")
    if not certfile or not os.path.exists(certfile):
        return None
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile, keyfile or None)
    # 强制 TLS 1.2+ (禁用 SSLv3/TLS 1.0/1.1)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    # 安全的 cipher suites (避免弱加密)
    try:
        ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:!aNULL:!MD5:!3DES")
    except ssl.SSLError:
        pass  # 旧 Python 可能不支持
    return ctx


def main():
    print(f"[core_service {VERSION}] port={PORT}", flush=True)
    print(f"  allowed_dirs: {ALLOWED_DIRS}", flush=True)
    print(f"  exec_whitelist: {len(EXEC_WHITELIST)} commands", flush=True)
    print(f"  token_levels: {list(SECRETS.keys())}")
    server = _Server((BIND, PORT), CoreHandler)
    ssl_ctx = _make_ssl_context()
    if ssl_ctx:
        try:
            # 把 socket 包成 TLS socket
            server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)
            print(f"[core_service] listening on {BIND}:{PORT} (HTTPS/TLS)", flush=True)
        except Exception as e:
            # SSL 初始化失败, 回退 HTTP (而不是 crash)
            print(f"[core_service] SSL init failed: {e}, falling back to HTTP", flush=True)
            sys.stderr.write(f"[core_service] SSL fallback: {e}\n")
            server = _Server((BIND, PORT), CoreHandler)  # 重建 socket
            print(f"[core_service] listening on {BIND}:{PORT} (HTTP, fallback)", flush=True)
    else:
        print(f"[core_service] listening on {BIND}:{PORT} (HTTP, no TLS)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
