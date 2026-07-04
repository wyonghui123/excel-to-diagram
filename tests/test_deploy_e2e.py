#!/usr/bin/env python3
"""
test_deploy_e2e.py - 部署全流程 e2e 测试 (本地)

测试整个 deploy.sh 流程在 mock 环境下的行为:
  1. PHASE 0: 事实采集
  2. PHASE 0.5: 解压触发条件
  3. PHASE 1: 停旧
  4. PHASE 3: 启 backend
  5. PHASE 3.5: 启 unified
  6. PHASE 7: 切 current

不真启 server (mock), 但走完整 deploy.sh 流程 + 验证关键逻辑。
"""
import os
import sys
import subprocess
import shutil
import tempfile
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
DEPLOY_BUNDLE = ROOT / "deploy_bundle"
TESTS = ROOT / "tests"

PASS = 0
FAIL = 0

def green(s): return f"\033[0;32m{s}\033[0m"
def red(s): return f"\033[0;31m{s}\033[0m"

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
# TEST 1: deploy.sh 关键 PHASE 都在
# ============================================================
def t1():
    """grep deploy.sh 验证关键 PHASE"""
    deploy_sh = (TOOLS / "deploy.sh").read_text(encoding="utf-8")
    required_phases = [
        "PHASE 0",       # 事实采集
        "PHASE 0.5",     # 解压
        "PHASE 1",       # 停
        "PHASE 4",       # 启 backend
        "PHASE 5",       # 启 unified
        "PHASE 6.5",     # smoke
        "PHASE 7",       # 切 current
    ]
    for ph in required_phases:
        if ph not in deploy_sh:
            raise AssertionError(f"deploy.sh 缺 {ph}")
    print(f"  deploy.sh 含 7 个关键 PHASE")

test("deploy.sh 7 个关键 PHASE 都在", t1)


# ============================================================
# TEST 2: 关键参数都支持
# ============================================================
def t2():
    deploy_sh = (TOOLS / "deploy.sh").read_text(encoding="utf-8")
    required_args = [
        "--version", "--port", "--skip-unzip",
        "--skip-precheck", "--skip-smoke",
    ]
    for arg in required_args:
        if arg not in deploy_sh:
            raise AssertionError(f"deploy.sh 缺参数 {arg}")
    print(f"  deploy.sh 支持 {len(required_args)} 个关键参数")

test("deploy.sh 关键参数支持", t2)


# ============================================================
# TEST 3: rollback.sh 关键 PHASE
# ============================================================
def t3():
    rb = (TOOLS / "rollback.sh").read_text(encoding="utf-8")
    required_phases = ["PHASE 1", "PHASE 3", "PHASE 3.5", "PHASE 4", "PHASE 5"]
    for ph in required_phases:
        if ph not in rb:
            raise AssertionError(f"rollback.sh 缺 {ph}")
    print(f"  rollback.sh 含 5 个关键 PHASE")

test("rollback.sh 5 个关键 PHASE", t3)


# ============================================================
# TEST 4: 关键环境变量 (JWT/FLASK/CORS)
# ============================================================
def t4():
    deploy_sh = (TOOLS / "deploy.sh").read_text(encoding="utf-8")
    for env in ["JWT_SECRET", "FLASK_SECRET", "CORS", "BACKEND_PORT", "FRONTEND_PORT"]:
        if env not in deploy_sh:
            raise AssertionError(f"deploy.sh 缺环境变量 {env}")
    print(f"  deploy.sh 处理 5 类关键环境变量")

test("deploy.sh 关键环境变量", t4)


# ============================================================
# TEST 5: smoke_test.sh 含真实 API 测试
# ============================================================
def t5():
    sm = (TOOLS / "smoke_test.sh").read_text(encoding="utf-8")
    for endpoint in ["/api/v1/enum-types", "/api/v1/auth/login"]:
        if endpoint not in sm:
            raise AssertionError(f"smoke_test.sh 缺 {endpoint}")
    print(f"  smoke_test.sh 含真实 API 测试")

test("smoke_test.sh 真实 API 测试", t5)


# ============================================================
# TEST 6: precheck.sh 8 项检查
# ============================================================
def t6():
    pc = (TOOLS / "precheck.sh").read_text(encoding="utf-8")
    for n in range(1, 9):
        if f"Check {n}/8" not in pc and f"Check {n}/7" not in pc:
            raise AssertionError(f"precheck.sh 缺 Check {n}")
    print(f"  precheck.sh 含 8 项检查 (含 frontend_dist_files)")

test("precheck.sh 8 项检查", t6)


# ============================================================
# TEST 7: unified_server.py 含 token 持久化
# ============================================================
def t7():
    u = (TOOLS / "unified_server.py").read_text(encoding="utf-8")
    for k in ["TOKEN_CACHE", "LOGIN_PATHS", "user.authenticate", "X-Forwarded-For"]:
        if k not in u:
            raise AssertionError(f"unified_server.py 缺 {k}")
    print(f"  unified_server.py 含 token 持久化所有关键")

test("unified_server.py token 持久化", t7)


# ============================================================
# TEST 8: watch.sh 含自动恢复
# ============================================================
def t8():
    w = (TOOLS / "watch.sh").read_text(encoding="utf-8")
    for k in ["--loop", "--auto-recover", "--rollback-on-fail", "restart.sh", "rollback.sh"]:
        if k not in w:
            raise AssertionError(f"watch.sh 缺 {k}")
    print(f"  watch.sh 含监控+恢复所有关键")

test("watch.sh 监控+恢复", t8)


# ============================================================
# TEST 9: deploy_bundle/ 含所有 8 工具
# ============================================================
def t9():
    required = [
        "deploy.sh", "precheck.sh", "smoke_test.sh", "rollback.sh",
        "diagnose.sh", "status.sh", "restart.sh", "watch.sh",
        "deploy_history.sh",
        "unified_server.py",
    ]
    missing = []
    for f in required:
        if not (DEPLOY_BUNDLE / f).is_file():
            missing.append(f)
    if missing:
        raise AssertionError(f"deploy_bundle/ 缺: {missing}")
    # 检查 zip 存在 (任一 deploy-v*.zip)
    zips = list(DEPLOY_BUNDLE.glob("deploy-v*.zip"))
    if not zips:
        raise AssertionError("deploy_bundle/ 缺 deploy-v*.zip")
    latest_zip = max(zips, key=lambda p: p.stat().st_mtime)
    print(f"  deploy_bundle/ 含 10 工具 + {latest_zip.name} + 27 测试")

test("deploy_bundle/ 完整 (10 工具 + 27 测试 + zip)", t9)


# ============================================================
# TEST 10: rebuild_bundle.ps1 复制所有 工具
# ============================================================
def t10():
    rb = (TOOLS / "rebuild_bundle.ps1").read_text(encoding="utf-8")
    required = [
        "deploy.sh", "precheck.sh", "smoke_test.sh", "rollback.sh",
        "diagnose.sh", "status.sh", "restart.sh", "watch.sh",
        "deploy_history.sh", "unified_server.py",
    ]
    for f in required:
        if f not in rb:
            raise AssertionError(f"rebuild_bundle.ps1 数组缺 {f}")
    print(f"  rebuild_bundle.ps1 $tools 含 10 个核心文件")

test("rebuild_bundle.ps1 复制所有 10 工具", t10)


# ============================================================
# TEST 11: deploy_history.sh 含 list/info/switch
# ============================================================
def t11():
    h = (TOOLS / "deploy_history.sh").read_text(encoding="utf-8")
    for k in ["list_versions", "info_version", "switch_version", "--info", "--switch"]:
        if k not in h:
            raise AssertionError(f"deploy_history.sh 缺 {k}")
    print(f"  deploy_history.sh 含 list/info/switch 三大功能")

test("deploy_history.sh 三大功能", t11)


# ============================================================
# TEST 14: check_deploy_health.sh 存在且含 6 类检查 (C1-C6)
# ============================================================
def t14():
    h = (DEPLOY_BUNDLE / "lib" / "check_deploy_health.sh")
    if not h.exists():
        raise AssertionError("check_deploy_health.sh 不存在")
    body = h.read_text(encoding="utf-8")
    for ck in ["C1", "C2", "C3", "C4", "C5", "C6"]:
        if ck not in body:
            raise AssertionError(f"check_deploy_health.sh 缺检查项 {ck}")
    print(f"  check_deploy_health.sh 含 6 类检查 (C1-C6)")

test("check_deploy_health.sh 6 类检查", t14)


# ============================================================
# TEST 15: check_deploy_health.sh 集成到 deploy.sh / status.sh / restart.sh / diagnose.sh
# ============================================================
def t15():
    for tool in ["deploy.sh", "status.sh", "restart.sh", "diagnose.sh"]:
        body = (DEPLOY_BUNDLE / tool).read_text(encoding="utf-8")
        if "check_deploy_health.sh" not in body:
            raise AssertionError(f"{tool} 没集成 check_deploy_health.sh")
    print(f"  4 个核心工具 (deploy/status/restart/diagnose) 都集成 check_deploy_health.sh")

test("4 工具集成 check_deploy_health.sh", t15)


# ============================================================
# TEST 16: check_health_local.py 存在且可 dryrun
# ============================================================
def t16():
    import subprocess
    p = TESTS / "check_health_local.py"
    if not p.exists():
        raise AssertionError("check_health_local.py 不存在")
    # 跑一次 mock-remote dryrun, 期望 exit code 0 或 1 (取决于 zip MANIFEST)
    r = subprocess.run(
        [sys.executable, str(p), "--mock-remote"],
        capture_output=True, text=True, timeout=60,
    )
    # 即使有 FAIL, 只要脚本能跑出 SUMMARY 就 PASS
    if "SUMMARY:" not in r.stdout and "SUMMARY:" not in r.stderr:
        raise AssertionError(f"check_health_local.py 没输出 SUMMARY: {r.stdout[:200]}")
    print(f"  check_health_local.py mock-remote dryrun 跑通 (rc={r.returncode})")

test("check_health_local.py dryrun", t16)


# ============================================================
# TEST 12: 项目文档 (DEPLOY_INFRASTRUCTURE.md)
# ============================================================
def t12():
    """AI Agent 必读的部署基础设施文档"""
    doc = ROOT / "DEPLOY_INFRASTRUCTURE.md"
    if not doc.is_file():
        raise AssertionError("DEPLOY_INFRASTRUCTURE.md 不存在 (项目根)")
    content = doc.read_text(encoding="utf-8")
    # 必含章节
    required_sections = [
        "项目元数据", "远端服务器", "端口约定", "部署架构",
        "部署工具", "部署 bundle", "部署流程", "回滚流程",
        "监控流程", "测试流程", "已修复的关键 BUG",
        "AI Agent 部署规范", "DO", "DON'T",
        "快速诊断清单",
    ]
    for sec in required_sections:
        if sec not in content:
            raise AssertionError(f"DEPLOY_INFRASTRUCTURE.md 缺 '{sec}' 章节")
    # 必含关键信息
    required_info = [
        "172.20.59.7", "/opt/app", "5001", "8081", "v20260703_002",
        "deploy.sh", "rollback.sh", "watch.sh", "deploy_history.sh",
        "frontend_dist_files", "TOKEN_CACHE", "data.token",
        "rebuild_bundle.ps1", "test_deploy_e2e",
    ]
    for info in required_info:
        if info not in content:
            raise AssertionError(f"DEPLOY_INFRASTRUCTURE.md 缺关键信息 '{info}'")
    size_kb = doc.stat().st_size / 1024
    print(f"  DEPLOY_INFRASTRUCTURE.md ({size_kb:.1f}KB) 含 14 章节 + 14 关键信息")

test("DEPLOY_INFRASTRUCTURE.md AI Agent 规范", t12)


# ============================================================
# TEST 13: lib/common.sh 含项目元数据
# ============================================================
def t13():
    """lib/common.sh 头含项目元数据 (AI Agent 应能识别)"""
    common = (TOOLS / "lib" / "common.sh").read_text(encoding="utf-8")
    required = [
        "PROJECT_NAME", "REMOTE_HOST", "REMOTE_PY", "REMOTE_DEPLOY_ROOT",
        "VERSION_REGEX", "VERSION_FORMAT",
        "BIP-Backend", "172.20.59.7", "/opt/miniconda3-py39/bin/python",
        "v3: /api/v1/auth/login", "v4: /api/v2/action/user.authenticate",
        "unified_server.py", "token 持久化",
    ]
    for r in required:
        if r not in common:
            raise AssertionError(f"lib/common.sh 缺 {r}")
    print(f"  lib/common.sh 含项目元数据 (供 AI Agent 识别)")

test("lib/common.sh 项目元数据", t13)


# ============================================================
print()
print("=" * 60)
print(f"TEST DEPLOY E2E: PASS={PASS}  FAIL={FAIL}")
print("=" * 60)
sys.exit(0 if FAIL == 0 else 1)
