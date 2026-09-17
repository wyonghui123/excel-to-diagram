"""
test_precheck_smoke.py - 验证 precheck.sh + smoke_test.sh 自身
"""
import subprocess
import time
import sys
import os
import tempfile
import shutil
import urllib.request
import json
from pathlib import Path

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"

results = {"passed": 0, "failed": 0}

def log_pass(msg): print(f"{GREEN}[PASS]{NC} {msg}"); results["passed"] += 1
def log_fail(msg, detail=""): print(f"{RED}[FAIL]{NC} {msg}\n  {detail}"); results["failed"] += 1
def log_warn(msg): print(f"{YELLOW}[WARN]{NC} {msg}")

# Windows 没 bash, 改用 Python 模拟 precheck + smoke 逻辑
def python_precheck(version, port, frontend_port=8081, zip_path="", db_source=""):
    """模拟 precheck.sh 的 7 项检查 (Python 版)"""
    checks = []

    # Check 1: Python
    checks.append(("Python 可用", "pass" if sys.executable else "fail"))

    # Check 2: 磁盘
    test_root = Path(tempfile.gettempdir())
    free_mb = shutil.disk_usage(test_root).free / 1024 / 1024
    checks.append((f"磁盘空间: {int(free_mb)}MB", "pass" if free_mb >= 500 else "fail"))

    # Check 3: systemctl (Windows 没有)
    checks.append(("systemctl", "warn"))

    # Check 4: 端口
    import socket
    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
    if is_port_in_use(port):
        checks.append((f"端口 {port} 占用", "fail"))
    else:
        checks.append((f"端口 {port} 空闲", "pass"))
    if is_port_in_use(frontend_port):
        checks.append((f"端口 {frontend_port} 占用", "warn"))
    else:
        checks.append((f"端口 {frontend_port} 空闲", "pass"))

    # Check 5: zip
    if zip_path and os.path.exists(zip_path):
        size = os.path.getsize(zip_path)
        checks.append((f"zip 存在 ({size} bytes)", "pass"))
    elif zip_path:
        checks.append((f"zip 不存在: {zip_path}", "fail"))
    else:
        checks.append(("zip 未指定", "warn"))

    # Check 6: db
    if db_source and os.path.exists(db_source):
        checks.append((f"db 源可用", "pass"))
    elif db_source:
        checks.append((f"db 源不存在: {db_source}", "fail"))
    else:
        checks.append(("db 源未指定", "warn"))

    # Check 7: 网络
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2).close()
        checks.append(("外网可达", "pass"))
    except:
        checks.append(("外网不可达", "warn"))

    return checks


def python_smoke(backend_port, frontend_port):
    """模拟 smoke_test.sh 的 5 项测试"""
    tests = []

    # Test 1: backend health
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{backend_port}/health", timeout=3) as r:
            tests.append((f"backend /health = {r.status}", "pass" if r.status in (200, 410) else "fail"))
    except Exception as e:
        tests.append((f"backend /health 不可达: {e}", "fail"))

    # Test 2: frontend /
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{frontend_port}/", timeout=3) as r:
            tests.append((f"frontend / = {r.status}", "pass" if r.status == 200 else "fail"))
    except Exception as e:
        tests.append((f"frontend / 不可达: {e}", "fail"))

    # Test 3: login
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{frontend_port}/api/v1/auth/login",
            data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read())
            if "token" in str(data) or data.get("success"):
                tests.append(("login 成功", "pass"))
                token = data.get("data", {}).get("token", "")
            else:
                tests.append(("login 失败", "fail"))
                token = ""
    except Exception as e:
        tests.append((f"login 不可达: {e}", "fail"))
        token = ""

    # Test 4: enum-types
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{frontend_port}/api/v1/enum-types", timeout=3) as r:
            data = json.loads(r.read())
            items = data.get("data", [])
            has_mut = any("mutability" in e for e in items)
            tests.append((f"enum-types 含 mutability ({len(items)} 条)", "pass" if has_mut else "fail"))
    except Exception as e:
        tests.append((f"enum-types 不可达: {e}", "fail"))

    # Test 5: users/me (用 token)
    if token:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{frontend_port}/api/v1/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=3) as r:
                data = json.loads(r.read())
                if "admin" in str(data) or data.get("success"):
                    tests.append(("users/me 用 token 成功", "pass"))
                else:
                    tests.append(("users/me 异常", "fail"))
        except Exception as e:
            tests.append((f"users/me err: {e}", "fail"))
    else:
        tests.append(("users/me (无 token, 跳过)", "warn"))

    return tests


def main():
    print(f"{CYAN}=== 验证 precheck + smoke 自身 ==={NC}\n")

    # ============================================================
    # Test 1: precheck 7 项逻辑
    # ============================================================
    print(f"\n{CYAN}[Test 1] precheck 7 项逻辑 (Python 模拟){NC}")
    checks = python_precheck("v20260703_002", 5001, 8081, "", "")
    for name, result in checks:
        if result == "pass":
            log_pass(f"precheck: {name}")
        elif result == "fail":
            log_fail(f"precheck: {name}")
        else:
            log_warn(f"precheck: {name}")

    # ============================================================
    # Test 2: smoke 5 项逻辑
    # ============================================================
    print(f"\n{CYAN}[Test 2] smoke 5 项逻辑 (需要 mock 服务){NC}")
    # 起 mock v004 (5001) + unified (8081)
    test_root = Path(tempfile.mkdtemp(prefix="smoke_test_"))
    deploy_root = test_root / "deploy"
    deploy_root.mkdir()
    (deploy_root / "shared" / "logs").mkdir(parents=True)
    (deploy_root / "backups").mkdir()
    (deploy_root / "deployments" / "v20260703_002" / "meta").mkdir(parents=True)
    (deploy_root / "deployments" / "v20260703_002" / "frontend_dist_files").mkdir(parents=True)
    (deploy_root / "deployments" / "v20260703_002" / "frontend_dist_files" / "index.html").write_text("<h1>v004</h1>")

    py = sys.executable
    # server.py
    server_py = '''
import os, json
from flask import Flask, jsonify, request
app = Flask(__name__)
USERS = [{"id": 1, "username": "admin", "password": "admin123"}]
ENUM_TYPES = [
    {"id": 1, "code": "a", "mutability": "fullEditable"},
    {"id": 2, "code": "b", "mutability": "extensible"},
    {"id": 3, "code": "c", "mutability": "locked"},
]
@app.route("/health")
def h(): return jsonify({"status": "ok"})
@app.route("/api/v1/health")
def h2(): return jsonify({"status": "ok", "data": []})
@app.route("/api/v1/enum-types")
def e(): return jsonify({"success": True, "data": ENUM_TYPES})
@app.route("/api/v1/users/me")
def me(): return jsonify({"success": True, "data": USERS[0]})
@app.route("/api/v1/auth/login", methods=["POST"])
def login():
    d = request.get_json()
    for u in USERS:
        if u["username"] == d.get("username") and u["password"] == d.get("password"):
            return jsonify({"success": True, "data": {"token": "mock-token-12345", "user": u}})
    return jsonify({"success": False}), 401
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
'''
    server_path = deploy_root / "deployments" / "v20260703_002" / "meta" / "server.py"
    server_path.write_text(server_py)

    # 复制 unified_server.py
    tools_dir = Path("D:/filework/worktrees/release-prep/tools")
    unified_dst = deploy_root / "unified_server.py"
    shutil.copy(tools_dir / "unified_server.py", unified_dst)

    # 启 backend
    backend_proc = subprocess.Popen(
        [py, "server.py"],
        cwd=str(server_path.parent),
        env={**os.environ, "PORT": "5001", "JWT_SECRET_KEY": "x"*40, "FLASK_SECRET_KEY": "y"*40, "CORS_ALLOWED_ORIGINS": "*", "FLASK_DEBUG": "false", "FLASK_ENV": "production"},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    time.sleep(3)
    if backend_proc.poll() is None:
        log_pass("mock v004 backend 启 PID={}".format(backend_proc.pid))
    else:
        log_fail("mock backend 死了")
        return 1

    # 启 unified
    frontend_dir = deploy_root / "deployments" / "v20260703_002" / "frontend_dist_files"
    u_proc = subprocess.Popen(
        [py, str(unified_dst), str(frontend_dir)],
        env={**os.environ, "BACKEND_PORT": "5001"},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    time.sleep(2)
    if u_proc.poll() is None:
        log_pass("mock unified_server 启 PID={}".format(u_proc.pid))
    else:
        log_fail("mock unified 死了")
        return 1

    # 跑 smoke
    print(f"\n  Running smoke tests...")
    tests = python_smoke(5001, 8081)
    for name, result in tests:
        if result == "pass":
            log_pass(f"smoke: {name}")
        elif result == "fail":
            log_fail(f"smoke: {name}")
        else:
            log_warn(f"smoke: {name}")

    # ============================================================
    # SUMMARY
    # ============================================================
    print(f"\n{CYAN}=== Test Summary ==={NC}")
    print(f"  PASSED: {results['passed']}")
    print(f"  FAILED: {results['failed']}")

    # 清理
    for proc in [backend_proc, u_proc]:
        if proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=3)
            except: proc.kill()
    shutil.rmtree(test_root, ignore_errors=True)

    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
