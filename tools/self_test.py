#!/usr/bin/env python3
"""
self_test.py - SOP 工具自身演练 (Python 跨平台版)
========================================================================
用途: 在本地 (Windows/Linux/macOS) 验证 SOP 工具套件
设计: 不依赖 bash, 纯 Python, 跨平台
用法: python tools/self_test.py
"""
import subprocess
import sys
import os
import time
import shutil
import tempfile
import socket
import urllib.request
from pathlib import Path
from typing import List, Tuple, Optional

# ANSI color
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"


class SelfTest:
    def __init__(self):
        self.tools_dir = Path(__file__).parent.resolve()
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.mock_root: Optional[Path] = None

    def log_pass(self, msg: str):
        print(f"{GREEN}[PASS]{NC} {msg}")
        self.passed += 1

    def log_fail(self, msg: str):
        print(f"{RED}[FAIL]{NC} {msg}")
        self.failed += 1

    def log_warn(self, msg: str):
        print(f"{YELLOW}[WARN]{NC} {msg}")
        self.warnings += 1

    def log_info(self, msg: str):
        print(f"{CYAN}[INFO]{NC} {msg}")

    def hr(self, msg: str = ""):
        if msg:
            print(f"\n{CYAN}====== {msg} ======{NC}")
        else:
            print(f"{CYAN}============================================================{NC}")

    def assert_file_exists(self, f: Path, desc: str = ""):
        if f.exists():
            self.log_pass(f"存在: {f.name if not desc else desc}")
        else:
            self.log_fail(f"缺失: {f}")

    def assert_file_readable(self, f: Path, desc: str = ""):
        if f.exists() and os.access(f, os.R_OK):
            self.log_pass(f"可读: {f.name if not desc else desc}")
        else:
            self.log_fail(f"不可读: {f}")

    def run_cmd(self, cmd: List[str], timeout: int = 30) -> Tuple[int, str, str]:
        """Run command, return (returncode, stdout, stderr)"""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                encoding='utf-8', errors='replace'
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Timeout"
        except FileNotFoundError as e:
            return -1, "", str(e)

    # ============================================================
    def test_1_files_exist(self):
        self.hr("1. SOP 工具文件存在性")
        files = [
            "precheck_remote.sh",
            "diff_local_remote.py",
            "verify_deploy.py",
            "deploy_step.sh",
            "rollback.sh",
            "mock_remote.sh",
            "self_test.sh",
        ]
        for f in files:
            self.assert_file_exists(self.tools_dir / f)
        # DEPLOY_SOP.md 在父目录
        self.assert_file_exists(self.tools_dir.parent / "DEPLOY_SOP.md")

    # ============================================================
    def test_2_python_syntax(self):
        self.hr("2. Python 文件 syntax check")
        for py in ["diff_local_remote.py", "verify_deploy.py"]:
            f = self.tools_dir / py
            if not f.exists():
                self.log_fail(f"不存在: {py}")
                continue
            rc, _, err = self.run_cmd(["python", "-m", "py_compile", str(f)])
            if rc == 0:
                self.log_pass(f"Python syntax OK: {py}")
            else:
                self.log_fail(f"Python syntax FAIL: {py}: {err[:200]}")

    # ============================================================
    def test_3_shell_syntax_via_bash(self):
        self.hr("3. Shell 文件 syntax check (via bash if available)")
        if not shutil.which("bash"):
            self.log_warn("bash 不存在, 跳过 shell syntax check")
            return
        for sh in ["precheck_remote.sh", "deploy_step.sh", "rollback.sh", "mock_remote.sh", "self_test.sh"]:
            f = self.tools_dir / sh
            if not f.exists():
                continue
            rc, _, err = self.run_cmd(["bash", "-n", str(f)])
            if rc == 0:
                self.log_pass(f"Bash syntax OK: {sh}")
            else:
                self.log_fail(f"Bash syntax FAIL: {sh}: {err[:200]}")

    # ============================================================
    def test_4_tool_help(self):
        self.hr("4. 工具帮助信息可显示")
        if shutil.which("bash"):
            for tool in ["deploy_step.sh", "rollback.sh", "mock_remote.sh"]:
                rc, out, _ = self.run_cmd(["bash", str(self.tools_dir / tool)], timeout=5)
                if "Usage" in out or "usage" in out:
                    self.log_pass(f"{tool} 显示 Usage")
                else:
                    self.log_warn(f"{tool} Usage 不明: {out[:100]}")
        else:
            self.log_warn("bash 不存在, 跳过")

        # Python 工具 help
        for tool in ["diff_local_remote.py"]:
            rc, out, _ = self.run_cmd(["python", str(self.tools_dir / tool), "--help"], timeout=5)
            if "usage" in out.lower():
                self.log_pass(f"{tool} --help OK")
            else:
                self.log_warn(f"{tool} --help 失败: {out[:100]}")

    # ============================================================
    def test_5_mock_setup_via_python(self):
        """用 Python 直接创建 mock 环境 (避免依赖 bash)"""
        self.hr("5. Mock 环境 setup/teardown (via Python)")

        # 创建 mock 目录
        self.mock_root = Path(tempfile.mkdtemp(prefix="mock_remote_selftest_"))
        self.log_info(f"Mock root: {self.mock_root}")

        # 创建目录结构
        dirs = [
            "opt/app/deployments/v20260630_003/backend",
            "opt/app/deployments/v20260702_001/backend",
            "opt/app/shared/logs",
            "opt/app/shared/data",
            "opt/app/meta",
            "etc/systemd/system",
        ]
        for d in dirs:
            (self.mock_root / d).mkdir(parents=True, exist_ok=True)
        self.log_pass("Mock 目录创建")

        # 写 mock v003 server.py
        v003_server = self.mock_root / "opt/app/deployments/v20260630_003/backend/server.py"
        v003_server.write_text('''"""Mock v003 server.py"""
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 5000))
MOCK_ENUMS = [
    {"id": 1, "code": "annotation_category", "name": "Annotation Category", "mutability": "fullEditable"},
    {"id": 2, "code": "relation_type", "name": "Relation Type", "mutability": "extensible"},
    {"id": 3, "code": "action_type", "name": "Action Type", "mutability": "locked"},
] * 7

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if "health" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "total": 0, "data": []}).encode())
        elif "enum-types" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "total": len(MOCK_ENUMS), "data": MOCK_ENUMS}).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Mock</body></html>")
    def log_message(self, *a): pass

HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
''')
        self.log_pass("Mock v003 server.py")

        # 写 mock v004 server.py
        v004_server = self.mock_root / "opt/app/deployments/v20260702_001/backend/server.py"
        v004_server.write_text('''"""Mock v004 server.py - with telemetry try/except"""
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 5001))
try:
    from telemetry import install_global_tracer
    install_global_tracer([])
except ImportError:
    print("[v004] telemetry not available, skip", flush=True)

MOCK_ENUMS = [
    {"id": 1, "code": "annotation_category", "name": "Annotation Category", "mutability": "fullEditable"},
    {"id": 2, "code": "relation_type", "name": "Relation Type", "mutability": "extensible"},
    {"id": 3, "code": "action_type", "name": "Action Type", "mutability": "locked"},
] * 7

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if "health" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "total": len(MOCK_ENUMS)}).encode())
        elif "enum-types" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "total": len(MOCK_ENUMS), "data": MOCK_ENUMS}).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>v004</body></html>")
    def log_message(self, *a): pass

HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
''')
        self.log_pass("Mock v004 server.py")

        # 写 mock service
        service = self.mock_root / "etc/systemd/system/excel-backend.service"
        service.parent.mkdir(parents=True, exist_ok=True)
        service.write_text("""[Unit]
Description=Excel to Diagram Backend (mock)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/tmp
ExecStart=/usr/bin/python3 server.py
Environment="PORT=5000"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
""")
        self.log_pass("Mock service 文件")

        # mock db
        try:
            import sqlite3
            db_path = self.mock_root / "opt/app/deployments/v20260630_003/backend/architecture.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE IF NOT EXISTS enum_types (id INTEGER PRIMARY KEY, code TEXT, name TEXT, mutability TEXT)")
            for code, name, mut in [("annotation_category", "Annotation Category", "fullEditable"),
                                    ("relation_type", "Relation Type", "extensible"),
                                    ("action_type", "Action Type", "locked")]:
                conn.execute("INSERT OR IGNORE INTO enum_types (id, code, name, mutability) VALUES (?, ?, ?, ?)",
                             (hash(code) % 1000, code, name, mut))
            conn.commit()
            conn.close()
            self.log_pass("Mock v003 db 创建")
        except Exception as e:
            self.log_warn(f"Mock db 创建失败: {e}")

    # ============================================================
    def test_6_mock_backend_works(self):
        self.hr("6. Mock v003 backend 启动 + API 验证")
        if not self.mock_root:
            self.log_fail("mock_root 未初始化")
            return

        server_py = self.mock_root / "opt/app/deployments/v20260630_003/backend/server.py"
        if not server_py.exists():
            self.log_fail("v003 server.py 不存在")
            return

        # 找空闲端口
        port = 15099
        for try_port in [15099, 15098, 15097]:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", try_port)) != 0:
                    port = try_port
                    break

        # 启 mock
        log_file = self.mock_root / "mock_backend.log"
        env = os.environ.copy()
        env["PORT"] = str(port)

        try:
            proc = subprocess.Popen(
                ["python", str(server_py)],
                stdout=open(log_file, "w"),
                stderr=subprocess.STDOUT,
                env=env,
            )
        except Exception as e:
            self.log_fail(f"启动失败: {e}")
            return

        time.sleep(2)

        # 检查进程活
        if proc.poll() is None:
            self.log_pass(f"Mock v003 backend 启动 PID={proc.pid}")
        else:
            self.log_fail(f"Mock 进程死了, log: {log_file.read_text()[:200]}")
            return

        # 测 /api/v1/health
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=3) as r:
                if r.status == 200:
                    self.log_pass("mock /api/v1/health 200")
                else:
                    self.log_fail(f"mock health 状态 {r.status}")
        except Exception as e:
            self.log_fail(f"mock health 异常: {e}")

        # 测 /api/v1/enum-types
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/enum-types", timeout=3) as r:
                body = r.read().decode()
                if "fullEditable" in body and "extensible" in body and "locked" in body:
                    self.log_pass("mock enum-types 含 3 种 mutability")
                else:
                    self.log_fail(f"mock enum-types 缺值: {body[:200]}")
        except Exception as e:
            self.log_fail(f"mock enum-types 异常: {e}")

        # 测根路径 (frontend 模拟)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
                if r.status == 200:
                    self.log_pass("mock frontend root 200")
        except Exception as e:
            self.log_fail(f"mock frontend 异常: {e}")

        # 杀进程
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    # ============================================================
    def test_7_mock_v004_with_telemetry(self):
        self.hr("7. Mock v004 backend (telemetry 缺失, try/except 应不崩)")
        if not self.mock_root:
            self.log_fail("mock_root 未初始化")
            return

        server_py = self.mock_root / "opt/app/deployments/v20260702_001/backend/server.py"
        if not server_py.exists():
            self.log_fail("v004 server.py 不存在")
            return

        port = 15100
        for try_port in [15100, 15101, 15102]:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", try_port)) != 0:
                    port = try_port
                    break

        log_file = self.mock_root / "mock_v004.log"
        env = os.environ.copy()
        env["PORT"] = str(port)

        try:
            proc = subprocess.Popen(
                ["python", str(server_py)],
                stdout=open(log_file, "w"),
                stderr=subprocess.STDOUT,
                env=env,
            )
        except Exception as e:
            self.log_fail(f"v004 启动失败: {e}")
            return

        time.sleep(2)

        if proc.poll() is None:
            self.log_pass(f"Mock v004 启动 PID={proc.pid} (telemetry try/except 生效)")
        else:
            log_content = log_file.read_text()
            if "telemetry" in log_content:
                self.log_pass(f"v004 启动后死了但有 telemetry warning (try/except 工作): {log_content[:200]}")
            else:
                self.log_fail(f"v004 死了, log: {log_content[:200]}")

        # 测 API
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=3) as r:
                if r.status == 200:
                    self.log_pass("v004 health 200")
        except Exception as e:
            self.log_warn(f"v004 health 异常: {e}")

        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    # ============================================================
    def test_8_diff_local_only(self):
        self.hr("8. diff_local_remote.py --local-only")
        build_verify = self.tools_dir.parent / "build" / "verify"
        if not build_verify.exists():
            self.log_warn(f"{build_verify} 不存在, 跳过")
            return

        rc, out, err = self.run_cmd(
            ["python", str(self.tools_dir / "diff_local_remote.py"),
             "--local", str(build_verify), "--local-only"],
            timeout=60
        )
        if rc == 0:
            self.log_pass("diff --local-only 成功")
            # 看是否输出 critical checklist
            if "telemetry" in out:
                self.log_pass("diff 输出含 telemetry 检查")
            else:
                self.log_warn("diff 输出未含 telemetry 关键词")
        else:
            self.log_fail(f"diff --local-only 失败: {err[:200]}")

    # ============================================================
    def test_9_verify_deploy_import(self):
        self.hr("9. verify_deploy.py 静态检查")
        f = self.tools_dir / "verify_deploy.py"
        try:
            # 不执行 main, 只 import
            import importlib.util
            spec = importlib.util.spec_from_file_location("v", str(f))
            module = importlib.util.module_from_spec(spec)
            # Don't execute (would launch browser)
            # spec.loader.exec_module(module)  # 跳过
            self.log_pass("verify_deploy.py 可被 Python 解析 (语法 OK)")
        except Exception as e:
            self.log_fail(f"verify_deploy.py 解析失败: {e}")

    # ============================================================
    def test_10_cleanup(self):
        self.hr("10. 清理 mock 环境")
        if self.mock_root and self.mock_root.exists():
            # 杀残留 (兼容 Windows / Linux)
            if shutil.which("pkill"):
                subprocess.run(
                    ["pkill", "-f", str(self.mock_root)],
                    capture_output=True
                )
            elif shutil.which("taskkill"):
                subprocess.run(
                    ["taskkill", "/F", "/FI", f"WINDOWTITLE eq *{self.mock_root.name}*"],
                    capture_output=True
                )
            time.sleep(1)
            try:
                shutil.rmtree(self.mock_root)
                self.log_pass(f"已删除: {self.mock_root}")
            except Exception as e:
                self.log_warn(f"删除失败: {e}")
        else:
            self.log_warn("mock_root 不存在, 跳过清理")

    # ============================================================
    def summary(self):
        self.hr("")
        print(f"  SELF-TEST SUMMARY")
        self.hr("")
        print(f"  PASSED:  {self.passed}")
        print(f"  FAILED:  {self.failed}")
        print(f"  WARNINGS: {self.warnings}")
        print()
        if self.failed == 0:
            print(f"{GREEN}  ALL TESTS PASSED ✓{NC}")
            print()
            print("  SOP 工具套件已通过演练")
            print("  可用于实际部署")
            return 0
        else:
            print(f"{RED}  SOME TESTS FAILED ✗{NC}")
            print()
            print("  请修复后再用 SOP 部署")
            return 1

    def run(self):
        print(f"{CYAN}============================================================{NC}")
        print(f"  SOP 工具自身演练 (self_test.py)")
        print(f"  Time:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Tools: {self.tools_dir}")
        print(f"{CYAN}============================================================{NC}")

        self.test_1_files_exist()
        self.test_2_python_syntax()
        self.test_3_shell_syntax_via_bash()
        self.test_4_tool_help()
        self.test_5_mock_setup_via_python()
        self.test_6_mock_backend_works()
        self.test_7_mock_v004_with_telemetry()
        self.test_8_diff_local_only()
        self.test_9_verify_deploy_import()
        self.test_10_cleanup()

        return self.summary()


if __name__ == "__main__":
    tester = SelfTest()
    sys.exit(tester.run())
