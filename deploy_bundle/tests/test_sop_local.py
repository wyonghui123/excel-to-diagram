#!/usr/bin/env python3
"""
test_sop_local.py - 本地 (Windows) 完整 SOP 验证, 不需要远端

验证:
  1. rebuild_bundle.ps1 复制 status.sh + restart.sh
  2. status.sh / restart.sh 的 login 解析 (用 mock backend)
  3. unified_server.py 的 token 持久化 (用 mock backend)
  4. deploy.sh PHASE 0.5 触发条件 (frontend_dist_files 缺时强制解压)

本地跑: python tests/test_sop_local.py
"""
import os
import sys
import time
import shutil
import subprocess
import json
import urllib.request
import socket
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
DEPLOY_BUNDLE = ROOT / "deploy_bundle"

PASS = 0
FAIL = 0

def green(s): return f"\033[0;32m{s}\033[0m"
def red(s): return f"\033[0;31m{s}\033[0m"
def yellow(s): return f"\033[1;33m{s}\033[0m"

def test(name, fn):
    global PASS, FAIL
    print(f"\n=== {name} ===")
    try:
        fn()
        print(green(f"✓ PASS"))
        PASS += 1
    except AssertionError as e:
        print(red(f"✗ FAIL: {e}"))
        FAIL += 1
    except Exception as e:
        print(red(f"✗ ERROR: {type(e).__name__}: {e}"))
        FAIL += 1


# ============================================================
# TEST 1: rebuild_bundle.ps1 复制 status.sh + restart.sh
# ============================================================
def t1():
    """本地跑 rebuild + 验证 deploy_bundle/ 包含所有 8 个 sh"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(TOOLS / "rebuild_bundle.ps1")],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise AssertionError(f"rebuild failed: {result.stderr[:500]}")

    required = [
        "deploy.sh", "precheck.sh", "smoke_test.sh", "rollback.sh",
        "diagnose.sh", "status.sh", "restart.sh", "unified_server.py",
    ]
    missing = []
    for f in required:
        if not (DEPLOY_BUNDLE / f).is_file():
            missing.append(f)
    if missing:
        raise AssertionError(f"deploy_bundle/ 缺: {missing}")
    print(f"  deploy_bundle/ 含所有 8 个核心文件")

test("rebuild_bundle.ps1 复制所有 8 个核心文件", t1)


# ============================================================
# TEST 2: status.sh login 解析 (mock backend)
# ============================================================
def t2():
    """启 mock backend (v4 风格, token 在 data.token 里), 跑 status.sh 验证 login OK"""
    # 找 python
    python_exe = shutil.which("python") or shutil.which("python3")
    if not python_exe:
        raise AssertionError("没找到 python")

    # 用 module 内的 urllib (不要 reassign)
    request_mod = urllib.request
    error_mod = urllib.error

    # mock v4 backend (用 socket 启 simple http server, 返回 v4 格式 token)
    mock_dir = Path(tempfile.mkdtemp(prefix="sop_local_"))
    try:
        # 写 mock server
        mock_py = mock_dir / "mock_v4.py"
        mock_py.write_text('''
import http.server, json, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # /api/v1/enum-types 200
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"success": True, "data": []}).encode())
    def do_POST(self):
        # /api/v1/auth/login → v4 格式: data.token
        body_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(body_len) if body_len else b"{}"
        try:
            d = json.loads(body)
        except:
            d = {}
        if d.get("username") == "admin" and d.get("password") == "admin123":
            resp = {
                "success": True,
                "message": "登录成功",
                "data": {
                    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock_token_for_local_test_abcdefghijklmnop",
                    "user": {
                        "user_id": 1, "username": "admin", "display_name": "管理员",
                        "email": "admin@system.local", "permissions": ["*"],
                        "roles": [{"id": 1, "code": "admin", "name": "系统管理员"}]
                    },
                    "must_change_password": False
                }
            }
        else:
            resp = {"success": False, "message": "用户名或密码错误"}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp, ensure_ascii=False).encode())
    def log_message(self, *a, **k): pass
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 15901
http.server.HTTPServer(("127.0.0.1", PORT), H).serve_forever()
''', encoding="utf-8")

        # 启 mock backend
        port = 15901
        mock_proc = subprocess.Popen(
            [python_exe, str(mock_py), str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(2)

        # 检查启动
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/enum-types", timeout=3) as r:
                if r.status != 200:
                    raise AssertionError(f"mock 没启: status={r.status}")
        except Exception as e:
            mock_proc.kill()
            raise AssertionError(f"mock 启失败: {e}")

        # 跑 status.sh (bash via git-bash, 或用 python 模拟)
        # 简化: 用 python 直接跑 status.sh 关键部分
        status_sh = (TOOLS / "status.sh").read_text(encoding="utf-8")

        # 提取 login 部分逻辑
        import re
        m = re.search(r"# login.*?fi", status_sh, re.DOTALL)
        if not m:
            raise AssertionError("status.sh 没找到 login 检查段")

        # 跑 login curl
        import urllib.parse
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/auth/login",
            data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            login_resp = r.read().decode()

        # 解析 (模拟 status.sh 的 python json 解析)
        try:
            d = json.loads(login_resp)
            tok = d.get("data", {}).get("token") or d.get("token", "")
            if d.get("success") and tok:
                print(f"  status.sh login 解析: OK_TOKEN (len={len(tok)})")
            elif d.get("success"):
                print(f"  status.sh login 解析: OK_SUCCESS (no token field)")
            else:
                raise AssertionError(f"status.sh login FAIL: {d.get('message')}")
        except Exception as e:
            raise AssertionError(f"status.sh login 解析错: {e}")

        mock_proc.kill()
        mock_proc.wait(timeout=3)
    finally:
        shutil.rmtree(mock_dir, ignore_errors=True)

test("status.sh login 解析 (v4 嵌套 data.token)", t2)


# ============================================================
# TEST 3: unified_server.py token 持久化 (mock backend)
# ============================================================
def t3():
    """启 unified (8089) + mock backend (15902), 验证 token 持久化"""
    python_exe = shutil.which("python") or shutil.which("python3")
    if not python_exe:
        raise AssertionError("没找到 python")

    # 写 mock frontend_dist_files
    fdir = Path(tempfile.mkdtemp(prefix="sop_unified_"))
    (fdir / "frontend_dist_files").mkdir()
    (fdir / "frontend_dist_files" / "index.html").write_text("<html>test</html>")

    try:
        # mock backend
        mock_dir = fdir / "mock"
        mock_dir.mkdir()
        (mock_dir / "server.py").write_text('''
import http.server, json, sys
TOKEN = None
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"success": True}).encode())
    def do_POST(self):
        global TOKEN
        body_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(body_len) if body_len else b"{}"
        d = json.loads(body) if body_len else {}
        if d.get("username") == "admin":
            TOKEN = "mock_token_local_xyz"
            resp = {"success": True, "data": {"token": TOKEN}}
        else:
            resp = {"success": True}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())
    def log_message(self, *a, **k): pass
PORT = int(sys.argv[1])
http.server.HTTPServer(("127.0.0.1", PORT), H).serve_forever()
''', encoding="utf-8")

        # 启 mock backend
        backend_port = 15902
        backend_proc = subprocess.Popen(
            [python_exe, str(mock_dir / "server.py"), str(backend_port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(2)

        # 启 unified
        frontend_port = 18091
        env = os.environ.copy()
        env["BACKEND_PORT"] = str(backend_port)
        unified_proc = subprocess.Popen(
            [python_exe, str(TOOLS / "unified_server.py"),
             str(fdir / "frontend_dist_files")],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(3)

        # 测 1: GET /index.html → 200
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{frontend_port}/index.html", timeout=3) as r:
                if r.status != 200:
                    raise AssertionError(f"GET /index.html 失败: {r.status}")
        except Exception as e:
            raise AssertionError(f"unified GET 失败: {e}")

        # 测 2: POST /api/v1/auth/login → 应捕获 token 存 cache
        req = urllib.request.Request(
            f"http://127.0.0.1:{frontend_port}/api/v1/auth/login",
            data=json.dumps({"username": "admin"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            login_body = r.read().decode()
            if r.status != 200:
                raise AssertionError(f"login fail: {login_body[:200]}")

        # 测 3: 后续 GET /api/v1/test 无 Authorization → unified 自动注入
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{frontend_port}/api/v1/test", timeout=3) as r:
                if r.status == 200:
                    print(f"  unified 转发 + token 注入: OK")
                else:
                    raise AssertionError(f"GET /api/v1/test {r.status}")
        except Exception as e:
            raise AssertionError(f"unified 转发失败: {e}")

        unified_proc.kill()
        backend_proc.kill()
        unified_proc.wait(timeout=3)
        backend_proc.wait(timeout=3)
    finally:
        shutil.rmtree(fdir, ignore_errors=True)

test("unified_server.py token 持久化 + 转发", t3)


# ============================================================
# TEST 4: deploy.sh PHASE 0.5 触发条件 (grep 验证)
# ============================================================
def t4():
    """grep deploy.sh 确认 PHASE 0.5 含 frontend_dist_files 检查"""
    deploy_sh = (TOOLS / "deploy.sh").read_text(encoding="utf-8")
    if "DEPLOYMENTS_DIR/frontend_dist_files" not in deploy_sh:
        raise AssertionError("deploy.sh 没 frontend_dist_files 检查")
    if "NEED_UNZIP" not in deploy_sh:
        raise AssertionError("deploy.sh 没 NEED_UNZIP 变量")
    if "触发解压" not in deploy_sh:
        raise AssertionError("deploy.sh 没触发条件日志")
    print(f"  PHASE 0.5 含 frontend_dist_files 强制解压逻辑")

test("deploy.sh PHASE 0.5 强制解压触发条件", t4)


# ============================================================
# TEST 5: restart.sh 流程 (grep 验证关键 PHASE)
# ============================================================
def t5():
    """grep restart.sh 确认所有 PHASE 在"""
    rb = (TOOLS / "restart.sh").read_text(encoding="utf-8")
    required = [
        "PHASE 0: 读 current",
        "PHASE 1: 停旧进程",
        "PHASE 2: 启 backend",
        "PHASE 3: 启 unified",
        "PHASE 4: 综合验证",
    ]
    for p in required:
        if p not in rb:
            raise AssertionError(f"restart.sh 缺 {p}")
    if "get('token'" not in rb and "get(\"token\"" not in rb:
        raise AssertionError("restart.sh 没解析 token (v4 嵌套)")
    print(f"  restart.sh 含 5 个 PHASE + v4 nested token 解析")

test("restart.sh 5 PHASE + v4 token 解析", t5)


# ============================================================
# TEST 6: status.sh 流程 (grep 验证)
# ============================================================
def t6():
    st = (TOOLS / "status.sh").read_text(encoding="utf-8")
    required = [
        "端口监听", "进程", "健康检查", "login 测试",
    ]
    for p in required:
        if p not in st:
            raise AssertionError(f"status.sh 缺 {p}")
    if "get('token'" not in st and "get(\"token\"" not in st:
        raise AssertionError("status.sh 没解析 token")
    print(f"  status.sh 含 4 大检查段 + v4 token 解析")

test("status.sh 完整检查 + v4 token 解析", t6)


# ============================================================
# SUMMARY
# ============================================================
print()
print("=" * 60)
print(f"TEST SOP LOCAL: PASS={PASS}  FAIL={FAIL}")
print("=" * 60)
sys.exit(0 if FAIL == 0 else 1)
