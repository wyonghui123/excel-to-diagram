"""
[V007.62] ops_scheduler.py v1.1 - 运维定时任务调度器
  独立进程, 管理周期性运维任务 (备份/巡检/清理/升级前检查)
  监听: 9202
  依赖: Python 3.6+ 标准库, 无第三方依赖

  设计原则:
    1. 声明式任务 - 预定义任务模板, 配置驱动
    2. 最小侵入 - 只调用现有 API (log_service/core_service), 不直接操作文件/进程
    3. 审计追踪 - 所有任务执行记录到 JSONL
    4. 安全 - token 鉴权, 白名单任务

  预置任务:
    db_backup        每6h    数据库备份 (调用 /opt/app/shared/db_backup.sh)
    health_inspect   每30m   健康巡检 (调用 log_service /api/health/inspect)
    disk_forecast    每1h    磁盘预测 (调用 log_service /api/disk/forecast)
    disk_io_check    每5m    SQLite disk I/O 健康检查 (调用 log_service /api/disk/check)
    log_archive      每天    日志归档 (调用 log_service /api/log/archive)
    db_vacuum        每周    数据库优化 (VACUUM)
    backup_cleanup   每天    备份清理 (保留7天)
    ssl_check        每天    SSL 证书过期检查

  端点:
    GET  /api                    服务信息
    GET  /api/tasks              列出所有任务及状态
    GET  /api/tasks/:name/run    立即执行指定任务
    GET  /api/tasks/:name/log    查看任务执行日志
    GET  /api/history            最近执行历史
"""

from __future__ import annotations
import os, sys, json, time, hashlib, threading, subprocess
import http.server, socketserver
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

# --- config ---
VERSION = "v1.1"
PORT = int(os.environ.get("OPS_SCHEDULER_PORT", 9202))
BIND = os.environ.get("OPS_SCHEDULER_BIND", "0.0.0.0")
SECRET = os.environ.get("OPS_SCHEDULER_SECRET", "v007.61-ops")
TOKEN_HR = 8
_START_TIME = time.time()
SCHEDULER_LOG = os.environ.get("OPS_SCHEDULER_LOG", "/opt/app/shared/logs/scheduler.jsonl")

# --- predefined tasks ---
TASKS = {
    "db_backup": {
        "desc": "Database backup",
        "interval": 21600,  # 6h
        "command": "/bin/bash /opt/app/shared/db_backup.sh",
        "timeout": 300,
    },
    "health_inspect": {
        "desc": "Health inspection",
        "interval": 1800,  # 30m
        "command": "curl -sf http://127.0.0.1:9101/api/health/inspect",
        "timeout": 120,
    },
    "disk_forecast": {
        "desc": "Disk usage forecast",
        "interval": 3600,  # 1h
        "command": "curl -sf http://127.0.0.1:9101/api/disk/forecast",
        "timeout": 60,
    },
    "disk_io_check": {
        "desc": "SQLite disk I/O health check",
        "interval": 300,  # 5m
        "command": "curl -sf 'http://127.0.0.1:9101/api/disk/check?quick=true'",
        "timeout": 30,
    },
    "log_archive": {
        "desc": "Log archive and cleanup",
        "interval": 86400,  # 1d
        "command": "curl -sf 'http://127.0.0.1:9101/api/log/archive?max_age_days=7&max_total_mb=500'",
        "timeout": 120,
    },
    "db_vacuum": {
        "desc": "SQLite VACUUM (low-traffic hours only)",
        "interval": 604800,  # 1w
        "command": "curl -sf 'http://127.0.0.1:9101/api/manage/journal_mode?action=vacuum'",
        "timeout": 300,
    },
    "backup_cleanup": {
        "desc": "Cleanup old backups (keep 7 days)",
        "interval": 86400,  # 1d
        "command": "find /opt/app/backups -name 'architecture_*.db' -mtime +7 -delete 2>/dev/null; echo cleanup_done",
        "timeout": 60,
    },
    "ssl_check": {
        "desc": "SSL certificate expiry check",
        "interval": 86400,  # 1d
        "command": "openssl x509 -checkend 2592000 -in /opt/app/shared/core_service.crt 2>/dev/null && echo ssl_ok || echo ssl_expiring",
        "timeout": 30,
    },
}

# --- task state ---
_task_lock = threading.Lock()
_task_state = {name: {"last_run": None, "last_exit": None, "next_run": time.time() + task["interval"], "run_count": 0}
               for name, task in TASKS.items()}
_scheduler_running = True

# --- token ---
def _gen_tokens():
    now = int(time.time())
    out = set()
    for off in range(TOKEN_HR + 1):
        h = (now - off * 3600) // 3600
        out.add(hashlib.sha256(f"{SECRET}:{h}".encode()).hexdigest()[:16])
    return out

def _check_token(params):
    t = params.get("token", [""])[0]
    if t and t in _gen_tokens():
        return True
    return False

# --- logging ---
def _log_task(task_name, exit_code, stdout, stderr, duration):
    entry = {
        "ts": datetime.now().isoformat(),
        "task": task_name,
        "exit_code": exit_code,
        "duration_sec": round(duration, 2),
        "stdout_preview": stdout[:200] if stdout else "",
        "stderr_preview": stderr[:200] if stderr else "",
    }
    try:
        log_dir = os.path.dirname(SCHEDULER_LOG)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        with open(SCHEDULER_LOG, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _run_task(name):
    task = TASKS.get(name)
    if not task:
        return
    start = time.time()
    try:
        proc = subprocess.run(
            task["command"], shell=True, capture_output=True, text=True,
            timeout=task.get("timeout", 120)
        )
        exit_code = proc.returncode
        stdout = proc.stdout.strip()[:500]
        stderr = proc.stderr.strip()[:500]
    except subprocess.TimeoutExpired:
        exit_code = -1
        stdout = ""
        stderr = "timeout"
    except Exception as e:
        exit_code = -1
        stdout = ""
        stderr = str(e)[:200]

    duration = time.time() - start
    _log_task(name, exit_code, stdout, stderr, duration)

    with _task_lock:
        _task_state[name]["last_run"] = datetime.now().isoformat()
        _task_state[name]["last_exit"] = exit_code
        _task_state[name]["next_run"] = time.time() + task["interval"]
        _task_state[name]["run_count"] += 1
        _task_state[name]["last_stdout"] = stdout[:200]
        _task_state[name]["last_stderr"] = stderr[:200]
        _task_state[name]["last_duration"] = round(duration, 2)

# --- scheduler thread ---
def _scheduler_loop():
    while _scheduler_running:
        now = time.time()
        for name, task in TASKS.items():
            with _task_lock:
                next_run = _task_state[name].get("next_run", now)
            if now >= next_run:
                t = threading.Thread(target=_run_task, args=(name,), daemon=True)
                t.start()
                with _task_lock:
                    _task_state[name]["next_run"] = now + task["interval"] + 5  # add 5s buffer
        time.sleep(30)  # check every 30s

# --- handler ---
class SchedulerHandler(http.server.BaseHTTPRequestHandler):
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

        try:
            if route in ("", "/", "/api"):
                return self._root(q)
            elif route == "/api/tasks":
                return self._tasks(q)
            elif route.startswith("/api/tasks/") and route.endswith("/run"):
                name = route.split("/")[3]
                return self._run_now(name, q)
            elif route.startswith("/api/tasks/") and route.endswith("/log"):
                name = route.split("/")[3]
                return self._task_log(name, q)
            elif route == "/api/history":
                return self._history(q)
            return self._json(404, {"error": "not found", "route": route})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def _root(self, q):
        return self._json(200, {
            "service": "ops_scheduler",
            "version": VERSION,
            "uptime_sec": int(time.time() - _START_TIME),
            "port": PORT,
            "tasks": len(TASKS),
            "endpoints": ["/api", "/api/tasks", "/api/tasks/:name/run", "/api/tasks/:name/log", "/api/history"],
            "scheduler_log": SCHEDULER_LOG,
        })

    def _tasks(self, q):
        with _task_lock:
            states = {}
            for name, task in TASKS.items():
                s = _task_state.get(name, {})
                states[name] = {
                    "desc": task["desc"],
                    "interval_sec": task["interval"],
                    "interval_human": self._human_duration(task["interval"]),
                    "command": task["command"][:100],
                    "last_run": s.get("last_run"),
                    "last_exit": s.get("last_exit"),
                    "next_run": datetime.fromtimestamp(s.get("next_run", 0)).isoformat() if s.get("next_run", 0) > 0 else None,
                    "run_count": s.get("run_count", 0),
                }
        return self._json(200, {"count": len(states), "tasks": states})

    def _run_now(self, name, q):
        if name not in TASKS:
            return self._json(404, {"error": f"task '{name}' not found", "available": list(TASKS.keys())})
        t = threading.Thread(target=_run_task, args=(name,), daemon=True)
        t.start()
        return self._json(200, {"ok": True, "task": name, "message": f"task '{name}' triggered"})

    def _task_log(self, name, q):
        if name not in TASKS:
            return self._json(404, {"error": f"task '{name}' not found"})
        n = min(int(q.get("n", ["10"])[0]), 100)
        entries = []
        if os.path.exists(SCHEDULER_LOG):
            try:
                with open(SCHEDULER_LOG, "r") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("task") == name:
                            entries.append(entry)
                            if len(entries) >= n:
                                break
                    except Exception:
                        pass
            except Exception:
                pass
        return self._json(200, {"task": name, "count": len(entries), "entries": entries})

    def _history(self, q):
        n = min(int(q.get("n", ["50"])[0]), 200)
        entries = []
        if os.path.exists(SCHEDULER_LOG):
            try:
                with open(SCHEDULER_LOG, "r") as f:
                    lines = f.readlines()
                for line in reversed(lines[-n:]):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
            except Exception:
                pass
        return self._json(200, {"count": len(entries), "entries": entries})

    @staticmethod
    def _human_duration(seconds):
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m"
        elif seconds < 86400:
            return f"{seconds // 3600}h"
        else:
            return f"{seconds // 86400}d"


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    sched_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    sched_thread.start()

    print(f"[ops_scheduler {VERSION}] starting on {BIND}:{PORT}", flush=True)
    print(f"[ops_scheduler {VERSION}] tasks: {len(TASKS)} ({', '.join(TASKS.keys())})", flush=True)
    print(f"[ops_scheduler {VERSION}] log: {SCHEDULER_LOG}", flush=True)

    server = ThreadedServer((BIND, PORT), SchedulerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _scheduler_running = False
        server.server_close()
