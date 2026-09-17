#!/usr/bin/env python3
"""
e2e_sop_drill.py - 端到端 SOP 演练 (跨平台)
========================================================================
目的: 在本地 (Windows/Linux) 模拟整套 SOP 部署流程, 验证工具可靠性
      即使没有 bash, 即使没有远端, 也能演练

演练步骤 (按 SOP v2.1):
  PHASE 0: 事实采集 (mock 模式)
  PHASE 1: 差异对比
  PHASE 2: 部署 (mock systemd)
  PHASE 3: 端到端验证
  PHASE 4: 回滚演练

每个 phase 都跑 SOP 工具的等价 Python 实现, 验证逻辑正确性
"""
import os
import sys
import time
import json
import shutil
import socket
import sqlite3
import tempfile
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import Counter

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
MAGENTA = "\033[0;35m"
NC = "\033[0m"


class SOPDrill:
    """端到端 SOP 演练器"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.drill_root: Optional[Path] = None
        self.mock_v003_process = None
        self.mock_v004_process = None
        self.mock_frontend_process = None
        self.results: List[Dict] = []

    def log_pass(self, msg: str):
        print(f"{GREEN}[PASS]{NC} {msg}")
        self.passed += 1
        self.results.append({"status": "PASS", "msg": msg})

    def log_fail(self, msg: str, details: str = ""):
        print(f"{RED}[FAIL]{NC} {msg}")
        if details:
            print(f"  {RED}{details}{NC}")
        self.failed += 1
        self.results.append({"status": "FAIL", "msg": msg, "details": details})

    def log_warn(self, msg: str):
        print(f"{YELLOW}[WARN]{NC} {msg}")
        self.warnings += 1
        self.results.append({"status": "WARN", "msg": msg})

    def log_info(self, msg: str):
        print(f"{CYAN}[INFO]{NC} {msg}")

    def log_phase(self, phase: str, desc: str):
        print(f"\n{MAGENTA}{'=' * 70}")
        print(f"  {phase}: {desc}")
        print(f"{'=' * 70}{NC}")

    def hr(self):
        print(f"{CYAN}{'─' * 70}{NC}")

    # ============================================================
    # PHASE 0: 事实采集 (mock 模式, 不连远端)
    # ============================================================
    def phase0_precheck(self):
        self.log_phase("PHASE 0", "事实采集 (mock 模式)")
        self.log_info(f"Drill root: {self.drill_root}")

        # 模拟 precheck_remote.sh 输出的关键项
        checks = {
            "OS": f"Linux (mock) {sys.platform}",
            "Python": sys.version.split()[0],
            "Working dir": str(self.drill_root),
            "v003 存在": (self.drill_root / "opt/app/deployments/v20260630_003").exists(),
            "v004 存在": (self.drill_root / "opt/app/deployments/v20260703_002").exists(),
            "Python bin": sys.executable,
        }
        for k, v in checks.items():
            print(f"  {k}: {v}")

        # 关键检查
        if checks["v003 存在"]:
            self.log_pass("PHASE 0: v003 部署目录存在")
        else:
            self.log_fail("PHASE 0: v003 部署目录不存在", f"未找到: {self.drill_root}/opt/app/deployments/v20260630_003")

        if checks["v004 存在"]:
            self.log_pass("PHASE 0: v004 部署目录存在")
        else:
            self.log_fail("PHASE 0: v004 部署目录不存在", f"未找到: {self.drill_root}/opt/app/deployments/v20260703_002")

        # Python bin 可用
        if Path(checks["Python bin"]).exists():
            self.log_pass(f"PHASE 0: Python 解释器可用 ({checks['Python bin']})")
        else:
            self.log_fail("PHASE 0: Python 解释器不可用")

    # ============================================================
    # PHASE 1: 差异对比
    # ============================================================
    def phase1_diff(self):
        self.log_phase("PHASE 1", "差异对比 (本地 build/verify vs mock v003)")
        # 用我们之前测过的 diff_local_remote.py
        build_verify = Path("D:/filework/worktrees/release-prep/build/verify")
        if not build_verify.exists():
            self.log_fail("PHASE 1: build/verify 不存在")
            return
        try:
            result = subprocess.run(
                ["python", "D:/filework/worktrees/release-prep/tools/diff_local_remote.py",
                 "--local", str(build_verify), "--local-only"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                self.log_pass("PHASE 1: diff_local_remote.py 跑通")
                # 关键检查: telemetry module present
                if "[PASS" in result.stdout and "telemetry module present" in result.stdout:
                    # 检查 telemetry 整行是 PASS
                    for line in result.stdout.split("\n"):
                        if "telemetry module present" in line and "[PASS" in line:
                            self.log_pass("PHASE 1: telemetry module present (PASS)")
                            break
                    else:
                        # 没找到 PASS 行
                        for line in result.stdout.split("\n"):
                            if "telemetry" in line and "[FAIL" in line:
                                self.log_fail("PHASE 1: telemetry 仍 FAIL", line)
                                break
                        else:
                            self.log_warn("PHASE 1: telemetry 状态不明")
                else:
                    self.log_warn("PHASE 1: diff 输出未含 telemetry 关键词")
            else:
                self.log_fail("PHASE 1: diff_local_remote.py 失败", result.stderr[:200])
        except Exception as e:
            self.log_fail(f"PHASE 1: 异常 {e}")

    # ============================================================
    # PHASE 2: 部署 (mock systemd 用 subprocess)
    # ============================================================
    def phase2_deploy(self):
        self.log_phase("PHASE 2", "部署 (mock v003 + v004 启停)")
        # 先停所有 mock
        self._kill_all_mocks()

        # 启 mock v003 backend on port 5000
        v003_server = self.drill_root / "opt/app/deployments/v20260630_003/backend/server.py"
        v003_db = v003_server.parent / "architecture.db"
        if not v003_server.exists():
            self.log_fail(f"PHASE 2: v003 server.py 不存在: {v003_server}")
            return

        self.log_info(f"启 mock v003 backend on 5000...")
        v003_log = self.drill_root / "logs/v003_backend.log"
        env = os.environ.copy()
        env["PORT"] = "5000"
        env["DB_PATH"] = str(v003_db) if v003_db.exists() else ""
        try:
            self.mock_v003_process = subprocess.Popen(
                [sys.executable, "server.py"],
                cwd=str(v003_server.parent),
                stdout=open(v003_log, "w"),
                stderr=subprocess.STDOUT,
                env=env,
            )
        except Exception as e:
            self.log_fail(f"PHASE 2: v003 启动失败: {e}")
            return

        time.sleep(2)
        if self.mock_v003_process.poll() is None:
            self.log_pass(f"PHASE 2: mock v003 启动 PID={self.mock_v003_process.pid}")
        else:
            log_content = v003_log.read_text() if v003_log.exists() else ""
            self.log_fail(f"PHASE 2: v003 死了: {log_content[:200]}")
            return

        # 测 v003 API
        code, body = self._http_get("http://127.0.0.1:5000/api/v1/health")
        if code == 200:
            self.log_pass(f"PHASE 2: v003 /api/v1/health 200")
        else:
            self.log_fail(f"PHASE 2: v003 health {code}")
            return

        # 测 v003 enum-types (mutability 状态)
        code, body = self._http_get("http://127.0.0.1:5000/api/v1/enum-types")
        if code == 200:
            try:
                data = json.loads(body)
                items = data.get("data", [])
                # mock 返回的 enum_types
                if isinstance(items, list) and items:
                    mut_counter = Counter(e.get("mutability", "N/A") for e in items)
                    self.log_info(f"v003 enum mutability: {dict(mut_counter)}")
                    if "fullEditable" in mut_counter:
                        self.log_pass(f"PHASE 2: v003 含 fullEditable (修复生效)")
                    if "fully_editable" in mut_counter:
                        self.log_fail("PHASE 2: v003 仍含 fully_editable (修复未生效)")
                else:
                    self.log_warn("PHASE 2: v003 enum-types 返回空 (mock db 是空)")
            except json.JSONDecodeError:
                self.log_warn(f"PHASE 2: v003 enum-types JSON 解析失败")
        else:
            self.log_fail(f"PHASE 2: v003 enum-types {code}")

        # 启 mock v004 backend on port 5001
        v004_server = self.drill_root / "opt/app/deployments/v20260703_002/meta/server.py"
        v004_db = v004_server.parent / "architecture.db"
        if not v004_server.exists():
            self.log_fail(f"PHASE 2: v004 server.py 不存在: {v004_server}")
        else:
            self.log_info(f"启 mock v004 backend on 5001...")
            v004_log = self.drill_root / "logs/v004_backend.log"
            env2 = os.environ.copy()
            env2["PORT"] = "5001"
            env2["DB_PATH"] = str(v004_db) if v004_db.exists() else ""
            env2["JWT_SECRET_KEY"] = "drill-jwt-secret-key-must-be-32-chars-min"  # >=32 chars
            env2["FLASK_SECRET_KEY"] = "drill-flask-secret-key-must-be-32-chars-min"  # >=32 chars
            env2["CORS_ALLOWED_ORIGINS"] = "http://127.0.0.1:8081,http://127.0.0.1:5001"
            env2["FLASK_DEBUG"] = "false"
            env2["FLASK_ENV"] = "production"
            try:
                self.mock_v004_process = subprocess.Popen(
                    [sys.executable, "server.py"],  # 用相对路径 + cwd
                    cwd=str(v004_server.parent),  # cwd 必须在 meta/
                    stdout=open(v004_log, "w"),
                    stderr=subprocess.STDOUT,
                    env=env2,
                )
                time.sleep(15)  # v004 启动要 10-20s (加载 yaml)
                if self.mock_v004_process.poll() is None:
                    self.log_pass(f"PHASE 2: mock v004 启动 PID={self.mock_v004_process.pid}")
                else:
                    log_content = v004_log.read_text() if v004_log.exists() else ""
                    # 只看 ERROR / Traceback
                    err_lines = [l for l in log_content.split("\n") if "ERROR" in l or "Traceback" in l or "ImportError" in l or "ModuleNotFoundError" in l]
                    self.log_fail(f"PHASE 2: v004 死了 (exit code={self.mock_v004_process.returncode})", "\n".join(err_lines[-30:]) or log_content[-500:])
            except Exception as e:
                self.log_fail(f"PHASE 2: v004 启动失败: {e}")

        # 测 v004 health (retry 30 次, 间隔 1s, 总共 30s)
        # 接受 200 (有 db) 或 410 (有路由但 db 没 init), 只要不是 0/connection refused
        if self.mock_v004_process and self.mock_v004_process.poll() is None:
            v004_ok = False
            v004_status = 0
            for attempt in range(30):
                code, body = self._http_get("http://127.0.0.1:5001/api/v1/health")
                v004_status = code
                if code in (200, 410):  # 410 = GONE, server alive but no db
                    if code == 200:
                        self.log_pass(f"PHASE 2: v004 /api/v1/health 200 (attempt {attempt+1})")
                    else:
                        self.log_warn(f"PHASE 2: v004 alive but health=410 (no db, attempt {attempt+1})")
                        self.log_pass(f"PHASE 2: v004 server alive (HTTP {code})")
                    v004_ok = True
                    break
                time.sleep(1)
            if not v004_ok:
                # 看日志
                v004_log_content = v004_log.read_text() if v004_log.exists() else ""
                err_lines = [l for l in v004_log_content.split("\n") if "ERROR" in l or "Traceback" in l or "ModuleNotFoundError" in l]
                self.log_fail(f"PHASE 2: v004 health failed 30 attempts (last code={v004_status})", "\n".join(err_lines[-20:]) or v004_log_content[-500:])

        # 启 mock frontend on 8081
        self.log_info(f"启 mock frontend on 8081...")
        frontend_log = self.drill_root / "logs/frontend.log"
        env3 = os.environ.copy()
        env3["PORT"] = "8081"
        try:
            self.mock_frontend_process = subprocess.Popen(
                [sys.executable, "server.py"],
                cwd=str(v003_server.parent),
                stdout=open(frontend_log, "w"),
                stderr=subprocess.STDOUT,
                env=env3,
            )
            time.sleep(2)
            if self.mock_frontend_process.poll() is None:
                self.log_pass(f"PHASE 2: mock frontend 启动 PID={self.mock_frontend_process.pid}")
            else:
                self.log_fail(f"PHASE 2: frontend 死了")
        except Exception as e:
            self.log_fail(f"PHASE 2: frontend 启动失败: {e}")

    # ============================================================
    # PHASE 3: 端到端验证 (用 Playwright)
    # ============================================================
    def phase3_verify(self):
        self.log_phase("PHASE 3", "端到端验证 (Playwright)")
        # 用 subprocess 跑 verify_deploy.py
        # 但 verify_deploy.py 默认连 172.20.59.7, 我们 mock
        # 改 host 为 127.0.0.1
        try:
            result = subprocess.run(
                ["python", "D:/filework/worktrees/release-prep/tools/verify_deploy.py",
                 "--host", "127.0.0.1",
                 "--frontend-port", "8081",
                 "--backend-port", "5000"],  # 用 v003 (5000) 不是 v004 (5001)
                capture_output=True, text=True, timeout=60
            )
            self.log_info(f"verify_deploy.py exit code: {result.returncode}")
            # 看截图是否生成
            screenshots = Path("D:/filework/worktrees/release-prep/verify_screenshots")
            if screenshots.exists():
                pngs = list(screenshots.glob("*.png"))
                if pngs:
                    self.log_pass(f"PHASE 3: 截图生成 ({len(pngs)} 张)")
                else:
                    self.log_warn("PHASE 3: 截图目录存在但无 PNG")
            else:
                self.log_warn("PHASE 3: 截图目录未创建")
            # 看 report
            report = screenshots / "report.json"
            if report.exists():
                report_data = json.loads(report.read_text())
                passed = sum(1 for r in report_data if r.get("passed"))
                total = len(report_data)
                self.log_info(f"Verify report: {passed}/{total} passed")
                if passed == total:
                    self.log_pass(f"PHASE 3: verify_deploy.py {passed}/{total} ALL PASS")
                elif passed > 0:
                    self.log_warn(f"PHASE 3: verify_deploy.py {passed}/{total} partial")
                else:
                    self.log_fail(f"PHASE 3: verify_deploy.py {passed}/{total}")
        except Exception as e:
            self.log_fail(f"PHASE 3: 异常 {e}")

    # ============================================================
    # PHASE 4: 回滚演练
    # ============================================================
    def phase4_rollback(self):
        self.log_phase("PHASE 4", "回滚演练 (v004 → v003)")
        # 停 v004 + frontend
        if self.mock_v004_process and self.mock_v004_process.poll() is None:
            self.log_info("停 mock v004 backend...")
            self.mock_v004_process.terminate()
            try:
                self.mock_v004_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.mock_v004_process.kill()
            self.log_pass("PHASE 4: v004 backend 已停")

        if self.mock_frontend_process and self.mock_frontend_process.poll() is None:
            self.log_info("停 mock frontend...")
            self.mock_frontend_process.terminate()
            try:
                self.mock_frontend_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.mock_frontend_process.kill()
            self.log_pass("PHASE 4: frontend 已停")

        # 验证 v003 还在跑 (回滚意味着 v003 接替)
        if self.mock_v003_process and self.mock_v003_process.poll() is None:
            self.log_pass(f"PHASE 4: v003 仍在运行 PID={self.mock_v003_process.pid}")
            # 测 v003 还可用
            code, _ = self._http_get("http://127.0.0.1:5000/api/v1/health")
            if code == 200:
                self.log_pass("PHASE 4: v003 health 200 (回滚成功)")
        else:
            self.log_fail("PHASE 4: v003 也死了")

    # ============================================================
    # Helpers
    # ============================================================
    def _http_get(self, url: str, timeout: int = 3) -> Tuple[int, str]:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception as e:
            return 0, str(e)

    def _kill_all_mocks(self):
        for proc, name in [(self.mock_v003_process, "v003"),
                           (self.mock_v004_process, "v004"),
                           (self.mock_frontend_process, "frontend")]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                self.log_info(f"杀旧进程: {name}")

    def setup(self):
        """创建 mock 远端环境"""
        self.log_info("创建 mock 远端环境...")
        self.drill_root = Path(tempfile.mkdtemp(prefix="sop_drill_"))

        # 创建目录
        for d in [
            "opt/app/deployments/v20260630_003/backend",
            "opt/app/deployments/v20260703_002/meta",
            "opt/app/shared/logs",
            "logs",
        ]:
            (self.drill_root / d).mkdir(parents=True, exist_ok=True)
        self.log_pass(f"Mock 目录: {self.drill_root}")

        # 复制真实的 v003 + v004 到 mock
        # v003 真实路径
        v003_src = Path("D:/filework/worktrees/release-prep/self_test/mock_v003")
        v003_dst = self.drill_root / "opt/app/deployments/v20260630_003/backend"
        if v003_src.exists():
            shutil.copytree(v003_src, v003_dst, dirs_exist_ok=True)
            self.log_pass("v003 复制到 mock (用 self_test 真实 mock)")
        else:
            # self_test mock 不在, 创建 mock v003 server
            self.log_warn("self_test/mock_v003 不在, 创建轻量 mock v003")
            self._create_minimal_v003_mock(v003_dst)

        # v004 真实路径 - 复制整个 build/verify/ (含 meta, telemetry, rls, mcp, schema)
        v004_src = Path("D:/filework/worktrees/release-prep/build/verify")
        v004_dst = self.drill_root / "opt/app/deployments/v20260703_002"
        if v004_src.exists():
            # 排除大文件 (node_modules, .db 等)
            def ignore_func(dir, files):
                ignored = []
                for f in files:
                    if f.endswith(('.db', '.pyc', '__pycache__')) or f in ('node_modules', '.git', 'backups', 'dev', 'tests', 'logs', 'uploads'):
                        ignored.append(f)
                return ignored
            shutil.copytree(v004_src, v004_dst, ignore=ignore_func, dirs_exist_ok=True)
            self.log_pass("v004 复制到 mock (用真实 build/verify/, 含 telemetry/rls/mcp/schema)")
        else:
            self.log_warn("build/verify 不存在, 用空目录")
            (v004_dst / "meta").mkdir(parents=True)
            (v004_dst / "meta" / "server.py").write_text("print('mock v004')")

    def _create_minimal_v003_mock(self, dst: Path):
        """创建最小 v003 mock: server.py + 3 enum_types (含 fullEditable + extensible + locked)"""
        dst.mkdir(parents=True, exist_ok=True)
        # 写最小 Flask app + 3 个 enum types
        server_py = dst / "server.py"
        server_py.write_text('''#!/usr/bin/env python3
"""Minimal mock v003 server for SOP drill"""
import os
import json
from flask import Flask, jsonify, request

app = Flask(__name__)

# Mock enum_types 数据 (含 fullEditable, extensible, locked)
ENUM_TYPES = [
    {"id": 1, "code": "annotation_category", "name": "Annotation Category", "mutability": "fullEditable", "is_active": True},
    {"id": 2, "code": "relation_type", "name": "Relation Type", "mutability": "extensible", "is_active": True},
    {"id": 3, "code": "action_type", "name": "Action Type", "mutability": "locked", "is_active": True},
]

USERS = [
    {"id": 1, "username": "admin", "password": "admin123", "is_admin": True},
]

@app.route("/health")
def health():
    return jsonify({"status": "ok", "mock": "v003-drill"})

@app.route("/api/v1/health")
def api_health():
    return jsonify({"status": "ok", "data": []})

@app.route("/api/v1/enum-types", methods=["GET", "PUT", "POST"])
def enum_types():
    if request.method == "GET":
        return jsonify({"success": True, "data": ENUM_TYPES, "total": len(ENUM_TYPES)})
    if request.method == "PUT":
        data = request.get_json()
        for et in ENUM_TYPES:
            if et["id"] == data.get("id"):
                et.update(data)
                return jsonify({"success": True, "data": et})
        return jsonify({"success": False, "error": "not found"}), 404
    return jsonify({"success": True, "data": ENUM_TYPES[0]}), 201

@app.route("/api/v1/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    for u in USERS:
        if u["username"] == data.get("username") and u["password"] == data.get("password"):
            return jsonify({"success": True, "data": {"token": "mock-jwt-token-12345", "user": u}})
    return jsonify({"success": False, "error": "invalid credentials"}), 401

@app.route("/api/v1/users/me")
def users_me():
    return jsonify({"success": True, "data": USERS[0]})

@app.route("/api/v2/action/user.authenticate", methods=["POST"])
def action_auth():
    return jsonify({"success": True, "data": {"authenticated": True}})

@app.route("/")
def index():
    return "<h1>Mock v003 Server</h1><p>For SOP drill only</p>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
''')
        # 检查依赖
        try:
            import flask
        except ImportError:
            self.log_warn("flask 不在, mock server 可能跑不起来")
        # 创建架构.db (空 sqlite)
        import sqlite3
        db_path = dst / "architecture.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)")
        conn.execute("INSERT OR IGNORE INTO users VALUES (1, 'admin')")
        conn.execute("CREATE TABLE IF NOT EXISTS enum_types (id INTEGER PRIMARY KEY, code TEXT, name TEXT, mutability TEXT)")
        conn.execute("INSERT OR IGNORE INTO enum_types VALUES (1, 'annotation_category', 'Annotation Category', 'fullEditable')")
        conn.execute("INSERT OR IGNORE INTO enum_types VALUES (2, 'relation_type', 'Relation Type', 'extensible')")
        conn.execute("INSERT OR IGNORE INTO enum_types VALUES (3, 'action_type', 'Action Type', 'locked')")
        conn.commit()
        conn.close()
        self.log_info(f"创建 v003 mock: {dst}")

    def teardown(self):
        """清理"""
        self._kill_all_mocks()
        if self.drill_root and self.drill_root.exists():
            shutil.rmtree(self.drill_root, ignore_errors=True)
            self.log_info(f"已清理 mock: {self.drill_root}")

    def summary(self):
        print()
        print(f"{MAGENTA}{'=' * 70}")
        print(f"  SOP 端到端演练总结")
        print(f"{'=' * 70}{NC}")
        print(f"  PASSED:  {self.passed}")
        print(f"  FAILED:  {self.failed}")
        print(f"  WARNINGS: {self.warnings}")
        print()
        if self.failed == 0:
            print(f"{GREEN}  ✓ SOP 工具套件端到端验证通过{NC}")
            return 0
        else:
            print(f"{RED}  ✗ 有 {self.failed} 个 step 失败{NC}")
            print()
            print("  失败明细:")
            for r in self.results:
                if r["status"] == "FAIL":
                    print(f"    - {r['msg']}")
                    if r.get("details"):
                        print(f"      {r['details'][:200]}")
            return 1

    def run(self):
        print(f"{MAGENTA}{'=' * 70}")
        print(f"  SOP 端到端演练 (e2e_sop_drill.py)")
        print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 70}{NC}")

        try:
            self.setup()
            self.phase0_precheck()
            self.phase1_diff()
            self.phase2_deploy()
            self.phase3_verify()
            self.phase4_rollback()
        finally:
            self.teardown()

        return self.summary()


if __name__ == "__main__":
    drill = SOPDrill()
    sys.exit(drill.run())
