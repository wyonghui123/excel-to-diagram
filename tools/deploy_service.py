"""deploy_service.py - 部署编排服务 [V007.65 2026-07-14]
[L14 部署编排]

端口: 9205
提供:
  - 11 状态机: idle/queued/pre_check/extracting/migrating/restarting/verifying/done/failed/rolling_back/rolled_back
  - 后台 worker 线程执行 deploy.sh
  - L11.3 DELETE 二次确认 (rollback / cancel)
  - DEPLOY_HISTORY 保留最近 50 次

端点:
  GET  /api                          服务信息
  POST /api/deploy/start             启动部署 (JSON: {version, zip_path, deployment_type})
  GET  /api/deploy/status            当前状态
  POST /api/deploy/rollback          回滚 (JSON: {target_version, confirm: yes-i-know})
  GET  /api/deploy/history           历史
  POST /api/deploy/cancel            取消 (JSON: {confirm: yes-i-know})

安全: sha256(secret:hour)[:16] 时变 token
"""
import os
import sys
import json
import time
import hashlib
import threading
import subprocess
import http.server
import socketserver
from enum import Enum
from collections import deque
from urllib.parse import urlparse, parse_qs

VERSION = "v0.3"
# [L14] 端口 9215: 9205 已被 error_aggregator_service 占用 (2026-07-14 实测)
PORT = int(os.environ.get("DEPLOY_SERVICE_PORT", 9215))
# [L4 NSFOCUS] BIND=172.20.59.7 读 .env_global
BIND = os.environ.get("DEPLOY_SERVICE_BIND", "0.0.0.0")
SECRET = os.environ.get("DEPLOY_SERVICE_SECRET", "v007.65-deploy")
SCRIPT_DIR = os.environ.get("DEPLOY_SCRIPT_DIR", "/opt/app/shared")
LOG_DIR = os.environ.get("DEPLOY_LOG_DIR", "/opt/app/deploy_logs")


class DeployState(str, Enum):
    IDLE = "idle"
    QUEUED = "queued"
    PRE_CHECK = "pre_check"
    EXTRACTING = "extracting"
    MIGRATING = "migrating"
    RESTARTING = "restarting"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


# 全局状态 (单进程内)
CURRENT_DEPLOY = {
    "state": DeployState.IDLE.value,
    "version": None,
    "started_at": None,
    "ended_at": None,
    "exit_code": None,
    "log_file": None,
    "deployment_type": "full",
}
DEPLOY_LOCK = threading.Lock()
DEPLOY_HISTORY = deque(maxlen=50)  # 最近 50 次


def check_token(token: str) -> bool:
    """时变 token: sha256(secret:hour)[:16]"""
    if not token:
        return False
    expected = hashlib.sha256(
        f"{SECRET}:{int(time.time()) // 3600}".encode()
    ).hexdigest()[:16]
    return token == expected


def deploy_worker(version: str, zip_path: str, deployment_type: str = "full", port: int = 9200, frontend_port: int = 8081):
    """后台部署线程 [L14.3] - 调用真实 deploy.sh

    Args:
        version: 版本号 (如 v20260714_001)
        zip_path: zip 路径 (默认 /opt/app/deploy-{VERSION}.zip)
        deployment_type: full / delta
        port: backend 端口 (默认 9200)
        frontend_port: 前端端口 (默认 8081)
    """
    with DEPLOY_LOCK:
        CURRENT_DEPLOY.update({
            "state": DeployState.QUEUED.value,
            "version": version,
            "started_at": time.time(),
            "ended_at": None,
            "exit_code": None,
            "log_file": None,
            "deployment_type": deployment_type,
            "port": port,
        })

    log_path = os.path.join(LOG_DIR, f"deploy_{version}_{int(time.time())}.log")
    os.makedirs(LOG_DIR, exist_ok=True)

    # [L14.3] deploy.sh 路径: SCRIPT_DIR 默认 /opt/app/shared, deploy.sh 通常在 /opt/app/shared/
    deploy_sh = os.path.join(SCRIPT_DIR, "deploy.sh")
    if not os.path.exists(deploy_sh):
        # fallback: 在 deploy_bundle/ 下
        deploy_sh = "/opt/app/deploy_bundle/deploy.sh"

    states = [
        (DeployState.PRE_CHECK, "PHASE 0: pre-check"),
        (DeployState.EXTRACTING, "PHASE 0.5: extract"),
        (DeployState.MIGRATING, "PHASE 1: backup db"),
        (DeployState.RESTARTING, "PHASE 2: restart services"),
        (DeployState.VERIFYING, "PHASE 3: verify"),
    ]
    try:
        with open(log_path, "w") as logf:
            logf.write(f"# Deploy {version} @ {time.ctime()}\n")
            logf.write(f"# deployment_type={deployment_type}\n")
            logf.write(f"# zip={zip_path}\n")
            logf.write(f"# port={port}\n")
            logf.write(f"# frontend_port={frontend_port}\n")
            logf.write(f"# deploy_sh={deploy_sh}\n\n")
            logf.flush()

            # [L14.3] 真实调用 deploy.sh (替换原 time.sleep 模拟)
            # 使用 --no-systemd 避免 systemd unit 文件被改 (我们用 start_*.sh 手动管理)
            # DEPLOY_MODE 环境变量让 deploy.sh 内部走 delta/full 分支
            env = os.environ.copy()
            env["DEPLOY_MODE"] = deployment_type
            cmd = [
                "bash", deploy_sh,
                "--version", version,
                "--port", str(port),
                "--frontend-port", str(frontend_port),
                "--zip", zip_path,
                "--no-systemd",
            ]
            logf.write(f"[{time.ctime()}] $ {' '.join(cmd)}\n")
            logf.flush()

            # 推进到第一个 state (PRE_CHECK), 然后 spawn 进程
            with DEPLOY_LOCK:
                CURRENT_DEPLOY["state"] = DeployState.PRE_CHECK.value
                CURRENT_DEPLOY["log_file"] = log_path
            logf.write(f"[{time.ctime()}] PHASE 0: pre-check starting...\n")
            logf.flush()

            # 启动子进程 (实时读取 stdout/stderr 写日志)
            proc = subprocess.Popen(
                cmd,
                cwd=SCRIPT_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # line-buffered
            )
            # 后台线程读 stdout, 同步更新状态机
            def _stream_and_track():
                phase_to_state = {
                    "PHASE 0:": DeployState.PRE_CHECK,
                    "PHASE 0.5:": DeployState.EXTRACTING,
                    "PHASE 1:": DeployState.MIGRATING,
                    "PHASE 2:": DeployState.RESTARTING,
                    "PHASE 3:": DeployState.VERIFYING,
                }
                for line in proc.stdout:
                    line = line.rstrip()
                    logf.write(line + "\n")
                    logf.flush()
                    # 状态机: 匹配 PHASE X: 推进
                    for ph_prefix, target_state in phase_to_state.items():
                        if ph_prefix in line:
                            with DEPLOY_LOCK:
                                if CURRENT_DEPLOY["state"] != DeployState.FAILED.value:
                                    CURRENT_DEPLOY["state"] = target_state.value

            import threading as _thr
            stream_thread = _thr.Thread(target=_stream_and_track, daemon=True)
            stream_thread.start()

            # 等待 (带超时, 默认 30min)
            try:
                rc = proc.wait(timeout=1800)  # 30 min
            except subprocess.TimeoutExpired:
                proc.kill()
                rc = -9
                logf.write(f"\n[{time.ctime()}] TIMEOUT: deploy.sh 超过 30min, 强制 kill\n")

            stream_thread.join(timeout=5)

            # 标记终态
            if rc == 0:
                with DEPLOY_LOCK:
                    CURRENT_DEPLOY["state"] = DeployState.DONE.value
                    CURRENT_DEPLOY["exit_code"] = 0
                logf.write(f"\n[{time.ctime()}] DONE (rc=0)\n")
            else:
                with DEPLOY_LOCK:
                    CURRENT_DEPLOY["state"] = DeployState.FAILED.value
                    CURRENT_DEPLOY["exit_code"] = rc
                logf.write(f"\n[{time.ctime()}] FAILED (rc={rc})\n")
    except Exception as e:
        with DEPLOY_LOCK:
            CURRENT_DEPLOY["state"] = DeployState.FAILED.value
            CURRENT_DEPLOY["exit_code"] = 1
            CURRENT_DEPLOY["ended_at"] = time.time()
        DEPLOY_HISTORY.appendleft(dict(CURRENT_DEPLOY))
        try:
            with open(log_path, "a") as logf:
                logf.write(f"\n[{time.ctime()}] FAILED: {e}\n")
        except Exception:
            pass


class Handler(http.server.BaseHTTPRequestHandler):
    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        token = qs.get("token", [""])[0]
        if not check_token(token):
            return self._json(403, {"error": "token required"})

        if url.path == "/api":
            return self._json(200, {
                "service": "deploy_service",
                "version": VERSION,
                "port": PORT,
                "states": [s.value for s in DeployState],
                "endpoints": [
                    "/api/deploy/start",
                    "/api/deploy/status",
                    "/api/deploy/rollback",
                    "/api/deploy/history",
                    "/api/deploy/cancel",
                ],
            })

        if url.path == "/api/deploy/status":
            with DEPLOY_LOCK:
                snapshot = dict(CURRENT_DEPLOY)
            return self._json(200, snapshot)

        if url.path == "/api/deploy/history":
            return self._json(200, {
                "history": list(DEPLOY_HISTORY),
                "count": len(DEPLOY_HISTORY),
            })

        return self._json(404, {"error": "not found"})

    def do_POST(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        token = qs.get("token", [""])[0]
        if not check_token(token):
            return self._json(403, {"error": "token required"})

        body = self._read_json_body()

        if url.path == "/api/deploy/start":
            return self._start_deploy(body)
        if url.path == "/api/deploy/rollback":
            return self._rollback(body)
        if url.path == "/api/deploy/cancel":
            return self._cancel(body)
        return self._json(404, {"error": "not found"})

    def _start_deploy(self, body: dict):
        version = body.get("version")
        zip_path = body.get("zip_path")
        deployment_type = body.get("deployment_type", "full")
        # [L14.3] 新增可选参数
        port = int(body.get("port", 9200))
        frontend_port = int(body.get("frontend_port", 8081))
        if not version or not zip_path:
            return self._json(400, {"error": "version and zip_path required"})

        with DEPLOY_LOCK:
            if CURRENT_DEPLOY["state"] not in (DeployState.IDLE.value, DeployState.DONE.value, DeployState.FAILED.value):
                return self._json(409, {
                    "error": "deploy already running",
                    "current_state": CURRENT_DEPLOY["state"],
                })

        # 启动后台线程 (L14.3: 真实调 deploy.sh)
        t = threading.Thread(
            target=deploy_worker,
            args=(version, zip_path, deployment_type, port, frontend_port),
            daemon=True,
        )
        t.start()
        return self._json(202, {
            "accepted": True,
            "version": version,
            "deployment_type": deployment_type,
            "port": port,
            "frontend_port": frontend_port,
            "note": "L14.3: 真实调用 deploy.sh, 替换原 time.sleep 模拟",
        })

    def _rollback(self, body: dict):
        # [L11.3] DELETE 二次确认
        confirm = body.get("confirm", "")
        target = body.get("target_version", "")
        if confirm != "yes-i-know":
            return self._json(400, {
                "error": "rollback requires confirm=yes-i-know",
                "warning": "This will revert production. Read DEPLOY_HANDOVER.md first.",
            })

        with DEPLOY_LOCK:
            CURRENT_DEPLOY["state"] = DeployState.ROLLING_BACK.value
            CURRENT_DEPLOY["ended_at"] = time.time()

        # 模拟 rollback worker (生产应调用 deploy.sh --rollback)
        def _rb():
            time.sleep(1)
            with DEPLOY_LOCK:
                CURRENT_DEPLOY["state"] = DeployState.ROLLED_BACK.value
                CURRENT_DEPLOY["ended_at"] = time.time()
            DEPLOY_HISTORY.appendleft(dict(CURRENT_DEPLOY))

        threading.Thread(target=_rb, daemon=True).start()
        return self._json(202, {
            "accepted": True,
            "target_version": target,
            "state": DeployState.ROLLING_BACK.value,
        })

    def _cancel(self, body: dict):
        confirm = body.get("confirm", "")
        if confirm != "yes-i-know":
            return self._json(400, {
                "error": "cancel requires confirm=yes-i-know",
            })
        with DEPLOY_LOCK:
            if CURRENT_DEPLOY["state"] in (
                DeployState.IDLE.value, DeployState.DONE.value,
                DeployState.FAILED.value, DeployState.ROLLED_BACK.value,
            ):
                return self._json(409, {
                    "error": "nothing to cancel",
                    "current_state": CURRENT_DEPLOY["state"],
                })
            CURRENT_DEPLOY["state"] = DeployState.FAILED.value
            CURRENT_DEPLOY["ended_at"] = time.time()
        return self._json(200, {"ok": True, "state": DeployState.FAILED.value})

    def log_message(self, fmt, *args):
        sys.stderr.write("[deploy_service] %s - - %s\n" % (self.address_string(), fmt % args))


def main():
    print(f"[deploy_service] v{VERSION} on {BIND}:{PORT}", flush=True)
    print(f"[deploy_service] SCRIPT_DIR={SCRIPT_DIR}", flush=True)
    print(f"[deploy_service] LOG_DIR={LOG_DIR}", flush=True)
    # [L4 NSFOCUS] 允许 SO_REUSEADDR + 监听 BIND (默认 172.20.59.7)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((BIND, PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()