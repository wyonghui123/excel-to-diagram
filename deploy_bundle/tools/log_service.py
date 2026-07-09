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

  usage:
    nohup python3 log_service.py > /tmp/log_service.log 2>&1 &
    curl http://localhost:9101/api/system

  端口: 9101
  依赖: Python 3.8+ 标准库, 无 pip 依赖
  内存: < 25MB RSS (v4 加了 SSE 缓冲)
"""

from __future__ import annotations  # Py3.7+ 让 `X | Y` 语法兼容
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
MAX_LINES = int(os.environ.get("LOG_SERVICE_MAX_LINES", 5000))  # 单次最大行数
TOKEN_HR  = int(os.environ.get("LOG_SERVICE_TOKEN_HOURS", 8))

# 安全白名单: /api/log, /api/config 只读这些目录
ALLOWED_DIRS = [
    "/opt/app/deployments",
    "/opt/app/shared/logs",
    "/opt/app/shared",
    "/tmp",
    "/var/log",
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
                    "note": "v4 has 21 endpoints; common: /api/system /api/proc /api/process /api/log /api/db/health /api/sqlite/load /api/iostat /api/dmesg",
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

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    print(f"[log_service v4.5] V007.37 starting on {BIND}:{PORT}", flush=True)
    print(f"[log_service v4.5] LOG_DIR={LOG_DIR}", flush=True)
    print(f"[log_service v4.5] DB_PATH={DB_PATH}", flush=True)
    print(f"[log_service v4.5] token(first16)={_gen_token().split(',')[0]}", flush=True)
    print(f"[log_service v4.5] new endpoints: /api/sqlite, /api/sqlite/load, /api/iostat, /api/proc/io", flush=True)
    server = ThreadedHTTPServer((BIND, PORT), LogHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[log_service v4.5] shutdown", flush=True)
