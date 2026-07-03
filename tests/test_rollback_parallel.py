#!/usr/bin/env python3
"""
test_rollback_parallel.py - 并行验证 rollback 流程, 不影响 current 部署
  v3 用 5002/8082 (测试端口, 避开 5001/8081 业务)
  通过临时改 v3 .env 强制 PORT=5002, 避开 v3 server.py 强 check 8081
  启 v3 backend + unified, 跑健康检查, 清理
  验证 current 5001/8081 不受影响
"""
import os
import sys
import time
import signal
import socket
import subprocess
import shutil
import urllib.request
import json
from pathlib import Path

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"
PASS = 0
FAIL = 0
SKIP = 0

V3_VERSION = "v20260630_003"
V4_VERSION = "v20260703_002"
V3_BACKEND_PORT = 5002
V3_FRONTEND_PORT = 8082
V4_BACKEND_PORT = 5001
V4_FRONTEND_PORT = 8081
DEPLOY_BUNDLE = "/tmp/deploy_bundle"
DEPLOYMENTS_DIR = "/opt/app/deployments"
PY = "/opt/miniconda3-py39/bin/python"
HEALTH_TIMEOUT = 15


def log(s):
    print(s, flush=True)


def pass_(msg):
    global PASS
    log(f"{GREEN}✓ PASS{NC} {msg}")
    PASS += 1


def fail(msg):
    global FAIL
    log(f"{RED}✗ FAIL{NC} {msg}")
    FAIL += 1


def warn(msg):
    log(f"{YELLOW}⚠ WARN{NC} {msg}")


def info(msg):
    log(f"[INFO] {msg}")


def banner(s):
    log("")
    log("=" * 60)
    log(s)
    log("=" * 60)


def port_listening(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def http_get(url, timeout=HEALTH_TIMEOUT):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)


def http_post(url, data, timeout=HEALTH_TIMEOUT):
    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)


def kill_port(port):
    subprocess.run(["fuser", "-k", f"{port}/tcp"], stderr=subprocess.DEVNULL)
    time.sleep(1)


def kill_pid(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


# ============================================================
# PHASE 0: 验证 current 业务
# ============================================================
banner("PHASE 0: 验证 current 业务 (5001/8081) 不受影响")

if not port_listening(V4_BACKEND_PORT):
    log(f"{RED}current backend {V4_BACKEND_PORT} NOT listening - 不能并行测试{NC}")
    sys.exit(1)

status, _ = http_get(f"http://127.0.0.1:{V4_BACKEND_PORT}/api/v1/enum-types")
if status == 200:
    pass_(f"current backend {V4_BACKEND_PORT} alive (enum-types 200)")
else:
    fail(f"current backend {V4_BACKEND_PORT} health {status}")
    sys.exit(1)

if not port_listening(V4_FRONTEND_PORT):
    log(f"{RED}current unified {V4_FRONTEND_PORT} NOT listening - 不能并行测试{NC}")
    sys.exit(1)

status, _ = http_get(f"http://127.0.0.1:{V4_FRONTEND_PORT}/")
if status == 200:
    pass_(f"current unified {V4_FRONTEND_PORT} alive (200)")
else:
    fail(f"current unified {V4_FRONTEND_PORT} {status}")
    sys.exit(1)

# ============================================================
# PHASE 1: 杀干净 5002/8082
# ============================================================
banner("PHASE 1: 准备 5002/8082 (清理残留)")

if port_listening(V3_BACKEND_PORT):
    warn(f"{V3_BACKEND_PORT} 被占, 杀")
    kill_port(V3_BACKEND_PORT)

if port_listening(V3_FRONTEND_PORT):
    warn(f"{V3_FRONTEND_PORT} 被占, 杀")
    kill_port(V3_FRONTEND_PORT)

if port_listening(V3_BACKEND_PORT) or port_listening(V3_FRONTEND_PORT):
    fail("5002/8082 杀不干净")
    sys.exit(1)
pass_("5002/8082 干净")

# ============================================================
# PHASE 2: 检查 v3 文件 + 备份 .env
# ============================================================
banner("PHASE 2: 验证 v3 部署文件 + 备份 .env")

V3_PATH = Path(DEPLOYMENTS_DIR) / V3_VERSION
V3_SERVER = V3_PATH / "meta" / "server.py"
V3_ENV = V3_PATH / ".env"
V3_ENV_BACKUP = Path("/tmp") / f".env.v3.backup.{int(time.time())}"

if not V3_PATH.is_dir():
    fail(f"v3 路径不存在: {V3_PATH}")
    sys.exit(1)
if not V3_SERVER.is_file():
    fail(f"v3 server.py 不存在: {V3_SERVER}")
    sys.exit(1)
pass_(f"v3 文件在: {V3_PATH}")

# 备份 .env
ENV_MODIFIED = False
if V3_ENV.is_file():
    shutil.copy(V3_ENV, V3_ENV_BACKUP)
    info(f"备份 .env → {V3_ENV_BACKUP}")

    # 强制改 PORT=5002
    lines = V3_ENV.read_text(encoding="utf-8", errors="replace").split("\n")
    new_lines = []
    port_found = False
    for line in lines:
        if line.strip().startswith("PORT="):
            new_lines.append(f"PORT={V3_BACKEND_PORT}")
            port_found = True
        else:
            new_lines.append(line)
    if not port_found:
        new_lines.append(f"PORT={V3_BACKEND_PORT}")
    V3_ENV.write_text("\n".join(new_lines), encoding="utf-8")
    ENV_MODIFIED = True
    info(f"改 .env: PORT={V3_BACKEND_PORT}")
    pass_("v3 .env 改 PORT=5002")

# ============================================================
# PHASE 3: 启 v3 backend 5002
# ============================================================
banner("PHASE 3: 启 v3 backend 5002")

JWT_KEY = f"test-parallel-rollback-jwt-key-{int(time.time())}"
FLASK_KEY = f"test-parallel-rollback-flask-key-{int(time.time())}"
CORS_ORIGINS = f"http://172.20.59.7:{V3_FRONTEND_PORT}"

env = os.environ.copy()
env.update({
    "PORT": str(V3_BACKEND_PORT),
    "JWT_SECRET_KEY": JWT_KEY,
    "FLASK_SECRET_KEY": FLASK_KEY,
    "CORS_ALLOWED_ORIGINS": CORS_ORIGINS,
})

v3_log = open("/tmp/v3-backend-test.log", "w")
v3_proc = subprocess.Popen(
    [PY, "server.py"],
    cwd=str(V3_PATH / "meta"),
    env=env,
    stdout=v3_log,
    stderr=subprocess.STDOUT,
)
info(f"v3 backend PID={v3_proc.pid}")
time.sleep(8)

if not port_listening(V3_BACKEND_PORT):
    fail(f"v3 backend {V3_BACKEND_PORT} 没启")
    with open("/tmp/v3-backend-test.log") as f:
        log(f.read()[-1500:])
    kill_pid(v3_proc.pid)
    if ENV_MODIFIED:
        shutil.copy(V3_ENV_BACKUP, V3_ENV)
    sys.exit(1)
pass_(f"v3 backend {V3_BACKEND_PORT} listening")

status, body = http_get(f"http://127.0.0.1:{V3_BACKEND_PORT}/api/v1/enum-types")
if status == 200:
    pass_("v3 backend health 200")
else:
    fail(f"v3 backend health {status}: {body[:200]}")
    with open("/tmp/v3-backend-test.log") as f:
        log(f.read()[-500:])
    kill_pid(v3_proc.pid)
    if ENV_MODIFIED:
        shutil.copy(V3_ENV_BACKUP, V3_ENV)
    sys.exit(1)

# ============================================================
# PHASE 4: 启 unified 8082
# ============================================================
banner("PHASE 4: 启 unified 8082 → 5002")

unified_log = open("/tmp/v3-frontend-test.log", "w")
unified_proc = subprocess.Popen(
    [PY, f"{DEPLOY_BUNDLE}/unified_server.py", f"{DEPLOYMENTS_DIR}/frontend_dist_files"],
    env={**env, "BACKEND_PORT": str(V3_BACKEND_PORT), "PYTHONUNBUFFERED": "1"},
    stdout=unified_log,
    stderr=subprocess.STDOUT,
)
info(f"v3 unified PID={unified_proc.pid}")
time.sleep(5)

if not port_listening(V3_FRONTEND_PORT):
    fail(f"v3 unified {V3_FRONTEND_PORT} 没启")
    with open("/tmp/v3-frontend-test.log") as f:
        log(f.read()[-1500:])
    kill_pid(v3_proc.pid)
    kill_pid(unified_proc.pid)
    if ENV_MODIFIED:
        shutil.copy(V3_ENV_BACKUP, V3_ENV)
    sys.exit(1)
pass_(f"v3 unified {V3_FRONTEND_PORT} listening")

# ============================================================
# PHASE 5: 验证 v3 业务
# ============================================================
banner("PHASE 5: 验证 v3 unified 8082 业务")

status, _ = http_get(f"http://127.0.0.1:{V3_FRONTEND_PORT}/")
if status == 200:
    pass_("v3 unified GET / 200")
else:
    fail(f"v3 unified GET / {status}")

status, body = http_post(
    f"http://127.0.0.1:{V3_FRONTEND_PORT}/api/v1/auth/login",
    {"username": "admin", "password": "admin123"},
)
token = ""
if status == 200:
    try:
        data = json.loads(body)
        token = data.get("data", {}).get("token", "")
    except Exception:
        pass
if token:
    pass_(f"v3 login OK (token len={len(token)})")
else:
    fail(f"v3 login FAIL: {body[:200]}")

if token:
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{V3_FRONTEND_PORT}/api/v1/menu-permission/visible",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    if status == 200:
        pass_("v3 BO endpoint (with token) 200")
    else:
        warn(f"v3 BO endpoint {status} (v3 可能用不同 endpoint)")

status, _ = http_get(f"http://127.0.0.1:{V3_FRONTEND_PORT}/api/v1/users/me")
if status == 401:
    pass_("v3 无 token BO endpoint 401 (符合预期)")
else:
    warn(f"v3 无 token NOT 401 (got: {status})")

# ============================================================
# PHASE 6: 验证 current 不受影响
# ============================================================
banner("PHASE 6: 验证 current 业务仍 alive")

status, _ = http_get(f"http://127.0.0.1:{V4_BACKEND_PORT}/api/v1/enum-types")
if status == 200:
    pass_(f"current {V4_BACKEND_PORT} 仍 200")
else:
    fail(f"current {V4_BACKEND_PORT} 受影响 (got: {status})")

status, _ = http_get(f"http://127.0.0.1:{V4_FRONTEND_PORT}/")
if status == 200:
    pass_(f"current {V4_FRONTEND_PORT} 仍 200")
else:
    fail(f"current {V4_FRONTEND_PORT} 受影响 (got: {status})")

try:
    current_link = os.readlink("/opt/app/current")
    if V4_VERSION in current_link:
        pass_(f"current 链接仍是 v4: {current_link}")
    else:
        fail(f"current 链接变了: {current_link}")
except Exception as e:
    fail(f"读 current 链接失败: {e}")

# ============================================================
# PHASE 7: 清理
# ============================================================
banner("PHASE 7: 清理 v3 5002/8082 + 恢复 .env")

# 恢复 .env 第一
if ENV_MODIFIED:
    shutil.copy(V3_ENV_BACKUP, V3_ENV)
    V3_ENV_BACKUP.unlink(missing_ok=True)
    pass_(".env 恢复")

kill_pid(v3_proc.pid)
kill_pid(unified_proc.pid)
time.sleep(2)
kill_port(V3_BACKEND_PORT)
kill_port(V3_FRONTEND_PORT)

if port_listening(V3_BACKEND_PORT):
    fail("v3 5002 没杀掉")
else:
    pass_("v3 5002 killed")

if port_listening(V3_FRONTEND_PORT):
    fail("v3 8082 没杀掉")
else:
    pass_("v3 8082 killed")

v3_log.close()
unified_log.close()
try:
    os.remove("/tmp/v3-backend-test.log")
    os.remove("/tmp/v3-frontend-test.log")
except Exception:
    pass

# ============================================================
# SUMMARY
# ============================================================
banner(f"SUMMARY: PASS={PASS}  FAIL={FAIL}  SKIP={SKIP}")

if FAIL == 0:
    log(f"{GREEN}✓ ALL PASS{NC} - rollback 修在并行模式下 OK")
    log(f"{GREEN}  v3 启 5002/8082 OK, current 5001/8081 不受影响{NC}")
    sys.exit(0)
else:
    log(f"{RED}✗ FAIL - rollback 修有问题{NC}")
    sys.exit(1)
