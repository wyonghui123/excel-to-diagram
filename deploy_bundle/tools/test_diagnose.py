"""
test_diagnose.py - 验证 diagnose.sh 自身
Windows 没 bash, 改用 Python 模拟 diagnose 的所有检查
"""
import os
import sys
import time
import json
import socket
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
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


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def python_diagnose(backend_port, frontend_port, deploy_root):
    """模拟 diagnose.sh 的所有检查"""
    diag_ok = 0
    diag_warn = 0
    diag_fail = 0
    findings = []  # 收集所有发现, 给 summary

    # [1] 部署状态
    current_link = deploy_root / "current"
    if current_link.exists():
        log_pass("[1a] current 链接存在")
    else:
        log_fail("[1a] current 链接不存在")

    deployments = deploy_root / "deployments"
    if deployments.exists():
        versions = [d.name for d in deployments.iterdir() if d.is_dir()]
        log_pass(f"[1b] 发现 {len(versions)} 个版本: {versions}")
    else:
        log_fail("[1b] deployments 不存在")

    # [2] 端口
    for port in [backend_port, frontend_port]:
        if is_port_in_use(port):
            log_pass(f"[2] 端口 {port} 监听")
        else:
            log_fail(f"[2] 端口 {port} 未监听")
            findings.append(f"port-{port}-not-listening")

    # [3] 进程
    procs = []
    for p in psutil_iter():
        if "server.py" in p or "unified_server" in p:
            procs.append(p)
    log_pass(f"[3] 发现 {len(procs)} server 进程")

    # [4] 健康
    for port in [backend_port]:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                log_pass(f"[4a] backend /health = {r.status}")
        except Exception as e:
            log_fail(f"[4a] backend /health err: {e}")
            findings.append(f"health-{port}-failed")

    # [5] API
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{frontend_port}/api/v1/enum-types", timeout=2) as r:
            data = json.loads(r.read())
            items = data.get("data", [])
            has_mut = any("mutability" in e for e in items)
            if has_mut:
                log_pass(f"[5] enum-types 含 mutability ({len(items)} 条)")
            else:
                log_fail("[5] enum-types 无 mutability")
    except Exception as e:
        log_fail(f"[5] enum-types err: {e}")

    # [6] 资源
    free_mb = shutil.disk_usage(deploy_root).free / 1024 / 1024
    if free_mb >= 500:
        log_pass(f"[6] 磁盘: {int(free_mb)}MB")
    else:
        log_warn(f"[6] 磁盘紧: {int(free_mb)}MB")

    return findings


def psutil_iter():
    """简易版 ps -ef (跨平台, 不依赖 psutil)"""
    import subprocess
    try:
        if sys.platform == "win32":
            # PowerShell 方式
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Process python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
                capture_output=True, text=True, timeout=5
            )
            return [f"python PID {l.strip()}" for l in r.stdout.split("\n") if l.strip()]
        else:
            r = subprocess.run(["pgrep", "-f", "python"], capture_output=True, text=True, timeout=5)
            return [f"python PID {l.strip()}" for l in r.stdout.split("\n") if l.strip()]
    except Exception:
        return []


def main():
    print(f"{CYAN}=== 验证 diagnose 自身 ==={NC}\n")

    # ============================================================
    # Test 1: 在无服务环境跑 diagnose (应 FAIL)
    # ============================================================
    print(f"\n{CYAN}[Test 1] 在 mock 环境跑 diagnose (无服务, 应 FAIL){NC}")
    test_root = Path(tempfile.mkdtemp(prefix="diag_test_"))
    deploy_root = test_root / "deploy"
    deploy_root.mkdir()
    # Windows 创建 symlink 需权限, 改用普通目录表示 current
    (deploy_root / "current").mkdir()  # placeholder
    (deploy_root / "deployments" / "v20260703_002" / "meta").mkdir(parents=True)
    (deploy_root / "shared" / "logs").mkdir(parents=True)

    findings = python_diagnose(5001, 8081, deploy_root)
    if "port-5001-not-listening" in findings and "port-8081-not-listening" in findings:
        log_pass("diagnose 正确发现端口未监听")
    else:
        log_fail("diagnose 漏报", str(findings))

    # ============================================================
    # Test 2: 在 mock 服务环境跑 diagnose (应 PASS)
    # ============================================================
    print(f"\n{CYAN}[Test 2] 起 mock v004 (5001) + unified (8081) 再 diagnose{NC}")
    py = sys.executable
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
            return jsonify({"success": True, "data": {"token": "tok", "user": u}})
    return jsonify({"success": False}), 401
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
'''
    server_path = deploy_root / "deployments" / "v20260703_002" / "meta" / "server.py"
    server_path.write_text(server_py)

    tools_dir = Path("D:/filework/release-prep-worktree/tools")
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

    # 启 unified
    frontend_dir = deploy_root / "deployments" / "v20260703_002" / "frontend_dist_files"
    frontend_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dir / "index.html").write_text("<h1>v004</h1>")

    u_proc = subprocess.Popen(
        [py, str(unified_dst), str(frontend_dir)],
        env={**os.environ, "BACKEND_PORT": "5001"},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    time.sleep(2)

    findings = python_diagnose(5001, 8081, deploy_root)
    if "port-5001-not-listening" not in findings and "port-8081-not-listening" not in findings:
        log_pass("diagnose 在服务正常时通过")
    else:
        log_fail("diagnose 误报", str(findings))

    # 清理
    backend_proc.terminate()
    u_proc.terminate()
    try: backend_proc.wait(timeout=3)
    except: backend_proc.kill()
    try: u_proc.wait(timeout=3)
    except: u_proc.kill()
    time.sleep(2)
    shutil.rmtree(test_root, ignore_errors=True)

    # ============================================================
    # SUMMARY
    # ============================================================
    print(f"\n{CYAN}=== Test Summary ==={NC}")
    print(f"  PASSED: {results['passed']}")
    print(f"  FAILED: {results['failed']}")
    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
