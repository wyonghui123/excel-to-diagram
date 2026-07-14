"""
[V007.61] core_service.py v2.0 - 极简元能力服务 (核心冻结)
  只做三件事: 上传文件 + 执行命令 + 审计日志
  监听: 9200
  依赖: Python 3.6+ 标准库, 无第三方依赖

  设计原则:
    1. 极简 (~400 行) - 越少代码越少 bug
    2. 不做服务管理 - 避免 pkill/Popen 误杀自身
    3. 调用方决定生命周期 - 通过 exec pkill 停服务, exec bash start.sh 启服务
    4. [v1.2] 审计日志 - 所有 upload/exec 记录
    5. [v1.3] 三级权限 - admin (full) / write (upload+exec) / read (exec readonly + audit)
    6. [v1.4] HTTPS 支持 - TLS 1.2+
    7. [v1.5] audit log 轮转 - 10MB 自动 rotate, 保留 3 个 backup
    8. [v2.0] 解耦 - 可观测性/批量上传拆分到 observability_service (端口 9201)

  扩展能力 (observability_service, 端口 9201, 独立启动/重启):
    - Prometheus 监控指标  (原 v1.7 → obs)
    - 健康检查 liveness+readiness  (原 v1.8 → obs)
    - 批量上传 multipart/form-data  (原 v1.6 → obs)
    - 请求 ID 追踪  (原 v1.9 → obs)

  端点:
    GET   /api                          服务信息
    POST  /api/upload?path=PATH         上传单文件 (500MB)
    GET   /api/exec?cmd=CMD             执行命令 (白名单, bg=true 后台)
    GET   /api/audit?lines=N            查看最近审计日志
    POST  /api/audit/rotate             手动触发 audit 轮转 (admin only)
"""

from __future__ import annotations
import os, sys, json, time, hashlib, threading, subprocess
import http.server, socketserver
from urllib.parse import urlparse, parse_qs

# --- config ---
VERSION         = "v2.0"
PORT            = int(os.environ.get("CORE_SERVICE_PORT", 9200))
BIND            = os.environ.get("CORE_SERVICE_BIND", "0.0.0.0")
TOKEN_HR        = 8
MAX_UPLOAD_MB   = 500
_START_TIME     = time.time()

# [V007.54 v1.3] 三级 token 权限
SECRETS = {
    "admin": os.environ.get("CORE_SERVICE_ADMIN_SECRET", "v007.52-core-admin"),
    "write": os.environ.get("CORE_SERVICE_WRITE_SECRET", "v007.52-core-write"),
    "read":  os.environ.get("CORE_SERVICE_READ_SECRET",  "v007.52-core-read"),
}
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
    "/opt/app/staging",       # [V007.49-D 2026-07-13] staging 隔离环境
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
    # [V007.53] audit log
    AUDIT_LOG = os.environ.get("CORE_SERVICE_AUDIT_LOG", "/var/log/core_service_audit.log")
    AUDIT_LOCK = threading.Lock()
    # [V007.56 v1.5] audit log 轮转
    AUDIT_MAX_BYTES = int(os.environ.get("CORE_SERVICE_AUDIT_MAX_BYTES", 10 * 1024 * 1024))
    AUDIT_BACKUP_KEEP = int(os.environ.get("CORE_SERVICE_AUDIT_BACKUPS", 3))

    @classmethod
    def _audit(cls, action, client_ip, detail):
        """线程安全审计日志 + 自动轮转"""
        try:
            import datetime as _dt
            ts = _dt.datetime.now().isoformat(timespec='seconds')
            line = json.dumps({"ts": ts, "ip": client_ip, "action": action, **detail},
                              ensure_ascii=False)
            with cls.AUDIT_LOCK:
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
            pass

    @classmethod
    def _rotate_audit(cls):
        """[V007.56 v1.5] 轮转 audit log: .log → .log.1 → .log.2 → .log.3"""
        try:
            oldest = f"{cls.AUDIT_LOG}.{cls.AUDIT_BACKUP_KEEP}"
            if os.path.exists(oldest):
                os.unlink(oldest)
            for i in range(cls.AUDIT_BACKUP_KEEP - 1, 0, -1):
                src = f"{cls.AUDIT_LOG}.{i}"
                dst = f"{cls.AUDIT_LOG}.{i + 1}"
                if os.path.exists(src):
                    os.rename(src, dst)
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

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)
        route = p.path.rstrip("/")
        if not _limiter.allow(self.client_address[0]):
            return self._json(429, {"error": "rate limited"})
        try:
            if route in ("", "/", "/api"):
                return self._root(q)
            elif route == "/api/exec":
                return self._exec(q)
            elif route == "/api/audit":
                return self._audit_log(q)
            elif route == "/api/audit/rotate":
                return self._audit_rotate_endpoint(q)
            elif route == "/api/danger/confirm" or route == "/api/danger/verify":
                return self._danger_confirm(q)
            elif route == "/api/isolation_check":
                return self._isolation_check(q)
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
            elif route == "/api/audit/rotate":
                return self._audit_rotate_endpoint(q)
            elif route == "/api/danger/confirm" or route == "/api/danger/verify":
                return self._danger_confirm(q)
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
            "observability": "port 9201 (health/metrics/upload_multi/request_id)",
        })

    # ── GET /api/audit ─────────────────────────────────────
    def _audit_log(self, q):
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
            all_files = [self.AUDIT_LOG]
            for i in range(1, self.AUDIT_BACKUP_KEEP + 1):
                p = f"{self.AUDIT_LOG}.{i}"
                if os.path.exists(p):
                    all_files.append(p)
            all_lines = []
            for f in sorted(all_files, key=lambda x: (x.count("."), x)):
                try:
                    with open(f, "r") as fh:
                        all_lines.extend(fh.readlines())
                except OSError:
                    continue
            recent = all_lines[-n:]
            entries = []
            for line in recent:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    entries.append({"raw": line})
            return self._json(200, {
                "file": self.AUDIT_LOG,
                "backup_files": [f for f in all_files if f != self.AUDIT_LOG],
                "count": len(entries),
                "entries": entries,
            })
        except Exception as e:
            return self._json(500, {"error": str(e)})

    # ── GET /api/isolation_check ──────────────────────────────
    def _isolation_check(self, q):
        """[L8.8] 检测 /tmp 隔离状态 (PrivateTmp)

        Returns:
            tmp_isolated: bool
            systemd_private_tmp: bool
            test_file_real_path: 实际写入路径
            dirs: 各目录隔离状态
        """
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})

        # 1. /tmp inode vs / inode
        tmp_inode = root_inode = None
        tmp_isolated = None
        try:
            tmp_inode = os.stat("/tmp").st_ino
            root_inode = os.stat("/").st_ino
            tmp_isolated = (tmp_inode != root_inode)
        except Exception:
            pass

        # 2. systemd PrivateTmp
        systemd_isolated = None
        try:
            svc = os.environ.get("SERVICE_NAME", "core_service.service")
            out = subprocess.run(
                ["systemctl", "show", svc, "-p", "PrivateTmp"],
                capture_output=True, text=True, timeout=5
            ).stdout
            if out:
                # 输出形如: PrivateTmp=yes
                for line in out.splitlines():
                    if line.startswith("PrivateTmp="):
                        val = line.split("=", 1)[1].strip().lower()
                        systemd_isolated = (val == "yes")
                        break
        except Exception:
            pass

        # 3. 实际写入测试
        test_file = f"/tmp/_isolation_test_{os.getpid()}_{int(time.time())}"
        real_path = ""
        try:
            with open(test_file, "w") as f:
                f.write("test")
            real_path = os.path.realpath(test_file)
        finally:
            try:
                os.remove(test_file)
            except Exception:
                pass

        # 4. 各目录隔离状态
        dirs = ["/tmp", "/var/tmp", "/opt/app/shared", "/opt/app/deployments"]
        isolation_status = {}
        for d in dirs:
            try:
                isolation_status[d] = {
                    "exists": os.path.exists(d),
                    "writable": os.access(d, os.W_OK) if os.path.exists(d) else False,
                    "inode": os.stat(d).st_ino if os.path.exists(d) else None,
                }
            except Exception as ex:
                isolation_status[d] = {"error": str(ex)}

        return self._json(200, {
            "service": "core_service",
            "pid": os.getpid(),
            "tmp_isolated": tmp_isolated,
            "tmp_inode": tmp_inode,
            "root_inode": root_inode,
            "systemd_private_tmp": systemd_isolated,
            "test_file_real_path": real_path,
            "isolation_warning": bool(tmp_isolated and systemd_isolated),
            "dirs": isolation_status,
        })

    # ── POST /api/audit/rotate (admin only) ───────────────
    def _audit_rotate_endpoint(self, q):
        level = _check_token(q)
        if not level:
            self._audit("audit_rotate_denied", self.client_address[0], {"reason": "no_token"})
            return self._json(403, {"error": "token required"})
        if level != "admin":
            self._audit("audit_rotate_denied", self.client_address[0],
                        {"reason": "not_admin", "level": level})
            return self._json(403, {"error": f"admin required, have '{level}'"})
        try:
            existed = os.path.exists(self.AUDIT_LOG)
            size_before = os.path.getsize(self.AUDIT_LOG) if existed else 0
            self._rotate_audit()
            self._audit("audit_rotate_ok", self.client_address[0],
                        {"size_before": size_before})
            return self._json(200, {
                "rotated": True,
                "size_before": size_before,
                "backups_kept": self.AUDIT_BACKUP_KEEP,
            })
        except Exception as e:
            return self._json(500, {"error": str(e)})

    # ── POST /api/upload ─────────────────────────────────
    def _upload(self, q):
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
        # [L8.5 fix 2026-07-13] Multipart 解析 — 客户端发 multipart/form-data 时, 只写 boundary 后的 file 内容
        # 不解析会导致文件被 multipart 头污染 (--Boundary\r\nContent-Disposition:...)
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" in content_type:
            try:
                import re as _re
                m = _re.search(r'boundary=(?:"([^"]+)"|([^;\s]+))', content_type)
                if not m:
                    return self._json(400, {"error": "multipart but no boundary"})
                boundary = (m.group(1) or m.group(2)).encode()
                sep = b'--' + boundary
                # 找到 file 字段的 part (Content-Disposition 包含 filename)
                idx = 0
                file_content = None
                file_name = None
                while True:
                    start = body.find(sep, idx)
                    if start == -1:
                        break
                    part_start = start + len(sep)
                    if body[part_start:part_start+2] == b'--':
                        break  # 结束
                    # 跳过分隔行 (\r\n)
                    if body[part_start:part_start+2] == b'\r\n':
                        part_start += 2
                    # 找 part header 结束 (\r\n\r\n)
                    header_end = body.find(b'\r\n\r\n', part_start)
                    if header_end == -1:
                        break
                    headers = body[part_start:header_end].decode('utf-8', errors='replace')
                    # 找 Content-Disposition
                    cd_match = _re.search(r'Content-Disposition:\s*form-data;\s*name="([^"]+)"(?:;\s*filename="([^"]*)")?',
                                          headers, _re.IGNORECASE)
                    if cd_match and cd_match.group(2):  # 有 filename = file field
                        content_start = header_end + 4
                        # 找下一个 boundary (前面有 \r\n)
                        next_sep = body.find(b'\r\n' + sep, content_start)
                        if next_sep == -1:
                            file_content = body[content_start:]
                        else:
                            file_content = body[content_start:next_sep]
                        file_name = cd_match.group(2)
                        break
                    # 找下一个 boundary
                    next_part = body.find(sep, header_end)
                    if next_part == -1:
                        break
                    idx = next_part
                if file_content is None:
                    return self._json(400, {"error": "multipart: no file field found"})
                # 安全: 拒绝 path traversal 的 filename
                if '..' in file_name or '/' in file_name or '\\' in file_name:
                    self._audit("upload_denied", self.client_address[0],
                                {"reason": "bad_filename", "filename": file_name})
                    return self._json(400, {"error": f"bad filename: {file_name}"})
                # 如果 client 没传 path, 用 path/<file_name>
                if target.endswith('/') or target == '/tmp':
                    target = target.rstrip('/') + '/' + file_name
                body = file_content
                clen = len(body)
            except Exception as mp_err:
                return self._json(400, {"error": f"multipart parse failed: {mp_err}"})
        try:
            os.makedirs(os.path.dirname(target) or "/tmp", exist_ok=True)
            with open(target, "wb") as f:
                f.write(body)
            exe = target.endswith((".sh", ".py"))
            if exe:
                os.chmod(target, 0o755)
            # [V007.49-B 2026-07-13] Upload 契约校验 — 防止"假成功"bug (observability v?/api/upload_multi 报告 200 但实际未写盘)
            # 立即读回磁盘, 验证 size + md5 必须与上传的一致, 不一致返回 500 + audit.
            try:
                verified_size = os.path.getsize(target)
                import hashlib
                with open(target, "rb") as f:
                    verified_md5 = hashlib.md5(f.read()).hexdigest()
                expected_md5 = hashlib.md5(body).hexdigest()
                contract_ok = (verified_size == len(body)) and (verified_md5 == expected_md5)
            except Exception as verify_err:
                contract_ok = False
                verified_size = -1
                verified_md5 = ""
                expected_md5 = hashlib.md5(body).hexdigest()
                self._audit("upload_verify_error", self.client_address[0],
                            {"path": target, "err": str(verify_err)})
            if not contract_ok:
                # 删除可疑文件, 避免下次读取拿到残缺数据
                try:
                    os.remove(target)
                except Exception:
                    pass
                self._audit("upload_contract_violated", self.client_address[0],
                            {"path": target, "sent_size": len(body),
                             "verified_size": verified_size, "expected_md5": expected_md5,
                             "verified_md5": verified_md5})
                return self._json(500, {
                    "error": "upload contract violated (file on disk != uploaded data)",
                    "path": target,
                    "sent_size": len(body),
                    "verified_size": verified_size,
                    "expected_md5": expected_md5,
                    "verified_md5": verified_md5,
                    "hint": "file removed, please retry",
                })
            self._audit("upload_ok", self.client_address[0],
                        {"level": level, "path": target, "size": len(body),
                         "verified_size": verified_size, "md5": verified_md5, "executable": exe})
            return self._json(200, {"action": "uploaded", "path": target,
                                    "size": len(body), "verified_size": verified_size,
                                    "md5": verified_md5, "executable": exe,
                                    "contract": "ok"})
        except Exception as e:
            self._audit("upload_fail", self.client_address[0], {"path": target, "err": str(e)})
            return self._json(500, {"error": str(e)})

    # ── POST /api/danger/confirm (L11.3 fix 2026-07-13) ──
    # 危险操作二次确认 — 用于防止 AI/用户误删关键实体
    # 用法:
    #   1. POST /api/danger/confirm?object_type=role&object_id=1201&token=XXX
    #      → 返回 { "confirm_required": true, "confirm_token": "<uuid>", "warn": "..." }
    #   2. 真实删除 API 必须带 X-Confirm-Delete: <uuid> header
    # 注: backend meta/server.py 检查 X-Confirm-Delete (见 action_executor.py L11.3 fix)
    #     core_service 仅提供 token 颁发 + 验证服务
    def _danger_confirm(self, q):
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})
        if level not in ("write", "admin"):
            return self._json(403, {"error": f"insufficient permission: have '{level}'"})
        object_type = q.get("object_type", [""])[0]
        object_id = q.get("object_id", [""])[0]
        action = q.get("action", ["delete"])[0]
        if not object_type or not object_id:
            return self._json(400, {"error": "object_type + object_id required"})
        import uuid as _uuid
        import time as _t
        token = str(_uuid.uuid4())
        # 危险等级评估
        warn_msgs = []
        danger_level = "info"
        try:
            import sqlite3
            # [V007.49-D 2026-07-13] 支持 staging 环境 (CORE_SERVICE_DB_PATH 覆盖默认)
            db_path = os.environ.get("CORE_SERVICE_DB_PATH", "/opt/app/deployments/meta/architecture.db")
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            if object_type == "role" and action == "delete":
                cur.execute("SELECT COUNT(*) FROM role_permissions WHERE role_id = ?", (object_id,))
                warn_msgs.append(f"role_permissions ref: {cur.fetchone()[0]}")
                cur.execute("SELECT COUNT(*) FROM role_menu_permissions WHERE role_id = ?", (object_id,))
                warn_msgs.append(f"role_menu_permissions ref: {cur.fetchone()[0]}")
                cur.execute("SELECT COUNT(*) FROM role_dimension_scopes WHERE role_id = ?", (object_id,))
                warn_msgs.append(f"role_dimension_scopes ref: {cur.fetchone()[0]}")
                cur.execute("SELECT code, name FROM role WHERE id = ?", (object_id,))
                row = cur.fetchone()
                if row:
                    warn_msgs.insert(0, f"target: role#{object_id} ({row[0]}: {row[1]})")
                danger_level = "critical" if any('ref: 0' not in m and 'ref:' in m for m in warn_msgs if 'ref:' in m) else "warn"
            elif object_type == "user":
                danger_level = "high"
            conn.close()
        except Exception as e:
            warn_msgs.append(f"ref check failed: {e}")
        self._audit("danger_confirm_issued", self.client_address[0],
                    {"object_type": object_type, "object_id": object_id,
                     "action": action, "warn_msgs": warn_msgs, "danger_level": danger_level})
        return self._json(200, {
            "confirm_required": True,
            "confirm_token": token,
            "object_type": object_type,
            "object_id": object_id,
            "action": action,
            "warn_msgs": warn_msgs,
            "danger_level": danger_level,
            "issued_at": _t.time(),
            "hint": f"with token in HTTP header: X-Confirm-Delete: {token}",
            "usage": "Delete API will check X-Confirm-Delete header; missing or wrong token returns 409",
        })

    # ── GET /api/exec ───────────────────────────────────
    def _exec(self, q):
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


# [V007.55 v1.4] HTTPS 支持
def _make_ssl_context():
    certfile = os.environ.get("CORE_SERVICE_SSL_CERTFILE", "")
    keyfile = os.environ.get("CORE_SERVICE_SSL_KEYFILE", "")
    if not certfile or not os.path.exists(certfile):
        return None
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile, keyfile or None)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:!aNULL:!MD5:!3DES")
    except ssl.SSLError:
        pass
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
            server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)
            print(f"[core_service] listening on {BIND}:{PORT} (HTTPS/TLS)", flush=True)
        except Exception as e:
            print(f"[core_service] SSL init failed: {e}, falling back to HTTP", flush=True)
            sys.stderr.write(f"[core_service] SSL fallback: {e}\n")
            server = _Server((BIND, PORT), CoreHandler)
            print(f"[core_service] listening on {BIND}:{PORT} (HTTP, fallback)", flush=True)
    else:
        print(f"[core_service] listening on {BIND}:{PORT} (HTTP, no TLS)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
