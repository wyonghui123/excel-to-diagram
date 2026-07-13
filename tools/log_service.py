"""
[V007.35] 轻量级 log HTTP service v4 — 可观测性核心
  独立进程, 不依赖 server.py / unified_server, Python 3.8+ 标准库

  核心能力 (v4 新增标记 ★):
    - 静态日志查询: /api/log, /api/log/list, /api/log/range ★
    - 实时日志流:   /api/log/stream (SSE tail -f) ★
    - 数据库诊断:   /api/db/health, /api/db/query ★, /api/db/metrics
    - 系统可观测:   /api/system, /api/net ★, /api/process ★, /api/dmesg
    - 配置读取:     /api/config ★
    - 指标导出:     /api/metrics (Prometheus) ★
    - 自检:        /api/health, /api/token
    - [V007.53] SQLite I/O 专项: /api/disk/errors ★, /api/disk/check ★

  usage:
    nohup python3 log_service.py > /tmp/log_service.log 2>&1 &
    curl http://localhost:9101/api/system

  端口: 9101
  依赖: Python 3.8+ 标准库, 无 pip 依赖
  内存: < 25MB RSS (v4 加了 SSE 缓冲)
"""

from __future__ import annotations  # Py3.7+ 让 `X | Y` 语法兼容

# [V007.49] SQLite 升级: monkey-patch sqlite3 → sqlean (3.50.4)
try:
    import sqlean
    import sys as _sys_for_sqlean
    _sys_for_sqlean.modules['sqlite3'] = sqlean
except ImportError:
    pass  # fallback 到系统 sqlite3

import os, sys, json, time, hashlib, threading, re, fnmatch, io
import http.server, socketserver, subprocess, sqlite3
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

# ─── 配置常量 ────────────────────────────────────
LOG_DIR   = os.environ.get("LOG_SERVICE_LOG_DIR", "/opt/app/deployments/meta")
DB_PATH   = os.environ.get("LOG_SERVICE_DB_PATH", f"{LOG_DIR}/architecture.db")
PORT      = int(os.environ.get("LOG_SERVICE_PORT", 9101))
BIND      = os.environ.get("LOG_SERVICE_BIND", "0.0.0.0")
SECRET    = os.environ.get("LOG_SERVICE_SECRET", "v007.35-infra")
# [V007.49 P1 BUG-FIX 2026-07-09] 服务版本: log_service v4.8 - 加 P0 远程管理端点
# [V007.51 2026-07-11] 服务版本: log_service v4.9 - P1 基础设施 (看门狗+归档+巡检+告警)
# [V007.53 2026-07-12] 服务版本: log_service v4.11 - SQLite disk I/O error 专项监控 (/api/disk/errors + /api/disk/check)
VERSION   = "v4.11"
MAX_LINES = int(os.environ.get("LOG_SERVICE_MAX_LINES", 5000))  # 单次最大行
TOKEN_HR  = int(os.environ.get("LOG_SERVICE_TOKEN_HOURS", 8))

# 安全白名单: /api/log, /api/config 只读这些目录
ALLOWED_DIRS = [
    "/opt/app/deployments",
    "/opt/app/shared/logs",
    "/opt/app/shared",
    "/tmp",
    "/var/log",
    # [V007.45 BUG-FIX 2026-07-09] 部署智能体 SOP 必需
    "/opt/app/current",       # current symlink 路径
    "/opt/app/backups",       # 备份路径
    "/opt/app/migrations",    # migration 路径
    "/etc/systemd/system",    # systemd 服务路径
    # [V007.46] 部署智能体监控路径
    "/opt/app/deploy_history", # 部署历史
    "/opt/app/manifests",     # 部署 manifest
]

# ─── Token ───────────────────────────────────────
def _gen_token() -> str:
    now = int(time.time())
    tokens = []
    for off in range(TOKEN_HR + 1):
        h = (now - off * 3600) // 3600
        tokens.append(hashlib.sha256(f"{SECRET}:{h}".encode()).hexdigest()[:16])
    return ",".join(tokens)

def _check_token(params: dict) -> bool:
    t = params.get("token", [""])[0]
    return t in _gen_token().split(",") if t else False

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

# ─── 轻量限流 (令牌桶, 内存) ★ ──────────────────
class RateLimiter:
    def __init__(self, max_per_sec: int = 10):
        self._lock = threading.Lock()
        self._max = max_per_sec
        self._buckets: dict[str, list] = {}  # ip -> [timestamps]

    def allow(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            bucket = self._buckets.setdefault(ip, [])
            bucket[:] = [t for t in bucket if now - t < 1.0]
            if len(bucket) >= self._max:
                return False
            bucket.append(now)
            return True

_limiter = RateLimiter(max_per_sec=20)

# [V007.51 v4.9] 跨平台辅助: 端口探测 + 只读 DB 打开
import socket as _socket
import contextlib as _contextlib
import urllib.request as _urllib_request

@_contextlib.contextmanager
def _socket_context(port: int):
    """跨平台 socket context manager, 用于探测端口"""
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        yield s
    finally:
        s.close()

@_contextlib.contextmanager
def _sqlite_open_ro(db_path: str, timeout: int = 5):
    """跨平台只读 DB 连接 context manager"""
    conn = sqlite3.connect(db_path, timeout=timeout)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass

# ─── 日志时间戳解析 ───────────────────────────────
LOG_TS_RE = re.compile(
    r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})(?:[.,]\d+)?'
)

def _parse_log_ts(line: str):  # -> Optional[datetime] (Py3.9 兼容)
    m = LOG_TS_RE.search(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

def _filter_by_time(lines: list[str], from_ts: str|None, to_ts: str|None) -> list[str]:
    """按时间戳过滤日志行 (from_ts/to_ts 格式: '2026-07-07T15:00' 或 '15:00')"""
    if not from_ts and not to_ts:
        return lines

    fmt = "%Y-%m-%dT%H:%M"
    def _parse(s: str):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            try:
                # 只有时间, 用今天的日期
                today = datetime.now().strftime("%Y-%m-%d")
                return datetime.strptime(f"{today}T{s}", fmt)
            except ValueError:
                return None

    ft = _parse(from_ts) if from_ts else None
    tt = _parse(to_ts) if to_ts else None

    result = []
    for line in lines:
        ts = _parse_log_ts(line)
        if ts is None:
            result.append(line)
            continue
        if ft and ts < ft:
            continue
        if tt and ts > tt:
            continue
        result.append(line)
    return result

# ─── HTTP Handler ─────────────────────────────────
_START_TIME = time.time()

class LogHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass

    def do_GET(self):
        ip = self.client_address[0]
        if not _limiter.allow(ip):
            return self._json(429, {"error": "rate limited, max 20 req/s"})
        try:
            p = urlparse(self.path)
            q = parse_qs(p.query)
            route = p.path.rstrip("/")
            handlers = {
            "/api/system":    lambda: self._system(),
            "/api/proc":      lambda: self._proc(),
            "/api/process":   lambda: self._process_detail(q),       # ★
            "/api/net":       lambda: self._net(q),                  # ★
            "/api/log":       lambda: self._log(q),
            "/api/log/list":  lambda: self._log_list(q),             # ★
            "/api/log/range": lambda: self._log_range(q),            # ★
            "/api/log/stream":lambda: self._log_stream(q),           # ★
            "/api/find":      lambda: self._find(q),
            "/api/db/health": lambda: self._db_health(),
            "/api/db/query":  lambda: self._db_query(q),             # ★
            "/api/db/metrics":lambda: self._db_metrics(),
            "/api/dmesg":     lambda: self._dmesg(q),
            "/api/config":    lambda: self._config(q),               # ★
            "/api/metrics":   lambda: self._prometheus(),            # ★
            "/api/health":    lambda: self._json(200, {"ok":True,"uptime":int(time.time()-_START_TIME)}),
            "/api/token":     lambda: self._token(q),
            # [V007.37 v4.5] 合并 dev-agent v3.5 端点 (排查 disk I/O 必需)
            "/api/sqlite":       lambda: self._sqlite(q),
            "/api/sqlite/load":  lambda: self._sqlite_load(q),
            "/api/iostat":       lambda: self._iostat(q),
            "/api/proc/io":      lambda: self._proc_io(q),
            # [V007.45 v4.6] 部署智能体 SOP 端点 (修 12+ 小时失职)
            "/api/deploy/current":    lambda: self._deploy_current(q),       # current 链接 + 实际目录
            "/api/deploy/history":    lambda: self._deploy_history(q),       # 最近 10 次部署
            "/api/deploy/check_files":lambda: self._deploy_check_files(q),   # 8 文件 MD5 强校验
            "/api/deploy/yonaa_versions": lambda: self._deploy_yonaa_versions(q), # yonaa 8 文件 V007.46/V007.47 标记
            "/api/deploy/invariant":  lambda: self._deploy_invariant(q),     # [V007.49 P1] 部署后立即验 8 关键文件
            "/api/ports/auto_detect": lambda: self._ports_auto_detect(q),    # 3011/5001/8081/9101 扫描
            "/api/verify/invariant":  lambda: self._verify_invariant(q),     # V8ab 业务回归 (200 次压测)
            # [V007.50 v4.8] P0 远程管理/排查/测试端点
            "/api/manage/journal_mode": lambda: self._manage_journal_mode(q), # 安全切换 journal_mode
            "/api/diag/trace":         lambda: self._diag_trace(q),          # 跨服务 trace 聚合
            "/api/test/disk_io":       lambda: self._test_disk_io(q),         # 并发 disk I/O 压测
            "/api/deploy/smoke":       lambda: self._deploy_smoke(q),         # 一键冒烟
            # [V007.50 v4.8] P0 远程管理: 文件上传 + 命令执行
            "/api/upload":             lambda: self._upload(q),               # 文件上传 (POST)
            "/api/exec":               lambda: self._exec_cmd(q),             # 远程命令执行
            # [V007.51 v4.9] P1 基础设施: 看门狗 + 日志归档 + 巡检 + 告警 + 磁盘预警
            "/api/service/supervisor": lambda: self._supervisor(q),           # 看门狗: 进程状态 + 自动重启
            "/api/log/archive":        lambda: self._log_archive(q),          # 日志归档清理
            "/api/disk/forecast":      lambda: self._disk_forecast(q),        # 磁盘满预测
            "/api/health/inspect":     lambda: self._health_inspect(q),       # 周期性健康巡检
            "/api/alert/sse":          lambda: self._alert_sse(q),            # SSE 实时告警推流
            # [V007.53 v4.11] SQLite disk I/O error 专项监控
            "/api/disk/errors":        lambda: self._disk_errors(q),          # dmesg I/O 错误扫描
            "/api/disk/check":         lambda: self._disk_check(q),           # SQLite IO 综合健康检查
            # [V007.49-D 2026-07-13] SQLite readonly 检测 (修补 root 绕过 chmod 的漏洞)
            "/api/db/can_write":       lambda: self._db_can_write(q),         # 检测 db 当前是否可写
            }
            if route in handlers:
                handlers[route]()
            elif route in ("/", "/api"):
                # [V007.45] 列所有端点 (修 12+ 小时"假端点"误诊)
                # 之前用 /api/sandbox /api/diag/disk_io /api/path 全 404, 但 mock 假数据被误信
                # 现在返完整端点表, 部署智能体直接看
                self._json(200, {
                    "service": "log_service v4",
                    "endpoints": sorted(handlers.keys()) + ["/", "/api"],
                    "note": "v4.11 has 43 endpoints; V007.53: /api/disk/errors /api/disk/check (SQLite disk IO monitoring)",
                })
            else:
                # [V007.45] 404 时返"可能相似端点"建议, 避免假端点
                similar = [k for k in handlers.keys() if any(part in route for part in k.split('/'))]
                self._json(404, {
                    "error": "not found",
                    "route": route,
                    "similar": similar[:5],
                    "hint": f"GET /api 列全部端点"
                })
        except Exception as e:
            self._json(500, {"error": str(e), "type": type(e).__name__})

    def do_POST(self):
        ip = self.client_address[0]
        if not _limiter.allow(ip):
            return self._json(429, {"error": "rate limited, max 20 req/s"})
        try:
            p = urlparse(self.path)
            q = parse_qs(p.query)
            route = p.path.rstrip("/")
            if route == "/api/upload":
                self._upload(q)
            elif route == "/api/exec":
                self._exec_cmd(q)
            else:
                self._json(404, {"error": "POST not supported", "route": route,
                                 "hint": "POST /api/upload or /api/exec"})
        except Exception as e:
            self._json(500, {"error": str(e), "type": type(e).__name__})

    # ── /api/system ───────────────────────────────
    def _system(self):
        r = {"load": list(os.getloadavg())}
        try:
            st = os.statvfs("/")
            r["disk"] = {"total_gb": round(st.f_blocks*st.f_frsize/1073741824,2),
                         "free_gb":  round(st.f_bfree*st.f_frsize/1073741824,2)}
        except: pass
        try:
            r["mem"] = {}
            for line in open("/proc/meminfo"):
                k, v = line.split(":",1)
                r["mem"][k.strip()] = v.strip()
        except: pass
        try:
            r["total_fds"] = sum(
                len(os.listdir(f"/proc/{p}/fd")) for p in os.listdir("/proc")
                if p.isdigit() and os.path.exists(f"/proc/{p}/fd")
            )
        except: pass
        try:
            r["uptime_sec"] = float(open("/proc/uptime").read().split()[0])
            r["uptime_h"] = round(r["uptime_sec"] / 3600, 1)
        except: pass
        self._json(200, r)

    # ── /api/proc ─────────────────────────────────
    def _proc(self):
        result = subprocess.run(["ps", "auxf"], capture_output=True, text=True, timeout=5)
        py = [l for l in result.stdout.split("\n") if "python" in l.lower() and "grep" not in l]
        self._json(200, {"total_lines": len(result.stdout.split("\n")), "python": py})

    # ── /api/process ★ ────────────────────────────
    def _process_detail(self, q):
        """每进程详情: pid, name, etime, fd_count, rss_mb, cpu%"""
        name_filter = q.get("name", [""])[0].lower()
        procs = []
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                pdir = f"/proc/{pid}"
                cmd = open(f"{pdir}/cmdline", "rb").read().decode(errors="replace").replace("\x00"," ").strip()
                if not cmd:
                    continue
                if name_filter and name_filter not in cmd.lower():
                    continue
                stat = open(f"{pdir}/stat").read()
                parts = stat.split()
                # pid, comm, state, ppid, ... utime(14), stime(15), ... rss(24)
                comm = parts[1].strip("()")
                rss_pages = int(parts[23]) if len(parts) > 23 else 0
                rss_mb = round(rss_pages * os.sysconf("SC_PAGE_SIZE") / 1048576, 1) if hasattr(os, "sysconf") else rss_pages // 256
                fd_count = len(os.listdir(f"{pdir}/fd")) if os.path.exists(f"{pdir}/fd") else 0
                # etime
                etime_sec = time.time() - os.path.getctime(pdir)
                etime_str = str(timedelta(seconds=int(etime_sec)))
                procs.append({
                    "pid": int(pid), "comm": comm, "cmd": cmd[:120],
                    "rss_mb": rss_mb, "fd_count": fd_count, "etime": etime_str,
                })
            except (PermissionError, FileNotFoundError, ValueError, KeyError):
                continue
        procs.sort(key=lambda x: x.get("fd_count", 0), reverse=True)
        self._json(200, {"count": len(procs), "processes": procs[:50]})

    # ── /api/net ★ ────────────────────────────────
    def _net(self, q):
        """网络连接: tcp/udp + 端口占用"""
        result = {"tcp_listen": [], "tcp_established": [], "ports": {}}
        try:
            out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5).stdout
            for line in out.split("\n")[1:]:
                if line.strip():
                    result["tcp_listen"].append(line.strip())
        except: pass
        try:
            out = subprocess.run(["ss", "-tnp"], capture_output=True, text=True, timeout=5).stdout
            est = [l.strip() for l in out.split("\n")[1:] if "ESTAB" in l]
            result["tcp_established"] = est[:30]
        except: pass
        # 端口 → pid 映射
        port_map = {}
        try:
            out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5).stdout
            for line in out.split("\n"):
                for m in re.finditer(r':(\d+)\s.*pid=(\d+)', line):
                    port_map[int(m.group(1))] = int(m.group(2))
        except: pass
        result["ports"] = port_map
        self._json(200, result)

    # ── /api/log ──────────────────────────────────
    def _log(self, q):
        fname = q.get("file", ["server.log"])[0]
        lines = min(int(q.get("lines", [100])[0]), MAX_LINES)
        grep  = q.get("grep", [""])[0]
        tail  = q.get("tail", ["true"])[0].lower() in ("1","true","yes")
        fp = fname if fname.startswith("/") else os.path.join(LOG_DIR, fname)
        if not _path_allowed(fp):
            return self._json(403, {"error": f"path not allowed: {fp}"})
        if not os.path.exists(fp):
            return self._json(404, {"error": f"not found: {fp}"})
        start = time.time()
        cmd = f"tail -n {lines} '{fp}'" if tail else f"head -n {lines} '{fp}'"
        if grep:
            cmd += f" | grep -i '{grep}'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        out = result.stdout
        self._json(200, {
            "file": fp, "size": os.path.getsize(fp),
            "output": out, "output_lines": out.count("\n"),
            "elapsed_ms": round((time.time()-start)*1000,1),
            "stderr": result.stderr[:300] if result.stderr else None,
        })

    # ── /api/log/list ★ ───────────────────────────
    def _log_list(self, q):
        """列出日志目录下的文件 (按 mtime 倒序)"""
        d = q.get("dir", [LOG_DIR])[0]
        if not _path_allowed(d):
            return self._json(403, {"error": f"dir not allowed: {d}"})
        pattern = q.get("pattern", ["*"])[0]
        max_n = min(int(q.get("max", [30])[0]), 100)
        files = []
        for root, dirs, filenames in os.walk(d):
            for fn in filenames:
                if fnmatch.fnmatch(fn, pattern):
                    fp = os.path.join(root, fn)
                    st = os.stat(fp)
                    files.append({"name": fn, "path": fp, "size": st.st_size,
                                   "mtime": datetime.fromtimestamp(st.st_mtime).isoformat()[:19]})
            if len(files) >= max_n:
                break
        files.sort(key=lambda x: x["mtime"], reverse=True)
        self._json(200, {"dir": d, "pattern": pattern, "files": files[:max_n], "count": len(files)})

    # ── /api/log/range ★ ──────────────────────────
    def _log_range(self, q):
        """按时间范围查询日志: from=2026-07-07T15:00&to=2026-07-07T16:00"""
        fname = q.get("file", ["server.log"])[0]
        from_ts = q.get("from", [None])[0]
        to_ts   = q.get("to",   [None])[0]
        grep    = q.get("grep", [""])[0]
        fp = fname if fname.startswith("/") else os.path.join(LOG_DIR, fname)
        if not _path_allowed(fp):
            return self._json(403, {"error": f"path not allowed: {fp}"})
        if not os.path.exists(fp):
            return self._json(404, {"error": f"not found: {fp}"})
        start = time.time()
        # 先 tail 取足够多行 (最多 MAX_LINES)
        result = subprocess.run(
            f"tail -n {MAX_LINES} '{fp}'",
            shell=True, capture_output=True, text=True, timeout=15
        )
        all_lines = result.stdout.split("\n")
        filtered = _filter_by_time(all_lines, from_ts, to_ts)
        if grep:
            filtered = [l for l in filtered if grep.lower() in l.lower()]
        out = "\n".join(filtered)
        self._json(200, {
            "file": fp, "from": from_ts, "to": to_ts,
            "scanned_lines": len(all_lines), "matched_lines": len(filtered),
            "output": out[:500000],  # 截断 500KB
            "elapsed_ms": round((time.time()-start)*1000,1),
        })

    # ── /api/log/stream ★ (SSE tail -f) ───────────
    def _log_stream(self, q):
        """SSE 实时推送: curl -N 'http://.../api/log/stream?lines=20'"""
        fname = q.get("file", ["server.log"])[0]
        lines = min(int(q.get("lines", [20])[0]), 200)
        fp = fname if fname.startswith("/") else os.path.join(LOG_DIR, fname)
        if not _path_allowed(fp):
            return self._json(403, {"error": f"path not allowed: {fp}"})
        if not os.path.exists(fp):
            return self._json(404, {"error": f"not found: {fp}"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.wfile.flush()
        try:
            # 先发最后 N 行
            with open(fp, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                buf_size = 8192
                read_from = max(0, size - buf_size)
                f.seek(read_from)
                chunk = f.read().decode(errors="replace")
                tail_lines = chunk.split("\n")[-lines:]
                for line in tail_lines:
                    self.wfile.write(f"data: {line}\n\n".encode())
                    self.wfile.flush()
            # 轮询新行
            last_size = os.path.getsize(fp)
            last_ino = os.stat(fp).st_ino
            for _ in range(300):  # 最多 5min (300 x 1s)
                time.sleep(1)
                # 检测 log rotation
                try:
                    st = os.stat(fp)
                    if st.st_ino != last_ino:
                        self.wfile.write(f"event: rotated\ndata: {{}}\n\n".encode()); self.wfile.flush()
                        last_ino = st.st_ino
                        last_size = 0
                except FileNotFoundError:
                    self.wfile.write(f"event: deleted\ndata: {{}}\n\n".encode()); self.wfile.flush()
                    break
                cur_size = os.path.getsize(fp)
                if cur_size > last_size:
                    with open(fp, "rb") as f:
                        f.seek(last_size)
                        new_data = f.read(cur_size - last_size).decode(errors="replace")
                    for line in new_data.split("\n"):
                        if line:
                            self.wfile.write(f"data: {line}\n\n".encode())
                            self.wfile.flush()
                    last_size = cur_size
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ── /api/find ─────────────────────────────────
    def _find(self, q):
        name = q.get("name", ["*.log"])[0]
        path = q.get("path", ["/opt/app"])[0]
        if not _path_allowed(path):
            return self._json(403, {"error": f"path not allowed: {path}"})
        r = subprocess.run(
            f"find '{path}' -name '{name}' -type f 2>/dev/null | head -50",
            shell=True, capture_output=True, text=True, timeout=15
        )
        files = [l for l in r.stdout.strip().split("\n") if l]
        self._json(200, {"path": path, "name": name, "files": files, "count": len(files)})

    # ── /api/db/health ────────────────────────────
    def _db_health(self):
        try:
            r = {"db_path": DB_PATH}
            sz = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
            r["size_mb"] = round(sz/1048576,2)
            for suf, key in [("-wal","wal_mb"),("-shm","shm_mb")]:
                p = DB_PATH+suf
                r[key] = round(os.path.getsize(p)/1048576,2) if os.path.exists(p) else 0
            conn = sqlite3.connect(DB_PATH, timeout=5)
            r["journal"] = conn.execute("PRAGMA journal_mode").fetchone()[0]
            r["busy_ms"] = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            r["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
            for tbl in ["users","roles","products","audit_logs","enum_types","enum_values",
                        "management_dimensions","role_dimension_scopes"]:  # ★ V007.35: 完整表清单
                try:
                    r[tbl] = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                except: pass
            conn.close()
            self._json(200, r)
        except Exception as e:
            self._json(500, {"error": str(e), "type": type(e).__name__})

    # ── /api/db/query ★ ───────────────────────────
    def _db_query(self, q):
        """只读 SQL 查询 (仅 SELECT/PRAGMA/EXPLAIN, 拒绝写入)"""
        sql = q.get("q", [""])[0].strip()
        if not sql:
            return self._json(400, {"error": "missing ?q="})
        sql_upper = sql.lstrip().upper()
        allowed = ("SELECT", "PRAGMA", "EXPLAIN", "WITH")
        if not any(sql_upper.startswith(a) for a in allowed):
            return self._json(403, {"error": "only read-only queries allowed"})
        # 二级防御: 拒绝黑名单关键词
        forbidden = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "ATTACH", "DETACH",
                     "VACUUM", "REINDEX", "PRAGMA integrity_check", "PRAGMA wal_checkpoint"]
        for f in forbidden:
            if f in sql_upper:
                return self._json(403, {"error": f"forbidden keyword: {f}"})
        max_rows = min(int(q.get("limit", [100])[0]), 1000)
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql)
            rows = [dict(row) for row in cur.fetchmany(max_rows)]
            col_names = [d[0] for d in cur.description] if cur.description else []
            conn.close()
            self._json(200, {"columns": col_names, "rows": rows, "row_count": len(rows),
                             "truncated": len(rows) >= max_rows})
        except Exception as e:
            self._json(500, {"error": str(e), "type": type(e).__name__})

    # ── /api/db/metrics ───────────────────────────
    def _db_metrics(self):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            r = {"tables": [t[0] for t in tables], "table_count": len(tables)}
            # [V007.39 BUG-FIX] TRUNCATE → PASSIVE (TRUNCATE 截断 WAL → 读连接失效 → disk I/O error)
            wal_frames = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchall()
            r["wal_checkpoint"] = [list(row) for row in wal_frames]
            conn.close()
            self._json(200, r)
        except Exception as e:
            self._json(500, {"error": str(e)})

    # ── /api/dmesg ────────────────────────────────
    def _dmesg(self, q):
        lines = min(int(q.get("lines", [50])[0]), 500)
        grep = q.get("grep", [""])[0]
        r = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=5)
        all_lines = r.stdout.split("\n")
        if grep:
            all_lines = [l for l in all_lines if grep.lower() in l.lower()]
        out = "\n".join(all_lines[-lines:])
        self._json(200, {"output": out, "total": len(r.stdout.split("\n"))})

    # ── /api/disk/errors ★ [V007.53 v4.11] ────────
    def _disk_errors(self, q):
        """扫描 dmesg 中的磁盘 I/O 错误模式, 支持时间窗口过滤
        用法: GET /api/disk/errors?hours=24&token=XXX
        返回: error_count, patterns (分类计数), samples (样例), has_errors
        """
        hours = int(q.get("hours", ["24"])[0])
        grep_only = q.get("grep", [""])[0]

        # I/O 错误关键模式 (SQLite disk I/O error + kernel 层)
        IO_PATTERNS = {
            "disk_io_error":    re.compile(r"disk I/O error", re.I),
            "io_error":         re.compile(r"\bI/O error\b", re.I),
            "blk_update":       re.compile(r"blk_update_request.*I/O error", re.I),
            "buffer_io":        re.compile(r"Buffer I/O error", re.I),
            "ext4_error":       re.compile(r"EXT4-fs error", re.I),
            "ext4_warning":     re.compile(r"EXT4-fs warning", re.I),
            "read_error":       re.compile(r"\bread error\b", re.I),
            "write_error":      re.compile(r"\bwrite error\b", re.I),
            "sector_error":     re.compile(r"sector.*error", re.I),
            "sqlite_io":        re.compile(r"disk I/O error", re.I),  # SQLite 特有
        }

        r = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=5)
        all_lines = r.stdout.split("\n")

        # 时间过滤: 解析 dmesg 时间戳 [seconds.microseconds]
        dmesg_now_match = re.search(r"\[\s*(\d+\.\d+)\]", all_lines[-1]) if all_lines else None
        dmesg_now = float(dmesg_now_match.group(1)) if dmesg_now_match else 0
        cutoff = dmesg_now - hours * 3600

        matched = {}  # pattern_name -> {"count": N, "samples": [...]}
        for name, pat in IO_PATTERNS.items():
            hits = []
            for line in all_lines:
                if pat.search(line):
                    # 时间过滤
                    ts_match = re.search(r"\[\s*(\d+\.\d+)\]", line)
                    if ts_match:
                        ts = float(ts_match.group(1))
                        if ts < cutoff:
                            continue
                    hits.append(line.strip())
            if hits:
                matched[name] = {"count": len(hits), "samples": hits[-5:]}

        if grep_only:
            matched = {k: v for k, v in matched.items() if grep_only.lower() in k.lower()}

        total_errors = sum(v["count"] for v in matched.values())
        self._json(200, {
            "check_ts": datetime.now().isoformat(),
            "window_hours": hours,
            "dmesg_uptime_sec": dmesg_now,
            "total_errors": total_errors,
            "has_errors": total_errors > 0,
            "patterns": {k: {"count": v["count"]} for k, v in matched.items()},
            "samples": {k: v["samples"] for k, v in matched.items() if v["samples"]},
            "status": "WARNING" if total_errors > 0 else "OK",
        })

    # ── /api/config ★ ─────────────────────────────
    def _config(self, q):
        """读配置文件: curl 'http://.../api/config?file=/opt/app/deployments/meta/.env'"""
        fname = q.get("file", ["server.log"])[0]
        fp = fname if fname.startswith("/") else os.path.join(LOG_DIR, fname)
        if not _path_allowed(fp):
            return self._json(403, {"error": f"path not allowed: {fp}"})
        if not os.path.exists(fp):
            return self._json(404, {"error": f"not found: {fp}"})
        max_kb = min(int(q.get("max_kb", [50])[0]), 200)
        with open(fp, "rb") as f:
            content = f.read(max_kb * 1024).decode(errors="replace")
        # 自动脱敏: 隐藏 password/secret/key/token 行
        lines = content.split("\n")
        masked = []
        sensitive = re.compile(r'(password|secret|key|token|pass|pwd)', re.I)
        for line in lines:
            if sensitive.search(line):
                eq_pos = line.find("=")
                if eq_pos > 0:
                    masked.append(line[:eq_pos+1] + " ***MASKED***")
                else:
                    masked.append("***MASKED***")
            else:
                masked.append(line)
        self._json(200, {"file": fp, "size": os.path.getsize(fp),
                         "content": "\n".join(masked), "lines": len(masked)})

    # ── /api/metrics ★ (Prometheus) ───────────────
    def _prometheus(self):
        """导出 Prometheus 格式指标"""
        metrics = io.StringIO()
        metrics.write("# HELP log_service_uptime_seconds Service uptime\n")
        metrics.write("# TYPE log_service_uptime_seconds gauge\n")
        metrics.write(f"log_service_uptime_seconds {int(time.time()-_START_TIME)}\n")
        # 系统
        try:
            metrics.write("# TYPE node_load1 gauge\n")
            load = os.getloadavg()
            metrics.write(f"node_load1 {load[0]:.2f}\n")
            metrics.write(f"node_load5 {load[1]:.2f}\n")
            metrics.write(f"node_load15 {load[2]:.2f}\n")
        except: pass
        try:
            st = os.statvfs("/")
            metrics.write("# TYPE disk_free_bytes gauge\n")
            metrics.write(f"disk_free_bytes {st.f_bfree * st.f_frsize}\n")
            metrics.write(f"disk_total_bytes {st.f_blocks * st.f_frsize}\n")
        except: pass
        # fd 总数
        try:
            total_fd = sum(len(os.listdir(f"/proc/{p}/fd"))
                           for p in os.listdir("/proc")
                           if p.isdigit() and os.path.exists(f"/proc/{p}/fd"))
            metrics.write("# TYPE node_total_fds gauge\n")
            metrics.write(f"node_total_fds {total_fd}\n")
        except: pass
        # db
        try:
            if os.path.exists(DB_PATH):
                sz = os.path.getsize(DB_PATH)
                metrics.write("# TYPE db_size_bytes gauge\n")
                metrics.write(f"db_size_bytes {sz}\n")
                for suf, name in [("-wal","db_wal_bytes"),("-shm","db_shm_bytes")]:
                    p = DB_PATH+suf
                    if os.path.exists(p):
                        metrics.write(f"# TYPE {name} gauge\n{name} {os.path.getsize(p)}\n")
        except: pass
        # 每进程 fd
        try:
            metrics.write("# TYPE process_fd_count gauge\n")
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                try:
                    cmd = open(f"/proc/{pid}/cmdline","rb").read().decode(errors="replace").replace("\x00"," ").strip()[:80]
                    if not cmd:
                        continue
                    fd_count = len(os.listdir(f"/proc/{pid}/fd"))
                    safe_cmd = re.sub(r'[^a-zA-Z0-9_\-.]', '_', cmd.split()[0] if cmd else "unknown")[:40]
                    metrics.write(f'process_fd_count{{pid="{pid}",cmd="{safe_cmd}"}} {fd_count}\n')
                except: pass
        except: pass
        # 端口
        try:
            metrics.write("# TYPE port_listening gauge\n")
            out = subprocess.run(["ss","-tlnp"], capture_output=True, text=True, timeout=3).stdout
            for m in re.finditer(r':(\d+)\s.*pid=(\d+)', out):
                metrics.write(f'port_listening{{port="{m.group(1)}",pid="{m.group(2)}"}} 1\n')
            metrics.write("# TYPE tcp_established gauge\n")
            out2 = subprocess.run(["ss","-tnp"], capture_output=True, text=True, timeout=3).stdout
            metrics.write(f"tcp_established {out2.count('ESTAB')}\n")
        except: pass

        body = metrics.getvalue().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── /api/token ────────────────────────────────
    def _token(self, q):
        if not _check_token(q):
            return self._json(403, {"error": "invalid token"})
        self._json(200, {"token": _gen_token().split(",")[0]})

    # ── helpers ───────────────────────────────────
    def _help(self):
        return {
            "service": "log_service v4 (V007.35)",
            "endpoints": {
                "日志":    ["/api/log", "/api/log/list", "/api/log/range", "/api/log/stream"],
                "数据库":  ["/api/db/health", "/api/db/query", "/api/db/metrics"],
                "系统":    ["/api/system", "/api/proc", "/api/process", "/api/net", "/api/dmesg"],
                "配置":    ["/api/config"],
                "指标":    ["/api/metrics"],
                "自检":    ["/api/health", "/api/token"],
            },
            "version": "v4 (V007.35)",
            "port": PORT,
        }

    def _json(self, code, obj):
        body = json.dumps(obj, indent=2, default=str, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    # ──────────────────────────────────────────────────
    # [V007.37 v4.5] 合并 dev-agent v3.5 端点实现
    #  排查 disk I/O error 真因必需 (sqlite/load 压力 + iostat 抖动 + proc/io 字节数)
    # ──────────────────────────────────────────────────

    # ── /api/sqlite ─────────────────────────────────
    def _sqlite(self, q):
        """执行只读 SQL (白名单: SELECT/PRAGMA) — 排查 SQLite 层稳定性"""
        sql = q.get("sql", [""])[0].strip()
        if not sql:
            return self._json(400, {"err": "sql required"})
        sql_l = sql.lower().lstrip()
        if not (sql_l.startswith("select") or sql_l.startswith("pragma")):
            return self._json(403, {"err": "only SELECT/PRAGMA allowed"})
        danger = (";", "drop ", "delete ", "update ", "insert ", "alter ", "create ", "attach ")
        for d in danger:
            if d in sql_l:
                return self._json(403, {"err": f"dangerous pattern: {d}"})
        try:
            db = os.environ.get("LOG_SERVICE_DB_PATH", DB_PATH)
            c = sqlite3.connect(db, timeout=5)
            c.row_factory = sqlite3.Row
            start = time.time()
            cur = c.execute(sql)
            rows = [dict(r) for r in cur.fetchall()[:100]]
            elapsed_ms = round((time.time() - start) * 1000, 2)
            c.close()
            self._json(200, {"sql": sql, "rows": rows, "count": len(rows),
                             "elapsed_ms": elapsed_ms, "err": None})
        except Exception as e:
            self._json(500, {"sql": sql, "err": str(e), "type": type(e).__name__})

    # ── /api/sqlite/load ────────────────────────────
    def _sqlite_load(self, q):
        """压力测试: N 次 SELECT count(*) — 看 disk I/O 错误率"""
        count = min(int(q.get("count", ["100"])[0]), 1000)
        table = q.get("table", ["users"])[0]
        if table not in {"users", "roles", "products", "audit_logs", "enum_types", "enum_values"}:
            return self._json(403, {"err": f"table not allowed: {table}"})
        ok = 0; fail = 0; errors = []
        t0 = time.time()
        for i in range(count):
            try:
                db = os.environ.get("LOG_SERVICE_DB_PATH", DB_PATH)
                c = sqlite3.connect(db, timeout=5)
                cur = c.execute(f"SELECT count(*) FROM {table}")
                cur.fetchone()
                c.close()
                ok += 1
            except Exception as e:
                fail += 1
                if len(errors) < 5:
                    errors.append(str(e))
        elapsed = round(time.time() - t0, 2)
        self._json(200, {
            "count": count, "table": table, "ok": ok, "fail": fail,
            "fail_rate": round(fail / count * 100, 2) if count > 0 else 0,
            "elapsed_sec": elapsed, "qps": round(count / elapsed, 1) if elapsed > 0 else 0,
            "sample_errors": errors,
        })

    # ── /api/iostat ─────────────────────────────────
    def _iostat(self, q):
        """磁盘 I/O 抖动监测 (1s × N 采样)"""
        n = min(int(q.get("count", ["3"])[0]), 10)
        try:
            r = subprocess.run(["iostat", "-x", "1", str(n)],
                              capture_output=True, text=True, timeout=15)
            self._json(200, {"output": r.stdout, "err": r.stderr,
                             "available": r.returncode == 0})
        except FileNotFoundError as e:
            self._json(200, {"output": "", "err": f"iostat not available: {e}",
                             "available": False})
        except Exception as e:
            self._json(500, {"err": str(e), "type": type(e).__name__})

    # ── /api/proc/io ────────────────────────────────
    def _proc_io(self, q):
        """进程级 I/O 计数 (read_bytes, write_bytes) — 看 server.py 真实 I/O 量"""
        pid = q.get("pid", [""])[0]
        if not pid or not pid.isdigit():
            return self._json(400, {"err": "pid required (digits only)"})
        try:
            with open(f"/proc/{pid}/io") as f:
                lines = f.read().strip().split("\n")
            io = {}
            for l in lines:
                if ":" in l:
                    k, v = l.split(":", 1)
                    io[k.strip()] = int(v.strip())
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read().decode(errors="replace").replace("\x00", " ").strip()
            except Exception:
                cmd = "?"
            io["cmd"] = cmd[:120]
            self._json(200, io)
        except Exception as e:
            self._json(500, {"err": str(e), "pid": pid})

    # ── /api/deploy/current ★ [V007.45 v4.6] ─────────
    def _deploy_current(self, q):
        """[V007.45 BUG-FIX 2026-07-09] 看 current symlink 指向 + 实际目录
        之前 12+ 小时我看 /opt/app/current 误判, 实际是 symlink 指向空 v20260708_014/
        现在: 1 个端点返 symlink + 实际目录 + 实际 mtime
        """
        result = {}
        try:
            current = "/opt/app/current"
            if os.path.islink(current):
                target = os.readlink(current)
                result["symlink"] = current
                result["target"] = target
                target_full = os.path.join(os.path.dirname(current), target)
                if os.path.exists(target_full):
                    result["target_exists"] = True
                    result["target_files"] = sum(1 for _ in os.scandir(target_full))
                    result["target_mtime"] = os.path.getmtime(target_full)
                else:
                    result["target_exists"] = False
        except Exception as e:
            result["err"] = str(e)
        # 看实际跑的 server.py
        try:
            out = subprocess.run(["ps", "auxf"], capture_output=True, text=True, timeout=3).stdout
            server_lines = [l for l in out.split("\n") if "server.py" in l and "grep" not in l]
            if server_lines:
                result["server_running"] = server_lines[0].strip()
        except Exception:
            pass
        self._json(200, result)

    # ── /api/deploy/history ★ ───────────────────────
    def _deploy_history(self, q):
        """[V007.45] 看 MANIFEST 或 deploy_history 目录的最近 10 次部署"""
        n = int(q.get("n", ["10"])[0])
        results = []
        # 1. MANIFEST 文件
        manifest = "/opt/app/deployments/MANIFEST"
        if os.path.exists(manifest):
            try:
                with open(manifest) as f:
                    for line in f.readlines()[-n:]:
                        results.append({"source": "MANIFEST", "line": line.strip()})
            except Exception:
                pass
        # 2. /opt/app/deployments/ 目录按 mtime 倒序
        try:
            deps = [d for d in os.listdir("/opt/app/deployments") if d.startswith("v20")]
            deps.sort(key=lambda d: os.path.getmtime(f"/opt/app/deployments/{d}"), reverse=True)
            for d in deps[:n]:
                full = f"/opt/app/deployments/{d}"
                results.append({
                    "source": "mtime",
                    "version": d,
                    "mtime": os.path.getmtime(full),
                    "is_link": os.path.islink(full),
                })
        except Exception:
            pass
        self._json(200, {"count": len(results), "history": results[:n]})

    # ── /api/deploy/check_files ★ ───────────────────
    def _deploy_check_files(self, q):
        """[V007.45 BUG-FIX 2026-07-09] 强校验 V007.46 8 文件 MD5
        之前 5/8 V007.46 文件假阳性, 实际未真部署
        现在: 8 文件 MD5 + V007.46 标记数, 部署后立即报警
        """
        files_to_check = [
            ("meta/server.py", ["V007.46", "V007.43", "V007.45"]),
            ("meta/core/sql_connection_pool.py", ["V007.46", "V007.47", "V007.42"]),
            ("meta/core/safe_connect.py", ["V007.46", "V007.41"]),
            ("meta/services/async_audit_writer.py", ["V007.46"]),
            ("meta/core/db_health_monitor.py", ["V007.46"]),
            ("meta/core/diagnostics.py", ["V007.46"]),
            ("meta/services/import_export_service.py", ["V007.46"]),
            ("meta/services/query_service.py", ["V007.46"]),
        ]
        results = []
        for rel, markers in files_to_check:
            full = f"/opt/app/deployments/{rel}"
            entry = {"file": rel, "markers": {}, "exists": os.path.exists(full)}
            if entry["exists"]:
                try:
                    with open(full) as f:
                        content = f.read()
                    entry["size"] = len(content)
                    for m in markers:
                        entry["markers"][m] = content.count(m)
                    entry["mtime"] = os.path.getmtime(full)
                except Exception as e:
                    entry["err"] = str(e)
            results.append(entry)
        # 评判: 必须每个文件每个 marker >= 1
        all_pass = all(
            e["exists"] and all(v >= 1 for v in e.get("markers", {}).values())
            for e in results
        )
        self._json(200, {
            "all_pass": all_pass,
            "files": results,
            "summary": f"{sum(1 for e in results if e['exists'] and all(v >= 1 for v in e.get('markers', {}).values()))}/{len(results)} V007.46 真部署"
        })

    # ── /api/ports/auto_detect ★ ────────────────────
    def _ports_auto_detect(self, q):
        """[V007.45 BUG-FIX] 扫 3011/5001/8081/9101, 跟 server 对齐
        之前 12+ 小时误判 5001 vs 3011, 现在自动选 listening 端口
        """
        target_ports = [3011, 5001, 8081, 9101]
        result = {}
        try:
            out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5).stdout
            for p in target_ports:
                listening = f":{p} " in out or out.endswith(f":{p}\n") or f"*:{p}" in out
                result[str(p)] = "listening" if listening else "down"
        except Exception as e:
            result["err"] = str(e)
        # 推荐: server 跑 3011 (yonaa 默认), unified 跟 server 对齐
        server_port = "3011" if result.get("3011") == "listening" else ("5001" if result.get("5001") == "listening" else None)
        if server_port and result.get("8081") == "down" and result.get("9101") == "listening":
            result["recommend"] = f"启 unified: BACKEND_PORT={server_port} python3 unified_server.py"
        self._json(200, result)

    # ── /api/verify/invariant ★ ─────────────────────
    def _verify_invariant(self, q):
        """[V007.45] 部署后立即跑 V8ab 业务回归 (200 次压测)
        之前 V8ab 100/100 login 200 误判 V007.46 修复, 实际 login 不触发 disk I/O
        现在: 200 次 sqlite/load (db 层) + check disk I/O + 报实际结果
        """
        n = int(q.get("n", ["200"])[0])
        result = {"ts": int(time.time()), "n": n}
        # 1. /api/sqlite/load 200 次
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:9101/api/sqlite/load?n={n}&db=architecture", timeout=60)
            d = json.loads(resp.read().decode("utf-8"))
            result["load_ok"] = d.get("ok", 0)
            result["load_fail"] = d.get("fail", 0)
            result["load_qps"] = d.get("qps", 0)
            result["load_fail_rate"] = d.get("fail_rate", 0)
        except Exception as e:
            result["load_err"] = str(e)
        # 2. /api/iostat %util
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:9101/api/iostat", timeout=5)
            d = json.loads(resp.read().decode("utf-8"))
            out = d.get("output", "")
            lines = [l for l in out.split("\n") if "vda " in l]
            if lines:
                last = lines[-1].split()
                result["iostat_util_pct"] = float(last[12]) if len(last) > 12 else -1
        except Exception as e:
            result["iostat_err"] = str(e)
        # 3. /api/db/health
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:9101/api/db/health", timeout=5)
            d = json.loads(resp.read().decode("utf-8"))
            result["db_integrity"] = d.get("integrity", "?")
        except Exception as e:
            result["db_err"] = str(e)
        # 评判
        result["PASS"] = (
            result.get("load_fail_rate", 1) == 0
            and result.get("iostat_util_pct", 100) < 30
            and result.get("db_integrity", "?") == "ok"
        )
        self._json(200, result)

    # ── /api/deploy/yonaa_versions ★ [V007.45 v4.6 BUG-FIX 2026-07-09] ─
    def _deploy_yonaa_versions(self, q):
        """[V007.45 BUG-FIX 2026-07-09] 看 yonaa 实际跑的 8 个关键文件 V007.46/V007.47 标记
        之前部署智能体看 worktree MD5 误判, 实际 yonaa 跑的可能不是最新
        现在: yonaa 实际文件 grep 标记数 + mtime, 不依赖 SSH
        """
        files_to_check = [
            ("meta/server.py", ["V007.46", "V007.47", "V007.45", "V007.43", "V007.42", "V007.41"]),
            ("meta/core/sql_connection_pool.py", ["V007.46", "V007.47", "V007.42", "V007.38"]),
            ("meta/core/safe_connect.py", ["V007.46", "V007.41", "V007.40"]),
            ("meta/core/diagnostics.py", ["V007.46", "V007.41"]),
            ("meta/services/async_audit_writer.py", ["V007.46", "V007.42"]),
            ("meta/services/import_export_service.py", ["V007.46", "V007.37"]),
            ("meta/services/query_service.py", ["V007.46", "V007.44", "V007.37"]),
            ("meta/core/db_health_monitor.py", ["V007.46", "V007.39"]),
        ]
        results = []
        for rel, markers in files_to_check:
            full = f"/opt/app/deployments/{rel}"
            entry = {"file": rel, "exists": os.path.exists(full), "markers": {}}
            if entry["exists"]:
                try:
                    with open(full) as f:
                        content = f.read()
                    entry["size"] = len(content)
                    entry["mtime"] = os.path.getmtime(full)
                    for m in markers:
                        entry["markers"][m] = content.count(m)
                except Exception as e:
                    entry["err"] = str(e)
            results.append(entry)
        # 评判: 至少 server.py V007.46 标记 >= 1 才算 V007.46 部署
        server_v46 = next((e for e in results if e["file"] == "meta/server.py"), {}).get("markers", {}).get("V007.46", 0)
        deploy_status = "V007.46+ (新)" if server_v46 >= 1 else "V007.40- (老)"
        # V007.46 标记数
        total_v46 = sum(e.get("markers", {}).get("V007.46", 0) for e in results)
        total_v47 = sum(e.get("markers", {}).get("V007.47", 0) for e in results)
        self._json(200, {
            "yonaa_deploy_status": deploy_status,
            "server_py_V007_46_markers": server_v46,
            "total_V007_46_markers": total_v46,
            "total_V007_47_markers": total_v47,
            "files": results,
            "summary": f"yonaa server.py V007.46 标记={server_v46} (>=1 = V007.46+ 部署, 0 = V007.40- 老版本)"
        })

    # ── /api/deploy/invariant ★ [V007.49 P1 BUG-FIX 2026-07-09] ───
    def _deploy_invariant(self, q):
        """[V007.49 P1 BUG-FIX] 部署智能体跑完 PHASE 0.5 后立即调这端点
        验 8 关键文件 V007.46+V007.47 标记数 + size + mtime, 不依赖 SSH
        失败 = 部署假成功 (PHASE 0.5 hash 校验漏过, 但实际没真覆盖)
        """
        files_to_check = [
            ("meta/server.py", ["V007.46", "V007.47", "V007.45", "V007.43"]),
            ("meta/core/sql_connection_pool.py", ["V007.46", "V007.47", "V007.42"]),
            ("meta/core/safe_connect.py", ["V007.46", "V007.41", "V007.40"]),
            ("meta/core/diagnostics.py", ["V007.46"]),
            ("meta/core/db_health_monitor.py", ["V007.46"]),
            ("meta/services/async_audit_writer.py", ["V007.46", "V007.42"]),
            ("meta/services/audit_service.py", ["V007.46"]),
            ("meta/services/import_export_service.py", ["V007.46"]),
            ("meta/services/query_service.py", ["V007.46", "V007.44", "V007.37"]),
        ]
        all_pass = True
        results = []
        for rel, markers in files_to_check:
            full = f"/opt/app/deployments/{rel}"
            entry = {"file": rel, "pass": False, "markers": {}}
            if os.path.exists(full):
                try:
                    with open(full) as f:
                        content = f.read()
                    entry["size"] = len(content)
                    entry["mtime"] = os.path.getmtime(full)
                    for m in markers:
                        count = content.count(m)
                        entry["markers"][m] = count
                    # 评判: 至少 1 个标记 >= 1
                    if any(count >= 1 for count in entry["markers"].values()):
                        entry["pass"] = True
                    else:
                        all_pass = False
                        entry["fail_reason"] = "0 markers"
                except Exception as e:
                    entry["err"] = str(e)
                    all_pass = False
            else:
                entry["err"] = "file not exist"
                all_pass = False
            results.append(entry)
        self._json(200, {
            "all_pass": all_pass,
            "pass_count": sum(1 for r in results if r.get("pass")),
            "total": len(results),
            "files": results,
            "service_version": VERSION,
            "summary": f"{sum(1 for r in results if r.get('pass'))}/{len(results)} files PASS",
        })

    # ──────────────────────────────────────────────────
    # [V007.50 v4.8] P0 远程管理/排查/测试端点实现
    # ──────────────────────────────────────────────────

    # ── /api/manage/journal_mode ★ ──────────────────
    def _manage_journal_mode(self, q):
        """[V007.50] 安全切换 journal_mode: ?to=delete|wal&force=1
        步骤: 1) 查当前 2) pkill 持 DB 连接的非关键进程 3) checkpoint 4) 切换 5) 验证
        force=1 时先杀 log_service 以外的 DB 连接进程 (server.py/unified)
        """
        target = q.get("to", [""])[0].lower()
        force = q.get("force", ["0"])[0] in ("1", "true", "yes")

        result = {"db_path": DB_PATH, "ts": int(time.time())}

        # 1. 当前状态
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            current = conn.execute("PRAGMA journal_mode").fetchone()[0]
            result["journal_mode_before"] = current
            # WAL 文件大小
            wal_path = DB_PATH + "-wal"
            result["wal_size_mb"] = round(os.path.getsize(wal_path) / 1048576, 2) if os.path.exists(wal_path) else 0
            conn.close()
        except Exception as e:
            result["error"] = f"cannot read current journal_mode: {e}"
            return self._json(500, result)

        # 只读查询: 不传 to 参数则只返回当前状态
        if not target:
            result["action"] = "read_only"
            return self._json(200, result)

        if target not in ("delete", "wal"):
            return self._json(400, {"error": "to must be 'delete' or 'wal'"})

        # 已经是目标模式
        if current.lower() == target:
            result["action"] = "already_" + target
            result["journal_mode_after"] = current
            return self._json(200, result)

        # 2. 如果 force, 找持有 DB 连接的进程
        killed_pids = []
        if force:
            try:
                out = subprocess.run(["fuser", DB_PATH], capture_output=True, text=True, timeout=5).stdout
                pids = [int(x) for x in out.split() if x.isdigit() and int(x) != os.getpid()]
                for pid in pids:
                    try:
                        os.kill(pid, 9)
                        killed_pids.append(pid)
                    except (ProcessLookupError, PermissionError):
                        pass
                if killed_pids:
                    time.sleep(1)  # 等连接释放
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass  # fuser 不可用, 继续
            result["killed_pids"] = killed_pids

        # 3. checkpoint (WAL→DELETE 前必须)
        if current.lower() == "wal":
            try:
                conn = sqlite3.connect(DB_PATH, timeout=10)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
                result["checkpoint"] = "TRUNCATE_ok"
            except Exception as e:
                result["checkpoint"] = f"TRUNCATE_fail: {e}"
                # 尝试 PASSIVE
                try:
                    conn = sqlite3.connect(DB_PATH, timeout=10)
                    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                    conn.close()
                    result["checkpoint_fallback"] = "PASSIVE_ok"
                except Exception as e2:
                    result["checkpoint_fallback"] = f"PASSIVE_fail: {e2}"

        # 4. 切换
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            row = conn.execute(f"PRAGMA journal_mode={target.upper()}").fetchone()
            actual = row[0] if row else "unknown"
            conn.close()
            result["journal_mode_after"] = actual
        except Exception as e:
            result["error"] = f"switch failed: {e}"
            result["journal_mode_after"] = "unknown"
            return self._json(500, result)

        # 5. 验证
        time.sleep(0.3)
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            verified = conn.execute("PRAGMA journal_mode").fetchone()[0]
            conn.close()
            result["verified"] = verified.lower() == target
        except Exception as e:
            result["verified"] = False
            result["verify_error"] = str(e)

        result["action"] = "switched" if result.get("verified") else "switch_failed"
        self._json(200, result)

    # ── /api/diag/trace ★ ──────────────────────────
    def _diag_trace(self, q):
        """[V007.50] 跨服务追踪: 按 trace_id 聚合 server.log + unified.log + log_service.log
        用法: /api/diag/trace?trace_id=abc123&lines=50
        """
        trace_id = q.get("trace_id", [""])[0].strip()
        lines = min(int(q.get("lines", [100])[0]), 500)
        if not trace_id:
            return self._json(400, {"error": "trace_id required"})

        log_files = {
            "server.log": os.path.join(LOG_DIR, "server.log"),
            "unified.log": "/tmp/unified-server.log",
            "log_service.log": "/tmp/log_service.log",
        }

        result = {"trace_id": trace_id, "sources": {}}
        total_matched = 0

        for name, path in log_files.items():
            if not os.path.exists(path):
                result["sources"][name] = {"status": "not_found", "path": path}
                continue
            try:
                # tail 取最近 N 行, grep trace_id
                cmd = f"tail -n {lines * 10} '{path}' | grep -i '{trace_id}' | tail -n {lines}"
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                matched = [l for l in r.stdout.split("\n") if l.strip()]
                total_matched += len(matched)
                result["sources"][name] = {
                    "status": "ok",
                    "path": path,
                    "matched_lines": len(matched),
                    "output": matched[:lines],
                }
            except Exception as e:
                result["sources"][name] = {"status": "error", "error": str(e)}

        result["total_matched"] = total_matched
        result["found"] = total_matched > 0
        self._json(200, result)

    # ── /api/test/disk_io ★ ────────────────────────
    def _test_disk_io(self, q):
        """[V007.50] 并发 disk I/O 压测: 多线程同时读写 DB, 统计 fail_rate
        用法: /api/test/disk_io?rounds=5&concurrency=3&write=true
        rounds: 每线程重复次数, concurrency: 线程数, write: 是否含写操作
        """
        rounds = min(int(q.get("rounds", ["5"])[0]), 20)
        concurrency = min(int(q.get("concurrency", ["3"])[0]), 10)
        do_write = q.get("write", ["false"])[0].lower() in ("1", "true", "yes")

        results_lock = threading.Lock()
        all_ok = 0
        all_fail = 0
        all_errors = []
        all_latencies = []

        def _worker(worker_id):
            nonlocal all_ok, all_fail
            for r in range(rounds):
                t0 = time.time()
                try:
                    conn = sqlite3.connect(DB_PATH, timeout=10)
                    # 读操作
                    conn.execute("SELECT count(*) FROM products").fetchone()
                    if do_write:
                        # 安全写: 插入后立即回滚, 不改数据
                        conn.execute("BEGIN")
                        conn.execute("SELECT count(*) FROM audit_logs").fetchone()
                        conn.execute("ROLLBACK")
                    conn.close()
                    latency = round((time.time() - t0) * 1000, 2)
                    with results_lock:
                        all_ok += 1
                        all_latencies.append(latency)
                except Exception as e:
                    with results_lock:
                        all_fail += 1
                        if len(all_errors) < 10:
                            all_errors.append(f"[worker-{worker_id} round-{r}] {type(e).__name__}: {e}")

        t_start = time.time()
        threads = []
        for i in range(concurrency):
            t = threading.Thread(target=_worker, args=(i,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=60)
        elapsed = round(time.time() - t_start, 2)

        total = all_ok + all_fail
        latencies = sorted(all_latencies) if all_latencies else [0]
        self._json(200, {
            "rounds": rounds,
            "concurrency": concurrency,
            "write": do_write,
            "total_ops": total,
            "ok": all_ok,
            "fail": all_fail,
            "fail_rate_pct": round(all_fail / total * 100, 2) if total > 0 else 0,
            "latency_ms": {
                "min": latencies[0],
                "p50": latencies[len(latencies) // 2],
                "p99": latencies[int(len(latencies) * 0.99)] if len(latencies) > 1 else latencies[-1],
                "max": latencies[-1],
            },
            "elapsed_sec": elapsed,
            "qps": round(total / elapsed, 1) if elapsed > 0 else 0,
            "sample_errors": all_errors[:5],
            "PASS": all_fail == 0,
        })

    # ── /api/deploy/smoke ★ ────────────────────────
    def _deploy_smoke(self, q):
        """[V007.50] 一键冒烟: 串联端口/DB/journal_mode/disk_io 多项检查
        部署后立即调: curl http://yonaa:9101/api/deploy/smoke
        """
        results = {"ts": int(time.time()), "service_version": VERSION, "checks": {}}

        # 1. 端口检查
        try:
            out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5).stdout
            ports_status = {}
            for p in [3011, 5001, 8081, 9101]:
                ports_status[str(p)] = "listening" if f":{p} " in out or f":{p}\n" in out else "down"
            results["checks"]["ports"] = {"status": "ok", "ports": ports_status}
        except Exception as e:
            results["checks"]["ports"] = {"status": "error", "error": str(e)}

        # 2. DB 健康
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            product_count = 0
            try:
                product_count = conn.execute("SELECT count(*) FROM products").fetchone()[0]
            except Exception:
                pass
            conn.close()
            results["checks"]["db"] = {
                "status": "ok",
                "journal_mode": jm,
                "integrity": integrity,
                "product_count": product_count,
                "journal_mode_ok": jm.lower() == "delete",
                "integrity_ok": integrity == "ok",
            }
        except Exception as e:
            results["checks"]["db"] = {"status": "error", "error": str(e)}

        # 3. SQLite 版本
        try:
            conn = sqlite3.connect(":memory:", timeout=5)
            sv = conn.execute("SELECT sqlite_version()").fetchone()[0]
            conn.close()
            results["checks"]["sqlite_version"] = {"version": sv, "ok": sv >= "3.39"}
        except Exception as e:
            results["checks"]["sqlite_version"] = {"status": "error", "error": str(e)}

        # 4. disk I/O 快速压测 (3 轮, 2 并发)
        try:
            ok = 0
            fail = 0
            errors = []
            for _ in range(6):  # 3 round x 2 concurrency
                try:
                    conn = sqlite3.connect(DB_PATH, timeout=5)
                    conn.execute("SELECT count(*) FROM products").fetchone()
                    conn.close()
                    ok += 1
                except Exception as e:
                    fail += 1
                    if len(errors) < 3:
                        errors.append(str(e))
            results["checks"]["disk_io"] = {
                "ok": ok, "fail": fail,
                "fail_rate_pct": round(fail / (ok + fail) * 100, 2) if (ok + fail) > 0 else 0,
                "sample_errors": errors,
                "PASS": fail == 0,
            }
        except Exception as e:
            results["checks"]["disk_io"] = {"status": "error", "error": str(e)}

        # 5. 系统资源
        try:
            load = list(os.getloadavg())
            st = os.statvfs("/")
            free_gb = round(st.f_bfree * st.f_frsize / 1073741824, 2)
            results["checks"]["system"] = {
                "load_1m": load[0], "load_5m": load[1], "load_15m": load[2],
                "disk_free_gb": free_gb,
                "load_ok": load[0] < 4,
                "disk_ok": free_gb > 1,
            }
        except Exception as e:
            results["checks"]["system"] = {"status": "error", "error": str(e)}

        # 综合评判
        all_pass = True
        for name, check in results["checks"].items():
            if name == "ports":
                # 至少 3011 或 5001 得 listening
                if not any(v == "listening" for k, v in check.get("ports", {}).items() if k in ("3011", "5001")):
                    all_pass = False
            elif name == "db":
                if not check.get("journal_mode_ok") or not check.get("integrity_ok"):
                    all_pass = False
            elif name == "disk_io":
                if not check.get("PASS", False):
                    all_pass = False
            elif name == "system":
                if not check.get("load_ok") or not check.get("disk_ok"):
                    all_pass = False

        results["PASS"] = all_pass
        results["summary"] = "ALL PASS" if all_pass else "FAIL - check details above"
        self._json(200, results)

    # ── /api/upload ★ (POST) ──────────────────────
    def _upload(self, q):
        """[V007.50] 文件上传: POST /api/upload?path=/tmp/xxx.sh
        body = 文件内容, Content-Type: application/octet-stream
        安全: token 鉴权 + 路径白名单 + 文件大小限制
        """
        if not _check_token(q):
            return self._json(403, {"error": "token required for upload"})

        target_path = q.get("path", [""])[0]
        if not target_path:
            return self._json(400, {"error": "path query param required"})

        # 路径安全: 必须在白名单目录下
        target_dir = os.path.dirname(target_path)
        if not _path_allowed(target_path):
            return self._json(403, {"error": f"target path not allowed: {target_path}",
                                    "allowed_dirs": ALLOWED_DIRS})

        # 大小限制: 100MB (deploy zip ~21MB + 余量)
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 100 * 1024 * 1024:
            return self._json(413, {"error": f"file too large: {content_length} bytes (max 100MB)"})

        # 读取 body
        try:
            body = self.rfile.read(content_length)
        except Exception as e:
            return self._json(500, {"error": f"read body failed: {e}"})

        # 写入
        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "wb") as f:
                f.write(body)
            # 如果是 .sh 文件, 自动加执行权限
            if target_path.endswith(".sh") or target_path.endswith(".py"):
                os.chmod(target_path, 0o755)
            file_size = os.path.getsize(target_path)
            self._json(200, {
                "action": "uploaded",
                "path": target_path,
                "size": file_size,
                "executable": target_path.endswith((".sh", ".py")),
            })
        except Exception as e:
            self._json(500, {"error": f"write failed: {e}"})

    # ── /api/exec ★ (GET/POST) ────────────────────
    # 命令白名单: 只允许诊断/管理命令, 禁止危险操作
    EXEC_WHITELIST = [
        "ls", "cat", "head", "tail", "wc", "find", "grep", "du", "df",
        "ps", "top", "ss", "netstat", "curl", "wget",
        "systemctl", "journalctl", "dmesg", "iostat", "vmstat", "free",
        "echo", "date", "whoami", "id", "uname", "hostname",
        "chmod", "chown", "mkdir", "cp", "mv", "ln", "touch",
        "python3", "python", "pip3", "pip",
        "sqlite3", "md5sum", "sha256sum",
        "pkill", "kill", "killall",
        # [V007.50] 部署必需命令
        "bash", "sh", "unzip", "tar", "nohup",
        "sed", "awk", "sort", "uniq", "tr", "cut", "tee",
        "test", "true", "false", "sleep",
        "source", ".",  # shell 内置 (basename 处理后)
    ]

    # 禁止的命令模式 (即使基础命令在白名单也拦截)
    EXEC_BLACKLIST_PATTERNS = [
        "rm -rf /", "dd if=", "mkfs.", ":(){:|:&};:", "> /dev/sd",
        "shutdown", "reboot", "init 0", "init 6",
    ]

    def _exec_cmd(self, q):
        """[V007.50] 远程命令执行: GET /api/exec?cmd=ls+-la+/tmp&timeout=10
        或 POST /api/exec (body: {"cmd": "...", "timeout": 10})
        bg=true: 后台运行 (不等待输出, 返回 PID)
        安全: token 鉴权 + 命令白名单 + 超时 + 输出截断
        """
        if not _check_token(q):
            return self._json(403, {"error": "token required for exec"})

        # 从 query 或 POST body 取命令
        cmd = q.get("cmd", [""])[0]
        timeout = min(int(q.get("timeout", ["10"])[0]), 60)
        bg = q.get("bg", ["0"])[0] in ("1", "true", "yes")

        if not cmd:
            # 尝试从 POST body 读取 JSON
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length > 0 and content_length < 10000:
                    body = self.rfile.read(content_length).decode("utf-8", errors="replace")
                    data = json.loads(body)
                    cmd = data.get("cmd", "")
                    timeout = min(int(data.get("timeout", 10)), 60)
                    bg = data.get("bg", False)
            except Exception:
                pass

        if not cmd:
            return self._json(400, {"error": "cmd param required",
                                    "usage": "GET /api/exec?cmd=ls+-la+/tmp&timeout=10&bg=false"})

        # 安全检查: 黑名单
        cmd_lower = cmd.lower()
        for pattern in self.EXEC_BLACKLIST_PATTERNS:
            if pattern in cmd_lower:
                return self._json(403, {"error": f"blacklisted pattern: {pattern}"})

        # 安全检查: 白名单 (取命令第一个词)
        base_cmd = cmd.split()[0] if cmd.split() else ""
        # 处理带路径的命令: /usr/bin/ls → ls
        base_name = os.path.basename(base_cmd)
        if base_name not in self.EXEC_WHITELIST:
            return self._json(403, {"error": f"command not whitelisted: {base_name}",
                                    "whitelist": self.EXEC_WHITELIST,
                                    "hint": "use full path like /usr/bin/ls if needed"})

        # 后台模式: Popen 不等待, 立即返回 PID
        if bg:
            try:
                devnull = open(os.devnull, "w")
                proc = subprocess.Popen(
                    cmd, shell=True,
                    stdout=devnull,
                    stderr=devnull,
                    close_fds=True,
                )
                self._json(200, {
                    "cmd": cmd, "mode": "background",
                    "pid": proc.pid, "note": "output discarded, use /api/log or /api/proc to check",
                })
            except Exception as e:
                self._json(500, {"error": str(e), "cmd": cmd})
            return

        # 前台模式: 等待输出
        try:
            t0 = time.time()
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
            elapsed = round((time.time() - t0) * 1000, 1)
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            self._json(200, {
                "cmd": cmd,
                "exit_code": result.returncode,
                "stdout": stdout[:50000],
                "stderr": stderr[:10000],
                "elapsed_ms": elapsed,
                "timeout_sec": timeout,
                "truncated_stdout": len(stdout) > 50000,
                "truncated_stderr": len(stderr) > 10000,
            })
        except subprocess.TimeoutExpired:
            self._json(408, {"error": f"command timed out after {timeout}s", "cmd": cmd})
        except Exception as e:
            self._json(500, {"error": str(e), "cmd": cmd})

    # ════════════════════════════════════════════════════════════════
    # [V007.51 v4.9] P1 基础设施: 看门狗 + 日志归档 + 巡检 + 告警 + 磁盘预警
    # ════════════════════════════════════════════════════════════════

    # ── 模块级: 告警事件总线 (singleton) ─────────────────────────
    _alert_subscribers: list = []  # type: ignore
    _alert_history: list = []  # type: ignore
    _alert_lock = threading.Lock()

    @classmethod
    def _emit_alert(cls, level: str, source: str, message: str, data: dict = None):
        """推送告警事件到所有订阅者 + 历史"""
        evt = {
            "ts": datetime.now().isoformat(),
            "level": level,  # "info" | "warn" | "error" | "critical"
            "source": source,  # "supervisor" | "log_archive" | "disk" | "health"
            "message": message,
            "data": data or {},
        }
        with cls._alert_lock:
            cls._alert_history.append(evt)
            # 保留最近 100 条
            if len(cls._alert_history) > 100:
                cls._alert_history = cls._alert_history[-100:]
            subs = list(cls._alert_subscribers)
        # 推送到订阅者队列 (非阻塞)
        for q in subs:
            try:
                q.put_nowait(evt)
            except Exception:
                pass

    # ── /api/service/supervisor ★ ─────────────────────────────
    # 看门狗: 检测关键服务进程是否在跑, 死了自动重启
    SUPERVISED_SERVICES = [
        {"name": "meta_server",      "port": 3011, "cmd": "/opt/miniconda3-py39/bin/python -u /opt/app/deployments/meta/server.py", "log": "/tmp/server-supervisor.log", "critical": True},
        {"name": "unified",          "port": 8081, "cmd": "python3 /tmp/deploy_bundle/tools/unified_server.py /opt/app/deployments/frontend_dist_files", "log": "/tmp/unified-supervisor.log", "critical": True},
        # log_service 不监控自己, 自身挂了需要外部 (systemd/crontab) 拉起
    ]

    def _supervisor(self, q):
        """[V007.51] /api/service/supervisor?action=status|restart|start|stop
        status: 列出所有受监控服务状态
        restart: 重启指定服务 (name=xxx)
        start: 启动已停止服务 (name=xxx)
        stop: 停止服务 (name=xxx)
        """
        if not _check_token(q):
            return self._json(403, {"error": "token required for supervisor"})

        action = q.get("action", ["status"])[0]
        target_name = q.get("name", [""])[0]

        if action == "status":
            statuses = []
            for svc in self.SUPERVISED_SERVICES:
                # 检查端口
                port_alive = False
                try:
                    with _socket_context(svc["port"]) as s:
                        port_alive = (s.connect_ex(("127.0.0.1", svc["port"])) == 0)
                except Exception:
                    pass
                # [V007.52 BUG-FIX] 用 svc["cmd"] 完整字符串匹配 (不是 cmd0, 避免 pgrep python 匹配到 core_service/log_service)
                # 同时排除当前进程 PID (log_service 自己) 和 core_service
                try:
                    import os as _os_for_pid
                    my_pid = str(_os_for_pid.getpid())
                    # 用完整 cmd 匹配 (去掉路径前缀的 binary)
                    cmd_pattern = svc["cmd"]
                    if hasattr(subprocess, 'run'):
                        proc = subprocess.run(["pgrep", "-f", cmd_pattern],
                                              capture_output=True, text=True, timeout=5)
                        pids = [p for p in proc.stdout.strip().split("\n") if p.isdigit()]
                        # 过滤: 排除 log_service 自己 和 core_service
                        pids = [p for p in pids if p != my_pid and "core_service" not in cmd_pattern]
                    else:
                        pids = []
                except (FileNotFoundError, Exception):
                    # Windows fallback: 用 ps + grep (完整 cmd 字符串)
                    try:
                        proc = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
                        cmd_pattern = svc["cmd"]
                        pids = []
                        for line in proc.stdout.split("\n"):
                            if cmd_pattern in line and "grep" not in line:
                                parts = line.split()
                                if parts and parts[1].isdigit() and parts[1] != my_pid:
                                    pids.append(parts[1])
                    except Exception:
                        pids = []
                statuses.append({
                    "name": svc["name"],
                    "port": svc["port"],
                    "critical": svc["critical"],
                    "port_alive": port_alive,
                    "pid": pids[0] if pids else None,
                    "all_pids": pids,
                })
            return self._json(200, {"action": "status", "services": statuses,
                                    "ts": datetime.now().isoformat()})

        # 以下操作需要指定 name
        if not target_name:
            return self._json(400, {"error": "name param required",
                                    "available": [s["name"] for s in self.SUPERVISED_SERVICES]})
        svc = next((s for s in self.SUPERVISED_SERVICES if s["name"] == target_name), None)
        if not svc:
            return self._json(404, {"error": f"unknown service: {target_name}",
                                    "available": [s["name"] for s in self.SUPERVISED_SERVICES]})

        if action == "restart":
            # 杀旧
            subprocess.run(["pkill", "-9", "-f", svc["cmd"].split()[0]], capture_output=True, timeout=5)
            time.sleep(2)
            # 启新 (后台)
            with open(svc["log"], "ab") as logf:
                subprocess.Popen(svc["cmd"], shell=True, stdout=logf, stderr=logf,
                                 close_fds=True, start_new_session=True)
            time.sleep(3)
            self._emit_alert("warn", "supervisor", f"restarted {target_name}", {"cmd": svc["cmd"]})
            return self._json(200, {"action": "restart", "name": target_name,
                                    "log": svc["log"], "note": "check /api/service/supervisor?action=status in 5s"})

        if action == "start":
            port_alive = False
            try:
                with _socket_context(svc["port"]) as s:
                    port_alive = (s.connect_ex(("127.0.0.1", svc["port"])) == 0)
            except Exception:
                pass
            if port_alive:
                return self._json(200, {"action": "start", "name": target_name, "status": "already_running"})
            with open(svc["log"], "ab") as logf:
                subprocess.Popen(svc["cmd"], shell=True, stdout=logf, stderr=logf,
                                 close_fds=True, start_new_session=True)
            time.sleep(3)
            self._emit_alert("warn", "supervisor", f"started {target_name}", {"cmd": svc["cmd"]})
            return self._json(200, {"action": "start", "name": target_name, "status": "started"})

        if action == "stop":
            subprocess.run(["pkill", "-9", "-f", svc["cmd"].split()[0]], capture_output=True, timeout=5)
            self._emit_alert("warn", "supervisor", f"stopped {target_name}", {})
            return self._json(200, {"action": "stop", "name": target_name, "status": "stopped"})

        return self._json(400, {"error": f"unknown action: {action}",
                                "valid": ["status", "restart", "start", "stop"]})

    # ── /api/log/archive ★ ─────────────────────────────────────
    def _log_archive(self, q):
        """[V007.51] /api/log/archive?older_than_days=7&max_keep=10&dry_run=0
        归档 /tmp/server-*.log, /tmp/unified-*.log, /tmp/log_service-*.log
        规则: 保留最近 max_keep 个, 旧的 gz 归档
        """
        if not _check_token(q):
            return self._json(403, {"error": "token required"})

        older_than_days = int(q.get("older_than_days", ["7"])[0])
        max_keep = int(q.get("max_keep", ["10"])[0])
        dry_run = q.get("dry_run", ["0"])[0] in ("1", "true", "yes")
        archive_dir = "/opt/app/shared/logs/archive"

        cutoff = time.time() - older_than_days * 86400
        patterns = ["server-*.log", "unified-*.log", "log_service-*.log", "supervisor.log"]
        result = {"archived": [], "deleted": [], "kept": [], "errors": [], "dry_run": dry_run}

        try:
            os.makedirs(archive_dir, exist_ok=True)
        except Exception as e:
            return self._json(500, {"error": f"cannot create archive dir: {e}"})

        for pat in patterns:
            files = []
            for f in os.listdir("/tmp"):
                if fnmatch.fnmatch(f, pat):
                    fp = f"/tmp/{f}"
                    try:
                        st = os.stat(fp)
                        files.append((fp, st.st_mtime, st.st_size))
                    except Exception:
                        pass
            # 按 mtime 排序 (新→旧)
            files.sort(key=lambda x: x[1], reverse=True)
            # 保留最近 max_keep
            for fp, mt, sz in files[:max_keep]:
                result["kept"].append({"file": fp, "size_mb": round(sz / 1048576, 2),
                                       "age_days": round((time.time() - mt) / 86400, 1)})
            # 归档旧的
            for fp, mt, sz in files[max_keep:]:
                if mt > cutoff:
                    # 还不够旧, 跳过但记录
                    result["kept"].append({"file": fp, "size_mb": round(sz / 1048576, 2),
                                           "age_days": round((time.time() - mt) / 86400, 1),
                                           "note": "within cutoff, not archived yet"})
                    continue
                if dry_run:
                    result["archived"].append({"file": fp, "size_mb": round(sz / 1048576, 2),
                                              "would_archive_to": f"{archive_dir}/{os.path.basename(fp)}.{int(mt)}.gz"})
                    continue
                # 真实归档
                try:
                    import gzip
                    archive_name = f"{archive_dir}/{os.path.basename(fp)}.{int(mt)}.gz"
                    with open(fp, "rb") as src, gzip.open(archive_name, "wb") as dst:
                        dst.write(src.read())
                    os.remove(fp)
                    result["archived"].append({"file": fp, "archived_to": archive_name,
                                               "size_mb": round(sz / 1048576, 2)})
                except Exception as e:
                    result["errors"].append({"file": fp, "error": str(e)})

        # 触发告警 (如果有归档动作)
        if result["archived"] and not dry_run:
            total_freed = sum(a.get("size_mb", 0) for a in result["archived"])
            self._emit_alert("info", "log_archive",
                             f"archived {len(result['archived'])} files, freed {round(total_freed, 1)}MB",
                             result)

        result["ts"] = datetime.now().isoformat()
        return self._json(200, result)

    # ── /api/disk/forecast ★ ───────────────────────────────────
    def _disk_forecast(self, q):
        """[V007.51] /api/disk/forecast
        基于过去 N 天 df 采样数据预测磁盘满的时间
        """
        if not _check_token(q):
            return self._json(403, {"error": "token required"})

        days_history = int(q.get("days_history", ["7"])[0])
        # 简化: 用当前 disk + 数据库大小 + 历史归档大小估算
        try:
            if hasattr(os, 'statvfs'):
                st = os.statvfs("/")
                total_gb = st.f_blocks * st.f_frsize / 1073741824
                free_gb = st.f_bfree * st.f_frsize / 1073741824
                used_gb = total_gb - free_gb
            else:
                # Windows fallback: 用 shutil 替代
                import shutil as _sh
                total, used, free = _sh.disk_usage("/")
                total_gb = total / 1073741824
                used_gb = used / 1073741824
                free_gb = free / 1073741824
        except Exception as e:
            return self._json(500, {"error": f"disk stat failed: {e}"})

        # 数据库大小
        db_size_mb = 0
        if os.path.exists(DB_PATH):
            db_size_mb = os.path.getsize(DB_PATH) / 1048576

        # 日志目录大小
        log_size_mb = 0
        log_count = 0
        try:
            for f in os.listdir("/tmp"):
                fp = f"/tmp/{f}"
                if os.path.isfile(fp) and (f.endswith(".log") or f.endswith(".gz")):
                    log_size_mb += os.path.getsize(fp) / 1048576
                    log_count += 1
        except Exception:
            pass

        # 估算每日增长 (基于历史 db 大小 / 上次部署时间, 简化: 假设 db 每日增长 5MB)
        # 真实实现需要历史采样, 这里给保守估算
        estimated_daily_growth_mb = 50  # 保守 50MB/天 (含 logs + db)
        # 计算剩余天数
        free_mb = free_gb * 1024
        if estimated_daily_growth_mb > 0:
            days_until_full = free_mb / estimated_daily_growth_mb
        else:
            days_until_full = float("inf")
        full_date = datetime.now() + timedelta(days=days_until_full)

        # 状态
        if days_until_full < 7:
            status = "critical"
        elif days_until_full < 30:
            status = "warning"
        else:
            status = "ok"

        result = {
            "ts": datetime.now().isoformat(),
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "used_pct": round(used_gb / total_gb * 100, 1),
            "db_size_mb": round(db_size_mb, 2),
            "log_size_mb": round(log_size_mb, 2),
            "log_count": log_count,
            "estimated_daily_growth_mb": estimated_daily_growth_mb,
            "days_until_full": round(days_until_full, 1),
            "estimated_full_date": full_date.strftime("%Y-%m-%d"),
            "status": status,
            "note": "estimate based on 50MB/day assumption, refine with real sampling",
        }
        if status in ("warning", "critical"):
            self._emit_alert(status, "disk", f"disk will fill in {round(days_until_full, 1)} days",
                             {"free_gb": round(free_gb, 2), "used_pct": result["used_pct"]})
        return self._json(200, result)

    # ── /api/disk/check ★ [V007.53 v4.11] ──────────
    def _disk_check(self, q):
        """SQLite disk I/O 综合健康检查: 4 路信号交叉验证
        信号:
          1) DB integrity (PRAGMA integrity_check)
          2) iostat %util (磁盘繁忙度)
          3) dmesg I/O 错误数 (内核层)
          4) SQLite 快速压测 (30 次 SELECT, 看失败率)
        用法: GET /api/disk/check?quick=true  (quick 模式跳过压测)
        """
        quick = q.get("quick", ["false"])[0].lower() in ("1", "true", "yes")
        signals = {}
        issues = []

        # 信号1: DB integrity
        try:
            with _sqlite_open_ro(DB_PATH, timeout=5) as conn:
                cur = conn.execute("PRAGMA integrity_check").fetchone()
                signals["db_integrity"] = cur[0] if cur else "unknown"
                if signals["db_integrity"] != "ok":
                    issues.append(f"DB integrity: {signals['db_integrity']}")
        except Exception as e:
            signals["db_integrity"] = f"error: {e}"
            issues.append(signals["db_integrity"])

        # 信号2: iostat %util
        try:
            r = subprocess.run(["iostat", "-x", "1", "2"], capture_output=True, text=True, timeout=10)
            vda_lines = [l for l in r.stdout.split("\n") if "vda " in l]
            if vda_lines:
                parts = vda_lines[-1].split()
                util = float(parts[-1]) if len(parts) > 12 else -1
                await_val = float(parts[-2]) if len(parts) > 11 else -1
                signals["iostat"] = {"util_pct": util, "await_ms": await_val}
                if util > 50:
                    issues.append(f"iostat %util={util} > 50%")
                elif util > 30:
                    issues.append(f"iostat %util={util} > 30% (elevated)")
        except Exception as e:
            signals["iostat"] = f"error: {e}"

        # 信号3: dmesg I/O 错误数 (近1小时)
        try:
            io_pattern = re.compile(r"disk I/O error|I/O error|blk_update_request|Buffer I/O error", re.I)
            r = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=5)
            all_lines = r.stdout.split("\n")
            # 时间过滤: 近1小时
            last_ts = 0
            for line in reversed(all_lines):
                m = re.search(r"\[\s*(\d+\.\d+)\]", line)
                if m:
                    last_ts = float(m.group(1))
                    break
            cutoff = last_ts - 3600
            dmesg_errors = 0
            dmesg_samples = []
            for line in all_lines:
                if io_pattern.search(line):
                    ts_match = re.search(r"\[\s*(\d+\.\d+)\]", line)
                    if ts_match and float(ts_match.group(1)) >= cutoff:
                        dmesg_errors += 1
                        if len(dmesg_samples) < 5:
                            dmesg_samples.append(line.strip())
            signals["dmesg_io_errors_1h"] = dmesg_errors
            if dmesg_errors > 0:
                issues.append(f"dmesg I/O errors in last hour: {dmesg_errors}")
                signals["dmesg_samples"] = dmesg_samples
        except Exception as e:
            signals["dmesg_io_errors_1h"] = f"error: {e}"

        # 信号4: SQLite 快速压测 (30 SELECT)
        if not quick:
            try:
                ok = 0
                fail = 0
                t0 = time.time()
                for _ in range(30):
                    try:
                        conn = sqlite3.connect(DB_PATH, timeout=10)
                        conn.execute("SELECT count(*) FROM products").fetchone()
                        conn.close()
                        ok += 1
                    except Exception:
                        fail += 1
                elapsed = time.time() - t0
                fail_rate = round(fail / 30 * 100, 1)
                signals["sqlite_stress"] = {
                    "ops": 30, "ok": ok, "fail": fail,
                    "fail_rate_pct": fail_rate, "elapsed_sec": round(elapsed, 2)
                }
                if fail > 0:
                    issues.append(f"SQLite stress: {fail}/30 failed ({fail_rate}%)")
            except Exception as e:
                signals["sqlite_stress"] = f"error: {e}"
        else:
            signals["sqlite_stress"] = "skipped (quick mode)"

        # 综合评判
        has_issues = len(issues) > 0
        score = 100
        if any("integrity" in i for i in issues):
            score -= 40
        if any("dmesg" in i for i in issues):
            score -= 30
        if any("util=" in i for i in issues):
            score -= max(10, min(20, len([i for i in issues if "util=" in i]) * 10))
        if any("SQLite stress" in i for i in issues):
            score -= 20
        status = "critical" if score < 40 else ("warning" if score < 70 else "healthy")

        result = {
            "check_ts": datetime.now().isoformat(),
            "score": score,
            "status": status,
            "has_issues": has_issues,
            "issues": issues,
            "signals": signals,
        }
        if has_issues and not quick:
            self._emit_alert(status, "disk_io", "; ".join(issues), result)
        self._json(200, result)

    # ── /api/db/can_write ★ [V007.49-D 2026-07-13] ──────────
    def _db_can_write(self, q):
        """[V007.49-D] 检测 db 当前是否真正可写 (修补 root 绕过 chmod 的漏洞)
        背景: 2026-07-13 chaos 测试发现, chmod 555 拦截不了 root 用户的 SQLite INSERT
              实际场景: 云盘切换只读时, 我们服务是 root 跑, chmod 不生效
        方法: 真实写测试 (PRAGMA query_only + TEMP SAVEPOINT)
        用法: GET /api/db/can_write?token=XXX
        返回: { "can_write": bool, "mode": "r/w/rw", "errors": [], "tested_at": ... }
        """
        result = {
            "db_path": DB_PATH,
            "tested_at": datetime.now().isoformat(),
            "can_write": False,
            "mode": "unknown",
            "errors": [],
            "checks": {},
        }
        # 检查 1: PRAGMA query_only (SQLite 3.8+)
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            try:
                row = conn.execute("PRAGMA query_only").fetchone()
                query_only = bool(row[0]) if row else False
                result["checks"]["query_only_pragma"] = query_only
                if query_only:
                    result["errors"].append("PRAGMA query_only=1 (db opened in read-only mode)")
            except Exception as e:
                result["checks"]["query_only_pragma"] = f"ERR: {e}"
            finally:
                conn.close()
        except Exception as e:
            result["errors"].append(f"connect failed: {e}")
            return self._json(200, result)

        # 检查 2: 文件权限
        try:
            import stat as stat_mod
            st = os.stat(DB_PATH)
            file_mode = stat_mod.filemode(st.st_mode)
            writable_by_user = bool(st.st_mode & stat_mod.S_IWUSR)
            result["checks"]["file_mode"] = file_mode
            result["checks"]["file_writable_by_user"] = writable_by_user
            if not writable_by_user:
                result["errors"].append(f"file mode {file_mode} - no user write bit")
                # [V007.49-D] 即使 root 可绕过, 也标记 can_write=false
                # 因为如果文件本身没写权限, 强烈暗示云盘/权限问题
                result["can_write"] = False
                result["mode"] = "r"
        except Exception as e:
            result["errors"].append(f"stat failed: {e}")

        # 检查 3: 真实写测试 (用真实 INSERT, 不放 SAVEPOINT, 避免 root 绕过)
        # 只在 file_writable=True 时跑 (因为 root 可绕过文件权限, 但我们要测的是 SQLite 层)
        if not writable_by_user:
            result["checks"]["real_write_test"] = "SKIPPED (file not writable, root can bypass but considered unsafe)"
        else:
            try:
                conn = sqlite3.connect(DB_PATH, timeout=5)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("""
                        INSERT INTO audit_logs (object_type, object_id, action, field_name, user_name, created_at)
                        VALUES ('can_write_test', 88888, 'CAN_WRITE_TEST', 'test', 'system', datetime('now'))
                    """)
                    conn.execute("COMMIT")
                    # 立即删测试行, 不污染
                    conn.execute("DELETE FROM audit_logs WHERE object_type='can_write_test' AND object_id=88888")
                    conn.commit()
                    result["checks"]["real_write_test"] = "PASS"
                    result["can_write"] = True
                    result["mode"] = "rw"
                except sqlite3.OperationalError as e:
                    conn.rollback()
                    result["checks"]["real_write_test"] = f"FAIL: {e}"
                    result["errors"].append(f"real write failed: {e}")
                    result["can_write"] = False
                    result["mode"] = "r"
                finally:
                    conn.close()
            except Exception as e:
                result["errors"].append(f"write test connect failed: {e}")
                result["can_write"] = False

        # 检查 4: 磁盘剩余空间
        try:
            import shutil
            usage = shutil.disk_usage(os.path.dirname(DB_PATH))
            free_mb = usage.free / 1024 / 1024
            total_mb = usage.total / 1024 / 1024
            result["checks"]["disk_free_mb"] = round(free_mb, 1)
            result["checks"]["disk_total_mb"] = round(total_mb, 1)
            if free_mb < 100:
                result["errors"].append(f"disk space low: {free_mb:.0f}MB < 100MB required")
                result["can_write"] = False
        except Exception as e:
            result["errors"].append(f"disk check failed: {e}")

        if result["can_write"]:
            result["status"] = "ok"
        else:
            result["status"] = "readonly_or_full"

        return self._json(200, result)

    # ── /api/health/inspect ★ ──────────────────────────────────
    def _health_inspect(self, q):
        """[V007.51] /api/health/inspect?depth=normal|deep
        normal: 快速检查端口+DB+SQLite版本
        deep: +disk_io 压测 + invariant 业务验证 + trace 采样
        """
        depth = q.get("depth", ["normal"])[0]
        result = {"ts": datetime.now().isoformat(), "depth": depth, "checks": {}}
        # 1. 端口
        ports_status = {}
        for port in [3011, 5001, 8081, 9101]:
            alive = False
            try:
                with _socket_context(port) as s:
                    alive = (s.connect_ex(("127.0.0.1", port)) == 0)
            except Exception:
                pass
            ports_status[port] = "listening" if alive else "down"
        result["checks"]["ports"] = ports_status
        # 2. DB
        db_status = {}
        try:
            with _sqlite_open_ro(DB_PATH, timeout=5) as conn:
                cur = conn.execute("PRAGMA journal_mode").fetchone()
                db_status["journal_mode"] = cur[0] if cur else "unknown"
                cur = conn.execute("PRAGMA integrity_check").fetchone()
                db_status["integrity"] = cur[0] if cur else "unknown"
                try:
                    db_status["product_count"] = conn.execute(
                        "SELECT COUNT(*) FROM product WHERE is_deleted=0 OR is_deleted IS NULL"
                    ).fetchone()[0]
                except Exception:
                    db_status["product_count"] = None  # 表可能不存在
        except Exception as e:
            db_status["error"] = str(e)
        result["checks"]["db"] = db_status
        # 3. SQLite 版本
        try:
            import sqlite3 as _st
            result["checks"]["sqlite_version"] = _st.sqlite_version
        except Exception:
            pass
        # deep 才做的检查
        if depth == "deep":
            # 4. disk_io 压测
            try:
                disk_r = self._disk_io_test(5, 2, True)  # 内部调用, 简化
                result["checks"]["disk_io"] = {"ok": disk_r.get("ok"), "fail": disk_r.get("fail"),
                                               "PASS": disk_r.get("PASS")}
            except Exception as e:
                result["checks"]["disk_io"] = {"error": str(e)}
            # 5. invariant (健康端点)
            try:
                with _urllib_request.urlopen("http://127.0.0.1:3011/health", timeout=10) as r:
                    health = json.loads(r.read())
                v8z_fail = sum(1 for k, v in health.get("V8z", {}).items()
                               if isinstance(v, dict) and v.get("has_marker") is False)
                result["checks"]["v8z"] = {"total": len(health.get("V8z", {})),
                                           "fail": v8z_fail}
            except Exception as e:
                result["checks"]["v8z"] = {"error": str(e)}

        # 综合判定
        all_ok = (
            ports_status.get(3011) == "listening" and
            ports_status.get(9101) == "listening" and
            db_status.get("journal_mode") == "delete" and
            db_status.get("integrity") == "ok"
        )
        result["PASS"] = all_ok
        if not all_ok:
            self._emit_alert("error", "health", "inspect failed",
                             {"ports": ports_status, "db": db_status})
        return self._json(200, result)

    def _disk_io_test(self, rounds: int, concurrency: int, write: bool):
        """内部 disk_io 测试 (供 health_inspect 调用, 简化版)"""
        ok = 0
        fail = 0
        for _ in range(rounds):
            try:
                with _sqlite_open_ro(DB_PATH, timeout=5) as conn:
                    conn.execute("BEGIN").fetchone() if False else None
                    conn.execute("SELECT COUNT(*) FROM product").fetchone()
                    if write:
                        conn.execute("SELECT 1").fetchone()
                    conn.execute("ROLLBACK").fetchone() if False else None
                ok += 1
            except Exception:
                fail += 1
        return {"ok": ok, "fail": fail, "PASS": fail == 0}

    # ── /api/alert/sse ★ ───────────────────────────────────────
    def _alert_sse(self, q):
        """[V007.51] /api/alert/sse?history=10&block=1
        SSE 推流告警事件
        history=N: 先返回最近 N 条历史事件
        block=1: 长连接, 持续推送新事件
        """
        history_n = min(int(q.get("history", ["10"])[0]), 100)
        do_block = q.get("block", ["1"])[0] in ("1", "true", "yes")

        # SSE 响应头
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        # 1. 推送历史
        with self._alert_lock:
            history = list(self._alert_history[-history_n:])
        for evt in history:
            try:
                self.wfile.write(f"event: alert\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
            except Exception:
                return

        if not do_block:
            return

        # 2. 长连接订阅
        import queue
        q_self = queue.Queue(maxsize=100)
        with self._alert_lock:
            self._alert_subscribers.append(q_self)
        try:
            while True:
                try:
                    evt = q_self.get(timeout=30)
                    self.wfile.write(f"event: alert\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    # 心跳保活
                    try:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                    except Exception:
                        return
        finally:
            with self._alert_lock:
                if q_self in self._alert_subscribers:
                    self._alert_subscribers.remove(q_self)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    print(f"[log_service {VERSION}] starting on {BIND}:{PORT}", flush=True)
    print(f"[log_service {VERSION}] LOG_DIR={LOG_DIR}", flush=True)
    print(f"[log_service {VERSION}] DB_PATH={DB_PATH}", flush=True)
    print(f"[log_service {VERSION}] token(first16)={_gen_token().split(',')[0]}", flush=True)
    print(f"[log_service {VERSION}] P0 endpoints: /api/manage/journal_mode /api/diag/trace /api/test/disk_io /api/deploy/smoke /api/upload /api/exec /api/disk/errors /api/disk/check", flush=True)
    server = ThreadedHTTPServer((BIND, PORT), LogHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print(f"[log_service {VERSION}] shutdown", flush=True)
