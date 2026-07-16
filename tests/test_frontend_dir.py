#!/usr/bin/env python3
"""
test_frontend_dir.py - 验证 deploy.sh/rollback.sh 的 FRONTEND_DIR 设置正确
用 Python 模拟部署目录结构, 启 unified 验证 8081 能服务 frontend
"""
import os
import sys
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

PASS = 0
FAIL = 0

def green(s): return f"\033[0;32m{s}\033[0m"
def red(s): return f"\033[0;31m{s}\033[0m"

def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(green(f"✓ PASS") + f" {name}")
        PASS += 1
    except AssertionError as e:
        print(red(f"✗ FAIL") + f" {name}: {e}")
        FAIL += 1
    except Exception as e:
        print(red(f"✗ ERROR") + f" {name}: {type(e).__name__}: {e}")
        FAIL += 1


# ==============================================================
# TEST 1: deploy.sh FRONTEND_DIR 应该指向 $DEPLOYMENTS_DIR/frontend_dist_files
# ==============================================================
def t1():
    deploy_sh = (TOOLS / "deploy.sh").read_text(encoding="utf-8")
    for line in deploy_sh.split("\n"):
        if "FRONTEND_DIR=" in line and "DEPLOYMENTS_DIR/frontend_dist_files" in line:
            return  # 找到正确的赋值
    raise AssertionError("deploy.sh 没有 FRONTEND_DIR=$DEPLOYMENTS_DIR/frontend_dist_files")

test("deploy.sh FRONTEND_DIR 指向 zip 解压根目录", t1)


# ==============================================================
# TEST 2: rollback.sh 启 unified 用 UNIFIED_FRONTEND_DIR
# ==============================================================
def t2():
    rb_sh = (TOOLS / "rollback.sh").read_text(encoding="utf-8")
    if "UNIFIED_FRONTEND_DIR" not in rb_sh:
        raise AssertionError("rollback.sh 没 UNIFIED_FRONTEND_DIR 变量")
    if "DEPLOYMENTS_DIR/frontend_dist_files" not in rb_sh:
        raise AssertionError("rollback.sh 没指 UNIFIED_FRONTEND_DIR=$DEPLOYMENTS_DIR/frontend_dist_files")

test("rollback.sh 用 UNIFIED_FRONTEND_DIR 指向 zip 根目录", t2)


# ==============================================================
# TEST 3: 实际启 unified 验证 8081 服务 frontend
# ==============================================================
def t3():
    # mock 目录
    mock = Path(tempfile.mkdtemp(prefix="frontend_test_"))
    try:
        # 模拟 zip 解压后的结构:
        # /mock/frontend_dist_files/index.html
        # /mock/v20260703_002/meta/server.py
        fdir = mock / "frontend_dist_files"
        fdir.mkdir()
        (fdir / "index.html").write_text("<html>v4 frontend</html>", encoding="utf-8")

        # mock backend 启动 - 启 unified 时 BACKEND_PORT=15001
        # 用 python 启一个 15001 mock server
        mock_backend_code = '''
import http.server, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.end_headers()
        self.wfile.write(b'{"success":true,"data":{"token":"mock_token"}}')
    def log_message(self, *a, **k): pass
http.server.HTTPServer(("127.0.0.1", 15001), H).serve_forever()
'''
        mock_backend_log = mock / "mock_backend.log"
        mock_backend_log.write_text("", encoding="utf-8")
        # 启 backend
        mock_backend = subprocess.Popen(
            [sys.executable, "-c", mock_backend_code],
            stdout=open(mock_backend_log, "w"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(2)

        # 启 unified
        unified_script = TOOLS / "unified_server.py"
        unified_log = mock / "mock_unified.log"
        unified_log.write_text("", encoding="utf-8")
        env = os.environ.copy()
        env["BACKEND_PORT"] = "15001"
        unified = subprocess.Popen(
            [sys.executable, str(unified_script), str(fdir)],
            env=env,
            stdout=open(unified_log, "w"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(3)

        # 测试 1: GET /index.html → 200 + 正确内容
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:18081/index.html", timeout=5)
            code = resp.status
            body = resp.read().decode()
            assert code == 200, f"HTTP {code}"
            assert body == "<html>v4 frontend</html>", f"body={body!r}"
        except Exception as e:
            log_content = unified_log.read_text(encoding="utf-8")
            raise AssertionError(f"GET /index.html failed: {e}, unified log:\n{log_content[:500]}")

        # 测试 2: GET /api/v1/test → 200 (proxy to mock backend)
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:18081/api/v1/test", timeout=5)
            code = resp.status
            assert code == 200, f"HTTP {code}"
        except Exception as e:
            raise AssertionError(f"GET /api/v1/test failed: {e}")

        # 测试 3: SPA fallback (GET /unknown → 200 + index.html)
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:18081/unknown", timeout=5)
            code = resp.status
            body = resp.read().decode()
            assert code == 200, f"HTTP {code}"
            assert body == "<html>v4 frontend</html>", f"SPA fallback 没回 index.html, body={body!r}"
        except Exception as e:
            raise AssertionError(f"SPA fallback failed: {e}")

        # 清理
        unified.terminate()
        mock_backend.terminate()
        unified.wait(timeout=5)
        mock_backend.wait(timeout=5)
    finally:
        shutil.rmtree(mock, ignore_errors=True)

test("启 unified 8081 能正确服务 frontend + proxy API + SPA fallback", t3)


# ==============================================================
# TEST 4: unified_server.py 头有 token cache 逻辑
# ==============================================================
def t4():
    unified = (TOOLS / "unified_server.py").read_text(encoding="utf-8")
    if "TOKEN_CACHE" not in unified:
        raise AssertionError("unified_server.py 缺 TOKEN_CACHE")
    if "LOGIN_PATHS" not in unified:
        raise AssertionError("unified_server.py 缺 LOGIN_PATHS")
    if "/api/v2/action/user.authenticate" not in unified:
        raise AssertionError("unified_server.py 缺 v4 login 端点")

test("unified_server.py 含 token 持久化 + v4 login 端点", t4)


# ==============================================================
print()
print("=" * 50)
print(f"TEST FRONTEND_DIR: PASS={PASS}  FAIL={FAIL}")
print("=" * 50)
sys.exit(0 if FAIL == 0 else 1)
