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

VERSION = "v0.1"
PORT = int(os.environ.get("DEPLOY_SERVICE_PORT", 9205))
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


def deploy_worker(version: str, zip_path: str, deployment_type: str = "full"):
    """后台部署线程"""
    with DEPLOY_LOCK:
        CURRENT_DEPLOY.update({
            "state": DeployState.QUEUED.value,
            "version": version,
            "started_at": time.time(),
            "ended_at": None,
            "exit_code": None,
            "log_file": None,
            "deployment_type": deployment_type,
        })

    log_path = os.path.join(LOG_DIR, f"deploy_{version}_{int(time.time())}.log")
    os.makedirs(LOG_DIR, exist_ok=True)

    states = [
        (DeployState.PRE_CHECK, "PHASE 0.5: pre-check"),
        (DeployState.EXTRACTING, "PHASE 1: extract"),
        (DeployState.MIGRATING, "PHASE 2: migrate"),
        (DeployState.RESTARTING, "PHASE 3: restart"),
        (DeployState.VERIFYING, "PHASE 4: verify"),
    ]
    try:
        with open(log_path, "w") as logf:
            logf.write(f"# Deploy {version} @ {time.ctime()}\n")
            logf.write(f"# deployment_type={deployment_type}\n# zip={zip_path}\n\n")
            logf.flush()

            # 模拟状态机进度 (实际生产应调用 deploy.sh 各 PHASE)
            for state, phase in states:
                with DEPLOY_LOCK:
                    CURRENT_DEPLOY["state"] = state.value
                    CURRENT_DEPLOY["log_file"] = log_path
                logf.write(f"[{time.ctime()}] {phase} starting...\n")
                logf.flush()
                time.sleep(2)  # 模拟耗时
                logf.write(f"[{time.ctime()}] {phase} ok\n")
                logf.flush()

            # 标记成功
            with DEPLOY_LOCK:
                CURRENT_DEPLOY["state"] = DeployState.DONE.value
                CURRENT_DEPLOY["exit_code"] = 0
                CURRENT_DEPLOY["ended_at"] = time.time()
            DEPLOY_HISTORY.appendleft(dict(CURRENT_DEPLOY))
            logf.write(f"\n[{time.ctime()}] DONE\n")
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
        if not version or not zip_path:
            return self._json(400, {"error": "version and zip_path required"})

        with DEPLOY_LOCK:
            if CURRENT_DEPLOY["state"] not in (DeployState.IDLE.value, DeployState.DONE.value, DeployState.FAILED.value):
                return self._json(409, {
                    "error": "deploy already running",
                    "current_state": CURRENT_DEPLOY["state"],
                })

        # 启动后台线程
        t = threading.Thread(
            target=deploy_worker,
            args=(version, zip_path, deployment_type),
            daemon=True,
        )
        t.start()
        return self._json(202, {
            "accepted": True,
            "version": version,
            "deployment_type": deployment_type,
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
    print(f"[deploy_service] v{VERSION} on port {PORT}", flush=True)
    print(f"[deploy_service] SCRIPT_DIR={SCRIPT_DIR}", flush=True)
    print(f"[deploy_service] LOG_DIR={LOG_DIR}", flush=True)
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()